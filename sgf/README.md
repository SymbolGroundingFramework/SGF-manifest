# SGF — The Synapedia Grammar Framework

### A Meaning Infrastructure for Verifiable Knowledge Graphs

---

## In 30 Seconds

SGF replaces the open‑predicate model of RDF/OWL with a **closed grammar of ~38 primitives**. It compiles prose (via **GLEAN**) and structured data (via the **DB Adapter**) into a unified format called **Synapses** — native n‑ary event structures grounded in a bootstrapped core lexicon (**Synapedia**). It aligns concepts across ontologies deterministically using **SOAM** (the Rosetta Stone for meaning), eliminating the N² integration tax. The output can be exported to **Neo4j, Stardog, Kuzu, TypeDB, or Neptune** without losing structural fidelity.

---

## The Philosophy (Why This Architecture Exists)

SGF is built on four commitments. They are not design preferences; they are structural necessities forced by the nature of meaning.

1.  **The Compiler, Not the Map.** RDF/OWL treats meaning as a lookup problem (query a URI). This fails because "Bach" means "person" in a biography and "corpus" in a music store. Meaning must be **compiled** from context at ingestion time (GLEAN resolves polysemy during the first pass), not looked up from a dictionary at query time.

2.  **The Universe Is Not Self‑Annotating.** Symbols carry no intrinsic meaning. Classification is always an act of a particular agent. This forces meaning to be **negotiated** (SOAM compares slot‑by‑slot) rather than decreed (inventing a URI).

3.  **The Closed Grammar.** The secret to linear integration. You cannot invent a 16th thematic role, a 9th link type, or a 6th binary relation (beyond `HAS_POSSESSOR`). You can only invent new vocabulary to fill the existing structural shapes. Predicate explosion is structurally impossible.

4.  **The Finite Bedrock.** Meaning must terminate somewhere. SGF terminates at ~65 NSM primes + NIST constants (the **Prime Registry**). RDF/OWL terminates at `owl:Thing`, which is a logical axiom, not a grounded concept. This is why SGF can be honest about what it does not know (via **GapReports**).

---

## The Two Ingestion Pipelines

Both pipelines produce an identical **Synapse Intermediate Representation**. The downstream Reasoner, Exporter, and Living Lexicon do not know or care which path produced the data.

### 1. Prose-to-Graph: GLEAN (The Prose Compiler)

GLEAN is a **21‑stage compiler (+ Stage 0)**. It is not a "triple extractor". It preserves negation, hedging, perspective, and discourse structure.

```
Prose → Defluffer → Entity Census → Clause Extraction → VerbHub + 15 Roles → Framing → Provenance → Synapses
```

| Stage | Description |
|---|---|
| **0. Defluffer** | Removes filler, hedging, throat‑clearing, redundancy (30–50% token reduction) *before* a single entity is resolved. |
| **1–6. Parse** | Tokenisation, POS tagging, dependency parsing, clause segmentation. |
| **7–11. Entity Census** | 7 passes: named entity collection, role‑noun collection, alias clustering (multi‑pass, fixed‑point), pronoun resolution (~3‑sentence window), possessive chain detection ("Tom's house" → instances), context harvest, lexicon lookup. Detects **12 metonymic patterns** (Creator‑to‑Corpus, Place‑for‑Institution, etc.) *before* the lexicon lookup to prevent ghost entries from figurative language. |
| **12–15. Clause Extraction** | One **Synapse** per root verb. A deterministic `dep_to_role.json` map maps spaCy dependency labels to exactly one of the 15 closed roles. The VerbHub captures polarity, modality, tense, aspect, and rhetorical mode. |
| **16–18. Framing** | Every Synapse gets a **frame** carrying `point_of_view`, `speech_act`, `hedging_level`, `scope`, `temporal_anchor`, `conditional_marker`. |
| **18–21. Quality Gates** | **Coverage Gate** (OOV > 2% → Halt. The system never guesses). **Reconstruction Test** (a different model must reconstruct 95% of the original propositions from the Synapses. If it fails, the ingestion is rejected). **BFO Category Validation** (assigned category must be consistent with the Synapse structure). |

**Key Principle — Truth of Saying vs. Truth of What Was Said:** The outer Synapse (someone said *X*) and the inner Synapse (*X* is true) are distinct. They are nested, never conflated. Journalism, testimony, and fiction are handled natively.

### 2. Data-to-Graph: DB Adapter (The Data Compiler)

Ingests CSV/TSV via a **YAML mapping configuration**. Produces the exact same Synapse format as GLEAN.

```yaml
tables:
  - name: network_elements
    verb: install
    roles:
      tower_id: { role: HAS_THEME, entity_type: cell_tower }
      location: { role: HAS_LOCATION }
      install_date: { role: HAS_TIME, data_type: date }
```

