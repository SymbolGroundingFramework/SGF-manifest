#!/usr/bin/env python3
"""
reranker.py — cross-encoder reranker for the lexicon search path

A second-pass scoring layer that re-ranks the top-N candidates produced
by the bi-encoder cosine search. Bi-encoders embed query and candidates
independently; cross-encoders score (query, candidate) PAIRS together
and catch interactions the cosine path misses. Cost trade: cross-
encoders are 100-1000x slower per pair, so we only run them on the
small set of top candidates the cheap cosine path already short-listed.

USED BY
-------
search_server.py (server side). The server checks its cascade config;
if reranker_enabled and the margin is below the configured threshold,
the server invokes this module to rescore the top-N candidates.

MODELS
------
BGE rerankers are cross-encoders that score (query, text) pairs.
Preference order:

    bge-reranker-v2-m3   (~2.3 GB)   best, multilingual (default)
    bge-reranker-large   (~1.1 GB)   strong English-only
    bge-reranker-base    (~280 MB)   smaller, faster, lower accuracy

LIGHTWEIGHT DEPLOYMENT
======================
This module uses HuggingFace's `tokenizers` library (Rust-based, fast,
no PyTorch/TensorFlow dependency) and `onnxruntime` for inference.
It does NOT use `transformers.AutoTokenizer` — that would add ~500MB
of dependencies and slow startup.

If the dependencies are not installed, the module degrades gracefully:
    reranker: missing dependency; reranker disabled.
              Run `pip install onnxruntime tokenizers huggingface_hub` to enable.

FIX APPLIED IN THIS VERSION
===========================
Line 165: Changed from f-string concatenation ("[SEP]") to proper paired
encoding via tokenizer.encode(q, pair=t). The BGE reranker expects the
[SEP] special token (ID 102) to be inserted by the tokenizer between
the query and candidate sequences. Without this, the model treats the
entire string as one blob and cannot distinguish which tokens belong
to the query vs. the candidate.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np


# Cached singletons so a long-running server does not re-download or
# re-load the ONNX model on every query.
_RERANKER_CACHE = {}


def load_reranker(preferred_models: List[str]) -> Optional[Tuple[str, object, object, int]]:
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
        from tokenizers import Tokenizer
        from huggingface_hub import hf_hub_download
    except ImportError as e:
        print(
            f"reranker: missing dependency ({e}); reranker disabled. "
            f"Run `pip install onnxruntime tokenizers huggingface_hub` "
            f"to enable."
        )
        _RERANKER_CACHE[cache_key] = None
        return None

    # Map short names to HuggingFace ONNX repos
    RERANKER_MODELS = {
        "bge-reranker-v2-m3": {
            "onnx_repo": "Xenova/bge-reranker-v2-m3",
            "tok_repo": "BAAI/bge-reranker-v2-m3",
            "max_length": 512,
            "onnx_file": "onnx/model.onnx",
            "tok_file": "tokenizer.json",
        },
        "bge-reranker-large": {
            "onnx_repo": "Xenova/bge-reranker-large",
            "tok_repo": "BAAI/bge-reranker-large",
            "max_length": 512,
            "onnx_file": "onnx/model.onnx",
            "tok_file": "tokenizer.json",
        },
        "bge-reranker-base": {
            "onnx_repo": "Xenova/bge-reranker-base",
            "tok_repo": "BAAI/bge-reranker-base",
            "max_length": 512,
            "onnx_file": "onnx/model.onnx",
            "tok_file": "tokenizer.json",
        },
    }

    for model_key in preferred_models:
        meta = RERANKER_MODELS.get(model_key)
        if meta is None:
            print(f"reranker: unknown model {model_key!r}; skipping")
            continue
        try:
            # Download tokenizer.json and ONNX model
            tok_path = hf_hub_download(meta["tok_repo"], meta["tok_file"])
            model_path = hf_hub_download(meta["onnx_repo"], meta["onnx_file"])

            # Load tokenizer (lightweight, no PyTorch)
            tokenizer = Tokenizer.from_file(tok_path)
            tokenizer.enable_truncation(meta["max_length"])
            tokenizer.enable_padding(length=meta["max_length"])

            # Load ONNX session
            session = ort.InferenceSession(
                model_path, providers=["CPUExecutionProvider"],
            )
            print(f"reranker: loaded {model_key}")
            result = (model_key, session, tokenizer, meta["max_length"])
            _RERANKER_CACHE[cache_key] = result
            return result
        except Exception as exc:
            print(f"reranker: failed to load {model_key}: {exc}; trying next")
            continue

    print("reranker: no model could be loaded; reranker disabled")
    _RERANKER_CACHE[cache_key] = None
    return None


def rerank(query_text: str, candidates: List[dict],
           preferred_models: Optional[List[str]] = None,
           text_field: str = "microgloss") -> List[dict]:
    """Rescore candidates with the best available cross-encoder reranker.

    Each candidate is a dict (server response shape). We score each
    (query, candidate text) pair, attach as candidate['rerank_score'],
    and return the list sorted descending by rerank_score.

    If no reranker loads, the input is returned unchanged.
    """
    if preferred_models is None:
        preferred_models = ["bge-reranker-v2-m3", "bge-reranker-large", "bge-reranker-base"]

    loaded = load_reranker(preferred_models)
    if loaded is None:
        return candidates
    if not candidates:
        return candidates

    model_key, session, tokenizer, max_length = loaded

    # Build (query, text) pairs
    pairs = [(query_text, _candidate_text(c, text_field)) for c in candidates]

    # ------------------------------------------------------------------
    # FIXED: Use proper paired encoding.
    #
    # Before: tokenizer.encode(f"{q} [SEP] {t}") — treats "[SEP]" as
    #         literal text tokens, not the special separator token.
    #
    # After:  tokenizer.encode(q, pair=t) — the tokenizer inserts the
    #         [CLS] and [SEP] special tokens correctly:
    #         [CLS] query_tokens [SEP] candidate_tokens [SEP]
    #
    # Without this fix, the BGE reranker treats the entire string as
    # one blob and cannot distinguish query from candidate, producing
    # unreliable scores.
    # ------------------------------------------------------------------
    encodings = [
        tokenizer.encode(q, pair=t)
        for q, t in pairs
    ]

    # Pad to max_length and convert to numpy arrays
    batch_size = len(encodings)
    input_ids = np.zeros((batch_size, max_length), dtype=np.int64)
    attention_mask = np.zeros((batch_size, max_length), dtype=np.int64)

    for i, enc in enumerate(encodings):
        ids = enc.ids[:max_length]
        length = len(ids)
        input_ids[i, :length] = ids
        attention_mask[i, :length] = 1

    # Run ONNX inference
    inputs = {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
    }
    # Check if the model expects token_type_ids
    try:
        # Some reranker ONNX models don't have token_type_ids
        outputs = session.run(None, inputs)
    except Exception:
        # Add token_type_ids if needed
        inputs["token_type_ids"] = np.zeros((batch_size, max_length), dtype=np.int64)
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


def _candidate_text(c: dict, text_field: str) -> str:
    """Best descriptive text for a candidate. Tries multiple fields
    in order of preference, falling back to canonical_id."""
    parts = []
    if c.get("lemma"):
        parts.append(str(c["lemma"]))
    if c.get("microgloss"):
        parts.append(str(c["microgloss"]))
    elif c.get(text_field) and text_field != "lemma":
        parts.append(str(c[text_field]))
    if c.get("pos_ud"):
        parts.append(f"({c['pos_ud']})")
    return " : ".join(parts) if parts else (c.get("canonical_id") or "")


# ---------------------------------------------------------------------------
# Self-test (run this file directly to verify it can load and score)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Quick smoke test — uses mock candidates so we can verify the module
    # loads and the function runs without crashing.
    test_candidates = [
        {"canonical_id": "en.bank.financial_institution.noun.synapedia_wordnet",
         "lemma": "bank", "microgloss": "financial institution",
         "pos_ud": "noun", "score": 0.85},
        {"canonical_id": "en.bank.river_side.noun.synapedia_wordnet",
         "lemma": "bank", "microgloss": "river side",
         "pos_ud": "noun", "score": 0.72},
    ]
    # Try to load a reranker; if not available, just verify the function
    # returns the input unchanged.
    result = rerank("river bank", test_candidates)
    print(f"Reranker test: {len(result)} candidates returned")
    for c in result:
        has_score = "rerank_score" in c
        print(f"  {c['canonical_id'][:40]:40s} reranked={has_score}")
    print("RERANKER CHECK COMPLETE")