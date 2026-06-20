#!/usr/bin/env python3
"""
lexicon_metadata.py

Harvests structured metadata from Wiktionary tags onto the SGF
lexicon's controlled vocabulary:

    register         (9 values: formal, neutral, informal, slang, vulgar,
                                affectionate, poetic, clinical, archaic)
    temporal_status  (5 values: live, dated, archaic, obsolete, revived)
    social_status    (6 values: unmarked, informal_only, dated, flagged,
                                offensive, slur)

These values are referenced throughout the pipeline:
    - sgf_lexicon columns: register, temporal_status, social_status
    - canonical_id format: en.<lemma>.<microgloss>.<pos_simple>.<register>
    - build_embedding_texts.py: labeled tokens in embedding_text
    - retrieval policy: scoring weights per axis
    - improve_microgloss.py: refinement of provisional values

This module is the SINGLE SOURCE OF TRUTH for the tag mappings.

See SGF_LEXICON_PIPELINE.md Parts 2.6-2.8 for the full mapping rationale.
"""

from __future__ import annotations

import json


# ===========================================================================
# Controlled vocabularies (single source of truth)
# ===========================================================================

VALID_REGISTERS = frozenset({
    "formal", "neutral", "informal", "slang", "vulgar",
    "affectionate", "poetic", "clinical", "archaic",
})

VALID_TEMPORAL = frozenset({
    "live", "dated", "archaic", "obsolete", "revived",
})

VALID_SOCIAL = frozenset({
    "unmarked", "informal_only", "dated", "flagged", "offensive", "slur",
})

VALID_COUSIN_RELATIONS = frozenset({
    "TRUE_SYNONYM", "SHADED_SYNONYM", "COHYPONYM",
    "HYPONYM", "HYPERNYM",
    "PART_OF", "AGENT_OF", "LOCATION_OF",
    "EMBEDDER_NOISE", "UNCLEAR",
})

VALID_SPECIFICITY = frozenset({
    "general", "specialist", "technical",
})
SPECIFICITY_DEFAULT = "general"

# The canonical SGF semantic-role inventory. THESE ARE THE ONLY 17 ALLOWED
# RELATION NAMES (2 ontological + 15 semantic roles). LLM-produced relation
# types outside this allowlist are dropped during persistence. Do not
# extend this set without updating the spec (Part 6.4) -- HAS_PURPOSE in
# particular is INTENTIONALLY EXCLUDED; use HAS_REASON instead.
VALID_ONTOLOGICAL_RELATIONS = frozenset({
    "IS_A", "HAS_PART",
})
VALID_CORE_ROLES = frozenset({
    "HAS_AGENT", "HAS_PATIENT", "HAS_THEME", "HAS_EXPERIENCER",
    "HAS_RECIPIENT", "HAS_BENEFICIARY",
})
VALID_CONTEXT_ROLES = frozenset({
    "HAS_TIME", "HAS_LOCATION", "HAS_SOURCE", "HAS_DESTINATION",
    "HAS_MANNER", "HAS_INSTRUMENT", "HAS_CAUSE", "HAS_REASON",
    "HAS_ATTRIBUTE",
})
VALID_SEMANTIC_RELATIONS = (
    VALID_ONTOLOGICAL_RELATIONS
    | VALID_CORE_ROLES
    | VALID_CONTEXT_ROLES
)

# TODO V2 (lexicon as encyclopedia):
# V2 will introduce descriptive synapses attached to lexicon entries
# (the gloss + example sentences run through GLEAN's prose extractor).
# Those synapses use the SAME 17 relations above. The closed grammar
# does not expand. If something looks like it needs HAS_TITLE,
# HAS_JOB, HAS_NATIONALITY, that meaning belongs in a SynapseGroup
# composition, not in this allowlist. See V2_VISION.md and the V2
# entry in SGF_ROADMAP.md.


# ===========================================================================
# Wiktionary tag -> controlled-vocabulary value mappings
# ===========================================================================

REGISTER_TAG_MAP = {
    "formal":       "formal",
    "informal":     "informal",
    "colloquial":   "informal",
    "slang":        "slang",
    "vulgar":       "vulgar",
    "coarse":       "vulgar",
    "poetic":       "poetic",
    "literary":     "poetic",
    "medical":      "clinical",
    "clinical":     "clinical",
    "archaic":      "archaic",
    "endearing":    "affectionate",
    "childish":     "affectionate",
    "babytalk":     "affectionate",
}
REGISTER_DEFAULT = "neutral"

