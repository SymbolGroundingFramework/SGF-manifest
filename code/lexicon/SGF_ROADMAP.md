# SGF Lexicon Roadmap

This file lists known-deferred work. Each item is shippable on its own;
nothing here is a blocker for v1.

## Recently shipped (v1.3): inflection resolution + bug fixes

- **`lemma_form` table** maps inflected surface forms to lemmas
  (burned -> burn, geese -> goose, ran -> run). Populated by
  `build_lemma_forms.py` from `wiktionary_source.forms_json`.
- **`lemma_resolver.py`** is the in-memory lookup. Cached on first
  call; supports identity match, multi-pos disambiguation, and
  a `prefer_pos` hint.
- **Search server + CLI accept `auto_resolve_forms`**. New
  `--auto-resolve-forms` flag on `glean_search.py`, new JSON field on
  `/search` POST. With it enabled, `--lemma-restrict burned` returns
  all senses of `burn`.
- **New `--pos-restrict` CLI flag** for narrowing to one part-of-speech.
- **bge-m3 vs bge-m3-v1 alignment.** Canonical name is now
  `bge-m3-v1` everywhere (matches `compute_embeddings.py`). The bare
  `bge-m3` string still works in repo lookup tables for backward
  compatibility, but TOML cascades, README, and configs use the
  versioned name.
- **Bug fix: v1 SELECT column-count mismatch.** `build_embedding_texts.py`
  was returning 22 columns for v1 (10 NULL pads instead of 9), causing
  `ValueError: too many values to unpack (expected 21)` during
  `run_frontier.py`. Fixed; regression test added.
- **README ordering fix.** Step 5 now puts `run_frontier.py` BEFORE
  the standalone `compute_embeddings.py` examples so users do not
  accidentally skip Phase 1.

## Recently shipped (v1.2): deterministic iterative microgloss generator

A new path for assigning microglosses without an LLM per sense, with
full assignment provenance recorded so the choice can be re-audited
later (e.g. after an embedder upgrade).

- **Polysemy-tier classification.** Lemmas bin into `low` (1-5 senses),
  `medium` (6-15), `high` (16-40), `very_high` (41+). The cluster cap
  and audit thresholds adapt per tier so high-polyseme lemmas like
  `bank` or `set` are not held to standards their structure cannot
  meet.
- **Eight deterministic candidate strategies** (`candidate_strategies.py`):
  compositional, lemma-mate disambig, cluster anchor, tag qualified,
  example distilled, antonym contrast, hypernym specialized,
  definitional fallback. Tried in order; tournament picks the best.
- **Two-test audit** (`microgloss_audit.py`): T1 lemma-filtered top-K,
  T2 lemma-free top-K within a close-cousin cluster. Both gates must
  pass; quantile reported for diagnosis.
- **`microgloss_assignment` table.** New schema records the winning
  strategy, both audit verdicts, tournament candidate JSON, embedder
  at assignment time, and a `superseded_by` chain so assignment
  history is preserved across re-audits.
- **`iterate_microglosses.py`** is the entry point. Supports
  `--target-audit-failures`, `--revisit`, `--wsids-file`, `--dry-run`,
  and `--show-assignment CANONICAL_ID_OR_WSID`. LLM improver runs
  only as a fallback when all eight deterministic strategies fail
  the tournament; configurable via `--llm-wrapper` / `--no-llm-fallback`.

## Recently shipped (v1.1): retrieval-quality polish

- **Loader enrichment.** `build_embedding_texts.py` now emits all
  available linkage types per sense (synonyms, antonyms, hypernyms,
  hyponyms, related, coordinate_terms) and up to four example
  sentences instead of one. `GLOSS_MAX_CHARS` raised 240 -> 600;
  `MAX_SYNONYMS` raised 5 -> 15.
- **Default cascade promotes bge-large.** The default
  `[retrieval.embedder_cascade]` no longer leads with `bge-m3`; it
  leads with `bge-large-en-v1` for stronger English-only separation.
  `bge-m3` stays available in the explicit `multilingual` cascade row.
