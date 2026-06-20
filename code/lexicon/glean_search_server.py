#!/usr/bin/env python3
"""
glean_search_server.py  (Stage 0 of the GLEAN family)

A long-running daemon that loads the SGF lexicon's embedder and
embedding matrices ONCE, then serves HTTP queries from any client
(the `glean-search` CLI, the GLEAN compiler, the lexicon's
quality_audit, custom scripts, etc.).

WHY THIS EXISTS
---------------
Without this daemon, every tool that wants to query the lexicon pays a
~120-second cold-start cost (model load + matrix load). With it, that
cost is paid once at boot. Every subsequent query returns in 10-50ms.

The server is also the place where policy lives. A query for "kiddo"
returns "children" because the server's snap_to_standard policy
rewrites results to the content_identical_group's standard form. A
query for "leukemia" stays "leukemia" because specialist terms are
preserved by default.

ARCHITECTURAL COMMITMENTS
-------------------------
1. Read-only against the lexicon. The server never writes to the DB.
2. Multi-embedder. Loads whatever embedders the DB has. Routes
   queries to bge-large for English by default with bge-small as
   fallback when needed.
3. Policy-driven. Reads retrieval_policy.toml (from the bundle dir or
   ~/.glean/). Legacy name policy.toml is also accepted.
   No policy decisions are hard-coded.
4. Auth-gated. Loopback binding does not require auth; non-loopback
   bind requires a 24-character base32 shared-secret token via
   X-API-Key header. Token is auto-generated on first non-loopback
   start and written to ~/.glean/auth.toml.
5. Tier-aware. By default refuses to return senses below the
   'improved' maturity tier. Caller opts in via min_tier_returned.
6. Specialist-preserving. The snap_to_standard policy honors the
   leukemia rule: specificity='specialist' and 'technical' senses
   are NEVER rewritten to a general hypernym, even when they
   participate in a content_identical_group.
7. Honest about what it has. /health reports which embedders are
   loaded, how many senses each covers, and the tier distribution.

USAGE
-----
    # Default: bind localhost:8400, no auth required
    python glean_search_server.py --lexicon sgf_lexicon.db

    # LAN exposure: requires the auto-generated auth token
    python glean_search_server.py --lexicon sgf_lexicon.db --host 0.0.0.0

    # Custom policy file
    python glean_search_server.py --lexicon sgf_lexicon.db \\
        --policy /etc/glean/retrieval_policy.toml
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
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib
    except ImportError:
        print(
            "ERROR: tomllib (3.11+) or tomli is required.\n"
            "Install: pip install tomli",
            file=sys.stderr,
        )
        sys.exit(2)

try:
    from fastapi import FastAPI, HTTPException, Header, Request
    from pydantic import BaseModel, Field
    import uvicorn
except ImportError:
    print(
        "ERROR: fastapi + uvicorn + pydantic are required.\n"
        "Install: pip install fastapi uvicorn pydantic",
        file=sys.stderr,
    )
    sys.exit(2)


# ===========================================================================
# Constants and default policy
# ===========================================================================

GLEAN_HOME = Path(os.environ.get("GLEAN_HOME", str(Path.home() / ".glean")))
BUNDLE_DIR = Path(__file__).resolve().parent

# Canonical filename first, then legacy names (back-compat).
# Users editing config files should see the self-evident name.
# search_config.toml is the merged one-file format; the others are
# accepted for users who haven't migrated.
POLICY_FILENAMES = ("search_config.toml", "retrieval_policy.toml", "policy.toml")
DEFAULT_POLICY_PATH = GLEAN_HOME / POLICY_FILENAMES[0]
DEFAULT_AUTH_PATH = GLEAN_HOME / "auth.toml"


def _first_existing(directory: Path, filenames):
    for fn in filenames:
        p = directory / fn
        if p.exists():
            return p
    return None


def resolve_policy_path(explicit_path=None, config_dir=None):
    """Find the retrieval policy TOML in priority order:

    1. explicit --policy PATH (caller knows where they want it)
    2. <config_dir>/retrieval_policy.toml (or legacy policy.toml)
    3. <bundle>/retrieval_policy.toml (or legacy policy.toml)
    4. ~/.glean/retrieval_policy.toml (auto-created on first boot)
    """
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
    # Also check legacy ~/.glean/policy.toml for back-compat
    legacy_home = GLEAN_HOME / "policy.toml"
    if legacy_home.exists() and not DEFAULT_POLICY_PATH.exists():
        return legacy_home
    return DEFAULT_POLICY_PATH

TIER_ORDER = [
    "raw", "provisional", "embedded_v1", "improved",
    "embedded_v2", "clustered", "related",
]

# Default policy. Used when ~/.glean/policy.toml doesn't exist or is
# missing keys. Conservative: snap to standard, drop slurs / obsolete,
# soft-demote dated and slang, preserve specialist terms.
DEFAULT_POLICY = {
    "default_policy": "snap_to_standard",
    "policies": {
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
        "snap_to_neutral": {
            "rewrite_to_standard_form": True,
            "preserve_specialist_terms": True,
            "audience_tier": "general",
            "snap_social_status": ["slur", "offensive", "vulgar"],
            "snap_temporal_status": ["obsolete"],
            "on_snap_failure": "drop",
            "exclude_social_status": [],
            "exclude_temporal_status": [],
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
    },
}


# ===========================================================================
# Logging
# ===========================================================================

logger = logging.getLogger("glean_search")


def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )


# ===========================================================================
# Policy
# ===========================================================================

@dataclass
class Policy:
    name: str
    rewrite_to_standard_form: bool
    preserve_specialist_terms: bool
    audience_tier: str
    exclude_social_status: List[str]
    exclude_temporal_status: List[str]
    # snap_to_neutral fields. When non-empty, marked senses are
    # SUBSTITUTED with their content-identical neutral form rather
    # than dropped. Hard-exclude lists above still apply on top.
    snap_social_status: List[str]
    snap_temporal_status: List[str]
    on_snap_failure: str  # "drop" | "passthrough" | "sentinel"
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
            min_tier_returned=str(d.get("min_tier_returned", "improved")),
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


def write_default_policy_file(path: Path):
    """Write a heavily-commented default policy.toml to path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = '''# ============================================================
# GLEAN search policy
# ============================================================
# This file controls how the search server ranks and filters
# results before returning them to clients.
#
# Out-of-the-box defaults: snap to standard contemporary language,
# exclude slurs and offensive terms, soft-demote dated vocabulary,
# preserve specialist terms (leukemia stays leukemia, not cancer).
#
# CONTENT-IDENTICAL vs RELATED-BUT-DISTINCT:
#
# snap_to_standard rewrites slang/dated/marked terms to their
# standard form, but ONLY within content-identical groups.
#
#   "kiddo" -> "children"         (same content, different register)
#   "daddy-o" -> "father"          (same content, different register)
#   "pops" -> "father"             (same content, different register)
#
# Specialist terms are NOT snapped to their general-audience
# hypernyms (because they are not in the same content-identical
# group at the general audience tier):
#
#   "leukemia" stays "leukemia"    (not snapped to "cancer")
#   "negligence" stays "negligence" (not snapped to "carelessness")
#
# To override per-request, the client sends a `policy_overrides`
# field in the JSON payload that selectively overrides any of these.
# Or pass --policy <name> to switch to a different named policy.
# ============================================================

default_policy = "snap_to_standard"


# -------- embedder cascade ---------------------------------
# Ranked preference list of embedders to try, by language.
# At boot, the server intersects each list with the embedders
# actually present in the lexicon AND filters out any embedder
# whose coverage (n_rows_with_embedding / n_total_senses) is
# below `embedder_min_coverage`. This prevents the cascade from
# silently picking a half-built embedder whose results would be
# missing most of the lexicon.
#
# Quality order is preserved by the configured list -- if both
# bge-large and bge-small reach the coverage threshold, bge-large
# wins because it appears first.
#
# If a client passes --embedder X explicitly, the cascade and
# coverage gate are BYPASSED. Lexicon authors testing a partial
# embedder use this.
#
# Adding new embedders later (medium, m3, multilingual-e5,
# whatever) does not require code changes -- just add them to
# the cascade and they will be used preferentially the moment
# they reach the coverage threshold.
# -----------------------------------------------------------
embedder_min_coverage = 0.95

[embedder_cascade]
default = ["bge-large-en-v1", "bge-medium-en-v1", "bge-small-en-v1"]
en = ["bge-large-en-v1", "bge-medium-en-v1", "bge-small-en-v1"]
multilingual = ["bge-m3-v1", "bge-large-en-v1", "bge-small-en-v1"]


# -------- snap_to_standard (the recommended default) --------
[policies.snap_to_standard]
# Rewrite results to their content_identical_group's standard form
# when one exists at the requested audience_tier.
rewrite_to_standard_form = true

# Never rewrite specialist (medicine/law/science/...) or technical
# (subspecialty) terms even if a group exists. The leukemia rule.
preserve_specialist_terms = true

# Audience tier for content_identical lookups. "general" matches
# most users. "expert_medical", "expert_legal", etc. opt into
# specialty content-identical groups.
audience_tier = "general"

# Hard exclusions: results matching ANY of these are dropped
exclude_social_status = ["slur", "offensive"]
exclude_temporal_status = ["obsolete"]

# Don't return senses whose lexicon maturity is below this tier.
# Tiers in order: raw, provisional, embedded_v1, improved,
# embedded_v2, clustered, related.
min_tier_returned = "improved"

# Soft demotions: results matching these get a cosine penalty
# applied to their score before re-ranking. 0.0 = no penalty,
# 0.10 = treat as 0.10 less similar than the raw cosine says.
[policies.snap_to_standard.demote_register]
slang = 0.08
vulgar = 0.15
poetic = 0.03

[policies.snap_to_standard.demote_temporal]
dated = 0.05
archaic = 0.10

[policies.snap_to_standard.demote_social]
flagged = 0.10


# -------- snap_to_neutral (substitution-based, general audience) --------
# Marked senses are SUBSTITUTED with their content-identical
# neutral form rather than dropped. A query that hits a slur
# returns its neutral equivalent; if no neutral form exists,
# on_snap_failure decides what to do (drop / passthrough /
# sentinel). Use this when you want graceful answers instead of
# refusals for general-audience queries.
[policies.snap_to_neutral]
rewrite_to_standard_form = true
preserve_specialist_terms = true
audience_tier = "general"
snap_social_status = ["slur", "offensive", "vulgar"]
snap_temporal_status = ["obsolete"]
on_snap_failure = "drop"
exclude_social_status = []
exclude_temporal_status = []
min_tier_returned = "improved"

[policies.snap_to_neutral.demote_register]
slang = 0.08
vulgar = 0.15
poetic = 0.03

[policies.snap_to_neutral.demote_temporal]
dated = 0.05
archaic = 0.10

[policies.snap_to_neutral.demote_social]
flagged = 0.10


# -------- preserve_register (for narrators with distinct voice) --------
[policies.preserve_register]
# Match the source's metadata profile. GLEAN uses this when
# compiling a slang-heavy first-person narrator -- "kiddo" stays
# "kiddo", not "children".
rewrite_to_standard_form = false
preserve_specialist_terms = true
audience_tier = "general"
exclude_social_status = ["slur"]
exclude_temporal_status = []
min_tier_returned = "improved"

[policies.preserve_register.demote_register]
[policies.preserve_register.demote_temporal]
[policies.preserve_register.demote_social]


# -------- research_unfiltered (for lexicon authoring) --------
# All senses, including raw and offensive. Lexicon editors use this
# to inspect the full record.
[policies.research_unfiltered]
rewrite_to_standard_form = false
preserve_specialist_terms = true
audience_tier = "general"
exclude_social_status = []
exclude_temporal_status = []
min_tier_returned = "raw"

[policies.research_unfiltered.demote_register]
[policies.research_unfiltered.demote_temporal]
[policies.research_unfiltered.demote_social]
'''
    path.write_text(content, encoding="utf-8")


