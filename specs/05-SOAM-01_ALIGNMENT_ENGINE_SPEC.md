SGF Design Pattern Specification
INTERNET-DRAFT                                             Expires: February 2027
File: 05-SOAM-01_ALIGNMENT_ENGINE_SPEC.md
Layer: ALIGNMENT
Status: Design Pattern Specification

       SOAM — Structural Ontology Alignment Method Specification
                         Version 1.0 — August 2026


                          Symbol Grounding Framework


1.  Introduction

    This document specifies SOAM (Structural Ontology Alignment Method),
    a design pattern for dictionary and ontology search that produces a
    verifiable verdict — MATCH or NO MATCH — rather than a similarity
    score.  SOAM is intended for use cases where the consequence of a
    wrong match is significant: procurement alignment, cross-lingual
    concept matching, RFP-to-proposal compliance verification, and
    safety-critical part identification.

    SOAM is a design pattern, not a protocol.  Implementers may adapt
    the pattern to their specific domain, latency budget, and tolerance
    for error.  The pattern has been found effective across a range of
    applications; the component selection and depth level are determined
    by the implementer's policy, not by the pattern itself.

    SOAM is distinguished from simpler approaches (cosine similarity
    alone, BM25, or LLM-only comparison) by three properties.  First,
    it defines multiple modes of search: Level 1 for speed, Level 2 for
    structural comparison, and Level 3 for recursive decomposition.
    The implementer selects the mode based on the consequence of being
    wrong.  Second, it provides a shared vocabulary — the profile
    string — so that two parties can communicate exactly which mode and
    which components were used, with zero ambiguity about the method.
    Third, it is a design pattern, not a fixed algorithm: the
    implementer chooses which components to activate, at what depth to
    decompose, and what confidence to require.  These three properties
    together make SOAM a framework for alignment rather than a single
    technique.

    SOAM operates after source text has been parsed into concept
    definitions by GLEAN [GLEAN] and before alignment results are
    transported via HFF [HFF] or evaluated by Omega [OMEGA].  It
    consumes concept definitions from the SGF Core schema [SGF-CORE]
    and the layered lexicon stack [LEXICON].  Fingerprint computation
    follows the Exact Profile Contract [EXACT-PROFILE].  This document
    does not re-specify those components.

    The three depth levels (L1, L2, L3) correspond to those described
    in the SGF white paper [WHITEPAPER].  This document provides the
    implementation specification; the white paper provides the
    motivation.

    The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
    "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY",
    and "OPTIONAL" in this document are to be interpreted as described
    in BCP 14 [RFC2119] [RFC8174] when, and only when, they are used
    in all capitals, as shown here.


2.  Conformance

    A SOAM implementation is expected to support at least one depth
    level (L1, L2, or L3), at least one decider mechanism (threshold-
    based or LLM-based), and at least one method for restricting the
    candidate set (lemma filtering, POS filtering, or embedding pre-
    filtering).

    Implementations that meet these criteria may describe their work
    as using SOAM.  Implementations that deviate from the recognized
    component set (Section 4) SHOULD document the deviation in the
    profile string (Section 6).

    There is no certification authority for SOAM and no conformance
    test suite.  Conformance is self-declared using the profile
    vocabulary.