- **Absolute-confidence floor trigger.** `search_pipeline.bm25` and
  `search_pipeline.llm_tiebreak` accept a new `abs_confidence_floor`
  field. When set above 0.0, the stage fires whenever the prior
  stage's top-1 score is below the floor, in addition to the
  margin-based trigger. Catches the cosine-flat case where every
  candidate scores low and the embedder is essentially guessing.
- **Targeted improver.** `improve_microgloss.py` gains a
  `--target-audit-failures` flag that scopes the improver run to
  exactly the senses that failed the most recent quality_audit run
  (paired with `--audit-phase post|diagnostic`).
- **Diagnostic dump.** `build_embedding_texts.py --show-embedding-text
  CANONICAL_ID_OR_WSID` prints the v1 and v2 embedding texts for one
  sense without writing to the DB. Useful when investigating why a
  search query missed (or matched) a given sense.

## Recently shipped (v1.0): Phase 1 / Phase 2A / Phase 2B refactor

The 12-stage pipeline has been reorganized into three named phases
backed by two friendly runners. This is the v1.0 user-facing
interface:

- **Phase 1 (Bootstrap, no LLM):** Stages 1-5.5, driven by
  `run_frontier.py --config bootstrap_no_llm.toml`. Ends at
  `embedded_v1`. The lexicon is queryable after this phase.
- **Phase 2A (Improve microglosses + metadata, LLM):** Stages 6, 7,
  8, 8.5, driven by `improve_lexicon.py --top-lemmas N`. The
  improver is now contrast-aware: it shows the LLM the sense's
  lemma-mates and embedding cousins (K=5, cousin_min_cosine=0.70),
  plus the diagnostic-audit collision when one exists. Four metadata
  axes filled (register, temporal_status, social_status,
  specificity), with allowlist validation.
- **Phase 2B (Build the relation graph, LLM):** Stages 9, 10, 11,
  driven by `build_relations.py --top-lemmas N`. The 17 canonical
  relation names are enforced at parse time (anything else is
  silently dropped). The Stage 11 resolver uses embed-and-filter:
  LLM produces `target_lemma` + `target_description`; resolver
  embeds the description with lemma_restrict, picks top-1.

Both Phase 2 runners are incremental, idempotent, and support
`--revisit` to refine prior LLM output. They are thin wrappers over
the existing stage scripts and stream subprocess output live.

LLM contract is now `<answer>...</answer>` envelope + key-value
blocks (no JSON, no regex). Parser lives in `llm_kv_parser.py`.

## v1.1: Closed-loop refinement (Stage 8.6)

**The gap.** After Stage 8.5 audits the production embeddings, any
sense still failing `pass_intralemma` is recorded in `quality_audit`
but not re-attempted. The pipeline declares victory if the aggregate
pass rate cleared 99%. That is acceptable for a v1 ship gate, but it
is not what the architecture should be.

**The fix.** Add Stage 8.6, which loops on residual failures only:

```
Inputs:  senses where Stage 8.5 reported pass_intralemma = 0
Loop (max N iterations, default 3):
  1. For each failing sense, gather:
     - current microgloss
     - the audit verdict (what ranked above it, by how much)
     - the competing sense's microgloss (the one that beat it)
  2. LLM call with a sharper prompt:
     "These two senses collided in vector space. Sense A is currently
      glossed '<X>', Sense B is currently glossed '<Y>'. Rewrite the
      microgloss for Sense A to be unambiguously distinguishable from
      Sense B while staying content-only and faithful to its Wiktionary
      source."
  3. Rebuild embedding_text for affected senses; re-embed.
  4. Re-audit the affected senses.
  5. If pass_intralemma = 1, stop for that sense. If still failing,
     iterate up to N times.
```

**Cost.** Bounded by the residual failure set, which by Stage 8.5
should be a small percentage of in-scope senses. Each LLM call here
is cheaper than the original Stage 6 call because it's targeted at
one specific collision, not a full enrichment.