BUILT_IN_CASCADE = {
    "default":      ["bge-large-en-v1", "bge-medium-en-v1", "bge-small-en-v1"],
    "en":           ["bge-large-en-v1", "bge-medium-en-v1", "bge-small-en-v1"],
    "multilingual": ["bge-m3-v1", "bge-large-en-v1", "bge-small-en-v1"],
}


def load_policies(path: Path):
    """Load named policies + embedder cascade from a TOML file. Falls back
    to defaults when path doesn't exist or is missing keys.

    Returns (policies_dict, embedder_cascade_dict, min_coverage).
    """
    if not path.exists():
        logger.warning(f"Policy file not found at {path}; writing defaults.")
        write_default_policy_file(path)

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    # New shape puts these keys under [retrieval]. Legacy shape has them
    # at the top level. Pick whichever is present.
    cfg = raw.get("retrieval", raw)

    default_name = cfg.get("default_policy", "snap_to_standard")
    policies_data = cfg.get("policies", {})
    if not policies_data:
        policies_data = DEFAULT_POLICY["policies"]

    out: Dict[str, Policy] = {}
    for name, pd in policies_data.items():
        out[name] = Policy.from_dict(name, pd)

    out["__default__"] = out[default_name]

    cascade_cfg = cfg.get("embedder_cascade", {})
    cascade = {**BUILT_IN_CASCADE, **{k: list(v) for k, v in cascade_cfg.items()}}

    min_coverage = float(cfg.get("embedder_min_coverage", 0.95))

    return out, cascade, min_coverage


# ===========================================================================
# Auth
# ===========================================================================