3.  Depth Levels

    SOAM defines three depth levels for concept comparison.  Higher
    levels provide higher confidence at higher computational cost.
    The level used is a policy decision of the implementation, not a
    property of the pattern.

    The three levels describe the depth of comparison, not the
    mechanism.  An implementation at any level MAY use any subset of
    the matching components listed in Section 4.  For example, an L1
    implementation MAY use cross-attention reranking, and an L3
    implementation MAY skip operator gating.

    3.1  L1: Embedding-Only Search

    L1 uses embedding similarity as the sole comparison mechanism.
    The query and each dictionary entry are represented as embedding
    vectors.  The top N candidates are selected by cosine similarity.

    Optional filters MAY be applied before or after the embedding
    comparison: lemma matching, part-of-speech filtering, BM25
    lexical boost.  Optional reranking MAY be applied using a
    cross-attention model.

    The top N candidates are presented to the decider, which selects
    the best match or returns no match.

    L1 is appropriate when the cost of a wrong match is low and the
    primary requirement is speed.

    3.2  L2: Ontology Comparison

    L2 compares ontological features of the query and each candidate
    that passes the L1 pre-filter.  The following features are
    compared:

      IS_A:          The taxonomic parent sets.  A pass requires at
                     least one overlapping parent.
      HAS_PART:      The component sets.  A pass requires at least one
                     overlapping component.
      HAS_ATTRIBUTE: The property sets.  Qualitative attributes are
                     compared by embedding; quantitative attributes
                     numerically (see Section 5).
      VerbHub:       The verb canonical ID for the concept's primary
                     function.

    Each feature comparison uses the same embedding mechanism as L1.
    The decider combines the feature-level results with the L1 score.

    L2 is appropriate for moderate to high consequence use cases
    where embedding similarity alone is insufficient.

    3.3  L3: Recursive Decomposition

    L3 extends L2 by decomposing each ontological feature one or more
    additional levels.  For each IS_A parent, HAS_PART component, or
    HAS_ATTRIBUTE value that is itself a concept with ontological
    features, the implementation MAY retrieve its definition and
    compare those features recursively.

    Recursion continues until one of the following conditions is met:

      - The decider determines that confidence is sufficient.
      - The feature cannot be further decomposed (no ontological
        features defined).
      - The maximum configured depth is reached.
      - The comparison reaches a Prime Registry entry or physical
        constant, at which point comparison is exact.

    L3 is appropriate for high to critical consequence use cases:
    safety-critical parts, regulatory compliance, legal decisions.

    The three-level naming is a convention.  Implementations MAY
    decompose to depth N and describe the alignment using the
    profile vocabulary with a depth parameter (Section 6).


4.  Matching Components

    All components listed in this section are OPTIONAL.  An
    implementation MAY use any subset.  The components used in a
    particular alignment are recorded in the profile string
    (Section 6).

    4.1  Lemma Matching

      lemma-strict:    Candidates with an exact lemma match are
                       preferred; candidates without a lemma match
                       are excluded.
      lemma-relaxed:   Lemma match adds a boost to the embedding
                       score; candidates with different lemmas are
                       retained.
      lemma-free:      Lemma is not considered.

    4.2  Part-of-Speech Filtering

      pos-filtered:    Only candidates with the same part of speech
                       are retained.
      pos-free:        Part of speech is not considered.

    4.3  Embedding Pre-Filter

    REQUIRED for all levels.  The embedding pre-filter computes
    cosine similarity between the query embedding and each candidate
    embedding.  The top K candidates (K configurable) are retained
    for further processing.

    Implementations MAY precompute content fingerprints (86-character
    Base64URL LSH, computed per [EXACT-PROFILE]) at ingestion time.
    At query time, fingerprint Hamming distance MAY replace or precede
    full embedding cosine comparison for fast candidate rejection.
    Fingerprint matching is less accurate than full cosine comparison
    and is RECOMMENDED only for low-consequence queries or as a
    first-pass filter.  Because fingerprints are derived from the same
    embedding, they cannot produce a match that cosine would miss;
    they are a speed optimization, not a matching improvement.

    4.4  BM25 Lexical Boost

    An OPTIONAL component.  BM25 similarity is computed between the
    query text and the candidate's canonical description text.  The
    BM25 score is combined with the embedding cosine score using a
    weighted sum.  The weight is configurable.

    4.5  Cross-Attention Reranker

    An OPTIONAL component.  A trained cross-encoder model reranks
    the top K candidates from the embedding pre-filter.  The cross-
    encoder processes the query and each candidate as a paired input
    and produces a relevance score.

    4.6  Decider

    The decider selects the best match from the candidate set or
    returns no match.  Three decider types are defined:

      threshold-decide:  The candidate with the highest combined
                         score is accepted if the score exceeds a
                         configurable threshold.  Otherwise, no
                         match is returned.

      llm-decide:        The top N candidates (N configurable) are
                         presented to an LLM with a structured
                         prompt.  The LLM selects the best match or
                         returns NONE.  A confidence category
                         (Section 5) is assigned.

      human-review:      The top N candidates are presented to a
                         human operator, who selects the best match
                         or rejects all candidates.  The human
                         decision is recorded with the same profile
                         string and confidence category as an
                         automated decision, preserving auditability.

    The llm-decide decider is RECOMMENDED when the cost of a wrong
    match is high and an LLM is available.  The threshold-decide
    decider is appropriate when latency is critical.  The
    human-review decider is appropriate when automated judgment is
    insufficient or when regulation requires human sign-off.

    4.7  Boolean Operators

    An OPTIONAL component.  Slot fillers in the concept schema MAY
    be logical expressions using AND, OR, XOR, and NOT operators.
    When operator gating is enabled, the implementation evaluates
    these expressions:

      AND:  All child expressions must match.
      OR:   At least one child expression must match.
      XOR:  Exactly one child expression must match.
      NOT:  The inner expression must not match.

    When operator gating is disabled, slot fillers are treated as
    an implicit AND of all atomic references.

    Component options: operator-gated, ungated.

    4.8  Bidirectional Checking

    An OPTIONAL component.  When bidirectional checking is enabled,
    each slot is compared in both directions: the candidate must
    satisfy the query, AND the query must satisfy the candidate.
    This prevents asymmetric alignments where one concept is a
    superset of the other.

    Implementations SHOULD document which document is authoritative
    (e.g., an RFP vs. a proposal) and SHOULD NOT require the
    authority document to satisfy the response document on any
    slot.  Authority asymmetry is a policy decision, not a property
    of the alignment engine.

    Component options: bidirectional, unidirectional.

    4.9  Grounding Check

    An OPTIONAL component.  The grounding check verifies that the
    candidate's concept definition traces to a shared reference
    lexicon.  Three levels of grounding are defined:

      grounding-none:   No traceability requirement.
      grounding-core:   All slot fillers MUST trace to the Core
                        Lexicon (L0) via IS_A edges.
      grounding-prime:  All slot fillers MUST trace to the Core
                        Lexicon or to the Prime Registry (NSM primes
                        or physical constants).

    Candidates that fail the grounding check are excluded from
    consideration when the component is enabled.  The grounding
    check is RECOMMENDED for L2 and L3 alignments where cross-party
    verifiability is required.


