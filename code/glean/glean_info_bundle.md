# GLEAN — The Prose-to-Synapse Compiler

An info bundle. Thesis, claim chain, pipeline, integrity protocol, role catalog, FAQ. Written to clarify the architecture before any code is written.

---

## 1. Thesis

GLEAN compiles prose written in an open-vocabulary, open-grammar medium (natural language) into a structured representation that preserves the open vocabulary but locks the grammar to a closed, fixed inventory of fifteen semantic roles. The resulting structure is a graph of hub-and-spoke synapses, each grounded in canonical IDs from the SGF lexicon, each annotated with a frame that preserves rhetorical mode, point of view, modality, polarity, and hedging. The graph is queryable, composable, auditable, and federable across systems that have never met. The compiler is the missing piece between human-written knowledge and machine-reasoning systems that need to operate on it without inventing or losing what was said.

---

## 2. Claim chain

The argument nests. Each level answers the previous level's "so what."

### Surface claim

Prose can be mechanically compiled into structured knowledge.

### Depth 2

The compilation produces synapses, not triples. Each synapse is a verb-centered hub with up to fifteen typed spokes carrying semantic-role-tagged participants.

### Depth 3

The fifteen-role inventory is closed. Vocabulary at the hub and spokes is open. This split — open vocabulary, closed grammar — is what makes the resulting graph compilable, federable, and verifiable.

### Depth 4

Closed grammar is not a stylistic preference. It is the architectural property that makes type-checking, safety enforcement, and cross-system federation possible. Every prior knowledge graph architecture has left the relation vocabulary open, which is what makes those systems uncompilable at the structural level. SGF's closure of the role inventory at fifteen is the move that has been missing for forty years.

### Bedrock

The vocabulary-grammar cut is the architectural property every successful interoperable system has. Natural languages have it. Programming languages have it. Mathematics has it. RDF and its descendants do not. SGF puts the cut in the right place. GLEAN is the compiler that exploits the cut. Together they form a substrate that other systems can build on without negotiation.

---

## 3. The pipeline

GLEAN is not a single program. It is a pipeline of named stages, each deterministic where possible and LLM-augmented where deterministic methods fail. Each stage has a defined input, a defined output, and a defined integrity invariant.

```
PROSE
  -> 1. CLEAN              strip markup, footnotes, citations, tables, code
  -> 2. DEFLUFF            (optional) LLM removes prose carrying no facts
  -> 3. SEGMENT            sentence and clause boundaries via spaCy
  -> 4. ENTITY CENSUS      identify named and role entities, cluster aliases,
                           resolve pronouns by proximity
  -> 5. LEXICON LOOKUP     deterministic cosine search against SGF lexicon;
                           LLM rerank for ambiguous cases
  -> 6. MICRO-LEXICON MINT mint canonical IDs for entities not in the lexicon
  -> 7. CLAUSE-TO-SYNAPSE  spaCy-driven predicate-frame extraction;
                           LLM refinement for ambiguous role assignment
  -> 8. CHAIN RESOLUTION   resolve possessive chains into multi-synapse trees
  -> 9. FRAMING            LLM-driven layer: rhetorical mode, POV, hedging,
                           statement type, 41-dimension verb features
  -> 10. PERSIST           write synapses, frames, and entities to SQLite
  -> 11. GROUP             cluster synapses by shared entity, shared predicate,
                           or discourse cohesion
SYNAPSE STORE -> KNOWLEDGE GRAPH
```

Three properties hold across the pipeline:

**Deterministic-first.** Each stage attempts the deterministic path before escalating to an LLM. Most clauses, most entities, and most disambiguations resolve without an LLM call. The LLM is a refiner, not a generator.

**Provenance-preserving.** Every synapse carries source_doc_id, source_clause_id, and source_span back to the original prose. No fact enters the graph without a verifiable origin.

**Halt-or-quarantine on uncertainty.** When the deterministic path fails and the LLM is not confident, the pipeline marks the clause for human review rather than inventing structure. The Silence Rule: silence is structurally superior to confident nonsense.

---

## 4. The vocabulary-grammar cut

This is the architectural property that makes everything else work. The cut deserves its own section because it is what distinguishes SGF + GLEAN from every prior knowledge graph attempt.

### Two layers, two policies

Every interoperable system separates two layers:

| Layer | Required policy | Reason |
|---|---|---|
| Vocabulary | Open and extensible | The world keeps inventing things |
| Grammar | Closed and fixed | Compilation requires fixed structure |

