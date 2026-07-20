# SGF — The Synapedia Grammar Framework

### A Meaning Infrastructure for Verifiable, Auditable Knowledge Graphs

---

## What Is SGF?

SGF is an engineering framework for building knowledge graphs that are **deterministic, auditable, and evolvable**. It is built on three architectural insights:

1. **Closed grammar** — ~38 primitives (15 thematic roles, 5 binary core relations, 5 BFO dependence relations, 8 link types, 1 generic verb, 4 identity primitives) prevent predicate explosion. You cannot invent new structural shapes — only new vocabulary.

2. **Compiler, not map** — Meaning is compiled from context at compile time, not looked up from a dictionary at query time. **GLEAN** (prose‑to‑graph) and **the DB Adapter** (data‑to‑graph) produce the same Synapse IR — a native n‑ary event structure with full provenance.

3. **Deterministic alignment** — **SOAM** compares concepts across ontologies using an 18‑slot schema, producing either a **ProofTrace** (verified match) or a **GapReport** (structured failure). This is the Rosetta Stone that makes ontology alignment a linear mapping problem rather than a quadratic one.

The framework is **open source** with a **vow to never patent the architecture**.

---

## The Philosophy

SGF is grounded in four philosophical commitments. They are not design preferences — they are structural necessities forced by the nature of meaning.

### The Universe Is Not Self‑Annotating

Symbols carry no intrinsic meaning. Classification is always an act of a particular agent, in a particular context, for a particular purpose. Two agents will classify the same thing differently because they have different purposes.

This means meaning must be **negotiated**, not decreed. SOAM formalises this negotiation: it compares two concept definitions through a shared pivot (the Core Lexicon), producing either a verifiable ProofTrace or a structured GapReport. Alignment is never assumed; it is always proved.

### The Compiler, Not the Map

RDF/OWL treats meaning as a lookup problem: build a dictionary (ontology), look up URIs at query time. This fails because meaning is not static.

- "Bach" in *"I love Bach!"* means music.
- "Bach" in *"Bach was born in 1685"* means a person.

No dictionary can capture this without context. The meaning must be **compiled** from the sentence at the time of ingestion, not looked up from a URI at the time of query.

GLEAN and the DB Adapter are **compilers**. They produce unambiguous Synapses at compile time, resolving polysemy, metonymy, and hedging *before* the data ever enters the graph. The graph receives finished events, not fragments that must be reconstructed heuristically at query time.

### The Closed Grammar

The structural secret of SGF is not the verb hub. Linguists have known about verb frames since Fillmore's case grammar (1968). The secret is that **meaning cannot be structured reliably with an open grammar**.

An open grammar (RDF/OWL) gives infinite flexibility. That flexibility is its fatal flaw: every integration becomes a bespoke mapping project. SGF closes the grammar. You cannot invent new roles, new binary relations, or new link types. You can only invent new vocabulary to fill the existing shapes.

This is the inversion that makes integration linear: there is exactly one shape for an event, one shape for a hierarchy, one shape for a discourse link — no matter what domain you are in.

### The Finite Bedrock Principle

Every unbounded domain requires a finite bedrock. For meaning, this is ~65 NSM primes + NIST physical constants. For events, it is the 15 closed semantic roles. For identity, it is the Canonical ID with microgloss.

SGF's architecture terminates here. RDF/OWL's does not — its recursion ends at `owl:Thing`, a logical axiom, not a grounded concept. This is why SGF can be honest about what it does not know: the compiler stops when it hits the bedrock, and it tells you exactly what it cannot ground (via GapReports).

### Meaning Transfer Conserves Four Components

Every crossing of meaning across a boundary requires:

| Component | Without it | SGF Instantiation |
|---|---|---|
| **Pivot** (shared reference) | Grounding collapse — semantic drift | The Core Lexicon (Synapedia) |
| **Bridge** (verifiable connection) | Isolation — parties cannot connect | Bridge Map + SOAM alignment |
| **Policy** (rules for admission) | Anarchy or paralysis — every message admitted or refused | Receiver Policy, SurfaceArea |
| **Proof** (record of the crossing) | Amnesia — no audit trail | ProofTrace, GapReport |

This law is not architectural. It is a discovery about meaning itself.

---

## How SGF Improves Existing Knowledge Graphs