def generate_token() -> str:
    """24-character base32 token, ~120 bits entropy."""
    raw = secrets.token_bytes(15)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def load_or_create_auth(path: Path) -> str:
    if path.exists():
        with open(path, "rb") as f:
            cfg = tomllib.load(f)
        return cfg.get("api_token", "")
    token = generate_token()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'# Auto-generated GLEAN search-server auth token.\n'
        f'# Required only when server binds to a non-loopback address.\n'
        f'# Pass to clients via the X-API-Key HTTP header,\n'
        f'# or set GLEAN_API_TOKEN in the client environment.\n'
        f'api_token = "{token}"\n',
        encoding="utf-8",
    )
    logger.warning(f"Generated new auth token at {path}")
    return token


# ===========================================================================
# Lexicon backend
# ===========================================================================

@dataclass
class EmbedderState:
    method: str
    dim: int
    wsids: List[int]
    vectors: List[List[float]]      # parallel to wsids
    wsid_to_idx: Dict[int, int] = field(default_factory=dict)


@dataclass
class SenseRecord:
    wsid: int
    lemma: str
    pos_simple: str
    microgloss: str
    canonical_id: str
    register: Optional[str]
    temporal_status: Optional[str]
    social_status: Optional[str]
    specificity: Optional[str]
    maturity_tier: Optional[str]
    namespace: Optional[str]


