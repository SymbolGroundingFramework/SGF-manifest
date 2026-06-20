#!/usr/bin/env python3
"""
glean_search.py  (Stage 0 of the GLEAN family)

Universal CLI client for the GLEAN search server. Every tool that
queries the SGF lexicon should go through this CLI (or the
underlying HTTP API directly). This is the one entry point.

USAGE
-----
    # Search by text (server embeds the query)
    glean-search "the boy walked to the river" --k 5

    # Look up by lemma
    glean-search --lemma kiddo
    glean-search --lemma leukemia

    # Look up by canonical_id
    glean-search --cid en.father.male_parent.noun.core

    # Apply a different policy
    glean-search "kiddo" --policy preserve_register
    glean-search "kiddo" --no-rewrite

    # Server health and tier distribution
    glean-search --health

    # Listed available policies
    glean-search --policies

ENVIRONMENT
-----------
GLEAN_SEARCH_SERVER  default: http://127.0.0.1:8400
GLEAN_API_TOKEN      required when server is on a non-loopback address
                     (or pass --token)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


DEFAULT_SERVER = os.environ.get("GLEAN_SEARCH_SERVER", "http://127.0.0.1:8400")
DEFAULT_AUTH_FILE = Path(os.environ.get("GLEAN_HOME", str(Path.home() / ".glean"))) / "auth.toml"


def get_token(arg_token: Optional[str]) -> Optional[str]:
    if arg_token:
        return arg_token
    env = os.environ.get("GLEAN_API_TOKEN")
    if env:
        return env
    if DEFAULT_AUTH_FILE.exists() and tomllib is not None:
        try:
            with open(DEFAULT_AUTH_FILE, "rb") as f:
                cfg = tomllib.load(f)
            return cfg.get("api_token")
        except OSError:
            pass
    return None


def request(
    server: str, method: str, path: str,
    payload: Optional[dict] = None, token: Optional[str] = None,
    timeout: float = 30.0,
) -> Any:
    url = server.rstrip("/") + path
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-API-Key"] = token
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {body}", file=sys.stderr)
        sys.exit(2)
    except urllib.error.URLError as e:
        print(f"Cannot reach server at {server}: {e}", file=sys.stderr)
        print(
            "  Start the server first:\n"
            f"  python glean_search_server.py --lexicon <path>",
            file=sys.stderr,
        )
        sys.exit(3)


def format_results(resp: Dict[str, Any], pretty: bool):
    if pretty:
        results = resp.get("results", [])
        print(f"  policy_applied: {resp.get('policy_applied', '?')}")
        emb = resp.get("embedder_used") or resp.get("query_embedding_method") or "?"
        print(f"  embedder:       {emb}")
        if resp.get("reranker_applied"):
            print(f"  reranker:       {resp.get('reranker_applied')}")
        if resp.get("bm25_applied"):
            print(f"  bm25:           applied (lexical rescore)")
        if resp.get("llm_tiebreak_applied"):
            print(f"  llm tiebreak:   applied")
        print(f"  results:        {len(results)}")
        print()
        # Indicate the final ranking authority for each result. When the
        # LLM tiebreaker fired, the top result carries `llm_tiebreak_picked`
        # and reflects the LLM's choice -- which may disagree with the
        # reranker. We display results in their FINAL order.
        for i, r in enumerate(results, 1):
            tier = r.get("maturity_tier") or "?"
            spec = r.get("specificity") or "general"
            reg = r.get("register") or "neutral"
            rewrote = " (snapped)" if r.get("rewritten_to_standard") else ""
            tag = ""
            if r.get("llm_tiebreak_picked"):
                tag = " (LLM PICK)"
            elif i == 1 and resp.get("bm25_applied"):
                tag = " (cascade pick: rerank+BM25)"
            elif i == 1 and "rerank_score" in r and resp.get("reranker_applied"):
                tag = " (reranker pick)"
            elif "rerank_score" in r:
                tag = " (reranked)"
            print(f"  {i:2}. {r['canonical_id']}{rewrote}{tag}")
            line = f"      cosine={r.get('raw_cosine', r['score']):+.4f}"
            if "rerank_score" in r:
                line += f"  rerank={r['rerank_score']:+.4f}"
            if "bm25_score" in r:
                line += f"  bm25={r['bm25_score']:+.4f}"
            line += f"  penalty={r.get('penalty', 0):.4f}"
            print(line)
            print(f"      tier={tier}  reg={reg}  spec={spec}")
    else:
        print(json.dumps(resp, indent=2))


def apply_client_postprocess(query_text, resp, rr_cfg, tb_cfg, llm_wrapper_override):
    """Apply client-side reranker + LLM tiebreaker to a server response.

    Idempotent: if the server already applied reranker / tiebreaker and
    the margin is now wide, both layers will no-op here.
    """
    if not query_text:
        return resp  # lemma-only and cid-only lookups have no text to rerank against
    results = resp.get("results") or []
    if not results:
        return resp

    # --- Client-side reranker ---
    if rr_cfg.get("enabled"):
        top_n = int(rr_cfg.get("top_n", 20))
        always = bool(rr_cfg.get("rerank_always", False))
        margin_th = float(rr_cfg.get("rerank_margin_threshold", 0.05))
        margin = _top2_margin(results)
        if always or (margin is not None and margin < margin_th):
            import reranker as rk
            rescored = rk.rerank(
                query_text, list(results[:top_n]),
                rr_cfg.get("models", ["bge-reranker-v2-m3"]),
            )
            # Replace the top-N with rescored; append the rest after
            tail = results[top_n:]
            resp["results"] = rescored + tail
            resp["reranker_applied"] = (
                rescored[0].get("rerank_model") if rescored else None
            )
            results = resp["results"]

    # --- Client-side LLM tiebreaker ---
    if tb_cfg.get("client_enabled"):
        import llm_tiebreaker as tb
        margin_th = float(tb_cfg.get("margin_threshold", 0.03))
        if tb.needs_tiebreak(results, margin_th):
            wrapper = llm_wrapper_override or tb_cfg.get("llm_wrapper", "llm_wrapper.py")
            top_n_llm = int(tb_cfg.get("top_n_to_llm", 5))
            tiebroken = tb.tiebreak(
                query_text, list(results[:top_n_llm]),
                wrapper,
                tier=tb_cfg.get("tier", "flash"),
                temp=float(tb_cfg.get("temp", 0.0)),
            )
            resp["results"] = tiebroken + results[top_n_llm:]
            resp["llm_tiebreak_applied"] = True

    return resp


def _top2_margin(results):
    if not results or len(results) < 2:
        return None
    s1 = _score_of(results[0])
    s2 = _score_of(results[1])
    if s1 is None or s2 is None:
        return None
    return s1 - s2


def _score_of(r):
    if "rerank_score" in r:
        return float(r["rerank_score"])
    if "score" in r:
        return float(r["score"])
    if "raw_cosine" in r:
        return float(r["raw_cosine"])
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("text", nargs="?", default=None,
                   help="Query text (will be embedded server-side)")
    p.add_argument("--lemma", help="Look up a lemma directly (no embedding)")
    p.add_argument("--pos", help="POS hint when using --lemma")
    p.add_argument("--cid", help="Look up by canonical_id")

    p.add_argument("--k", type=int, default=10)
    p.add_argument("--policy", help="Named policy override")
    p.add_argument("--no-rewrite", action="store_true",
                   help="Disable snap-to-standard for this query")
    p.add_argument("--audience-tier", help="Override audience_tier")
    p.add_argument("--include-temporal", default=None,
                   help="Comma-separated temporal_status to re-include (e.g. obsolete)")
    p.add_argument("--include-social", default=None,
                   help="Comma-separated social_status to re-include (e.g. offensive)")
    p.add_argument("--min-tier", default=None,
                   help="Override min_tier_returned")
    p.add_argument("--lemma-restrict", default=None,
                   help="Restrict embedding-space search to a lemma")
    p.add_argument("--auto-resolve-forms", action="store_true",
                   help="Expand --lemma-restrict via the lemma_form "
                        "table (e.g. 'burned' resolves to 'burn'). "
                        "Requires that build_lemma_forms.py has been run.")
    p.add_argument("--pos-restrict", default=None,
                   choices=["n", "v", "adj", "adv", "name", "other"],
                   help="Restrict to one pos_simple bucket.")
    p.add_argument("--language", default="en")
    p.add_argument("--embedder", default=None,
                   help="Embedding method (default: server picks best)")

    p.add_argument("--health", action="store_true")
    p.add_argument("--policies", action="store_true")

    p.add_argument("--server", default=DEFAULT_SERVER)
    p.add_argument("--token", default=None)
    p.add_argument("--json", action="store_true",
                   help="Emit raw JSON instead of pretty output")
    p.add_argument("--llm-wrapper", default=None,
                   help="Override llm_wrapper.py path (for LLM tiebreak)")
    p.add_argument("--rerank", dest="rerank", action="store_true", default=None,
                   help="Force client-side reranker on (overrides config)")
    p.add_argument("--no-rerank", dest="rerank", action="store_false",
                   help="Force client-side reranker off (overrides config)")
    p.add_argument("--llm-tiebreak", dest="llm_tiebreak", action="store_true",
                   default=None,
                   help="Force client-side LLM tiebreak on (overrides config)")
    p.add_argument("--no-llm-tiebreak", dest="llm_tiebreak",
                   action="store_false",
                   help="Force client-side LLM tiebreak off (overrides config)")
    p.add_argument("--config", default=None,
                   help="Override path to glean_search_policy.toml")
    p.add_argument("--config-dir", default=None,
                   help="Directory holding glean_search_policy.toml "
                        "(overrides ~/.glean/ lookup)")
    args = p.parse_args()

    # Load client-side reranker/tiebreak config (auto-creates on first use)
    import glean_search_config as _gcfg
    _cfg = _gcfg.load_config(args.config, config_dir=args.config_dir)
    rr_cfg = _gcfg.get_reranker_config(_cfg, side="client")
    tb_cfg = _gcfg.get_tiebreak_config(_cfg, side="client")
    if args.rerank is not None:
        rr_cfg = {**rr_cfg, "enabled": args.rerank}
    if args.llm_tiebreak is not None:
        tb_cfg = {**tb_cfg, "client_enabled": args.llm_tiebreak, "enabled": args.llm_tiebreak}

    token = get_token(args.token)
    pretty = not args.json

    # Diagnostic endpoints
    if args.health:
        resp = request(args.server, "GET", "/health", token=token)
        print(json.dumps(resp, indent=2))
        return 0
    if args.policies:
        resp = request(args.server, "GET", "/policies", token=token)
        print(json.dumps(resp, indent=2))
        return 0

    # Build per-request overrides
    overrides: Dict[str, Any] = {}
    if args.no_rewrite:
        overrides["rewrite_to_standard_form"] = False
    if args.audience_tier:
        overrides["audience_tier"] = args.audience_tier
    if args.include_temporal:
        # Default exclusions minus the re-included set
        # Caller should send a fresh exclusion list
        included = set(t.strip() for t in args.include_temporal.split(","))
        # Start from a conservative default and remove the included ones
        default_excl = {"obsolete"}
        overrides["exclude_temporal_status"] = sorted(default_excl - included)
    if args.include_social:
        included = set(t.strip() for t in args.include_social.split(","))
        default_excl = {"slur", "offensive"}
        overrides["exclude_social_status"] = sorted(default_excl - included)
    if args.min_tier:
        overrides["min_tier_returned"] = args.min_tier

    # Dispatch
    if args.cid:
        resp = request(args.server, "POST", "/lookup/canonical",
                       payload={"canonical_id": args.cid}, token=token)
        print(json.dumps(resp, indent=2))
        return 0

    if args.lemma:
        payload = {"lemma": args.lemma}
        if args.pos:
            payload["pos"] = args.pos
        if args.policy:
            payload["policy"] = args.policy
        if overrides:
            payload["policy_overrides"] = overrides
        resp = request(args.server, "POST", "/lookup/lemma",
                       payload=payload, token=token)
        format_results(resp, pretty)
        return 0

    if args.text:
        payload = {
            "text": args.text,
            "k": args.k,
            "language": args.language,
        }
        if args.policy:
            payload["policy"] = args.policy
        if overrides:
            payload["policy_overrides"] = overrides
        if args.lemma_restrict:
            payload["lemma_restrict"] = args.lemma_restrict
        if args.auto_resolve_forms:
            payload["auto_resolve_forms"] = True
        if args.pos_restrict:
            payload["pos_restrict"] = args.pos_restrict
        if args.embedder:
            payload["embedding_method"] = args.embedder
        resp = request(args.server, "POST", "/search", payload=payload, token=token)
        # Client-side reranker + LLM tiebreaker (idempotent if server
        # already applied them).
        resp = apply_client_postprocess(
            args.text, resp, rr_cfg, tb_cfg, args.llm_wrapper,
        )
        format_results(resp, pretty)
        return 0

    # Nothing to do
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
