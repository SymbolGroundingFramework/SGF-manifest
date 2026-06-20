# SGF Lexicon Pipeline

Turn raw Wiktionary data into an embedded, ontologically-related lexicon
that downstream tools (semantic search, knowledge-graph compilers,
symbol grounding) can query with confidence.

**License:** Apache 2.0. See `LICENSE` and `NOTICE`. Free to use,
modify, redistribute, including commercially. No attribution required
(though appreciated).

**Verified end-to-end** on Simple English Wiktionary (about 72,000
senses) through the no-LLM stages. Read this file top to bottom. Every
section is in execution order, and nothing references a concept that
has not been introduced above it.

---

## What you are building

A single SQLite file, `sgf_lexicon.db`, built in three phases:

- **Phase 1: Bootstrap.** Ingest Wiktionary, generate deterministic
  microglosses, compute diagnostic (bge-small) embeddings, audit
  self-retrieval. No LLM required. End state: a queryable lexicon at
  tier `embedded_v1`. You can ship and query the lexicon here.
- **Phase 2A: Improve microglosses (optional, incremental).** An LLM
  rewrites the microgloss and the four metadata axes (register,
  temporal_status, social_status, specificity) for a
  frequency-prioritized top-N slice. Re-embeds those senses with
  bge-large. Re-audits.
- **Phase 2B: Build the relation graph (optional, incremental).** An
  LLM proposes `IS_A`, `HAS_PART`, and the 15 SGF semantic roles for a
  top-N slice. Clusters are discovered, standard forms are picked, and
  relation targets are resolved by embed-and-filter against the
  lexicon's own embeddings.

Phase 1 is one orchestrator command. Phase 2A and Phase 2B are each
one friendly-runner command, independent of each other, idempotent,
and rerunnable on larger frontiers as you go.

That is the entire flow. The rest of this file walks through it in
order.

---

## Prerequisites

- **Python 3.11 or newer.**
- **About 5 GB of free disk space** for models, the JSONL dump, and the
  resulting database.
- **An LLM you can call from Python.** Not needed for Phase 1.
  Configured before Phase 2.

---

## Phase 1: Bootstrap

Five steps. After this you have a queryable lexicon at tier
`embedded_v1`.

### Step 1. Install Python packages

From this directory:

```
pip install -r requirements.txt
```

`requirements.txt` ships with the CPU build of `onnxruntime` selected.
If you have an NVIDIA GPU or are on Windows with DirectML, open
`requirements.txt`, comment out the `onnxruntime` line, and uncomment
the variant for your hardware. Do not install more than one
`onnxruntime` variant. They conflict silently.

### Step 2. Pre-fetch the heavy assets

```
python download_models.py
```

This downloads about 1.5 GB and stashes everything where the pipeline
will look for it:

| Asset | Size | Stored at |
|---|---|---|
| `Xenova/bge-small-en-v1.5` ONNX model | ~130 MB | HuggingFace cache |
| `Xenova/bge-large-en-v1.5` ONNX model | ~1.34 GB | HuggingFace cache |
| OpenSubtitles 2018 English unigram counts | ~30 MB | `./data/en_full.txt` |

Add `--include-m3` if you want the cross-language `bge-m3` model too
(another ~2.2 GB; only needed for multilingual builds).

You can skip this step and let the downloads happen mid-pipeline, but
the progress reporting gets noisy. Better to do them now.

### Step 3. Download a Wiktionary JSONL dump

Pick one of these direct links. Simple English is the recommended
starting point: tiny, clean, and runs through the whole pipeline in
minutes.

| Edition | Compressed | Expanded | Entries | Senses | Direct link |
|---|---|---|---|---|---|
| Simple English | 4.3 MB | 35 MB | ~61K | ~72K | https://kaikki.org/dictionary/downloads/simple/simple-extract.jsonl.gz |
| Full English | 2.6 GB | 22 GB | several million | many millions | https://kaikki.org/dictionary/raw-wiktextract-data.jsonl.gz |