Natural languages: English vocabulary has grown from 50,000 to over 1,000,000 words. English grammar (subject-verb-object, modifiers, tense rules) has not expanded. The grammar is closed and stable. The vocabulary is open and growing. Anyone can coin a word. Nobody can coin a new grammatical relation.

Programming languages: Python's identifier space is unbounded. Anyone can name anything. Python's grammar is a fixed BNF, frozen per version. The interpreter parses against the closed grammar; the identifiers fill the open vocabulary slots.

Mathematics: Anyone can introduce a new symbol with a definition. Nobody can introduce a new logical connective. The vocabulary of mathematical objects grows; the grammar of logical inference is fixed.

### Where prior knowledge graphs put the cut

RDF closed the structural shape — every fact is a triple of (subject, predicate, object). But it left the predicate slot open. Anyone can mint a new predicate. The result: predicate vocabulary explodes. Two RDF systems that have never met cannot share data without bilateral predicate-mapping negotiation. Integration cost is quadratic in the number of systems.

Property graphs (Neo4j, et al.) closed the node-edge structure. They left edge labels and property keys open. Same problem at the edge layer.

Schema.org closed the type system (a fixed catalog of types) but left properties extensible. The catalog grew from a few hundred to thousands of properties through community contributions, and federation across schema.org-using systems still requires bilateral schema reconciliation.

In every case, the architects closed the wrong layer. They closed the structural shell and left the relation vocabulary open. The relation vocabulary IS the grammar. Open grammars do not compile.

### Where SGF puts the cut

SGF closes the role inventory at fifteen. The verb at the hub is open vocabulary, drawn from the lexicon. The entities at the spokes are open vocabulary, drawn from the lexicon plus per-document micro-lexicons. The roles themselves — HAS_AGENT, HAS_PATIENT, HAS_LOCATION, and twelve others — are fixed. You cannot invent role number sixteen.

This is the correct cut. Vocabulary stays open. Grammar gets locked. Two SGF systems that have never met share the same fifteen roles by definition. Integration cost is linear: each system maps once into the shared grammar, not pairwise into every other system's grammar. This is what SGF calls saving the Babel Tax.

The closed grammar is also what makes the synapse store type-checkable. A proposed synapse that uses a role not in the closed inventory is rejected at compile time. A proposed synapse that places an entity into a role the verb cannot take (a verb requiring an animate agent, with an inanimate filler) can be flagged at compile time. The closed grammar IS the type system.

### One sentence that captures the architecture

Vocabulary is what changes. Grammar is what stays. Knowledge graphs that fail close vocabulary or leave grammar open. SGF does the opposite, and that is why it compiles.

---

## 5. The fifteen roles

The closed inventory. Six core, nine contextual. No role number sixteen.

### Six core roles

These are the roles a verb's argument structure may require. Most verbs take two or three of these.

| Role | Meaning | Example |
|---|---|---|
| HAS_AGENT | Who causes or performs the action | "Beethoven composed" → Beethoven |
| HAS_PATIENT | Who or what undergoes the action and is affected | "Caesar killed Brutus" → Brutus |
| HAS_THEME | What the action is about (without being affected) | "He discussed politics" → politics |
| HAS_EXPERIENCER | Who feels or perceives | "Mary heard the music" → Mary |
| HAS_RECIPIENT | Who receives | "Tom gave Mary a book" → Mary |
| HAS_BENEFICIARY | Who benefits | "She knitted a scarf for her son" → her son |

### Nine contextual roles

These are situational modifiers any verb may take.

| Role | Meaning | Example |
|---|---|---|
| HAS_TIME | When | "in 1792" |
| HAS_LOCATION | Where | "in Vienna" |
| HAS_SOURCE | From where or whom | "from Bonn" |
| HAS_DESTINATION | To where or whom | "to Vienna" |
| HAS_MANNER | How | "carefully" |
| HAS_INSTRUMENT | With what | "with a quill pen" |
| HAS_CAUSE | Physical cause | "because of the flood" |
| HAS_REASON | Volitional reason | "to escape the war" |
| HAS_ATTRIBUTE | What quality | "a red brick house" → red brick |

### Why fifteen and not twelve or twenty