| Pattern | Grammar | Example |
|---|---|---|
| **Static Structure** (hierarchies, taxonomies) | Binary Core relations (`PART_OF`, `IS_A`, `HAS_PART`) | `Chicago_Warehouse PART_OF Central_Region` |
| **Dynamic Flow** (movement, events, state changes) | Hub‑and‑spoke Synapses with `HAS_TIME`, `HAS_LOCATION` | `Truck T-771 arrive St. Louis at 14:30` |

*   **Entity Minting:** Rows become `corp.*` instances (e.g., `corp.cell_tower.TWR-042`) directly tethered to the Core Lexicon via `IS_A`.
*   **Cross‑source Queries:** Because GLEAN and the DB Adapter share the same canonical IDs, a single query can join a contract extract with a network inventory extract seamlessly. The KG does not know which pipeline produced the data.

---

## The Pivot: Synapedia Core Lexicon

The bootstrapped, shared reference for entity resolution. This is the **L0** that makes the pivot strategy work.

| Source | Size | License | Tier |
|---|---|---|---|
| Open English WordNet 2025 | ~200K synsets | CC‑BY‑4.0 | `CORE_DEFINITION` |
| Kaikki Wiktionary (English) | ~1.7M entries | CC‑BY‑SA‑3.0 | `LEXICAL_EXTENSION` |
| Simple English Wikipedia | ~100K abstracts | CC‑BY‑SA‑4.0 | `CORE_KNOWLEDGE` |

**Canonical ID:** `en.{lemma}.{microgloss}.{pos}.{namespace}`

**BFO Categories:** Every entry receives a derivable BFO category annotation (Independent Continuant, Quality, Role, Disposition, Process, etc.), ensuring all exported data is BFO‑conformant.

**The Living Lexicon:** Three triggers call the shared `mint_entry()` function:
1.  **Ontology Gap:** Missing parent / part discovered during enrichment.
2.  **Compound:** Multi‑word phrase passes the "remove‑clause" test and the "functional role" test.
3.  **Sense Discovery:** Background HDBSCAN clustering of the Usage Ledger discovers a new sense of an existing lemma.

**The Ghost Protocol:** When a term cannot be resolved, the system creates a **Ghost** (provisional node, TTL 30 days). It is marked `UNKNOWN`, never enters the reasoning core, and waits for resolution or expiry.

---

## The Alignment Engine: SOAM

SOAM is SGF's answer to the **Rosetta Stone** problem. It aligns concepts deterministically, producing either a **ProofTrace** (verified match) or a **GapReport** (structured failure).

### The NASA Screwdriver Problem (The Motivation)

A procurement officer ordered a "flight‑qualified torque driver". The system returned three candidates. The officer guessed. The wrong (atmospheric‑only) part shipped to the ISS. The cost to send the correct screwdriver on the next resupply: **one billion dollars**.

Current systems cannot solve this because they cannot *verify*. They can only guess, rank, and recommend. SOAM is the verification layer.

### The Four Theodore Roosevelts (Entity Resolution, Three‑Axis Theorem)

Four entities share the name "Theodore Roosevelt". The **Y‑axis** (ontology: `IS_A person`) cannot distinguish them. The **P‑axis** (properties: `HAS_ATTRIBUTE birth_year`) fails if documents lack dates. The **X‑axis** (events: "charged up San Juan Hill") uniquely identifies TR Jr.

**Theorem:** Entity resolution requires three irreducible axes. No two are sufficient. The Synaptic Lexicon integrates all three.

### The Ontology Alignment Strategy (The Pivot)

Instead of aligning `Org_A` directly to `Org_B` (N² cost), SGF aligns each to the Synapedia Core Lexicon (L0):

```
org_A:torque_screwdriver → SOAM → en.flight_qualified_torque_driver
org_B:flight_qualified_torque_driver → SOAM → en.flight_qualified_torque_driver
```

The **Bridge Map** stores the verified alignment. Integration cost is **N‑to‑1**, never N‑to‑N. This is the architectural mechanism that dismantles the Babel Tax.

### Deep Search (Beyond Lemma + Embedding)

Most search stops at lemma + embedding. SGF goes deeper. The **18‑slot schema** allows structural comparison during a search:

| # | Slot | Source | Depth |
|---|---|---|---|
| 1–3 | IS_A (parent, grandparent, great‑grandparent) | Binary relation (Y‑axis) | Walked DAG |
| 4–5 | HAS_PART (essential, optional) | Binary relation (Y‑axis) | Set check |
| 7–8 | HAS_ATTRIBUTE (structural, definitional) | Thematic role (P‑axis) | Embedding + metric |
| 12 | RELATES_TO | Generic verb (P‑axis) | Resolved to pivot |
| 13–17 | CONSTITUTIVE_EVENT | Hub‑and‑spoke (X‑axis) | Event alignment |
| 18 | **BFO_CATEGORY** | Derived | Formal ontological check |