Vocabulary note: an *entry* in Wiktionary is one word at one part of
speech (for example, "father" as a noun). Each entry contains one or
more *senses* (for example, "a male parent" vs. "the originator of
something").

**Decompress the `.gz` file** and put the `.jsonl` next to this README.
Use 7-Zip on Windows or `gzip -d` on Linux/Mac.

The default filenames after decompressing are `simple-extract.jsonl`
or `raw-wiktextract-data.jsonl`. The next step expects to find a file
called `kaikki.org-dictionary-English.jsonl`. You have two options:

- **Easy.** Rename your downloaded file to
  `kaikki.org-dictionary-English.jsonl`. Every command below works
  as-is.
- **Explicit.** Keep the original filename and pass it via `--source`
  to Step 4's first command (shown there).

### Step 4. Ingest Wiktionary and build the skeleton lexicon

These five commands run once each, in order. Each prints progress and
exits. None require an LLM.

```
python load_wiktionary_jsonl.py
python apply_schema.py
python build_wiktionary_source.py --target sgf_lexicon.db
python build_sgf_lexicon.py --target sgf_lexicon.db
python load_lemma_frequency.py --target sgf_lexicon.db
python build_lemma_forms.py --target sgf_lexicon.db
```

If you kept your downloaded JSONL under its original filename, replace
the first command with:

```
python load_wiktionary_jsonl.py --source simple-extract.jsonl
```

What each command does:

| Command | What it does |
|---|---|
| `load_wiktionary_jsonl.py` | Loads the raw JSONL into an intermediate SQLite (`wiktionary_raw.db`). |
| `apply_schema.py` | Creates `sgf_lexicon.db` with the canonical schema. |
| `build_wiktionary_source.py` | Copies senses from raw into a structured `wiktionary_source` table. |
| `build_sgf_lexicon.py` | Promotes that into the skinny `sgf_lexicon` table: one row per sense, no embeddings yet. |
| `load_lemma_frequency.py` | Joins in OpenSubtitles frequency ranks so the frontier knows which lemmas are common. |
| `build_lemma_forms.py` | Populates `lemma_form` so `--lemma-restrict burned` resolves to senses of `burn` automatically. Enables `--auto-resolve-forms` on the search CLI. |

**Check your work:**

```
python promote_tier.py --target sgf_lexicon.db --show
```

For Simple English you should see roughly 72,000 senses, all at tier
`raw`. (Tier vocabulary is defined in **Reference: tier vocabulary**
below.)

### Step 5. Run the bootstrap pipeline (no LLM)

The pipeline phase is driven by a **config file**: a TOML file that
declares how far each sense should progress (the "target tier") and
which senses are in scope (the "frontier").

The bundle ships `bootstrap_no_llm.toml` for this step. Open it and
read the comments at the top. They explain every setting in place. You
do not have to edit anything to get a first run going. The defaults
run every sense through Stages 3, 4, 5, and 5.5 (deterministic
microgloss, build embedding text, compute diagnostic embedding, audit
retrieval) and stop at maturity tier `embedded_v1`.

#### Choosing your embedder(s)

The lexicon supports three ONNX embedders. You must populate **at
least one** for the lexicon to be queryable. You may populate more
than one; the search server then cascades from best-available to
fallback automatically (see Querying the lexicon).

| Embedder | Size | Dim | Use case |
|---|---|---|---|
| `bge-small-en-v1` | ~130 MB | 384 | English, fast diagnostic, low RAM. Recommended starting point. |
| `bge-large-en-v1` | ~1.34 GB | 1024 | English, best disambiguation. Recommended for production. |
| `bge-m3` | ~2.2 GB | 1024 | Cross-language. Needed only for multilingual builds. |

The shipped `bootstrap_no_llm.toml` config runs `bge-small-en-v1`
because it is the cheapest and fastest. If you want a different
embedder at Phase 1, edit the `diagnostic_embedder` line at the top
of the TOML before running.

#### Run the orchestrator (REQUIRED -- do this BEFORE any standalone
`compute_embeddings.py` invocation)

```
python run_frontier.py --config bootstrap_no_llm.toml
```

The orchestrator runs Stages 3, 4, 5, 5.5 in order: generate
microglosses, build embedding text, compute embeddings, audit. Do not
run the individual scripts by hand for your first build -- the
orchestrator handles the sequencing, resume-on-crash, and progress
reporting. On Simple English (~72K senses) expect 10-30 minutes.

When it finishes, verify:

```
python promote_tier.py --target sgf_lexicon.db --show
```

You should see most senses at tier `embedded_v1`. A handful may still
be at `provisional` if their embedding text was empty.

#### After Phase 1: add more embedders (optional)

The orchestrator built ONE embedder (whichever your config's
`diagnostic_embedder` line named). To populate additional embedders
so the search server's cascade has fallbacks, run `compute_embeddings.py`
directly **only after** the orchestrator above has completed:

```
python compute_embeddings.py --target sgf_lexicon.db --embedding-method bge-large-en-v1 --no-frequency
python compute_embeddings.py --target sgf_lexicon.db --embedding-method bge-m3-v1 --no-frequency
```

The `--no-frequency` flag tells it to process every sense, not just
the frequency-prioritized frontier. Each embedder takes 5-15 minutes
on CPU for the Simple English Wiktionary corpus.

The search server's coverage gate (default 95%) excludes partial
embedders from the automatic cascade, so a half-built embedder does
not silently corrupt query results.

> Note: running `compute_embeddings.py` BEFORE `run_frontier.py` will
> report "0 rows pending" because no `embedding_text` has been built
> yet. That field is populated by Stage 4 (`build_embedding_texts.py`),
> which the orchestrator runs for you.

If you also want to confirm the bundle is healthy on your machine:

```
python selftest.py
```

This builds a synthetic 7-sense database in a tmpdir, runs every
non-LLM stage on it, and prints `ALL TESTS PASS` (or names the broken
stage). Takes under a minute. Safe to run any time.

### What you have after Phase 1

A queryable lexicon. Every sense has a deterministic microgloss, a
canonical_id, the Wiktionary-harvested register / temporal_status /
social_status (where present), a bge-small embedding, and a recorded
self-retrieval audit verdict.

You can use the lexicon now via the search library or the search
server (see **Querying the lexicon** below). The two optional Phase 2
runners sharpen specific slices of the lexicon when you have an LLM
configured.

---

## Configure your LLM (before Phase 2)

Phase 2A and Phase 2B both call an LLM. The pipeline always invokes
one specific file: `llm_wrapper.py`, shipped in this bundle. You shape
it to call whatever LLM you trust.

Open `llm_wrapper.py`. Near the top, two clearly-marked blocks let
you pick how to wire it up:

- **Option A: delegate.** If you already have an LLM-calling script
  that works, set `USE_OPTION_A = True` and edit `EXISTING_LLM_SCRIPT`
  to its absolute path. The adapter forwards every call to your
  existing script. Two-line edit, nothing else.
- **Option B: direct call.** If you do not have an existing script,
  or you want a project-local copy, replace the body of
  `call_my_llm(prompt, tier, temp)` with code that turns a prompt
  string into a response string. Anything in Python is fair game:
  cloud API client, local subprocess, internal endpoint.

Either way works. The pipeline only sees `llm_wrapper.py` and the
contract it honors. (See **Reference: LLM wrapper contract** below.)

Before committing to a real pipeline run, verify the adapter is wired
up:

```
python llm_wrapper.py --self-test
```

Sends a one-word test prompt through your configured path and reports
PASS or FAIL in seconds. Catch a misconfigured adapter now instead of
hours into a real run.

---

## Phase 2A (alternative): Deterministic iterative generator

There is now a second way to assign microglosses that does NOT rely
on one LLM call per sense: `iterate_microglosses.py`. It runs eight
deterministic candidate strategies through a two-test audit
(lemma-filtered + lemma-free in-cluster), keeps the highest-scoring
candidate that passes both gates, and records the full tournament
in a `microgloss_assignment` table. The LLM improver runs only as a
fallback for senses where all eight strategies fail.

When to use which:

- `iterate_microglosses.py` -- the default for new lexicons, the
  long tail, and rebuilds after an embedder upgrade. Cheap.
- `improve_lexicon.py` / `improve_microgloss.py` -- the LLM-driven
  path, recommended for the high-frequency top-N and for senses the
  deterministic generator could not resolve.

```
# Run on every sense that has no current assignment yet:
python iterate_microglosses.py --target sgf_lexicon.db --embedder bge-large-en-v1

# Run only on senses that failed the most recent quality_audit:
python iterate_microglosses.py --target-audit-failures \
    --embedder bge-large-en-v1

# Re-tournament every assignment (after upgrading the embedder):
python iterate_microglosses.py --revisit --embedder bge-large-en-v1

# Inspect one assignment + its full tournament history:
python iterate_microglosses.py --show-assignment en.bank.river_edge.n.wiktionary

# With LLM fallback for tournament failures:
python iterate_microglosses.py --llm-wrapper /path/to/llm_wrapper.py
```

Assignments persist with an `assignment_id` chain via `superseded_by`,
so when you re-tournament after an embedder upgrade the prior
assignment is kept (not deleted) and the new one becomes current.

## Phase 2A: Improve microglosses on a top-N frontier

