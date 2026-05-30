# SGF Core Specification v1.0 Final Candidate

## Scope

SGF Core defines the logical model for grounded claim-bearing structure. It does not define a database product, graph-query language, radio protocol, AI operating system, reasoning engine, or governance language.

## Core claim

SGF represents meaning as grounded, source-traceable, frame-aware claim-bearing structures.

It does not claim to capture all meaning. It captures what can be grounded, structured, sourced, traced, linked, validated, transported, and audited.

## Seven invariants

Every conforming implementation must preserve:

```text
identity
structure
provenance
time
state
authority
composition
```

## Synapse

```text
Synapse = one VerbHub + many role-bound Spokes
```

Required fields:

```text
synapse_id
hub
spokes
proof_trace_id
```

Recommended fields:

```text
temporal_frame_id
act_frame_id
propositional_frame_id
validation_state_id
authority_frame_id
lifecycle_state_id
profile_context_id
```

Profile-specific fields may be added through ExtensionManifest but must not redefine the Synapse grammar or the 15 core roles.

## VerbHub

Required fields:

```text
verb_canonical_id
actuality_status
```

Recommended fields:

```text
verb_content_fingerprint
verb_features
polarity
modality
voice
tense
aspect
mood
verb_grounding_trace_id
```

Tense, aspect, and mood are verb features. Implementations may project them for querying, but they do not create new primitive objects.

## Spoke

Required fields:

```text
role
target_type
target_ref
```

Allowed target types:

```text
LEXICON_ENTRY
DOCUMENT_ENTITY
BUSINESS_ENTITY
INSTANCE
TYPED_LITERAL
PLACEHOLDER
GHOST
SYNAPSE
SYNAPSE_GROUP
```

## Closed semantic role set

The SGF Core 1.0 role set is closed:

```text
HAS_AGENT
HAS_PATIENT
HAS_THEME
HAS_EXPERIENCER
HAS_RECIPIENT
HAS_BENEFICIARY
HAS_TIME
HAS_LOCATION
HAS_SOURCE
HAS_DESTINATION
HAS_MANNER
HAS_INSTRUMENT
HAS_CAUSE
HAS_REASON
HAS_ATTRIBUTE
```

Not core roles:

```text
HAS_STIMULUS
HAS_PURPOSE
HAS_RESULT
HAS_VALUE
HAS_WHOLE
HAS_CONDITION
HAS_PATH
HAS_PROVENANCE
```

These meanings are handled through existing roles, TypedLiteral, EvidenceBinding, SynapseLink, SynapseGroup, ProofTrace, SourceDocument, SourceSpan, ActFrame, PropositionalFrame, NormativeFrame, or GeneralizationFrame.

## Lexicon and Canonical IDs

SGF Core relies on a shared Lexicon for sense-level canonical IDs, ontological relations, and grounding status. The full Core Lexicon and Lexicon construction model, including `lexicon_entry`, `lexicon_relation`, canonical IDs, Prime Registry, Core/extension boundaries, and `grounding_status`, is defined in `LEXICON.md`.

Implementations MUST conform to the Lexicon specification when constructing, importing, or exporting Core or extension lexicons. All Synapse `verb_canonical_id` and Spoke `LEXICON_ENTRY` targets MUST resolve through a conforming Lexicon implementation.


## Source and proof objects

### SourceDocument

Recommended fields:

```text
source_document_id
source_type
title
uri_or_locator
publisher
author_or_originator
publication_or_filed_date
retrieved_at
jurisdiction
case_id_or_corpus_id
content_hash
license_or_access_policy
```

### SourceSpan

Recommended fields:

```text
source_span_id
source_document_id
span_type
char_start
char_end
page
section
quote
```

### ProofTrace

Required for any SGF object exported across trust boundaries.

Recommended fields:

```text
proof_trace_id
source_span_refs
extractor_id
extractor_version
run_id
derivation_type
validation_events
created_at
```

## Frame model

Frames describe what the fixed Synapse grammar is carrying. They do not add semantic roles.

### ActFrame

Used for communicative and coordination acts.

Recommended fields:

```text
act_type
illocution
payload_ref
sender_ref
recipient_ref_or_scope
deontic_type
actuality_status
authority_frame_id
proof_trace_id
temporal_frame_id
priority
deadline
ack_required
conversation_id
```

Act types:

```text
INFORM
ADVISE
REQUEST
QUERY
COMMAND
PROMISE
PROPOSE
ACCEPT
REFUSE
CANCEL
CONFIRM
ACK
ERROR
```

### PropositionalFrame

Used to classify claim-bearing content.

Recommended fields:

```text
propositional_kind
modal_force
epistemic_status
binding_force
deontic_type
enforcement_profile
lifecycle_state_id
scope
applies_when
anti_applies_when
source_document_id
perspective_frame_id
authority_frame_id
trust_lens_id
```

Starter propositional kinds:

```text
FACTUAL_CLAIM
TESTIMONY
ALLEGATION
DENIAL
OPINION
PHILOSOPHICAL_THESIS
HYPOTHESIS
ASSERTION
COMMAND_PAYLOAD
QUESTION_PAYLOAD
REQUEST_PAYLOAD
PROMISE_PAYLOAD
RULE
MOTIVATION
DIRECTIVE
CONSTRAINT
INVARIANT
CAPABILITY
GOVERNANCE_LAW
FICTIONAL_PROPOSITION
```

### NormativeFrame

Used when a proposition is behavior-shaping.

Recommended fields:

```text
normative_kind
binding_force
priority
scope
applies_when
anti_applies_when
preconditions
exceptions
override_policy
defeater_refs
conflict_group_id
risk_class
enforcement_profile
authority_frame_id
proof_trace_id
lifecycle_state_id
```

Normative kinds:

```text
ADVISORY
DEFAULT_RULE
DUTY
PROHIBITION
PERMISSION
EXCEPTION
OVERRIDE_RULE
META_RULE
CONSTRAINT
INVARIANT
GOVERNANCE_LAW
OMEGA_RULE
```

### GeneralizationFrame

Used when a specific claim, rule, example, or episode becomes a generalized proposition.

Recommended fields:

```text
generalization_id
source_refs
generalized_ref
abstraction_level
source_domain
target_domains
preserved_intent
changed_scope
analogical_basis
generalization_method
derivation_type
confidence
binding_force
applicability_tests
anti_examples
defeater_refs
human_review_required
proof_trace_id
```

Generalized rules are derived unless the source explicitly states the general rule.

### PerspectiveFrame

Recommended fields:

```text
perspective_frame_id
asserter_ref
asserter_role
point_of_view
stance
audience_or_addressee
institutional_context
legal_or_domain_context
```

### TrustLens

Query-time and reasoning-time filter.

Recommended fields:

```text
trust_lens_id
allowed_source_classes
allowed_epistemic_statuses
allowed_derivation_types
authority_tiers
minimum_confidence
include_opinion
include_testimony_as_world_fact
contradiction_policy
preferred_jurisdiction_or_authority
time_horizon
```

### ReasoningContext

Recommended fields:

```text
reasoning_context_id
query_or_task_id
trust_lens_id
domain_profile_id
corpus_scope
time_horizon
purpose
output_policy
```

## Composition: Synapse groups and links

Not all structure belongs inside a single Synapse. SGF Core represents larger thought units and cross-Synapse relations using SynapseGroup, SynapseGroupMembership, SynapseLink, and SynapseGroupLink.

Inside a Synapse, links are semantic roles (the 15 fixed theta roles). Between Synapses, links are either group membership or explicit link records with typed `link_type` values.

### SynapseGroup

`SynapseGroup` represents larger thought units: paragraphs, clauses, arguments, event clusters, timelines, definitions, method/result groups, contradiction groups, and narrative arcs.

Required fields:

```text
synapse_group_id
group_type      # e.g., ARGUMENT, EPISODE, PROCEDURE, CONTRADICTION_SET, NARRATIVE_ARC
members         # array of synapse_group_membership
proof_trace_id
```

`group_type` is a profile- or domain-specific label describing how the members function together. Core does not fix the `group_type` vocabulary.

### Starter group types (non-exhaustive)

`group_type` is a profile- or domain-specific label. SGF Core does not fix the vocabulary, but the following patterns are common:

- ARGUMENT: Synapses that function together as premises, conclusions, counterexamples, or explanatory steps in a line of reasoning.
- EPISODE: Synapses that describe a coherent event or scene (for example, a specific incident in a narrative or case file).
- PROCEDURE: Synapses representing steps in a method, workflow, or protocol.
- CONTRADICTION_SET: Synapses that assert incompatible claims about the same subject, preserved for audit and downstream TrustLens filtering.
- NARRATIVE_ARC: SynapseGroups that link episodes into a larger narrative or case progression.

### SynapseGroupMembership

`SynapseGroupMembership` attaches Synapses (and optionally nested groups) to a SynapseGroup.

Recommended fields:

```text
synapse_group_id
member_ref        # synapse_id or nested_synapse_group_id
membership_role   # e.g., PREMISE, CONCLUSION, STEP, COUNTEREXAMPLE, EXAMPLE, SUMMARY
sequence_index
```

`membership_role` is an optional label used within the group. It does not add new semantic roles to the Synapse itself.

### SynapseLink

`SynapseLink` connects one Synapse to another Synapse or SynapseGroup. It is not a Spoke role. SynapseLinks capture relations that do not belong inside the 15 core roles, such as causal, argumentative, or temporal relations between events or claims.

Recommended fields:

```text
synapse_link_id
source_synapse_id
link_type
target_kind        # SYNAPSE or SYNAPSE_GROUP
target_ref         # synapse_id or synapse_group_id
proof_trace_id
confidence
source_basis
```

Starter `link_type` values:

```text
CAUSES        # source event causes target event
CONDITIONS    # source is a necessary condition for target
MOTIVATES     # source is the motivation or reason for target, distinct from mechanical cause
SUPPORTS      # source supports the claim in target
CONTRADICTS   # source contradicts the claim in target
ELABORATES    # source adds detail or explanation to target
QUALIFIES     # source adds conditions or scope to target
PRECEDES      # source happens before target in world or narrative time
FOLLOWS       # source happens after target
CONTINUES     # source is a continuation or next step of target
```

Implementations MAY extend `link_type` in domain profiles but MUST NOT overload these core meanings.

### Recommended link patterns

`link_type` is also profile- or domain-specific, but SGF Core assumes certain recurring patterns:

- Argumentation:
  - SUPPORTS, CONTRADICTS, QUALIFIES, ELABORATES between Synapses in an ARGUMENT group.
- Temporal and narrative:
  - PRECEDES, FOLLOWS, CONTINUES between Synapses in an EPISODE or NARRATIVE_ARC.
- Causal and enabling:
  - CAUSES, CONDITIONS, ENABLES between event Synapses to represent causal and enabling relations.

Implementations MAY extend `link_type` vocabularies in profiles but MUST NOT overload the core meanings of starter link types.

### SynapseGroupLink

`SynapseGroupLink` connects one SynapseGroup to another. It is not a Spoke role. Typical uses include linking an EXAMPLE group to a RULE group, linking an EPISODE group to a SUMMARY group, or linking a PROCEDURE group to a RISK group.

Profile-specific fields may be added through ExtensionManifest but must not redefine the Synapse grammar or the 15 core roles.


## Identity

IdentityLinks are proof-bearing and reversible. `SAME_AS` is not destructive merge and is not transitive by default.

Recommended identity relations:

```text
SAME_AS
POSSIBLY_SAME_AS
DIFFERENT_FROM
INSTANCE_OF
ALIAS_OF
MENTIONS
```

AmbiguityCluster represents unresolved identity and must not silently unwrap to the top candidate.

## Planes

Implementations should distinguish:

```text
claim_plane
evidence_plane
identity_plane
lexicon_plane
reasoning_plane
```

Default fact queries search the claim plane. Audit and legal explanation queries may traverse evidence plane.

## Storage and query neutrality

SGF Core is backend-neutral. Implementations may use graph databases, relational databases, document stores, object stores, embedded databases, files, custom memory structures, or hybrids.

SGF does not prescribe Cypher, SQL, SPARQL, Gremlin, Kuzu query syntax, or any storage dialect.

Conformance is judged by logical behavior and export/import semantics, not backend choice.