A search for "titanium torque driver" does not just look at embeddings. It checks if the candidate's `IS_A` chain matches `tool → fastener_tool → torque_driver`. It checks if `HAS_ATTRIBUTE` includes `material=titanium`. It checks if the candidate was used in high‑temperature applications (`HAS_REASON`). This is deterministic slot‑by‑slot matching, not probabilistic vector similarity.

### Three Execution Modes / Three Depth Levels

The **Decider** selects the mode based on consequence and confidence.

| Mode | Level | Depth | Latency | Certainty |
|---|---|---|---|---|
| **Fast Path** (Browsing) | L1 | Embedding Fingerprint | ~1ms | Probabilistic |
| **Clarification** (Medium) | L1 + Q&A | Fingerprint + Ask Sender | ~10ms + round trip | Interaction |
| **Verified Path** (High) | L2/L3 | L2: 1‑level IS_A + Attributes. L3: Recursive to Primes. | ~10ms–1s | Deterministic |

**Bidirectional Bisatisfiability:** Every slot comparison is tested in both directions. A concept that is a superset of the other is a failure. Asymmetric alignment is detected and refused.

### ProofTrace vs. GapReport

| Outcome | Content | When |
|---|---|---|
| **ProofTrace** | Verifiable record of every comparison. Signed SHA‑256 digest. | Alignment passes. |
| **GapReport** | Structured failure. `failing_slot`, `expected_ref`, `observed_ref`, `failure_reason`, `suggested_action` (`sender_action`). | Alignment fails. |

**A GapReport is not a `500 Internal Server Error`. It is a typed `REFUSE` with a roadmap for the sender.** The sender receives explicit guidance on how to fix the mapping — not an opaque rejection.

### Privacy‑Preserving Verification

Two organisations with different Exact Profile Contracts can compare 86‑character fingerprints to prove equivalence without exposing proprietary data. The protocol:
1.  Agency publishes spec fingerprint.
2.  Supplier computes local fingerprint from internal design.
3.  Supplier exports only the fingerprint + pass/fail metric flags.
4.  Agency verifies Hamming distance.
5.  Conclusão: Compliance proven without exposing trade secrets.

---

## The Knowledge Graph Schema & Export

| Form | Role | Carries |
|---|---|---|
| **Synapse** (Hub‑and‑Spoke) | **Source of Truth** | Verb hub, 15 roles, frame, provenance, epistemic status, BFO category |
| **SynapseLink** (Binary Edge) | **Query Optimisation** | Subject, predicate, object, confidence, source Synapse ID |

**Projection Rule:** ≤3 populated roles → projected as binary edge. >3 roles (complex event) → remains as full Synapse. No information loss.

**Hybrid Storage:**
- **Events** (actions, transactions) → Synapses.
- **Static Descriptions** (customer records, catalog items) → EAV Triples (subject, predicate, object). No verb hub wasted on static data.

**Export Adapters:**
| Backend | Format | Frame Preservation |
|---|---|---|
| **Neo4j** | Cypher (MERGE) | `:Frame` nodes connected via `:HAS_FRAME` |
| **Stardog / GraphDB** | Turtle + SPARQL INSERT | RDF‑star annotations or named graphs |
| **TypeDB** | TypeQL insert | Native n‑ary relation attributes |
| **Kuzu** | Cypher (Kuzu‑native) | Frame nodes |
| **Neptune** | SPARQL or Gremlin | RDF‑star or Gremlin properties |

**High‑Frequency Data Pattern:** Event Store (Kuzu/ClickHouse, append‑only) + Snapshot Store (Neo4j, upsert). Bridge: `SELECT entity_id, LAST(value) FROM events GROUP BY entity_id`.

---

## Comparison with RDF/OWL

| Concern | RDF/OWL | SGF |
|---|---|---|
| **Predicate Model** | Open — anyone invents a URI | **Closed — ~38 primitives** |
| **Integration Cost** | N² — every partner needs a new mapping | **N‑to‑1 — align to the Core Lexicon via SOAM** |
| **Event Representation** | Reification (heavy, non‑standard, loses n‑arity) | **Native n‑ary Synapses (15 roles, standard)** |
| **Meaning Grounding** | Recursive URIs (terminates at `owl:Thing`, a logical axiom) | **Finite Bedrock (~65 NSM primes + NIST constants)** |
| **Vocabulary Evolution** | Static ontology (manual updates) | **Living Lexicon (auto‑discovers from usage)** |
| **Provenance** | Optional, non‑standard | **Mandatory (byte‑offset, epistemic status, derivation tag)** |
| **Federation** | Open‑world assumption (anything can be asserted) | **Receiver sovereignty (policy‑gated admission)** |
| **Transparency of Failure** | Silent failure or error | **ProofTrace (pass) or GapReport (actionable failure)** |