def vec_from_blob(blob) -> List[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


def dot(a, b):
    s = 0.0
    for x, y in zip(a, b):
        s += x * y
    return s


class LexiconBackend:
    """Loads sense metadata and embeddings into RAM. Read-only.

    Thread-safe for reads after load_all(). Reads happen from many
    request handlers concurrently; no locking needed because nothing
    mutates the loaded state during normal operation.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.senses: Dict[int, SenseRecord] = {}
        self.embedders: Dict[str, EmbedderState] = {}
        self.content_groups: Dict[int, Dict[str, Any]] = {}
        # wsid -> {audience_tier: group_id}
        self.wsid_to_groups: Dict[int, Dict[str, int]] = {}
        self.tier_counts: Dict[str, int] = {t: 0 for t in TIER_ORDER}
        self.namespaces: set = set()
        self.lemma_index: Dict[str, List[int]] = {}
        self.has_v3_1: bool = False

    def load_all(self):
        t0 = time.time()
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA query_only = 1")
        cur = conn.cursor()

        # Detect v3.1 columns
        cur.execute("PRAGMA table_info(sgf_lexicon)")
        sgf_cols = {row[1] for row in cur.fetchall()}
        self.has_v3_1 = "maturity_tier" in sgf_cols and "specificity" in sgf_cols
        ns_col = "namespace" if "namespace" in sgf_cols else None
        spec_col = "specificity" if "specificity" in sgf_cols else None
        tier_col = "maturity_tier" if "maturity_tier" in sgf_cols else None

        # Load senses
        select_cols = [
            "wiktionary_source_id", "lemma", "pos_simple",
            "microgloss", "canonical_id",
            "register", "temporal_status", "social_status",
        ]
        if spec_col:
            select_cols.append(spec_col)
        if tier_col:
            select_cols.append(tier_col)
        if ns_col:
            select_cols.append(ns_col)
        cur.execute(
            f"SELECT {', '.join(select_cols)} FROM sgf_lexicon "
            f"WHERE canonical_id IS NOT NULL"
        )
        rows = cur.fetchall()
        for r in rows:
            idx = 0
            wsid = r[idx]; idx += 1
            lemma = r[idx]; idx += 1
            pos_simple = r[idx]; idx += 1
            microgloss = r[idx]; idx += 1
            canonical_id = r[idx]; idx += 1
            register = r[idx]; idx += 1
            temporal_status = r[idx]; idx += 1
            social_status = r[idx]; idx += 1
            specificity = r[idx] if spec_col else "general"; idx += 1 if spec_col else 0
            maturity_tier = r[idx] if tier_col else "improved"; idx += 1 if tier_col else 0
            namespace = r[idx] if ns_col else "core"
            self.senses[wsid] = SenseRecord(
                wsid=wsid, lemma=lemma, pos_simple=pos_simple,
                microgloss=microgloss, canonical_id=canonical_id,
                register=register, temporal_status=temporal_status,
                social_status=social_status, specificity=specificity,
                maturity_tier=maturity_tier, namespace=namespace,
            )
            self.tier_counts[maturity_tier] = self.tier_counts.get(maturity_tier, 0) + 1
            self.namespaces.add(namespace)
            self.lemma_index.setdefault(lemma.lower(), []).append(wsid)
        logger.info(f"  Loaded {len(self.senses):,} senses in {time.time()-t0:.1f}s")

        # Load embeddings, grouped by method
        cur.execute(
            "SELECT wiktionary_source_id, embedding_method, embed "
            "FROM sense_embedding WHERE embed IS NOT NULL"
        )
        per_method: Dict[str, List[Tuple[int, List[float]]]] = {}
        for wsid, method, blob in cur:
            if wsid not in self.senses:
                continue
            v = vec_from_blob(blob)
            per_method.setdefault(method, []).append((wsid, v))
        for method, items in per_method.items():
            wsids = [w for w, _ in items]
            vectors = [v for _, v in items]
            dim = len(vectors[0]) if vectors else 0
            state = EmbedderState(
                method=method, dim=dim, wsids=wsids, vectors=vectors,
                wsid_to_idx={w: i for i, w in enumerate(wsids)},
            )
            self.embedders[method] = state
            logger.info(f"  Embedder {method}: {len(wsids):,} senses, dim={dim}")

        # Load content_identical groups (if present)
        try:
            cur.execute(
                "SELECT group_id, audience_tier, standard_form_wsid "
                "FROM content_identical_group"
            )
            for gid, tier, std_wsid in cur:
                self.content_groups[gid] = {
                    "audience_tier": tier,
                    "standard_form_wsid": std_wsid,
                }
            cur.execute(
                "SELECT cim.wsid, cig.audience_tier, cim.group_id "
                "FROM content_identical_member cim "
                "JOIN content_identical_group cig ON cig.group_id = cim.group_id"
            )
            for wsid, tier, gid in cur:
                self.wsid_to_groups.setdefault(wsid, {})[tier] = gid
            logger.info(
                f"  Content-identical: {len(self.content_groups):,} groups, "
                f"{sum(len(g) for g in self.wsid_to_groups.values()):,} memberships"
            )
        except sqlite3.OperationalError:
            logger.info("  No content_identical tables present (v3.0 or older lexicon)")

        conn.close()
        logger.info(f"Lexicon fully loaded in {time.time()-t0:.1f}s")

    # ---------------- Lookups ----------------

    def lookup_by_canonical_id(self, cid: str) -> Optional[SenseRecord]:
        for s in self.senses.values():
            if s.canonical_id == cid:
                return s
        return None

    def neutral_substitute_for(
        self, wsid: int, audience_tier: str = "general"
    ) -> Optional["SenseRecord"]:
        """Find the content-identical neutral substitute for a marked sense.

        Returns the sense pointed at by the group's standard_form_wsid for
        the requested audience_tier. Returns None if:
          - the sense has no content_identical_group at this tier
          - the group's standard_form_wsid is unset
          - the standard sense itself is missing or also marked
        Callers should treat None as "no neutral substitute available" and
        fall back to whatever on_snap_failure specifies.
        """
        tier_to_group = self.wsid_to_groups.get(wsid)
        if not tier_to_group:
            return None
        gid = tier_to_group.get(audience_tier)
        if gid is None:
            return None
        group = self.content_groups.get(gid)
        if not group:
            return None
        std_wsid = group.get("standard_form_wsid")
        if not std_wsid or std_wsid == wsid:
            # No standard form chosen, or this sense IS the standard form
            return None
        return self.senses.get(std_wsid)

    def topk(
        self, query_vec: List[float], method: str, k: int,
        lemma_restrict: Optional[str] = None,
        auto_resolve_forms: bool = False,
        db_path: Optional[str] = None,
        pos_restrict: Optional[str] = None,
    ) -> List[Tuple[int, float]]:
        emb = self.embedders.get(method)
        if emb is None:
            return []
        if lemma_restrict:
            wanted = [lemma_restrict.lower()]
            if auto_resolve_forms and db_path:
                try:
                    import lemma_resolver
                    expanded = list(wanted)
                    seen = set(expanded)
                    for surface in wanted:
                        for lemma in lemma_resolver.expand_to_lemmas(
                                surface, db_path, prefer_pos=pos_restrict):
                            if lemma not in seen:
                                expanded.append(lemma)
                                seen.add(lemma)
                    wanted = expanded
                except Exception:
                    pass
            wsids = []
            for lemma in wanted:
                wsids.extend(self.lemma_index.get(lemma, []))
            candidate_idxs = [emb.wsid_to_idx[w] for w in wsids
                              if w in emb.wsid_to_idx]
        else:
            candidate_idxs = range(len(emb.wsids))
        scored = []
        for i in candidate_idxs:
            d = dot(query_vec, emb.vectors[i])
            scored.append((emb.wsids[i], d))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:k]

    def embedder_coverage(self, method: str) -> float:
        """Coverage = fraction of senses in the lexicon that have an
        embedding under this method. 1.0 means complete."""
        n_total = len(self.senses)
        if n_total == 0:
            return 0.0
        emb = self.embedders.get(method)
        if emb is None:
            return 0.0
        return len(emb.wsids) / n_total

    def embedder_status(self, method: str, min_coverage: float = 0.95) -> str:
        """Classify an embedder as 'complete', 'partial', or 'empty'."""
        c = self.embedder_coverage(method)
        if c >= min_coverage:
            return "complete"
        if c >= 0.001:
            return "partial"
        return "empty"

    def cascade_for_language(
        self, language: str, cascade_config: Dict[str, List[str]],
        min_coverage: float = 0.95,
    ) -> List[str]:
        """Build the ordered list of embedders to try.

        The list is the configured preference cascade, intersected with
        what is actually loaded AND filtered by coverage. A partial
        embedder (coverage < min_coverage) is dropped silently so the
        cascade never returns questionable results from a half-built
        embedder. Quality order is preserved (the cascade list is
        already a quality-ranked preference).

        Last-resort fallback: if NO embedder passes the coverage gate
        but at least one is loaded, return the most-covered embedder
        anyway. The caller can decide whether to use it; this prevents
        a 0% lexicon from being unusable just because nothing reached
        the threshold.
        """
        lang_key = (language or "").lower()
        if lang_key in ("en", "english"):
            preferred = cascade_config.get("en", [])
        else:
            preferred = cascade_config.get("multilingual", [])
        if not preferred:
            preferred = cascade_config.get("default", [])

        # Walk in configured (quality-ranked) order; keep only loaded
        # AND coverage-passing embedders.
        ordered = [
            m for m in preferred
            if m in self.embedders
            and self.embedder_coverage(m) >= min_coverage
        ]

        # Last-resort fallback: nothing passed coverage but something is
        # loaded. Pick the most-covered loaded embedder so the server is
        # not bricked.
        if not ordered and self.embedders:
            best = max(self.embedders.keys(),
                       key=lambda m: self.embedder_coverage(m))
            ordered = [best]
        return ordered

    def best_embedder_for_language(self, language: str = "en") -> Optional[str]:
        """Back-compat shim: return the first embedder from the default cascade."""
        cascade = self.cascade_for_language(
            language,
            getattr(self, "_cascade_config", BUILT_IN_CASCADE),
        )
        return cascade[0] if cascade else None


# ===========================================================================
# Policy application
# ===========================================================================

def apply_policy(
    sense_id_and_score: List[Tuple[int, float]],
    backend: LexiconBackend,
    policy: Policy,
) -> List[Dict[str, Any]]:
    """Convert raw (wsid, cosine) results into policy-filtered dicts."""
    min_tier_idx = TIER_ORDER.index(policy.min_tier_returned) \
        if policy.min_tier_returned in TIER_ORDER else 0

    out: List[Dict[str, Any]] = []
    exclusions = 0
    rewrites = 0
    demotions = 0

    for wsid, raw_score in sense_id_and_score:
        sense = backend.senses.get(wsid)
        if sense is None:
            continue

        # Tier floor
        sense_tier_idx = TIER_ORDER.index(sense.maturity_tier) \
            if sense.maturity_tier in TIER_ORDER else 0
        if sense_tier_idx < min_tier_idx:
            exclusions += 1
            continue

        # Hard exclusions
        if sense.social_status and sense.social_status in policy.exclude_social_status:
            exclusions += 1
            continue
        if sense.temporal_status and sense.temporal_status in policy.exclude_temporal_status:
            exclusions += 1
            continue

        # snap_to_neutral: substitute marked senses with their
        # content-identical neutral form, OR fall through per
        # on_snap_failure.
        # We preserve the matched_wsid/matched_canonical_id pointing at
        # what the embedder retrieved, even after substitution swaps the
        # display sense to the neutral form.
        matched_wsid_for_record = wsid
        matched_cid_for_record = sense.canonical_id
        substituted_from_wsid: Optional[int] = None
        substituted_from_cid: Optional[str] = None
        snap_reason: Optional[str] = None
        if (sense.social_status and
                sense.social_status in policy.snap_social_status):
            snap_reason = f"social_status={sense.social_status}"
        elif (sense.temporal_status and
                sense.temporal_status in policy.snap_temporal_status):
            snap_reason = f"temporal_status={sense.temporal_status}"
        if snap_reason is not None:
            # Specialist preservation overrides snap (the leukemia rule
            # applied to substitution, not just rewriting).
            if policy.preserve_specialist_terms and sense.specificity in (
                "specialist", "technical"
            ):
                pass  # leave the marked sense alone
            else:
                neutral = backend.neutral_substitute_for(
                    wsid, policy.audience_tier
                )
                if neutral is not None:
                    # Substitute. Treat the neutral sense as the matched
                    # result; remember the original for transparency.
                    substituted_from_wsid = wsid
                    substituted_from_cid = sense.canonical_id
                    sense = neutral
                    wsid = neutral.wsid
                else:
                    # No neutral substitute available. Apply failure mode.
                    failure_mode = (policy.on_snap_failure or "drop").lower()
                    if failure_mode == "drop":
                        exclusions += 1
                        continue
                    elif failure_mode == "sentinel":
                        out.append({
                            "wsid": None,
                            "canonical_id": None,
                            "lemma": sense.lemma,
                            "pos_simple": sense.pos_simple,
                            "microgloss": None,
                            "score": round(raw_score, 6),
                            "raw_cosine": round(raw_score, 6),
                            "penalty": 0.0,
                            "register": None,
                            "temporal_status": None,
                            "social_status": None,
                            "specificity": None,
                            "maturity_tier": None,
                            "namespace": None,
                            "matched_wsid": sense.wsid,
                            "matched_canonical_id": sense.canonical_id,
                            "excluded_by_policy": True,
                            "exclusion_reason": snap_reason,
                            "rewritten_to_standard": False,
                        })
                        exclusions += 1
                        continue
                    # "passthrough": fall through and let the marked
                    # sense be returned unchanged (least conservative).

        # Demotions
        penalty = 0.0
        penalty += policy.demote_register.get(sense.register or "", 0.0)
        penalty += policy.demote_temporal.get(sense.temporal_status or "", 0.0)
        penalty += policy.demote_social.get(sense.social_status or "", 0.0)
        score = raw_score - penalty
        if penalty > 0:
            demotions += 1

        # Standard-form rewrite (snap-to-standard)
        rewritten_to_wsid: Optional[int] = None
        rewritten_to_cid: Optional[str] = None
        if policy.rewrite_to_standard_form:
            if policy.preserve_specialist_terms and sense.specificity in (
                "specialist", "technical"
            ):
                pass  # never snap specialist terms
            else:
                groups_for_wsid = backend.wsid_to_groups.get(wsid, {})
                gid = groups_for_wsid.get(policy.audience_tier)
                if gid is not None:
                    grp = backend.content_groups.get(gid)
                    std_wsid = grp.get("standard_form_wsid") if grp else None
                    if std_wsid and std_wsid != wsid:
                        std_sense = backend.senses.get(std_wsid)
                        if std_sense is not None:
                            rewritten_to_wsid = std_wsid
                            rewritten_to_cid = std_sense.canonical_id
                            rewrites += 1

        # Final returned record uses the (possibly rewritten) sense for
        # display fields, but preserves the original match.
        display_sense = (
            backend.senses[rewritten_to_wsid] if rewritten_to_wsid else sense
        )
        out.append({
            "wsid": display_sense.wsid,
            "canonical_id": display_sense.canonical_id,
            "lemma": display_sense.lemma,
            "pos_simple": display_sense.pos_simple,
            "microgloss": display_sense.microgloss,
            "score": round(score, 6),
            "raw_cosine": round(raw_score, 6),
            "penalty": round(penalty, 6),
            "register": display_sense.register,
            "temporal_status": display_sense.temporal_status,
            "social_status": display_sense.social_status,
            "specificity": display_sense.specificity,
            "maturity_tier": display_sense.maturity_tier,
            "namespace": display_sense.namespace,
            "matched_wsid": matched_wsid_for_record,
            "matched_canonical_id": matched_cid_for_record,
            "rewritten_to_standard": rewritten_to_cid is not None,
            "substituted_from_canonical_id": substituted_from_cid,
            "snap_reason": snap_reason if substituted_from_cid else None,
        })

    # Re-sort by score (after penalties)
    out.sort(key=lambda r: r["score"], reverse=True)

    return out


# ===========================================================================
# Query embedding (deferred, optional)
# ===========================================================================

class EmbedderProxy:
    """Loads an ONNX embedder on first use. If sgflib is importable
    from the GLEAN bundle, we reuse its OnnxEmbedder. Otherwise we
    fall back to a minimal local embedder.

    For Stage 0 of the rollout, we DON'T require the ONNX runtime to
    be installed; the server can run in 'lookup-only' mode where
    clients supply pre-computed query vectors. /embed will return 503
    in that case.
    """

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._available = self._probe()

    def _probe(self) -> bool:
        try:
            import onnxruntime  # noqa: F401
            return True
        except ImportError:
            logger.warning(
                "onnxruntime not installed; /embed endpoint will be disabled. "
                "Clients must supply query vectors directly."
            )
            return False

    def available(self) -> bool:
        return self._available

    def embed(self, text: str, method: str) -> List[float]:
        # Lazy import inside the function so the server boots without ONNX.
        if method not in self._cache:
            self._cache[method] = self._load(method)
        return self._cache[method](text)

    def _load(self, method: str):
        # Minimal ONNX BGE loader. For Stage 0 we trust the user has
        # already downloaded the model via huggingface_hub.
        import onnxruntime
        from tokenizers import Tokenizer
        from huggingface_hub import hf_hub_download
        repo_map = {
            "bge-small-en-v1": ("Xenova/bge-small-en-v1.5", "BAAI/bge-small-en-v1.5"),
            "bge-large-en-v1": ("Xenova/bge-large-en-v1.5", "BAAI/bge-large-en-v1.5"),
            "bge-m3":          ("Xenova/bge-m3",            "BAAI/bge-m3"),
            "bge-m3-v1":       ("Xenova/bge-m3",            "BAAI/bge-m3"),
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

        def embed_fn(text: str) -> List[float]:
            enc = tok.encode(text)
            ids = [enc.ids]
            mask = [enc.attention_mask]
            ttype = [enc.type_ids]
            import numpy as np
            ort_in = {
                "input_ids": np.array(ids, dtype="int64"),
                "attention_mask": np.array(mask, dtype="int64"),
                "token_type_ids": np.array(ttype, dtype="int64"),
            }
            out = sess.run(None, ort_in)[0][0][0]  # CLS pooling
            arr = out / (np.linalg.norm(out) + 1e-12)
            return arr.tolist()
        return embed_fn


# ===========================================================================
# Request / response schemas
# ===========================================================================

class SearchRequest(BaseModel):
    text: Optional[str] = Field(None, description="Query text (will be embedded)")
    query_vector: Optional[List[float]] = Field(None, description="Pre-computed vector")
    k: int = Field(10, ge=1, le=200)
    lemma_restrict: Optional[str] = Field(None, description="Restrict to a lemma")
    auto_resolve_forms: bool = Field(False, description="If True, expand lemma_restrict via lemma_form table (e.g. 'burned' -> 'burn')")
    pos_restrict: Optional[str] = Field(None, description="Restrict to a pos_simple (n|v|adj|adv|name)")
    language: str = Field("en")
    embedding_method: Optional[str] = Field(None, description="Override embedder choice")
    policy: Optional[str] = Field(None, description="Named policy")
    policy_overrides: Optional[Dict[str, Any]] = None


class LookupCanonicalRequest(BaseModel):
    canonical_id: str


class LookupLemmaRequest(BaseModel):
    lemma: str
    pos: Optional[str] = None
    policy: Optional[str] = None
    policy_overrides: Optional[Dict[str, Any]] = None


# ===========================================================================
# Server
# ===========================================================================

@dataclass
class ServerState:
    backend: LexiconBackend
    policies: Dict[str, Policy]
    embedder: EmbedderProxy
    api_token: Optional[str]  # None = no auth required
    booted_at: float
    embedder_cascade: Dict[str, List[str]]  # config-derived cascade lists
    embedder_min_coverage: float = 0.95
    reranker_cfg: Dict[str, Any] = field(default_factory=dict)
    bm25_cfg: Dict[str, Any] = field(default_factory=dict)
    tiebreak_cfg: Dict[str, Any] = field(default_factory=dict)
    llm_wrapper_path: Optional[str] = None


_state: Optional[ServerState] = None


def _check_auth(x_api_key: Optional[str]):
    if _state is None or _state.api_token is None:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, _state.api_token):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


def _top2_score_margin(results):
    """Margin between top-1 and top-2 result scores. Returns None if N/A."""
    if not results or len(results) < 2:
        return None
    def pick(r):
        if "rerank_score" in r:
            return float(r["rerank_score"])
        if "score" in r:
            return float(r["score"])
        if "raw_cosine" in r:
            return float(r["raw_cosine"])
        return None
    s1 = pick(results[0])
    s2 = pick(results[1])
    if s1 is None or s2 is None:
        return None
    return s1 - s2


def _candidate_text_for_bm25(result):
    """Concatenate the doc-side text fields BM25 will score over.

    Order matters slightly: most-disambiguating text first so that if
    a downstream caller ever truncates very long documents, the
    most-useful text is retained. Order: improved_microgloss >
    microgloss > gloss > example_sentences > lemma.
    """
    parts = []
    for field_name in ("improved_microgloss", "microgloss", "gloss",
                       "example_sentences", "lemma"):
        val = result.get(field_name) if isinstance(result, dict) else None
        if not val:
            continue
        if isinstance(val, (list, tuple)):
            parts.append(" ".join(str(x) for x in val))
        else:
            parts.append(str(val))
    return " ".join(parts)


def _resolve_policy(name: Optional[str], overrides: Optional[dict]) -> Policy:
    assert _state is not None
    base_name = name or "__default__"
    pol = _state.policies.get(base_name)
    if pol is None:
        raise HTTPException(404, f"Unknown policy {name!r}")
    return pol.merge_overrides(overrides)


def make_app() -> FastAPI:
    app = FastAPI(
        title="GLEAN Search Server",
        version="1.0",
        description="Universal entry point for the SGF lexicon.",
    )

    @app.get("/health")
    def health(x_api_key: Optional[str] = Header(None)):
        _check_auth(x_api_key)
        assert _state is not None
        tier_dist = {t: _state.backend.tier_counts.get(t, 0) for t in TIER_ORDER}
        emb_info = [
            {"method": m, "dim": e.dim, "n_senses": len(e.wsids)}
            for m, e in _state.backend.embedders.items()
        ]
        min_cov = _state.embedder_min_coverage
        cascade_en = _state.backend.cascade_for_language(
            "en", _state.embedder_cascade, min_cov)
        cascade_multi = _state.backend.cascade_for_language(
            "multilingual", _state.embedder_cascade, min_cov)
        # Enrich emb_info with coverage + status
        emb_info = [
            {
                "method": m,
                "dim": _state.backend.embedders[m].dim,
                "n_senses": len(_state.backend.embedders[m].wsids),
                "coverage": round(_state.backend.embedder_coverage(m), 4),
                "status": _state.backend.embedder_status(m, min_cov),
            }
            for m in _state.backend.embedders
        ]
        return {
            "status": "ok",
            "uptime_seconds": round(time.time() - _state.booted_at, 1),
            "n_senses_total": len(_state.backend.senses),
            "embedder_min_coverage": min_cov,
            "embedders_loaded": emb_info,
            "embedder_cascade_en": cascade_en,
            "embedder_cascade_multilingual": cascade_multi,
            "default_embedder_english":
                cascade_en[0] if cascade_en else None,
            "tier_distribution": tier_dist,
            "namespaces": sorted(_state.backend.namespaces),
            "n_content_identical_groups": len(_state.backend.content_groups),
            "policies_available": [
                n for n in _state.policies.keys() if not n.startswith("__")
            ],
            "default_policy": _state.policies["__default__"].name,
            "embedder_runtime_available": _state.embedder.available(),
            "lexicon_v3_1_features": _state.backend.has_v3_1,
        }

    @app.get("/policies")
    def list_policies(x_api_key: Optional[str] = Header(None)):
        _check_auth(x_api_key)
        assert _state is not None
        return {
            name: {
                "rewrite_to_standard_form": p.rewrite_to_standard_form,
                "preserve_specialist_terms": p.preserve_specialist_terms,
                "audience_tier": p.audience_tier,
                "min_tier_returned": p.min_tier_returned,
                "exclude_social_status": p.exclude_social_status,
                "exclude_temporal_status": p.exclude_temporal_status,
            }
            for name, p in _state.policies.items()
            if not name.startswith("__")
        }

    @app.post("/embed")
    def embed(
        req: Dict[str, Any],
        x_api_key: Optional[str] = Header(None),
    ):
        _check_auth(x_api_key)
        assert _state is not None
        if not _state.embedder.available():
            raise HTTPException(503, "Embedder runtime not installed on this server")
        text = req.get("text")
        if not text:
            raise HTTPException(400, "text is required")
        method = req.get("embedding_method") \
            or _state.backend.best_embedder_for_language(req.get("language", "en"))
        if not method:
            raise HTTPException(503, "No embedders loaded")
        v = _state.embedder.embed(text, method)
        return {"vector": v, "embedding_method": method, "dim": len(v)}

    @app.post("/search")
    def search(req: SearchRequest, x_api_key: Optional[str] = Header(None)):
        _check_auth(x_api_key)
        assert _state is not None
        policy = _resolve_policy(req.policy, req.policy_overrides)

        # Build the cascade. Explicit --embedder pins exactly one embedder;
        # no cascade in that case. Otherwise: configured cascade for the
        # requested language, intersected with what is loaded.
        if req.embedding_method:
            # Explicit override: coverage gate bypassed.
            if req.embedding_method not in _state.backend.embedders:
                raise HTTPException(
                    503,
                    f"Embedder {req.embedding_method!r} not loaded. "
                    f"Loaded: {list(_state.backend.embedders.keys())}",
                )
            cascade = [req.embedding_method]
        else:
            cascade = _state.backend.cascade_for_language(
                req.language, _state.embedder_cascade,
                _state.embedder_min_coverage,
            )
        if not cascade:
            raise HTTPException(503, "No embedders loaded")

        # Iterate the cascade. First embedder that returns a non-empty
        # result set wins. Each attempt re-embeds the query text under that
        # embedder's tokenizer/model -- score scales are NOT comparable
        # across embedders, so we never blend.
        results = []
        embedder_used = None
        attempted = []
        for method in cascade:
            attempted.append(method)
            if req.query_vector is not None and method == cascade[0]:
                # Caller supplied a precomputed vector; only valid for the
                # first embedder in the cascade (the one the caller
                # presumably embedded under). After that we'd need text.
                qv = req.query_vector
            elif req.text:
                if not _state.embedder.available():
                    raise HTTPException(
                        503,
                        "Embedder runtime unavailable; supply query_vector",
                    )
                qv = _state.embedder.embed(req.text, method)
            else:
                if req.query_vector is not None:
                    # We've exhausted the precomputed vector's one valid
                    # embedder; cannot cascade further without text.
                    break
                raise HTTPException(400, "Provide text or query_vector")

            raw = _state.backend.topk(
                qv, method, req.k * 3,
                req.lemma_restrict,
                auto_resolve_forms=req.auto_resolve_forms,
                db_path=str(_state.backend.db_path),
                pos_restrict=req.pos_restrict,
            )
            candidate = apply_policy(raw, _state.backend, policy)[: req.k]
            if candidate:
                results = candidate
                embedder_used = method
                break

        # Server-side cascade: rerank -> BM25 -> LLM tiebreak.
        # Each stage is config-driven and optional. Stages no-op when
        # their mode is "never" or when the prior stage left the top-2
        # margin wide enough that the stage shouldn't fire. The cascade
        # runs only when we have query text (not pure query_vector).
        reranker_applied = None
        bm25_applied = False
        tiebreak_applied = False
        rr_cfg = _state.reranker_cfg or {}
        bm25_cfg = _state.bm25_cfg or {}
        tb_cfg = _state.tiebreak_cfg or {}
        if results and req.text:
            # Stage 2: cross-encoder reranker
            if rr_cfg.get("enabled"):
                top_n = int(rr_cfg.get("top_n", 20))
                always = bool(rr_cfg.get("rerank_always", False))
                margin_th = float(rr_cfg.get("rerank_margin_threshold", 0.05))
                margin = _top2_score_margin(results)
                if always or (margin is not None and margin < margin_th):
                    import reranker as rk
                    rescored = rk.rerank(
                        req.text, list(results[:top_n]),
                        rr_cfg.get("models",
                                   ["bge-reranker-v2-m3"]),
                    )
                    results = rescored + results[top_n:]
                    if rescored and rescored[0].get("rerank_model"):
                        reranker_applied = rescored[0]["rerank_model"]

            # Stage 3: BM25 lexical scoring over retained candidates
            bm25_mode = (bm25_cfg.get("mode") or "never").lower()
            if bm25_mode != "never":
                import bm25_score as _bm
                bm25_margin_th = float(bm25_cfg.get("margin_threshold", 0.04))
                bm25_abs_floor = float(bm25_cfg.get("abs_confidence_floor", 0.0))
                bm25_top_n_out = int(bm25_cfg.get("top_n_out", 3))
                prior_scores = [r.get("score", 0.0) for r in results]
                top1_score = prior_scores[0] if prior_scores else 0.0
                margin_tight = (_bm.normalized_margin(prior_scores)
                                < bm25_margin_th)
                abs_low = (bm25_abs_floor > 0.0
                           and top1_score < bm25_abs_floor)
                fire_bm25 = (bm25_mode == "always" or
                             (bm25_mode == "when_tight" and
                              (margin_tight or abs_low)))
                if fire_bm25:
                    cand_texts = [_candidate_text_for_bm25(r) for r in results]
                    bm25_raw = _bm.score_candidates(req.text, cand_texts, bm25_cfg)
                    fusion = (bm25_cfg.get("fusion") or "weighted").lower()
                    if fusion == "sequential":
                        order = sorted(range(len(results)),
                                       key=lambda i: bm25_raw[i],
                                       reverse=True)
                    else:
                        alpha = float(bm25_cfg.get("weighted_alpha", 0.7))
                        prior_norm = _bm.normalize_minmax(prior_scores)
                        bm25_norm = _bm.normalize_minmax(bm25_raw)
                        fused = _bm.fuse_weighted(prior_norm, bm25_norm, alpha)
                        order = sorted(range(len(results)),
                                       key=lambda i: fused[i],
                                       reverse=True)
                    new_results = []
                    for old_idx in order:
                        r = dict(results[old_idx])
                        r["bm25_score"] = bm25_raw[old_idx]
                        new_results.append(r)
                    results = new_results[:bm25_top_n_out] + new_results[bm25_top_n_out:]
                    bm25_applied = True

            # Stage 4: LLM tiebreak (slowest)
            tb_mode = (tb_cfg.get("mode")
                       or ("when_tight" if tb_cfg.get("server_enabled") else "never")
                       ).lower()
            if tb_mode != "never":
                import llm_tiebreaker as tbm
                import bm25_score as _bm
                margin_th = float(tb_cfg.get("margin_threshold", 0.03))
                abs_floor = float(tb_cfg.get("abs_confidence_floor", 0.0))
                prior_scores = [r.get("score", 0.0) for r in results]
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
                        axes = list(tb_cfg.get("divergent_axes")
                                    or ["register", "social_status",
                                        "temporal_status", "specificity"])
                        top_n_llm = int(tb_cfg.get("top_n_to_llm", 5))
                        fire_llm = _bm.candidates_diverge_on(results[:top_n_llm], axes)
                if fire_llm:
                    wrapper = (_state.llm_wrapper_path
                               or tb_cfg.get("llm_wrapper", "llm_wrapper.py"))
                    top_n_llm = int(tb_cfg.get("top_n_to_llm", 5))
                    tiebroken = tbm.tiebreak(
                        req.text, list(results[:top_n_llm]),
                        wrapper,
                        tier=tb_cfg.get("tier", "flash"),
                        temp=float(tb_cfg.get("temp", 0.0)),
                    )
                    results = tiebroken + results[top_n_llm:]
                    tiebreak_applied = True

        return {
            "query_embedding_method": embedder_used,  # back-compat
            "embedder_used": embedder_used,
            "embedder_cascade_attempted": attempted,
            "policy_applied": policy.name,
            "reranker_applied": reranker_applied,
            "bm25_applied": bm25_applied,
            "llm_tiebreak_applied": tiebreak_applied,
            "results": results,
            "n_results": len(results),
        }

    @app.post("/lookup/canonical")
    def lookup_canonical(
        req: LookupCanonicalRequest,
        x_api_key: Optional[str] = Header(None),
    ):
        _check_auth(x_api_key)
        assert _state is not None
        s = _state.backend.lookup_by_canonical_id(req.canonical_id)
        if s is None:
            raise HTTPException(404, f"No sense with canonical_id={req.canonical_id!r}")
        return {
            "wsid": s.wsid, "canonical_id": s.canonical_id,
            "lemma": s.lemma, "pos_simple": s.pos_simple,
            "microgloss": s.microgloss, "register": s.register,
            "temporal_status": s.temporal_status,
            "social_status": s.social_status,
            "specificity": s.specificity,
            "maturity_tier": s.maturity_tier,
            "namespace": s.namespace,
        }

    @app.post("/lookup/lemma")
    def lookup_lemma(
        req: LookupLemmaRequest,
        x_api_key: Optional[str] = Header(None),
    ):
        _check_auth(x_api_key)
        assert _state is not None
        policy = _resolve_policy(req.policy, req.policy_overrides)
        wsids = _state.backend.lemma_index.get(req.lemma.lower(), [])
        if req.pos:
            wsids = [
                w for w in wsids
                if _state.backend.senses[w].pos_simple == req.pos
            ]
        scored = [(w, 1.0) for w in wsids]
        results = apply_policy(scored, _state.backend, policy)
        return {
            "lemma": req.lemma, "pos": req.pos,
            "policy_applied": policy.name,
            "results": results,
            "n_results": len(results),
        }

    return app


# ===========================================================================
# Main
# ===========================================================================

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--lexicon", required=True, help="Path to sgf_lexicon.db")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8400)
    p.add_argument("--policy", default=str(DEFAULT_POLICY_PATH),
                   help="Path to policy.toml")
    p.add_argument("--auth-file", default=str(DEFAULT_AUTH_PATH),
                   help="Path to auth.toml (read on non-loopback bind)")
    p.add_argument("--no-auth", action="store_true",
                   help="Skip auth even on non-loopback bind (NOT recommended)")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--search-config", default=None,
                   help="Path to glean_search_policy.toml (reranker + tiebreak)")
    p.add_argument("--config-dir", default=None,
                   help="Directory holding policy.toml + glean_search_policy.toml. "
                        "Overrides ~/.glean/ as the lookup location. Useful when "
                        "running the bundle in a self-contained directory.")
    p.add_argument("--llm-wrapper", default=None,
                   help="Override llm_wrapper.py path for server-side LLM tiebreak")
    args = p.parse_args()

    setup_logging(args.verbose)

    db_path = Path(args.lexicon)
    if not db_path.exists():
        print(f"Lexicon DB not found: {db_path}", file=sys.stderr)
        return 1

    logger.info(f"Loading lexicon: {db_path}")
    backend = LexiconBackend(db_path)
    backend.load_all()

    # Resolve policy file location with priority: --policy > --config-dir
    # > bundle dir > ~/.glean/.
    policy_path = resolve_policy_path(
        explicit_path=(args.policy if args.policy != str(DEFAULT_POLICY_PATH)
                       else None),
        config_dir=args.config_dir,
    )
    logger.info(f"Loading policy: {policy_path}")
    policies, embedder_cascade, min_coverage = load_policies(policy_path)
    backend._cascade_config = embedder_cascade

    is_loopback = args.host in ("127.0.0.1", "localhost", "::1")
    if is_loopback or args.no_auth:
        api_token = None
        if not is_loopback:
            logger.warning(
                "Running without auth on a non-loopback address. "
                "This is insecure. Use only on trusted networks."
            )
    else:
        api_token = load_or_create_auth(Path(args.auth_file))
        logger.info(f"Auth required. Token loaded from {args.auth_file}")

    embedder = EmbedderProxy()

    global _state
    # Load reranker + LLM-tiebreak config. Priority order: --search-config
    # > --config-dir > bundle dir > ~/.glean/.
    import glean_search_config as _gcfg
    _search_cfg_path = _gcfg.resolve_config_path(
        explicit_path=args.search_config,
        config_dir=args.config_dir,
    )
    logger.info(f"Loading search config: {_search_cfg_path}")
    _scfg = _gcfg.load_config(args.search_config, config_dir=args.config_dir)
    reranker_cfg = _gcfg.get_reranker_config(_scfg, side="server")
    bm25_cfg = _gcfg.get_bm25_config(_scfg, side="server")
    tiebreak_cfg = _gcfg.get_tiebreak_config(_scfg, side="server")

    _state = ServerState(
        backend=backend,
        policies=policies,
        embedder=embedder,
        api_token=api_token,
        booted_at=time.time(),
        embedder_cascade=embedder_cascade,
        embedder_min_coverage=min_coverage,
        reranker_cfg=reranker_cfg,
        bm25_cfg=bm25_cfg,
        tiebreak_cfg=tiebreak_cfg,
        llm_wrapper_path=args.llm_wrapper,
    )

    app = make_app()
    logger.info(f"Starting GLEAN search server on http://{args.host}:{args.port}")
    logger.info(f"  Default policy: {policies['__default__'].name}")
    logger.info(f"  Coverage threshold: {min_coverage:.2f} (embedders below this are"
                f" excluded from the cascade)")
    n_total = len(backend.senses)
    for m in backend.embedders:
        n = len(backend.embedders[m].wsids)
        cov = backend.embedder_coverage(m)
        status = backend.embedder_status(m, min_coverage)
        status_label = {
            "complete": "COMPLETE",
            "partial":  "PARTIAL (below coverage threshold, excluded from cascade)",
            "empty":    "EMPTY (no rows in sense_embedding for this method)",
        }[status]
        logger.info(
            f"  Embedder {m}: {n:,}/{n_total:,} senses "
            f"({cov:.1%}) -- {status_label}"
        )
    cascade_en = backend.cascade_for_language("en", embedder_cascade, min_coverage)
    cascade_multi = backend.cascade_for_language(
        "multilingual", embedder_cascade, min_coverage)
    logger.info(f"  Cascade (en):           {cascade_en}")
    logger.info(f"  Cascade (multilingual): {cascade_multi}")
    logger.info(f"  Auth: {'required' if api_token else 'disabled (loopback)'}")
    rr_status = ("enabled" if reranker_cfg.get("enabled") else "disabled")
    bm25_status = bm25_cfg.get("mode", "never")
    tb_mode = (tiebreak_cfg.get("mode")
               or ("when_tight" if tiebreak_cfg.get("server_enabled") else "never"))
    logger.info(f"  Reranker (server-side): {rr_status}; "
                f"models={reranker_cfg.get('models', [])}")
    logger.info(f"  BM25 (server-side): mode={bm25_status}; "
                f"fusion={bm25_cfg.get('fusion', 'weighted')}; "
                f"alpha={bm25_cfg.get('weighted_alpha', 0.7)}")
    logger.info(f"  LLM tiebreak (server-side): mode={tb_mode}; "
                f"margin<{tiebreak_cfg.get('margin_threshold', 0.03)} fires")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