What it does: an LLM rewrites the microgloss and the four metadata
axes (register, temporal_status, social_status, specificity) for the
top-N most-frequent senses, then re-embeds them with bge-large and
re-audits.

The improver is **contrast-aware**. When it asks the LLM to improve a
sense, it shows the LLM two specific competitor sets to disambiguate
from:

- **Lemma-mates.** Other senses that share this lemma (the other
  meanings of `bank`).
- **Cousins.** The K nearest senses in embedding space that are NOT
  lemma-mates (the words like `tumor` and `carcinoma` that crowd
  around `cancer` even though they spell differently). Default K=5,
  minimum cosine 0.70.

The LLM must produce a microgloss that distinguishes the sense from
both sets. Audit-failed senses are surfaced with their specific
audit collision, so the LLM knows exactly which competitor pushed
self-retrieval below threshold.

### Run it

Start small. Validate the LLM is producing sane output before
scaling up.

```
python improve_lexicon.py --target sgf_lexicon.db --llm-wrapper llm_wrapper.py --top-lemmas 100
```

Then expand:

```
python improve_lexicon.py --target sgf_lexicon.db --llm-wrapper llm_wrapper.py --top-lemmas 1000
python improve_lexicon.py --target sgf_lexicon.db --llm-wrapper llm_wrapper.py --top-lemmas 5000
```

### How it composes

`improve_lexicon.py` is a thin friendly wrapper. It runs four stages
in order, streaming each one's output:

| Stage | What it does | LLM? |
|---|---|---|
| Stage 1/4: improver | LLM rewrites microgloss and the 4 metadata axes for in-scope senses, using contrast sets and (when present) audit collisions | Yes |
| Stage 2/4: embedding text v2 | Rebuilds the embedder input text from the new microglosses | No |
| Stage 3/4: production embeddings | Computes bge-large embeddings for the improved senses | No |
| Stage 4/4: production audit | Four-criterion self-retrieval audit against the bge-large embeddings. This is the ship gate. | No |

Already-improved senses are skipped on re-run. To refine prior LLM
output (for example, after you have improved your LLM wrapper), add
`--revisit`:

```
python improve_lexicon.py --target sgf_lexicon.db --llm-wrapper llm_wrapper.py --top-lemmas 1000 --revisit
```

`--dry-run` prints the plan without running anything.

### What Phase 2A produces

In-scope senses move from `embedded_v1` to `embedded_v2`:

- Sharper microglosses (contrast-disambiguated against lemma-mates and
  cousins).
- All four metadata axes filled, validated against controlled
  vocabularies (invalid values silently dropped).
- bge-large production embeddings.
- Updated `quality_audit` rows under the production audit phase.

Senses outside the top-N stay where they are. Re-run Phase 2A any
time with a larger `--top-lemmas` to expand the improved slice.

---

## Phase 2B: Build the relation graph on a top-N frontier

What it does: an LLM proposes `IS_A`, `HAS_PART`, and the 15 SGF
semantic roles for the top-N most-frequent senses. The lexicon picks
up its navigation graph.

Each proposed relation goes through an **embed-and-filter resolver**:
the LLM provides a `target_lemma` and a `target_description`. The
resolver embeds the description, restricts the search to senses
sharing the lemma, and picks the top-1 match. This handles polysemes
correctly: when the LLM says `target_lemma: bank` with the description
"a financial institution that holds money", the resolver lands on the
correct sense of `bank` even when there are three.

Relation names are validated against a strict 17-name allowlist (the
17 canonical SGF relations, listed at the bottom of this file).
Anything else (the LLM's well-meaning `HAS_PURPOSE`, `HAS_FUNCTION`,
`HAS_USAGE`, and so on) is silently dropped.

### Run it

```
python build_relations.py --target sgf_lexicon.db --llm-wrapper llm_wrapper.py --top-lemmas 100
```

Then expand:

```
python build_relations.py --target sgf_lexicon.db --llm-wrapper llm_wrapper.py --top-lemmas 1000
python build_relations.py --target sgf_lexicon.db --llm-wrapper llm_wrapper.py --top-lemmas 5000
```

### How it composes

`build_relations.py` is a friendly wrapper for three stages:

| Stage | What it does | LLM? |
|---|---|---|
| Stage 1/3: discover clusters | Finds cosine-similar sense clusters (candidates for "these mean the same thing" merging) | No |
| Stage 2/3: standard-form selection | LLM picks the canonical lemma per cluster, so relation targets land on a single standard sense, not on N near-duplicates | Yes (one call per cluster) |
| Stage 3/3: harvest semantic relations | LLM proposes IS_A, HAS_PART, and the 15 SGF roles for each in-scope sense; targets resolved by embed-and-filter | Yes (one call per sense) |