**Implementation.** One new script, `refine_microgloss.py`. One new
column on `quality_audit`: `audit_iteration` (integer, default 0).
One orchestrator update in `run_frontier.py`.

## v1.1: Post-cluster audit (Stage 9.5)

**The gap.** Once Stages 9 and 10 build clusters, the `pass_cluster`
criterion becomes computable. The current pipeline does not have a
dedicated re-audit stage after clusters land. `pass_cluster` should
be the v1.1 ship gate, replacing the strict-pass criterion.

**The fix.** Add Stage 9.5, which re-runs `quality_audit.py` against
the production embeddings after Stage 10 has selected standard forms.
This is the same script with no code change; only a new orchestrator
hook.

## v1.1: Retire the standalone glean_search_server bundle

**The change in v1.0 of this bundle:** the search server's code has
been folded INTO the lexicon bundle. The lexicon bundle now ships
three files that together provide the canonical search-server
implementation:

- `lexicon_search.py` -- the shared library (flat module of functions,
  dict-based context; no classes). This is the canonical search +
  policy + standard-form-rewrite code.
- `glean_search_server.py` -- a thin FastAPI wrapper that exposes the
  shared library over HTTP. Used for long-running daemon deployments
  (cold-start once, serve many).
- `glean_search.py` -- a thin CLI client over HTTP.

The lexicon bootstrap's Stage 11 resolver imports `lexicon_search`
IN-PROCESS. No HTTP, no two-process dance. Same code path as the
production server -- there is only ONE search implementation now.

**What v1.1 needs to do:**

- Delete the standalone `glean_search_server_v1` bundle (or stub it
  out as a thin re-export from this bundle).
- Update the GLEAN compiler's HTTP client to point at this bundle's
  server.
- Add a small README pointer in any retired bundle telling users to
  use the lexicon bundle instead.

The lexicon-side change is already done in v1.0 of this bundle.

## v1.1: FAISS swap-in

**The gap.** v1 uses NumPy batched matmul for all nearest-neighbor
work. This is correct and fast up to ~200K senses (audit completes in
~3 minutes). Above that, FAISS is meaningfully faster and the BLAS
matmul kernel starts to dominate wall time.

**The fix.** Two call sites change:

- `quality_audit.py`: replace the `Q @ vecs.T` + `argpartition` block
  with `faiss_index.search(Q, K)`.
- `discover_clusters.py`: same swap, in the per-batch top-K kernel.

**No schema change. No CLI change. No downstream change.** FAISS
becomes a hard dependency; the CPU build is dependency-free.

## v1.1: Cross-language coverage (bge-m3)

**The gap.** The lexicon design supports cross-language retrieval
(Part 7.5) via the universal English microgloss vocabulary, but the
bge-m3 multilingual embedder is currently optional (`download_models.py
--include-m3`). Full cross-language coverage requires running
`compute_embeddings.py` with the m3 method for the same scope as the
production English embeddings.

**The fix.** Make `--include-m3` the default in `download_models.py`.
Add an `embeddings.cross_language = "bge-m3-v1"` config key to the
TOML configs. Run the m3 pass as Stage 8.7 (or as part of an extended
Stage 8) when configured.

## v2: Stage 3.5 deterministic refinement

**The gap.** Stage 3 produces deterministic microglosses without ever
being told "your gloss for sense X collided with sense Y" -- because
Stage 5.5 happens after Stage 3 has already finished. Some intralemma
collisions can be resolved deterministically (e.g., by adding a
controlled-vocabulary marker like `_aviation` or `_finance`) without
ever calling an LLM.

**The fix.** Add Stage 3.5, which:

1. Runs a mini-audit against the Stage 3 deterministic embeddings
   (cheap, no production embedder needed).
2. For any polyseme whose senses collide, attempts deterministic
   marker injection from the controlled vocabulary in Part 1.3 of
   the spec.
3. Re-runs the deterministic microgloss generator on the marked-up
   senses.

This shrinks the work Stage 6 has to do (fewer senses need LLM
attention) without changing the architecture.

