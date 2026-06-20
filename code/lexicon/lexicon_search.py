#!/usr/bin/env python3
"""
lexicon_search.py -- shared search library for the SGF lexicon

This is the canonical lexicon-search code. Two consumers import it:

  1. glean_search_server.py -- a long-running FastAPI daemon that
     exposes the functions in this file over HTTP. Used by downstream
     tools (GLEAN compiler, ad-hoc query CLI, etc.) so they don't
     each have to load the embedder + matrix.

  2. harvest_semantic_relations.py (Stage 11) -- the lexicon
     bootstrap's own resolver imports these functions IN-PROCESS to
     ground LLM-produced relation targets to lexicon wsids. Single
     bootstrap process; no HTTP needed.

Both consumers get the same logic. There is only ONE implementation
of search, policy application, and standard-form rewrite. If a bug
exists in the lexicon bootstrap resolver, it also exists in
production retrieval; fixing it fixes both.

DESIGN NOTES
------------
- No classes. State is a context dict returned by load_lexicon(). All
  functions take the context dict as their first argument.
- No regex.
- NumPy is used for the topk inner kernel (BLAS matmul over the
  candidate-set vectors). For lemma-restricted queries the candidate
  set is small (typically 1-40 senses), so the matmul is trivial. For
  unrestricted queries it's the full lexicon, so the BLAS path
  matters.
- Policy is a plain dict. It is loaded from TOML if a path is given,
  or built from the DEFAULT_POLICY constant otherwise.
- The lexicon backend is read-only. Nothing in this file writes to the
  database.
"""

from __future__ import annotations

import sqlite3
import struct
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIER_ORDER = [
    "raw", "provisional", "embedded_v1", "improved",
    "embedded_v2", "clustered", "related",
]

# The default policy set. Used when no policy file is provided.
# Conservative: snap to standard, drop slurs / obsolete, soft-demote
# dated and slang, preserve specialist terms (the leukemia rule).
DEFAULT_POLICIES = {
    "snap_to_standard": {
        "rewrite_to_standard_form": True,
        "preserve_specialist_terms": True,
        "audience_tier": "general",
        "exclude_social_status": ["slur", "offensive"],
        "exclude_temporal_status": ["obsolete"],
        "min_tier_returned": "improved",
        "demote_register": {
            "slang": 0.08, "vulgar": 0.15, "poetic": 0.03,
        },
        "demote_temporal": {
            "dated": 0.05, "archaic": 0.10,
        },
        "demote_social": {
            "flagged": 0.10,
        },
    },
    "preserve_register": {
        "rewrite_to_standard_form": False,
        "preserve_specialist_terms": True,
        "audience_tier": "general",
        "exclude_social_status": ["slur"],
        "exclude_temporal_status": [],
        "min_tier_returned": "improved",
        "demote_register": {},
        "demote_temporal": {},
        "demote_social": {},
    },
    "research_unfiltered": {
        "rewrite_to_standard_form": False,
        "preserve_specialist_terms": True,
        "audience_tier": "general",
        "exclude_social_status": [],
        "exclude_temporal_status": [],
        "min_tier_returned": "raw",
        "demote_register": {},
        "demote_temporal": {},
        "demote_social": {},
    },
}


# ---------------------------------------------------------------------------
# Loading the lexicon into RAM
# ---------------------------------------------------------------------------