SGF does not require a rip‑and‑replace. It is a **governance layer** that sits above existing triple stores and provides deterministic alignment, grounded definitions, and linear integration cost.

| Problem in Existing KGs | How SGF Addresses It | Without Overclaiming |
|---|---|---|
| **Predicate explosion** — every new relation requires a new URI | Closed grammar (~38 primitives) absorbs all domain relations via `RELATES_TO` + 15 roles | Predicates are not eliminated; they are structured into a fixed set of shapes. The vocabulary of relation types still grows, but the structural alphabet is closed. |
| **N² ontology alignment** — every integration is bespoke | SOAM aligns each ontology to the Core Lexicon pivot, making integration linear | Requires L0 (Core Lexicon) coverage for the domain. Without it, alignment remains N². |
| **Event fragmentation** — multi‑participant events are scattered across triples | Native n‑ary Synapses preserve event integrity (verb hub + 15 roles) | Events with >3 roles are not projected to binary edges; they remain as Synapses. No information loss. |
| **No provenance** — claims arrive without source or epistemic status | Every Synapse carries byte‑offset provenance, epistemic status, and derivation tag | Provenance is mandatory, not optional. The Coverage Gate halts ingestion if provenance cannot be attached. |
| **Lexicon drift** — vocabulary evolves but ontologies stay frozen | Living Lexicon detects gaps via three triggers and mints new entries deterministically | New entries are `INFERRED` tier until promoted. Drift is surfaced, not silently corrected. |
| **No honesty about gaps** — systems fabricate when they don't know | GapReports and Ghost Protocol ensure structured failure and provisional placeholders | The system does not guess. It tells you exactly what it cannot ground. |

---

## Capabilities

| Capability | Component | What It Produces |
|---|---|---|
| **Build a lexicon** from open data | Synapedia bootstrapping pipeline | `synapedia.db` — ~1.9M entries with canonical IDs, microglosses, embeddings, BFO categories |
| **Compile prose** into structured events | GLEAN pipeline (21 stages + Defluffer) | Synapses (verb hub + 1–15 thematic roles) with full provenance |
| **Ingest structured data** into the same format | DB Adapter (CSV/TSV via YAML mapping) | Synapses in the same format as GLEAN |
| **Align ontologies** deterministically | SOAM engine | ProofTrace (verified match) or GapReport (structured failure) |
| **Export** to any knowledge graph | Export adapters | Neo4j (Cypher), Stardog (SPARQL INSERT), GraphDB (Turtle), TypeDB (TypeQL), Kuzu (Cypher), Neptune (SPARQL or Gremlin) |
| **Search** the lexicon | Search server (FastAPI, port 8400) | 3‑factor scoring (lemma, POS, cosine) with reranker and LLM tiebreaker |
| **Learn new terms** automatically | Living Lexicon | New entries minted via three triggers (ontology gaps, compounds, sense discovery) |
| **Resolve synonyms** | Synonym Registry | Bidirectional mapping to canonical pivot |
| **Handle unknowns** | Ghost Protocol | Provisional nodes with TTL, promotable to canonical entries |
| **Embed text** to vectors | Embedding service (BGE‑large‑en‑v1.5, ONNX, port 18401) | 1024‑dim L2‑normalised vectors |

---

## How the Knowledge Graph Schema Is Structured

Every structural assertion in SGF exists in two forms:

| Form | Role | Carries |
|---|---|---|
| **Synapse** (hub‑and‑spoke) | **Source of truth** | Verb hub, 15 roles, frames, provenance, epistemic status, BFO category |
| **SynapseLink** (binary edge) | **Query optimisation** | Subject, predicate, object, confidence, source Synapse ID |

The Synapse is the truth. The binary edge is the projection. The Reasoner is the bridge.

**Projection rule:** Synapses with ≤3 populated roles are projected as binary edges. Synapses with >3 roles remain as Synapses only — collapsing them would lose information.

**Hybrid storage model:**
- **Events** (prose, actions, transactions) → Synapses with hub‑and‑spoke grammar.
- **Static descriptions** (customer records, product catalogs, network inventory) → **EAV triples** (subject, predicate, object). No verb hub wasted on static data.
- Both use the same **canonical IDs**, same **provenance**, same **governance**.

**Export adapters** translate this internal representation to any backend:

| Backend | Pattern | Frame Preservation |
|---|---|---|
| **Neo4j** | `:Event` + role relationships (`:HAS_AGENT`) | Separate `:Frame` nodes via `:HAS_FRAME` |
| **Stardog / GraphDB** | Reified event nodes (`syn:Event`) | RDF‑star annotations or named graphs |
| **TypeDB** | Native n‑ary relations (`action`) | Relation attributes |
| **Kuzu** | Columnar property graph | Frame nodes |
| **Neptune** | RDF or property graph (user choice) | RDF‑star or Gremlin properties |

**For high‑frequency data (telemetry, location pings):**

| Store | Pattern | Query |
|---|---|---|
| **Event store** | Append‑only, temporal | "Where was it at 3:14 PM on June 5?" |
| **Snapshot store** | Upsert, current state | "Where is it right now?" |

Bridge: `SELECT entity_id, LAST(value) FROM events GROUP BY entity_id`

---

## The Alignment Engine: SOAM as Rosetta Stone

SOAM (Semantic Ontology Alignment Module) is SGF's answer to the Rosetta Stone problem. It compares two concept definitions deterministically, producing either a **ProofTrace** or a **GapReport**.

**The 18‑Slot Schema:**

| # | Slot | Source |
|---|---|---|
| 1–3 | IS_A (parent, grandparent, great‑grandparent) | Binary relation (DAG walk) |
| 4–5 | HAS_PART (essential, optional) | Binary relation |
| 6 | HAS_MEMBER | Binary relation |
| 7–8 | HAS_ATTRIBUTE (structural, definitional) | Thematic role |
| 9–11 | HAS_DEFAULT_UTILITY, ALTERNATE, PROHIBITED | Hub‑and‑spoke |
| 12 | RELATES_TO | Generic verb |
| 13–17 | CONSTITUTIVE_EVENT (birth, founding, achievement, death, other) | Hub‑and‑spoke |
| **18** | **BFO_CATEGORY** | Derived from grammar |

**Three Depth Levels:**

| Level | Depth | Speed | Use Case |
|---|---|---|---|
| **L1 (Search)** | Direct ontology join only | ~1ms | Browsing, catalog search |
| **L2 (Alignment)** | +1 IS_A walk + slots 7–8 | ~10ms–1s | Standard procurement |
| **L3 (Proof)** | Full recursive to primes (all 18 slots) | ~1s+ | High‑stakes compliance, aerospace |

**The Decider** selects the appropriate path based on confidence and consequence. When confidence is borderline and consequence is moderate, the system asks the sender via a structured `CLARIFY` question, then re‑evaluates. It never guesses silently.

---

## Comparison: SGF vs RDF/OWL

| Concern | RDF/OWL | SGF |
|---|---|---|
| **Predicate model** | Open — anyone can invent a URI | **Closed — ~38 primitives** |
| **Integration cost** | N² — every partner needs a new mapping | **N‑to‑1 — align to the Core Lexicon via SOAM** |
| **Event representation** | Reification (heavy, non‑standard, loses n‑arity) | **Native n‑ary Synapses (15 roles, standard)** |
| **Meaning grounding** | Recursive URIs (terminates at `owl:Thing`, a logical axiom) | **Finite Bedrock (~65 NSM primes + NIST constants)** |
| **Vocabulary evolution** | Static ontology (manual updates) | **Living Lexicon (auto‑discovers from usage)** |
| **Provenance** | Optional, non‑standard | **Mandatory (byte‑offset, epistemic status, derivation tag)** |
| **Federation** | Open‑world assumption (anything can be asserted) | **Receiver sovereignty (policy‑gated admission)** |
| **Truth of saying** | No native mechanism (reification required) | **First‑class nesting (outer = utterance, inner = proposition)** |
| **Corrigibility** | Destructive merge is common | **Reversible `SAME_AS` edges (never fuse nodes)** |
| **Epistemic context** | No standard vocabulary | **15‑field frame (POV, hedging, speech act, scope, etc.)** |

---

## Repository Layout