5.  Confidence Categories

    The decider assigns each alignment to one of six confidence
    categories.  The implementation MAY set a minimum acceptable
    category per query or per deployment.

      NONE:         No candidate matches.  The decider determined
                    that no candidate is satisfactory.

      WEAK:         A candidate was found but semantic distance is
                    significant.  Not suitable for decisions with
                    real consequences.

      MODERATE:     A candidate was found with moderate similarity.
                    Suitable for browsing and exploration.

      STRONG:       A candidate was found with high confidence.
                    Suitable for most procurement decisions.

      VERY STRONG:  A candidate was found with very high confidence.
                    Suitable for important decisions.

      EXACT:        The candidate matches on all checked dimensions
                    at the selected depth.  Suitable for safety-
                    critical, regulatory, and legal decisions.

    The categories are ordinal.  The mapping from scores and
    structural comparison results to categories is implementation-
    defined and SHOULD be documented.


6.  Profile Vocabulary

    6.1  Purpose

    The profile vocabulary permits any SOAM-based alignment to be
    described in a short, precise string.  Two parties that share
    the vocabulary can communicate how a match was performed without
    requiring knowledge of each other's implementation details.

    The profile string is used in Bridge Map entries, ProofTrace
    headers, and cross-party exchange.  It enables a receiving party
    to determine whether a received alignment meets their own
    requirements.

    6.2  Syntax

      SOAM-v{VERSION} {LEVEL}, {COMPONENT_OPTIONS},
           min-confidence-{CATEGORY}

    The version number is incremented when the recognized component
    set changes.  This document defines version 1.

    6.3  Recognized Options

    The following component options are recognized:

      Lemma:        lemma-strict, lemma-relaxed, lemma-free
      POS:          pos-filtered, pos-free
      Pre-filter:   cosine, hybrid-bm25, cross-attention
      Decider:      threshold-decide, llm-decide, human-review
      Operators:    operator-gated, ungated
      Bidirectional: bidirectional, unidirectional
      Grounding:    grounding-none, grounding-core, grounding-prime

    Additional implementation-specific components MAY be added.
    Non-standard options SHOULD be prefixed with +custom().

    6.4  Examples

      SOAM-v1 L1, llm-decide, min-confidence-MODERATE
        L1 with LLM-based decider; accepts moderate or better.

      SOAM-v1 L2, lemma-relaxed, cross-attention, llm-decide,
           bidirectional, min-confidence-STRONG
        L2 with lemma boost, cross-attention reranking, LLM
        decider, bidirectional checking; accepts strong or better.

      SOAM-v1 L3, lemma-strict, operator-gated, llm-decide,
           min-confidence-EXACT
        L3 with strict lemma, operator gating, LLM decider;
        requires exact match.

      SOAM-v1 L1, threshold-decide, min-confidence-WEAK
        L1 with threshold-based decider; accepts weak.  Fast but
        low precision.

      SOAM-v1 L3, llm-decide, bidirectional, min-confidence-
           VERY_STRONG, +custom(authority-asymmetric)
        L3 with LLM decider, bidirectional checking, very strong
        minimum, custom authority-asymmetry flag.