The number is empirical. Fifteen is what the closure converges on when you actually run the experiment across PropBank, FrameNet, VerbNet, and the cross-linguistic Natural Semantic Metalanguage findings. Fewer than fifteen and you lose distinctions that matter for reasoning (HAS_CAUSE versus HAS_REASON, HAS_PATIENT versus HAS_THEME). More than fifteen and you fragment roles that should cluster (HAS_INSTRUMENT versus HAS_MEDIUM versus HAS_TOOL all collapse to HAS_INSTRUMENT).

The set is fixed. Federation depends on it.

---

## 6. The integrity protocol

A synapse without framing is not a fact. It is a string. The framing layer is what preserves what natural language preserves and what LLMs lose.

Each synapse carries the following framing attributes:

| Attribute | Values | What it preserves |
|---|---|---|
| polarity | positive, negative | "did" vs "did not" |
| modality | indicative, hypothetical, counterfactual, modal | "did" vs "might have" vs "would have" vs "could" |
| rhetorical_mode | straight, irony, sarcasm, hyperbole, humor, metaphor, rhetorical_question | "I could eat ten pizzas" stays hyperbole |
| hedging_level | none, light, heavy, disclaimer-saturated | "may", "some scholars believe", "potentially" |
| point_of_view | author, character, witness, citation, hypothesis, reported | who is making the claim |
| pov_entity | (entity_id) | the specific entity asserting it, if not the author |
| statement_type | factual, opinion, wisdom, hypothetical, counterfactual, quoted, rumor, definition | what kind of utterance |
| verb_features | 41-dimension verb space | tense, aspect, mood, voice, etc. |
| temporal_anchor | ISO date, relative duration, or null | when the event occurred |

Without these attributes, a synapse strips off the very things humans use to distinguish a confession from a denial, a teaching example from a commitment, a quotation from an assertion, a rumor from a fact. LLMs that summarize prose strip these attributes by default. GLEAN preserves them as first-class data.

The framing layer is one LLM call per synapse, or batched per paragraph. Output is in MDKV format (markdown-delimited key-value blocks), not JSON, because LLMs produce MDKV reliably and produce JSON unreliably.

---

## 7. Statement, not fact

A terminological commitment.

GLEAN extracts statements, not facts. The distinction matters.

A fact carries an implicit truth claim. To call something a fact is to assert it is true. The system has no business making truth claims about prose it compiles. A Wikipedia article on Beethoven says he was born in Bonn. GLEAN compiles that as a statement asserting Beethoven was born in Bonn, attributed to the Wikipedia article, with full provenance. Whether the statement is true is a separate question the system does not answer.

This is why every synapse has a statement_type field:

- factual — author asserts as plain truth
- opinion — marked as opinion, author or character
- wisdom — general-truth claim ("water is wet")
- hypothetical — conditional or speculative
- counterfactual — "If X had happened..."
- quoted — reported speech, not author's own claim
- rumor — hearsay
- definition — categorical, "X is a Y"

A reasoning engine downstream can apply truth-evaluation logic across statements. The synapse store itself just records what was uttered.

This terminological discipline matters because the failure mode of every "knowledge graph" project is treating every extracted relation as a fact. Wikidata struggles with this. Cyc struggled with this. GLEAN does not, by design.

---

## 8. The micro-lexicon

The vocabulary is open. The lexicon grows. The core lexicon is the closed-world floor; the micro-lexicons are the open extensions.

### Three tiers

| Tier | Scope | Examples | How it grows |
|---|---|---|---|
| Core Lexicon | Universal English (1.76M senses) | Wiktionary-derived | Periodic rebuild from Wiktionary |
| Domain Lexicon | Specialized industries | medical, legal, financial | Curated by domain experts |
| Document Lexicon | Per-corpus or per-document | "Tom Wilson", "Acme Corp" | Minted by GLEAN at compile time |

Every entity that appears in prose either resolves to a canonical_id in one of these tiers or is minted into the document lexicon.

### Micro-lexicon entries

When GLEAN encounters "Tom Wilson" and finds no match in any tier above, it mints a document-scoped entry:

```
canonical_id: doc.tom_wilson.named_entity.person.docloc
preferred_canonical: Tom Wilson
type_chain: en.person.human_being.noun.core
aliases: ["Tom", "Mr. Wilson", "Wilson"]
first_mention: clause_id=23
provenance: doc_id="biography_smith_2024", confidence=0.85
```

The type_chain must terminate in a core lexicon entry. Tom Wilson is a person; person grounds out in the core lexicon. This is the Verification Anchor: no entity may float ungrounded.

### Aliases and pronouns

