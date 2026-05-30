## Core Lexicon and Lexicon Construction

### 1. Purpose

The Core Lexicon is SGF’s shared grounding substrate for common meaning. It is not merely a dictionary. It is a graph of sense‑level entries with stable identifiers and structure so independent systems can point to the same meanings, detect gaps, and refuse to fabricate grounding.

The Core Lexicon occupies the ontological plane in the four‑plane architecture (ontological, event, framing, claims). It describes types and their composition only, not events, rhetorical stance, or claims. Event structure lives in Synapses on the event plane; framing and epistemic status live in Frames and Claims on higher planes.

The Core Lexicon provides:

- Sense‑level `canonical_id`s as machine‑readable addresses for meaning  
- A directed acyclic `IS_A` graph over types  
- A finite Prime Registry and an explicit `grounding_status` field  
- A reproducible release artifact (`lexicon_release`) identified by hash and signature.

Non‑core lexicons extend this substrate for domains, organizations, corpora, documents, missions, and products.

***

### 2. Data model

#### 2.1 `lexicon_release`

A `lexicon_release` represents one published Core or extension lexicon release.

Minimum fields:

- `lexicon_id`  
- `lexicon_scope` (for example, `core`, `lexmed`, `lexfin`, `acmecorpus2025`)  
- `version`  
- `source_basis` (dictionary snapshot or other source identifier)  
- `language_coverage`  
- `issued_at`  
- `issuer`  
- `uri`  
- `content_hash`  
- `signature`.

`content_hash` is a cryptographic hash over a canonical export of the lexicon content. It is used for integrity, reproducibility, and signatures. Canonical rule:

- canonical JSON  
- sort keys lexicographically  
- remove insignificant whitespace  
- UTF‑8 encode  
- SHA‑256  
- lowercase hex with `sha256:` prefix.

The hash covers content, not URL.

Each Core Lexicon release MUST be accompanied by a machine‑readable Core profile that identifies at minimum:

- the dictionary snapshot or source basis,  
- the Prime Registry version,  
- the Core Grounding Patch Set version, and  
- any declared embedding / fingerprint profiles used during bootstrapping.

Two independent implementations that use the same Core profile and adhere to the Core Lexicon invariants MUST be able to reconstruct the same Core release and match its `content_hash`.

#### 2.2 `namespace`

A `namespace` identifies the authority and version context for canonical IDs.

Recommended fields:

- `namespace_id`  
- `namespace_kind` (for example, `core`, `domain`, `business`, `corpus`, `document`)  
- `owner_or_issuer`  
- `version`  
- `uri`  
- `content_hash`.

Namespaces SHOULD be used internally as structured fields. Systems SHOULD NOT rely on parsing dotted strings when structured fields are available.

#### 2.3 `lexicon_entry`

A `lexicon_entry` represents a **sense‑level** entry, not merely a surface word. One lemma with multiple senses corresponds to multiple `lexicon_entry` records.

Required fields:

- `lexicon_entry_id` (opaque unique record ID, such as UUID or ULID)  
- `canonical_id`  
- `lexicon_id`  
- `namespace_id`  
- `language_tag` (BCP‑47, for example `en`, `en-US`, `es`)  
- `lemma`  
- `part_of_speech`  
- `microgloss`  
- `lexicon_scope`  
- `grounding_status`.

Recommended fields:

- `normalized_lemma`  
- `source_sense_id` / `sense_index`  
- `gloss`  
- `example_sentences`  
- `synonyms`  
- `source_refs`  
- `content_fingerprint`  
- `isa_core`  
- `isa_chain`  
- `authority_frame_id`  
- `content_hash`  
- `status`  
- `created_at`  
- `updated_at`.

`language_tag` SHOULD use BCP‑47. `lexicon_entry_id` is the durable record handle. `canonical_id` is the semantic address.

`microgloss` is a terse disambiguator for lemma‑mates. It MUST use lowercase `snake_case`. It MUST NOT use `IS_A` as a bare token.

A `lexicon_entry` MAY carry descriptive literals such as `gloss`, `example_sentences`, hashes, timestamps, and source references, but MUST NOT hide structurally meaningful concepts in generic property fields. Any datum that should be linkable, joinable, or governable (for example, lungs, dwelling, jurisdiction, disease category) MUST be represented as a node in `lexicon_entry` / `lexicon_relation` or as a participant in a Synapse, not as an untyped value inside the entry. Instance‑level magnitudes (such as a particular person’s current weight) do not belong on the ontological plane; they are modeled on the instance plane via attribute Synapses and value nodes.

#### 2.4 `canonical_id`