def load_lexicon(db_path, verbose=True):
    """Load the SGF lexicon into a context dict suitable for searching.

    Returns a dict with these keys:
        senses        : dict wsid -> sense dict (lemma, microgloss, ...)
        embedders     : dict method -> embedder dict with:
                          method, dim, wsids (np.int64 array),
                          vectors (np.float32 (N, D) array,
                          L2-normalized), wsid_to_idx (dict)
        content_groups : dict group_id -> {audience_tier, standard_form_wsid}
        wsid_to_groups : dict wsid -> {audience_tier: group_id}
        tier_counts    : dict tier -> count of senses at that tier
        lemma_index    : dict lemma.lower() -> list of wsids
        namespaces     : set of namespace strings
        load_seconds   : float, time taken to load

    The context dict is read-only after this call. Multiple search
    operations can be run against it concurrently.
    """
    t0 = time.time()
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA query_only = 1")
    cur = conn.cursor()

    # Detect which v3+ columns are present so we degrade gracefully on
    # older DBs (specificity, maturity_tier, namespace).
    cur.execute("PRAGMA table_info(sgf_lexicon)")
    sgf_cols = {row[1] for row in cur.fetchall()}
    has_spec = "specificity" in sgf_cols
    has_tier = "maturity_tier" in sgf_cols
    has_ns = "namespace" in sgf_cols

    # Load senses
    select_cols = [
        "wiktionary_source_id", "lemma", "pos_simple",
        "microgloss", "canonical_id",
        "register", "temporal_status", "social_status",
    ]
    if has_spec:
        select_cols.append("specificity")
    if has_tier:
        select_cols.append("maturity_tier")
    if has_ns:
        select_cols.append("namespace")

    cur.execute(
        f"SELECT {', '.join(select_cols)} FROM sgf_lexicon "
        f"WHERE canonical_id IS NOT NULL"
    )

    senses = {}
    tier_counts = {t: 0 for t in TIER_ORDER}
    lemma_index = {}
    namespaces = set()
    for r in cur.fetchall():
        idx = 0
        wsid = r[idx]; idx += 1
        lemma = r[idx]; idx += 1
        pos_simple = r[idx]; idx += 1
        microgloss = r[idx]; idx += 1
        canonical_id = r[idx]; idx += 1
        register = r[idx]; idx += 1
        temporal_status = r[idx]; idx += 1
        social_status = r[idx]; idx += 1
        if has_spec:
            specificity = r[idx]; idx += 1
        else:
            specificity = "general"
        if has_tier:
            maturity_tier = r[idx]; idx += 1
        else:
            maturity_tier = "improved"
        if has_ns:
            namespace = r[idx]; idx += 1
        else:
            namespace = "core"

        senses[wsid] = {
            "wsid": wsid,
            "lemma": lemma,
            "pos_simple": pos_simple,
            "microgloss": microgloss,
            "canonical_id": canonical_id,
            "register": register,
            "temporal_status": temporal_status,
            "social_status": social_status,
            "specificity": specificity or "general",
            "maturity_tier": maturity_tier or "improved",
            "namespace": namespace or "core",
        }
        tier_counts[maturity_tier] = tier_counts.get(maturity_tier, 0) + 1
        namespaces.add(namespace or "core")
        if lemma:
            lemma_index.setdefault(lemma.lower(), []).append(wsid)

    if verbose:
        print(f"  Loaded {len(senses):,} senses in {time.time()-t0:.1f}s")

    # Load embeddings, grouped by method. Materialize to NumPy.
    cur.execute(
        "SELECT wiktionary_source_id, embedding_method, embed "
        "FROM sense_embedding WHERE embed IS NOT NULL"
    )
    per_method_wsids = {}
    per_method_blobs = {}
    for wsid, method, blob in cur:
        if wsid not in senses:
            continue
        per_method_wsids.setdefault(method, []).append(wsid)
        per_method_blobs.setdefault(method, []).append(blob)

    embedders = {}
    for method, wsids_l in per_method_wsids.items():
        blobs = per_method_blobs[method]
        # Determine dim from first blob
        first_blob = blobs[0]
        dim = len(first_blob) // 4

        n = len(wsids_l)
        vectors = np.empty((n, dim), dtype=np.float32)
        for i, blob in enumerate(blobs):
            if len(blob) // 4 != dim:
                # Skip dim-mismatched rows
                vectors[i] = 0.0
                continue
            vectors[i] = np.frombuffer(blob, dtype="<f4", count=dim)
        # Normalize defensively
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        vectors = vectors / norms

        wsid_arr = np.array(wsids_l, dtype=np.int64)
        wsid_to_idx = {int(w): i for i, w in enumerate(wsid_arr)}
        embedders[method] = {
            "method": method,
            "dim": dim,
            "wsids": wsid_arr,
            "vectors": vectors,
            "wsid_to_idx": wsid_to_idx,
        }
        if verbose:
            print(f"  Embedder {method}: {n:,} senses, dim={dim}")

    # Load content_identical groups if present
    content_groups = {}
    wsid_to_groups = {}
    try:
        cur.execute(
            "SELECT group_id, audience_tier, standard_form_wsid "
            "FROM content_identical_group"
        )
        for gid, tier, std_wsid in cur.fetchall():
            content_groups[gid] = {
                "audience_tier": tier,
                "standard_form_wsid": std_wsid,
            }
        cur.execute(
            "SELECT cim.wsid, cig.audience_tier, cim.group_id "
            "FROM content_identical_member cim "
            "JOIN content_identical_group cig ON cig.group_id = cim.group_id"
        )
        for wsid, tier, gid in cur.fetchall():
            wsid_to_groups.setdefault(wsid, {})[tier] = gid
        if verbose:
            n_grp = len(content_groups)
            n_mem = sum(len(g) for g in wsid_to_groups.values())
            print(f"  Content-identical groups: {n_grp:,} groups, {n_mem:,} memberships")
    except sqlite3.OperationalError:
        if verbose:
            print("  No content_identical tables (pre-Stage-9 lexicon)")

    conn.close()
    load_seconds = time.time() - t0
    if verbose:
        print(f"  Lexicon fully loaded in {load_seconds:.1f}s")

    return {
        "db_path": str(db_path),
        "senses": senses,
        "embedders": embedders,
        "content_groups": content_groups,
        "wsid_to_groups": wsid_to_groups,
        "tier_counts": tier_counts,
        "lemma_index": lemma_index,
        "namespaces": namespaces,
        "load_seconds": load_seconds,
    }


