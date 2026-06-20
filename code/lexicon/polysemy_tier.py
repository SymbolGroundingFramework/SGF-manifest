"""polysemy_tier.py -- classify a lemma's polysemy and pick audit thresholds.

A lemma like "the" has one sense; "set" has 150+. A one-size-fits-all
audit standard either fails the easy cases or never fails the hard
ones. This module bins lemmas into four tiers and exposes the
tier-specific knobs used by microgloss_audit and the cluster builder.

Pure functions, no DB, no embedder. Easy to test in isolation.
"""


# ---------------------------------------------------------------------------
# Tier classification
# ---------------------------------------------------------------------------

LOW = "low"
MEDIUM = "medium"
HIGH = "high"
VERY_HIGH = "very_high"

# Boundaries are inclusive of the lower bound and exclusive of the upper.
# (1..5) -> low, (6..15) -> medium, (16..40) -> high, (41..inf) -> very_high
_TIER_BOUNDARIES = (
    (1,   6,    LOW),
    (6,   16,   MEDIUM),
    (16,  41,   HIGH),
    (41,  10**9, VERY_HIGH),
)


def classify_polysemy(n_senses):
    """Return one of LOW, MEDIUM, HIGH, VERY_HIGH for a lemma with n senses.

    n_senses must be a positive integer. A lemma with zero senses is
    nonsensical; the function raises ValueError so the caller catches the
    bug instead of silently bucketing it.
    """
    n = int(n_senses)
    if n <= 0:
        raise ValueError(f"n_senses must be positive, got {n_senses!r}")
    for lo, hi, tier in _TIER_BOUNDARIES:
        if lo <= n < hi:
            return tier
    return VERY_HIGH  # defensive; the last bucket above already covers infty


# ---------------------------------------------------------------------------
# Cluster size cap (used when building the T2 in-cluster comparison set)
# ---------------------------------------------------------------------------

# How many candidates to include in the close-cousin cluster for T2.
# Low-polyseme lemmas have small natural neighborhoods; a generous cap
# would just pad the test with distant cousins. Very-high lemmas need a
# tight cap or the candidate has to outrank 100+ near-twins, which is
# unrealistic.
_CLUSTER_CAP = {
    LOW:       5,
    MEDIUM:    10,
    HIGH:      15,
    VERY_HIGH: 20,
}


def cluster_cap_for_tier(tier):
    """Return the max cluster size for the T2 audit at this tier."""
    if tier not in _CLUSTER_CAP:
        raise ValueError(f"Unknown polysemy tier: {tier!r}")
    return _CLUSTER_CAP[tier]


# ---------------------------------------------------------------------------
# Audit thresholds by tier
# ---------------------------------------------------------------------------

# Each tier defines:
#   t1_max_rank          : top-K acceptable in lemma-filtered search
#                          (1 = strict top-1; 3 = top-3 acceptable)
#   t2_max_rank          : top-K acceptable in lemma-free cluster
#                          (None = use quantile gate instead)
#   t2_max_quantile      : alternative quantile gate (0.25 = top quartile);
#                          when both t2_max_rank and t2_max_quantile are set,
#                          EITHER passes
#   t2_score_floor       : minimum cosine score the candidate must achieve
#                          in the lemma-free cluster regardless of rank;
#                          0.0 disables the floor.
#
# The fail-rate budget per tier (how often we expect to fall through to
# the LLM improver) is roughly: low ~3-5%, medium ~5-10%, high ~10-20%,
# very_high ~20-35%. These are tunable in the config below.
_AUDIT_THRESHOLDS = {
    LOW: {
        "t1_max_rank":     1,
        "t2_max_rank":     3,
        "t2_max_quantile": None,
        "t2_score_floor":  0.0,
    },
    MEDIUM: {
        "t1_max_rank":     1,
        "t2_max_rank":     5,
        "t2_max_quantile": None,
        "t2_score_floor":  0.0,
    },
    HIGH: {
        "t1_max_rank":     1,
        "t2_max_rank":     10,
        "t2_max_quantile": 0.25,
        "t2_score_floor":  0.0,
    },
    VERY_HIGH: {
        "t1_max_rank":     3,
        "t2_max_rank":     15,
        "t2_max_quantile": 0.25,
        "t2_score_floor":  0.0,
    },
}


def audit_thresholds_for_tier(tier):
    """Return a dict of audit thresholds for the given tier.

    The returned dict is a copy; callers may mutate it freely (e.g.
    overriding from a CLI flag or TOML config) without affecting other
    tiers' thresholds.
    """
    if tier not in _AUDIT_THRESHOLDS:
        raise ValueError(f"Unknown polysemy tier: {tier!r}")
    return dict(_AUDIT_THRESHOLDS[tier])


# ---------------------------------------------------------------------------
# DB helper: count senses per lemma in one query
# ---------------------------------------------------------------------------

def load_lemma_polysemy_counts(conn):
    """Return dict[lemma_lower, n_senses] for all lemmas in sgf_lexicon.

    Counts senses regardless of pos. If you want pos-specific tiering,
    do that in the caller; this helper is a sane default. Lemma key is
    lowercased to match the case-insensitive convention used elsewhere
    in the lexicon (lemma_index, lemma_restrict).
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT lower(lemma) AS l, COUNT(*) AS n
          FROM sgf_lexicon
         WHERE canonical_id IS NOT NULL
         GROUP BY lower(lemma)
    """)
    return {row[0]: int(row[1]) for row in cur.fetchall()}