Already-harvested senses are skipped on re-run. To re-harvest prior
output (for example, after Phase 2A sharpened the microglosses that
relation targets resolve against), add `--revisit`:

```
python build_relations.py --target sgf_lexicon.db --llm-wrapper llm_wrapper.py --top-lemmas 1000 --revisit
```

If you have already discovered clusters and selected standard forms
on a larger scope, you can skip those stages:

```
python build_relations.py --target sgf_lexicon.db --llm-wrapper llm_wrapper.py --top-lemmas 1000 --skip-clusters --skip-forms
```

`--dry-run` prints the plan without running anything.

### What Phase 2B produces

In-scope senses move to tier `related`:

- `sense_cluster` rows grouping near-duplicate senses.
- `sense_standard_form` rows declaring the canonical lemma per
  cluster.
- `sense_semantic_relation` rows carrying typed edges from the 17
  canonical relation names only. Each edge records the resolution
  method (`embed_filter` or `pattern`) and, for embed-filter resolutions,
  the cosine score.

### Phase 2A and Phase 2B are independent

You can run either without the other. You can run them in either
order. Running Phase 2A first is the recommended pattern, because
sharper microglosses make cousin discovery (Phase 2A) and target
resolution (Phase 2B) both more accurate. But the pipeline does not
require it.

---

## Querying the lexicon

After Phase 1 (or after any Phase 2 run), the lexicon is queryable.
Two ways to ask it questions.

### Option 1: programmatic, in-process (no server)

For scripts that already run Python and want to query the lexicon from
code:

```python
import lexicon_search

ctx = lexicon_search.load_lexicon("sgf_lexicon.db")

# Search by text (requires onnxruntime + tokenizers for embedding)
result = lexicon_search.search(
    ctx,
    text="the river bank flooded",
    k=5,
    policy_name="snap_to_standard",
)
for r in result["results"]:
    print(r["canonical_id"], r["score"])

# Search restricted to a lemma (the grounding-mode case)
result = lexicon_search.search(
    ctx,
    text="a soft inner tissue where blood cells form",
    lemma_restrict="marrow",
    k=3,
)
```

This is the same library Phase 2B's relation resolver uses internally
to ground LLM-produced relation targets. One canonical implementation,
no drift.

### Option 2: HTTP server (load once, query many)

For long-running services that need many queries without paying the
embedder and matrix load cost each time:

```
pip install fastapi uvicorn pydantic
python glean_search_server.py --lexicon sgf_lexicon.db
```

Then from any client (CLI, GLEAN compiler, custom script):

```
python glean_search.py "the river bank flooded"
python glean_search.py --lemma kiddo
python glean_search.py --lemma leukemia
python glean_search.py --health
```

The server loads the lexicon and embedders ONCE at boot (about 1-2
minutes for a 1.7M-sense full English build), then answers queries in
10-50ms. By default it binds to `127.0.0.1:8400` with no auth.

The server is a thin FastAPI wrapper over `lexicon_search.py`. Same
code, two deployment modes.

---

## Reference: tier vocabulary

Each sense in `sgf_lexicon.db` carries a **maturity tier** that says
how far it has progressed:

| Tier | What is true | Set by |
|---|---|---|
| `raw` | Wiktionary record loaded; no microgloss yet | Phase 1 Step 4 |
| `provisional` | Microgloss + canonical_id + metadata harvested | Phase 1 Step 5 (Stage 3) |
| `embedded_v1` | First-pass (bge-small) embedding present | Phase 1 Step 5 (Stage 5) |
| `improved` | LLM-improved microgloss + 4 metadata axes filled | Phase 2A |
| `embedded_v2` | Production (bge-large) embedding present | Phase 2A |
| `clustered` | In a content-identical group, or confirmed singleton | Phase 2B |
| `related` | Semantic relations harvested | Phase 2B |

Tiers progress in this exact order. Senses already at or past a
target tier are skipped on re-runs. The two Phase 2 runners are
incremental: re-running with a larger `--top-lemmas` only processes
the newly-in-scope senses.

---

## Reference: how the pipeline knows it worked

The pipeline does not ask you to trust it. It runs a falsifiable test
on its own output and reports the result.