The micro-lexicon also serves as the alias registry for the document. Every reference to Tom — "Tom", "Mr. Wilson", "Wilson", "he" (when disambiguated to Tom) — points to the same canonical_id. Pronoun resolution writes its decisions back to the document lexicon so all downstream stages see consistent identities.

### The Coverage Gate

If too many entities cannot be grounded — typically more than 2% out-of-vocabulary — GLEAN halts ingestion and emits a GapReport. The system prefers a Known Unknown over a False Known. A medical paper introducing a novel compound triggers the gate; a curator decides whether to mint the term into the medical domain lexicon. Silence is structurally superior to confident nonsense.

---

## 9. Synapse groups

A document is not a list of synapses. It is a graph of synapses, organized into groups that capture the discourse structure. Three cohesion signals form groups.

### By shared entity

Multiple synapses that mention the same canonical_id form a group. "Beethoven moved to Vienna. He studied with Haydn. He composed nine symphonies." Three synapses, all referencing ent_beethoven. One group: "things known about Beethoven."

### By shared predicate

Multiple synapses with the same verb form a group. "Tom built a house. Mary built a barn. Jim built a fence." Three synapses, predicate=build. One group: "build events." Useful for predicate-centric queries.

### By discourse cohesion

All synapses extracted from the same paragraph form a discourse group. Cheap to compute. Captures topical clustering that may not be visible through entity or predicate sharing alone.

Groups are not exclusive. A synapse belongs to as many groups as apply. The query layer chooses which grouping signal to use depending on the question.

---

## 10. The four-step lookup cascade

Every entity in prose must resolve to a canonical_id. The lookup cascade has four levels, in order, with escalation when each level fails.

| Level | Method | Confidence required | What fires next on failure |
|---|---|---|---|
| 1 | Exact lemma match | Surface-form match plus POS agreement | Step 2 |
| 2 | Embedded cosine search | Top-1 cosine >= 0.80 AND margin to top-2 >= 0.05 | Step 3 |
| 3 | LLM rerank from top-K candidates | LLM picks one with rationale | Step 4 |
| 4 | Micro-lexicon mint | Mint new entry in document lexicon, type-chain to core | Coverage Gate check |

The cascade is conservative. Most common nouns resolve at step 1 or 2. Polysemous words ("bank", "spring", "match") escalate to step 3. Proper nouns ("Tom Wilson") usually go to step 4. The cascade is logged: every entity in every document has a record of which level resolved it and with what confidence.

This is how the system maintains the Silence Rule. If step 4 cannot find a verifiable type-chain root for the new term, ingestion halts.

---

## 11. Implementation philosophy

A few commitments that shape every script in the pipeline.

**Deterministic first.** The LLM is a refiner, not a generator. Where spaCy can produce a candidate, spaCy produces it; the LLM polishes. Where embeddings can resolve a sense, embeddings resolve it; the LLM only ranks when embeddings are ambiguous.

**Standalone scripts.** Each stage is its own command-line program. Each can be tested in isolation. The pipeline is composed by shell scripts or Python orchestrators, not by a monolithic framework.

**Config-driven.** No hardcoded paths. Every script reads sgf.toml for the lexicon location, the embedding method, the LLM endpoint, the cascade thresholds. Move the lexicon to another disk, change one line in the config.

**Embedder loaded once.** The ONNX BGE model loads at process startup, lives in memory for the duration of the run. Within a single process, every lookup call reuses the loaded model. For multi-process workflows, a persistent embedder service (FastAPI or ZeroMQ) holds the model and serves embeddings over IPC.

**MDKV for LLM output.** Not JSON. LLMs produce MDKV reliably. Parsers for MDKV are five lines of regex. Failure modes are diagnosable. JSON failures are not.

**Provenance over plausibility.** Every synapse stores source_doc_id, source_clause_id, source_span. Every micro-lexicon entry stores first_mention and provenance. Every cascade decision stores the level it resolved at. The graph is auditable end-to-end.

---

## 12. FAQ

### Is this just RDF with a closed predicate vocabulary?

No. RDF's structural unit is the triple — three slots, one of which is the predicate. To represent a verb with multiple participants in RDF, you need either reification (a triple about a triple, with all the indirection that costs) or n-ary helpers (the Neo-Davidsonian event-node hack). Either way, the verb's argument structure is scattered across multiple triples, which is what makes RDF queries explode in size for any non-trivial reasoning.