TEMPORAL_TAG_MAP = {
    "obsolete":     "obsolete",
    "archaic":      "archaic",
    "historical":   "archaic",
    "dated":        "dated",
    "rare":         "dated",
    "revived":      "revived",
}
TEMPORAL_DEFAULT = "live"

SOCIAL_TAG_MAP = {
    "slur":         "slur",
    "offensive":    "offensive",
    "derogatory":   "offensive",
    "pejorative":   "flagged",
    "disparaging":  "flagged",
    "vulgar":       "informal_only",
    "informal":     "informal_only",
    "colloquial":   "informal_only",
    "slang":        "informal_only",
    "dated":        "dated",
}
SOCIAL_DEFAULT = "unmarked"


# Severity ordering. When multiple tags map to the same axis, the
# highest-severity value wins. E.g., [slang, offensive, dated] maps to:
#   register=slang           (slang severity 4 beats neutral's 0)
#   temporal_status=dated    (dated severity 1 beats live's 0)
#   social_status=offensive  (offensive severity 4 beats informal_only's 1)
#
# This prevents weak mappings (e.g., "informal" -> social_status=informal_only)
# from overriding strong ones (e.g., "offensive" -> social_status=offensive).

REGISTER_SEVERITY = {
    "neutral": 0,
    "formal": 1,
    "clinical": 1,
    "informal": 2,
    "affectionate": 3,
    "poetic": 3,
    "slang": 4,
    "archaic": 5,
    "vulgar": 6,
}

TEMPORAL_SEVERITY = {
    "live": 0,
    "revived": 0,
    "dated": 1,
    "archaic": 2,
    "obsolete": 3,
}

SOCIAL_SEVERITY = {
    "unmarked": 0,
    "informal_only": 1,
    "dated": 2,
    "flagged": 3,
    "offensive": 4,
    "slur": 5,
}


# ===========================================================================
# Public API
# ===========================================================================

def _normalize_tags_input(tags_in):
    """Accept JSON string, list, or None. Return list of lowercase strings."""
    if tags_in is None:
        return []
    if isinstance(tags_in, str):
        try:
            parsed = json.loads(tags_in)
            tags_in = parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(tags_in, list):
        return []
    return [str(t).lower().strip() for t in tags_in if t]


def harvest_metadata_from_tags(tags_json_or_list) -> dict:
    """
    Harvest register / temporal_status / social_status from Wiktionary tags.

    Args:
        tags_json_or_list: JSON-encoded list, Python list, or None.

    Returns:
        dict with three keys: 'register', 'temporal_status', 'social_status'.
        Each set to the highest-severity matched value, or the axis default
        if no tag matched.

    Examples:
        >>> harvest_metadata_from_tags(["slang", "dated", "derogatory"])
        {'register': 'slang', 'temporal_status': 'dated', 'social_status': 'offensive'}

        >>> harvest_metadata_from_tags([])
        {'register': 'neutral', 'temporal_status': 'live', 'social_status': 'unmarked'}

        >>> harvest_metadata_from_tags(["archaic", "poetic"])
        {'register': 'archaic', 'temporal_status': 'archaic', 'social_status': 'unmarked'}

        >>> harvest_metadata_from_tags(["slang", "offensive"])
        {'register': 'slang', 'temporal_status': 'live', 'social_status': 'offensive'}
    """
    tags = _normalize_tags_input(tags_json_or_list)

    register = REGISTER_DEFAULT
    register_sev = REGISTER_SEVERITY[REGISTER_DEFAULT]
    for tag in tags:
        cand = REGISTER_TAG_MAP.get(tag)
        if cand and REGISTER_SEVERITY.get(cand, 0) > register_sev:
            register = cand
            register_sev = REGISTER_SEVERITY[cand]

    temporal_status = TEMPORAL_DEFAULT
    temporal_sev = TEMPORAL_SEVERITY[TEMPORAL_DEFAULT]
    for tag in tags:
        cand = TEMPORAL_TAG_MAP.get(tag)
        if cand and TEMPORAL_SEVERITY.get(cand, 0) > temporal_sev:
            temporal_status = cand
            temporal_sev = TEMPORAL_SEVERITY[cand]

    social_status = SOCIAL_DEFAULT
    social_sev = SOCIAL_SEVERITY[SOCIAL_DEFAULT]
    for tag in tags:
        cand = SOCIAL_TAG_MAP.get(tag)
        if cand and SOCIAL_SEVERITY.get(cand, 0) > social_sev:
            social_status = cand
            social_sev = SOCIAL_SEVERITY[cand]

    return {
        "register": register,
        "temporal_status": temporal_status,
        "social_status": social_status,
    }