7.  Concept Schema

    SOAM operates on concepts defined using the SGF Core schema
    [SGF-CORE].  A concept is a hub-and-spoke structure: a VerbHub
    at the center carrying the concept's primary function, with up
    to 18 role-bound slots.

      VerbHub:      Canonical verb ID for the concept's primary
                    function.

      Y-axis (object logic):
        IS_A:         Set of taxonomic parent concepts.
        HAS_PART:     Set of functional component concepts.

      X-axis (event logic), 15 semantic roles:
        HAS_AGENT:    Entity that initiates the event.
        HAS_PATIENT:  Entity that undergoes change.
        HAS_THEME:    Entity that is moved, located, or possessed.
        HAS_EXPERIENCER: Entity experiencing a state.
        HAS_RECIPIENT: Destination entity for possession change.
        HAS_BENEFICIARY: Entity for whose advantage the event
                        occurs.
        HAS_TIME:     Temporal coordinate or span.
        HAS_LOCATION: Spatial region or coordinate.
        HAS_SOURCE:   Origin state.
        HAS_DESTINATION: Endpoint state.
        HAS_MANNER:   Style or quality of execution.
        HAS_INSTRUMENT: Tool or intermediary.
        HAS_CAUSE:    Non-volitional trigger.
        HAS_REASON:   Motivational purpose.
        HAS_ATTRIBUTE:  Properties and constraint values.

      Constraint:
        HAS_CONSTRAINT: Quantitative restrictions.

    Any slot MAY be empty.  An empty slot in the query or the
    candidate imposes no matching requirement.  If a slot is
    populated in both, it MUST match for the alignment to succeed.

    Slot fillers MAY be logical expressions (AND, OR, XOR, NOT)
    or atomic references.  The default logical operator is AND.

    When decomposition encounters mathematical formulas or
    algorithmic constraints, the Systemic Pointer mechanism
    (defined in [SGF-CORE]) halts recursion and routes execution
    to an isolated sandbox.  The sandbox validates structural
    inputs and outputs without further semantic decomposition.