A `canonical_id` identifies a sense‑level `lexicon_entry`. It is a structured identifier, not just a printable string.

Recommended logical fields:

- `language_tag`  
- `lemma`  
- `microgloss`  
- `part_of_speech`  
- `namespace_id` or `lexicon_scope`.

The printable form MAY use a dotted string such as:

- `en.bank.financial_business.noun`  
- `en.calico_cat.domestic_cat_breed.noun`.

If dots are used, fields containing dots MUST be escaped or encoded. HFF MUST carry the structured fields as well as any printable `canonical_id` string.

The important point is that machines share a stable address for meaning. A `canonical_id` is a machine interlingua: it lets different systems point to the same sense‑level meaning, even across languages or organizations.

#### 2.5 `lexicon_relation`

Lexical relations are modeled as separate records, not as fields on `lexicon_entry`.

Recommended fields:

- `lexicon_relation_id`  
- `source_lexicon_entry_id`  
- `relation_type`  
- `target_lexicon_entry_id`  
- `proof_trace_id`  
- `confidence`  
- `source_basis`.

Starter `relation_type` values (ALLCAPS tokens):

- `IS_A`  
- `HAS_PART`  
- `PART_OF`  
- `SYNONYM_OF`  
- `ANTONYM_OF`  
- `RELATED_TO`  
- `INSTANCE_OF`  
- `DERIVED_FROM`  
- `TRANSLATION_OF`  
- `NEAR_EQUIVALENT_TO`.

`IS_A` is the primary taxonomic relation and is always type‑to‑type on the Lexicon plane. `HAS_PART` and `PART_OF` express type‑level composition. These three relation types form the ontological backbone of the Core Lexicon and are the only relations considered by Core decompression and grounding procedures. Synonymy and other lateral relations (for example, `SYNONYM_OF`, `TRANSLATION_OF`) MAY be stored for convenience, but MUST NOT be followed as `IS_A` or used to bypass the backbone.

#### 2.6 `embedding_record` and `content_fingerprint_record`

Embeddings:

- `embedding_id`  
- `lexicon_entry_id`  
- `embedding_model`  
- `embedding_model_version`  
- `embedding_profile`  
- `vector_ref`  
- `created_at`.

Content fingerprint:

- `content_fingerprint_id`  
- `lexicon_entry_id`  
- `fingerprint_value`  
- `fingerprint_profile`  
- `embedding_id`  
- `created_at`.

`content_hash` proves bytes/content have not changed. `content_fingerprint` is a semantic signature derived from an embedding or similar representation. Fingerprints support semantic matching, lookup, hydration, and candidate retrieval. They do **not** prove identity. Fingerprints are comparable only when parties use the same `fingerprint_profile` (model, dimensionality, projection, seed, encoding, version).

#### 2.7 Source attribution and media

Lexicon entries SHOULD preserve source attribution for open lexicon builds:

- `source_project`  
- `source_page`  
- `source_revision_id`  
- `source_url`  
- `license`  
- `extracted_at`.

Media assets and perceptual grounding objects MAY be attached to `lexicon_entry` records, but are not required for minimal conformance.

#### 2.8 `lexicon_synapse_link`

A `lexicon_synapse_link` record associates a `lexicon_entry` with one or more Synapses on the event plane. It connects types on the ontological plane to default scripts, canonical facts, and typical scenarios without embedding event structure into the Lexicon.

Recommended fields:

- `lexicon_synapse_link_id`  
- `lexicon_entry_id`  
- `synapse_id`  
- `link_role` (for example, `DEFAULT_SCRIPT`, `DESCRIPTIVE_FACT`, `TYPICAL_SCENARIO`, `USAGE_SCRIPT`)  
- `source_basis`  
- `created_at`.

`link_role` declares why the Synapse is attached. Behavior and usage patterns are modeled entirely in Synapses; `lexicon_synapse_link` records are pointers from types to those scripts. The presence or absence of `lexicon_synapse_link` records does not affect Core Lexicon invariants over `IS_A`, `HAS_PART`, `PART_OF`, or `grounding_status`.

***

### 3. Core Lexicon invariants

The Core Lexicon is SGF’s engineered stopping rule for semantic regress. A conforming Core implementation MUST satisfy all of the following invariants.

#### 3.1 Sense‑level entries

- Each Core `lexicon_entry` represents **one sense of a lemma**, not just a surface word.  
- Each Core sense MUST have, at minimum: `canonical_id`, `lemma`, `part_of_speech`, `language_tag`, `microgloss`, `lexicon_scope`, and `grounding_status`.

#### 3.2 DAG structure over `IS_A`