def compute_sparse_data_flag(tags_json, examples_json, etymology_text,
                              linkages_json) -> int:
    """
    Returns 1 if the Wiktionary signal for this sense is sparse.

    Sparse senses are priority candidates for the LLM improver because
    the deterministic Stage 3 has little to work with beyond the gloss
    itself.

    A sense is sparse if ALL of:
      - no tags
      - no examples
      - no etymology text
      - no linkages (synonyms, antonyms, hypernyms, etc.)
    """
    def _is_empty(blob):
        if not blob:
            return True
        try:
            parsed = json.loads(blob) if isinstance(blob, str) else blob
            return not (isinstance(parsed, list) and len(parsed) > 0)
        except (json.JSONDecodeError, TypeError):
            return True

    no_tags = _is_empty(tags_json)
    no_examples = _is_empty(examples_json)
    no_etym = not (etymology_text and str(etymology_text).strip())
    no_linkages = _is_empty(linkages_json)

    return 1 if (no_tags and no_examples and no_etym and no_linkages) else 0


def validate_register(value: str) -> bool:
    """True if value is in the controlled register vocabulary."""
    return value in VALID_REGISTERS


def validate_temporal_status(value: str) -> bool:
    return value in VALID_TEMPORAL


def validate_social_status(value: str) -> bool:
    return value in VALID_SOCIAL


def validate_cousin_relation(value: str) -> bool:
    return value in VALID_COUSIN_RELATIONS


# ===========================================================================
# Self-test
# ===========================================================================

def _self_test() -> int:
    cases = [
        # (tags, expected_register, expected_temporal, expected_social)
        ([], "neutral", "live", "unmarked"),
        (["slang"], "slang", "live", "informal_only"),
        (["slang", "offensive"], "slang", "live", "offensive"),
        (["slang", "dated", "derogatory"], "slang", "dated", "offensive"),
        (["archaic"], "archaic", "archaic", "unmarked"),
        (["archaic", "poetic"], "archaic", "archaic", "unmarked"),
        (["vulgar"], "vulgar", "live", "informal_only"),
        (["formal"], "formal", "live", "unmarked"),
        (["literary"], "poetic", "live", "unmarked"),
        (["medical"], "clinical", "live", "unmarked"),
        (["informal", "vulgar"], "vulgar", "live", "informal_only"),
        (["slur", "offensive"], "neutral", "live", "slur"),
        (None, "neutral", "live", "unmarked"),
        # slang+dated -> social=dated wins over informal_only (severity-based)
        ('["slang", "dated"]', "slang", "dated", "dated"),
    ]
    failed = 0
    for tags, exp_r, exp_t, exp_s in cases:
        result = harvest_metadata_from_tags(tags)
        ok = (result["register"] == exp_r and
              result["temporal_status"] == exp_t and
              result["social_status"] == exp_s)
        status = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"  [{status}] tags={tags!r}")
        if not ok:
            print(f"           expected: register={exp_r}, temporal={exp_t}, social={exp_s}")
            print(f"           got:      register={result['register']}, temporal={result['temporal_status']}, social={result['social_status']}")

    # Sparse-data flag tests
    sparse_cases = [
        (None, None, None, None, 1),
        ('[]', '[]', '', '[]', 1),
        ('["slang"]', None, None, None, 0),
        (None, '[{"text":"example"}]', None, None, 0),
        (None, None, "From Old English", None, 0),
        (None, None, None, '[{"word":"x"}]', 0),
    ]
    for tags, ex, etym, link, expected in sparse_cases:
        actual = compute_sparse_data_flag(tags, ex, etym, link)
        ok = actual == expected
        status = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"  [{status}] sparse(tags={tags!r}, ex={ex!r}, etym={etym!r}, link={link!r}) -> {actual}")

    print()
    if failed == 0:
        print(f"All {len(cases) + len(sparse_cases)} tests passed.")
        return 0
    print(f"{failed} test(s) failed.")
    return 1


if __name__ == "__main__":
    import sys
    sys.exit(_self_test())