SGF's structural unit is the synapse — one hub plus up to fifteen spokes, all in one structural object. A verb with five arguments is one synapse, not five triples. The closed grammar IS the structural shell. Closing RDF's predicate vocabulary would not produce SGF; you would still have the triple-fragmentation problem.

### Why fifteen roles? Why not twelve or twenty?

Fifteen is empirical, not arbitrary. PropBank, FrameNet, VerbNet, and cross-linguistic Natural Semantic Metalanguage all converge on a number in this range when you cluster their categories by genuine semantic distinction. Fewer than fifteen and you lose HAS_CAUSE vs HAS_REASON, HAS_PATIENT vs HAS_THEME, HAS_SOURCE vs HAS_BENEFICIARY. More than fifteen and you start splitting roles that should cluster (instrument vs medium vs tool). Fifteen is the smallest closure that preserves the distinctions reasoning systems actually need.

The closure matters more than the exact number. If field experience eventually shows fourteen or sixteen would be better, SGF can ship a versioned grammar (SGF-v2, SGF-v3). The point is that the inventory is fixed per version. You cannot mint role-sixteen at runtime.

### What about facts that do not fit one synapse?

Most don't. "Beethoven, who had moved to Vienna in 1792 to study with Haydn, composed the Eroica in 1804" contains four facts: a move event, a study event, a compose event, and a temporal relation between them. GLEAN extracts four synapses and links them through shared entities. Synapses are the atoms. Groups are the molecules. The document is the collection of molecules.

This is also why GLEAN's output is not a flat list of synapses but a graph. Each synapse can reference others by canonical_id or by synapse_id. Complex thoughts that exceed one synapse compose through inter-synapse references.

### Doesn't Google already do this?

No. Google's Knowledge Graph has overlapping surface area but fundamentally different architecture. They have ~5000 typed relations (predicates) and they keep them proprietary. Their unit is the entity record, not the statement. They privilege encyclopedic facts and have no architecture for preserving rhetorical mode, hedging, or POV. They are closed-source and unqueryable from outside Google.

SGF + GLEAN has fifteen closed roles and an open vocabulary. The unit is the statement, not the entity. Rhetorical mode, hedging, and POV are first-class. The architecture is open. The substrate is publishable. Anyone can compile their own corpus into the same substrate and federate.

The closest analogy: Google's KG is to SGF + GLEAN as Google's search index is to the open web. Both organize information. They are not substitutes.

### How does the lexicon grow?

Three ways. The core lexicon grows when Wiktionary grows; periodic rebuilds incorporate new entries. Domain lexicons grow through expert curation; medical, legal, financial communities maintain their own. Document lexicons grow at compile time, automatically, for entities and terms specific to a document or corpus.

All three tiers contribute canonical_ids. All three are queried by the lookup cascade in order: core, then domain, then document, then mint. No tier overrides another; they layer.

### What happens when the same entity appears in many documents?

The document lexicon mints a per-document canonical_id (doc.tom_wilson.named_entity.person.docloc). When a downstream process determines that two document-scoped entities refer to the same real-world entity, it can mint a corpus-level canonical_id and link both document entries to it. Or, for high-confidence cases (a person with a Wikidata Q-number), the entity can be promoted to a domain or core entry with its Wikidata identifier as the bridge.

Cross-document entity resolution is itself a separate stage that runs after compilation, against the populated synapse store. It is not GLEAN's job to do this during compilation. GLEAN's job is to preserve what each document said. Reconciliation is downstream.

### What about pronouns that span paragraphs or chapters?

Within a paragraph, proximity resolution handles most pronouns. Across paragraphs or chapters, GLEAN falls back to LLM resolution: given the pronoun, the surrounding paragraph, and the document's entity census so far, the LLM picks the most likely referent. The pick is logged with confidence. Low-confidence picks are flagged for human review.

The Bible Mode (entity census) stage of the CCE Decomposer runs first and establishes the document's actor set. Pronouns can only resolve to entities in the census. A pronoun that cannot resolve to any census entity is marked GHOST and flagged.

### What if a sentence is sarcasm or irony?

The framing layer's rhetorical_mode field captures it. "Oh great, another Monday" with rhetorical_mode=sarcasm tells downstream consumers the polarity is inverted. A reasoning engine that treats sarcastic statements as literal is wrong; the framing layer gives it the data to do better.

Detecting sarcasm reliably requires LLM judgment. The framing layer is an LLM call by design.

### What if the LLM is wrong?