The test is called **self-retrieval at top-1**. For every sense in
the lexicon, take that sense's embedding vector and ask: "which sense
in the lexicon is the nearest neighbor by cosine similarity?" The
answer should be the sense itself. If it is not (if the embedding for
`bank` (river edge) ranks `bank` (financial institution) above
itself), that sense's embedding is degenerate. Downstream clustering
and relation-harvesting on a degenerate embedding produces garbage.

### Four criteria, four production regimes

The lexicon supports two search modes, plus a snap-to-standard policy.
Each has its own audit criterion:

| Criterion | What it tests | Production regime it mirrors |
|---|---|---|
| `pass_intralemma` | Among lemma-mates only, am I nearest to me? | Grounding mode (the lemma is known) |
| `pass_strict` | Across the entire lexicon, am I at top-1? | Cross-language mode (foreign-language token, no lemma overlap) |
| `pass_topk` | Across the entire lexicon, am I in top-K? | Cross-language mode, relaxed |
| `pass_cluster` | Is top-1 either me OR a content-identical sibling? | Snap-to-standard policy. Only meaningful after clusters are built. |

Monosemes (lemmas with only one sense) trivially pass intralemma:
there are no siblings to compete with. The audit reports the
polyseme intralemma pass rate separately so the number is meaningful.

### Where the audit runs

- **Phase 1's diagnostic audit** runs against the bge-small embeddings
  at the end of Step 5. Failures are recorded so Phase 2A can show
  them to the LLM as "you collided with sense X; disambiguate."
- **Phase 2A's production audit** runs against the bge-large
  embeddings after the improver has rewritten the microglosses. This
  is the ship gate.

Results are written per-sense to the `quality_audit` table so you can
see exactly which senses failed and why. The aggregate pass rate is
printed at the end of each audit run.

### Why this matters

Most embedding-based systems ship without a self-test. They report
"we used model X" and ask you to take it on faith that the vectors
mean something. This pipeline reports a number (a falsifiable,
automatable number) that says whether the lexicon is actually
queryable.

If the diagnostic audit reports 60% on `pass_intralemma`, you know
not to spend on Phase 2A yet, because something upstream is broken.
If the production audit reports 99.2% on `pass_cluster`, you know
what you are shipping.

The audit also runs fast: batched NumPy matmul on a CPU does 72,000
senses in about a minute. There is never a reason to skip it.

---

## Reference: the 12 stages

You do not run these by hand. The orchestrator and the two Phase 2
runners do. This list documents what each stage does, in order,
mapped to the phase that drives it:

```
Phase 1 (bootstrap_no_llm.toml via run_frontier.py)
  1.   Build wiktionary_source                  -> build_wiktionary_source.py     (raw)
  2.   Build sgf_lexicon (skinny)               -> build_sgf_lexicon.py           (raw)
  2.5  Load lemma frequency rankings            -> load_lemma_frequency.py        (raw)
  3.   Generate provisional microglosses        -> generate_microglosses.py       (provisional)
  4.   Build embedding_text v1                  -> build_embedding_texts.py --pass v1
  5.   Compute first-pass embeddings            -> compute_embeddings.py (bge-small) (embedded_v1)
  5.5  Audit first-pass self-retrieval          -> quality_audit.py

Phase 2A (improve_lexicon.py)
  6.   LLM improvement pass                     -> improve_microgloss.py          (improved)
  7.   Build embedding_text v2                  -> build_embedding_texts.py --pass v2
  8.   Compute production embeddings            -> compute_embeddings.py (bge-large) (embedded_v2)
  8.5  Audit production self-retrieval          -> quality_audit.py

Phase 2B (build_relations.py)
  9.   Discover content-identical clusters      -> discover_clusters.py
  10.  Select standard form per cluster         -> select_standard_forms.py       (clustered)
  11.  Harvest semantic relations               -> harvest_semantic_relations.py  (related)
  12.  (optional) Per-sense fingerprints        -> compute_sense_fingerprints.py
```

Stages 1, 2, and 2.5 are the same scripts you ran in Phase 1 Step 4.
The orchestrator can re-run them safely (they are idempotent), but
once your DB is populated you typically only re-run from Stage 3
onward.

---

## Reference: the 17 canonical semantic relations

Phase 2B's harvester accepts edges only from these 17 names. Anything
else (the LLM's `HAS_PURPOSE`, `HAS_FUNCTION`, `HAS_USAGE`, and
similar inventions) is silently dropped.

**Ontological (2):** `IS_A`, `HAS_PART`