# ---------------------------------------------------------------------------
# Embedder selection
# ---------------------------------------------------------------------------

def best_embedder_for_language(ctx, language="en"):
    """Pick the best available embedder for the given language."""
    embedders = ctx["embedders"]
    lang = (language or "en").lower()
    if lang in ("en", "english"):
        for pref in ("bge-large-en-v1", "bge-large", "bge-m3-v1", "bge-m3", "bge-small-en-v1"):
            if pref in embedders:
                return pref
            for m in embedders:
                if m.startswith(pref):
                    return m
    for m in embedders:
        if "m3" in m.lower():
            return m
    for m in embedders:
        if "large" in m.lower():
            return m
    return next(iter(embedders), None)


# ---------------------------------------------------------------------------
# topk: the nearest-neighbor primitive
# ---------------------------------------------------------------------------

def topk(ctx, query_vec, method, k, lemma_restrict=None, pos_restrict=None,
         auto_resolve_forms=False, db_path=None):
    """Return top-K (wsid, cosine_similarity) pairs.

    Arguments:
        ctx           : the loaded lexicon context dict
        query_vec     : np.ndarray or list of floats, length=embedder dim,
                        L2-normalized
        method        : which embedder to query (e.g. "bge-large-en-v1")
        k             : number of results to return
        lemma_restrict: if given, restrict candidates to senses with this
                        lemma (case-insensitive). May be a string or a
                        list of strings (multiple lemmas merged).
        pos_restrict  : if given, further restrict by pos_simple.
        auto_resolve_forms : when True, look up `lemma_restrict` in the
                        lemma_form table and expand to the set of
                        candidate lemmas. Lets the caller pass
                        "burned" and get back senses of "burn".
                        Requires `db_path` to be set so the resolver
                        can read lemma_form. Silently no-op if the
                        table does not exist.
        db_path       : path to the sgf_lexicon.db; only consulted
                        when auto_resolve_forms=True.

    Returns: list of (wsid, cosine) tuples sorted descending by cosine.
    """
    emb = ctx["embedders"].get(method)
    if emb is None:
        return []
    senses = ctx["senses"]
    lemma_index = ctx["lemma_index"]

    qv = np.asarray(query_vec, dtype=np.float32)
    # Normalize defensively
    qn = float(np.linalg.norm(qv))
    if qn > 0:
        qv = qv / qn

    if lemma_restrict:
        # Normalize to a list of lowercased lemmas. Then optionally
        # expand via the form-to-lemma resolver.
        if isinstance(lemma_restrict, str):
            wanted_lemmas = [lemma_restrict.lower()]
        else:
            wanted_lemmas = [str(l).lower() for l in lemma_restrict if l]

        if auto_resolve_forms and db_path is not None:
            try:
                import lemma_resolver
                expanded = list(wanted_lemmas)
                seen = set(expanded)
                for surface in wanted_lemmas:
                    for lemma in lemma_resolver.expand_to_lemmas(
                            surface, db_path, prefer_pos=pos_restrict):
                        if lemma not in seen:
                            expanded.append(lemma)
                            seen.add(lemma)
                wanted_lemmas = expanded
            except Exception:
                # Resolver failure is non-fatal -- fall through with
                # the un-expanded list. This keeps lookup working on
                # DBs that have not yet built lemma_form.
                pass

        candidate_wsids = []
        for lemma in wanted_lemmas:
            candidate_wsids.extend(lemma_index.get(lemma, []))
        if pos_restrict:
            candidate_wsids = [
                w for w in candidate_wsids
                if senses.get(w, {}).get("pos_simple") == pos_restrict
            ]
        # Map wsids to row indices in the embedder's matrix
        candidate_idxs = [
            emb["wsid_to_idx"][w] for w in candidate_wsids
            if w in emb["wsid_to_idx"]
        ]
        if not candidate_idxs:
            return []
        idx_arr = np.array(candidate_idxs, dtype=np.int64)
        cand_vecs = emb["vectors"][idx_arr]
        sims = cand_vecs @ qv
        # Sort within the small candidate set
        order = np.argsort(-sims)
        out = []
        for o in order[:k]:
            out.append((int(emb["wsids"][idx_arr[o]]), float(sims[o])))
        return out
    else:
        # Full lexicon search
        sims = emb["vectors"] @ qv
        # argpartition + sort the top-K
        kk = min(k, sims.shape[0])
        part_idx = np.argpartition(-sims, kth=kk - 1)[:kk]
        part_sims = sims[part_idx]
        order = np.argsort(-part_sims)
        out = []
        for o in order:
            row = int(part_idx[o])
            out.append((int(emb["wsids"][row]), float(part_sims[o])))
        return out