Every LLM call is logged with its inputs and outputs. Every synapse stores the cascade-level it resolved at. When the LLM is wrong, the audit trail shows where it was wrong and what alternatives existed. Corrections can be applied by adding a synapse with a higher binding force that overrides the original, or by demoting the original to a lower-confidence band.

The architecture does not assume the LLM is right. The architecture assumes every claim is auditable.

### Can this scale to all of Wikipedia?

In principle, yes. In practice, the bottleneck is compute time for the LLM calls, not algorithmic. Compiling all of English Wikipedia (~6 million articles, ~3 billion words) would take significant compute. Cloud-LLM cost makes this expensive. Local LLM at the right scale makes it feasible. The architecture does not change; only the deployment does.

A first useful milestone is not all of Wikipedia. It is a focused corpus where structured knowledge unlocks real reasoning — perhaps the biographies of major composers, the case law of a specific jurisdiction, or the technical specifications of a regulatory domain. Depth before breadth.

### What is the smallest demonstration that proves the system works?

One paragraph of prose, compiled end-to-end into synapses, with the synapse store queryable for the questions the paragraph answered. If a paragraph about Beethoven studying with Haydn in Vienna in 1792 produces synapses that can answer "who did Beethoven study with?" and "when did Beethoven move to Vienna?" and "what did scholars believe but cannot prove about Beethoven?", the architecture is real. Scale is then a question of deployment, not architecture.

---

## 13. Naming commitments

A few terminology decisions made and locked.

**Statement, not fact.** A synapse records a statement. Truth evaluation is downstream.

**Synapse, not triple, claim, or assertion.** The hub-and-spoke unit is a synapse. The word emphasizes connection and binding force, both apt.

**Framing, not metadata.** The integrity layer is framing. It carries the rhetorical and epistemic context. Metadata is too thin a word; framing is what allows distinguishing a confession from a quotation.

**Frame, not group.** A frame is the rhetorical-epistemic context attached to a single synapse. A group is the discourse cluster of synapses sharing an entity, predicate, or paragraph. Two different concepts. Two different words.

**Canonical ID, not URI.** SGF identifiers are local-grounded canonical IDs, not web-resolvable URIs. They look like en.beethoven.composer.name.core. They are addressable but not crawlable. Federation does not require URLs.

**Core, Domain, Document Lexicon.** Three tiers. The core is the universal floor. Domains are industry specializations. Documents are per-corpus. The terminology is fixed.

**Open vocabulary, closed grammar.** The architectural slogan. Vocabulary at the hub and spokes is open. Grammar (the fifteen roles) is closed. This is the cut.

---

## 14. What is in scope, what is not

In scope for GLEAN v1:

- Compiling English prose into synapses
- Resolving entities against the SGF core lexicon
- Minting micro-lexicon entries for unrecognized terms
- Resolving pronouns within and across paragraphs
- Resolving possessive chains into multi-synapse trees
- Producing framing for each synapse (rhetorical mode, POV, modality, etc.)
- Persisting to SQLite
- Grouping synapses by entity, predicate, and discourse

Out of scope for GLEAN v1:

- Multilingual prose (English only; multilingual is a v2 expansion when BGE-M3 is added as an embedding method)
- Cross-document entity resolution (separate downstream stage)
- Truth evaluation (separate downstream reasoning engine)
- Real-time streaming compilation (v1 is batch only)
- Graphical query interface (v1 produces SQLite; queries are SQL)
- Federation across SGF systems (v1 produces a single-system synapse store; federation is a v2 capability)

The boundary between scope and out-of-scope is firm. Each v2 capability becomes its own info bundle when its time comes.

---

## 15. Connection back to the rest of SGF

GLEAN is one stage of the SGF stack, not the whole stack. Other stages exist already or are planned:

- **Core Lexicon Build Pipeline** (built): wiktionary -> sgf_lexicon -> microglosses -> embeddings -> fingerprints
- **CCE Decomposer** (built, ready for integration): prose -> clausal IR with entity census
- **GLEAN** (this document): clausal IR -> synapse store
- **Synapse Store** (this document): SQLite database holding synapses, frames, groups
- **Query Layer** (planned): SQL or graph queries against the synapse store
- **Reasoning Engine** (planned): rule-based inference over the synapse store
- **Federation Layer** (planned): cross-system synapse exchange using the Stranger Rule

GLEAN sits in the middle. It is the compiler. Everything above it produces prose. Everything below it consumes synapses. GLEAN is the bridge from human-readable to machine-reasonable.

---

*End of info bundle. Next: the code.*