**Core roles (6):** `HAS_AGENT`, `HAS_PATIENT`, `HAS_THEME`,
`HAS_EXPERIENCER`, `HAS_RECIPIENT`, `HAS_BENEFICIARY`

**Context roles (9):** `HAS_TIME`, `HAS_LOCATION`, `HAS_SOURCE`,
`HAS_DESTINATION`, `HAS_MANNER`, `HAS_INSTRUMENT`, `HAS_CAUSE`,
`HAS_REASON`, `HAS_ATTRIBUTE`

`HAS_PURPOSE` is intentionally excluded. Use `HAS_REASON` instead.
(See Part 11 of `SGF_LEXICON_PIPELINE.md` for the deliberation.)

---

## Reference: LLM wrapper contract

The pipeline invokes `llm_wrapper.py` with this command line:

```
python llm_wrapper.py --in-file <prompt.txt> --out-file <response.txt>
```

The adapter must read the entire prompt from `--in-file`, send it to
your LLM, and write the entire response to `--out-file`. The pipeline
always passes absolute paths.

The pipeline may also pass `--tier flash` or `--tier reasoning`, and
`--temp 0.0` (or some other float). The pipeline uses `flash` for the
typical case and `reasoning` only for the rare harder calls. Your
adapter can honor those flags by routing to whichever model you
consider cheap vs. heavy, or ignore them entirely.

The shipped `llm_wrapper.py` already handles all the argument parsing
and file I/O. You only fill in the LLM-calling part.

The pipeline's prompts are designed around a two-layer envelope
contract:

- LLM output is read by extracting whatever is between
  `<answer>...</answer>` tags. Anything in `<comments>...</comments>`
  tags (or anywhere else) is ignored.
- Inside the envelope, fields are key-value blocks (one block per
  proposed item; one `key: value` line per field). No JSON.

The shipped parser (`llm_kv_parser.py`) is permissive about
whitespace, blank lines between blocks, and case. Allowlist
validation runs after parsing; values outside the controlled
vocabularies are silently dropped.

---

## Reference: friendly-runner and orchestrator flags

### Phase 1 orchestrator

```
python run_frontier.py --config <FILE>            # required
                       [--target sgf_lexicon.db]   # default
                       [--llm-wrapper <PATH>]      # required for stages 6, 10, 11
                       [--dry-run]                 # print plan, run nothing
                       [--skip-stages 6,10,11]     # comma-separated stage IDs to skip
                       [--only-stages 5,5.5]       # comma-separated stage IDs to RUN
                       [--log-dir logs/]           # where stage logs are written
```

### Phase 2A friendly runner

```
python improve_lexicon.py --target sgf_lexicon.db
                          --llm-wrapper <PATH>             # required
                          [--top-lemmas 1000]              # frequency-prioritized scope
                          [--revisit]                      # re-process already-improved senses
                          [--diagnostic-embedder bge-small-en-v1]
                          [--production-embedder bge-large-en-v1]
                          [--device cpu|dml|cuda]
                          [--tier flash]                   # LLM tier hint
                          [--temp 0.0]
                          [--skip-improve|--skip-embed|--skip-audit]
                          [--dry-run]
```

### Phase 2B friendly runner

```
python build_relations.py --target sgf_lexicon.db
                          --llm-wrapper <PATH>             # required
                          [--top-lemmas 1000]              # frequency-prioritized scope
                          [--revisit]                      # re-process already-harvested senses
                          [--production-embedder bge-large-en-v1]
                          [--cluster-top-k 20]
                          [--strong-threshold <FLOAT>]
                          [--tier flash]
                          [--temp 0.0]
                          [--patterns-only|--llm-only]
                          [--skip-clusters|--skip-forms|--skip-harvest]
                          [--dry-run]
```

---

## Files

