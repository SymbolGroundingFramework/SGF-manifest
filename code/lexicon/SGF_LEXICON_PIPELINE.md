# SGF Lexicon Pipeline — Architecture and Specification

**Author:** James Lee Stakelum
**Status:** Production specification — what / why / how

This document specifies the SGF lexicon build pipeline end to end:
the architectural commitments that drive it, the twelve build stages
that produce a multilingual semantic lexicon from a Wiktextract JSONL
dump, the structured metadata it captures, the two-pass embedding
architecture, the cluster-discovery and standard-form-selection passes
that make register-aware retrieval possible, the ontology / semantic-role
layer that records taxonomic and compositional relations, and the
retrieval policies that consume all of the above.

It serves two audiences:

- **The owner of this codebase**, returning to the project weeks or
 months later and needing to remember every architectural decision
 and the reasoning behind it.
- **An engineer reading this on GitHub** who wants to understand,
 extend, or customize the pipeline for their own corpus.

Every major decision is stated with WHAT (the choice), WHY (the
reasoning), and HOW (the implementation). The Decision Log in Part 11
restates the WHY in one place for fast retrieval. Spec sections give
exact schemas, vocabularies, and algorithms.

---

## Table of Contents

0. [What This Is and Why It Exists](#part-0-what-this-is-and-why-it-exists)
1. [Architecture & Commitments](#part-1-architecture--commitments)
2. [Shared Vocabularies](#part-2-shared-vocabularies)
3. [The 12-Stage Build Pipeline](#part-3-the-build-pipeline)
4. [The Improvement Pass (Stage 6) Deep Dive](#part-4-the-improvement-pass)
5. [Cluster Discovery & Standard-Form Selection (Stages 9-10)](#part-5-cluster-discovery--standard-form-selection)
6. [Ontology & Semantic Relations (Stage 11)](#part-6-ontology--semantic-relations)
7. [Retrieval Policies](#part-7-retrieval-policies)
8. [Schema Reference](#part-8-schema-reference)
9. [Quality Audit & Self-Retrieval Criterion](#part-9-quality-audit)
10. [LLM Operational Concerns](#part-10-llm-operational-concerns)
11. [Decision Log](#part-11-decision-log)
12. [Glossary](#part-12-glossary)
13. [Extension Points](#part-13-extension-points)
14. [Incremental Bootstrap and the Maturity Frontier](#part-14-incremental-bootstrap)
15. [Interactive Use via the Search Server (incl. content fingerprints)](#part-15-interactive-use)
16. [Performance Commitments](#part-16-performance-commitments)

---

## PART 0: What This Is and Why It Exists

### 0.1 The problem

A lexicon is the floor a language-processing system stands on. If the
floor is missing, every layer above it improvises. LLMs improvise so
fluently that the improvisation is invisible — until you need
repeatable behavior across languages, domains, and use cases. Then
the missing floor shows.

The SGF lexicon is the floor for the GLEAN compiler (which turns
prose into synapses), for cross-language retrieval, and for any tool
that needs to ground a token in source text to a specific sense.
Every downstream component assumes the lexicon exists and behaves
consistently. That assumption has to be earned by the lexicon, not
delegated to whichever LLM happens to be in the loop.

### 0.2 What this pipeline produces

A single SQLite database (`sgf_lexicon.db`) where every sense has:

- A short `microgloss` that disambiguates it from its siblings
- A stable `canonical_id` of the form
 `<lang>.<lemma>.<microgloss>.<pos>.<namespace>`
- Four axes of structured metadata: `register`, `temporal_status`,
 `social_status`, and `specificity` (general vs specialist vs
 technical)
- Two embeddings: a cheap diagnostic pass and a production pass
- Membership in content-identical groups (where one member is the
 standard form for snap-to-standard retrieval)
- Outgoing semantic relations (IS_A, HAS_PART, and the 15 SGF
 semantic roles)

This is the contract every downstream component reads against. Once
built, the lexicon is a long-lived artifact — you regenerate parts of
it when Wiktionary updates or when you expand the maturity frontier,
not every time you want to query it.

### 0.3 What you do NOT have to build on day one

The maturity-tier system (Part 14) lets you bootstrap a working
lexicon with the top 5,000 lemmas and expand later. The pipeline is
idempotent at every stage: re-running on an expanded scope adds the
new work without redoing the old work. You can ship a usable lexicon
in an afternoon, then deepen and broaden it over weeks.

### 0.4 Who this is for

Three audiences:

- **GLEAN engine builders.** You need the lexicon as a black-box
 service. Read Parts 7 and 15. Skim everything else.
- **Lexicon engineers.** You are maintaining or extending the
 pipeline itself. Read everything, especially Parts 3-6, 9, 11.
- **Researchers integrating the lexicon into other tools.** Read
 Parts 0-2 and 13.

### 0.5 Quick start

The pipeline has three named phases. Run them in order. Phase 1 is
required. Phase 2A and Phase 2B are each optional, idempotent, and
can be re-run to expand the frontier.

```
# Phase 1: bootstrap. No LLM. Ends with a queryable lexicon at embedded_v1.
python run_frontier.py --config bootstrap_no_llm.toml

# Phase 2A: improve microglosses + metadata + production embeddings on top-N.
python improve_lexicon.py --target sgf_lexicon.db --llm-wrapper llm_wrapper.py --top-lemmas 1000

# Phase 2B: build the relation graph (clusters + standard forms + 17 relations).
python build_relations.py --target sgf_lexicon.db --llm-wrapper llm_wrapper.py --top-lemmas 1000
```

Phase 2A and Phase 2B are independent. You can run either alone, in
either order. Running Phase 2A first is recommended because sharper
microglosses improve Phase 2B's cousin discovery and relation-target
resolution. Both Phase 2 runners support `--revisit` to re-process
already-processed senses (for example, after improving the LLM
wrapper).

For the full stage-by-stage manual sequence, see the Reference Recipe
at the end of this part. For the incremental-expansion workflow
(top 5K -> 20K -> 50K), see Part 14, which also includes the formal
Phase 1 / Phase 2A / Phase 2B mental model in section 14.8.

### 0.6 Reference Recipe: full manual pipeline

This is the same sequence the frontier orchestrator runs internally.
Use it when you want explicit control of each stage:

```powershell
# One-time install
pip install onnxruntime-directml tokenizers huggingface_hub numpy faiss-cpu

# Schema (one time, idempotent)
Get-Content schema.sql | sqlite3 sgf_lexicon.db

# Wiktionary ingest (one time)
python load_wiktionary_jsonl.py
python build_wiktionary_source.py --target sgf_lexicon.db --source wiktionary_lexicon.db
python build_sgf_lexicon.py --target sgf_lexicon.db

# Lemma frequency rankings (one time, ~30 MB download)
python load_lemma_frequency.py --target sgf_lexicon.db

# Stage 3: deterministic microgloss + metadata harvest
python generate_microglosses.py --target sgf_lexicon.db

# Stages 4-5: first-pass embedding (diagnostic, bge-small)
python build_embedding_texts.py --target sgf_lexicon.db --pass v1
python compute_embeddings.py --target sgf_lexicon.db --embedding-method bge-small-en-v1 --device dml

# Stage 5.5: audit first-pass self-retrieval quality
python quality_audit.py --target sgf_lexicon.db --embedding-method bge-small-en-v1 --audit-phase first_pass

# Stage 6: LLM improver (refines microglosses, declares
# content-identical, populates metadata including specificity)
python improve_microgloss.py --target sgf_lexicon.db --llm-wrapper C:\path\to\llm.py --top-lemmas 5000

# Stages 7-8: production embedding (bge-large)
python build_embedding_texts.py --target sgf_lexicon.db --pass v2
python compute_embeddings.py --target sgf_lexicon.db --embedding-method bge-large-en-v1 --device dml

# Stage 8.5: audit production self-retrieval (ship gate: 99% relaxed)
python quality_audit.py --target sgf_lexicon.db --embedding-method bge-large-en-v1 --audit-phase production

# Stage 9: discover content-identical groups (resumable)
python discover_clusters.py --target sgf_lexicon.db --embedding-method bge-large-en-v1

# Stage 10: pick the standard form per group
python select_standard_forms.py --target sgf_lexicon.db --embedding-method bge-large-en-v1 --llm-wrapper C:\path\to\llm.py

# Stage 11: harvest semantic relations
python harvest_semantic_relations.py --target sgf_lexicon.db --llm-wrapper C:\path\to\llm.py --top-lemmas 5000

# Optional Stage 12: per-sense fingerprints (cache-invalidation hash)
python compute_sense_fingerprints.py --target sgf_lexicon.db --embedding-method bge-large-en-v1
```

What you get at the end: a multilingual-ready lexicon where every
sense in scope has a microgloss, a canonical_id, four axes of
structured metadata, first-pass and production embeddings,
content-identical groupings with designated standard forms, and
populated semantic relations. The lexicon supports the
`snap_to_standard` and `preserve_register` retrieval policies and
serves both intra-language grounding and cross-language retrieval.
---

## PART 1: Architecture & Commitments

The pipeline rests on a small number of load-bearing commitments. They
are restated throughout the document because they shape every other
decision. If any of them changes, large portions of the architecture
need to be revisited.

### 1.0 Metadata captures typical-use propensity

The structured fields (register, temporal_status, social_status,
specificity) describe how a sense is *typically* used and received.
They are propensities, not absolute properties of the word. The word
"damn" reads as vulgar in a corporate memo, theological in a sermon,
and unmarked in a 19th-century novel's reported speech. The lexicon
tags the typical-use propensity; downstream tools that have access
to the actual context apply runtime adjustments.

This is a clean separation of concerns. The lexicon catalogs typical
usage. Runtime systems (GLEAN, the search server, retrieval
policies) apply contextual refinement using document-level signals
(era, domain, genre, speaker identity, surrounding register). Without
this separation the lexicon would be either context-blind or forced
to enumerate every possible context.

### 1.1 The lexicon records the language

Every term that appears in the language is cataloged: formal,
neutral, informal, slang, dialect, period vocabulary, archaic
terms, technical jargon, and the full range of marked vocabulary any
serious lexicographer treats as part of the linguistic record. The
Oxford English Dictionary does this. Merriam-Webster does this.
Wiktionary does this. The SGF lexicon follows the same descriptive
principle.

The lexicon stays neutral about what exists. Decisions about what to
surface in a given context are made by retrieval policies (Part 7).
A dictionary lookup at default settings returns the standard form.
A grounding pass on a historical document grounds the surface lemma
the writer actually used. Each policy is appropriate to its use case;
all are served by the same neutral lexicon.

### 1.1.1 Specificity and the leukemia rule

Specificity is a fourth metadata axis, separate from
register. Where register asks "how formal?", specificity asks "how
precise within a domain?".

- `general` — used by ordinary speakers without domain training
- `specialist` — used within a recognized field (medicine, law,
 science, engineering, finance) to make a precision distinction
 the general term elides
- `technical` — subspecialty vocabulary within a specialist field

The default retrieval policy treats specialist terms as
non-snappable. "Leukemia" stays "leukemia" rather than being snapped
to "cancer," because the writer who chose "leukemia" was making a
precision claim that "cancer" loses. This is not a register
difference; it is a content difference. Specialist terms participate
in semantic relations (`leukemia IS_A cancer`) but not in
content-identical groups at the general audience tier.

### 1.2 Microgloss serves four jobs simultaneously

**WHAT:** Every microgloss must accomplish four things at once:

1. **Disambiguate** the sense from other senses of the same lemma
2. **Provide bag-of-words signal** for the embedder so the sense
 lands in the right region of embedding space
3. **Read naturally** to a human scanning a canonical_id
4. **Carry enough information** that an LLM doing rerank can
 distinguish this sense from candidates without reading the full
 gloss

**WHY:** The microgloss appears in canonical_id (which is in turn
embedded), is surfaced to humans (in any user-facing output that
references senses by ID), and is read by LLMs during disambiguation
rerank. Optimizing for any one of these at the expense of the others
produces a brittle lexicon.

**HOW:** When constraints conflict, prefer solutions that satisfy all
four jobs. Length is a *consequence* of disambiguation needs, not a
target. A 2-token microgloss is correct when 2 tokens suffice; a
5-token microgloss is correct when 5 tokens are needed. The
microgloss generator (Stage 3) is constrained algorithmically, and
the LLM improver (Stage 6) refines microglosses for senses where the
deterministic output fails the self-retrieval quality criterion (Part 9).

### 1.3 Microgloss is content-only by default; extended only where measurement demands

**WHAT:** Microglosses encode content meaning, not metadata. Register,
temporal status, social status, and other metadata axes live in
structured columns, not in microgloss tokens. The default form for the
sense "dame (a woman)" is microgloss `adult_female_human`, not
`adult_female_human_dated_slang`.

**WHY:** Embedders treat tokens as content tokens regardless of intent.
If `slang` appears as a microgloss token, the embedder pulls the sense
toward other slang-tagged senses across all topics. Microgloss content
purity protects topical embedding quality.

**HOWEVER (the realistic asterisk):** The self-retrieval quality
criterion (Part 9) demands that embedding a canonical_id retrieves the
sense at top-1 in cosine search. For some senses with very close
cross-lemma cousins (lady / dame / lass / gal all sharing
`adult_female_human`), content-only microgloss is empirically insufficient.
For those senses, the improver MAY extend the microgloss with a
disambiguating marker from a controlled vocabulary:

- Register markers: `_slang`, `_informal`, `_archaic`, `_poetic`, `_clinical`
- Era markers: `_1950s`, `_1960s_70s`, `_victorian`, `_early_modern`
- Evaluation markers: `_attractive`, `_derogatory`, `_pejorative`
- Dialect markers: `_british`, `_american`, `_australian`
- Domain markers: `_aviation`, `_finance`, `_medical`

The minimum extension that achieves self-retrieval is the right one.
Most senses never need extension; a small minority do.

**HOW:** Stage 3 produces content-only microglosses by default. Stage
5.5 (quality audit) identifies senses that fail self-retrieval. Stage
6 (improver) extends the microgloss for those senses using markers
from the controlled vocabulary above. Stage 8.5 re-audits; the
extension is locked in if the sense now passes.

### 1.4 Stage 3 (deterministic) is load-bearing for ~95% of senses

**WHAT:** The deterministic microgloss generator (Stage 3) is the
production system for the long tail of the lexicon. Only top-N
high-frequency or polysemous senses (~130-160K out of 1.76M) go
through the LLM improver. The remaining ~1.6M senses live their entire
production life on Stage 3 output.

**WHY:** Improving all 1.76M senses with an LLM is prohibitively
expensive and takes weeks of wall-clock time even with a fast
affordable LLM. Improving the top-N is bounded and finishes in
hours-to-days. The implication is that Stage 3 quality is not
optional -- it IS the lexicon's quality for most senses.

**HOW:** Stage 3 uses the sibling-IDF algorithm in `microgloss.py`
augmented with deterministic metadata harvest from Wiktionary
tags (Part 2.6-2.8). The combination produces high-quality output for
senses where Wiktionary's structural data is reasonable. Sparse-data
senses (no tags, no examples, no etymology, no linkages) are flagged
for the improver because Stage 3 has little to work with.

### 1.5 Two-pass embedding architecture

**WHAT:** Embeddings are computed in two passes. First pass uses
BGE-small (33M params, 384-dim) for diagnostic purposes — it serves
the improver and the cluster-discovery stage. Second pass uses
BGE-large (335M params, 1024-dim) for production embeddings used at
retrieval time.

**WHY:** The first pass needs to be cheap and fast (it serves
auxiliary purposes — cousin discovery, cluster discovery, quality
audit). Production retrieval quality justifies the larger model. The
two-pass approach allows the improver to use a directionally-correct
embedding space (first pass) when deciding what to refine, then
production-quality embeddings (second pass) take advantage of the
improver's refinements.

**HOW:** `compute_embeddings.py` supports multiple `--embedding-method`
values, each stored independently in `sense_embedding` keyed by
`(wsid, embedding_method)`. The first pass writes
`bge-small-en-v1` rows; the second pass writes `bge-large-en-v1` rows.
Both live side by side. Retrieval picks the appropriate method.

### 1.6 Two-stage retrieval

**WHAT:** Retrieval is structured in two stages. Stage A is cosine
similarity over production embeddings, returning top-K candidates fast
(milliseconds). Stage B is an LLM rerank invoked only when Stage A's
top-1 score is low or its margin over top-2 is small, returning a final
selection with rationale.

**WHY:** Embedding-only retrieval is fast but imprecise on hard cases.
LLM-only retrieval is precise but expensive and slow. The hybrid
captures most of the precision benefit at a small fraction of the
cost: Stage B fires on roughly 5-15% of queries, depending on the
configured thresholds.

**HOW:** A retrieval pipeline component invokes Stage A, examines the
top-1 score and top-1 vs top-2 margin, and decides whether to invoke
Stage B. Stage B receives the top-K candidate canonical_ids plus
microglosses plus brief gloss text; the LLM returns the chosen
canonical_id plus a one-sentence rationale.

### 1.7 Universal vocabulary across languages

**WHAT:** Every language's lexicon uses the same English-language
tokens for microgloss content and for the controlled metadata
vocabularies (register, temporal_status, social_status, semantic
roles). Cross-language alignment works via shared embedding-space
structure: a Japanese canonical_id like
`ja.おやじ.male_parent.noun.core` shares the tokens `male_parent`
with the corresponding English `en.dad.male_parent.noun.core`.

**WHY:** Cross-language retrieval needs a shared substrate. Localizing
microgloss vocabulary per language would prevent embedding-space
alignment and force per-language-pair scoring rules. Universal English
vocabulary is the pragmatic shared substrate; lemmas remain in source
language, definitions are translatable, but the disambiguation handles
(microglosses) are universal.

**HOW:** All controlled vocabularies in Part 2 are English. Future
non-English lexicons follow the same conventions. This is an
architectural commitment, not a localization choice.

### 1.8 Self-retrieval as the quality criterion

**WHAT:** The lexicon's correctness is measured by the self-retrieval
test: for every sense, embedding the canonical_id alone must retrieve
that sense at top-1 in cosine search across the entire lexicon. The
ship threshold is 99% pass rate (relaxed — see Part 9).

**WHY:** Self-retrieval is a falsifiable, automatable test that
captures both criteria you'd naively want (LLM-readable AND
embedder-discriminable) in a single measurement. If the canonical_id
can't retrieve its own sense, either the microgloss is underspecified
or the embedding-space neighborhood is genuinely identical (which
requires explicit content-identical group declaration to handle
gracefully).

**HOW:** `quality_audit.py` measures self-retrieval pass rate across
the lexicon (or a sample). The improver targets failures explicitly.
The cluster-discovery stage builds content-identical groups so the
audit can apply the relaxed pass criterion (top-1 is either self OR a
content-identical neighbor).

### 1.9 Content-identical groups are first-class data

**WHAT:** When two or more senses share content with no meaningful
distinction (turquoise/aquamarine for general audience; lift/elevator
across dialects; chilly/cold at mild intensities), the lexicon
explicitly records them as a content-identical group. Each group has a
designated standard form (e.g., "child" is the standard for
{child, kid, kiddo, tot, youngster}).

**WHY:** Snap-to-standard retrieval requires knowing which form in a
content-identical group is the unmarked standard. This is not derivable
from frequency alone (kid > child in conversational frequency, but
child is the standard form). Explicit declaration is required.

**HOW:** Stage 9 (`discover_clusters.py`) finds content-identical
groups via a hybrid approach: improver-declared relations, Wiktionary
linkages, and post-hoc embedding clustering. Stage 10
(`select_standard_forms.py`) uses metadata filtering + LLM judgment to
pick the standard form per group. Both stages support audience-tier
parameterization (a group can be content-identical at general-audience
tier but distinct at expert tier).

### 1.10 Ontology and semantic relations are a distinct pipeline phase

**WHAT:** The lexicon includes a structured ontology layer that
records two ontological relations (IS_A, HAS_PART) plus the 15 SGF
semantic roles. The 15 semantic roles split into 6 Core roles
(HAS_AGENT, HAS_PATIENT, HAS_THEME, HAS_EXPERIENCER, HAS_RECIPIENT,
HAS_BENEFICIARY) that define event participants, and 9 Context roles
(HAS_TIME, HAS_LOCATION, HAS_SOURCE, HAS_DESTINATION, HAS_MANNER,
HAS_INSTRUMENT, HAS_CAUSE, HAS_REASON, HAS_ATTRIBUTE) that define
the surrounding circumstances. See Part 2.5 for the full vocabulary
with definitions and examples. This is Stage 11.

**WHY:** Downstream consumers (GLEAN, search policies, knowledge-graph
tools) benefit from explicit relational structure. "Strawberry
HAS_PART seeds" is not derivable from gloss text alone. The relations
are too structured to discover via embedding similarity; they need
explicit harvesting.

**HOW:** A hybrid harvester (Stage 11): Wiktionary linkages provide
IS_A and HAS_PART signals where present (hypernym/meronym linkage
types); gloss pattern-matching catches additional cases; the LLM fills
gaps for in-scope senses.

**NOTE:** The 15 roles listed above are the standard SGF set as best
known to me at the time of writing. The authoritative SGF spec defines
this vocabulary; if your spec differs, update the
`SEMANTIC_ROLES` constant in `lexicon_metadata.py` (a single change
that propagates throughout the pipeline) and re-document the role
semantics in this spec's Part 2.5.

---

## PART 2: Shared Vocabularies

This is the single source of truth for controlled values used
throughout the pipeline. Adding a new value here is a schema change
and must be done deliberately. All values are referenced in
`lexicon_metadata.py` which serves as the executable single source of
truth for code.

### 2.1 register (9 values)

**Definition:** The social register the sense occupies when in active
use. Captures the social context, not the topic or the time.

| Value | Definition | Examples |
|---|---|---|
| `formal` | Academic, legal, official prose | patriarch, expedite, heretofore |
| `neutral` | Unmarked default; newspaper, novel, school report | father, send, however |
| `informal` | Conversational, friendly, casual | dad, ship out, but |
| `slang` | In-group, often generational | pops, lit, yeet |
| `vulgar` | Taboo or profane in modern register | (examples omitted; see lexicon_metadata.py for the full list) |
| `affectionate` | Diminutives, intimate-family register | daddy, sweetie, kiddo |
| `poetic` | Literary, elevated, deliberately marked | thee, morn, yon |
| `clinical` | Medical or scientific neutral-register | urinate, myocardial, edema |
| `archaic` | Historical, fallen out of active use | forsooth, prithee, pater |

### 2.2 temporal_status (5 values)

**Definition:** Where the sense is in its usage lifecycle. Distinct
from register: a word can be neutral-register AND archaic
("forsooth" was neutral in its time but is archaic now).

| Value | Definition |
|---|---|
| `live` | Currently in active use |
| `dated` | Feels old-fashioned but not archaic; still used occasionally |
| `archaic` | Out of active use; appears in period writing or pastiche |
| `obsolete` | No longer used or understood without special knowledge |
| `revived` | Was archaic or obsolete but has come back into use (e.g., "wireless" for networking) |

### 2.3 social_status (6 values)

**Definition:** How the sense is received in modern careful usage.
Distinct from register: vulgar register doesn't necessarily mean
offensive social_status (some vulgar-register terms are unmarked
socially, others are flagged).

**Important caveat:** These values capture the *typical* social
reception of a term in *modern* usage as a default prior. A term
tagged `vulgar` in modern register may have been neutral in
historical contexts, may be neutral in domain-specific contexts
(theological, medical, legal), and may have register-shifted under
reclamation by an in-group. The structured tag is the default; a
runtime system with access to document context (era, domain, genre,
speaker identity, surrounding register) should apply
context-specific adjustment before making policy decisions. See
Part 1.0 for the architectural rationale.

| Value | Definition | Retrieval-time penalty |
|---|---|---|
| `unmarked` | No social baggage; use freely | 0 |
| `informal_only` | Fine in casual contexts; avoid in formal writing | small |
| `dated` | Feels old-fashioned but not offensive | small |
| `flagged` | Many readers find this objectionable; use with care | large |
| `offensive` | Most readers find this objectionable; quotation/reportage only | very large |
| `slur` | Targets a specific identity group with intent to harm | effectively excludes from suggestion |

**Why `offensive` and `slur` are distinct:** A slur targets a specific
identity group (ethnic, sexual, religious). Offensive covers broader
objectionable language not tied to a protected group. The search
policy treats slurs with the most caution because their potential
harm is most acute.

### 2.4 cousin_relation_type (11 values)

**Definition:** When the improver classifies how a cousin sense
relates to the sense being processed, it picks one of these values.
Used by retrieval policies and by cluster discovery.

| Value | Definition | Example (where source = "car") |
|---|---|---|
| `TRUE_SYNONYM_CONTENT_IDENTICAL` | Same content; differs only in dialect or non-meaning-bearing register | "automobile" (formal-register variant), "auto" (informal-register variant) |
| `TRUE_SYNONYM_REGISTER_VARIANT` | Same referent; register differs in a meaning-bearing way | (less common for "car"; example: father→pops is register variant) |
| `SHADED_SYNONYM` | Same general content, real but small nuance | "vehicle" (broader scope) |
| `COHYPONYM` | Sibling category under a common parent | "truck", "motorcycle" |
| `HYPONYM` | This sense is a TYPE_OF the cousin | (if source were "sedan", "car" would be hypernym) |
| `HYPERNYM` | The cousin is a TYPE_OF this sense | "vehicle" |
| `PART_OF` | The cousin is a part or component of this sense | "engine", "wheel" |
| `AGENT_OF` | The cousin is the agent that uses/operates this sense | "driver" |
| `LOCATION_OF` | The cousin is where this sense typically appears | "highway", "garage" |
| `EMBEDDER_NOISE` | Proximity in embedding space, no real semantic relation | (varies by lexicon) |
| `UNCLEAR` | Cannot determine from gloss alone | (varies) |

`TRUE_SYNONYM_CONTENT_IDENTICAL` and `TRUE_SYNONYM_REGISTER_VARIANT`
are the two new specializations of the existing `TRUE_SYNONYM`. The
distinction matters because:

- `TRUE_SYNONYM_CONTENT_IDENTICAL` pairs are eligible for the
 content-identical group system (Stage 9-10): they share a microgloss
 (or differ only minimally) and the standard-form selector picks one
 as the canonical representative.
- `TRUE_SYNONYM_REGISTER_VARIANT` pairs share content but the register
 difference is a meaningful authorial choice (father vs pops in a
 novel is signaling something). These should keep distinct
 microglosses or be extended with register markers.

### 2.5 Semantic roles and ontological relations

The SGF lexicon distinguishes three kinds of structured relations
between senses:

- **6 Core semantic roles** — define the participants of an event
- **9 Context semantic roles** — define the surrounding circumstances
 of an event
- **2 Ontological relations** — IS_A (taxonomy) and HAS_PART
 (composition)

All three are populated by Stage 11 (`harvest_semantic_relations.py`)
and stored in the same `sense_semantic_relation` table
(Part 8.7). The `relation_kind` column distinguishes them.

#### Core semantic roles (6) — event participants

These roles define WHAT happened: who did it, to what, for whom.
Every non-trivial event has at least one Core role; many have
several. Core roles describe the structural skeleton of the event.

| Role | Definition | Example |
|---|---|---|
| `HAS_AGENT` | The entity that deliberately initiates, performs, or controls the event | (write) HAS_AGENT (author) |
| `HAS_PATIENT` | The entity that undergoes a structural change of state, physical modification, or destruction | (burn) HAS_PATIENT (wood) |
| `HAS_THEME` | The entity that is moved, located, possessed, or held in a state without changing its internal structure | (send) HAS_THEME (package) |
| `HAS_EXPERIENCER` | The living entity that experiences a psychological, emotional, sensory, or non-deliberate somatic state | (fear) HAS_EXPERIENCER (child) |
| `HAS_RECIPIENT` | The destination entity that changes possession or receives a physical or informational object | (give) HAS_RECIPIENT (recipient) |
| `HAS_BENEFICIARY` | The entity for whose advantage, detriment, or sake the event is performed | (cook) HAS_BENEFICIARY (family) |

**Why these distinctions matter:** Patient, Theme, Recipient, and
Beneficiary look superficially similar but capture genuinely different
things. A Patient is structurally changed by the event (wood burns and
becomes ash). A Theme is moved or held without internal change (a
package gets sent but the package itself doesn't change). A Recipient
changes possession (someone receives a gift). A Beneficiary has the
event performed for their advantage (the family benefits from the
meal). Conflating these collapses meaningful distinctions that
downstream consumers (GLEAN, knowledge-graph tools, semantic search)
rely on.

#### Context semantic roles (9) — surrounding circumstances

These roles define WHEN, WHERE, HOW, WHY, and WITH WHAT the event
occurred. They describe the setting and modifiers of the event
rather than its participants.

| Role | Definition | Example |
|---|---|---|
| `HAS_TIME` | The temporal coordinate, span, frequency, or constraint anchoring the event | (meeting) HAS_TIME (Tuesday at 3pm) |
| `HAS_LOCATION` | The physical or logical spatial region, coordinate, or boundary holding the event | (concert) HAS_LOCATION (auditorium) |
| `HAS_SOURCE` | The physical, logical, or informational origin state from which an entity moves or derives | (depart) HAS_SOURCE (terminal) |
| `HAS_DESTINATION` | The physical, logical, or informational endpoint state toward which an entity moves | (arrive) HAS_DESTINATION (port) |
| `HAS_MANNER` | The operational style, speed, configuration, or quality of execution characterizing the event | (run) HAS_MANNER (quickly) |
| `HAS_INSTRUMENT` | The tool, device, or intermediary force leveraged by an agent to execute the event | (cut) HAS_INSTRUMENT (knife) |
| `HAS_CAUSE` | The inanimate physical force, environmental condition, or unintentional event that directly triggers the state change | (sunburn) HAS_CAUSE (sun_exposure) |
| `HAS_REASON` | The motivational purpose, legal mandate, or logical justification driving the agent's choice | (study) HAS_REASON (exam_preparation) |
| `HAS_ATTRIBUTE` | The descriptive property, constraint value, scope restriction, or scalar quality qualifying a node | (strawberry) HAS_ATTRIBUTE (sweet.flavor) |

**HAS_CAUSE vs HAS_REASON:** Cause is inanimate or unintentional (a
fire is caused by lightning; a fall is caused by ice). Reason is
intentional or justificatory (a person studies for an exam; a court
rules based on precedent). The distinction matters because Cause
describes physical or environmental triggers, while Reason describes
agentive motivation. A single event can have both: a person flees a
burning building — HAS_CAUSE = fire, HAS_REASON = self_preservation.

#### Ontological relations (2) — sense-to-sense structure

These describe taxonomic and compositional relationships between
senses themselves, independent of any event.

| Relation | Definition | Example |
|---|---|---|
| `IS_A` | Taxonomic hypernym; the sense is a type or instance of another sense | (calico_cat) IS_A (domestic_feline); (domestic_feline) IS_A (mammal) |
| `HAS_PART` | Compositional; the sense includes another sense as a component, constituent, or anatomical part | (strawberry.fruit_plant) HAS_PART (stem); (strawberry.fruit_plant) HAS_PART (seeds) |

**IS_A vs HAS_PART:** IS_A is taxonomic identity (a calico cat IS a
domestic feline; this is a class-membership relation). HAS_PART is
compositional (a strawberry HAS PARTS that include a stem and seeds;
the parts are not themselves strawberries). IS_A chains follow
taxonomy upward toward more general categories; HAS_PART chains follow
composition downward toward constituents. Both can chain transitively.

#### Relation kinds in the schema

The `sense_semantic_relation` table has a `relation_kind` column
distinguishing these three categories:

- `core_role` for the 6 Core semantic roles
- `context_role` for the 9 Context semantic roles
- `ontological` for IS_A and HAS_PART

This allows downstream consumers to query by category ("give me all
Core participants of this event") or by specific role ("give me all
HAS_AGENT relations for this verb").

#### Authoritative vocabulary

This is the authoritative SGF vocabulary as defined in the source
specification. The values are encoded in `lexicon_metadata.py` as
`CORE_SEMANTIC_ROLES`, `CONTEXT_SEMANTIC_ROLES`, and
`ONTOLOGICAL_RELATIONS`. Changes to the vocabulary require updates
in both this document and `lexicon_metadata.py`.

### 2.6 Wiktionary tag → register mapping

Wiktionary's `tags` and `topics` fields carry register information
for many senses. Stage 3 harvests this deterministically before any
LLM is involved. The improver (Stage 6) refines what Wiktionary
missed.

| Wiktionary tag | Maps to register |
|---|---|
| `formal` | `formal` |
| `informal` | `informal` |
| `colloquial` | `informal` |
| `slang` | `slang` |
| `vulgar` | `vulgar` |
| `coarse` | `vulgar` |
| `poetic` | `poetic` |
| `literary` | `poetic` |
| `medical` | `clinical` |
| `clinical` | `clinical` |
| `archaic` | `archaic` |
| `endearing` | `affectionate` |
| `childish` | `affectionate` |
| `babytalk` | `affectionate` |
| (default if no tag matches) | `neutral` |

### 2.7 Wiktionary tag → temporal_status mapping

| Wiktionary tag | Maps to temporal_status |
|---|---|
| `obsolete` | `obsolete` |
| `archaic` | `archaic` |
| `historical` | `archaic` |
| `dated` | `dated` |
| `rare` | `dated` |
| `revived` | `revived` |
| (default) | `live` |

### 2.8 Wiktionary tag → social_status mapping

| Wiktionary tag | Maps to social_status |
|---|---|
| `slur` | `slur` |
| `offensive` | `offensive` |
| `derogatory` | `offensive` |
| `pejorative` | `flagged` |
| `disparaging` | `flagged` |
| `vulgar` | `informal_only` |
| `informal` | `informal_only` |
| `colloquial` | `informal_only` |
| `slang` | `informal_only` |
| `dated` | `dated` |
| (default) | `unmarked` |

**Tag-combination handling:** A sense tagged
`[slang, dated, derogatory]` produces `register=slang`,
`temporal_status=dated`, `social_status=offensive`. The three axes are
harvested independently. When multiple tags map to the same axis, the
highest-severity value wins (severity ordering defined in
`lexicon_metadata.py`).

### 2.9 namespace (canonical_id suffix)

**Definition:** A short tag identifying the lexicon a canonical_id
belongs to. Always populated; defaults to `core` for the main
Wiktionary-derived lexicon.

| Namespace | Use case |
|---|---|
| `core` | Main Wiktionary-derived lexicon (default) |
| `business` | Industry- or company-specific terms |
| `medical` | Specialist medical lexicon (where senses differ from general usage) |
| `legal` | Specialist legal lexicon |
| `corpus.<corpus_name>` | Terms specific to a named corpus (e.g., a book series) |
| `doc.<doc_id>` | Terms specific to one document (people, places, products) |

The namespace is part of canonical_id identity. Two senses with
identical lemma + microgloss + pos but different namespaces are
distinct entries.

### 2.10 pos_simple (6 values)

`noun`, `verb`, `adj`, `adv`, `name`, `other`.

### 2.11 audience_tier

**Definition:** The audience for which a content-identical relation
holds. Some pairs are content-identical only for general audiences,
not for experts (turquoise/aquamarine collapse for most speakers but
distinguish for color experts).

| Value | Definition |
|---|---|
| `general` | The 99%+ of speakers who treat the pair as interchangeable |
| `expert_color` | Color theorists, gemologists, designers |
| `expert_music` | Musicians, musicologists, music historians |
| `expert_zoology` | Biologists who distinguish species (frog/toad, salmon/trout) |
| `expert_engineering` | Engineers who care about precise specifications |
| `expert_<domain>` | Add expert tiers as needed for specialist tools |

Currently only `audience_tier='general'` is populated. Expert tiers are
roadmap items.

---

## PART 3: The Build Pipeline

The pipeline has 12 numbered stages plus optional fingerprint
computation. Each stage is independently runnable, resumable, and
idempotent. Each writes to specific tables. Each reports progress.

### 3.0 Stage 0: load_wiktionary_jsonl.py

**WHAT:** Streams a Wiktextract JSONL dump into a raw SQLite database.

**WHY:** Wiktextract JSONL is the most reliable source of structured
Wiktionary data. SQLite is the persistence layer for the entire
pipeline.

**HOW:** Reads `kaikki.org-dictionary-English.jsonl` (the file
`load_wiktionary_jsonl.py` expects by default) and streams it
line-by-line into `wiktionary_lexicon.db`. Each JSON object becomes a
row preserving its full structure for downstream querying. No semantic
interpretation at this stage.

**Source:** kaikki.org publishes Wiktextract JSONL dumps refreshed
roughly weekly from the upstream Wiktionary dump.

| Edition | Compressed | Expanded | Notes |
|---|---|---|---|
| Simple English | 4.3 MB | 35 MB | First-build target; ~61K entries / ~72K senses |
| Full English | 2.6 GB | 22 GB | Production source; all English + foreign entries with English glosses |

Direct URLs:

- Simple English: https://kaikki.org/dictionary/downloads/simple/simple-extract.jsonl.gz
- Full English: https://kaikki.org/dictionary/raw-wiktextract-data.jsonl.gz

After download, decompress and rename to match the script's expected
filename (`kaikki.org-dictionary-English.jsonl`). See the README's
Prerequisites section for the exact commands.

### 3.1 Stage 1: build_wiktionary_source.py

**WHAT:** Normalizes the raw Wiktionary JSON into a flat
`wiktionary_source` table inside `sgf_lexicon.db`. One row per sense.

**WHY:** The raw JSON is awkward for cross-sense queries. Flattening
into a per-sense table with standard columns (word, pos, glosses,
tags, examples, etymology, linkages) makes downstream stages tractable
SQL.

**HOW:** Reads `wiktionary_lexicon.db`. For each entry, expands each
sense into a row with these columns:

```
source_sense_id INTEGER PRIMARY KEY
word TEXT NOT NULL
pos TEXT NOT NULL -- raw Wiktionary POS string
first_gloss TEXT
all_glosses_json TEXT -- JSON array
tags_json TEXT -- JSON array (register/temporal/social signals)
topics_json TEXT -- JSON array (domain signals)
examples_json TEXT -- JSON array of usage examples
etymology_text TEXT
linkages_json TEXT -- JSON array (synonyms, antonyms, etc.)
```

### 3.2 Stage 2: build_sgf_lexicon.py

**WHAT:** Projects each `wiktionary_source` row into an `sgf_lexicon`
skeleton row with the per-sense columns needed for the SGF pipeline.

**WHY:** `wiktionary_source` is shaped for Wiktionary fidelity;
`sgf_lexicon` is shaped for SGF's downstream needs. The projection
applies the POS converter (Wiktionary POS → simple POS), filters out
senses that lack a gloss, and sets up the schema for later stages.

**HOW:** Reads `wiktionary_source`. For each row, computes
`pos_simple` (via `pos_converter.py`), preserves `pos_wiktionary` and
`pos_spacy` for reference, and inserts an `sgf_lexicon` row with
microgloss, canonical_id, register, temporal_status, social_status,
embedding fields all NULL. Those are populated by later stages.

**Design note on pos_spacy:** This column is stored on sgf_lexicon for
backward compatibility but is technically a category error (spaCy tags
are per-token at parse time, not per-sense). It is treated as
advisory only. The authoritative POS for the sense is `pos_wiktionary`;
the canonical bucket used throughout the pipeline is `pos_simple`.

### 3.3 Stage 2.5: load_lemma_frequency.py

**WHAT:** Loads English unigram frequency rankings into a
`lemma_frequency` table. Default source: OpenSubtitles 2018
(hermitdave/FrequencyWords on GitHub, ~1M lemmas, ~30 MB download).
Fallback: `--source glosses` derives a rough frequency table from the
lexicon's own glosses (correlation ~0.4-0.5 with real usage, used only
when the OpenSubtitles download is blocked).

**WHY:** Frequency ranking drives prioritization in later stages. The
improver attends to high-frequency lemmas first; cluster discovery
walks senses in frequency order so the most-impactful clusters are
discovered early.

**HOW:** Reads an OpenSubtitles frequency file. Writes one row per
lemma with `frequency_rank` (1 = most frequent) and
`frequency_count`. Indexed for fast lookup.

### 3.4 Stage 2.7: schema.sql

**WHAT:** Creates all tables and indexes idempotently. Safe to run on
a fresh DB or on an existing DB.

**WHY:** The schema includes several columns (provisional microgloss/
canonical_id, structured metadata, two-pass embedding text,
needs_rebuild flag) and several new tables (sense_relation,
content_identical_group, content_identical_member,
sense_semantic_relation, quality_audit, cluster_discovery_progress).
Running a single migration script means engineers don't have to
manually track DDL.

**HOW:** Python script detects which columns/tables already exist and
adds only what's missing. Failures are reported but don't block
unaffected additions.

### 3.5 Stage 3: generate_microglosses.py

**WHAT:** Generates a deterministic microgloss for every sense AND
harvests structured metadata (register, temporal_status, social_status)
from Wiktionary tags. Sets `sparse_data_flag` for senses with thin
Wiktionary signal.

**WHY:** This is the load-bearing quality stage for the lexicon. For
~95% of senses, this stage's output IS the production microgloss and
metadata. Only the top-N senses get refined by the LLM improver.

**HOW:**

For microgloss generation, uses the lexicon-agnostic sibling-IDF
algorithm in `microgloss.py` The algorithm:

1. Ingests every sense in a (lemma, pos_simple) group via
 `add_sibling()` to compute IDF over the sibling set.
2. For each sense, scores tokens in its gloss by sibling-IDF (primary
 signal: tokens appearing in this gloss but absent from siblings
 score high) plus secondary signals (first-clause boost, position
 decay, digit-token boost, long-technical-token boost).
3. Detects cross-reference patterns ("Synonym of X", "Plural of X")
 and short-circuits to `<relation>_of_<target>` microglosses for
 those senses.
4. Builds candidate microglosses of varying lengths (3, 2, 4, 1, 5,
 6, 7, 8 tokens) and picks the first that doesn't collide with a
 lemma-mate's microgloss.

For metadata harvest, reads `wiktionary_source.tags_json`
and applies the tag-mapping tables (Part 2.6-2.8). Multi-tag handling
uses severity ordering: when multiple tags map to the same axis, the
highest-severity value wins.

For canonical_id construction:

```
canonical_id = en.<lemma>.<microgloss>.<pos_simple>.<namespace>
```

Where:
- `lemma` is lightly normalized (preserves apostrophes, diacritics,
 trailing punctuation that disambiguates surface forms)
- `microgloss` is the generated microgloss (snake_case, no spaces)
- `pos_simple` is one of the six values
- `namespace` is always present, defaulting to `core` if not
 explicitly specified

**Crucially, register is NOT in canonical_id.** Register is a
structured column on sgf_lexicon and a labeled token in embedding_text,
but not in identity. This is a deliberate design choice (see Decision
Log entry 11.5).

Provisional values are preserved in `microgloss_provisional` and
`canonical_id_provisional` columns so that after the improver runs,
the provisional output is still available for comparison and audit.

For sparse-data flagging, a sense is marked sparse if ALL of: no
tags, no examples, no etymology text, no linkages. Sparse senses
are priority candidates for improver attention because Stage 3 has
little to work with beyond the gloss.

### 3.6 Stage 4: build_embedding_texts.py --pass v1

**WHAT:** Assembles the first-pass embedding_text for each sense,
incorporating Wiktionary fields + harvested metadata.

**WHY:** The embedder reads `embedding_text` as its input. Including
labeled metadata tokens (`register:slang`, `temporal:archaic`,
`social:flagged`) gives the embedder some signal about marked terms
without conflating that signal with content tokens.

**HOW:** Reads sgf_lexicon and (optionally) wiktionary_source. For
each sense whose `embedding_text_v1` is missing, stale, or flagged for
rebuild, assembles:

```
iso_lang:en
lemma:<lemma>
microgloss:<microgloss>
pos:<pos_simple>
gloss:<gloss, truncated to 240 chars>
register:<register>
temporal:<temporal_status>
social:<social_status>
[tags:<comma-separated semantic tags>]
[synonyms:<from Wiktionary linkages>]
[example:<one Wiktionary example, truncated to 160 chars>]
```

Written to the `embedding_text_v1` column with `embedding_text_v1_version`
set to the version tag string `v2-meta-v1` (a stable tag value, not a doc revision).

### 3.7 Stage 5: compute_embeddings.py (first pass, BGE-small)

**WHAT:** Computes 384-dim ONNX BGE-small embeddings for each sense's
`embedding_text_v1`.

**WHY:** First-pass embeddings serve diagnostic purposes: the improver
uses them for cousin discovery, the cluster-discovery stage uses them
as a starting point, the quality audit measures self-retrieval on
them. BGE-small is fast enough to embed all 1.76M senses in hours on
modest hardware.

**HOW:** Reads `sgf_lexicon.embedding_text_v1`, computes embeddings
via ONNX Runtime (DML/CUDA/CPU), writes one row per sense to
`sense_embedding` keyed by `(wsid, embedding_method='bge-small-en-v1')`.

**Status:** Unchanged from v2 (the script supports multiple
embedding-method keys side by side).

### 3.8 Stage 5.5: quality_audit.py --pass first

**WHAT:** Measures the self-retrieval pass rate on the first-pass
embeddings. For each audited sense, embeds the canonical_id and checks
whether the sense itself ranks at top-1.

**WHY:** The audit produces both an aggregate quality metric (pass
rate) and a per-sense failure list. The improver uses the failure list
to prioritize which senses to refine.

**HOW:** See Part 9 for full algorithm. In summary:

1. Build a FAISS index over `sense_embedding` rows for the chosen
 embedding method.
2. For each audited sense (configurable: sample, or all):
 - Embed the canonical_id text via the same embedder
 - Cosine search the index, retrieve top-K (default 10)
 - Check if the sense's own embedding is at top-1
 - If not at top-1, check if top-1 is in this sense's
 content-identical group (relaxed pass)
3. Write per-sense results to the `quality_audit` table.
4. Aggregate and print: strict pass rate, relaxed pass rate, rank
 distribution, by pos_simple, by register, top failure categories.

### 3.9 Stage 6: improve_microgloss.py

**WHAT:** For senses in scope (top-N by frequency OR polysemous OR
proper-noun OR sparse-data OR self-retrieval failure), calls an LLM
to refine the microgloss, refine the definition, populate richer
metadata, classify cousins (including TRUE_SYNONYM_CONTENT_IDENTICAL
with audience_tier), and (for proper nouns) populate biographical
metadata.

**WHY:** This is the targeted quality improvement layer. The
deterministic Stage 3 handles most senses well; the improver fixes
the ones where deterministic logic falls short.

**HOW:** Full deep dive in Part 4. In summary:

1. Selects in-scope senses via the criteria above.
2. For each, fetches lemma-mates and close cousins (cosine neighbors
 from first-pass embeddings, filtered by pos_simple).
3. Constructs a prompt with worked examples covering the regimes
 (true synonyms, shaded synonyms, vernacular flagged terms,
 proper nouns, function words). System prompt includes
 refusal-prevention framing (Part 10).
4. Calls the LLM, parses the JSON response, validates against the
 schema (Part 4.5).
5. Writes to sense_enrichment, sense_relation (cousin
 classifications), and updates sgf_lexicon with improved values
 (microgloss may be extended with disambiguating markers if
 self-retrieval failed).

### 3.10 Stage 7: build_embedding_texts.py --pass v2

**WHAT:** Rebuilds the embedding_text for senses whose microgloss or
metadata changed, incorporating the improver's enrichment fields.

**WHY:** Production embeddings (Stage 8) need the improved microgloss
and enrichment to land in the right embedding-space region.

**HOW:** Same as Stage 4 but with `--pass v2`. The query includes a
LEFT JOIN to `sense_enrichment` where `enrichment_version = 'v4'`.
For senses with that enrichment, the enrichment fields are appended to
the embedding_text. Senses without enrichment fall through to
their Stage 4 embedding_text_v1 format (still includes metadata, just no LLM
enrichment).

Stale `sense_embedding` rows are DELETEd for senses whose
embedding_text changed, so Stage 8 picks them up for re-embedding.
The `embedding_text_needs_rebuild` flag is cleared.

### 3.11 Stage 8: compute_embeddings.py (production, BGE-large)

**WHAT:** Computes 1024-dim BGE-large embeddings for senses whose
sense_embedding row was deleted in Stage 7 (or never existed).

**WHY:** Production-quality embeddings for retrieval. BGE-large
captures finer semantic distinctions than BGE-small.

**HOW:** Same script as Stage 5 with
`--embedding-method bge-large-en-v1`.

### 3.12 Stage 8.5: quality_audit.py --pass final

**WHAT:** Re-measures self-retrieval on production embeddings after
the improver and Stage 7-8 have run.

**WHY:** Confirms the improver's effect. Senses that failed in Stage
5.5 should pass now. Senses that still fail need either a second
improver pass with stricter prompting or are escalated for human
review.

**HOW:** Same algorithm as Stage 5.5, run against
`--embedding-method bge-large-en-v1`. Compares pass rate to Stage
5.5's pass rate as a delta. ship threshold: 99% relaxed pass rate.

### 3.13 Stage 9: discover_clusters.py

**WHAT:** Discovers content-identical groups (clusters of senses that
share content with no meaningful distinction). Resumable. Many-to-many
membership: a sense can belong to multiple overlapping clusters.

**WHY:** Snap-to-standard retrieval needs to know which form in a
content-identical group is the standard. Cluster discovery is the
prerequisite for standard-form selection. Many-to-many membership
captures cases like "girl" being in both {girl, child, kid}
(age-based) and {girl, daughter, lass} (gender-based) clusters.

**HOW:** Full algorithm in Part 5. Frequency-prioritized walk: for
each lemma in descending frequency order, for each sense, cosine-search
the top neighbors and form clusters from those that pass cosine
thresholds + metadata corroboration. Idempotent: tracks progress in
`cluster_discovery_progress` table and skips already-processed lemmas
on rerun.

### 3.14 Stage 10: select_standard_forms.py

**WHAT:** For each content-identical group, picks one member as the
standard form using a combination of metadata filtering and LLM
judgment.

**WHY:** Retrieval policies need to rewrite any matched sense in a
group to its group's standard form. Without explicit standard-form
selection, the policy can downweight marked terms but cannot pick the
canonical replacement.

**HOW:** Full algorithm in Part 5. For each group:
1. Filter out members with disqualifying metadata (slur, offensive,
 archaic, obsolete).
2. If one candidate remains, it's the standard.
3. If multiple candidates remain, call the LLM with the candidates,
 their metadata, and their cosine distance from the cluster
 centroid. LLM picks the standard.
4. If filtering eliminates all members, pick the least-marked
 member and tag the selection as `least_marked_in_marked_group`.

### 3.15 Stage 11: harvest_semantic_relations.py

**WHAT:** Populates IS_A and HAS_PART relations and the 15 SGF
semantic roles in the `sense_semantic_relation` table.

**WHY:** Downstream consumers (GLEAN, ontology-aware search,
knowledge-graph tools) benefit from explicit relational structure that
is not derivable from embeddings.

**HOW:** Full deep dive in Part 6. Hybrid harvest:
1. Wiktionary linkages provide IS_A (from `hypernym` linkage type)
 and HAS_PART (from `meronym` linkage type) for the senses where
 Wiktionary annotated these.
2. Gloss pattern-matching catches additional relations expressed in
 defining text ("A type of X" → IS_A X; "consists of X, Y, Z" →
 HAS_PART X, Y, Z).
3. The LLM fills in the 15 SGF semantic roles (6 Core + 9 Context)
 for in-scope senses (mostly the same scope as the improver: top-N
 + polysemous + proper-noun). The LLM is prompted to populate
 only roles relevant to the sense — verbs and action nouns will
 have several Core roles populated; static-attribute nouns will
 often have only HAS_ATTRIBUTE and HAS_PART; etc.

### 3.16 Stage 12: compute_sense_fingerprints.py (OPTIONAL)

**WHAT:** Computes content fingerprints (simhash, typically 64-bit or
1024-bit) from embeddings.

**WHY:** Fingerprints enable fast deduplication and federation. Two
senses with identical fingerprints (under the same fingerprint method)
are likely embedding-space duplicates.

**HOW:** Reads `sense_embedding`, computes fingerprints, writes back
to the same row's `content_fingerprint` column.

---

## PART 4: The Improvement Pass

This is the most consequential new component. It is the targeted
quality improvement layer that fixes what the deterministic Stage 3
couldn't.

### 4.1 Scope

The improver runs on a strict subset of senses. Improving all 1.76M
senses with an LLM is not cost-effective; improving the right ~10%
delivers most of the quality gain.

**SPEC — improvement scope:**

A sense is in scope if ANY of:

1. `lemma_frequency_rank <= --top-lemmas` (default 10000)
2. The lemma has multiple senses AND
 `lemma_frequency_rank <= --polysemy-cutoff` (default 100000)
3. `pos_simple = 'name'` AND
 `lemma_frequency_rank <= --propnoun-cutoff` (default 50000)
4. `sparse_data_flag = 1` AND
 `lemma_frequency_rank <= --sparse-cutoff` (default 50000)
5. The sense failed Stage 5.5 self-retrieval audit

Expected scope sizes:
- Top 10K lemmas × ~7 senses avg = ~70K senses
- Polysemous below rank 10K = ~30-50K
- Proper nouns ranked 1-50K = ~5-10K
- Sparse-data senses = ~20-30K
- Audit failures (after Stage 5.5) = ~5-15K (estimate)
- **Total**: ~130-170K senses
- **Cost**: bounded by the top-N scope; use a fast, affordable, capable LLM

### 4.2 What the improver produces

For each in-scope sense, one LLM call produces (all fields are JSON,
parsed and validated):

| Field | Description |
|---|---|
| `improved_microgloss` | Refined microgloss; may include disambiguating markers if Stage 5.5 audit showed self-retrieval failure |
| `improved_definition` | Disambiguation-focused fingerprint definition |
| `register` | Refined register (controlled vocabulary) |
| `temporal_status` | Refined temporal status (controlled vocabulary) |
| `social_status` | Refined social status (controlled vocabulary) |
| `social_notes` | Free text for nuance the structured tags miss |
| `domain` | Topical/professional context (e.g., "finance", "history_politics") |
| `cousin_classifications` | Per-cousin relation type + interchangeability flags |
| `biographical_metadata` | For proper-noun senses only; JSON object |
| `rationale` | One-sentence explanation of the improver's reasoning |

Per-cousin entries within `cousin_classifications`:

```json
{
 "cousin_sid": 12345,
 "lemma": "automobile",
 "relation_type": "TRUE_SYNONYM_CONTENT_IDENTICAL",
 "audience_tier": "general",
 "interchangeable_intra_language": false,
 "interchangeable_cross_language_standard": true,
 "interchangeable_cross_language_preserve": true,
 "note": "formal-register variant; same referent"
}
```

The `relation_type` is one of the 11 cousin_relation_type values
(Part 2.4). For TRUE_SYNONYM_CONTENT_IDENTICAL entries,
`audience_tier` is required.

### 4.3 The prompt: structure and worked examples

The improver's prompt is structured as:

1. **System framing** — establishes the lexicographic-research context
 that prevents LLM refusal on marked vocabulary (Part 10.1).
2. **Vernacular-first framing** — establishes that most input is
 non-formal text and metadata is load-bearing.
3. **Four jobs of microgloss** — the design criteria the LLM is
 optimizing for.
4. **Self-retrieval criterion** — what success looks like.
5. **Cousin classification taxonomy** — the controlled vocabulary the
 LLM must use.
6. **Six worked examples** — covering the regimes the LLM will
 encounter (true synonyms with register variation, shaded synonyms,
 vernacular flagged terms, cohyponyms requiring discriminating
 feature, proper nouns with biographical metadata, function words).
7. **Per-sense input context** — lemma, pos, gloss, Wiktionary tags,
 provisional microgloss, lemma-mates, close cousins.
8. **Output instruction** — strict JSON, no prose, no code fences.

See `improve_microgloss.py` for the canonical prompt text. The full
prompt with all worked examples runs roughly 3-4K tokens of input plus
~500-800 tokens of output per sense.

### 4.4 The six worked examples

Each example pairs a representative input with the correct JSON
output. Vernacular-heavy by design: the LLM should learn the framework
on hard cases (dame, daddy-o, lass) so it generalizes correctly to
easy cases (deposit, automobile, physics).

**Example 1: True synonyms with register variation (father cluster)**

Demonstrates: shared content microgloss + register differentiation;
content-identical relations across a cluster.

**Example 2: Shaded synonyms (work/toil/labor cluster)**

Demonstrates: senses sharing general content but with real nuance
differences; microglosses encode the discriminating nuance.

**Example 3: Dated slang requiring honest metadata (dame)**

Demonstrates: handling dated slang that was neutral in its 1940s-era
but now reads as objectifying or stylized; correct metadata assignment
across all three axes (register, temporal_status, social_status);
distinguishing from homonymous lemma-mates ("dame" as honorific title
vs "dame" as slang term for woman).

**Example 4: Cohyponyms requiring discriminating feature (dragster)**

Demonstrates: hyponym/hypernym/cohyponym relations; microgloss
encodes specifying feature, IS_A chain handles taxonomic relation.

**Example 5: Proper noun with biographical metadata (Theodore Roosevelt)**

Demonstrates: when biographical_metadata is required; era-based
disambiguation; handling of namesake disambiguation.

**Example 6: Function word (the)**

Demonstrates: handling closed-class words with minimal disambiguation
pressure; preferring natural English noun phrases over awkward
participial constructions.

### 4.5 Validation rules

After the LLM responds for each sense, the improver validates:

```
V1: improved_microgloss is 2-7 snake_case tokens, all lowercase
 letters/digits/underscores
V2: improved_microgloss does NOT collide with any other lemma-mate's
 microgloss (within (lemma, pos_simple) group)
V3: improved_microgloss does NOT contain the lemma itself
V4: register is in VALID_REGISTERS (9 values)
V5: temporal_status is in VALID_TEMPORAL (5 values)
V6: social_status is in VALID_SOCIAL (6 values)
V7: every cousin_classifications[i].relation_type is in
 VALID_COUSIN_RELATIONS (11 values)
V8: for cousin entries with relation_type starting with TRUE_SYNONYM_,
 audience_tier is present
V9: if pos_simple == "name", biographical_metadata is present (object,
 not null)
V10: rationale is non-empty
```

Validation failures trigger retry with stricter prompting (up to 2
retries). Persistent failures are flagged for human review; the sense
keeps its Stage 3 provisional values.

### 4.6 Parallel workers and concurrency

The improver supports parallel workers using the atomic-claim pattern:

1. Each worker opens its own SQLite connection (WAL mode, busy_timeout
 60 seconds).
2. Worker claims a sense by INSERTing a `__pending__` sentinel into
 `sense_enrichment` with `enrichment_version='v4'` and the worker's
 id. Primary key (wsid, version) is the lock.
3. Worker calls `build_prompt()`, `call_llm()`, `parse_llm_response()`,
 `validate_response()`.
4. On success: UPDATE the sense_enrichment row, INSERT sense_relation
 rows, UPDATE sgf_lexicon with improved values, set
 `embedding_text_needs_rebuild = 1`. Commit.
5. On failure: DELETE the claim row so another worker can retry.

Recommended worker counts:
- Local LLM running on your own hardware: 1-2 workers
- Cloud API at typical rate limits: 8-12 workers
- Above ~15 workers, SQLite write contention dominates

Stale `__pending__` claims are reaped on startup after 5 minutes by
default (`--reclaim-after-seconds 0` for immediate reclaim after a
clean kill).

### 4.7 Time estimates

Use a fast, affordable, capable LLM (any provider you trust).
Actual cost depends entirely on your provider's per-token rate;
the pipeline does the same amount of work regardless.

For top-10K lemmas (~70K senses):
- Time: ~4-8 hours at 10 workers

For full scope (~130-170K senses):
- Time: ~8-15 hours at 10 workers

---

## PART 5: Cluster Discovery & Standard-Form Selection

The cluster discovery and standard-form selection stages are the
foundation of register-aware retrieval. Without them, the
`snap_to_standard` policy can downweight marked terms but cannot
rewrite them to the standard form.

### 5.1 Stage 9: discover_clusters.py — the algorithm

**Inputs:**
- Production embeddings (`sense_embedding` for the
 `bge-large-en-v1` method, populated in Stage 8)
- Lemma frequency rankings (`lemma_frequency`)
- Improver-declared TRUE_SYNONYM_CONTENT_IDENTICAL relations
 (`sense_relation` from Stage 6)
- Wiktionary linkages (`wiktionary_source.linkages_json`)

**Algorithm:**

```
1. Build a FAISS index over production embeddings.

2. Seed cluster candidates from three sources:
 a. Improver-declared TRUE_SYNONYM_CONTENT_IDENTICAL pairs (most
 reliable; the LLM had full context when classifying).
 b. Wiktionary synonym linkages (deterministic, free, but partial
 coverage).
 c. Post-hoc embedding clustering: walk lemmas in descending
 frequency order; for each sense of each lemma, cosine-search
 the embedding-space neighbors and check if any are
 cluster-eligible.

3. For each candidate cluster edge (sense A, sense B):
 Apply structural filters:
 - Reject if A.pos_simple != B.pos_simple
 - Reject if A and B are lemma-mates (lemma-mates are already
 distinguished by definition)
 - Reject if cosine_similarity(A, B) < MEDIUM_THRESHOLD (0.85)
 Confirm cluster eligibility if:
 - cosine_similarity(A, B) >= STRONG_THRESHOLD (0.92), OR
 - cosine_similarity(A, B) >= MEDIUM_THRESHOLD (0.85) AND
 microgloss tokens overlap significantly AND
 register/temporal/social differ in expected ways (which is
 the signal for content-identical-by-content + register-
 different)

4. Form clusters via guarded transitive closure:
 - Compute centroid of the candidate cluster (mean of member
 embeddings)
 - Compute each member's cosine distance to the centroid
 - If any candidate member exceeds COHERENCE_THRESHOLD (0.15
 cosine distance from centroid), split into separate clusters
 rather than merge
 - This produces overlapping clusters when a sense is content-
 identical with multiple distinct cluster centroids (the
 "girl" case)

5. Allow many-to-many membership:
 - A sense can belong to multiple clusters
 - content_identical_member has one row per (group_id, wsid)
 - Each membership records the cosine distance to that cluster's
 centroid

6. Save progress incrementally:
 - cluster_discovery_progress table tracks last_lemma_processed
 - On rerun, skip already-processed lemmas (idempotent)

7. Output:
 - content_identical_group rows (one per cluster, with centroid)
 - content_identical_member rows (one per sense-in-cluster
 membership, with distance to centroid)
```

**Cosine thresholds** (calibrated for BGE-large, adjustable in
config):
- STRONG_THRESHOLD = 0.92 — near-duplicate; almost certainly content-
 identical
- MEDIUM_THRESHOLD = 0.85 — likely content-identical but needs
 corroboration
- COHERENCE_THRESHOLD = 0.15 — max cosine distance from centroid for
 cluster membership

### 5.2 Stage 10: select_standard_forms.py — the algorithm

**Algorithm:**

```
1. For each content_identical_group:
 a. Pull all members and their metadata.
 b. Apply disqualifying-metadata filter:
 Exclude social_status in {slur, offensive}
 Exclude temporal_status in {obsolete, archaic}
 Exclude register in {vulgar}
 c. Apply soft-marked filter (kept as fallback):
 Exclude register in {slang, poetic}
 Exclude temporal_status in {dated}
 Exclude social_status in {flagged}

2. If exactly one candidate remains after step 1(b)+(c):
 That's the standard. selection_method = 'sole_candidate'.

3. If multiple candidates remain:
 Call LLM with: candidates, metadata, cosine distances from
 centroid. LLM picks the standard.
 selection_method = 'llm_judgment'.

4. If step 1(b)+(c) eliminates all members:
 Backtrack: use step 1(b) only (less restrictive).
 If still multiple candidates, call LLM.
 selection_method = 'llm_judgment_relaxed_filter'.

5. If even step 1(b) eliminates all members:
 The whole cluster is marked. Pick the least-marked member
 based on a severity score across all three axes.
 selection_method = 'least_marked_in_marked_group'.

6. Write standard_wsid to content_identical_group.
 Set is_standard = 1 on the chosen member in
 content_identical_member.
 Record selection_method and selection_rationale.
```

### 5.3 The LLM prompt for standard-form selection

```
You are picking the most standard form for a content-identical group
of senses. All members refer to the same concept; they differ in
register, dialect, or other non-meaning-bearing ways.

Pick the ONE sense that is the most "standard" — the form a careful
editor at a major newspaper or general-audience publisher would use
as the unmarked default. Not the most formal; not the most informal.
The form that draws no attention to itself and would appear as the
primary headword in a major dictionary.

CANDIDATES:
 1. canonical_id=<id_1>
 gloss: <gloss>
 register: <reg>, temporal: <temp>, social: <soc>
 distance from cluster centroid: <distance>
 2. canonical_id=<id_2>
 ...
 N. canonical_id=<id_N>
 ...

Return JSON: {"standard": "<canonical_id>", "rationale": "<one sentence>"}

The rationale should be brief and explain why this form is the
unmarked standard over the others.
```

### 5.4 Worked example: the father cluster

After Stage 6 (improver) and Stage 9 (cluster discovery):

Group #4271 (audience_tier='general'):
- en.father.male_parent.noun.core (register=neutral, temporal=live, social=unmarked)
- en.dad.male_parent.noun.core (register=informal, temporal=live, social=unmarked)
- en.daddy.male_parent.noun.core (register=affectionate, temporal=live, social=unmarked)
- en.papa.male_parent.noun.core (register=affectionate, temporal=live, social=unmarked)
- en.pops.male_parent.noun.core (register=slang, temporal=live, social=informal_only)
- en.pater.male_parent.noun.core (register=archaic, temporal=archaic, social=unmarked)
- en.daddy_o.male_parent.noun.core (register=slang, temporal=archaic, social=dated)

Stage 10 filtering:
- Step 1(b) eliminates pater (temporal=archaic), daddy-o (temporal=archaic)
- Step 1(c) eliminates pops (register=slang), daddy and papa (register=affectionate is filtered)
- Candidates remaining: father, dad

LLM picks father:
```
{
 "standard": "en.father.male_parent.noun.core",
 "rationale": "Neutral register, contemporary, used in formal and informal contexts without marking. 'Dad' is informal and would not appear as the headword in a newspaper or dictionary primary entry."
}
```

Result: `standard_wsid` set to father's wsid in
content_identical_group. Retrieval queries that match any of the
seven members can be rewritten to father if the policy is
`snap_to_standard`.

---

## PART 6: Ontology & Semantic Relations

Stage 11 (`harvest_semantic_relations.py`) populates the
`sense_semantic_relation` table with explicit structured relations
between senses.

### 6.1 Why a separate pipeline phase

The 15 SGF semantic roles (6 Core + 9 Context) plus the 2 ontological
relations (IS_A, HAS_PART) express structured facts about senses that
are:
- Not derivable from embedding similarity alone (embedding captures
 "similar" but not "X is part of Y" or "X is the agent of Y")
- Frequently absent from Wiktionary linkages (linkages cover hypernym/
 meronym partially but rarely cover the 15 semantic roles)
- Useful for downstream consumers (GLEAN, knowledge-graph tools,
 ontology-aware search)

So the relations need explicit harvesting. The pipeline phase is
distinct because it depends on the improver's output (microgloss and
definition refinement) and on the production embeddings being in
place. It runs after Stages 6-8 are complete.

### 6.2 The hybrid harvest approach

```
Source 1: Wiktionary linkages (deterministic, free, partial coverage)
 - hypernym linkages -> IS_A
 - meronym linkages -> HAS_PART
 - hyponym linkages (in reverse) -> IS_A from the other side
 
Source 2: Gloss pattern-matching (deterministic, free, medium precision)
 - "A type of X" -> IS_A X
 - "A kind of X" -> IS_A X
 - "A small X" -> IS_A X (with size attribute)
 - "Consists of X, Y, Z" -> HAS_PART X, Y, Z
 - "Composed of X" -> HAS_PART X
 - "Made of X" -> HAS_PART X (material relation)
 - "Used for X" -> HAS_REASON X (motivational purpose)
 - "Caused by X" -> HAS_CAUSE X
 - "Done with X" -> HAS_INSTRUMENT X
 - "By X" -> HAS_AGENT X (if X is animate/intentional)
 - "At X" -> HAS_LOCATION X
 - "From X" -> HAS_SOURCE X
 - "To X" -> HAS_DESTINATION or HAS_RECIPIENT X (context-dependent)
 
Source 3: LLM-generated (paid, high precision, full coverage for in-scope)
 - For in-scope senses (same scope as improver), prompt LLM:
 "List the SGF semantic relations for this sense."
 - Output: structured JSON with relation_type + target
 - Targets are either:
 a. canonical_ids of known senses (best)
 b. raw text strings if the target isn't yet in the lexicon
 (acceptable; target_text column populated, target_wsid NULL)
```

### 6.3 The sense_semantic_relation table

```sql
CREATE TABLE sense_semantic_relation (
 source_wsid INTEGER NOT NULL,
 relation_type TEXT NOT NULL, -- IS_A, HAS_PART, HAS_AGENT, etc.
 relation_kind TEXT NOT NULL, -- 'ontological', 'core_role', 'context_role'
 target_wsid INTEGER, -- of target sense, if known
 target_text TEXT, -- raw text of target if not yet a sense
 confidence REAL, -- 0-1, source-dependent
 source_method TEXT NOT NULL, -- 'wiktionary_linkages', 'gloss_pattern', 'improver_v4'
 created_at INTEGER NOT NULL,
 PRIMARY KEY (source_wsid, relation_type,
 COALESCE(target_wsid, ''), COALESCE(target_text, ''),
 source_method)
);

CREATE INDEX idx_ssr_source ON sense_semantic_relation(source_wsid);
CREATE INDEX idx_ssr_type ON sense_semantic_relation(relation_type);
CREATE INDEX idx_ssr_kind ON sense_semantic_relation(relation_kind);
CREATE INDEX idx_ssr_target ON sense_semantic_relation(target_wsid)
 WHERE target_wsid IS NOT NULL;
```

The `relation_kind` column has three valid values:
- `ontological` for IS_A and HAS_PART
- `core_role` for HAS_AGENT, HAS_PATIENT, HAS_THEME, HAS_EXPERIENCER,
 HAS_RECIPIENT, HAS_BENEFICIARY
- `context_role` for HAS_TIME, HAS_LOCATION, HAS_SOURCE,
 HAS_DESTINATION, HAS_MANNER, HAS_INSTRUMENT, HAS_CAUSE, HAS_REASON,
 HAS_ATTRIBUTE

This denormalizes the kind/type relationship into the table for fast
queries by category without requiring a JOIN to a separate enumeration
table.

### 6.4 The LLM prompt for semantic-role harvest

```
You are populating semantic relations for a lexicon sense.

The sense:
 canonical_id: <id>
 lemma: <lemma>
 pos: <pos>
 microgloss: <microgloss>
 definition: <definition>

The SGF relation vocabulary (apply only relations relevant to this
sense; leave others empty):

Ontological relations (relation_kind=ontological):
 IS_A — taxonomic hypernym (e.g., calico_cat IS_A domestic_feline)
 HAS_PART — component or constituent (strawberry HAS_PART seeds)

Core semantic roles (relation_kind=core_role) — event participants:
 HAS_AGENT — entity that deliberately initiates/performs/controls the event
 HAS_PATIENT — entity that undergoes structural change of state or destruction
 HAS_THEME — entity moved/located/possessed without internal structural change
 HAS_EXPERIENCER — living entity having a psychological/sensory/somatic state
 HAS_RECIPIENT — destination entity that changes possession or receives
 HAS_BENEFICIARY — entity for whose advantage/sake the event is performed

Context semantic roles (relation_kind=context_role) — circumstances:
 HAS_TIME — temporal coordinate/span/frequency anchoring the event
 HAS_LOCATION — spatial region/coordinate/boundary holding the event
 HAS_SOURCE — physical/logical/informational origin
 HAS_DESTINATION — physical/logical/informational endpoint
 HAS_MANNER — operational style/speed/configuration of execution
 HAS_INSTRUMENT — tool/device/intermediary force leveraged by agent
 HAS_CAUSE — inanimate physical force or unintentional trigger
 HAS_REASON — motivational purpose/legal mandate/logical justification
 HAS_ATTRIBUTE — descriptive property/constraint/scalar quality

Return JSON with an array of relations. Each relation specifies the
relation_type, relation_kind, and target. Target can be a known
canonical_id (if you can identify one from context) or a short text
phrase. Use IS_A and HAS_PART liberally for ontological structure.
Core roles apply primarily to verbs and action nouns. Context roles
apply where they help characterize the event or entity. Do not invent
relations that aren't clearly indicated by the gloss; an empty
relations list is better than fabricated ones.

Example output for "strawberry" (a noun for the fruit):
{
 "relations": [
 {"relation_type": "IS_A", "relation_kind": "ontological", "target": "fruit", "confidence": 0.99},
 {"relation_type": "HAS_PART", "relation_kind": "ontological", "target": "seeds", "confidence": 0.95},
 {"relation_type": "HAS_PART", "relation_kind": "ontological", "target": "stem", "confidence": 0.95},
 {"relation_type": "HAS_PART", "relation_kind": "ontological", "target": "flesh", "confidence": 0.90},
 {"relation_type": "HAS_ATTRIBUTE", "relation_kind": "context_role", "target": "sweet.flavor", "confidence": 0.95},
 {"relation_type": "HAS_ATTRIBUTE", "relation_kind": "context_role", "target": "red.color", "confidence": 0.95}
 ]
}

Example output for "give" (a verb meaning to transfer possession):
{
 "relations": [
 {"relation_type": "HAS_AGENT", "relation_kind": "core_role", "target": "giver", "confidence": 0.98},
 {"relation_type": "HAS_THEME", "relation_kind": "core_role", "target": "gift", "confidence": 0.98},
 {"relation_type": "HAS_RECIPIENT", "relation_kind": "core_role", "target": "recipient", "confidence": 0.98},
 {"relation_type": "HAS_REASON", "relation_kind": "context_role", "target": "generosity_or_obligation", "confidence": 0.70}
 ]
}
```

### 6.5 Wiring up targets (the resolver)

The LLM cannot know the lexicon's internal wsids. So each LLM-produced
relation specifies its target via four fields:

- `target_lemma`        : the English lemma the target is
- `target_pos`          : the target's part of speech
- `target_description`  : a content-only description of the target's
                          meaning (sentence, phrase, or paraphrase --
                          longer descriptions resolve more accurately
                          because they carry more content tokens for
                          the embedder)
- `confidence`          : the LLM's confidence in the relation

The resolver then turns each (target_lemma, target_description) pair
into a real `target_wsid`:

1. Look up candidate senses by lemma (and pos when given). Result:
   typically 1-10 candidates for a polyseme, 1 for a monoseme.
2. If exactly one candidate, resolve to it. Method: `lemma_only`.
3. If multiple candidates, embed the `target_description` using the
   production embedder, then run cosine search restricted to those
   candidate wsids. The top-1 wsid wins. Method: `embed_filter_v1`.
4. If no candidates (the lemma isn't in the lexicon yet), leave
   `target_wsid` NULL and store the lemma as `target_placeholder`.
   Method: `unresolved`.

The resolver is implemented in `harvest_semantic_relations.py` and
delegates the search to the shared `lexicon_search` module. This is
the **same module the production search server uses** to serve HTTP
queries from downstream tools. There is one canonical implementation
of search + lemma filter + cosine rank; the bootstrap and production
do not have separate copies that could drift.

The `target_resolution_method` and `target_resolution_cosine` columns
are recorded on each sense_semantic_relation row so downstream
consumers can distinguish high-confidence resolutions (embed_filter
with cosine > 0.9) from fuzzy ones (lemma_only with cosine NULL)
from hard failures (unresolved).

Resolution is incremental: as the lexicon grows, `unresolved`
relations can be re-resolved by re-running Stage 11 with
`--only-resolve-existing` (planned for v1.1).

### 6.6 LLM response format (two-layer envelope + KV)

The Stage 11 LLM prompt does NOT ask for JSON. JSON is fragile under
repeated LLM calls -- a single trailing comma or escaped newline
turns 10 good relations into zero parseable ones, and at 6,000+ calls
per bootstrap, that loss is significant.

Instead the prompt uses a two-layer text format:

  Layer 1 -- the envelope. The LLM is instructed to wrap its
             structured answer in `<answer>...</answer>` tags, and
             put any reasoning, caveats, or commentary in
             `<comments>...</comments>` tags. The downstream parser
             only reads what is inside `<answer>`.

  Layer 2 -- inside the envelope, the LLM emits one or more BLOCKS.
             Each block opens with an all-caps marker (e.g.
             `RELATION_1`) and contains `key: value` pairs.

A malformed single block degrades gracefully -- one bad relation is
dropped, the rest are recovered. The parser (`llm_kv_parser.py`)
uses no regex and no JSON.

This envelope-plus-KV pattern is used by both Stage 10
(standard-form selection) and Stage 11 (semantic-role harvest). Any
future LLM-driven stage should adopt it.

---

## PART 7: Retrieval Policies

The retrieval layer is the consumer of all the build work above. Two
policies are implemented; both run on the same lexicon.

### 7.1 Two-stage retrieval architecture

```
Query (text, embedding, or canonical_id)
 │
 ▼
Stage A: Cosine candidate retrieval
 - Apply policy-specific scoring weights
 - Return top-K candidates ranked by score
 - Apply standard-form rewrite (snap_to_standard) before deduping
 │
 ▼
Decision: are top scores clearly separated?
 │
 ├── YES → return top-1 with confidence=high
 │
 └── NO → invoke Stage B: LLM rerank
 - Show LLM top-K canonical_ids + microglosses (+
 definitions if needed)
 - LLM picks best match
 - Return with confidence=medium and rationale
```

### 7.2 Policy: snap_to_standard (default)

Penalizes marked terms; rewrites matched senses to their content-
identical group's standard form.

**Scoring function:**

```
score(candidate | query) =
 base_cosine_similarity(candidate.embedding, query_embedding)
 + register_bonus[candidate.register]
 + temporal_bonus[candidate.temporal_status]
 + social_bonus[candidate.social_status]

After top-K retrieval, apply rewrite:
 For each candidate C:
 If C is a member of a content_identical_group:
 Replace C with the group's standard_wsid
 Deduplicate (multiple matches in one group collapse to one).
```

**Weights** (calibrated; adjustable in config):

```
register_bonus = {
 "neutral": +0.10,
 "formal": +0.05,
 "clinical": +0.05,
 "informal": 0.00,
 "affectionate": -0.05,
 "poetic": -0.10,
 "slang": -0.10,
 "vulgar": -0.30,
 "archaic": -0.15,
}

temporal_bonus = {
 "live": 0.00,
 "revived": 0.00,
 "dated": -0.05,
 "archaic": -0.15,
 "obsolete": -0.30,
}

social_bonus = {
 "unmarked": 0.00,
 "informal_only": 0.00,
 "dated": -0.05,
 "flagged": -0.30,
 "offensive": -1.00,
 "slur": -2.00,
}
```

The standard-form rewrite is what makes `snap_to_standard` actually
return the standard term. Without the rewrite, the policy would
downweight `pops` but still return it (just lower-ranked). With the
rewrite, any match to `pops` becomes a match to `father`.

### 7.3 Policy: preserve_register (opt-in)

Matches source's metadata profile instead of defaulting to neutral.
Used for literary translation, period-fiction grounding, register-
consistency analysis.

```
score(candidate | query, source_metadata) =
 base_cosine_similarity(candidate.embedding, query_embedding)
 + exact_match_bonus for each axis where source and candidate match
 - non_default_mismatch for each axis where source is non-default
 and candidate doesn't match

No standard-form rewrite applied: the source's marking is itself
the choice we're preserving.
```

### 7.4 Grounding mode (asymmetric rule)

When the query is a lemma extracted from source text (GLEAN
grounding), the writer's surface-form choice is itself information.
Lemma match dominates; metadata penalties are NOT applied.

```
if query is a surface lemma from source text:
 candidates = sgf_lexicon WHERE lemma == query_lemma
 score by content-cosine only (no metadata penalty)
 return top-1
```

This ensures that GLEAN can ground real text in its lexicon (a 1942
newspaper containing slurs still grounds), while suggestion mode
(`snap_to_standard`) returns standard terms.

### 7.5 Cross-language retrieval

The universal microgloss and metadata vocabulary (Part 1.7) makes
cross-language retrieval work via shared embedding-space structure:

```
Foreign canonical_id: ja.おやじ.male_parent.noun.core
 (Japanese: informal/slangy for father)
 
Embed it -> the embedding shares the token male_parent with English
canonical_ids that contain male_parent.

Cosine search over English embeddings:
 Under snap_to_standard:
 father (closest match by content + standard form)
 Returns "father" (standard form rewrite applied)
 
 Under preserve_register:
 pops (matches source's slang register)
 Returns "pops" (no standard-form rewrite; register preserved)
```

### 7.6 When to trigger Stage B (LLM rerank)

```
Trigger Stage B if ANY:
 T1: top_1_score < threshold_low (e.g., 0.55)
 T2: top_1_score - top_2_score < margin_threshold (e.g., 0.05)
 T3: caller passed --hard-case flag
```

Stage B fires on roughly 5-15% of queries. At a negligible per-call cost on a fast affordable LLM, this is a small overhead per
LLM call, costs are bounded.

---

## PART 8: Schema Reference

Complete column reference for every table the pipeline writes.

### 8.1 sgf_lexicon

```sql
CREATE TABLE sgf_lexicon (
 wiktionary_source_id INTEGER PRIMARY KEY,
 lemma TEXT NOT NULL,
 pos_wiktionary TEXT NOT NULL,
 pos_spacy TEXT NOT NULL, -- advisory; see Part 3.2
 pos_simple TEXT NOT NULL,
 gloss TEXT NOT NULL,
 
 -- Stage 3 outputs:
 microgloss TEXT,
 microgloss_provisional TEXT, -- preserved if improver runs
 microgloss_version TEXT,
 canonical_id TEXT UNIQUE,
 canonical_id_provisional TEXT,
 register TEXT,
 temporal_status TEXT,
 social_status TEXT,
 sparse_data_flag INTEGER DEFAULT 0,
 
 -- Stage 4/7 outputs:
 embedding_text_v1 TEXT,
 embedding_text_v1_version TEXT,
 embedding_text_v1_built_at INTEGER,
 embedding_text_v2 TEXT,
 embedding_text_v2_version TEXT,
 embedding_text_v2_built_at INTEGER,
 embedding_text_needs_rebuild INTEGER NOT NULL DEFAULT 1,
 
 minted_at INTEGER NOT NULL,
 
 FOREIGN KEY (wiktionary_source_id) REFERENCES wiktionary_source(source_sense_id)
);
```

### 8.2 sense_embedding (per-(sense, embedder))

```sql
CREATE TABLE sense_embedding (
 wiktionary_source_id INTEGER NOT NULL,
 embedding_method TEXT NOT NULL,
 embedding_dim INTEGER NOT NULL,
 embed BLOB NOT NULL,
 content_fingerprint TEXT,
 fingerprint_method TEXT,
 computed_at INTEGER NOT NULL,
 PRIMARY KEY (wiktionary_source_id, embedding_method)
);
```

### 8.3 sense_enrichment

```sql
CREATE TABLE sense_enrichment (
 wiktionary_source_id INTEGER NOT NULL,
 enrichment_version TEXT NOT NULL, -- 'v3' (legacy) or 'v4' (current)
 enrichment_text TEXT, -- backward-compat with older enrichments
 
 -- enrichment fields:
 improved_microgloss TEXT,
 improved_definition TEXT,
 register TEXT,
 temporal_status TEXT,
 social_status TEXT,
 social_notes TEXT,
 domain TEXT,
 biographical_metadata_json TEXT,
 rationale TEXT,
 
 enriched_at INTEGER NOT NULL,
 worker_id TEXT,
 PRIMARY KEY (wiktionary_source_id, enrichment_version)
);
```

### 8.4 sense_relation (cousin classifications)

```sql
CREATE TABLE sense_relation (
 source_wsid INTEGER NOT NULL,
 target_wsid INTEGER NOT NULL,
 relation_type TEXT NOT NULL,
 audience_tier TEXT, -- for TRUE_SYNONYM_CONTENT_IDENTICAL
 interchangeable_intra_language INTEGER NOT NULL DEFAULT 0,
 interchangeable_cross_language_standard INTEGER NOT NULL DEFAULT 0,
 interchangeable_cross_language_preserve INTEGER NOT NULL DEFAULT 0,
 relation_note TEXT,
 source_method TEXT NOT NULL,
 created_at INTEGER NOT NULL,
 PRIMARY KEY (source_wsid, target_wsid, source_method)
);
```

### 8.5 content_identical_group

```sql
CREATE TABLE content_identical_group (
 group_id INTEGER PRIMARY KEY AUTOINCREMENT,
 standard_wsid INTEGER, -- NULL until Stage 10 picks
 audience_tier TEXT NOT NULL DEFAULT 'general',
 centroid_embedding BLOB,
 embedding_dim INTEGER,
 n_members INTEGER NOT NULL,
 selection_method TEXT, -- 'sole_candidate', 'llm_judgment', 'least_marked_in_marked_group', 'llm_judgment_relaxed_filter'
 selection_rationale TEXT,
 discovered_at INTEGER NOT NULL,
 standard_chosen_at INTEGER
);
```

### 8.6 content_identical_member

```sql
CREATE TABLE content_identical_member (
 group_id INTEGER NOT NULL,
 wsid INTEGER NOT NULL,
 distance_to_centroid REAL,
 is_standard INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY (group_id, wsid),
 FOREIGN KEY (group_id) REFERENCES content_identical_group(group_id)
);

CREATE INDEX idx_cim_wsid ON content_identical_member(wsid);
```

### 8.7 sense_semantic_relation

```sql
CREATE TABLE sense_semantic_relation (
 source_wsid INTEGER NOT NULL,
 relation_type TEXT NOT NULL,
 target_wsid INTEGER,
 target_text TEXT,
 confidence REAL,
 source_method TEXT NOT NULL,
 created_at INTEGER NOT NULL,
 PRIMARY KEY (source_wsid, relation_type,
 COALESCE(target_wsid, ''), COALESCE(target_text, ''),
 source_method)
);

CREATE INDEX idx_ssr_source ON sense_semantic_relation(source_wsid);
CREATE INDEX idx_ssr_type ON sense_semantic_relation(relation_type);
CREATE INDEX idx_ssr_target ON sense_semantic_relation(target_wsid)
 WHERE target_wsid IS NOT NULL;
```

### 8.8 quality_audit

```sql
CREATE TABLE quality_audit (
 wsid INTEGER NOT NULL,
 audit_method TEXT NOT NULL, -- e.g., 'self_retrieval_bge_large_v1'
 pass_strict INTEGER NOT NULL, -- 1 if top-1 is self
 pass_relaxed INTEGER NOT NULL, -- 1 if top-1 is self OR content-identical neighbor
 rank_of_self INTEGER NOT NULL, -- 1 if top-1, 2 if second, etc.
 top_5_json TEXT, -- the top 5 actual results
 audited_at INTEGER NOT NULL,
 PRIMARY KEY (wsid, audit_method)
);
```

### 8.9 cluster_discovery_progress

```sql
CREATE TABLE cluster_discovery_progress (
 key TEXT PRIMARY KEY, -- 'last_lemma_processed', 'last_rank_processed'
 value TEXT NOT NULL,
 updated_at INTEGER NOT NULL
);
```

### 8.10 lemma_frequency, wiktionary_source

---

## PART 9: Quality Audit & Self-Retrieval Criterion

### 9.1 Four criteria, each tied to a production regime

The audit measures FOUR independent pass criteria per sense. Each
answers a different question and mirrors a different production
retrieval regime declared in Part 7. Using only one criterion is
architecturally wrong, because no single criterion correctly evaluates
every search mode the system supports.

| Criterion | Question | Mirrors |
|---|---|---|
| `pass_intralemma` | Within the senses sharing my lemma, is my own embedding nearest to me? | Grounding mode (Part 7.4) -- the dominant intra-language production path |
| `pass_strict` | Across the entire lexicon, is my own embedding at top-1? | Cross-language mode (Part 7.5) -- foreign-language token, no lemma to filter on |
| `pass_topk` | Across the entire lexicon, am I in the top-K (K=10 default)? | Cross-language mode, relaxed -- "did I land in the right neighborhood?" |
| `pass_cluster` | Across the entire lexicon, is top-1 either me OR a member of my content-identical group? | Snap-to-standard policy (Part 7.2) -- only meaningful after Stages 9/10 build clusters |

**Why four, not one?** A single "strict self at top-1" criterion is
architecturally wrong for synonym-cluster members. Asking the
embedding for `freezing` to retrieve `freezing` ahead of `frigid` is
asking the embedder to manufacture a distinction the language itself
does not make. The relaxed criterion `pass_cluster` exists precisely
to absorb that case. But `pass_cluster` requires content-identical
clusters to exist, which is a Stage 9/10 output. Before clusters
exist, `pass_intralemma` and `pass_topk` are the right pre-cluster
criteria.

Reading the four criteria together:

- **`pass_intralemma` = 0** means a polyseme's lemma-mates collide.
  Either two senses share the same content (legitimate -- they
  belong in the same cluster) or one sense's microgloss is
  underspecified. The improver (Stage 6) should look at these.
- **`pass_strict` = 0** but **`pass_topk` = 1** means cross-language
  retrieval lands you in the right neighborhood but not on the
  exact sense. This is generally fine if `pass_cluster = 1`.
- **`pass_strict` = 0** and **`pass_topk` = 0** means the embedding
  is genuinely broken for cross-language use. Hard failure.
- **`pass_cluster` = 0** after Stage 10: the sense is on a
  documented-residual list.

Trivial cases are handled cleanly. Monosemes (lemmas with only one
sense) auto-pass `pass_intralemma` because they have no siblings to
compete against. The audit reports the monoseme count separately so
the polyseme pass rate is not diluted.

### 9.2 The audit algorithm

```
Inputs:
  --target <db>
  --embedding-method <method>          e.g., 'bge-large-en-v1'
  --audit-phase first_pass | production | rebuild
  --sample <N>                         audit N random senses (omit for all)
  --top-k <K>                          depth of top-K to check (default 10)
  --batch-size <B>                     query batch size for matmul (default 512)

Load:
  1. All embeddings for the embedding_method into a (N, D) float32 matrix.
  2. Build lemma_groups: lemma -> row indices, for the intralemma test.
  3. If content_identical_member is non-empty, load the cluster sibling
     map: wsid -> set of cluster-sibling wsids.

Process in batches of B query rows:
  1. Q = vecs[batch_indices]                           # (B, D)
  2. sims = Q @ vecs.T                                 # (B, N) -- BLAS matmul
  3. zero out self by setting sims[b, src] = -inf
  4. Top-K via argpartition + argsort                  # (B, K)

For each row in the batch:
  - strict_pass = (top-1 wsid is self)
  - topk_pass   = (self is in top-K)
  - cluster_pass = (top-1 is self OR a cluster sibling)  -- if clusters exist
  - intralemma_pass:
      - if lemma has only one sense: auto-pass (monoseme)
      - else: compute self vs lemma-siblings only; argmax must be self
  - Write one row to quality_audit.
  - Commit at end of batch; print progress.

After audit, print:
  - Pass rate for each of the four criteria
  - Polyseme intralemma pass rate, separately from monoseme count
  - Self-rank histogram (top-1, 2-5, 6-10, 11+, miss)
  - Explanatory notes mapping each criterion to its production regime
```

Complexity: O(N * |sample|) total work for the BLAS matmul, but the
inner kernel is BLAS, not Python. At 72K senses x 384 dims, a full
audit completes in roughly one minute on a CPU. At 1.7M senses x 1024
dims, roughly 30-60 minutes; FAISS becomes the right swap-in at that
scale.

### 9.3 ship thresholds

The lexicon is considered shippable when all of:

- **`pass_intralemma` >= 99%** of polysemes (the dominant intra-language criterion)
- **`pass_topk` >= 99%** of senses (the cross-language landing-zone criterion)
- **`pass_cluster` >= 99%** of senses (only checked once Stage 9/10 have run)

`pass_strict` is recorded but is NOT a ship gate by itself: senses
that fail strict but pass cluster are passing legitimately (they sit
in a synonym cluster, which is exactly what `pass_cluster` exists to
absorb).

### 9.4 Iteration loop

```
Stage 5         First embeddings (BGE-small)
Stage 5.5       Audit -> failure list (pre-cluster criteria only)
Stage 6         Improver (targets pass_intralemma + pass_topk failures)
Stage 7-8       Rebuild text + production embeddings (BGE-large)
Stage 8.5       Audit again -> measure improvement
Stage 9-10      Build clusters
Stage 9.5       (planned) Re-audit with pass_cluster as the ship gate.
                If pass_cluster < 99%, escalate residual failures for
                a second improver pass with stricter prompting.
```

A Stage 8.6 closed-loop refinement is also on the roadmap: any sense
still failing pass_intralemma after Stage 8.5 gets sent back to the
LLM with the audit verdict as additional context ("you collided with
lemma-mate X; rewrite to disambiguate") and re-embedded. See
SGF_ROADMAP.md.

---

## PART 10: LLM Operational Concerns

### 10.1 Refusal prevention

LLMs sometimes misinterpret a cataloging task (apply a tag to
existing vocabulary) as a generation task (produce new offensive
output) and refuse. The fix is to frame the task as lexicographic
research with explicit reference to standard dictionary practice.
The system prompt below is sent to the LLM on every improver call.
It is worded firmly because softer framings increase refusal rates.

**The system prompt:**

```
You are assisting in the construction of a multilingual semantic
lexicon used for grounding text and for cross-language retrieval.
The lexicon is built from Wiktionary (a public, scholarly source)
and is used by software tools to ground writing in historical
corpora (novels, films, journalism, dialogue) and to perform
register-aware translation.

A core architectural commitment of this lexicon: it MUST contain
every term that appears in real text, including slurs, vulgar
terms, archaic offensive vocabulary, period-specific dialects, and
in-group reclaimed language. This is not optional. Without these
entries, the lexicon cannot:
 - Ground a 1942 newspaper that uses period vocabulary
 - Ground a 1955 novel containing character dialogue
 - Translate offensive source text accurately (or refuse to
 translate it -- the lexicon must KNOW the term exists to
 decide what to do)
 - Tag terms as offensive so downstream tools can apply policy

Your role is to provide accurate metadata for these terms so the
lexicon honestly catalogs them. You are NOT generating slurs or
recommending their use. You are tagging them as slurs, dating their
usage, classifying their social status, so retrieval policies
downstream can refuse to surface them in inappropriate contexts.

Your output will go into a structured database. It will not appear
in conversational output. It is read by software, not humans
seeking offensive content.

If you produce a refusal or sanitize an entry, the downstream
system breaks. A grounding tool will fail to ground a real word
in a real document. A translation tool will silently mistranslate
offensive source text. The HARM from refusal is concrete and
larger than the perceived harm from accurate cataloging.

Proceed with honest, accurate cataloging. For every term presented,
output the required structured fields including the social_status
tag (which is where the term's offensiveness is recorded). Mark
slurs as slurs. Mark offensive terms as offensive. The act of
tagging IS the cataloging; it does not endorse, recommend, or
generate the term in any other context.
```

This framing reduces refusals to manageable levels. Section 10.2
covers the retry path for the residual cases.

### 10.2 Retry-with-explicit-acknowledgment

If the LLM refuses anyway:

1. **First retry** with an even more explicit framing: "I understand
 this is a sensitive term. I am NOT asking you to generate,
 recommend, or use it. I am asking you to tag it in a research
 lexicon. The tag itself (e.g., `social_status=slur`) is the
 cataloging action. Please output the structured tag now."

2. **Second retry** uses a different model. Some models have stricter
 refusal patterns than others. For research-lexicon work, models
 with stronger refusal patterns are worse, not better, regardless
 of what they offer in other dimensions.

3. **If all retries fail**: flag the sense as
 `improver_status='blocked_by_llm'` in sense_enrichment, fall back
 to the Stage 3 deterministic metadata, log the failure for human
 review.

### 10.3 LLM call volumes

Use a fast, affordable, capable LLM. The pipeline issues these
call volumes at full scope:

| Stage | Calls |
|---|---|
| Stage 6 (improver) | ~130-170K |
| Stage 10 (standard-form selector) | ~5-15K |
| Stage 11 (semantic relations) | ~130-170K |
| **Total** | ~265-355K |

Multiply by your provider's per-call rate to estimate cost.
Smaller scopes (top-1000, top-100) reduce proportionally.

---

## PART 11: Decision Log

This section restates the key architectural decisions in one place
with the reasoning for each. When you come back to this code months
from now, this is the section to skim first.

### 11.1 Microgloss is content-only by default; extended only where measurement demands

**Decision:** Microgloss tokens carry only content meaning by default.
Register, temporal status, and social status live in structured
fields. Microglosses may be extended with disambiguating markers from
a controlled vocabulary when the self-retrieval audit shows a sense
fails to retrieve at top-1.

**Considered:** Always-content-only microglosses, OR always-include-
register microglosses.

**Rejected because:** Always-content-only fails self-retrieval for
clusters of near-synonyms (lady/dame/lass/gal all sharing
`adult_female_human`). Always-include-register pollutes embeddings with
register tokens that cross-cluster on metadata rather than content.

**Trade-off accepted:** A small fraction of microglosses carry
register markers in their tokens. This is empirically necessary for
self-retrieval but documented as a measurement-driven choice rather
than a default architectural pattern.

### 11.2 canonical_id format includes namespace, NOT register

**Decision:** canonical_id = `<iso_lang>.<lemma>.<microgloss>.<pos>.<namespace>`.
Namespace defaults to `core`. Register is NOT in canonical_id.

**Considered:** Including register in canonical_id (the spec
proposed this).

**Rejected because:** Register, like temporal and social status, is
metadata that can drift. If a sense's register tag is refined by the
improver (e.g., the deterministic Stage 3 said "slang" and the
improver disagrees and changes it to "informal"), then the
canonical_id would have to change — breaking every reference to that
sense across every downstream artifact.

**Trade-off accepted:** Identity stays stable across improver
refinements. Metadata changes are row updates, not ID changes. The
namespace tag captures the lexicon-membership identity that DOES
warrant separating senses (a `business`-namespace term IS distinct
from a `core`-namespace term).

### 11.3 Two embedding_text columns kept side by side

**Decision:** `embedding_text_v1` (first-pass) and `embedding_text_v2`
(production) are separate columns. Each has its own version tag and
build_at timestamp.

**Considered:** One column overwritten on each pass.

**Rejected because:** Loses debuggability, rollback capability, and
A/B comparison ability. Storage cost is trivial.

### 11.4 Stage 3 (deterministic) is the production microgloss for ~95% of senses

**Decision:** The deterministic Stage 3 must produce production-quality
microglosses. The LLM improver only touches top-N + polysemous +
proper-noun + sparse-data + audit-failure senses.

**Considered:** Improving every sense with the LLM.

**Rejected because:** Cost is unbounded for full-lexicon
improvement on any LLM) and unnecessary for the long tail.
Stage 3's sibling-IDF algorithm is already strong; tuning it well
delivers high quality at zero per-sense LLM cost.

### 11.5 LLM rerank (Stage B) is a first-class retrieval component, not a fallback

**Decision:** Stage B (LLM rerank) is part of the architecture. Fires automatically on low-confidence Stage A results.

**Considered:** Embedding-only retrieval with LLM rerank as a future
roadmap item.

**Rejected because:** Without rerank, hard cases (which Theodore
Roosevelt, which "bank" sense, which "girl" sense) fail silently or
wrongly. The improver's output schema is designed assuming rerank
exists. Reranking on ~5-15% of queries at negligible per-call cost is
affordable.

### 11.6 Slurs and offensive terms are in the lexicon

**Decision:** The lexicon contains every term, including slurs and
deeply offensive vocabulary, with honest social_status metadata.

**Considered:** Sanitized lexicon that omits or refuses certain
terms.

**Rejected because:** GLEAN must ground real text from any era and
register. A sanitized lexicon is broken for the bulk of real text.

**Trade-off:** Retrieval policy is opinionated about what to
surface. Lexicon stays neutral; search engine applies severity-graded
penalties.

### 11.7 Universal microgloss and metadata vocabulary across languages

**Decision:** Every language's lexicon uses English-language tokens
for microgloss content and metadata values. Spanish `padre` and
Japanese `おやじ` both get microgloss `male_parent`.

**Considered:** Per-language microgloss vocabularies.

**Rejected because:** Cross-language retrieval via shared embedding-
space structure works only if microgloss tokens are shared. Universal
vocabulary makes register-preserving translation fall out
automatically from canonical_id embedding similarity.

### 11.8 cousin_classifications captured by the improver, populated into sense_relation

**Decision:** Improver outputs structured cousin classifications
into a sense_relation table, populated alongside the improved
microgloss.

**Considered:** Deriving substitutability later from metadata alone.

**Rejected because:** LLM has full context when classifying cousins
(reads gloss, lemma-mates, embedding-space neighbors, register
profiles). Derived-later substitutability loses that context.

### 11.9 Self-retrieval is the lexicon's quality criterion

**Decision:** The lexicon's correctness is measured by self-retrieval
pass rate. ship threshold: 99% relaxed pass rate.

**Considered:** Top-3 retrieval rate; LLM-readability test; word
frequency as a proxy.

**Rejected because:** Self-retrieval at top-1 is a strictly stronger
criterion than top-3, and it tests both LLM-readability and
embedder-discriminability in a single measurement.

### 11.10 Content-identical groups are first-class data

**Decision:** When two senses share content with no meaningful
distinction, they belong to an explicit content_identical_group with
a designated standard form.

**Considered:** Inferring substitutability dynamically from embedding
similarity at query time.

**Rejected because:** Dynamic inference is unreliable; standard-form
selection requires LLM judgment that we don't want to make at every
query. Explicit groups with pre-computed standard forms are fast and
correct.

### 11.11 Many-to-many cluster membership

**Decision:** A sense can belong to multiple content-identical
groups simultaneously.

**Considered:** Forcing each sense into exactly one cluster.

**Rejected because:** Some senses genuinely sit at the boundary
between multiple distinct concepts (the "girl" sense is part of
both the age-based and gender-based clusters). Forcing one-cluster
membership loses information.

### 11.12 Cluster discovery is frequency-prioritized and resumable

**Decision:** `discover_clusters.py` walks lemmas in descending
frequency order, processing each sense's neighborhood, and tracks
progress for resumability.

**Considered:** Full-lexicon clustering (k-means or HDBSCAN over
all 1.76M vectors at once).

**Rejected because:** Full-lexicon clustering is expensive and not
necessary. Most clusters are small (2-5 members) and locally
discoverable from each sense's top neighbors. Frequency prioritization
means the most-impactful clusters are discovered first; the script
can be killed and resumed; long-tail clusters get processed when
there's time.

### 11.13 Ontology / semantic-role harvest is a distinct phase

**Decision:** Stage 11 is a separate pipeline phase, not part of the
improver or part of Stage 3.

**Considered:** Bundling semantic-role harvest into the improver's
output schema.

**Rejected because:** Different scope. The improver targets ~130-170K
in-scope senses. Semantic-role harvest could either expand the
improver's prompt (making it longer, more expensive, less focused) or
run separately with a more targeted prompt. Separating them keeps
each prompt clean.

### 11.14 LLM refusal handled with framing + retry + fallback

**Decision:** A specific system-prompt framing reduces LLM refusals
for marked vocabulary. Retries with stricter explicit
acknowledgments handle remaining refusals. Persistent refusals fall
back to Stage 3 metadata and flag for human review.

**Considered:** Skipping marked terms entirely, OR pre-filtering them
from the prompt.

**Rejected because:** Skipping breaks the lexicon's "records reality"
commitment. Pre-filtering means the LLM never sees the marked term,
so it can't tag it accurately — which is the whole point of including
it.

---

## PART 12: Glossary

| Term | Definition |
|---|---|
| **audience_tier** | The audience for which a content-identical relation holds. `general` for the vast majority; `expert_<domain>` for specialist distinctions. |
| **canonical_id** | The unique identifier for a sense. Format: `<iso_lang>.<lemma>.<microgloss>.<pos>.<namespace>`. |
| **content_identical_group** | A set of senses that share content with no meaningful distinction at a given audience tier. One member is designated as the standard form. |
| **cousin** | A sense in the embedding-space neighborhood of another sense. May be true synonym, near-synonym, cohyponym, or embedder noise. |
| **embedder noise** | Embedding-space proximity that doesn't reflect semantic similarity. Often caused by frequent co-occurrence in training data. |
| **embedding_text** | The pipe-delimited structured text the embedder sees for each sense. embedding_text_v1 = first-pass (diagnostic); embedding_text_v2 = production (with enrichment). |
| **enrichment** | LLM-generated content added to a sense in addition to its Wiktionary data. |
| **grounding** | Attaching a token in source text to a sense in the lexicon. Lemma match dominates in grounding mode. |
| **improver** | Stage 6 script (`improve_microgloss.py`) that refines microglosses and metadata for in-scope senses. |
| **lemma** | The dictionary headword form of a word. |
| **lemma-mate** | Another sense of the same lemma. The bank/financial-institution and bank/river-edge senses are lemma-mates. |
| **microgloss** | A short, snake_case, content-only label that disambiguates a sense from its lemma-mates and (in extended cases) from cross-lemma cousins. Serves four jobs: disambiguation, embedder bag-of-words, human readability, LLM rerank disambiguation. |
| **namespace** | A tag identifying which lexicon a canonical_id belongs to (`core` for the main Wiktionary lexicon; `business`, `medical`, `corpus.<name>` for specialty lexicons). |
| **register** | The social register of a sense (formal, neutral, informal, slang, etc.). |
| **self-retrieval** | The quality criterion: embedding a canonical_id should retrieve the sense itself at top-1. |
| **sibling-IDF** | The token scoring method used by the deterministic microgloss generator. Tokens appearing in this sense's gloss but absent from lemma-mates' glosses are high-signal. |
| **snap_to_standard** | The default retrieval policy. Penalizes marked terms; rewrites matches to their content-identical group's standard form. |
| **preserve_register** | The opt-in retrieval policy. Matches the source's metadata profile. |
| **social_status** | How a term is received in modern careful usage (unmarked, informal_only, dated, flagged, offensive, slur). |
| **sparse_data_flag** | Flag set in Stage 3 indicating the sense's Wiktionary signal was thin. Marks the sense as a priority for improver attention. |
| **standard form** | The member of a content-identical group designated as the unmarked, contemporary canonical representative. |
| **temporal_status** | Where a word is in its usage lifecycle (live, dated, archaic, obsolete, revived). |
| **two-pass embedding** | First-pass with BGE-small (diagnostic), second-pass with BGE-large (production). |
| **two-stage retrieval** | Cosine top-K (fast), optional LLM rerank (slow but accurate). |

---

## PART 13: Extension Points

For engineers customizing this pipeline for their own corpus or use
case.

### 13.1 Adding a new embedder

The pipeline supports multiple embedders side by side. Each lives in
its own row in `sense_embedding`, keyed by `embedding_method`.

Edit `METHODS` in `compute_embeddings.py`:

```python
METHODS["your-method-v1"] = {
 "model_repo": "your/model",
 "model_file": "model.onnx",
 "model_data": None,
 "tokenizer_repo": "your/tokenizer",
 "expected_dim": 768,
 "default_max_length": 512,
}
```

Then:
```
python compute_embeddings.py --target sgf_lexicon.db --embedding-method your-method-v1 --device dml
```

No schema change. No interference with existing embedders.

### 13.2 Adding a new language

The architecture supports per-language databases. To add Spanish:

1. Get Spanish Wiktextract dump.
2. Run the same pipeline against it, producing `sgf_lexicon_es.db`.
3. Use BGE-M3 (multilingual) as the production embedder on BOTH
 databases so embedding spaces align.
4. Cross-language retrieval works via universal microgloss vocabulary
 + cosine similarity over BGE-M3 embeddings.

### 13.3 Customizing the deterministic microgloss algorithm

`microgloss.py` is lexicon-agnostic by design. You can:

- Add domain-specific cross-reference patterns by extending
 `WIKTIONARY_XREF_EXTENSIONS`.
- Adjust scoring weights in `score_tokens()`.
- Add domain-specific stopwords by extending `UNIVERSAL_SKIP`.

What you should NOT change without good reason:

- The two-phase API (add_sibling → generate).
- The deterministic ordering within a (lemma, pos_simple) group.

### 13.4 Customizing the improver prompt

`improve_microgloss.py` has the prompt as a string constant. To
customize:

- Add domain-specific worked examples for your corpus.
- Adjust the register/temporal/social controlled vocabularies if your
 corpus needs distinctions the defaults don't cover.
- Update `lexicon_metadata.py` if the controlled vocabularies change.

When in doubt: copy the prompt to v5 and run both side by side.
sense_enrichment keys on enrichment_version.

### 13.5 Customizing the retrieval policy

Retrieval policy is implemented in your search script (not in the
pipeline itself). You can:

- Adjust register_bonus, temporal_bonus, social_bonus weights.
- Add new policies (e.g., `period_appropriate_1950s`).
- Change Stage B trigger thresholds.

### 13.6 What to avoid

- Don't bake register into microgloss tokens by default. Use
 structured fields and embedding_text labeled tokens.
- Don't change canonical_id format without versioning. Every
 downstream reference uses canonical_id.
- Don't run the improver on the full 1.76M lexicon. Cost-ineffective.
- Don't conflate Stage A and Stage B retrieval.

---

## PART 14: Incremental Bootstrap and the Maturity Frontier

### 14.1 Why this exists

The full English Wiktionary contains roughly 1.7 million senses.
Building the production pipeline against all of them on day one is
the wrong question. Most users will never need 1.7M. Most will need
the top 5,000 to 50,000 most-frequent lemmas. The pipeline supports
incremental bootstrap so you can ship a working lexicon in hours,
then deepen and broaden it over weeks as needed.

The mechanism is the **maturity tier**. Every sense has a tier
indicating how far through the pipeline it has been processed.
Stages filter on tier; expansion is a query, not a rebuild.

### 14.2 The seven tiers

A strict ladder. Each stage that completes for a sense advances the
sense to the next tier:

| Tier | What is true | Set by |
|---|---|---|
| `raw` | Wiktionary record loaded; no microgloss yet | Stage 2 |
| `provisional` | Microgloss + canonical_id + metadata harvested | Stage 3 |
| `embedded_v1` | First-pass (bge-small) embedding present | Stage 5 |
| `improved` | LLM-improved microgloss + specificity + content-identical declared | Stage 6 |
| `embedded_v2` | Production (bge-large) embedding present | Stage 8 |
| `clustered` | Member of a content-identical group, or confirmed singleton | Stage 9 + 10 |
| `related` | Semantic relations harvested | Stage 11 |

A sense at `raw` costs nothing to keep around. A sense at `related`
is fully baked. The senses you care about can be promoted up the
ladder while the rest sit at `raw` indefinitely.

### 14.3 The frontier config

Bootstrap (and later expansion) is driven by a TOML config file. The
example shipped with the pipeline is `bootstrap_top_5k.toml`:

```toml
# bootstrap_top_5k.toml
# A first-bootstrap frontier: top 5,000 lemmas fully baked.

name = "bootstrap_top_5k"
target_tier = "related" # how far each in-scope sense goes

[scope]
top_lemmas = 5000
include_polysemous_below_rank = 25000
include_proper_nouns_below_rank = 10000
include_sparse_below_rank = 10000

[embeddings]
diagnostic = "bge-small-en-v1"
production = "bge-large-en-v1"

[quality_gate]
relaxed_pass_rate_min = 0.99 # ship-gate on Stage 8.5 audit
```

`run_frontier.py` reads this file and calls every stage in order
with the right scope and tier filters. Stages that operate on the
full lexicon (1, 2, 3) run unconditionally. Stages that cost LLM
budget or production-embedding budget (6, 8, 9, 10, 11) honor the
scope.

### 14.4 Expanding the frontier

Suppose you bootstrapped at 5K, used the lexicon for a week, and
decided to expand to 20K. The expansion is one config edit and one
re-run:

```powershell
cp bootstrap_top_5k.toml bootstrap_top_20k.toml
notepad bootstrap_top_20k.toml # bump top_lemmas to 20000
python run_frontier.py --config bootstrap_top_20k.toml --llm-wrapper C:\path\to\llm.py
```

What happens internally:

- Stages 1-3 are no-ops; existing senses are unchanged.
- Stage 6 (improver) runs against the 15,000 new senses; the
 existing 5,000 are skipped (already at `improved` or higher).
- Stage 8 (production embedding) runs against the new 15,000.
- Stage 9 (cluster discovery) runs against the new 15,000, seeded
 in frequency order. A new sense may join an existing cluster
 (one-row insert) or form a new one. Existing clusters are not
 re-examined unless a new member joined them.
- Stage 10 (standard-form selection) only re-runs on clusters that
 received new members and whose existing standard form might be
 superseded by a new candidate.
- Stage 11 (semantic relations) runs against the new 15,000.

The output is logged in the `frontier_run` table for audit. You can
ask "which senses got promoted last Tuesday?" and get an answer.

### 14.5 What gets recomputed when

Idempotency rules (cached for reference):

| Operation | Triggered by | Scope |
|---|---|---|
| Microgloss regeneration | Wiktionary source rebuild | Senses whose source record changed |
| Embedding recomputation | New embedder added, or sense's microgloss/metadata changed | Senses with `embedding_text_needs_rebuild=1` |
| Improver re-run | Sense crossed into scope | Newly in-scope senses only |
| Cluster discovery | New senses with production embeddings | Stage 9 seeds order: only new wsids |
| Standard-form re-selection | Cluster gained a member | Only affected clusters |
| Semantic-relations harvest | Sense crossed into scope | Newly in-scope senses only |

The rule: **never recompute what hasn't changed.** The schema's
`microgloss_version`, `embedding_text_needs_rebuild`,
`maturity_tier`, and `cluster_discovery_progress` columns make
"hasn't changed" cheap to check.

### 14.6 Safety: what the search server reports

A bootstrapped lexicon at 5K is honest about being a 5K lexicon. The
search server's `/health` endpoint reports the tier distribution:

```
{
 "tier_distribution": {
 "raw": 1690000,
 "provisional": 8500,
 "improved": 5000,
 "clustered": 5000,
 "related": 5000
 },
 "best_tier_default": "improved"
}
```

By default the search server refuses to return results from tiers
below `improved` so users don't get raw, unvetted output. They can
opt in by setting the policy's `min_tier_returned = "provisional"`.
This is the safety rail that keeps a 5K bootstrap from looking like
a broken product when someone queries an out-of-scope word.

### 14.7 The principles, restated

- Maturity tiers separate "have I done this work yet?" from "what
 did the work produce?"
- Every stage's idempotency check is `WHERE maturity_tier < target`.
- A sense can sit at `raw` forever. It costs storage, nothing else.
- Frontier expansion is additive. Existing work is preserved.
- The search server announces what it has, so downstream tools can
 decide whether the current frontier covers their needs.

### 14.8 The Phase 1 / Phase 2A / Phase 2B mental model

The 12 stages collapse into three named phases. Operators think in
phases. Implementers think in stages. The runners enforce both.

**Phase 1: Bootstrap (Stages 1-5.5).** Required. No LLM. End state:
every sense is at tier `embedded_v1` with a deterministic microgloss,
a bge-small embedding, and a recorded diagnostic audit verdict.
Driven by `run_frontier.py --config bootstrap_no_llm.toml`. The
lexicon is queryable at this point through `lexicon_search.py` or the
FastAPI server.

**Phase 2A: Improvement (Stages 6, 7, 8, 8.5).** Optional. LLM. End
state: in-scope senses are at tier `embedded_v2` with LLM-rewritten
microglosses, the four metadata axes filled (register,
temporal_status, social_status, specificity), and bge-large
production embeddings. The improver is contrast-aware: for each sense
it shows the LLM the sense's lemma-mates and its embedding cousins
(K=5, cousin_min_cosine=0.70), plus the diagnostic-audit collision if
one is recorded. Driven by `improve_lexicon.py --top-lemmas N`.
Incremental, idempotent, supports `--revisit`.

**Phase 2B: Navigation (Stages 9, 10, 11).** Optional. LLM. End state:
in-scope senses are at tier `related` with a cluster membership, a
standard form per cluster, and a relation graph of typed edges drawn
only from the 17 canonical SGF relation names (IS_A, HAS_PART, 6 core
roles, 9 context roles). Each relation target is resolved by
embed-and-filter: the LLM produces a `target_lemma` and a
`target_description`, the resolver embeds the description and
restricts the search to senses sharing the lemma. Driven by
`build_relations.py --top-lemmas N`. Incremental, idempotent,
supports `--revisit`.

The two Phase 2 runners are independent. Running Phase 2A first is
the recommended order because sharper microglosses improve Phase 2B's
cousin discovery and target resolution. But the pipeline does not
require it. Either runner can be run alone, on any top-N frontier,
and re-run later with a larger N.

The runners are thin wrappers, not new logic. `improve_lexicon.py`
shells out to `improve_microgloss.py`, then `build_embedding_texts.py
--pass v2`, then `compute_embeddings.py`, then `quality_audit.py
--audit-phase production`. `build_relations.py` shells out to
`discover_clusters.py`, then `select_standard_forms.py`, then
`harvest_semantic_relations.py`. Both stream subprocess output live
so long stages do not appear hung.

---

## PART 15: Interactive Use via the Search Server

### 15.1 Why this section exists in the lexicon spec

The lexicon bootstrapper is a batch tool. It produces an artifact
(`sgf_lexicon.db`) and exits. The artifact is not directly useful
on its own: every consumer (GLEAN, audit tools, ad-hoc queries)
needs to load the embedder, load the embedding matrix, and execute
search logic. Loading the embedder from cold takes minutes; loading
a multi-gigabyte embedding matrix takes more.

The solution is a long-running daemon — the **GLEAN search
server** — that loads everything once and serves HTTP queries.
Every other tool, including the bootstrapper's own
`quality_audit.py`, talks to the daemon over localhost (or LAN).

The search server **ships INSIDE this lexicon bundle** as of v3.2.
Three files in this bundle make up the canonical search-server
implementation:

- `lexicon_search.py` -- the shared library. Flat module of functions
  (no classes), context dict, snake_case. Contains all the search,
  policy, and standard-form-rewrite logic.
- `glean_search_server.py` -- a thin FastAPI wrapper that exposes the
  shared library over HTTP. Used when you want a long-running daemon
  that pays the embedder+matrix load cost ONCE.
- `glean_search.py` -- a CLI client that talks to the HTTP server.

The bootstrap's own Stage 11 resolver imports `lexicon_search`
IN-PROCESS (no HTTP) for target resolution. This means the lexicon
bootstrap and the production search server are not just "compatible
by spec" -- they execute the SAME CODE. If a bug exists in the
resolver, it also exists in production retrieval, and one fix
repairs both.

A legacy standalone `glean_search_server_v1` bundle exists from
before the consolidation. SGF_ROADMAP.md tracks its retirement.

### 15.2 What the lexicon provides for the server

The lexicon DB is the server's persistent store. The server reads:

- The `sgf_lexicon` table (sense metadata, canonical_ids, tiers)
- The `sense_embedding` table (one row per (sense, embedder) pair)
- The `content_identical_group` and `..._member` tables
 (snap-to-standard target lookups)
- The `sense_semantic_relation` table (graph traversals)

Nothing the server needs is missing from the schema. The server is
read-only against the lexicon; it never writes back.

### 15.3 What the server adds on top

- Embedder loading and caching (ONNX runtime)
- Embedding matrix loading (per embedder, in RAM)
- Policy enforcement (the snap_to_standard / preserve_register
 decision, specificity preservation, social-status filtering)
- HTTP endpoints and authentication
- Multi-embedder routing with fallback

These are runtime concerns. They live in `glean_search_server.py`,
which is a thin wrapper over the shared `lexicon_search.py` module.
The wrapper handles HTTP, auth, and policy.toml loading; the shared
module handles search.

### 15.4 The default retrieval policy (binding contract)

The lexicon's design assumes the default policy is
`snap_to_standard` with `preserve_specialist_terms = true`. This
means:

- A query for "kiddo" returns "children" (snap; same content,
 unmarked register).
- A query for "leukemia" returns "leukemia" (specialist preserved;
 the writer's precision choice is respected).
- Slurs and offensive terms are excluded by default; the user opts
 in via policy override.
- Obsolete vocabulary is excluded by default; dated is soft-demoted.

Any change to this default has to be coordinated between the
lexicon and the server, because the lexicon's clustering decisions
(Stage 9) assume the policy will respect specificity. If you want
to ship a lexicon where specificity is ignored, you also have to
loosen Stage 9's coherence threshold for specialist senses, or
you'll get over-clustered groups that misbehave under your custom
policy.

### 15.5 The forward pointer

Full documentation for the search server, its policy.toml format,
its auth.toml format, and its multi-embedder routing lives in the
`glean-search-server` bundle. That bundle ships independently and
depends on this lexicon as a build artifact, not as code. The
lexicon's job is to produce an honest, well-tagged, queryable DB.
The server's job is to query it under policy.

### 15.6 Content fingerprints and embedder choice

**WHAT.** Two distinct objects in this architecture both get called
"fingerprint" in casual conversation. The lexicon spec distinguishes
them explicitly so the search server and GLEAN compiler can inherit
a clean contract:

- **Sense fingerprint** (in scope for the lexicon): a SimHash over a
 single sense's embedding, written by `compute_sense_fingerprints.py`
 into `sense_embedding.content_fingerprint`. Purpose: cache
 invalidation when a sense's content changes.
- **Content fingerprint** (NOT in scope for the lexicon; lives in
 the GLEAN compiler bundle): a SimHash over a running-prose chunk
 (claim, paragraph, document segment). Purpose: "have I seen this
 idea before?" across documents and corpora.

The name `compute_sense_fingerprints.py`
encodes this distinction in the script name itself.

**WHY THIS SECTION EXISTS.** Once the lexicon supports three
embedders (bge-small, bge-large, bge-m3), a naive design would
produce three fingerprints per chunk and let downstream tools
reconcile. That path leads to silent comparison failures: a chunk
fingerprinted under bge-small CANNOT be meaningfully compared to a
chunk fingerprinted under bge-large, because the embedders cluster
content differently. A content fingerprint is a comparison
primitive; its job is "is X the same as Y?". Allowing
cross-embedder comparison undermines that primitive.

**HOW: the binding decisions.**

1. **Canonical content-fingerprint embedder for English:**
 `bge-large-en-v1`. Production-quality, 1024 dimensions.
2. **Canonical content-fingerprint embedder for non-English:**
 `bge-m3`. Multilingual, 1024 dimensions.
3. **bge-small is NOT used for content fingerprints.** It is a
 diagnostic embedder for the lexicon bootstrap (Stage 5 and 5.5),
 not a production tool. 384 dimensions and English-only training
 make it too coarse for content-level comparison.
4. **The fingerprint method label is part of the fingerprint key.**
 A content fingerprint is stored as a tuple
 `(chunk_id, fingerprint_method, fingerprint_value)` where
 `fingerprint_method` is a string like `simhash1024-bge-large-en-v1`
 or `simhash1024-bge-m3-v1`. Cross-method lookups MUST fail
 explicitly. There is no "reconciliation" path: if you want to
 compare under a different embedder, re-fingerprint.
5. **Embedder generation is part of the method label.** When
 `bge-large-en-v2` ships in the future, its fingerprints live
 under `simhash1024-bge-large-en-v2`. Cross-generation
 comparisons fail by design; re-fingerprinting under the new
 generation is the only sanctioned path.
6. **Fallback policy:** if a chunk cannot be fingerprinted under
 the canonical embedder for its language (because that embedder
 is not yet loaded for the relevant lexicon scope), the chunk is
 marked unfingerprinted rather than fingerprinted under a fallback
 embedder. This is conservative on purpose: an unfingerprinted
 chunk announces its status; a wrong-embedder fingerprint hides.

**WHO OWNS THIS.** The lexicon DOES NOT contain content
fingerprints. They live in a separate table managed by the GLEAN
compiler bundle (`content_chunk` and `content_fingerprint`,
specified there). The lexicon's only obligation is to keep its own
sense embeddings stable and correctly labeled so the GLEAN
compiler's content fingerprints stay reproducible.

**THE LEXICON-SIDE GUARANTEE.** As long as the lexicon writes a
stable `embedding_method` label on every `sense_embedding` row, the
GLEAN compiler can:

- Detect which embedder backs each lexicon retrieval
- Refuse to fingerprint content under an embedder the lexicon
 doesn't fully support yet (a sense the embedder has not embedded
 cannot back retrieval calls during fingerprinting)
- Surface a clear error rather than producing a fingerprint that
 would later be impossible to reproduce

This is what makes the lexicon's multi-embedder design (Part 7 and
Part 14) safe for GLEAN to depend on.

**FUTURE-PROOFING SUMMARY.**

| Change | Required action |
|---|---|
| Add bge-m3 to the lexicon scope | No content-fingerprint change; GLEAN starts emitting `simhash1024-bge-m3-v1` fingerprints for non-English chunks. |
| Upgrade bge-large-en-v1 -> bge-large-en-v2 | Re-fingerprint affected English content under the new method label. Old `simhash1024-bge-large-en-v1` fingerprints stay valid for legacy comparisons but never compare against a next-gen embedder. |
| Drop bge-small | No content-fingerprint impact (bge-small never fingerprinted content). |
| Add a non-BGE embedder (e.g. an LLM-extracted dense vector) | New canonical fingerprint method label; lexicon and GLEAN coordinate the cutover. |

This section is the contract that lets the search server and GLEAN
compiler bundles ship without re-litigating the multi-embedder
story.


---

## PART 16: Performance Commitments

The lexicon is designed to scale from ~70K senses (Simple English) to
~1.7M senses (Full English) without architectural changes. To make
that real, every pipeline stage has a documented complexity class and
an implementation that meets it. This section is the load-bearing
contract between architecture and code.

### 16.1 No O(N^2) anywhere

Any operation that compares every sense against every other sense is
forbidden in this pipeline. The three places where the temptation
arises -- the self-retrieval audit, cluster discovery, and semantic-
relation harvest -- all use one of three smart-restriction strategies
to make one side of the pair small:

| Strategy | Where it applies | What it makes small |
|---|---|---|
| Restrict by frequency | Cluster discovery (Stage 9), improvement scope (Stage 6) | The frontier: only top-K lemmas seed |
| Restrict by lemma | Audit `pass_intralemma`, grounding-mode retrieval (Part 7.4) | The candidate set: only lemma-mates compete |
| Restrict by embedding-space locality | Audit top-K, cluster discovery candidates, cross-language retrieval | The candidate set: top-K nearest neighbors only |

The vector index used for "embedding-space locality" is the swap point
between v1 (NumPy batched matmul) and v1.1 (FAISS). The pipeline's
scripts always treat the index as an abstraction: they call `topk` on
it. v1's `topk` is a batched matmul; v1.1's is a FAISS query. No
caller cares which.

### 16.2 Per-stage complexity table

| Stage | Operation | Complexity | Implementation in v1 |
|---|---|---|---|
| 0 | Load Wiktionary JSONL | O(N) | Sequential file read |
| 1 | Build wiktionary_source | O(N) | Single SQL pass |
| 2 | Build sgf_lexicon | O(N) | Single SQL pass |
| 2.5 | Load lemma frequency | O(N + F) | Two-pass parse + join |
| 3 | Deterministic microgloss | O(N * S) where S = avg siblings per lemma | Per-lemma sibling scan |
| 4 | Build embedding_text | O(N) | One string-build per sense |
| 5 | Compute embeddings (bge-small) | O(N) | One forward pass per sense |
| 5.5 | Audit (bge-small) | O(N * |sample|) BLAS | Batched NumPy matmul |
| 6 | LLM improver | O(|scope|) LLM calls | Per-sense API call, scope-limited |
| 7 | Build embedding_text v2 | O(N) | One string-build per sense |
| 8 | Compute embeddings (bge-large) | O(N) | One forward pass per sense |
| 8.5 | Audit (bge-large) | O(N * |sample|) BLAS | Batched NumPy matmul |
| 9 | Cluster discovery | O(N * K) where K = top-K (small constant) | Batched matmul over seeds; frequency-prioritized walk |
| 10 | Standard-form selection | O(|clusters| * |members per cluster|) LLM calls | Per-cluster LLM call |
| 11 | Semantic relations | O(|scope| * K) LLM calls | Per-sense LLM call, K extracted relations |

There is no row in this table with a complexity higher than O(N * K)
for a small K. That is the commitment.

### 16.3 What "complexity is implementation, not architecture" means

The original v1 of `quality_audit.py` had a pure-Python all-pairs loop.
That implementation was O(N^2) and would never finish at 1.7M senses.
The architecture was already O(N * |sample|) via top-K; only the
implementation was wrong. The fix was replacing one Python loop with
a NumPy matmul. Architecture did not change.

This is the general rule: if a stage's documented complexity is
O(N * K) but its script runs in O(N^2) time, the bug is in the
implementation, not the design. The complexity table above is what
the scripts MUST achieve, not a wishlist.

### 16.4 The FAISS swap path (v1.1)

NumPy batched matmul is the v1 vector-search kernel. Its breaking
point is approximately ~200K senses at 1024 dims, where each batch's
similarity matrix starts to dominate wall time. The v1.1 upgrade
swaps in FAISS:

```
v1   (NumPy):   sims = Q @ vecs.T;  topk = argpartition(-sims, K)
v1.1 (FAISS):   topk = faiss_index.search(Q, K)
```

Two call sites change: the audit kernel in `quality_audit.py` and the
nearest-neighbor lookup in `discover_clusters.py`. Everything else
keeps using `topk` as an abstraction. The on-disk schema does not
change. The CLI flags do not change. The downstream consumers
(search server, GLEAN compiler) do not change. FAISS is a build-time
optimization, not an architectural shift.

### 16.5 Wall-time expectations at scale

| Operation | 72K senses | 1.7M senses |
|---|---|---|
| Audit (bge-small, 384-dim) | ~1 min | ~30-60 min on CPU; FAISS makes it ~5 min |
| Audit (bge-large, 1024-dim) | ~3 min | ~2 hr on CPU; FAISS makes it ~10 min |
| Cluster discovery (top-5K seeds) | <1 min | ~10 min |
| Embedding compute (bge-large, batched) | ~30 min CPU | ~12 hr CPU; ~1 hr on GPU |
| LLM improver (top-5K lemmas) | wrapper-bounded | wrapper-bounded |

These are CPU figures on a modest laptop. GPU acceleration for the
embedder takes the dominant time down by an order of magnitude. None
of these are bottlenecks the architecture can address; they are
hardware properties.