8.  Worked Examples

    8.1  Example 1: Cross-Lingual Concept Matching

    Query: en.wagon.vehicle.noun — "A four-wheeled vehicle for
    transporting goods, typically pulled by horses."

    Target: German dictionary containing de.Pferdewagen,
    de.Waggon, de.Karren.

    Profile: SOAM-v1 L1, lemma-relaxed, llm-decide,
             min-confidence-MODERATE

    Process:
      1. Embedding pre-filter on the full German lexicon.  Top
         three candidates by cosine similarity: Pferdewagen
         (0.87), Waggon (0.83), Karren (0.79).
      2. LLM decider determines: "Wagon and Pferdewagen both
         describe a horse-drawn vehicle for transporting goods.
         Waggon is a railway car.  Karren is a handcart."
      3. Result: MATCH.  Confidence: STRONG.

    8.2  Example 2: Automotive Part Identification

    Query: "Brake rotor for a 1997 Toyota Tacoma, front passenger
    side, with ABS ring."

    Target: Parts catalog with 10,000 SKUs.

    Profile: SOAM-v1 L2, lemma-strict, cross-attention, llm-decide,
             bidirectional, min-confidence-VERY_STRONG

    Process:
      1. Lemma filter: retain entries containing "brake rotor" or
         "rotor".
      2. POS filter: retain only nouns.
      3. Embedding pre-filter: retain top 20 candidates.
      4. Cross-attention reranker: narrow to top 5.
      5. L2 ontology comparison for each candidate:
         - IS_A: candidate and query share parent
           "brake_rotor".  PASS.
         - HAS_PART: both share "ABS_ring".  PASS.
         - HAS_ATTRIBUTE: vehicle matches
           "1997_Toyota_Tacoma"; position matches
           "front_passenger".  PASS.
         - Bidirectional check: candidate satisfies query AND
           query satisfies candidate.  PASS.
      6. LLM decider: one candidate passes all checks.
      7. Result: MATCH — SKU verified.  Confidence: VERY STRONG.

    8.3  Example 3: Safety-Critical Part Verification

    Scenario from the SGF white paper: a procurement officer
    searches a catalog for a "flight-qualified torque driver,
    extreme environment rated — vacuum, zero gravity, arctic,
    underwater."  The catalog contains a "hand-held screwdriver,
    atmospheric use only."

    Profile: SOAM-v1 L3, lemma-relaxed, cross-attention, llm-decide,
             bidirectional, operator-gated, grounding-core,
             min-confidence-EXACT

    Process:
      1. Embedding pre-filter: top 10 candidates.
      2. Cross-attention reranker: top 3 candidates.
      3. L3 recursive decomposition for each candidate:
         - IS_A: query IS_A "precision_torque_tool"; candidate
           IS_A "handheld_screwdriver".  A common parent exists
           at depth 2 ("driver_tool"), but the distinct parents
           at depth 1 show functional divergence.
         - HAS_PART: query specifies "vacuum-rated_seal",
           "temperature_insulation".  Candidate does not include
           these components.
         - HAS_ATTRIBUTE: query specifies vacuum, zero-g, arctic,
           and underwater ratings; candidate specifies
           "atmospheric_only".
         - Bidirectional check: candidate fails to satisfy query
           on HAS_PART and HAS_ATTRIBUTE.
         - Operator gating: expression is "vacuum AND zero gravity
           AND arctic AND underwater".  Candidate satisfies zero
           of four conditions.
      4. LLM decider: no candidate passes all checks.
      5. Result: NO MATCH.  GapReport: "IS_A mismatch at depth 1.
         The offered part is a handheld screwdriver, not a
         precision torque tool.  HAS_ATTRIBUTE mismatch:
         candidate is atmospheric-only; query requires vacuum,
         zero-g, arctic, and underwater ratings.  Consider
         adding a vacuum-rated torque driver to the catalog."

    8.4  Example 4: RFP-to-Proposal Compliance

    An RFP with 200 requirements is compared against a 40-page
    proposal.  Each requirement and each offer is parsed into
    the 18-slot schema.  SOAM aligns them requirement by
    requirement.

    Profile: SOAM-v1 L2, llm-decide, bidirectional, operator-gated,
             min-confidence-STRONG, +custom(authority-asymmetric)

    A representative requirement-offer pair:

      Requirement (RFP, authoritative):
        VerbHub: STAFF
        HAS_AGENT: kitchen_manager
        HAS_CONSTRAINT: count >= 3 during peak hours
        NormativeFrame: DUTY (shall)

      Offer (proposal):
        VerbHub: STAFF
        HAS_AGENT: kitchen_manager
        HAS_CONSTRAINT: count = 2 during peak hours
        NormativeFrame: INTENTION (will)

      Comparison at L2:
        VerbHub:  STAFF = STAFF.                    PASS
        HAS_AGENT: kitchen_manager = kitchen_manager. PASS
        HAS_CONSTRAINT: required >= 3; offered = 2.
                    2 < 3.                          FAIL
        Modality (frame): DUTY vs. INTENTION.       FAIL

      Result: NO MATCH for this requirement.  GapReport:
        "Constraint mismatch: RFP requires >= 3 staff
        during peak hours; proposal offers 2.  Modality
        mismatch: 'shall' (obligation) vs. 'will'
        (intention).  Suggested corrective action: commit
        to staffing with 3 or more persons with binding
        obligation, or provide justification for the lower
        number."

    Aggregate output:
      - Passed requirements: each with a ProofTrace.
      - Failed requirements: each with a GapReport naming the
        failing slot, required value, offered value, and
        corrective action.
      - Overall verdict: ACCEPT, CONDITIONAL ACCEPT, or REJECT.

    This example demonstrates that SOAM scales from single-concept
    matching (Examples 1-3) to full-document alignment.  The
    engine is identical; the scale differs.


