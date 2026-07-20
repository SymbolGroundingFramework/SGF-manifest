# SGF — Synapedia Grammar Framework

**A complete infrastructure for compiling meaning from prose and structured data into verifiable, auditable knowledge graphs.**

---

## What is SGF?

SGF (Synapedia Grammar Framework) is an engineering framework for building knowledge graphs that are **deterministic, auditable, and evolvable**. It is built on three architectural insights:

1. **Closed grammar** — ~38 primitives (15 thematic roles, 5 binary core relations, 5 BFO dependence relations, 8 link types, 1 generic verb, 4 identity primitives) prevent predicate explosion. You cannot invent new structural shapes — only new vocabulary.

2. **Compiler, not map** — Meaning is compiled from context at compile time, not looked up from a dictionary at query time. GLEAN (the prose-to-graph pipeline) and the DB Adapter (the data-to-graph pipeline) both produce the same Synapse IR — a native n-ary event structure with full provenance.

3. **Deterministic alignment** — SOAM (Semantic Ontology Alignment Module) compares concepts across ontologies using an 18-slot schema, producing either a ProofTrace (verified match) or a GapReport (structured failure).

This framework is **open source** with a **vow to never patent the architecture**.

---

## Philosophy

The architecture is grounded in a set of philosophical claims developed in the companion document *"The Compiler and the Closed Grammar: The Philosophical Foundations of SGF"*:

- **The universe is not self-annotating** — symbols carry no intrinsic meaning. Classification is an act of an agent imposing a category on reality.
- **Meaning transfer conserves four components** — every crossing requires a pivot, a bridge, a policy, and a proof.
- **A finite bedrock guarantees termination** — ~65 NSM primes + NIST physical constants halt the regress of definition.
- **The closed grammar is the secret** — RDF/OWL's open predicates cause the Babel Tax. A closed grammar enables linear integration cost.

The full philosophical foundations are in `docs/philosophical_foundations.md` (or available as a standalone document).

---

## Capabilities

### What SGF Does

| Capability | Component | What it produces |
|---|---|---|
| **Build a lexicon** from open data | Synapedia bootstrapping pipeline | `synapedia.db` — ~1.9M entries with canonical IDs, microglosses, embeddings, BFO categories |
| **Compile prose** into structured events | GLEAN pipeline | Synapses (verb hub + 1–15 thematic roles) with full provenance |
| **Ingest structured data** into the same format | DB Adapter (CSV/TSV via YAML mapping) | Synapses (same format as GLEAN) |
| **Align ontologies** deterministically | SOAM engine | ProofTrace (verified match) or GapReport (structured failure) |
| **Export** to any knowledge graph | Export adapters | Neo4j (Cypher), Stardog (SPARQL INSERT), GraphDB (Turtle), TypeDB (TypeQL), Kuzu (Cypher), Neptune (SPARQL or Gremlin) |
| **Search** the lexicon | Search server (FastAPI, port 8400) | 3-factor scoring cascade (lemma, POS, cosine) with reranker and LLM tiebreaker |
| **Learn new terms** automatically | Living Lexicon | New entries minted via three triggers (ontology gaps, compounds, sense discovery) |
| **Resolve synonyms** | Synonym Registry | Bidirectional mapping to canonical pivot |
| **Handle unknowns** | Ghost Protocol | Provisional nodes with TTL, promotable to canonical entries |
| **Embed text** to vectors | Embedding service (BGE-large-en-v1.5, ONNX, port 18401) | 1024-dim L2-normalized vectors |

---

## Repository Structure