---

## Repository Layout

```
sgf/
├── README.md                         # This file
├── synapedia/                        # Lexicon bootstrapping pipeline
│   ├── import_wordnet.py             # WordNet → wordnet.db
│   ├── import_wiktionary.py          # Kaikki JSONL → wiktionary_raw.db
│   ├── import_wikipedia.py           # Wikipedia dumps → synapedia.db
│   ├── postprocess.py                # Microglosses, canonical IDs, BFO categories
│   ├── compute_embeddings.py         # BGE‑M3 embeddings
│   └── synapedia_mint.py             # Shared minting function
├── glean/                            # Prose‑to‑graph compiler
│   ├── compile_document.py           # Top‑level orchestrator (21 stages)
│   ├── defluffer.py                  # Stage 0: remove filler
│   ├── entity_census.py              # Entity identification + resolution
│   ├── clause_to_synapse.py          # Clause extraction → Synapses
│   ├── framing.py                    # Epistemic framing
│   ├── synapse_grouper.py            # Discource grouping
│   ├── synapse_store_persist.py      # Persist to DB
│   ├── dep_to_role.json              # Dependency‑to‑role mapping
│   ├── reporting_verbs.txt           # Verbs triggering attribution‑based POV
│   └── pos_rosetta.json              # spaCy POS → SGF POS
├── db_adapter/                       # Data‑to‑graph pipeline
│   ├── adapter.py                    # CSV/TSV reader + YAML mapper
│   ├── yaml_parser.py                # YAML configuration parser
│   └── entity_minter.py              # Mint corp.* instances
├── search_server/                    # FastAPI search daemon
│   ├── search_server.py              # Daemon (port 8400)
│   ├── syn_search_adapter.py         # Ontology‑aware search client
│   ├── bm25_score.py                 # BM25 lexical scoring
│   ├── reranker.py                   # Cross‑encoder reranker
│   ├── lemma_resolver.py             # Surface‑form‑to‑lemma resolution
│   ├── llm_tiebreaker.py             # LLM‑of‑last‑resort
│   ├── llm_wrapper.py                # Single‑file LLM caller
│   └── search_config.toml            # Configuration
├── embedder/                         # BGE‑large ONNX service
│   └── embed_service.py              # Service (port 18401)
├── exporters/                        # Export adapters
│   ├── glean_export_cypher.py        # → Neo4j (Cypher, MERGE)
│   ├── glean_export_sparql.py        # → Stardog/GraphDB (SPARQL INSERT, Turtle)
│   └── (other adapters planned)      # TypeDB, Kuzu, Neptune
├── soam/                             # Alignment engine (in development)
└── config/
    └── sgf.toml                      # Global configuration
```

---

## Quick Start

```bash
# 1. Build the Core Lexicon
cd synapedia
python import_wordnet.py
python import_wiktionary.py
python import_wikipedia.py
python postprocess.py
python compute_embeddings.py

# 2. Start the Services
# Terminal 1:
python embedder/embed_service.py --db synapedia.db --port 18401
# Terminal 2:
python search_server/search_server.py --lexicon synapedia.db --port 8400

# 3. Compile a Document
cd glean
python compile_document.py \
  --input beethoven.txt \
  --doc-id beethoven_001 \
  --accuracy-mode standard \
  --search-server http://localhost:8400

# 4. Export to Neo4j or Stardog
# Neo4j:
python exporters/glean_export_cypher.py \
  --input synapse_store.db \
  --main-lexicon synapedia.db \
  --parent-depth 1 \
  --output beethoven.cypher

# Stardog:
python exporters/glean_export_sparql.py \
  --input synapse_store.db \
  --main-lexicon synapedia.db \
  --parent-depth 1 \
  --output beethoven.ttl \
  --format turtle
```

---

## License & Patent Pledge

**Apache 2.0.** Free to use, modify, redistribute, including commercially.

**Patent Pledge:** The author vows to never patent the SGF architecture. This is a personal commitment, not a legal instrument, but it reflects the intent that this infrastructure remain open for all.

---

*The grammar is closed at ~38 primitives. The vocabulary is infinite. A dictionary accepts any word. A proof substrate requires every word to earn its place — and to earn the right to be seen, trusted, scaled, retained, and appealed.*