## v2: Single-file query CLI (SUPERSEDED in v1.0)

**Status: shipped.** The v1.0 bundle includes `glean_search.py`, a
standalone CLI that loads `lexicon_search.py` in-process and serves
the same policy-driven cascade as the FastAPI server. Use it for
sanity-checking a freshly built lexicon before standing up the
long-running server.

## v2: Lexicon as a miniature structured-knowledge encyclopedia

**The vision.** Today the lexicon grounds senses with one-sentence
microglosses. That is enough for cosine retrieval and downstream
GLEAN consumption. It is not yet an encyclopedia. A lexicon entry
for `president` knows the word exists, knows it IS_A leader, and
carries a microgloss. It does not know that presidents lead, govern,
are elected, sign bills, or veto. That structural knowledge lives in
the prose of glosses and example sentences but is not currently
extracted into queryable form.

**The opportunity.** Run each lexicon entry's gloss plus seeded
example sentences through the same extractor GLEAN already uses for
prose-to-synapses. Attach the resulting descriptive synapses (and
possibly conceptual SynapseGroups) to the lexicon entry. The lexicon
stops being a dictionary and starts being a miniature structured
encyclopedia: every concept carries the typical synapses that
characterize it.

**The shared sub-component.** GLEAN's pipeline today runs four
stages on prose: entity_census, clause_to_synapse, framing,
synapse_grouper. These four are not GLEAN-specific. They are a
generic prose-to-structured-meaning extractor. Factor them out of
GLEAN into a shared bundle (working name `synapse_extractor`) with
two consumers:

- GLEAN's `compile_document.py` -- the existing document-compilation
  caller (essays, PDFs, articles).
- A new lexicon stage (working name Phase 2C) that runs the same
  extractor against each lexicon entry's gloss + examples and writes
  the output into lexicon-side tables for descriptive synapses.

The extractor is the same code, the same closed grammar (17
relations), the same framing layer. Only the input source and the
output target differ.

**Open architectural question.** SGF doctrine currently says
"SynapseGroups are forbidden in lexicon entries" (Architecture of
Meaning context doc, derived from the prohibition against nesting
full discourse-level structures inside the flat sense-level DAG).
This blanket prohibition probably needs refinement. The intent
behind it is sound: instance-level facts ("Theodore Roosevelt was
the 26th president") do not belong in the lexicon's concept-level
DAG; they belong in the synapse store about instances. But
concept-level descriptive synapses ("presidents lead countries") are
about the concept itself, not about any particular instance, and
arguably do belong with the concept they describe. V2 is the right
time to formally distinguish these two cases and update doctrine if
needed.

**Implementation sketch (not committing yet).**

- New table `lexicon_descriptive_synapse` keyed on
  `wiktionary_source_id`, storing one row per (lexicon entry, hub
  verb canonical_id, role tuple).
- New table `lexicon_descriptive_group` for conceptual synapse
  groups attached to lexicon entries (only if doctrine permits).
- New Phase 2C friendly runner `extract_encyclopedic.py` that walks
  the top-N frontier, runs the extractor against each entry's
  gloss + examples, and writes the results.
- Audit-gate question: do attached synapses contribute to the
  embedding text? Working answer: no, the microgloss stays the
  retrieval anchor; descriptive synapses are queryable structure,
  not retrieval input. This keeps the 99% self-retrieval ship gate
  meaningful.

**Why this is V2, not V1.1.** The work touches doctrine, requires a
clean factoring of GLEAN's internals, and changes the lexicon's
identity from "sense dictionary" to "structured encyclopedia." That
is a deliberate architectural step, not a feature add.

## v2: GPU acceleration documentation

**The gap.** `compute_embeddings.py` already supports `--device dml`
(DirectML for Windows) and CUDA via `onnxruntime-gpu`, but the README
only documents the CPU path. Developers with GPUs see no benefit
without reading the script source.

**The fix.** Add a short "Going faster" section to the README that
documents the alternate ONNX Runtime builds and their `--device`
flags.