```
sgf/
├── README.md                       # This file
├── docs/
│   ├── philosophical_foundations.md  # The full philosophical argument
│   ├── architecture_overview.md      # 1-page summary for evaluators
│   └── quickstart.md                 # How to get up and running
├── synapedia/                      # Lexicon bootstrapping pipeline
│   ├── import_wordnet.py           # Stage 1: WordNet XML → wordnet.db
│   ├── import_wiktionary.py        # Stage 3: Kaikki JSONL → wiktionary_raw.db
│   ├── import_wikipedia.py         # Stage 5: Wikipedia dumps → synapedia.db
│   ├── postprocess.py              # Stage 7: microglosses, canonical IDs, BFO categories
│   ├── compute_embeddings.py       # Stage 8: BGE-M3 embeddings
│   ├── microgloss_generator.py     # Embedding-guided beam search
│   ├── canonical_id.py             # Canonical ID construction & collision detection
│   ├── bfo_category_mapper.py      # BFO category detection from grammar
│   └── synapedia_mint.py           # Shared minting function
├── glean/                          # Prose-to-graph pipeline
│   ├── compile_document.py         # Top-level orchestrator
│   ├── defluffer.py                # Stage 0: remove filler, hedging, redundancy
│   ├── entity_census.py            # Entity identification & resolution
│   ├── clause_to_synapse.py        # Clause extraction → Synapses
│   ├── framing.py                  # Epistemic framing (POV, hedging, speech act)
│   ├── synapse_grouper.py          # Group synapses by shared entities/predicates
│   ├── synapse_store_persist.py    # Persist to synapedia_synapse, spokes, groups
│   ├── dep_to_role.json            # Dependency-to-role mapping table
│   ├── reporting_verbs.txt         # Verbs that trigger attribution-based POV
│   └── pos_rosetta.json            # spaCy POS → SGF POS mapping
├── db_adapter/                     # Data-to-graph pipeline
│   ├── adapter.py                  # CSV/TSV reader + YAML mapper
│   ├── yaml_parser.py              # YAML configuration parser
│   └── entity_minter.py            # Mint corp.* instances with IS-A tethers
├── search_server/                  # Lexicon search server
│   ├── search_server.py            # FastAPI HTTP daemon (port 8400)
│   ├── syn_search_adapter.py       # Ontology-aware search client (v0.7.0)
│   ├── bm25_score.py               # BM25 lexical scoring
│   ├── reranker.py                 # Cross-encoder reranker
│   ├── lemma_resolver.py           # Surface-form-to-lemma resolution
│   ├── llm_tiebreaker.py           # LLM-of-last-resort tiebreaker
│   ├── llm_kv_parser.py            # <answer>/<comments> envelope parser
│   ├── llm_wrapper.py              # Single-file LLM caller
│   └── search_config.toml          # Configuration file
├── embedder/                       # Embedding service
│   └── embed_service.py            # BGE-large ONNX service (port 18401)
├── exporters/                      # Export adapters
│   ├── glean_export_cypher.py      # → Neo4j (Cypher)
│   ├── glean_export_sparql.py      # → Stardog/GraphDB (SPARQL INSERT + Turtle)
│   └── (other adapters planned)    # TypeDB, Kuzu, Neptune
├── soam/                           # Alignment engine (planned)
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

The atomic meaning unit. A verb hub with 1–15 bound thematic roles:

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

Every sense has a stable, grounded identifier:

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

RELATES_TO — absorbs all domain-specific relations (citizenship, employment, ownership) without predicate explosion.

---

## License

Apache 2.0. Free to use, modify, redistribute, including commercially.

**Patent pledge:** The author vows to never patent the SGF architecture. This is a personal commitment, not a legal instrument.

---

## Books

The SGF architecture is documented in a six-volume book series published on Amazon:

- *The Synapedia Grammar Framework, Volume 1: Foundation & Inevitability*
- *Volume 2: The Grammar*
- *Volume 3: The Lexicon & The Living Lexicon*
- *Volume 4: Pipelines: GLEAN & DB Adapter*
- *Volume 5: Reasoner & Export*
- *Volume 6: Alignment, Trust & Governance*

A hands-on implementation guide is forthcoming.

---

## Author

James Lee Stakelum