- The primary taxonomic relation is `IS_A` between sense‑level types on the Lexicon plane.  
- The global `IS_A` graph over Core entries MUST be a **directed acyclic graph (DAG)**.  
- Implementations MUST reject or repair any `IS_A` edge that would introduce a cycle.  
- `HAS_PART` and `PART_OF` relations MUST NOT be used to encode taxonomic (`IS_A`) structure and MUST NOT introduce implicit cycles in the type hierarchy.

#### 3.3 Prime Registry and `grounding_status`

- Each Core profile defines a **Prime Registry**: a finite set of Tier‑0 `lexicon_entry` records that act as semantic bedrock for the `IS_A` DAG.  
- Each Core entry MUST carry `grounding_status` with at least two values:
  - `GROUNDED`: the entry has at least one finite, acyclic `IS_A` path to one or more primes in the Prime Registry.  
  - `UNRESOLVED`: the pipeline could not construct such a path under the published recipe.
- Entries with `grounding_status = UNRESOLVED` MUST NOT be used as `IS_A` parents in the Core DAG.

This is the operational form of the Bedrock Stopping Rule: Core grounding stops when `IS_A` reaches the Prime Registry; when no such path exists, the system records explicit ignorance rather than fabricating structure.

#### 3.4 Core vs extension boundary

SGF separates lexicon space into:

- **Core Lexicon**: slow‑moving, versioned, compiled from an open dictionary snapshot plus a small patch set.  
- **Extension lexicons**: fast‑moving, scoped to domains, organizations, corpora, documents, missions, or products.

Rules:

- A Core Lexicon release is constructed from a declared dictionary snapshot, Prime Registry, Core Grounding Patch Set, and pipeline configuration.  
- In **Core build mode**, the builder MUST NOT invent new `.core` senses beyond what the recipe specifies. For each candidate sense from the snapshot, it MAY:
  - include it as `GROUNDED`,  
  - include it as `UNRESOLVED`, or  
  - exclude it from Core.  
- In **extension build mode**, new senses MUST live in non‑core scopes (for example, `lexmed`, `lexfin`, `acmecorpus2025`). Each new extension sense MUST either:
  - provide at least one `IS_A` bridge into a Core ancestor, or  
  - declare `grounding_status = UNRESOLVED`.  
- Extension build mode MUST NOT mutate a published Core release; it only references Core through `canonical_id` and `IS_A` links.

#### 3.5 Embeddings and content fingerprints are advisory

- Embeddings and `content_fingerprint` MAY be used to:
  - propose candidate parents,  
  - cluster similar senses,  
  - assist hydration, matching, and deduplication.  
- They MUST NOT be the **sole** basis for `IS_A` parent assignment or `grounding_status`.  
- Identity and grounding decisions MUST be justified by lexicon structure (`canonical_id`, `lexicon_relation`, manifests, source traces, proof) rather than vector similarity alone.

#### 3.6 Canonical `isa_chain` as projection

- Implementations MAY compute a canonical `isa_chain` for each grounded sense: a preferred `IS_A` path from that sense up to primes according to documented heuristics (for example, shortest path or preferred upper‑level parents).  
- `isa_chain` MUST be derived from the underlying DAG and MUST NOT introduce cycles or parent links that are not present in `IS_A`.  
- Reasoning engines MUST treat `IS_A` as the authoritative taxonomic structure. `isa_chain` is a convenience projection for serialization and late binding.

***

### 4. Core vs extension lexicons in SGF

- **Core Lexicon** entries typically use `lexicon_scope = core` and follow all invariants above. They function like a programming language standard: slow‑moving, public, reproducible.  
- **Extension lexicons** (domain, business, corpus, document, mission, product) use their own scopes and may:
  - mint new named entities and specialized terms,  
  - attach extra relations or media,  
  - package content as Knowledge Packs with their own `lexicon_release` and manifest.

Core Lexicon entries define types on the ontological plane. Extension lexicons may introduce new types and named entities, but MUST respect the same ontological constraints (sense‑level entries, `IS_A` DAG, `grounding_status`) and connect back to Core via `IS_A` bridges when possible.

Non‑core entries exported across trust boundaries SHOULD include an `IS_A` bridge to the nearest Core ancestor. If no reliable ancestor exists, unresolved grounding MUST be declared and, where applicable, accompanied by a GapReport.

Every HFF message that uses non‑core `canonical_id` values MUST ensure that the receiver can hydrate those IDs, either because the relevant lexicons are shared and known, or because a LexiconManifest is provided (inline or by signed reference) naming the lexicon scope, version, URI, hash, and signature.



