"""
sgflib.py -- shared utility module for the GLEAN family (v1.2).

Contents (all flat functions, no classes):

  - load_config(path)                 read sgf.toml -> dict
  - lookup_in_lexicon(...)            HTTP lookup against glean-search-server
  - get_server_health(cfg)            ping /health
  - embed_text(text, cfg)             HTTP /embed call
  - parse_mdkv(text)                  parse MDKV blocks
  - format_mdkv(kind, fields)         emit one MDKV block
  - get_reporting_verbs()             load reporting_verbs.txt
  - ROLES, CORE_ROLES, CONTEXTUAL_ROLES, LITERAL_TYPES, ...

DESIGN COMMITMENTS
------------------
- No classes. State is passed in explicitly. Each function is
  self-contained.
- @dataclass is NOT used. Records are plain dicts. Where a function
  returns a multi-field record, the keys are documented in its
  docstring.
- LLM calls go through call_llm.call_llm(). This module does NOT
  import a LLM-specific library or talk HTTP to any LLM provider.
- The search server is the ONE place that owns the embedder and the
  lexicon matrix. This module is a thin HTTP client.

LOOKUP RESULT DICT
------------------
lookup_in_lexicon() returns a dict with these keys:

    {
      "target":              str,
      "context":             str,
      "pos_hint":            str | None,
      "decision_level":      int,    # 1=exact, 2=cosine, 3=llm, 4=mint
      "decision_reason":     str,
      "canonical_id":        str | None,
      "confidence":          float,
      "matched_canonical_id": str | None,  # pre-snap; same as canonical_id when no rewrite
      "rewritten_to_standard": bool,
      "specificity":         str | None,
      "maturity_tier":       str | None,
      "policy_applied":      str | None,
      "minted":              bool,
      "candidates":          list[dict],   # see CANDIDATE DICT below
    }

CANDIDATE DICT
--------------
Each candidate inside the lookup result:

    {
      "canonical_id": str,
      "lemma":        str,
      "pos":          str,
      "microgloss":   str,
      "cosine":       float,
    }
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    import tomllib                # Python 3.11+
except ImportError:               # pragma: no cover
    import tomli as tomllib       # type: ignore


# ===========================================================================
# The closed grammar (15 roles)
# ===========================================================================

CORE_ROLES = (
    "HAS_AGENT",
    "HAS_PATIENT",
    "HAS_THEME",
    "HAS_EXPERIENCER",
    "HAS_RECIPIENT",
    "HAS_BENEFICIARY",
)

CONTEXTUAL_ROLES = (
    "HAS_TIME",
    "HAS_LOCATION",
    "HAS_SOURCE",
    "HAS_DESTINATION",
    "HAS_MANNER",
    "HAS_INSTRUMENT",
    "HAS_CAUSE",
    "HAS_REASON",
    "HAS_ATTRIBUTE",
)

ROLES = CORE_ROLES + CONTEXTUAL_ROLES
assert len(ROLES) == 15, "the closed grammar must have exactly 15 roles"


# ===========================================================================
# Literal entity types
# ===========================================================================

LITERAL_TYPES = frozenset({"year", "int_small"})
LITERAL_NER_LABELS = frozenset({
    "DATE", "TIME", "CARDINAL", "ORDINAL",
    "MONEY", "PERCENT", "QUANTITY",
})


# ===========================================================================
# Reporting verbs
# ===========================================================================

_REPORTING_VERBS_CACHE = None


def get_reporting_verbs(bundle_dir=None):
    """Load and cache the reporting-verb lemma set from reporting_verbs.txt.

    Returns a frozenset of lowercase lemmas.
    """
    global _REPORTING_VERBS_CACHE
    if _REPORTING_VERBS_CACHE is not None:
        return _REPORTING_VERBS_CACHE
    base = Path(bundle_dir) if bundle_dir else Path(__file__).resolve().parent
    p = base / "reporting_verbs.txt"
    verbs = set()
    if p.exists():
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#"):
                verbs.add(line.lower())
    _REPORTING_VERBS_CACHE = frozenset(verbs)
    return _REPORTING_VERBS_CACHE


# ===========================================================================
# Config loader (returns a plain dict)
# ===========================================================================

def _find_config_path():
    env = os.environ.get("SGF_CONFIG")
    if env:
        p = Path(env).expanduser()
        if p.exists():
            return p
        raise FileNotFoundError(
            f"SGF_CONFIG points to {p} but no file found there."
        )

    cwd_cfg = Path.cwd() / "sgf.toml"
    if cwd_cfg.exists():
        return cwd_cfg

    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", "")) / "sgf" / "sgf.toml"
        if appdata.exists():
            return appdata
    else:
        home_cfg = Path.home() / ".config" / "sgf" / "sgf.toml"
        if home_cfg.exists():
            return home_cfg

    script_cfg = Path(__file__).resolve().parent / "sgf.toml"
    if script_cfg.exists():
        return script_cfg

    raise FileNotFoundError(
        "Could not find sgf.toml. Set SGF_CONFIG, put it in cwd, or "
        "place it next to the GLEAN scripts."
    )


def load_config(path=None):
    """Find and parse sgf.toml. Returns a dict whose top-level keys are
    the TOML sections (lexicon, search_server, lookup, llm, ...).

    Two synthetic keys are added on top:
      "_config_path"  -- the resolved path on disk
      "_lexicon_db_path", "_synapse_store_path", "_default_embedding_method"
        for convenience.
    """
    cfg_path = Path(path) if path else _find_config_path()
    with open(cfg_path, "rb") as f:
        raw = tomllib.load(f)
    raw["_config_path"] = str(cfg_path)
    if "lexicon" in raw:
        raw["_lexicon_db_path"] = raw["lexicon"].get("db_path", "")
        raw["_default_embedding_method"] = raw["lexicon"].get(
            "default_embedding_method", "bge-large-en-v1"
        )
    if "synapse_store" in raw:
        raw["_synapse_store_path"] = raw["synapse_store"].get("db_path", "")
    return raw


# ===========================================================================
# MDKV: markdown-delimited key:value blocks
# ===========================================================================
# The agreed LLM output format. NEVER JSON.
#
# Wire format:
#   :::<kind>
#   key1: value1
#   key2: value2
#   ...
#   :::
#
# Multi-line values can be expressed by indenting continuation lines:
#   summary: This is the first line
#     and this is the second.
# ===========================================================================

_MDKV_FENCE = re.compile(r":::([a-zA-Z0-9_-]+)\s*$")
_MDKV_END = re.compile(r":::\s*$")
_MDKV_KV = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_.-]*):\s*(.*)$")


def format_mdkv(kind, fields):
    """Format a single MDKV block. fields is a dict[str, str|int|float|bool].

    Returns a string ending with a newline.
    """
    lines = [f":::{kind}"]
    for k, v in fields.items():
        if v is None:
            continue
        if isinstance(v, bool):
            s = "true" if v else "false"
        else:
            s = str(v).replace("\n", "\n  ")  # indent continuations
        lines.append(f"{k}: {s}")
    lines.append(":::")
    lines.append("")
    return "\n".join(lines)


def parse_mdkv(text):
    """Parse all MDKV blocks in text. Returns a list[dict].

    Each dict has a synthetic key "_kind" with the block's kind tag.
    Unknown content outside fences is ignored.
    """
    blocks = []
    current = None
    current_key = None
    for line in text.splitlines():
        if current is None:
            m = _MDKV_FENCE.match(line.strip())
            if m:
                current = {"_kind": m.group(1)}
                current_key = None
            continue
        # Inside a block
        if _MDKV_END.match(line.strip()) and not _MDKV_FENCE.match(line.strip()):
            blocks.append(current)
            current = None
            current_key = None
            continue
        # Continuation line (indented, no colon at start)
        if line.startswith(("  ", "\t")) and current_key is not None:
            current[current_key] = current.get(current_key, "") + "\n" + line.strip()
            continue
        m = _MDKV_KV.match(line.strip())
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip()
            current[key] = val
            current_key = key
    return blocks


# ===========================================================================
# HTTP helpers
# ===========================================================================

def _post_json(url, payload, token=None, timeout=30.0):
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-API-Key"] = token
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"search-server HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"cannot reach search server at {url}: {e}") from e


def _get_json(url, token=None, timeout=30.0):
    headers = {}
    if token:
        headers["X-API-Key"] = token
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"search-server HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"cannot reach search server at {url}: {e}") from e


def _server_url(cfg):
    srv = cfg.get("search_server", {})
    return srv.get("url", "http://127.0.0.1:8400").rstrip("/")


def _server_token(cfg):
    srv = cfg.get("search_server", {})
    return srv.get("api_token") or os.environ.get("GLEAN_API_TOKEN") or None


def _server_timeout(cfg):
    srv = cfg.get("search_server", {})
    return float(srv.get("timeout_seconds", 30.0))


def get_server_health(cfg):
    """Ping /health. Returns the parsed response dict."""
    return _get_json(_server_url(cfg) + "/health", _server_token(cfg),
                     _server_timeout(cfg))


def embed_text(text, cfg, method=None, language="en"):
    """Ask the server to embed text. Returns a list[float] vector."""
    payload = {"text": text, "language": language}
    if method:
        payload["embedding_method"] = method
    resp = _post_json(_server_url(cfg) + "/embed", payload,
                      _server_token(cfg), _server_timeout(cfg))
    return resp["vector"]


# ===========================================================================
# lookup_in_lexicon -- the four-step cascade, server-backed
# ===========================================================================

def _new_result_dict(target, context, pos_hint):
    return {
        "target": target,
        "context": context,
        "pos_hint": pos_hint,
        "decision_level": 0,
        "decision_reason": "not_started",
        "canonical_id": None,
        "confidence": 0.0,
        "matched_canonical_id": None,
        "rewritten_to_standard": False,
        "specificity": None,
        "maturity_tier": None,
        "policy_applied": None,
        "minted": False,
        "candidates": [],
    }


def _candidate_from_server(r):
    return {
        "canonical_id": r.get("canonical_id", ""),
        "lemma":        r.get("lemma", ""),
        "pos":          r.get("pos_simple", ""),
        "microgloss":   r.get("microgloss", ""),
        "cosine":       float(r.get("raw_cosine", r.get("score", 0.0))),
    }


def _mint(target, pos_hint, result, enable_mint):
    if not enable_mint:
        result["decision_level"] = 4
        result["decision_reason"] = "mint_disabled"
        return result
    lemma_norm = re.sub(r"\s+", "_", target.strip().lower())
    pos = (pos_hint or "noun").lower()
    result["decision_level"] = 4
    result["decision_reason"] = "minted"
    result["canonical_id"] = f"doc.{lemma_norm}.unmapped.{pos}.docloc"
    result["confidence"] = 0.0
    result["minted"] = True
    return result


def lookup_in_lexicon(
    target,
    context="",
    pos_hint=None,
    cfg=None,
    enable_mint=True,
    llm_cfg=None,
):
    """Four-step cascade lookup against the search server.

    Steps:
      1. /lookup/lemma   (exact lemma match; unique -> done)
      2. /search         (lemma-restricted cosine)
      3. LLM rerank      (only if llm_cfg points to a configured wrapper)
      4. mint            (doc-local canonical_id)

    Arguments
    ---------
    target : str            the lemma to look up
    context : str           surrounding text used at step 2
    pos_hint : str | None   'noun' | 'verb' | 'name' | ...
    cfg : dict              from load_config()
    enable_mint : bool      if False, step 4 returns canonical_id=None
    llm_cfg : dict | None   from call_llm.load_llm_config(); enables step 3

    Returns a dict with the LOOKUP RESULT DICT shape documented at the
    top of this module.
    """
    if cfg is None:
        cfg = load_config()

    server_url = _server_url(cfg)
    token = _server_token(cfg)
    timeout = _server_timeout(cfg)

    lookup_cfg = cfg.get("lookup", {})
    top_k = int(lookup_cfg.get("top_k", 10))
    auto_accept = float(lookup_cfg.get("auto_accept_cosine", 0.80))
    escalate_below = float(lookup_cfg.get("escalate_below_cosine", 0.65))
    policy_name = lookup_cfg.get("policy") or None
    embedding_method = cfg.get("_default_embedding_method", "bge-large-en-v1")

    result = _new_result_dict(target, context, pos_hint)

    # -- Step 1: exact lemma --
    try:
        lemma_resp = _post_json(
            server_url + "/lookup/lemma",
            {"lemma": target, "pos": pos_hint, "policy": policy_name},
            token, timeout,
        )
    except RuntimeError as e:
        result["decision_reason"] = f"server_unreachable: {e}"
        return _mint(target, pos_hint, result, enable_mint)

    hits = lemma_resp.get("results", [])
    if len(hits) == 1:
        top = hits[0]
        result["decision_level"] = 1
        result["decision_reason"] = "exact_lemma_unique"
        result["canonical_id"] = top.get("canonical_id")
        result["confidence"] = 1.0
        result["matched_canonical_id"] = top.get("matched_canonical_id")
        result["rewritten_to_standard"] = bool(top.get("rewritten_to_standard"))
        result["specificity"] = top.get("specificity")
        result["maturity_tier"] = top.get("maturity_tier")
        result["policy_applied"] = lemma_resp.get("policy_applied")
        result["candidates"] = [_candidate_from_server(top)]
        return result

    # -- Step 2: cosine search --
    query_text = context if context else target
    try:
        search_resp = _post_json(
            server_url + "/search",
            {
                "text": query_text,
                "k": top_k,
                "lemma_restrict": target,
                "language": "en",
                "policy": policy_name,
                "embedding_method": embedding_method,
            },
            token, timeout,
        )
    except RuntimeError as e:
        if hits:
            top = hits[0]
            result["decision_level"] = 2
            result["decision_reason"] = (
                f"cosine_unreachable_first_lemma: {e}"
            )
            result["canonical_id"] = top.get("canonical_id")
            result["confidence"] = 0.5
            result["candidates"] = [_candidate_from_server(h) for h in hits]
            return result
        return _mint(target, pos_hint, result, enable_mint)

    sresults = search_resp.get("results", [])
    result["candidates"] = [_candidate_from_server(r) for r in sresults]

    if not sresults:
        return _mint(target, pos_hint, result, enable_mint)

    top = sresults[0]
    top_score = float(top.get("score", 0.0))

    if top_score >= auto_accept:
        result["decision_level"] = 2
        result["decision_reason"] = (
            f"cosine_auto_accept score={top_score:.3f}"
        )
        result["canonical_id"] = top.get("canonical_id")
        result["confidence"] = top_score
        result["matched_canonical_id"] = top.get("matched_canonical_id")
        result["rewritten_to_standard"] = bool(top.get("rewritten_to_standard"))
        result["specificity"] = top.get("specificity")
        result["maturity_tier"] = top.get("maturity_tier")
        result["policy_applied"] = search_resp.get("policy_applied")
        return result

    # -- Step 3: LLM rerank --
    if (llm_cfg is not None
            and top_score >= escalate_below
            and len(sresults) >= 2):
        picked = _llm_rerank(target, context, sresults[:5], llm_cfg)
        if picked is not None:
            result["decision_level"] = 3
            result["decision_reason"] = "llm_rerank"
            result["canonical_id"] = picked.get("canonical_id")
            result["confidence"] = float(picked.get("score", top_score))
            result["matched_canonical_id"] = picked.get("matched_canonical_id")
            result["rewritten_to_standard"] = bool(
                picked.get("rewritten_to_standard")
            )
            result["specificity"] = picked.get("specificity")
            result["maturity_tier"] = picked.get("maturity_tier")
            result["policy_applied"] = search_resp.get("policy_applied")
            return result

    if top_score >= escalate_below:
        result["decision_level"] = 2
        result["decision_reason"] = (
            f"cosine_passable score={top_score:.3f}"
        )
        result["canonical_id"] = top.get("canonical_id")
        result["confidence"] = top_score
        result["matched_canonical_id"] = top.get("matched_canonical_id")
        result["rewritten_to_standard"] = bool(top.get("rewritten_to_standard"))
        result["specificity"] = top.get("specificity")
        result["maturity_tier"] = top.get("maturity_tier")
        result["policy_applied"] = search_resp.get("policy_applied")
        return result

    # -- Step 4: mint --
    return _mint(target, pos_hint, result, enable_mint)


def _llm_rerank(target, context, candidates, llm_cfg):
    """Ask the LLM to pick the best candidate. Returns the picked dict
    (from the candidates list) or None on failure.

    Uses MDKV output. The model returns:

        :::pick
        index: <1-based>
        confidence: <0.0-1.0>
        :::
    """
    # Import here so this module does not pay the cost when LLM is unused.
    try:
        from call_llm import call_llm, is_wrapper_configured
    except ImportError:
        return None

    if not is_wrapper_configured(llm_cfg):
        return None

    lines = []
    for i, c in enumerate(candidates, 1):
        lines.append(
            f"  {i}. canonical_id={c.get('canonical_id','?')} "
            f"lemma={c.get('lemma','?')} pos={c.get('pos_simple','?')} "
            f"micro={c.get('microgloss','?')} "
            f"score={float(c.get('score', 0)):.3f}"
        )
    user_prompt = (
        f"TARGET: {target}\n"
        f"CONTEXT: {context}\n\n"
        "CANDIDATES (pick the one whose sense best fits the context):\n"
        + "\n".join(lines)
        + "\n\nRespond with one MDKV block of kind 'pick':\n"
          ":::pick\nindex: <1-based index>\nconfidence: <0.0-1.0>\n:::\n"
    )
    system_text = (
        "You are a lexicographer. Pick the candidate whose canonical_id "
        "best matches the target word's sense in the given context. "
        "Respond with a single MDKV block of kind 'pick'. No prose."
    )

    try:
        raw = call_llm(
            prompt_text=user_prompt,
            llm_cfg=llm_cfg,
            system_text=system_text,
        )
    except RuntimeError:
        return None

    blocks = [b for b in parse_mdkv(raw) if b.get("_kind") == "pick"]
    if not blocks:
        return None
    try:
        idx = int(str(blocks[0].get("index", "0")).strip())
    except ValueError:
        return None
    if 1 <= idx <= len(candidates):
        return candidates[idx - 1]
    return None


# ===========================================================================
# Quick lookup (convenience for sgf_cli)
# ===========================================================================

def quick_lookup(target, context="", pos_hint=None, cfg=None):
    """One-shot lookup. cfg auto-loaded if None. Returns a result dict."""
    if cfg is None:
        cfg = load_config()
    return lookup_in_lexicon(target, context, pos_hint, cfg)