```
README.md                        # this file
requirements.txt                 # pip dependencies
schema.sql                       # canonical DB schema (idempotent)
apply_schema.py                  # apply schema.sql via Python (no sqlite3 CLI needed)
download_models.py               # pre-fetch ONNX models + frequency file
bootstrap_no_llm.toml            # Phase 1 config (no LLM)
bootstrap_top_5k.toml            # legacy single-shot LLM config (kept for compatibility)

SGF_LEXICON_PIPELINE.md          # the full architectural spec
SGF_ROADMAP.md                   # known-deferred work for v1.1 and v2
V2_VISION.md                     # forward-looking sketch: lexicon as encyclopedia
selftest.py                      # end-to-end self-test on a synthetic mini-DB
llm_wrapper.py                   # editable adapter the pipeline calls (you configure)

# Friendly runners (the user-facing entry points for Phase 2)
improve_lexicon.py               # Phase 2A: improve microglosses + metadata + re-embed + re-audit
build_relations.py               # Phase 2B: clusters + standard forms + relation graph

# Shared search library + optional HTTP server + CLI
lexicon_search.py                # canonical search/policy/contrast-set/standard-form module
glean_search_server.py           # FastAPI daemon (long-running query server)
glean_search.py                  # CLI client for the server
llm_kv_parser.py                 # tolerant LLM-response parser (envelope + KV blocks)

# Stage scripts (run by orchestrator and friendly runners, not by you)
load_wiktionary_jsonl.py         # Stage 0
build_wiktionary_source.py       # Stage 1
build_sgf_lexicon.py             # Stage 2
load_lemma_frequency.py          # Stage 2.5
generate_microglosses.py         # Stage 3
build_embedding_texts.py         # Stages 4 + 7
compute_embeddings.py            # Stages 5 + 8
quality_audit.py                 # Stages 5.5 + 8.5
improve_microgloss.py            # Stage 6
discover_clusters.py             # Stage 9
select_standard_forms.py         # Stage 10
harvest_semantic_relations.py    # Stage 11
compute_sense_fingerprints.py    # Stage 12 (optional)

# Shared modules (not invoked directly)
pos_converter.py                 # POS normalization
microgloss.py                    # deterministic gloss generator
lexicon_metadata.py              # controlled vocabularies (4 metadata axes + 17 relations)

# Orchestration + inspection
run_frontier.py                  # TOML-driven orchestrator (Phase 1)
promote_tier.py                  # tier inspection / adjustment
pipeline_status.py               # show pipeline progress

# Utilities
export_skinny_lexicon.py         # export a slim version for distribution
calibrate_fingerprint.py         # fingerprint tuning
wiktionary_diagnostic.py         # debug missing senses for specific lemmas
```

---

## What this feeds

This lexicon is the substrate for two downstream bundles:

| Bundle | Role |
|---|---|
| `glean_search_server` | FastAPI daemon that loads the embedder and embedding matrices once and serves HTTP queries with the policy-driven cascade (snap_to_standard / preserve_register / research_unfiltered) |
| `glean` (the compiler) | Prose-to-knowledge-graph compiler that reads English text and emits structurally typed synapses grounded against this lexicon |

The integration contract between the lexicon and the search server is
specified in Part 15 of `SGF_LEXICON_PIPELINE.md`.

---

## Looking ahead: V2

The lexicon you just built grounds senses. It is a structured
dictionary with cosine-queryable embeddings and a navigation graph
over IS_A, HAS_PART, and the 15 SGF roles. That is V1.

There is a possible V2 in which the lexicon becomes a miniature
structured encyclopedia: every concept carries the typical synapses
that characterize it (presidents lead, govern, are elected; rivers
flow, carry, flood; surgeons cut, heal, diagnose). The work to get
there is non-trivial and touches doctrine. It is captured in
`V2_VISION.md` and in the V2 entry of `SGF_ROADMAP.md`. Search the
code for `TODO V2:` to find the natural extension points.

Nothing about V2 changes how V1 is used. V1 ships clean. V2 is a
separate conversation when there is appetite for it.

---

## Design commitments

Brief version (full Decision Log in `SGF_LEXICON_PIPELINE.md` Part 11):

- **canonical_id format**: `<iso_lang>.<lemma>.<microgloss>.<pos>.<namespace>`
- **Quality criterion**: self-retrieval at top-1. Ship threshold: 99%
  relaxed pass rate.
- **Microgloss is content-only** by default; extended only when audit
  demands.
- **Specialist terms preserve themselves** under the default policy.
  Leukemia stays leukemia, not cancer.
- **Two-pass embedding**: bge-small (diagnostic) then bge-large
  (production). bge-m3 may be added for cross-language.
- **Maturity tiers enable incremental bootstrap**. Senses can sit at
  `raw` indefinitely; only frontier expansion incurs cost.
- **Contrast-aware improver**. The LLM sees lemma-mates and cousins,
  not just the sense in isolation.
- **17 relation names, period.** Allowlist enforced at parse time.
- **Two-layer LLM contract.** `<answer>...</answer>` envelope plus
  key-value blocks. No JSON.
- **ONNX only.** No `sentence-transformers`. Avoid the dependency
  hell.