9.  Policy Parameters

    The following parameters are configurable by the implementation.
    The pattern does not prescribe default values.

      Depth level: L1, L2, L3, or Ln (arbitrary N).
      Minimum confidence category: NONE through EXACT.
      Lemma matching mode: strict, relaxed, or free.
      POS filtering: enabled or disabled.
      Decider type: threshold-based, LLM-based, or human-review.
      Operator gating: enabled or disabled.
      Bidirectional checking: enabled or disabled.
      Grounding requirement: none, core, or prime.
      Tolerance for mismatched or missing slots.
      Recursive decomposition depth.
      Ontological features to compare (subset of the schema).

    The system reports what comparison was performed and at what
    confidence.  The implementation sets the acceptance bar.


10. Security Considerations

    10.1  LLM-Based Decider Input Integrity

    When using an LLM-based decider, the LLM receives concept
    definitions as structured inputs (slot fillers, canonical IDs,
    embedding scores).  Raw text from the query or the dictionary
    SHOULD NOT be passed directly to the LLM without validation.
    Concept definitions SHOULD be parsed and validated before
    presentation to the LLM.

    10.2  Content Fingerprint Privacy

    The 86-character content fingerprint (defined in
    [EXACT-PROFILE]) reveals semantic neighborhood information.
    An adversary with access to a set of fingerprints MAY be able
    to match a fingerprint to a known concept type.  For privacy-
    sensitive deployments, the fingerprint MAY be combined with a
    commitment scheme, or the grounding check MAY replace the
    fingerprint pre-filter.

    10.3  Cross-Party Profile Trust

    When a party receives an alignment described by a profile
    string, they SHOULD verify that the profile's minimum
    confidence meets their own requirements.  A receiving party
    MAY reject alignments whose profile indicates lower rigor
    than required and re-verify at a higher level.


11. IANA Considerations

    This document has no actions for IANA.


12. References

    12.1  Normative References

      [SGF-CORE]         Stakelum, J., "SGF Core Specification
                         v1.0", Symbol Grounding Framework, 2026.

      [LEXICON]          Stakelum, J., "The SGF Lexicon
                         Specification", Symbol Grounding
                         Framework, 2026.

      [EXACT-PROFILE]    Stakelum, J., "Exact Profile Contract
                         Specification", Symbol Grounding
                         Framework, 2026.

      [RFC2119]          Bradner, S., "Key words for use in RFCs
                         to Indicate Requirement Levels", BCP 14,
                         RFC 2119, DOI 10.17487/RFC2119, March
                         1997.

      [RFC8174]          Leiba, B., "Ambiguity of Uppercase vs.
                         Lowercase in RFC 2119 Key Words", BCP 14,
                         RFC 8174, DOI 10.17487/RFC8174, May 2017.

    12.2  Informative References

      [WHITEPAPER]       Stakelum, J., "SGF: The Symbol Grounding
                         Framework — A White Paper", 2026.

      [GLEAN]            Stakelum, J., "GLEAN — Prose-to-Graph
                         Compiler Specification", Symbol Grounding
                         Framework, 2026.

      [HFF]              Stakelum, J., "HFF — Honest Fact
                         Forwarding Specification", Symbol
                         Grounding Framework, 2026.

      [AFP]              Stakelum, J., "AFP — Act Framing
                         Protocol Specification", Symbol Grounding
                         Framework, 2026.

      [OMEGA]            Stakelum, J., "Omega — The Governance
                         Language Specification", Symbol Grounding
                         Framework, 2026.


Appendix A: Confidence Quick Reference

  Category      Meaning
  NONE          No match found.
  WEAK          Not suitable for decisions with consequences.
  MODERATE      Suitable for browsing and exploration.
  STRONG        Suitable for most procurement.
  VERY STRONG   Suitable for important decisions.
  EXACT         Suitable for safety-critical, regulatory, legal.

Appendix B: Profile Component Options

  Lemma         lemma-strict | lemma-relaxed | lemma-free
  POS           pos-filtered | pos-free
  Pre-filter    cosine | hybrid-bm25 | cross-attention
  Decider       threshold-decide | llm-decide | human-review
  Operators     operator-gated | ungated
  Bidirectional bidirectional | unidirectional
  Grounding     grounding-none | grounding-core | grounding-prime


Author's Address

   James Lee Stakelum
   The Symbol Grounding Company
   Calhoun, Louisiana
   Email: JamesLeeStakelum@Proton.me

   Full SGF specifications and reference code:
   https://github.com/SymbolGroundingFramework/SGF-manifest
