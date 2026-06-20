#!/usr/bin/env python3
"""
reranker.py -- cross-encoder reranker for the lexicon search path

A second-pass scoring layer that re-ranks the top-N candidates produced
by the bi-encoder cosine search. Bi-encoders embed query and candidates
independently; cross-encoders score (query, candidate) PAIRS together
and catch interactions the cosine path misses. Cost trade: cross-
encoders are 100-1000x slower per pair, so we only run them on the
small set of top candidates the cheap cosine path already short-listed.

USED BY
-------
glean_search.py (client side). The CLI checks its config file; if
reranker_enabled and the top-1/top-2 margin is below the configured
threshold (or rerank_always is set), the client invokes this module
to rescore the top-N candidates and re-orders them by reranker score
before printing.

MODELS
------
BGE ships three reranker sizes. We prefer the most accurate one
available:

    bge-reranker-v2-m3   (~2.3 GB)   best, multilingual (default)
    bge-reranker-large   (~1.1 GB)   strong English-only
    bge-reranker-base    (~280 MB)   smaller, faster, lower accuracy

The config file declares a preference list. We walk it and use the
first model that is loadable. Stateless models -- no 'coverage'
concept like embedders have; rerankers either work or they don't.
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np


# Cached singletons so a long-running client does not re-download or
# re-load the ONNX model on every query.
_RERANKER_CACHE = {}


# ---------------------------------------------------------------------------
# Reranker model registry. Mirrors the embedder registry shape so it is
# easy to swap, extend, or downgrade.
# ---------------------------------------------------------------------------

# Each entry lists candidate ONNX filenames to try in order. Some BGE
# rerankers are sharded (an .onnx index file PLUS a separate .onnx_data
# weights file). For those we declare the companion file too and
# download both.
RERANKER_MODELS = {
    "bge-reranker-v2-m3": {
        "model_repo": "BAAI/bge-reranker-v2-m3",
        "tokenizer_repo": "BAAI/bge-reranker-v2-m3",
        "max_length": 512,
        "size_label": "~2.3 GB, multilingual, most accurate",
        "onnx_candidates": [("onnx/model.onnx", "onnx/model.onnx_data"),
                            ("model.onnx", None)],
    },
    "bge-reranker-large": {
        "model_repo": "BAAI/bge-reranker-large",
        "tokenizer_repo": "BAAI/bge-reranker-large",
        "max_length": 512,
        "size_label": "~1.1 GB, English, strong",
        "onnx_candidates": [("onnx/model.onnx", "onnx/model.onnx_data"),
                            ("model.onnx", "model.onnx_data")],
    },
    "bge-reranker-base": {
        "model_repo": "BAAI/bge-reranker-base",
        "tokenizer_repo": "BAAI/bge-reranker-base",
        "max_length": 512,
        "size_label": "~280 MB, English, lightweight",
        "onnx_candidates": [("onnx/model.onnx", None),
                            ("model.onnx", None)],
    },
}


def load_reranker(preferred_models):
    """Load the first reranker model in the preference list that succeeds.

    Returns (model_key, session, tokenizer, max_length) or None.
    Cached across calls so re-querying does not re-download or re-init.
    """
    cache_key = tuple(preferred_models)
    if cache_key in _RERANKER_CACHE:
        return _RERANKER_CACHE[cache_key]

    # Lazy imports so this module is importable without onnxruntime
    # for users who never enable reranking.
    try:
        import onnxruntime as ort
        from transformers import AutoTokenizer
        from huggingface_hub import hf_hub_download
    except ImportError:
        print(
            "reranker: onnxruntime + transformers + huggingface_hub not "
            "installed; reranker disabled. Run "
            "`pip install onnxruntime transformers huggingface_hub` to enable."
        )
        _RERANKER_CACHE[cache_key] = None
        return None

    for model_key in preferred_models:
        meta = RERANKER_MODELS.get(model_key)
        if meta is None:
            print(f"reranker: unknown model {model_key!r}; skipping")
            continue
        try:
            tokenizer = AutoTokenizer.from_pretrained(meta["tokenizer_repo"])
            model_path = _download_onnx_pair(
                hf_hub_download,
                meta["model_repo"],
                meta.get("onnx_candidates", [("onnx/model.onnx", None)]),
            )
            if model_path is None:
                print(f"reranker: {model_key} has no downloadable ONNX "
                      f"build; trying next")
                continue
            session = ort.InferenceSession(
                model_path, providers=["CPUExecutionProvider"],
            )
            print(f"reranker: loaded {model_key} ({meta['size_label']})")
            result = (model_key, session, tokenizer, meta["max_length"])
            _RERANKER_CACHE[cache_key] = result
            return result
        except Exception as exc:
            print(f"reranker: failed to load {model_key}: {exc}; trying next")
            continue

    print("reranker: no model could be loaded; reranker disabled")
    _RERANKER_CACHE[cache_key] = None
    return None


def _download_onnx_pair(hf_hub_download, repo, candidates):
    """Try each (index, data) ONNX filename pair in order.

    For sharded models, the data file must download successfully too --
    otherwise onnxruntime fails when it tries to read the missing
    weights. Returns the local path to the index file, or None.
    """
    for pair in candidates:
        index_name = pair[0]
        data_name = pair[1] if len(pair) > 1 else None
        try:
            model_path = hf_hub_download(repo, filename=index_name)
        except Exception:
            continue
        if data_name:
            try:
                hf_hub_download(repo, filename=data_name)
            except Exception:
                # Index downloaded but weights file missing. Unusable.
                continue
        return model_path
    return None


def rerank(query_text, candidates, preferred_models, text_field="microgloss"):
    """Rescore candidates with the best available cross-encoder reranker.

    Each candidate is a dict (server response shape). We score each
    (query, candidate text) pair, attach as candidate['rerank_score'],
    and return the list sorted descending by rerank_score.

    If no reranker loads, the input is returned unchanged.
    """
    loaded = load_reranker(preferred_models)
    if loaded is None:
        return candidates
    if not candidates:
        return candidates

    model_key, session, tokenizer, max_length = loaded

    pairs = [(query_text, _candidate_text(c, text_field)) for c in candidates]
    enc = tokenizer(
        [p[0] for p in pairs],
        [p[1] for p in pairs],
        padding=True, truncation=True, max_length=max_length,
        return_tensors="np",
    )
    inputs = {
        "input_ids":      enc["input_ids"].astype(np.int64),
        "attention_mask": enc["attention_mask"].astype(np.int64),
    }
    if "token_type_ids" in enc:
        inputs["token_type_ids"] = enc["token_type_ids"].astype(np.int64)

    outputs = session.run(None, inputs)
    logits = outputs[0]
    if logits.ndim == 2 and logits.shape[1] == 1:
        scores = logits[:, 0]
    else:
        scores = logits.squeeze()

    # Sigmoid so scores live in [0, 1] and are comparable across runs.
    scores = 1.0 / (1.0 + np.exp(-scores))

    for c, s in zip(candidates, scores):
        c["rerank_score"] = float(s)
        c["rerank_model"] = model_key
    return sorted(candidates, key=lambda c: c["rerank_score"], reverse=True)


def _candidate_text(c, text_field):
    """Best descriptive text for a candidate."""
    parts = []
    if c.get("lemma"):
        parts.append(str(c["lemma"]))
    val = c.get(text_field) or c.get("microgloss") or c.get("canonical_id")
    if val:
        parts.append(str(val))
    return " : ".join(parts) if parts else (c.get("canonical_id") or "")
