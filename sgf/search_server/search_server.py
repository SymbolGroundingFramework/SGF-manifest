#!/usr/bin/env python3
"""
search_server.py  — Synapedia v7 Search Server (synchronous improvement, incremental update, compound decomposition)
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import secrets
import sqlite3
import struct
import subprocess
import sys
import threading
import time as _time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

try:
    from fastapi import FastAPI, HTTPException, Header, Request
    from pydantic import BaseModel, Field
    import uvicorn
except ImportError:
    print("ERROR: fastapi + uvicorn + pydantic required. Install with: pip install fastapi uvicorn pydantic", file=sys.stderr)
    sys.exit(2)

import numpy as np

# ---------------------------------------------------------------------------
# Timing helper
# ---------------------------------------------------------------------------
def _print_timing(label, t_start, threshold_ms=1.0):
    elapsed_ms = (_time.time() - t_start) * 1000
    if elapsed_ms >= threshold_ms:
        print(f"[TIMING] {label}: {elapsed_ms:.1f}ms", flush=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GLEAN_HOME = Path(os.environ.get("GLEAN_HOME", str(Path.home() / ".glean")))
BUNDLE_DIR = Path(__file__).resolve().parent
POLICY_FILENAMES = ("search_config.toml", "retrieval_policy.toml", "policy.toml")
DEFAULT_POLICY_PATH = GLEAN_HOME / POLICY_FILENAMES[0]
DEFAULT_AUTH_PATH = GLEAN_HOME / "auth.toml"
DEFAULT_DEFINITION_TIER = "CORE_ONTOLOGY"
DEFAULT_SOURCE_TYPE = "core"
DEFAULT_BATCH_EMBED_SIZE = 128
DEFAULT_BATCH_EMBED_FORCE = False
DEFAULT_EMBEDDER_DEVICE = "auto"

TIER_RANK_MAP = {
    "CORE_ONTOLOGY": 1, "CORE_KNOWLEDGE": 2, "LEXICAL_EXTENSION": 3,
    "CLAIMED": 4, "INFERRED": 5, "PROVISIONAL": 6, "GHOST": 7,
}
TIER_BONUS_MAP = {
    "CORE_ONTOLOGY": 0.15, "CORE_KNOWLEDGE": 0.10, "LEXICAL_EXTENSION": 0.05,
    "CLAIMED": 0.00, "INFERRED": -0.05, "PROVISIONAL": -0.10, "GHOST": -0.20,
}
LEGACY_TIER_MAP = {"raw": 99, "provisional": 6, "embedded_v1": 5,
    "improved": 3, "embedded_v2": 4, "clustered": 2, "related": 1}

DEFAULT_RERANKER_CFG = {
    "enabled": False, "models": ["bge-reranker-v2-m3", "bge-reranker-large", "bge-reranker-base"],
    "top_n": 20, "rerank_always": False, "margin_threshold": 0.05,
}
DEFAULT_BM25_CFG = {
    "mode": "never", "margin_threshold": 0.04, "abs_confidence_floor": 0.0,
    "top_n_out": 3, "fusion": "weighted", "weighted_alpha": 0.7,
    "stemmer": "porter", "lowercase": True,
}
DEFAULT_TIEBREAK_CFG = {
    "mode": "never", "margin_threshold": 0.03, "abs_confidence_floor": 0.0,
    "divergent_axes": ["definition_tier", "source_type"],
    "llm_wrapper": "llm_wrapper.py", "tier": "flash", "temp": 0.0,
    "top_n_to_llm": 5, "server_enabled": False, "client_enabled": False,
}

DEFAULT_IMPROVE_CFG = {
    "enabled": False,
    "top_n_to_improve": 5,
    "script_path": "improve_glossary_and_ontology.py",
    "embed_service_url": "http://localhost:18401",
    "llm_source": "cloud",
    "model": None,
    "max_attempts": 1,
    "generate_ontology": True,
    "generate_events": True,
    "avoid_floating_nodes": True,
    "search_server_url": "http://localhost:8400",
}

# Compound minting constants
COMPOUND_THRESHOLD = 0.5          # if top result raw_cosine < this, try compound decomposition
IMPROVEMENT_THRESHOLD = 0.6       # if known compounds push score >= this, skip minting
MINT_SCRIPT = "mint_compound.py"

BUILT_IN_CASCADE = {
    "default":      ["bge-large-en-v1"],
    "en":           ["bge-large-en-v1"],
    "multilingual": ["bge-large-en-v1"],
}

logger = logging.getLogger("glean_search")

def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s [%(name)s] %(message)s", datefmt="%H:%M:%S")

# ---------------------------------------------------------------------------
# Cache for lemma-group improvement (module-level)
# ---------------------------------------------------------------------------
_improved_lemmas: set = set()  # set of lemmas (lowercase) whose entire lemma group has been improved

# ---------------------------------------------------------------------------
# Cache for failed mint attempts (phrase → timestamp)
# Prevents retry loops when mint_compound.py times out or fails.
# ---------------------------------------------------------------------------
_failed_mints: dict = {}
_FAILED_MINT_TTL: float = 300.0  # 5 minutes before retry

# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------
@dataclass
class Policy:
    name: str
    rewrite_to_standard_form: bool
    preserve_specialist_terms: bool
    audience_tier: str
    exclude_social_status: List[str]
    exclude_temporal_status: List[str]
    snap_social_status: List[str]
    snap_temporal_status: List[str]
    on_snap_failure: str
    min_tier_returned: str
    demote_register: Dict[str, float]
    demote_temporal: Dict[str, float]
    demote_social: Dict[str, float]

    @classmethod
    def from_dict(cls, name: str, d: dict) -> "Policy":
        return cls(
            name=name,
            rewrite_to_standard_form=bool(d.get("rewrite_to_standard_form", True)),
            preserve_specialist_terms=bool(d.get("preserve_specialist_terms", True)),
            audience_tier=str(d.get("audience_tier", "general")),
            exclude_social_status=list(d.get("exclude_social_status", [])),
            exclude_temporal_status=list(d.get("exclude_temporal_status", [])),
            snap_social_status=list(d.get("snap_social_status", [])),
            snap_temporal_status=list(d.get("snap_temporal_status", [])),
            on_snap_failure=str(d.get("on_snap_failure", "drop")),
            min_tier_returned=str(d.get("min_tier_returned", "CORE_ONTOLOGY")),
            demote_register=dict(d.get("demote_register", {})),
            demote_temporal=dict(d.get("demote_temporal", {})),
            demote_social=dict(d.get("demote_social", {})),
        )

    def merge_overrides(self, overrides: Optional[dict]) -> "Policy":
        if not overrides:
            return self
        merged = self.__dict__.copy()
        for k, v in overrides.items():
            if k in merged:
                merged[k] = v
        merged["name"] = f"{self.name}+override"
        return Policy(**merged)

def _first_existing(directory: Path, filenames):
    for fn in filenames:
        p = directory / fn
        if p.exists():
            return p
    return None

def resolve_policy_path(explicit_path=None, config_dir=None):
    if explicit_path:
        ep = Path(explicit_path)
        if ep.exists() or not ep.parent.exists() or ep.parent != GLEAN_HOME:
            return ep
    if config_dir:
        found = _first_existing(Path(config_dir), POLICY_FILENAMES)
        if found is not None:
            return found
    bundle_found = _first_existing(BUNDLE_DIR, POLICY_FILENAMES)
    if bundle_found is not None:
        return bundle_found
    legacy_home = GLEAN_HOME / "policy.toml"
    if legacy_home.exists() and not DEFAULT_POLICY_PATH.exists():
        return legacy_home
    return DEFAULT_POLICY_PATH

def write_default_policy_file(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")

def load_policies(path: Path):
    if not path.exists():
        logger.warning(f"Policy file not found at {path}; writing defaults.")
        write_default_policy_file(path)
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    cfg = raw.get("retrieval", raw)
    default_name = cfg.get("default_policy", "snap_to_standard")
    policies_data = cfg.get("policies", {})
    if not policies_data:
        policies_data = {}
    out: Dict[str, Policy] = {}
    for name, pd in policies_data.items():
        out[name] = Policy.from_dict(name, pd)
    if out:
        out["__default__"] = out.get(default_name) or next(iter(out.values()))
    else:
        out["__default__"] = Policy.from_dict("snap_to_standard", {})
    cascade_cfg = cfg.get("embedder_cascade", {})
    cascade = {**BUILT_IN_CASCADE, **{k: list(v) for k, v in cascade_cfg.items()}}
    min_coverage = float(cfg.get("embedder_min_coverage", 0.95))
    return out, cascade, min_coverage

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def generate_token() -> str:
    raw = secrets.token_bytes(15)
    return base64.b32encode(raw).decode("ascii").rstrip("=")

def load_or_create_auth(path: Path) -> str:
    if path.exists():
        with open(path, "rb") as f:
            cfg = tomllib.load(f)
        return cfg.get("api_token", "")
    token = generate_token()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'api_token = "{token}"\n', encoding="utf-8")
    logger.warning(f"Generated new auth token at {path}")
    return token

# ---------------------------------------------------------------------------
# Lexicon backend
# ---------------------------------------------------------------------------
@dataclass
class EmbedderState:
    method: str
    dim: int
    entry_ids: List[int]
    vectors: np.ndarray
    entry_id_to_idx: Dict[int, int] = field(default_factory=dict)

@dataclass
class SenseRecord:
    entry_id: int
    lemma: str
    pos_ud: str
    microgloss: str
    canonical_id: str
    definition_tier: str
    source_type: str
    definition_tier_rank: int = 99

def vec_from_blob(blob: bytes) -> List[float]:
    n = len(blob) // 4
    if n == 0:
        return []
    return list(struct.unpack(f"<{n}f", blob))

def vec_to_blob(v: List[float]) -> bytes:
    if not v:
        return b""
    return struct.pack(f"<{len(v)}f", *v)

class LexiconBackend:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.senses: Dict[int, SenseRecord] = {}
        self.embedders: Dict[str, EmbedderState] = {}
        self.tier_counts: Dict[str, int] = {}
        self.source_types: set[str] = set()
        self.lemma_index: Dict[str, List[int]] = {}
        self._porter_stemmer_available = False
        try:
            from bm25_score import porter_stem
            self._porter_stemmer = porter_stem
            self._porter_stemmer_available = True
        except ImportError:
            self._porter_stemmer_available = False

    def load_all(self):
        t0 = _time.time()
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA query_only = 1")
        cur = conn.cursor()
        cur.execute("""
            SELECT entry_id, lemma, pos_ud, microgloss, canonical_id,
                   definition_tier, source_type
            FROM synapedia_entry
            WHERE canonical_id IS NOT NULL
        """)
        rows = cur.fetchall()
        for row in rows:
            entry_id, lemma, pos_ud, microgloss, canonical_id, \
                definition_tier, source_type = row
            if microgloss is None:
                microgloss = ""
            if definition_tier is None:
                definition_tier = DEFAULT_DEFINITION_TIER
            if source_type is None:
                source_type = DEFAULT_SOURCE_TYPE
            rank = TIER_RANK_MAP.get(definition_tier, 99)
            sr = SenseRecord(
                entry_id=entry_id, lemma=lemma, pos_ud=pos_ud,
                microgloss=microgloss, canonical_id=canonical_id,
                definition_tier=definition_tier, source_type=source_type,
                definition_tier_rank=rank,
            )
            self.senses[entry_id] = sr
            self.tier_counts[definition_tier] = self.tier_counts.get(definition_tier, 0) + 1
            self.source_types.add(source_type)
            self.lemma_index.setdefault(lemma.lower(), []).append(entry_id)
        logger.info(f"  Loaded {len(self.senses):,} senses")

        DEFAULT_EMBEDDER = "bge-large-en-v1"
        cur.execute("""
            SELECT entry_id, embedding
            FROM synapedia_entry
            WHERE embedding IS NOT NULL
        """)
        entry_ids: List[int] = []
        vectors_list: List[List[float]] = []
        for entry_id, blob in cur:
            if entry_id not in self.senses:
                continue
            v = vec_from_blob(blob)
            if len(v) == 0:
                continue
            entry_ids.append(entry_id)
            vectors_list.append(v)
        if vectors_list:
            dim = len(vectors_list[0])
            vectors_np = np.array(vectors_list, dtype=np.float32)
            state = EmbedderState(
                method=DEFAULT_EMBEDDER, dim=dim,
                entry_ids=entry_ids, vectors=vectors_np,
                entry_id_to_idx={eid: i for i, eid in enumerate(entry_ids)},
            )
            self.embedders[DEFAULT_EMBEDDER] = state
            logger.info(f"  Embedder {DEFAULT_EMBEDDER}: {len(entry_ids):,} senses, dim={dim}")
        else:
            logger.warning("  No embeddings found in synapedia_entry.embedding")
        conn.close()
        logger.info(f"Lexicon fully loaded in {_time.time()-t0:.1f}s")

    def lookup_by_canonical_id(self, cid: str) -> Optional[SenseRecord]:
        for s in self.senses.values():
            if s.canonical_id == cid:
                return s
        return None

    # ===================================================================
    # FIXED topk() — Always includes exact lemma matches
    # ===================================================================
    def topk(self, query_vec: List[float], method: str, k: int,
             lemma_restrict: Optional[str] = None,
             auto_resolve_forms: bool = False,
             db_path: Optional[str] = None,
             pos_restrict: Optional[str] = None) -> List[Tuple[int, float]]:
        """
        Return top-k entries by cosine similarity.
        
        When lemma_restrict is set, ALL exact matches for the lemma are
        guaranteed to be included in the results, even if their raw cosine
        score is below the top-k threshold. This allows apply_policy() to
        apply the lemma_exact_bonus to boost them to the top.
        
        Edge cases handled:
        - No lemma_restrict: normal behavior, no change
        - Lemma not in index: no exact matches, no change
        - Lemma has no embeddings: filtered out harmlessly
        - All exact matches already in top-k: no duplicates
        - Multi-word lemmas: lemma_index keys are full lemmas, works correctly
        - Empty result: returns [] as before
        """
        emb = self.embedders.get(method)
        if emb is None:
            return []
        
        candidate_entry_ids: List[int] = []
        exact_match_ids: set = set()  # Track exact lemma matches
        
        if lemma_restrict:
            wanted = [lemma_restrict.lower()]
            if auto_resolve_forms and db_path:
                try:
                    import lemma_resolver
                    expanded = list(wanted)
                    seen = set(expanded)
                    for surface in wanted:
                        for lemma in lemma_resolver.expand_to_lemmas(
                            surface, db_path, prefer_pos=pos_restrict
                        ):
                            if lemma not in seen:
                                expanded.append(lemma)
                                seen.add(lemma)
                    wanted = expanded
                except (ImportError, Exception):
                    pass

            # Step 1: Collect exact lemma matches
            for lemma in wanted:
                candidate_entry_ids.extend(self.lemma_index.get(lemma, []))
            existing = set(candidate_entry_ids)
            exact_match_ids = set(existing)  # Remember exact matches
            
            # Step 2: Stemmer fallback (if no exact matches found)
            if not candidate_entry_ids and self._porter_stemmer_available:
                stemmed = self._porter_stemmer(lemma_restrict.lower())
                if stemmed != lemma_restrict.lower():
                    for eid in self.lemma_index.get(stemmed, []):
                        if eid not in existing:
                            candidate_entry_ids.append(eid)
                            existing.add(eid)
            
            # Step 3: Fuzzy matches — multi-word lemmas containing the focus word
            for lemma, eids in self.lemma_index.items():
                words = lemma.lower().split()
                # Case 1: focus word appears as a word in a multi-word lemma
                if lemma_restrict.lower() in words:
                    for eid in eids:
                        if eid not in existing:
                            candidate_entry_ids.append(eid)
                            existing.add(eid)
                # Case 2: focus word is a substring of the lemma
                elif lemma_restrict.lower() in lemma.lower() and len(lemma_restrict) >= 4:
                    for eid in eids:
                        if eid not in existing:
                            candidate_entry_ids.append(eid)
                            existing.add(eid)

        if not candidate_entry_ids and not lemma_restrict:
            candidate_entry_ids = list(emb.entry_id_to_idx.keys())
        elif not candidate_entry_ids and lemma_restrict:
            return []
        
        # Filter to only entries that have embeddings
        candidate_idxs = [
            emb.entry_id_to_idx[eid]
            for eid in candidate_entry_ids
            if eid in emb.entry_id_to_idx
        ]
        if not candidate_idxs:
            return []
        
        query_np = np.array(query_vec, dtype=np.float32)
        vecs_np = emb.vectors[candidate_idxs]
        scores = np.dot(vecs_np, query_np)
        top_relative = np.argsort(scores)[::-1][:k]
        
        result: List[Tuple[int, float]] = []
        result_set: set = set()
        for pos in top_relative:
            actual_idx = candidate_idxs[int(pos)]
            eid = emb.entry_ids[actual_idx]
            result.append((eid, float(scores[int(pos)])))
            result_set.add(eid)
        
        # ================================================================
        # FIX: Always include exact lemma matches that were below top-k
        # ================================================================
        if lemma_restrict and exact_match_ids:
            added = 0
            for eid in exact_match_ids:
                if eid not in result_set and eid in emb.entry_id_to_idx:
                    idx = emb.entry_id_to_idx[eid]
                    score = float(np.dot(emb.vectors[idx], query_np))
                    result.append((eid, score))
                    result_set.add(eid)
                    added += 1
            if added > 0:
                logger.info(
                    "topk: Added %d exact lemma matches for '%s' "
                    "that were below top-%d cosine threshold",
                    added, lemma_restrict, k
                )
        
        return result

    def embedder_coverage(self, method: str) -> float:
        n_total = len(self.senses)
        if n_total == 0:
            return 0.0
        emb = self.embedders.get(method)
        if emb is None:
            return 0.0
        return len(emb.entry_ids) / n_total

    def embedder_status(self, method: str, min_coverage: float = 0.95) -> str:
        c = self.embedder_coverage(method)
        if c >= min_coverage:
            return "complete"
        if c >= 0.001:
            return "partial"
        return "empty"

    def cascade_for_language(self, language: str, cascade_config: Dict[str, List[str]], min_coverage: float = 0.95) -> List[str]:
        lang_key = (language or "").lower()
        if lang_key in ("en", "english"):
            preferred = cascade_config.get("en", [])
        else:
            preferred = cascade_config.get("multilingual", [])
        if not preferred:
            preferred = cascade_config.get("default", [])
        ordered = [m for m in preferred if m in self.embedders and self.embedder_coverage(m) >= min_coverage]
        if not ordered and self.embedders:
            best = max(self.embedders.keys(), key=lambda m: self.embedder_coverage(m))
            ordered = [best]
        return ordered

    def best_embedder_for_language(self, language: str = "en") -> Optional[str]:
        cascade = self.cascade_for_language(language, getattr(self, "_cascade_config", BUILT_IN_CASCADE))
        return cascade[0] if cascade else None

# ---------------------------------------------------------------------------
# Policy application
# ---------------------------------------------------------------------------
def apply_policy(
    sense_id_and_score: List[Tuple[int, float]],
    backend: LexiconBackend,
    policy: Policy,
    lemma_restrict: Optional[str] = None,
    pos_restrict: Optional[str] = None,
    lemma_exact_bonus: float = 0.20,
    pos_bonus: float = 0.10,
) -> List[Dict[str, Any]]:
    min_rank = TIER_RANK_MAP.get(policy.min_tier_returned)
    if min_rank is None:
        min_rank = LEGACY_TIER_MAP.get(policy.min_tier_returned, 0)
    out: List[Dict[str, Any]] = []
    for entry_id, raw_score in sense_id_and_score:
        sense = backend.senses.get(entry_id)
        if sense is None:
            continue
        if sense.definition_tier_rank > min_rank:
            continue
        if pos_restrict and sense.pos_ud.upper() != pos_restrict.upper():
            continue
        penalty = 0.0
        score = raw_score - penalty
        lemma_bonus_applied = 0.0
        pos_bonus_applied = 0.0
        if lemma_restrict and sense.lemma.lower() == lemma_restrict.lower():
            score += lemma_exact_bonus
            lemma_bonus_applied = lemma_exact_bonus
        if pos_restrict and sense.pos_ud.upper() == pos_restrict.upper():
            score += pos_bonus
            pos_bonus_applied = pos_bonus
        tier_bonus = TIER_BONUS_MAP.get(sense.definition_tier, 0.0)
        score += tier_bonus
        out.append({
            "entry_id": sense.entry_id, "canonical_id": sense.canonical_id,
            "lemma": sense.lemma, "pos_ud": sense.pos_ud,
            "microgloss": sense.microgloss, "score": round(score, 6),
            "raw_cosine": round(raw_score, 6), "penalty": round(penalty, 6),
            "lemma_bonus": round(lemma_bonus_applied, 6),
            "pos_bonus": round(pos_bonus_applied, 6),
            "tier_bonus": round(tier_bonus, 6),
            "definition_tier": sense.definition_tier, "source_type": sense.source_type,
        })
    out.sort(key=lambda r: r["score"], reverse=True)
    return out

# ---------------------------------------------------------------------------
# EmbedderProxy
# ---------------------------------------------------------------------------
class EmbedderProxy:
    def __init__(self, preload_method: Optional[str] = None, device: Optional[str] = None):
        self.device = device or DEFAULT_EMBEDDER_DEVICE
        self._cache: Dict[str, Any] = {}
        self._available = self._probe()
        if self._available and preload_method:
            logger.info(f"Preloading embedder: {preload_method} (device mode: {self.device})...")
            t0 = _time.time()
            self.batch_embed(["warmup"], preload_method)
            logger.info(f"Embedder loaded in {_time.time()-t0:.1f}s")

    def _probe(self) -> bool:
        try:
            import onnxruntime
            return True
        except ImportError:
            logger.warning("onnxruntime not installed; /embed endpoint disabled.")
            return False

    def _resolve_providers(self) -> List[str]:
        try:
            import onnxruntime
            avail = onnxruntime.get_available_providers()
        except Exception:
            return ["CPUExecutionProvider"]

        dev = (self.device or DEFAULT_EMBEDDER_DEVICE).lower()
        if dev in ("cuda", "auto") and "CUDAExecutionProvider" in avail:
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]
        if dev in ("rocm", "auto") and "ROCMExecutionProvider" in avail:
            return ["ROCMExecutionProvider", "CPUExecutionProvider"]
        if dev in ("cuda", "rocm"):
            logger.warning(f"Device '{dev}' requested, but corresponding execution provider not available in ONNX runtime ({avail}). Falling back to CPU.")
        return ["CPUExecutionProvider"]

    def available(self) -> bool:
        return self._available

    def embed(self, text: str, method: str) -> List[float]:
        return self.batch_embed([text], method)[0]

    def batch_embed(self, texts: List[str], method: str) -> List[List[float]]:
        import onnxruntime
        from tokenizers import Tokenizer
        from huggingface_hub import hf_hub_download
        import numpy as np
        repo_map = {
            "bge-large-en-v1": ("Xenova/bge-large-en-v1.5", "BAAI/bge-large-en-v1.5"),
        }
        onnx_repo, tok_repo = repo_map.get(method, ("Xenova/bge-large-en-v1.5", "BAAI/bge-large-en-v1.5"))
        batch_key = f"{method}_batch"
        if batch_key not in self._cache:
            onnx_path = hf_hub_download(onnx_repo, "onnx/model.onnx")
            tok_path = hf_hub_download(tok_repo, "tokenizer.json")
            providers = self._resolve_providers()
            sess = onnxruntime.InferenceSession(onnx_path, providers=providers)
            logger.info(f"Initialized ONNX session for '{method}' on providers: {sess.get_providers()}")
            tok = Tokenizer.from_file(tok_path)
            tok.enable_truncation(max_length=256)
            tok.enable_padding(length=256)
            self._cache[batch_key] = (sess, tok)
        else:
            sess, tok = self._cache[batch_key]
        encodings = [tok.encode(t) for t in texts]
        batch_ids = np.array([e.ids for e in encodings], dtype="int64")
        batch_mask = np.array([e.attention_mask for e in encodings], dtype="int64")
        batch_ttype = np.array([e.type_ids for e in encodings], dtype="int64")
        ort_in = {
            "input_ids": batch_ids, "attention_mask": batch_mask, "token_type_ids": batch_ttype,
        }
        out = sess.run(None, ort_in)[0][:, 0, :]
        norms = np.linalg.norm(out, axis=1, keepdims=True) + 1e-12
        out = out / norms
        return out.tolist()

# ---------------------------------------------------------------------------
# Cascade stage helpers
# ---------------------------------------------------------------------------
def _run_reranker_stage(query_text, candidates, rr_cfg):
    if not rr_cfg.get("enabled"):
        return None, None
    if not candidates or not query_text:
        return None, None
    try:
        import reranker as rk
        top_n = int(rr_cfg.get("top_n", 20))
        always = bool(rr_cfg.get("rerank_always", False))
        margin_th = float(rr_cfg.get("margin_threshold", 0.05))
        from bm25_score import normalized_margin
        prior_scores = [r.get("score", 0.0) for r in candidates]
        margin = normalized_margin(prior_scores)
        if not always and (margin is not None and margin >= margin_th):
            return None, None
        rescored = rk.rerank(query_text, list(candidates[:top_n]), rr_cfg.get("models", ["bge-reranker-v2-m3"]))
        model_name = rescored[0].get("rerank_model") if rescored else None
        return model_name, (rescored + candidates[top_n:])
    except Exception as e:
        logger.warning(f"Reranker stage failed: {e}; skipping")
        return None, None

def _run_bm25_stage(query_text, candidates, bm25_cfg, alpha_override=None, reranker_applied=None):
    bm25_mode = (bm25_cfg.get("mode") or "never").lower()
    if bm25_mode == "never" or not candidates or not query_text:
        return False, None
    try:
        import bm25_score as _bm
        bm25_margin_th = float(bm25_cfg.get("margin_threshold", 0.04))
        bm25_abs_floor = float(bm25_cfg.get("abs_confidence_floor", 0.0))
        bm25_top_n_out = int(bm25_cfg.get("top_n_out", 3))
        if reranker_applied and any("rerank_score" in r for r in candidates):
            prior_scores = [r.get("rerank_score", r.get("score", 0.0)) for r in candidates]
        else:
            prior_scores = [r.get("score", 0.0) for r in candidates]
        top1_score = prior_scores[0] if prior_scores else 0.0
        margin_tight = _bm.normalized_margin(prior_scores) < bm25_margin_th
        abs_low = bm25_abs_floor > 0.0 and top1_score < bm25_abs_floor
        fire_bm25 = (bm25_mode == "always" or (bm25_mode == "when_tight" and (margin_tight or abs_low)))
        if not fire_bm25:
            return False, None
        cand_texts = [_candidate_text_for_bm25(r) for r in candidates]
        bm25_raw = _bm.score_candidates(query_text, cand_texts, bm25_cfg)
        fusion = (bm25_cfg.get("fusion") or "weighted").lower()
        if fusion == "sequential":
            order = sorted(range(len(candidates)), key=lambda i: bm25_raw[i], reverse=True)
        else:
            alpha = alpha_override if alpha_override is not None else float(bm25_cfg.get("weighted_alpha", 0.7))
            prior_norm = _bm.normalize_minmax(prior_scores)
            bm25_norm = _bm.normalize_minmax(bm25_raw)
            fused = _bm.fuse_weighted(prior_norm, bm25_norm, alpha)
            order = sorted(range(len(candidates)), key=lambda i: fused[i], reverse=True)
        new_results = []
        for old_idx in order:
            r = dict(candidates[old_idx])
            r["bm25_score"] = bm25_raw[old_idx]
            new_results.append(r)
        results = new_results[:bm25_top_n_out] + new_results[bm25_top_n_out:]
        return True, results
    except Exception as e:
        logger.warning(f"BM25 stage failed: {e}; skipping")
        return False, None

def _run_tiebreaker_stage(query_text, candidates, tb_cfg, llm_wrapper_path=None):
    tb_mode = (tb_cfg.get("mode") or "never").lower()
    if tb_mode == "never" or not candidates or not query_text:
        return False, None
    try:
        import llm_tiebreaker as tbm
        import bm25_score as _bm
        margin_th = float(tb_cfg.get("margin_threshold", 0.03))
        abs_floor = float(tb_cfg.get("abs_confidence_floor", 0.0))
        prior_scores = [r.get("score", 0.0) for r in candidates]
        top1_score = prior_scores[0] if prior_scores else 0.0
        margin_ok = _bm.normalized_margin(prior_scores) < margin_th
        abs_low = abs_floor > 0.0 and top1_score < abs_floor
        trigger_tight = margin_ok or abs_low
        fire_llm = False
        if tb_mode == "always":
            fire_llm = True
        elif tb_mode == "when_tight":
            fire_llm = trigger_tight
        elif tb_mode == "when_tight_divergent":
            if trigger_tight:
                axes = list(tb_cfg.get("divergent_axes") or ["definition_tier", "source_type"])
                top_n_llm = int(tb_cfg.get("top_n_to_llm", 5))
                fire_llm = _bm.candidates_diverge_on(candidates[:top_n_llm], axes)
        if not fire_llm:
            return False, None
        wrapper = llm_wrapper_path or tb_cfg.get("llm_wrapper", "llm_wrapper.py")
        top_n_llm = int(tb_cfg.get("top_n_to_llm", 5))
        tiebroken = tbm.tiebreak(query_text, list(candidates[:top_n_llm]), wrapper,
                                 tier=tb_cfg.get("tier", "flash"), temp=float(tb_cfg.get("temp", 0.0)))
        results = tiebroken + candidates[top_n_llm:]
        return True, results
    except Exception as e:
        logger.warning(f"LLM tiebreak stage failed: {e}; skipping")
        return False, None

def _candidate_text_for_bm25(result: dict) -> str:
    parts = []
    for field_name in ("microgloss", "lemma", "canonical_id"):
        val = result.get(field_name)
        if val:
            parts.append(str(val))
    return " ".join(parts) if parts else ""

# ========== Compound decomposition helper ==========
def decompose_into_known_compounds(query: str, lemma_set: set) -> list:
    """
    Return all contiguous 2- and 3-word sub-phrases of the query that
    exist in the lemma_set (case-insensitive).
    """
    words = query.lower().split()
    found = []
    for n in (2, 3):
        if len(words) < n:
            continue
        for i in range(len(words) - n + 1):
            sub = " ".join(words[i:i+n])
            if sub in lemma_set:
                found.append(sub)
    return found

def call_mint_compound(db_path: str, compound: str, head_noun: str) -> List[int]:
    """
    Run mint_compound.py subprocess. Returns list of new entry_ids.
    Returns empty list if none minted.
    
    Guards:
    - Single-word queries: skipped (no compound to mint)
    - Overly long queries (>200 chars): skipped (likely paragraph text, not a compound)
    - Timeout: 30 seconds (was 120) — fails fast instead of hanging
    - Compound is truncated to 100 chars for the LLM call
    """
    # Skip single-word queries entirely
    if len(compound.split()) < 2:
        logger.debug("call_mint_compound: skipping single-word compound '%s'", compound)
        return []
    
    # Skip if compound is unreasonably long (paragraph-length text)
    if len(compound) > 200:
        logger.warning("call_mint_compound: skipping long compound '%s' (%d chars)", compound[:50], len(compound))
        return []
    
    # Truncate to 100 chars for the LLM subprocess call
    truncated = compound[:100]
    
    try:
        result = subprocess.run(
            [sys.executable, MINT_SCRIPT,
             "--db", db_path,
             "--compound", truncated,
             "--head-noun", head_noun],
            capture_output=True, text=True, timeout=30  # 120 → 30 seconds
        )
        if result.returncode != 0:
            logger.error("mint_compound.py failed: %s", result.stderr[:200])
            return []
        output = result.stdout.strip()
        if output == "0" or not output:
            return []
        return [int(eid) for eid in output.split(",")]
    except subprocess.TimeoutExpired:
        logger.warning("call_mint_compound: timed out after 30s for '%s'", truncated)
        return []
    except Exception as e:
        logger.error("Exception calling mint_compound: %s", e)
        return []

# ---------------------------------------------------------------------------
# Request/response schemas
# ---------------------------------------------------------------------------
class SearchRequest(BaseModel):
    text: Optional[str] = Field(None, description="Query text (will be embedded)")
    query_vector: Optional[List[float]] = Field(None, description="Pre-computed vector")
    k: int = Field(10, ge=1, le=200)
    lemma_restrict: Optional[str] = None
    auto_resolve_forms: bool = False
    pos_restrict: Optional[str] = None
    language: str = "en"
    embedding_method: Optional[str] = None
    policy: Optional[str] = None
    policy_overrides: Optional[Dict[str, Any]] = None
    focus_word: Optional[str] = Field(None, description="The word in the sentence to focus on. Sets lemma_restrict automatically.")
    focus_pos: Optional[str] = Field(None, description="Expected part-of-speech of the focus word. Sets pos_restrict automatically.")

class LookupCanonicalRequest(BaseModel):
    canonical_id: str

class LookupLemmaRequest(BaseModel):
    lemma: str
    pos: Optional[str] = None
    policy: Optional[str] = None
    policy_overrides: Optional[Dict[str, Any]] = None

class BatchSearchItem(BaseModel):
    text: Optional[str] = None
    lemma: Optional[str] = None
    pos: Optional[str] = None

class BatchSearchRequest(BaseModel):
    queries: List[BatchSearchItem]
    k: int = Field(3, ge=1, le=50)
    policy: Optional[str] = None
    policy_overrides: Optional[Dict[str, Any]] = None
    language: str = "en"
    embedding_method: Optional[str] = None

# ---------------------------------------------------------------------------
# Server state (no background worker fields)
# ---------------------------------------------------------------------------
@dataclass
class ServerState:
    backend: LexiconBackend
    policies: Dict[str, Policy]
    embedder: EmbedderProxy
    api_token: Optional[str]
    booted_at: float
    embedder_cascade: Dict[str, List[str]]
    embedder_min_coverage: float = 0.95
    reranker_cfg: Dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_RERANKER_CFG))
    bm25_cfg: Dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_BM25_CFG))
    tiebreak_cfg: Dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_TIEBREAK_CFG))
    llm_wrapper_path: Optional[str] = None
    reload_lock: threading.Lock = field(default_factory=threading.Lock)
    reload_interval: float = 0.0
    reload_thread: Optional[threading.Thread] = None
    improve_cfg: Dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_IMPROVE_CFG))
    db_path: str = ""
    lemma_set: set = field(default_factory=set)  # set of all lemmas for fast lookup

_state: Optional[ServerState] = None

def _check_auth(x_api_key: Optional[str]):
    if _state is None or _state.api_token is None:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, _state.api_token):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")

def _resolve_policy(name: Optional[str], overrides: Optional[dict]) -> Policy:
    assert _state is not None
    base_name = name or "__default__"
    pol = _state.policies.get(base_name)
    if pol is None:
        raise HTTPException(404, f"Unknown policy {name!r}")
    return pol.merge_overrides(overrides)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
def make_app() -> FastAPI:
    app = FastAPI(title="Search Server — Synapedia v7", version="1.0-synapedia")

    def _reload_in_background():
        if not _state.reload_lock.acquire(blocking=False):
            logger.warning("Reload already in progress, skipping.")
            return
        try:
            logger.info("Reloading lexicon in background...")
            t0 = _time.time()
            new_backend = LexiconBackend(_state.backend.db_path)
            new_backend.load_all()
            _state.backend = new_backend
            # Rebuild lemma_set
            _state.lemma_set = set(new_backend.lemma_index.keys())
            elapsed = _time.time() - t0
            logger.info(f"Reload complete in {elapsed:.1f}s: {len(new_backend.senses):,} senses, "
                         f"{len(new_backend.embedders):,} embedders")
        except Exception as e:
            logger.error(f"Reload failed: {e}")
        finally:
            _state.reload_lock.release()

    @app.get("/health")
    def health(x_api_key: Optional[str] = Header(None)):
        _check_auth(x_api_key)
        assert _state is not None
        tier_list = ["CORE_ONTOLOGY", "CORE_KNOWLEDGE", "LEXICAL_EXTENSION", "CLAIMED",
                      "INFERRED", "PROVISIONAL", "GHOST"]
        tier_dist = {t: _state.backend.tier_counts.get(t, 0) for t in tier_list}
        min_cov = _state.embedder_min_coverage
        cascade_en = _state.backend.cascade_for_language("en", _state.embedder_cascade, min_cov)
        cascade_multi = _state.backend.cascade_for_language("multilingual", _state.embedder_cascade, min_cov)
        emb_info = [
            {"method": m, "dim": _state.backend.embedders[m].dim,
             "n_senses": len(_state.backend.embedders[m].entry_ids),
             "coverage": round(_state.backend.embedder_coverage(m), 4),
             "status": _state.backend.embedder_status(m, min_cov)}
            for m in _state.backend.embedders
        ]
        return {
            "status": "ok",
            "uptime_seconds": round(_time.time() - _state.booted_at, 1),
            "n_senses_total": len(_state.backend.senses),
            "embedders_loaded": emb_info,
            "embedder_cascade_en": cascade_en,
            "embedder_cascade_multilingual": cascade_multi,
            "default_embedder_english": cascade_en[0] if cascade_en else None,
            "tier_distribution": tier_dist,
            "source_types": sorted(_state.backend.source_types),
            "policies_available": [n for n in _state.policies.keys() if not n.startswith("__")],
            "default_policy": _state.policies["__default__"].name,
            "embedder_runtime_available": _state.embedder.available(),
        }

    @app.get("/policies")
    def list_policies(x_api_key: Optional[str] = Header(None)):
        _check_auth(x_api_key)
        assert _state is not None
        return {name: {
            "rewrite_to_standard_form": p.rewrite_to_standard_form,
            "preserve_specialist_terms": p.preserve_specialist_terms,
            "audience_tier": p.audience_tier,
            "min_tier_returned": p.min_tier_returned,
            "exclude_social_status": p.exclude_social_status,
            "exclude_temporal_status": p.exclude_temporal_status,
        } for name, p in _state.policies.items() if not name.startswith("__")}

    @app.post("/reload")
    def reload_embeddings(x_api_key: Optional[str] = Header(None)):
        _check_auth(x_api_key); assert _state is not None
        thread = threading.Thread(target=_reload_in_background, daemon=True)
        thread.start()
        thread.join(timeout=30)
        return {"status": "reload_completed", "message": "Reload finished."}

    @app.post("/embed")
    def embed(req: Dict[str, Any], x_api_key: Optional[str] = Header(None)):
        _check_auth(x_api_key); assert _state is not None
        if not _state.embedder.available():
            raise HTTPException(503, "Embedder runtime not installed")
        text = req.get("text") or ""
        if not text:
            raise HTTPException(400, "text is required")
        method = req.get("embedding_method") or _state.backend.best_embedder_for_language(req.get("language", "en"))
        if not method:
            raise HTTPException(503, "No embedders loaded")
        v = _state.embedder.embed(text, method)
        return {"vector": v, "embedding_method": method, "dim": len(v)}

    @app.post("/batch_embed_db")
    @app.post("/recompute_db")
    def batch_embed_db(req: Optional[Dict[str, Any]] = None, x_api_key: Optional[str] = Header(None)):
        _check_auth(x_api_key); assert _state is not None
        if not _state.embedder.available():
            raise HTTPException(503, "Embedder runtime not installed")

        req_data = req or {}
        batch_size = req_data.get("batch_size") if "batch_size" in req_data else DEFAULT_BATCH_EMBED_SIZE
        force = req_data.get("force") if "force" in req_data else DEFAULT_BATCH_EMBED_FORCE
        method = req_data.get("embedding_method") or "bge-large-en-v1"

        db_path = _state.backend.db_path
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        if force:
            cur.execute("""
                SELECT entry_id, embedding_text, gloss, lemma
                FROM synapedia_entry
            """)
        else:
            cur.execute("""
                SELECT entry_id, embedding_text, gloss, lemma
                FROM synapedia_entry
                WHERE embedding IS NULL OR embedding_text_needs_rebuild = 1
            """)

        rows = cur.fetchall()
        if not rows:
            conn.close()
            return {"status": "completed", "embedded_count": 0, "message": "No entries require embedding."}

        total_count = len(rows)
        logger.info(f"Starting batch embedding for {total_count} entries (batch_size={batch_size}, method={method})...")

        total_embedded = 0
        for i in range(0, total_count, batch_size):
            batch_rows = rows[i:i + batch_size]
            batch_ids = []
            batch_texts = []

            for eid, emb_text, gloss, lemma in batch_rows:
                text = (emb_text or gloss or lemma or "").strip()
                if not text:
                    text = lemma or f"entry_{eid}"
                batch_ids.append(eid)
                batch_texts.append(text)

            vectors = _state.embedder.batch_embed(batch_texts, method)

            update_tuples = []
            for eid, vec in zip(batch_ids, vectors):
                blob = vec_to_blob(vec)
                update_tuples.append((blob, eid))

            cur.executemany("""
                UPDATE synapedia_entry
                SET embedding = ?, embedding_text_needs_rebuild = 0
                WHERE entry_id = ?
            """, update_tuples)
            conn.commit()
            total_embedded += len(update_tuples)
            logger.info(f"  Batch embedded {total_embedded}/{total_count} entries")

        conn.close()

        thread = threading.Thread(target=_reload_in_background, daemon=True)
        thread.start()
        thread.join(timeout=30)

        return {"status": "completed", "embedded_count": total_embedded, "message": f"Successfully embedded {total_embedded} entries."}

    @app.post("/search")
    def search(req: SearchRequest, x_api_key: Optional[str] = Header(None)):
        _check_auth(x_api_key); assert _state is not None
        t0 = _time.time()
        t_stage = {}
        policy = _resolve_policy(req.policy, req.policy_overrides)

        if req.focus_word and not req.lemma_restrict:
            req.lemma_restrict = req.focus_word
        if req.focus_pos and not req.pos_restrict:
            req.pos_restrict = req.focus_pos

        if req.embedding_method:
            if req.embedding_method not in _state.backend.embedders:
                raise HTTPException(503, f"Embedder {req.embedding_method!r} not loaded. Loaded: {list(_state.backend.embedders.keys())}")
            cascade = [req.embedding_method]
        else:
            cascade = _state.backend.cascade_for_language(req.language, _state.embedder_cascade, _state.embedder_min_coverage)
        if not cascade:
            raise HTTPException(503, "No embedders loaded")

        improve_cfg = _state.improve_cfg
        global _improved_lemmas

        # ========== SYNCHRONOUS IMPROVEMENT (runs at most once per search) ==========
        for improvement_round in range(improve_cfg.get("max_attempts", 1) + 1):
            results = []
            embedder_used = None
            attempted = []

            for method in cascade:
                attempted.append(method)
                if req.query_vector is not None and method == cascade[0]:
                    qv = req.query_vector
                elif req.text:
                    if not _state.embedder.available():
                        raise HTTPException(503, "Embedder runtime unavailable; supply query_vector")
                    if req.focus_word:
                        lemma_part = f"lemma:{req.focus_word}"
                        pos_part = f"pos:{req.focus_pos}" if req.focus_pos else ""
                        gloss_part = f"gloss:{req.text}" if req.text else ""
                        query_for_embed = "|".join(filter(None, [lemma_part, pos_part, gloss_part]))
                        logger.debug(f"Structured query for embedding: {query_for_embed}")
                    else:
                        query_for_embed = req.text
                    t_emb = _time.time()
                    qv = _state.embedder.embed(query_for_embed, method)
                    t_stage['embed'] = _time.time() - t_emb
                    _print_timing("search.embed", t_emb)
                else:
                    if req.query_vector is not None:
                        break
                    raise HTTPException(400, "Provide text or query_vector")

                t_topk = _time.time()
                raw = _state.backend.topk(qv, method, req.k * 3, req.lemma_restrict,
                                          auto_resolve_forms=req.auto_resolve_forms,
                                          db_path=str(_state.backend.db_path), pos_restrict=req.pos_restrict)
                t_stage['topk'] = _time.time() - t_topk
                _print_timing("search.topk", t_topk)

                t_pol = _time.time()
                candidate = apply_policy(raw, _state.backend, policy,
                                                 lemma_restrict=req.lemma_restrict,
                                                 pos_restrict=req.pos_restrict)[:req.k]
                t_stage['policy'] = _time.time() - t_pol
                _print_timing("search.policy", t_pol)

                if not candidate and req.pos_restrict:
                    logger.info("No results with pos_restrict='%s', retrying without POS restriction",
                                 req.pos_restrict)
                    t_pol2 = _time.time()
                    candidate = apply_policy(raw, _state.backend, policy,
                                                     lemma_restrict=req.lemma_restrict,
                                                     pos_restrict=None)[:req.k]
                    t_stage['policy_retry'] = _time.time() - t_pol2

                if candidate:
                    results = candidate
                    embedder_used = method
                    break

            if not results:
                break

            # ---- Check if improvement is needed ----
            need_improve = False
            improvement_target = None

            if improve_cfg.get("enabled") and improvement_round == 0:
                if req.lemma_restrict:
                    lemma_lower = req.lemma_restrict.lower()
                    if lemma_lower in _improved_lemmas:
                        logger.info("Lemma group '%s' already fully improved, skipping", lemma_lower)
                        need_improve = False
                    else:
                        conn = sqlite3.connect(str(_state.backend.db_path))
                        cur = conn.cursor()
                        entry_ids_for_lemma = _state.backend.lemma_index.get(lemma_lower, [])
                        if entry_ids_for_lemma:
                            placeholders = ','.join('?' * len(entry_ids_for_lemma))
                            cur.execute(f"""
                                SELECT entry_id FROM synapedia_entry
                                WHERE entry_id IN ({placeholders}) AND improved_at IS NULL
                            """, entry_ids_for_lemma)
                            unimproved = [row[0] for row in cur.fetchall()]
                            conn.close()
                            if unimproved:
                                need_improve = True
                                improvement_target = ("lemma", lemma_lower)
                                _improved_lemmas.add(lemma_lower)
                        else:
                            conn.close()
                else:
                    improve_top_n = improve_cfg.get("top_n_to_improve", 5)
                    top_ids = [r.get("entry_id") for r in results[:improve_top_n] if r.get("entry_id")]
                    if top_ids:
                        conn = sqlite3.connect(str(_state.backend.db_path))
                        cur = conn.cursor()
                        placeholders = ','.join('?' * len(top_ids))
                        cur.execute(f"""
                            SELECT entry_id FROM synapedia_entry
                            WHERE entry_id IN ({placeholders}) AND improved_at IS NULL
                        """, top_ids)
                        unimproved = [row[0] for row in cur.fetchall()]
                        conn.close()
                        if unimproved:
                            need_improve = True
                            improvement_target = ("ids", unimproved)

            if need_improve and improvement_target is not None:
                target_type, target_data = improvement_target
                if target_type == "lemma":
                    logger.info("Need to improve all entries for lemma group '%s'", target_data)
                    cmd = [
                        sys.executable, improve_cfg["script_path"],
                        "--db", str(_state.backend.db_path),
                        "--lemmas", target_data,
                        "--llm-source", improve_cfg.get("llm_source", "cloud"),
                        "--embed-service", improve_cfg.get("embed_service_url"),
                        "--search-server", improve_cfg.get("search_server_url", "http://localhost:8400"),
                    ]
                    if improve_cfg.get("generate_events", True):
                        cmd.append("--generate-events")
                    if improve_cfg.get("avoid_floating_nodes", True):
                        cmd.append("--avoid-floating-nodes")
                else:
                    ids_list = target_data
                    ids_str = ",".join(str(eid) for eid in ids_list)
                    logger.info("Need to improve top N entries for query '%s': IDs %s", req.text, ids_str)
                    cmd = [
                        sys.executable, improve_cfg["script_path"],
                        "--db", str(_state.backend.db_path),
                        "--entry-ids", ids_str,
                        "--llm-source", improve_cfg.get("llm_source", "cloud"),
                        "--embed-service", improve_cfg.get("embed_service_url"),
                        "--search-server", improve_cfg.get("search_server_url", "http://localhost:8400"),
                    ]
                    if improve_cfg.get("generate_events", True):
                        cmd.append("--generate-events")
                    if improve_cfg.get("avoid_floating_nodes", True):
                        cmd.append("--avoid-floating-nodes")

                model = improve_cfg.get("model")
                if model:
                    cmd.extend(["--model", model])

                logger.info("Running improvement: %s", " ".join(cmd))
                try:
                    sp_result = subprocess.run(cmd, capture_output=True, timeout=180)
                    if sp_result.returncode in (0, 3):
                        logger.info("Improvement completed, updating in-memory state...")
                        if target_type == "lemma":
                            conn = sqlite3.connect(str(_state.backend.db_path))
                            cur = conn.cursor()
                            lemma_lower = target_data
                            entry_ids_for_lemma = _state.backend.lemma_index.get(lemma_lower, [])
                            for eid in entry_ids_for_lemma:
                                cur.execute("""
                                    SELECT lemma, pos_ud, microgloss, canonical_id,
                                           definition_tier, source_type
                                    FROM synapedia_entry WHERE entry_id = ?
                                """, (eid,))
                                row = cur.fetchone()
                                if row:
                                    lemma, pos_ud, microgloss, canonical_id, def_tier, src_type = row
                                    rank = TIER_RANK_MAP.get(def_tier, 99)
                                    new_sense = SenseRecord(
                                        entry_id=eid, lemma=lemma, pos_ud=pos_ud,
                                        microgloss=microgloss or "",
                                        canonical_id=canonical_id,
                                        definition_tier=def_tier or DEFAULT_DEFINITION_TIER,
                                        source_type=src_type or DEFAULT_SOURCE_TYPE,
                                        definition_tier_rank=rank,
                                    )
                                    _state.backend.senses[eid] = new_sense
                                    method = "bge-large-en-v1"
                                    emb = _state.backend.embedders.get(method)
                                    if emb is not None and eid in emb.entry_id_to_idx:
                                        idx = emb.entry_id_to_idx[eid]
                                        cur.execute("SELECT embedding FROM synapedia_entry WHERE entry_id = ?", (eid,))
                                        blob = cur.fetchone()[0]
                                        if blob:
                                            new_vec = np.array(vec_from_blob(blob), dtype=np.float32)
                                            if new_vec.shape == (emb.dim,):
                                                emb.vectors[idx] = new_vec
                            conn.close()
                            logger.info("Updated lemma group '%s' (%d entries) in memory", lemma_lower, len(entry_ids_for_lemma))
                        else:
                            ids_list = target_data
                            conn = sqlite3.connect(str(_state.backend.db_path))
                            cur = conn.cursor()
                            for eid in ids_list:
                                cur.execute("""
                                    SELECT lemma, pos_ud, microgloss, canonical_id,
                                           definition_tier, source_type
                                    FROM synapedia_entry WHERE entry_id = ?
                                """, (eid,))
                                row = cur.fetchone()
                                if row:
                                    lemma, pos_ud, microgloss, canonical_id, def_tier, src_type = row
                                    rank = TIER_RANK_MAP.get(def_tier, 99)
                                    new_sense = SenseRecord(
                                        entry_id=eid, lemma=lemma, pos_ud=pos_ud,
                                        microgloss=microgloss or "",
                                        canonical_id=canonical_id,
                                        definition_tier=def_tier or DEFAULT_DEFINITION_TIER,
                                        source_type=src_type or DEFAULT_SOURCE_TYPE,
                                        definition_tier_rank=rank,
                                    )
                                    _state.backend.senses[eid] = new_sense
                                    method = "bge-large-en-v1"
                                    emb = _state.backend.embedders.get(method)
                                    if emb is not None and eid in emb.entry_id_to_idx:
                                        idx = emb.entry_id_to_idx[eid]
                                        cur.execute("SELECT embedding FROM synapedia_entry WHERE entry_id = ?", (eid,))
                                        blob = cur.fetchone()[0]
                                        if blob:
                                            new_vec = np.array(vec_from_blob(blob), dtype=np.float32)
                                            if new_vec.shape == (emb.dim,):
                                                emb.vectors[idx] = new_vec
                            conn.close()
                            logger.info("Updated %d entries in memory", len(ids_list))
                    else:
                        logger.error("Improvement failed: %s", sp_result.stderr.decode()[:500])
                except subprocess.TimeoutExpired:
                    logger.error("Improvement timed out")
                except Exception as e:
                    logger.error("Improvement error: %s", e)
            break

        # ========== COMPOUND RECOVERY ==========
        # Skip compound recovery for single-entity lookups (focus_word set)
        # Also skip if no text or no results
        if results and req.text and not req.focus_word:
            top_score = results[0].get("raw_cosine", 0.0)
            # Check known compounds first (even if score is moderate)
            known = decompose_into_known_compounds(req.text, _state.lemma_set)
            if known:
                logger.info("Known compounds in query: %s", known)
                known_entries = []
                conn = sqlite3.connect(str(_state.backend.db_path))
                cur = conn.cursor()
                for comp in known:
                    cur.execute("SELECT entry_id, lemma, gloss FROM synapedia_entry WHERE LOWER(lemma) = ?", (comp.lower(),))
                    for row in cur.fetchall():
                        eid, lemma, gloss = row
                        known_entries.append({"entry_id": eid, "lemma": lemma, "gloss": gloss, "raw_cosine": 1.0, "score": 1.0})
                conn.close()
                if known_entries:
                    best_known = max(known_entries, key=lambda x: x.get("raw_cosine", 0))["raw_cosine"]
                    if best_known >= IMPROVEMENT_THRESHOLD or top_score < COMPOUND_THRESHOLD:
                        known_policy = apply_policy(
                            [(e["entry_id"], e["raw_cosine"]) for e in known_entries],
                            _state.backend, policy,
                            lemma_restrict=req.lemma_restrict, pos_restrict=req.pos_restrict
                        )
                        if known_policy:
                            logger.info("Fast path: returning known compounds; skipping minting")
                            results = known_policy[:req.k]
                            return {
                                "query_embedding_method": embedder_used,
                                "embedder_used": embedder_used,
                                "embedder_cascade_attempted": attempted,
                                "policy_applied": policy.name,
                                "compound_recovery": "fast_known",
                                "results": results,
                                "n_results": len(results),
                            }

            # Slow path: call mint_compound (only if score is truly low AND no known compounds found)
            if top_score < COMPOUND_THRESHOLD:
                # Check failed-mint cache — skip if we tried recently
                now = _time.time()
                last_fail = _failed_mints.get(req.text, 0.0)
                if now - last_fail < _FAILED_MINT_TTL:
                    logger.info("Skipping mint for '%s' (failed recently, %ds ago)",
                                req.text[:50], int(now - last_fail))
                else:
                    logger.info("No known compounds; calling mint_compound for '%s'", req.text[:80])
                    head_noun = req.text.split()[-1] if req.text.split() else req.text
                    new_ids = call_mint_compound(str(_state.backend.db_path), req.text, head_noun)
                    if new_ids:
                        conn = sqlite3.connect(str(_state.backend.db_path))
                        cur = conn.cursor()
                        for eid in new_ids:
                            cur.execute("""
                                SELECT entry_id, lemma, pos_ud, microgloss, canonical_id,
                                       definition_tier, source_type
                                FROM synapedia_entry WHERE entry_id = ?
                            """, (eid,))
                            row = cur.fetchone()
                            if row:
                                entry_id, lemma, pos_ud, microgloss, canonical_id, def_tier, src_type = row
                                rank = TIER_RANK_MAP.get(def_tier, 99)
                                new_sense = SenseRecord(
                                    entry_id=eid, lemma=lemma, pos_ud=pos_ud,
                                    microgloss=microgloss or "",
                                    canonical_id=canonical_id,
                                    definition_tier=def_tier or DEFAULT_DEFINITION_TIER,
                                    source_type=src_type or DEFAULT_SOURCE_TYPE,
                                    definition_tier_rank=rank,
                                )
                                _state.backend.senses[eid] = new_sense
                                _state.backend.lemma_index.setdefault(lemma.lower(), []).append(eid)
                                _state.lemma_set.add(lemma.lower())
                        conn.close()
                        logger.info("Added %d minted compounds to in-memory index", len(new_ids))
                        minted_results = apply_policy(
                            [(eid, 1.0) for eid in new_ids],
                            _state.backend, policy,
                            lemma_restrict=req.lemma_restrict, pos_restrict=req.pos_restrict
                        )
                        if minted_results:
                            return {
                                "query_embedding_method": embedder_used,
                                "embedder_used": embedder_used,
                                "embedder_cascade_attempted": attempted,
                                "policy_applied": policy.name,
                                "compound_recovery": "minted",
                                "results": minted_results[:req.k],
                                "n_results": len(minted_results),
                            }
                    else:
                        # Cache the failure so we don't retry immediately
                        _failed_mints[req.text] = now
                        logger.info("Cached failed mint for '%s' (TTL=%ds)", req.text[:50], _FAILED_MINT_TTL)

        # ---- Stage 2: Reranker ----
        reranker_applied = None
        bm25_applied = False
        tiebreak_applied = False

        if results and req.text:
            rr_model, rr_results = _run_reranker_stage(req.text, results, _state.reranker_cfg or {})
            if rr_results is not None:
                results = rr_results
                reranker_applied = rr_model

            alpha_override = None
            if req.lemma_restrict:
                alpha_override = 0.5
            bm25_applied_flag, bm25_results = _run_bm25_stage(
                req.text, results, _state.bm25_cfg or {},
                alpha_override=alpha_override, reranker_applied=reranker_applied,
            )
            if bm25_results is not None:
                results = bm25_results
                bm25_applied = bm25_applied_flag

            tb_applied_flag, tb_results = _run_tiebreaker_stage(
                req.text, results, _state.tiebreak_cfg or {},
                llm_wrapper_path=_state.llm_wrapper_path,
            )
            if tb_results is not None:
                results = tb_results
                tiebreak_applied = tb_applied_flag

        t_total = _time.time() - t0
        _print_timing("search.total", t0)
        logger.info(f"SEARCH TIMING: {t_stage} total={t_total:.3f}s query={req.text!r}")
        return {
            "query_embedding_method": embedder_used, "embedder_used": embedder_used,
            "embedder_cascade_attempted": attempted, "policy_applied": policy.name,
            "reranker_applied": reranker_applied, "bm25_applied": bm25_applied,
            "llm_tiebreak_applied": tiebreak_applied,
            "results": results, "n_results": len(results),
        }

    @app.post("/batch_search")
    def batch_search(req: BatchSearchRequest, x_api_key: Optional[str] = Header(None)):
        _check_auth(x_api_key); assert _state is not None
        if not req.queries:
            return {"results": []}
        policy = _resolve_policy(req.policy, req.policy_overrides)
        if req.embedding_method:
            if req.embedding_method not in _state.backend.embedders:
                raise HTTPException(503, f"Embedder {req.embedding_method!r} not loaded. Loaded: {list(_state.backend.embedders.keys())}")
            method = req.embedding_method
        else:
            cascade = _state.backend.cascade_for_language(req.language, _state.embedder_cascade, _state.embedder_min_coverage)
            if not cascade:
                raise HTTPException(503, "No embedders loaded")
            method = cascade[0]
        if not _state.embedder.available():
            raise HTTPException(503, "Embedder runtime unavailable")
        query_texts = [q.text or q.lemma or "" for q in req.queries]
        t_emb = _time.time()
        all_vectors = _state.embedder.batch_embed(query_texts, method)
        t_stage = {"batch_embed": _time.time() - t_emb}
        _print_timing("batch_search.embed", t_emb)
        results_out = []
        for idx, (qv, q) in enumerate(zip(all_vectors, req.queries)):
            t_topk = _time.time()
            raw = _state.backend.topk(qv, method, req.k * 3, lemma_restrict=q.lemma or None, pos_restrict=q.pos or None)
            t_stage.setdefault("topk", 0.0); t_stage["topk"] += _time.time() - t_topk
            t_pol = _time.time()
            candidates = apply_policy(raw, _state.backend, policy, pos_restrict=q.pos.upper() if q.pos else None)[:req.k]
            t_stage.setdefault("policy", 0.0); t_stage["policy"] += _time.time() - t_pol
            if candidates:
                r = candidates[0]
                results_out.append({
                    "query_index": idx, "canonical_id": r.get("canonical_id"),
                    "entry_id": r.get("entry_id"), "score": r.get("score"),
                    "raw_cosine": r.get("raw_cosine"), "lemma": r.get("lemma"),
                    "pos_ud": r.get("pos_ud"), "microgloss": r.get("microgloss"),
                    "definition_tier": r.get("definition_tier"), "source_type": r.get("source_type"),
                    "n_candidates": len(candidates),
                })
            else:
                if q.lemma:
                    entry_ids = _state.backend.lemma_index.get(q.lemma.lower(), [])
                    if q.pos:
                        entry_ids = [w for w in entry_ids if _state.backend.senses[w].pos_ud.upper() == q.pos.upper()]
                    if entry_ids:
                        scored = [(w, 1.0) for w in entry_ids]
                        fallback = apply_policy(scored, _state.backend, policy, pos_restrict=q.pos.upper() if q.pos else None)[:1]
                        if fallback:
                            r = fallback[0]
                            results_out.append({
                                "query_index": idx, "canonical_id": r.get("canonical_id"),
                                "entry_id": r.get("entry_id"), "score": 0.5, "raw_cosine": 0.0,
                                "lemma": r.get("lemma"), "pos_ud": r.get("pos_ud"),
                                "microgloss": r.get("microgloss"),
                                "definition_tier": r.get("definition_tier"), "source_type": r.get("source_type"),
                                "n_candidates": 1, "from_fallback": "lemma_lookup",
                            })
                            continue
                results_out.append({
                    "query_index": idx, "canonical_id": None, "entry_id": None,
                    "score": 0.0, "raw_cosine": 0.0, "lemma": q.lemma,
                    "pos_ud": q.pos, "microgloss": None,
                    "definition_tier": None, "source_type": None,
                    "n_candidates": 0,
                })
        t_total = _time.time() - t_emb + 1e-6
        logger.info(f"BATCH SEARCH: {len(req.queries)} queries embed={t_stage.get('batch_embed',0):.3f}s topk={t_stage.get('topk',0):.3f}s policy={t_stage.get('policy',0):.3f}s total={t_total:.3f}s")
        return {"embedding_method": method, "policy_applied": policy.name, "results": results_out, "n_queries": len(req.queries)}

    @app.post("/lookup/canonical")
    def lookup_canonical(req: LookupCanonicalRequest, x_api_key: Optional[str] = Header(None)):
        _check_auth(x_api_key); assert _state is not None
        s = _state.backend.lookup_by_canonical_id(req.canonical_id)
        if s is None:
            raise HTTPException(404, f"No sense with canonical_id={req.canonical_id!r}")
        return {
            "entry_id": s.entry_id, "canonical_id": s.canonical_id,
            "lemma": s.lemma, "pos_ud": s.pos_ud,
            "microgloss": s.microgloss,
            "definition_tier": s.definition_tier, "source_type": s.source_type,
        }

    @app.post("/lookup/lemma")
    def lookup_lemma(req: LookupLemmaRequest, x_api_key: Optional[str] = Header(None)):
        _check_auth(x_api_key); assert _state is not None
        policy = _resolve_policy(req.policy, req.policy_overrides)
        entry_ids = _state.backend.lemma_index.get(req.lemma.lower(), [])
        if req.pos:
            entry_ids = [w for w in entry_ids if _state.backend.senses[w].pos_ud.upper() == req.pos.upper()]
        scored = [(w, 1.0) for w in entry_ids]
        results = apply_policy(scored, _state.backend, policy)
        return {"lemma": req.lemma, "pos": req.pos, "policy_applied": policy.name, "results": results, "n_results": len(results)}

    @app.post("/definition")
    def lookup_definition(req: LookupCanonicalRequest, x_api_key: Optional[str] = Header(None)):
        _check_auth(x_api_key); assert _state is not None
        s = _state.backend.lookup_by_canonical_id(req.canonical_id)
        if s is None:
            raise HTTPException(404, f"No sense with canonical_id={req.canonical_id!r}")
        conn = sqlite3.connect(_state.backend.db_path)
        cur = conn.cursor()
        cur.execute("""
            SELECT parent_lemma, parent_gloss, parent_pos, parent_canonical_id
            FROM synapedia_is_a
            WHERE synapedia_entry_id = ?
        """, (s.entry_id,))
        hypernyms = [{"lemma": r[0], "gloss": r[1], "pos": r[2], "canonical_id": r[3]}
                     for r in cur.fetchall()]
        cur.execute("""
            SELECT part_lemma, part_gloss, part_pos, part_canonical_id
            FROM synapedia_has_part
            WHERE synapedia_entry_id = ?
        """, (s.entry_id,))
        parts = [{"lemma": r[0], "gloss": r[1], "pos": r[2], "canonical_id": r[3]}
                 for r in cur.fetchall()]
        conn.close()
        return {
            "entry_id": s.entry_id, "canonical_id": s.canonical_id,
            "lemma": s.lemma, "pos_ud": s.pos_ud,
            "microgloss": s.microgloss,
            "definition_tier": s.definition_tier, "source_type": s.source_type,
            "hypernyms": hypernyms, "parts": parts,
        }

    return app

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--lexicon", required=True, help="Path to synapedia.db")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8400)
    p.add_argument("--policy", default=str(DEFAULT_POLICY_PATH))
    p.add_argument("--auth-file", default=str(DEFAULT_AUTH_PATH))
    p.add_argument("--no-auth", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--llm-wrapper", default=None)
    p.add_argument("--reload-interval", type=float, default=0.0,
                   help="Seconds between automatic lexicon reloads (0 = disabled)")
    p.add_argument("--device", default="auto", choices=["auto", "cuda", "rocm", "cpu"],
                   help="Execution device for ONNX embedder (auto, cuda, rocm, cpu)")
    args = p.parse_args()

    setup_logging(args.verbose)
    os.environ["HF_HUB_DISABLE_SYMLINKS_FORCE"] = "1"

    db_path = Path(args.lexicon)
    if not db_path.exists():
        print(f"Lexicon DB not found: {db_path}", file=sys.stderr)
        return 1

    logger.info(f"Loading lexicon: {db_path}")
    backend = LexiconBackend(db_path)
    backend.load_all()

    policy_path = resolve_policy_path(explicit_path=(args.policy if args.policy != str(DEFAULT_POLICY_PATH) else None),
                                      config_dir=None)
    logger.info(f"Loading policy: {policy_path}")
    policies, embedder_cascade, min_coverage = load_policies(policy_path)
    backend._cascade_config = embedder_cascade

    is_loopback = args.host in ("127.0.0.1", "localhost", "::1")
    if is_loopback or args.no_auth:
        api_token = None
        if not is_loopback:
            logger.warning("Running without auth on a non-loopback address. This is insecure.")
    else:
        api_token = load_or_create_auth(Path(args.auth_file))
        logger.info(f"Auth required. Token loaded from {args.auth_file}")

    cascade_en = backend.cascade_for_language("en", embedder_cascade, min_coverage)
    preload = cascade_en[0] if cascade_en else None
    embedder = EmbedderProxy(preload_method=preload, device=args.device)

    # --- Load pipeline config from TOML ---
    with open(policy_path, "rb") as f:
        raw_toml = tomllib.load(f)
    pipeline_raw = raw_toml.get("search_pipeline", {})
    reranker_cfg = dict(DEFAULT_RERANKER_CFG)
    bm25_cfg = dict(DEFAULT_BM25_CFG)
    tiebreak_cfg = dict(DEFAULT_TIEBREAK_CFG)
    def _merge_pipeline(default: dict, overrides: dict) -> dict:
        result = dict(default)
        result.update(overrides)
        return result
    reranker_cfg = _merge_pipeline(reranker_cfg, pipeline_raw.get("reranker", {}))
    bm25_cfg = _merge_pipeline(bm25_cfg, pipeline_raw.get("bm25", {}))
    tiebreak_cfg = _merge_pipeline(tiebreak_cfg, pipeline_raw.get("llm_tiebreak", {}))
    def _translate_mode(cfg, stage_name):
        mode = cfg.get("mode", "never")
        if mode == "always":
            cfg["enabled"] = True
            cfg["rerank_always"] = True
        elif mode == "when_tight":
            cfg["enabled"] = True
            cfg["rerank_always"] = False
        else:
            cfg["enabled"] = False
            cfg["rerank_always"] = False
    _translate_mode(reranker_cfg, "reranker")
    bm25_mode = bm25_cfg.get("mode", "never")
    bm25_cfg["enabled"] = (bm25_mode != "never")
    llm_mode = tiebreak_cfg.get("mode", "never")
    tiebreak_cfg["enabled"] = (llm_mode != "never")
    if reranker_cfg.get("enabled"):
        logger.info("Testing reranker at startup...")
        try:
            import reranker as rk
            test = rk.load_reranker(reranker_cfg.get("models", ["bge-reranker-v2-m3"]))
            if test is None:
                logger.warning("Reranker: no model could be loaded. Disabling.")
                reranker_cfg["enabled"] = False
            else:
                logger.info(f"Reranker: {test[0]} loaded successfully ({test[3]} dim)")
        except Exception as e:
            logger.warning(f"Reranker: load failed at startup: {e}. Disabling.")
            reranker_cfg["enabled"] = False

    # Load improve config
    improve_cfg = dict(DEFAULT_IMPROVE_CFG)
    improve_raw = raw_toml.get("improve", {})
    improve_cfg.update(improve_raw)

    # Build lemma_set from backend
    lemma_set = set(backend.lemma_index.keys())

    global _state
    _state = ServerState(
        backend=backend, policies=policies, embedder=embedder, api_token=api_token,
        booted_at=_time.time(), embedder_cascade=embedder_cascade,
        embedder_min_coverage=min_coverage, reranker_cfg=reranker_cfg,
        bm25_cfg=bm25_cfg, tiebreak_cfg=tiebreak_cfg,
        llm_wrapper_path=args.llm_wrapper, reload_interval=args.reload_interval,
        improve_cfg=improve_cfg,
        db_path=str(db_path),
        lemma_set=lemma_set,
    )

    # Periodic reload loop
    if args.reload_interval > 0.0:
        def _periodic_reload():
            while True:
                _time.sleep(args.reload_interval)
                if _state:
                    def _do_reload():
                        if not _state.reload_lock.acquire(blocking=False):
                            logger.warning("Periodic reload: already in progress, skipping.")
                            return
                        try:
                            logger.info("Periodic reload starting...")
                            t0 = _time.time()
                            new_backend = LexiconBackend(_state.backend.db_path)
                            new_backend.load_all()
                            _state.backend = new_backend
                            _state.lemma_set = set(new_backend.lemma_index.keys())
                            elapsed = _time.time() - t0
                            logger.info(f"Periodic reload complete in {elapsed:.1f}s: {len(new_backend.senses):,} senses")
                        except Exception as e:
                            logger.error(f"Periodic reload failed: {e}")
                        finally:
                            _state.reload_lock.release()
                    t = threading.Thread(target=_do_reload, daemon=True)
                    t.start()
        rt = threading.Thread(target=_periodic_reload, daemon=True)
        rt.start()
        _state.reload_thread = rt
        logger.info(f"Periodic reload every {args.reload_interval}s enabled")

    app = make_app()
    logger.info(f"Starting search server on http://{args.host}:{args.port}")
    logger.info(f"  Default policy: {policies['__default__'].name}")
    logger.info(f"  Coverage threshold: {min_coverage:.2f}")
    n_total = len(backend.senses)
    for m in backend.embedders:
        n = len(backend.embedders[m].entry_ids)
        cov = backend.embedder_coverage(m)
        status = backend.embedder_status(m, min_coverage)
        status_label = {"complete": "COMPLETE", "partial": "PARTIAL (excluded from cascade)", "empty": "EMPTY"}[status]
        logger.info(f"  Embedder {m}: {n:,}/{n_total:,} senses ({cov:.1%}) -- {status_label}")
    logger.info(f"  Cascade (en):           {cascade_en}")
    logger.info(f"  Auth: {'required' if api_token else 'disabled (loopback)'}")
    logger.info(f"  Reranker (server-side): {'enabled' if reranker_cfg.get('enabled') else 'disabled'}")
    logger.info(f"  BM25 (server-side): mode={bm25_cfg.get('mode', 'never')}")
    logger.info(f"  LLM tiebreak (server-side): mode={tiebreak_cfg.get('mode', 'never')}")
    logger.info(f"  Periodic reload: {'enabled every ' + str(args.reload_interval) + 's' if args.reload_interval > 0 else 'disabled'}")
    logger.info(f"  Structured query embedding: ENABLED when focus_word is provided")
    logger.info(f"  Porter stemmer fallback: ENABLED for missing lemma forms")
    logger.info(f"  Compound component matching: ENABLED for multi‑word entries")
    if improve_cfg.get("enabled"):
        logger.info(f"  Auto‑improvement: ENABLED (lemma‑group batching, synchronous, incremental update, script: {improve_cfg['script_path']})")
    else:
        logger.info(f"  Auto‑improvement: DISABLED (set [improve].enabled=true in TOML to enable)")
    logger.info(f"  Compound minting: ENABLED (threshold < {COMPOUND_THRESHOLD}, fast path via known compounds, failed-mint cache TTL={_FAILED_MINT_TTL}s)")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())