```
sgf/
├── README.md                       # This file
├── docs/
│   ├── philosophical_foundations.md  # Full philosophical argument
│   ├── architecture_overview.md      # 1‑page summary for evaluators
│   └── quickstart.md                 # Getting up and running
├── synapedia/                      # Lexicon bootstrapping pipeline
│   ├── import_wordnet.py           # Stage 1: WordNet → wordnet.db
│   ├── import_wiktionary.py        # Stage 3: Kaikki JSONL → wiktionary_raw.db
│   ├── import_wikipedia.py         # Stage 5: Wikipedia dumps → synapedia.db
│   ├── postprocess.py              # Stage 7: microglosses, canonical IDs, BFO categories
│   ├── compute_embeddings.py       # Stage 8: BGE‑M3 embeddings
│   ├── microgloss_generator.py     # Embedding‑guided beam search
│   ├── canonical_id.py             # Canonical ID construction & collision detection
│   ├── bfo_category_mapper.py      # BFO category detection from grammar
│   └── synapedia_mint.py           # Shared minting function
├── glean/                          # Prose‑to‑graph pipeline
│   ├── compile_document.py         # Top‑level orchestrator
│   ├── defluffer.py                # Stage 0: remove filler, hedging, redundancy
│   ├── entity_census.py            # Entity identification & resolution
│   ├── clause_to_synapse.py        # Clause extraction → Synapses
│   ├── framing.py                  # Epistemic framing (POV, hedging, speech act)
│   ├── synapse_grouper.py          # Group synapses by shared entities/predicates
│   ├── synapse_store_persist.py    # Persist to synapedia_synapse, spokes, groups
│   ├── dep_to_role.json            # Dependency‑to‑role mapping table
│   ├── reporting_verbs.txt         # Verbs triggering attribution‑based POV
│   └── pos_rosetta.json            # spaCy POS → SGF POS mapping
├── db_adapter/                     # Data‑to‑graph pipeline
│   ├── adapter.py                  # CSV/TSV reader + YAML mapper
│   ├── yaml_parser.py              # YAML configuration parser
│   └── entity_minter.py            # Mint corp.* instances with IS‑A tethers
├── search_server/                  # Lexicon search server
│   ├── search_server.py            # FastAPI HTTP daemon (port 8400)
│   ├── syn_search_adapter.py       # Ontology‑aware search client (v0.7.0)
│   ├── bm25_score.py               # BM25 lexical scoring
│   ├── reranker.py                 # Cross‑encoder reranker
│   ├── lemma_resolver.py           # Surface‑form‑to‑lemma resolution
│   ├── llm_tiebreaker.py           # LLM‑of‑last‑resort tiebreaker
│   ├── llm_kv_parser.py            # <answer>/<comments> envelope parser
│   ├── llm_wrapper.py              # Single‑file LLM caller
│   └── search_config.toml          # Configuration file
├── embedder/                       # Embedding service
│   └── embed_service.py            # BGE‑large ONNX service (port 18401)
├── exporters/                      # Export adapters
│   ├── glean_export_cypher.py      # → Neo4j (Cypher)
│   ├── glean_export_sparql.py      # → Stardog/GraphDB (SPARQL INSERT + Turtle)
│   └── (other adapters planned)    # TypeDB, Kuzu, Neptune
├── soam/                           # Alignment engine (in development)
└── config/                         # Shared configuration
    └── sgf.toml                    # Global configuration
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- spaCy English model (`en_core_web_lg` recommended)
- FastAPI, uvicorn, numpy, onnxruntime, tokenizers, huggingface_hub
- An LLM wrapper (OpenRouter or Ollama) for compound minting and enrichment

### 1. Build the Lexicon

```bash
cd synapedia
python import_wordnet.py
python import_wiktionary.py
python import_wikipedia.py
python postprocess.py
python compute_embeddings.py
```

This produces `synapedia.db` with ~1.9M entries, each with a canonical ID, microgloss, embedding, and BFO category.

### 2. Start the Services

```bash
# Terminal 1: Embedding service (ONNX model, ~2GB RAM)
python embedder/embed_service.py --db synapedia.db --port 18401

# Terminal 2: Search server
python search_server/search_server.py --lexicon synapedia.db --port 8400

# Terminal 3: Query via adapter
python search_server/syn_search_adapter.py "titanium torque driver"
```

### 3. Compile a Document

```bash
cd glean
python compile_document.py \
  --input beethoven.txt \
  --doc-id beethoven_001 \
  --accuracy-mode standard \
  --search-server http://localhost:8400
```

This produces:
- `entity_map.json` — all resolved entities
- `synapses.json` — structured events with 15 thematic roles
- `synapses_framed.json` — with epistemic frames
- `groups.json` — discourse structure with links
- Persisted to `synapse_store.db`

### 4. Export to Neo4j or Stardog

```bash
# Export to Neo4j
python exporters/glean_export_cypher.py \
  --input synapse_store.db \
  --main-lexicon synapedia.db \
  --parent-depth 1 \
  --output beethoven.cypher