def lookup_by_canonical_id(ctx, cid):
    """Return the sense dict whose canonical_id matches, or None."""
    for s in ctx["senses"].values():
        if s["canonical_id"] == cid:
            return s
    return None


def lookup_by_lemma(ctx, lemma, pos=None):
    """Return all sense dicts for a given lemma (optionally pos-filtered)."""
    wsids = ctx["lemma_index"].get(lemma.lower(), [])
    out = []
    for w in wsids:
        s = ctx["senses"].get(w)
        if s is None:
            continue
        if pos and s["pos_simple"] != pos:
            continue
        out.append(s)
    return out


def find_contrast_set(ctx, wsid, embedding_method,
                     k_cousins=5, cousin_min_cosine=0.70):
    """Return the disambiguation contrast set for a sense.

    Used by the LLM improver to sharpen microglosses: when we ask the
    LLM to improve sense X, we show it the OTHER senses it needs to
    distinguish itself from. Two categories:

      lemma_mates : other senses that share this lemma. The microgloss
                    must disambiguate from these for INTRA-LANGUAGE
                    grounding (Part 7.4 -- when the query has a lemma).

      cousins     : other senses near this one in embedding space that
                    are NOT lemma-mates. The microgloss must
                    disambiguate from these for CROSS-LANGUAGE
                    retrieval (Part 7.5 -- when there is no lemma
                    overlap and the microgloss content has to do all
                    the disambiguating work).

    Arguments:
        wsid              : the source sense
        embedding_method  : which embedder to use for cousin search
        k_cousins         : max number of cousins to return (default 5)
        cousin_min_cosine : cousin must be at least this similar (0.70)

    Returns: dict with keys 'lemma_mates' and 'cousins'.
        lemma_mates : list of sense dicts (excluding self)
        cousins     : list of (sense_dict, cosine) tuples, sorted desc

    Returns None if the sense or embedder is missing.
    """
    src = ctx["senses"].get(wsid)
    if src is None:
        return None
    emb = ctx["embedders"].get(embedding_method)
    if emb is None:
        return None

    # Lemma-mates: cheap database lookup.
    lemma = src["lemma"]
    lemma_mate_wsids = ctx["lemma_index"].get(lemma.lower(), [])
    lemma_mates = [
        ctx["senses"][w] for w in lemma_mate_wsids
        if w != wsid and w in ctx["senses"]
    ]
    lemma_mate_set = set(lemma_mate_wsids)

    # Cousins: cosine search excluding self and lemma-mates.
    idx = emb["wsid_to_idx"].get(wsid)
    if idx is None:
        cousins = []
    else:
        qv = emb["vectors"][idx]
        # Fetch more than we need so we can filter out lemma-mates and
        # still have k_cousins left.
        raw = topk(ctx, qv, embedding_method,
                   k=k_cousins + len(lemma_mate_set) + 1)
        cousins = []
        for w, cos in raw:
            if w == wsid:
                continue
            if w in lemma_mate_set:
                continue
            if cos < cousin_min_cosine:
                continue
            cand = ctx["senses"].get(w)
            if cand is None:
                continue
            cousins.append((cand, float(cos)))
            if len(cousins) >= k_cousins:
                break

    return {
        "lemma_mates": lemma_mates,
        "cousins": cousins,
    }


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

