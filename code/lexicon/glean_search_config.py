#!/usr/bin/env python3
"""
glean_search_config.py -- shared config loader for client + server

Reads `search_config.toml` from the bundle directory or `~/.glean/`.
One file, three top-level sections:

    [retrieval]        -- what the search engine returns and how it ranks
    [search_pipeline]  -- server-side four-stage cascade
    [client_pipeline]  -- client-side four-stage cascade (mirror)

Each cascade has four stages:

    cosine retrieval    (stage 1; always on; entry point)
    reranker            (stage 2; cross-encoder)
    bm25                (stage 3; lexical scoring on retained candidates)
    llm_tiebreak        (stage 4; opt-in; world-knowledge tiebreak)

Each downstream stage has a uniform `mode` knob:
    "always"      = run every query
    "never"       = skip
    "when_tight"  = run only when prior-stage top-1/top-2 margin
                    is below this stage's margin_threshold

The LLM tiebreak stage adds a fourth mode, "when_tight_divergent":
fire only when the top candidates are close in score AND differ on
at least one of the configured `divergent_axes` metadata fields.

Back-compat: older TOML shapes are accepted and remapped forward.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore


# Filenames recognized, in priority order. Canonical name first.
CONFIG_FILENAMES = (
    "search_config.toml",
    "search_engine.toml",
    "glean_search_policy.toml",
)

GLEAN_HOME = Path.home() / ".glean"
DEFAULT_CONFIG_PATH = GLEAN_HOME / CONFIG_FILENAMES[0]
BUNDLE_DIR = Path(__file__).resolve().parent
BUNDLE_CONFIG_PATH = BUNDLE_DIR / CONFIG_FILENAMES[0]


def _first_existing(directory):
    for name in CONFIG_FILENAMES:
        p = directory / name
        if p.exists():
            return p
    return None


def resolve_config_path(explicit_path=None, config_dir=None):
    """Decide which config file to read, in priority order:

    1. explicit_path  -- caller passed --config
    2. config_dir/<recognized_filename>  -- caller pointed at a dir
    3. <bundle>/<recognized_filename>    -- TOML shipped alongside code
    4. ~/.glean/<recognized_filename>    -- user home (auto-created)
    """
    if explicit_path:
        return Path(explicit_path)
    if config_dir:
        p = _first_existing(Path(config_dir))
        if p is not None:
            return p
    p = _first_existing(BUNDLE_DIR)
    if p is not None:
        return p
    p = _first_existing(GLEAN_HOME)
    if p is not None:
        return p
    return DEFAULT_CONFIG_PATH


# ---------------------------------------------------------------------------
# Default pipeline shape. This is the canonical internal representation.
# ---------------------------------------------------------------------------

_RERANKER_MODELS = ["bge-reranker-v2-m3", "bge-reranker-large", "bge-reranker-base"]
_DEFAULT_DIVERGENT_AXES = ["register", "social_status", "temporal_status", "specificity"]


def _default_pipeline(side):
    """Default cascade for either 'server' or 'client'."""
    if side not in ("server", "client"):
        raise ValueError(f"side must be 'server' or 'client', got {side!r}")
    # Server-side defaults turn the reranker, BM25, and LLM tiebreak
    # all on in "when_tight" mode -- each stage fires only when the
    # prior stage left the top-1/top-2 margin below its threshold.
    # Client-side defaults are all 'never' so the client trusts the
    # server's already-narrowed result.
    reranker_mode = "when_tight" if side == "server" else "never"
    bm25_mode = "when_tight" if side == "server" else "never"
    tiebreak_mode = "when_tight" if side == "server" else "never"
    return {
        "cosine_top_n": 50,
        "cosine_top_n_high_polyseme": 100,
        "high_polyseme_threshold": 20,
        "reranker": {
            "mode": reranker_mode,
            "margin_threshold": 0.05,
            "top_n_out": 10,
            "models": list(_RERANKER_MODELS),
        },
        "bm25": {
            "mode": bm25_mode,
            "margin_threshold": 0.04,
            "abs_confidence_floor": 0.0,
            "top_n_out": 3,
            "fusion": "weighted",
            "weighted_alpha": 0.7,
            "stemmer": "porter",
            "lowercase": True,
        },
        "llm_tiebreak": {
            "mode": tiebreak_mode,
            "margin_threshold": 0.03,
            "abs_confidence_floor": 0.0,
            "divergent_axes": list(_DEFAULT_DIVERGENT_AXES),
            "top_n_to_llm": 5,
            "llm_wrapper": "llm_wrapper.py",
            "tier": "flash",
            "temp": 0.0,
        },
    }


def _builtin_defaults():
    """Hard-coded defaults that match the shipped TOML."""
    return {
        "retrieval": {
            "default_policy": "snap_to_standard",
            "embedder_min_coverage": 0.95,
            "embedder_cascade": {},
            "policies": {},
        },
        "search_pipeline": _default_pipeline("server"),
        "client_pipeline": _default_pipeline("client"),
    }


# ---------------------------------------------------------------------------
# Default TOML text (auto-created on first boot in ~/.glean/)
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_TEXT = '''# ============================================================
# GLEAN SEARCH CONFIG -- one file, three sections
# ============================================================
# [retrieval]        = what comes back and how it ranks
# [search_pipeline]  = server-side four-stage cascade
# [client_pipeline]  = client-side four-stage cascade
#
# Each cascade has four stages: cosine -> reranker -> bm25 -> llm.
# Each stage has a uniform `mode` knob:
#   "always"      = run every query
#   "never"       = skip
#   "when_tight"  = run only when prior-stage margin is tight
#
# LLM tiebreak has a fourth mode, "when_tight_divergent":
# fire only when the top candidates are close in score AND
# differ on at least one of the listed metadata axes.
# ============================================================

[retrieval]
default_policy = "snap_to_standard"
embedder_min_coverage = 0.95

[retrieval.embedder_cascade]
# Default is English-only (bge-large leads). Switch to the `multilingual`
# row when you need cross-lingual matching; bge-m3 trades English
# precision for multilingual coverage.
default = ["bge-large-en-v1", "bge-medium-en-v1", "bge-small-en-v1"]
en = ["bge-large-en-v1", "bge-medium-en-v1", "bge-small-en-v1"]
multilingual = ["bge-m3-v1", "bge-large-en-v1", "bge-small-en-v1"]

[retrieval.policies.snap_to_standard]
rewrite_to_standard_form = true
preserve_specialist_terms = true
audience_tier = "general"
exclude_social_status = ["slur", "offensive"]
exclude_temporal_status = ["obsolete"]
min_tier_returned = "improved"

[retrieval.policies.snap_to_neutral]
rewrite_to_standard_form = true
preserve_specialist_terms = true
audience_tier = "general"
snap_social_status = ["slur", "offensive", "vulgar"]
snap_temporal_status = ["obsolete"]
on_snap_failure = "drop"
exclude_social_status = []
exclude_temporal_status = []
min_tier_returned = "improved"


[search_pipeline]
cosine_top_n = 50
cosine_top_n_high_polyseme = 100
high_polyseme_threshold = 20

[search_pipeline.reranker]
mode = "when_tight"
margin_threshold = 0.05
top_n_out = 10
models = ["bge-reranker-v2-m3", "bge-reranker-large", "bge-reranker-base"]

[search_pipeline.bm25]
mode = "when_tight"
margin_threshold = 0.04
# Absolute-confidence floor: also fires this stage when the prior
# stage's top-1 score is below this floor, even if the top-1/top-2
# margin is wide. Catches the "cosine-flat" case. 0.0 disables.
abs_confidence_floor = 0.0
top_n_out = 3
fusion = "weighted"
weighted_alpha = 0.7
stemmer = "porter"
lowercase = true

[search_pipeline.llm_tiebreak]
mode = "when_tight"
margin_threshold = 0.03
abs_confidence_floor = 0.0
divergent_axes = ["register", "social_status", "temporal_status", "specificity"]
top_n_to_llm = 5
llm_wrapper = "llm_wrapper.py"
tier = "flash"
temp = 0.0


[client_pipeline]
cosine_top_n = 50
cosine_top_n_high_polyseme = 100
high_polyseme_threshold = 20

[client_pipeline.reranker]
mode = "never"
margin_threshold = 0.05
top_n_out = 10
models = ["bge-reranker-v2-m3", "bge-reranker-large", "bge-reranker-base"]

[client_pipeline.bm25]
mode = "never"
margin_threshold = 0.04
abs_confidence_floor = 0.0
top_n_out = 3
fusion = "weighted"
weighted_alpha = 0.7
stemmer = "porter"
lowercase = true

[client_pipeline.llm_tiebreak]
mode = "never"
margin_threshold = 0.03
abs_confidence_floor = 0.0
divergent_axes = ["register", "social_status", "temporal_status", "specificity"]
top_n_to_llm = 5
llm_wrapper = "llm_wrapper.py"
tier = "flash"
temp = 0.0
'''


def ensure_default_config(path=None):
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    if p.exists():
        return p
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(DEFAULT_CONFIG_TEXT, encoding="utf-8")
    return p


def load_config(path=None, config_dir=None):
    """Load search config TOML and normalize to the canonical shape."""
    p = resolve_config_path(explicit_path=path, config_dir=config_dir)
    if not p.exists():
        ensure_default_config(p)
    if tomllib is None:
        print("glean_search_config: tomllib unavailable; using built-in defaults",
              file=sys.stderr)
        return _builtin_defaults()
    with open(p, "rb") as f:
        raw = tomllib.load(f)
    return _normalize(raw)


# ---------------------------------------------------------------------------
# Normalizers. Convert whatever TOML shape the user has into the canonical
# internal shape with [search_pipeline] and [client_pipeline].
# ---------------------------------------------------------------------------

def _merge_pipeline(user_section, side):
    """Deep-merge a user pipeline section onto the defaults for that side."""
    base = _default_pipeline(side)
    if not user_section:
        return base
    out = dict(base)
    for key in ("cosine_top_n", "cosine_top_n_high_polyseme", "high_polyseme_threshold"):
        if key in user_section:
            out[key] = user_section[key]
    for stage in ("reranker", "bm25", "llm_tiebreak"):
        if stage in user_section:
            out[stage] = {**base[stage], **user_section[stage]}
    return out


def _remap_legacy_rerank_section(user_section, side):
    """Convert a [server_rerank] or [client_rerank] section to the new shape."""
    base = _default_pipeline(side)
    if not user_section:
        return base
    # Old shape:
    #   enabled, models, top_n, rerank_always, rerank_margin_threshold
    #   [..].llm_tiebreak: enabled, margin_threshold, llm_wrapper, tier, temp, top_n_to_llm
    enabled = bool(user_section.get("enabled", side == "server"))
    rerank_always = bool(user_section.get("rerank_always", False))
    if not enabled:
        new_rr_mode = "never"
    elif rerank_always:
        new_rr_mode = "always"
    else:
        new_rr_mode = "when_tight"
    base["reranker"]["mode"] = new_rr_mode
    if "rerank_margin_threshold" in user_section:
        base["reranker"]["margin_threshold"] = user_section["rerank_margin_threshold"]
    if "top_n" in user_section:
        base["reranker"]["top_n_out"] = user_section["top_n"]
    if "models" in user_section:
        base["reranker"]["models"] = list(user_section["models"])

    legacy_tb = user_section.get("llm_tiebreak", {})
    tb_enabled = bool(legacy_tb.get("enabled", False))
    base["llm_tiebreak"]["mode"] = "when_tight" if tb_enabled else "never"
    for k in ("margin_threshold", "llm_wrapper", "tier", "temp", "top_n_to_llm"):
        if k in legacy_tb:
            base["llm_tiebreak"][k] = legacy_tb[k]
    return base


def _remap_legacy_flat(raw):
    """Convert flat [reranker] + [llm_tiebreak] (oldest shape) into new shape."""
    legacy_rr = raw.get("reranker", {})
    legacy_tb = raw.get("llm_tiebreak", {})
    server = _default_pipeline("server")
    client = _default_pipeline("client")

    if legacy_rr:
        enabled = bool(legacy_rr.get("enabled", True))
        rerank_always = bool(legacy_rr.get("rerank_always", False))
        if not enabled:
            mode = "never"
        elif rerank_always:
            mode = "always"
        else:
            mode = "when_tight"
        server["reranker"]["mode"] = mode
        if "rerank_margin_threshold" in legacy_rr:
            server["reranker"]["margin_threshold"] = legacy_rr["rerank_margin_threshold"]
        if "top_n" in legacy_rr:
            server["reranker"]["top_n_out"] = legacy_rr["top_n"]
        if "models" in legacy_rr:
            server["reranker"]["models"] = list(legacy_rr["models"])

    if legacy_tb:
        server_enabled = bool(legacy_tb.get("server_enabled", False))
        client_enabled = bool(legacy_tb.get("client_enabled", False))
        server["llm_tiebreak"]["mode"] = "when_tight" if server_enabled else "never"
        client["llm_tiebreak"]["mode"] = "when_tight" if client_enabled else "never"
        for k in ("margin_threshold", "llm_wrapper", "tier", "temp", "top_n_to_llm"):
            if k in legacy_tb:
                server["llm_tiebreak"][k] = legacy_tb[k]
                client["llm_tiebreak"][k] = legacy_tb[k]
    return server, client


def _normalize(raw):
    """Map any supported TOML shape onto the canonical internal shape."""
    out = _builtin_defaults()

    # [retrieval] is the same shape across all generations.
    if "retrieval" in raw:
        out["retrieval"] = {**out["retrieval"], **raw["retrieval"]}

    # Preferred new shape.
    if "search_pipeline" in raw or "client_pipeline" in raw:
        if "search_pipeline" in raw:
            out["search_pipeline"] = _merge_pipeline(raw["search_pipeline"], "server")
        if "client_pipeline" in raw:
            out["client_pipeline"] = _merge_pipeline(raw["client_pipeline"], "client")
        return out

    # Previous-generation shape: [server_rerank] / [client_rerank].
    if "server_rerank" in raw or "client_rerank" in raw:
        if "server_rerank" in raw:
            out["search_pipeline"] = _remap_legacy_rerank_section(raw["server_rerank"], "server")
        if "client_rerank" in raw:
            out["client_pipeline"] = _remap_legacy_rerank_section(raw["client_rerank"], "client")
        return out

    # Oldest shape: flat [reranker] + [llm_tiebreak].
    if "reranker" in raw or "llm_tiebreak" in raw:
        server, client = _remap_legacy_flat(raw)
        out["search_pipeline"] = server
        out["client_pipeline"] = client
        return out

    return out


# ---------------------------------------------------------------------------
# Public accessors. New code should prefer `get_pipeline_config`.
# `get_reranker_config` and `get_tiebreak_config` are kept for compatibility
# with call sites that pre-date the four-stage cascade. They project the new
# shape into the flat shape those call sites expect.
# ---------------------------------------------------------------------------

def get_pipeline_config(cfg, side="server"):
    """Return the full cascade config for the given side."""
    if side not in ("server", "client"):
        raise ValueError(f"side must be 'server' or 'client', got {side!r}")
    section_name = f"{side[:6]}_pipeline" if side == "server" else "client_pipeline"
    # Above: "server"[:6] == "server", so section name is "search_pipeline" only
    # via this manual mapping. Keep the explicit branch for clarity.
    section_name = "search_pipeline" if side == "server" else "client_pipeline"
    section = (cfg or {}).get(section_name)
    if not section:
        return _default_pipeline(side)
    return _merge_pipeline(section, side)


def get_retrieval_config(cfg):
    base = _builtin_defaults()["retrieval"]
    user = (cfg or {}).get("retrieval", {})
    return {**base, **user}


def get_reranker_config(cfg, side="server"):
    """Compatibility shim: project the new cascade into the flat shape
    older call sites expect: {enabled, models, top_n, rerank_always,
    rerank_margin_threshold}."""
    pipeline = get_pipeline_config(cfg, side=side)
    rr = pipeline["reranker"]
    mode = rr.get("mode", "never")
    return {
        "enabled": mode != "never",
        "models": list(rr.get("models", _RERANKER_MODELS)),
        "top_n": rr.get("top_n_out", 10),
        "rerank_always": mode == "always",
        "rerank_margin_threshold": rr.get("margin_threshold", 0.05),
    }


def get_tiebreak_config(cfg, side="server"):
    """Compatibility shim: project the new cascade into the flat shape
    older call sites expect, plus synthesized `server_enabled` /
    `client_enabled` keys."""
    pipeline = get_pipeline_config(cfg, side=side)
    tb = pipeline["llm_tiebreak"]
    mode = tb.get("mode", "never")
    enabled = mode != "never"
    out = {
        "enabled": enabled,
        "mode": mode,
        "margin_threshold": tb.get("margin_threshold", 0.03),
        "abs_confidence_floor": tb.get("abs_confidence_floor", 0.0),
        "divergent_axes": list(tb.get("divergent_axes", _DEFAULT_DIVERGENT_AXES)),
        "llm_wrapper": tb.get("llm_wrapper", "llm_wrapper.py"),
        "tier": tb.get("tier", "flash"),
        "temp": tb.get("temp", 0.0),
        "top_n_to_llm": tb.get("top_n_to_llm", 5),
    }
    out["server_enabled"] = enabled if side == "server" else False
    out["client_enabled"] = enabled if side == "client" else False
    return out


def get_bm25_config(cfg, side="server"):
    """Return the BM25 stage config for the given side."""
    pipeline = get_pipeline_config(cfg, side=side)
    return dict(pipeline["bm25"])