# Export to Stardog/GraphDB
python exporters/glean_export_sparql.py \
  --input synapse_store.db \
  --main-lexicon synapedia.db \
  --parent-depth 1 \
  --output beethoven.ttl \
  --format turtle
```

---

## Key Concepts

### Synapse

```json
{
  "synapse_id": "syn.a1b2c3d4e5f6",
  "verb_lemma": "compose",
  "verb_canonical_id": "en.compose.create_music.verb.synapedia_wordnet",
  "plane": "claim",
  "epistemic_status": "SOURCED",
  "spokes": [
    {"role": "HAS_AGENT", "target_id": "en.beethoven.composer.noun.core"},
    {"role": "HAS_PATIENT", "target_id": "en.mass_in_b_minor.musical_work.noun.core"},
    {"role": "HAS_TIME", "target_id": "1740s", "target_type": "TYPED_LITERAL"}
  ]
}
```

### Canonical ID

```
{language}.{lemma}.{microgloss}.{pos}.{namespace}
```

Example: `en.bank.financial_institution.noun.synapedia_wordnet`

### The 15 Thematic Roles (Closed)

| Core Roles | Context Roles |
|---|---|
| HAS_AGENT | HAS_TIME |
| HAS_PATIENT | HAS_LOCATION |
| HAS_THEME | HAS_SOURCE |
| HAS_EXPERIENCER | HAS_DESTINATION |
| HAS_RECIPIENT | HAS_MANNER |
| HAS_BENEFICIARY | HAS_INSTRUMENT |
| | HAS_CAUSE |
| | HAS_REASON |
| | HAS_ATTRIBUTE |

No sixteenth role may be added.

### The 5 Binary Core Relations (Closed)

IS_A, HAS_PART, HAS_MEMBER, HAS_INSTANCE, ANTONYM_OF

### The 5 BFO Dependence Relations (Closed)

specifically_depends_on, generically_depends_on, inheres_in, realizes, concretizes

### The 8 Link Types (Closed)

PRECEDES, CAUSES, ENABLES, SUPPORTS, CONTRADICTS, ELABORATES, SUPERSEDES, DEPENDS_ON

### The Generic Verb

`RELATES_TO` — absorbs all domain‑specific relations without predicate explosion.

---

## Open Questions and Honest Boundaries

SGF has known gaps. The architecture is designed to surface them honestly, not to claim omnicompetence.

| Gap | Impact | Status |
|---|---|---|
| **SOAM engine** | Cross‑ontology alignment requires a running aligner | Core logic defined; deployment pipeline pending |
| **Living Lexicon clustering** | Sense discovery from usage ledger | HDBSCAN integration planned |
| **Temporal regions as first‑class entities** | Time values stored as literals | Planned for next phase |
| **CL axiomatisation** | No formal logic proof of grammar consistency | Planned for government compliance phase |
| **Domain‑specific trust scores** | Trust is a single scalar per partner | Planned for federation phase |

The architecture never fabricates. The Coverage Gate ensures the system halts when it cannot ground a term. The GapReport ensures every failure is structured and actionable. SGF does not claim to have solved every problem — it claims to have built the infrastructure that *surfaces* problems honestly, so they can be solved systematically.

---

## License and Patent Pledge

**Apache 2.0.** Free to use, modify, redistribute, including commercially.

**The author vows to never patent the SGF architecture.** This is a personal commitment, not a legal instrument, but it reflects the intent that this infrastructure remain open for all.

---

## Further Reading

- `docs/philosophical_foundations.md` — The full philosophical argument: the closed grammar, the conservation laws, the finite bedrock principle.
- `docs/architecture_overview.md` — A one‑page summary for KG engineers and evaluators.
- `docs/quickstart.md` — Detailed walkthrough for getting up and running.
- Six‑volume SGF book series on Amazon (theory and philosophy).
- A hands‑on implementation guide is forthcoming.

---

*The grammar is closed at ~38 primitives. The vocabulary is infinite. A dictionary accepts any word. A proof substrate requires every word to earn its place — and to earn the right to be seen, trusted, scaled, retained, and appealed.*
```
