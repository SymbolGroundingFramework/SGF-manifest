# Knowledge Pack Specification v1.0 Final Candidate

## Scope

Knowledge Packs are versioned, signed bundles of SGF-compatible knowledge and/or lexicons.

Examples:

```text
Core Lexicon release
industry lexicon
Louisiana law pack
New Orleans municipal code pack
Wikipedia-derived factual reference pack
company corpus pack
common-sense physics pack
```

## Required package fields

```text
knowledge_pack_id
version
issuer
issued_at
source_class
content_hash
signature
sgf_core_version
```

Recommended fields:

```text
description
jurisdiction
authority_tier
epistemic_default
publisher_trust_model
recommended_trust_lens
known_limitations
license
dependencies
lexicon_manifest
```

## Source classes

```text
FACTUAL_REFERENCE
LEGAL_AUTHORITY
REGULATORY_AUTHORITY
SCIENTIFIC_LITERATURE
TESTIMONY_RECORD
OPINION_EDITORIAL
PHILOSOPHICAL_SYSTEM
POLICY_POSITION
SIMULATION_OUTPUT
FICTIONAL_WORLD
MIXED_CORPUS
```

## Import rule

Do not merge pack claims into local truth without preserving source class, provenance, authority, and recommended TrustLens.

## Package content

May contain:

```text
synapses
synapse_groups
links
frames
source_documents
proof_traces
lexicon_entries
gap_reports
conformance_report
```
