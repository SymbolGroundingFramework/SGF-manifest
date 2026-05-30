# GLEAN Process Specification v1.0 Final Candidate

## Scope

GLEAN turns a CleanTextBundle into SGF objects. It does not ingest raw text directly.

## Boundary

```text
RawSourceArtifact
-> Preprocessing / Scrubbing
-> CleanTextBundle
-> GLEAN
-> SGF objects
```

## Court Reporter rule

GLEAN records what can be grounded. It does not pretend to read minds, resolve all ambiguity, or capture total meaning.

If grounding fails, GLEAN emits GapReport, Ghost, retained source, or deferred review. It must not fabricate structure to hide uncertainty.

## Stage contract

```text
0. Preprocessing produces CleanTextBundle and SourceArtifactMap.
0.5. Create GLEAN RunPlan.
1. Register SourceDocument and SourceSpans.
2. Build DocumentStructureMap.
3. Build draft EntityMap / DocumentLexicon.
4. Classify discourse mode.
5. Build draft DiscourseMap, ReferenceMap, ArgumentMap, MethodFrame, or NarrativeArc as needed.
6. Build draft ClauseMap.
7. Refine EntityMap.
8. Refine DiscourseMap.
9. Generate ClaimCandidates.
10. Apply GranularityPolicy and create ExtractionDecisions.
11. Assemble Synapses.
12. Assemble SynapseLinks.
13. Assemble SynapseGroups and memberships.
14. Assemble SynapseGroupLinks.
15. Create or finalize GapReports and Ghosts.
16. Attach ProofTrace, ValidationState, TemporalFrame, ActFrame, PropositionalFrame, NormativeFrame, GeneralizationFrame, PerspectiveFrame, AuthorityFrame, LifecycleState, and ProfileContext as applicable.
17. Run consistency checks.
18. Run reconstruction or round-trip checks when required.
19. Prepare LexiconManifest and HFF export readiness.
```

## Hardening gates (recommended)

Implementations MAY apply the following hardening gates as part of a GLEAN profile:

- Coverage Gate: Measure out-of-vocabulary (OOV) rates against the Core Lexicon and halt or warn when a configured threshold is exceeded.
- Anchor Gate: Halt or flag windows where entities cannot be tethered to the Core Lexicon or an approved extension lexicon.
- Disambiguation Gate: Refine identifiers and microglosses until each entity is uniquely distinguishable within its population.
- Resolution Gate: Enforce the absence of bare pronouns in any Grounded Rewrite, ensuring every reference is resolved to a Canonical ID.

## Required outputs

At minimum:

```text
SourceDocument
SourceSpan
EntityMap
DocumentLexicon, if needed
ClaimCandidate records or equivalent trace
ExtractionDecision records or equivalent trace
Synapses
ProofTrace
GapReports, if any
```

Recommended outputs:

```text
DocumentStructureMap
DiscourseMap
ReferenceMap
ClauseMap
SynapseLinks
SynapseGroups
SynapseGroupLinks
Frame records
ValidationState
LexiconManifest
```

Profile-specific outputs may include domain frames, clinical profile outputs, legal profile outputs, or adapter-specific artifacts.

## Grounded Rewrite (optional profile)

In Grounded Rewrite profiles, GLEAN rewrites the input text into a canonicalized form before later extraction stages. At minimum:

- All resolved participants are replaced with their bracketed Canonical IDs.
- No bare pronouns remain in the rewrite; every reference is grounded to an entity in the EntityMap.
- The rewrite is treated as an intermediate artifact for downstream extraction, reducing hallucination risk by fixing the participant set and their roles in advance.

## Preprocessing requirements

Preprocessing must preserve source traceability. It may scrub the reading stream, but it must not silently destroy semantically relevant artifacts.

Required preprocessing outputs:

```text
CleanTextBundle
SourceArtifactMap
raw_to_clean_span_map
retained_artifact_inventory
content_hash_raw
content_hash_clean
redaction_log, if redacted
```

## Entity and lexicon requirements

GLEAN must identify terms that resolve to the Core Lexicon and terms requiring scoped lexicons.

Scoped lexicon layers:

```text
Core Lexicon
Domain / Industry Lexicon
Business / Organization Lexicon
Corpus Lexicon
Document Lexicon
```

Non-core terms exported over HFF require LexiconManifest entries or references to signed external lexicons.

## GapReport

GapReport should be emitted when:

```text
term cannot be grounded
role cannot be assigned
pronoun cannot be resolved
source span is missing
frame cannot be determined
confidence threshold fails
preprocessing artifact is missing
required lexicon bridge is absent
```

## Formal artifacts

Code, MIDI, equations, DNA, telemetry, Omega, structured logs, and similar sources require adapters. Preserve the artifact. Extract claim-bearing structures about the artifact.

## HFF readiness

Before export, GLEAN output should include:

```text
SGF version
Core Lexicon release
LexiconManifest
SourceDocument references
ProofTrace
content_hash
required frame records
GapReports
```
## Round-trip and conflict handling (recommended patterns)

The following patterns strengthen GLEAN without changing its core contract:

- Reconstruction Test: Implementations MAY perform a round-trip test by regenerating prose from stored Synapses and comparing it to the original text for propositional parity. Failures SHOULD trigger review.
- Rashomon Protocol: When conflicting but well-formed claims are extracted, GLEAN MUST preserve each as a separate Synapse with provenance, rather than reconciling or averaging at ingestion.
- Zero-Bit Test and Pivot Rule: Implementations MAY redirect vague, unbounded, or purely hedged statements into frames about epistemic state (for example, speaker uncertainty) instead of storing them as world facts.