def get_default_policy(name="snap_to_standard"):
    """Return a fresh copy of one of the built-in default policies.

    Use this when you don't have a policy.toml file (e.g. in the
    in-process bootstrap resolver).
    """
    if name not in DEFAULT_POLICIES:
        raise ValueError(f"unknown policy {name!r}; available: {list(DEFAULT_POLICIES)}")
    pol = dict(DEFAULT_POLICIES[name])
    pol["name"] = name
    # Deep-copy the nested dicts/lists so callers can mutate freely
    pol["exclude_social_status"] = list(pol["exclude_social_status"])
    pol["exclude_temporal_status"] = list(pol["exclude_temporal_status"])
    pol["demote_register"] = dict(pol["demote_register"])
    pol["demote_temporal"] = dict(pol["demote_temporal"])
    pol["demote_social"] = dict(pol["demote_social"])
    return pol


def merge_policy_overrides(base_policy, overrides):
    """Return a new policy dict with overrides applied on top of base."""
    if not overrides:
        return base_policy
    out = dict(base_policy)
    for k, v in overrides.items():
        if k in out:
            out[k] = v
    out["name"] = f"{base_policy.get('name', 'policy')}+override"
    return out


def apply_policy(ctx, raw_results, policy):
    """Convert raw (wsid, cosine) results into policy-filtered dicts.

    Arguments:
        ctx          : loaded lexicon context
        raw_results  : list of (wsid, cosine) from topk()
        policy       : a policy dict (use get_default_policy() to get one)

    Returns: list of result dicts, sorted by post-penalty score
    descending. Each result includes the matched and (if rewritten)
    display fields, so callers can distinguish "we matched X, we're
    showing you Y because of snap-to-standard."
    """
    senses = ctx["senses"]
    content_groups = ctx["content_groups"]
    wsid_to_groups = ctx["wsid_to_groups"]

    min_tier_returned = policy.get("min_tier_returned", "raw")
    min_tier_idx = (
        TIER_ORDER.index(min_tier_returned)
        if min_tier_returned in TIER_ORDER else 0
    )
    exclude_social = set(policy.get("exclude_social_status", []))
    exclude_temporal = set(policy.get("exclude_temporal_status", []))
    demote_register = policy.get("demote_register", {})
    demote_temporal = policy.get("demote_temporal", {})
    demote_social = policy.get("demote_social", {})
    rewrite = bool(policy.get("rewrite_to_standard_form", False))
    preserve_specialist = bool(policy.get("preserve_specialist_terms", True))
    audience_tier = policy.get("audience_tier", "general")

    out = []
    for wsid, raw_score in raw_results:
        sense = senses.get(wsid)
        if sense is None:
            continue

        # Tier floor
        sense_tier = sense.get("maturity_tier") or "raw"
        sense_tier_idx = (
            TIER_ORDER.index(sense_tier) if sense_tier in TIER_ORDER else 0
        )
        if sense_tier_idx < min_tier_idx:
            continue

        # Hard exclusions
        if sense.get("social_status") in exclude_social:
            continue
        if sense.get("temporal_status") in exclude_temporal:
            continue

        # Demotions
        penalty = 0.0
        penalty += demote_register.get(sense.get("register") or "", 0.0)
        penalty += demote_temporal.get(sense.get("temporal_status") or "", 0.0)
        penalty += demote_social.get(sense.get("social_status") or "", 0.0)
        score = raw_score - penalty

        # Standard-form rewrite
        rewritten_to_wsid = None
        rewritten_to_cid = None
        if rewrite:
            if preserve_specialist and sense.get("specificity") in (
                "specialist", "technical"
            ):
                pass  # leukemia rule -- never snap specialist terms
            else:
                grp_map = wsid_to_groups.get(wsid, {})
                gid = grp_map.get(audience_tier)
                if gid is not None:
                    grp = content_groups.get(gid)
                    std_wsid = grp.get("standard_form_wsid") if grp else None
                    if std_wsid and std_wsid != wsid:
                        std_sense = senses.get(std_wsid)
                        if std_sense is not None:
                            rewritten_to_wsid = std_wsid
                            rewritten_to_cid = std_sense["canonical_id"]

        # Pick the sense for display
        display_sense = (
            senses[rewritten_to_wsid] if rewritten_to_wsid is not None else sense
        )
        out.append({
            "wsid": display_sense["wsid"],
            "canonical_id": display_sense["canonical_id"],
            "lemma": display_sense["lemma"],
            "pos_simple": display_sense["pos_simple"],
            "microgloss": display_sense["microgloss"],
            "score": round(score, 6),
            "raw_cosine": round(raw_score, 6),
            "penalty": round(penalty, 6),
            "register": display_sense["register"],
            "temporal_status": display_sense["temporal_status"],
            "social_status": display_sense["social_status"],
            "specificity": display_sense["specificity"],
            "maturity_tier": display_sense["maturity_tier"],
            "namespace": display_sense["namespace"],
            "matched_wsid": sense["wsid"],
            "matched_canonical_id": sense["canonical_id"],
            "rewritten_to_standard": rewritten_to_cid is not None,
        })

    out.sort(key=lambda r: r["score"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# Embedder runtime (lazy ONNX loader)
# ---------------------------------------------------------------------------

# Cache embedder runtimes by method; loaded on first use.
_embedder_runtime_cache = {}


def embedder_runtime_available():
    """Return True if onnxruntime + tokenizers are importable."""
    try:
        import onnxruntime  # noqa: F401
        import tokenizers   # noqa: F401
        return True
    except ImportError:
        return False


def embed_text(text, method):
    """Embed a single text string using the given embedder method.

    Loads the embedder on first call per method; subsequent calls reuse
    the cached runtime. Returns an np.float32 array, L2-normalized.

    Raises RuntimeError if onnxruntime / tokenizers / huggingface_hub
    are not installed.
    """
    if method not in _embedder_runtime_cache:
        _embedder_runtime_cache[method] = _load_embedder_runtime(method)
    embed_fn = _embedder_runtime_cache[method]
    return embed_fn(text)


def _load_embedder_runtime(method):
    """Build a closure that embeds text under the given method."""
    try:
        import onnxruntime
        from tokenizers import Tokenizer
        from huggingface_hub import hf_hub_download
    except ImportError as e:
        raise RuntimeError(
            f"Embedder runtime requires onnxruntime, tokenizers, "
            f"huggingface_hub. Missing: {e}"
        )

    repo_map = {
        "bge-small-en-v1": ("Xenova/bge-small-en-v1.5", "BAAI/bge-small-en-v1.5"),
        "bge-large-en-v1": ("Xenova/bge-large-en-v1.5", "BAAI/bge-large-en-v1.5"),
        "bge-m3":          ("Xenova/bge-m3", "BAAI/bge-m3"),
        "bge-m3-v1":       ("Xenova/bge-m3", "BAAI/bge-m3"),
    }
    onnx_repo, tok_repo = repo_map.get(
        method,
        ("Xenova/bge-large-en-v1.5", "BAAI/bge-large-en-v1.5"),
    )
    onnx_path = hf_hub_download(onnx_repo, "onnx/model.onnx")
    tok_path = hf_hub_download(tok_repo, "tokenizer.json")
    sess = onnxruntime.InferenceSession(
        onnx_path, providers=["CPUExecutionProvider"]
    )
    tok = Tokenizer.from_file(tok_path)
    tok.enable_truncation(max_length=256)
    tok.enable_padding(length=256)

    def embed_fn(text):
        enc = tok.encode(text or "")
        ort_in = {
            "input_ids": np.array([enc.ids], dtype="int64"),
            "attention_mask": np.array([enc.attention_mask], dtype="int64"),
            "token_type_ids": np.array([enc.type_ids], dtype="int64"),
        }
        out = sess.run(None, ort_in)[0][0][0]  # CLS pooling
        arr = np.asarray(out, dtype=np.float32)
        n = float(np.linalg.norm(arr))
        if n > 0:
            arr = arr / n
        return arr

    return embed_fn


# ---------------------------------------------------------------------------
# Convenience: full pipeline in one call (load + embed + topk + policy)
# ---------------------------------------------------------------------------

def search(
    ctx, text=None, query_vec=None, k=10, lemma_restrict=None,
    pos_restrict=None, method=None, language="en", policy_name="snap_to_standard",
    policy_overrides=None,
):
    """High-level search: embed (if text), topk, apply policy.

    This is the function downstream code (the search server, Stage 11
    resolver, query CLI) call. It is the same code path for everyone.
    """
    if query_vec is None and text is None:
        raise ValueError("provide text or query_vec")

    if method is None:
        method = best_embedder_for_language(ctx, language)
    if method is None:
        return {"results": [], "query_embedding_method": None,
                "policy_applied": policy_name}

    if query_vec is None:
        query_vec = embed_text(text, method)

    # Over-fetch then policy-filter so the post-filter result count is
    # still close to k.
    raw = topk(ctx, query_vec, method, k * 3, lemma_restrict, pos_restrict)
    pol = merge_policy_overrides(get_default_policy(policy_name), policy_overrides)
    results = apply_policy(ctx, raw, pol)[:k]
    return {
        "query_embedding_method": method,
        "policy_applied": pol["name"],
        "results": results,
        "n_results": len(results),
    }
