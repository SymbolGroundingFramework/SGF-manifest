\# ADDENDUM: Pipeline Wrappers, Codebase Profiling, and Tranche Planning

\*\*Phase 2 Extensions to the AI OS Pipeline Architecture\*\*



\*Standalone document — supplements both the White Paper and Technical Specification v8. Does not invalidate or replace either.\*



\---



\## SECTION 1: Conceptual Addendum to the White Paper



\### 1.1 Motivation



The original architecture defined a single pipeline: workflow map → stages → primitives → artifacts. This is the \*\*atomic unit of execution\*\*. Experience with real-world use cases revealed three recurring patterns that are natural compositions of this atomic unit — not new architectures, but \*\*wrappers around the same core\*\*.



These patterns are:



1\. \*\*Iterative refinement\*\* (outer loop) — run the pipeline multiple times, feeding previous output as context for the next pass.

2\. \*\*Codebase profiling\*\* — scan an existing folder, build searchable metadata, then use that metadata during retrieval stages.

3\. \*\*Tranche planning\*\* — take a large, unstructured wish list, burst it into ordered delivery phases, then run the pipeline once per phase.



All three patterns share a common insight: \*\*the pipeline is a composable CLI\*\*. Each wrapper calls the one below it with no knowledge of internal stages. This is the Unix philosophy applied to LLM pipelines.



\### 1.2 The Composability Principle



```

tranche.py     → calls iterate.py N times (once per phase)

iterate.py     → calls run.py N times (once per iteration)

run.py         → executes the workflow map once

```



Each layer:

\- Is independently invocable (you can call any layer directly)

\- Normalizes its own input at the boundary (defensive idempotent cleaning)

\- Produces its own set of artifacts (visible, auditable, restartable)

\- Does not need to know about layers above it



This preserves the core architectural guarantees: determinism, visibility, and restartability. Each wrapper simply loops over calls to the layer below, passing explicit artifacts between iterations.



\### 1.3 Normalize at the Boundary (Defensive Cleaning)



Every layer applies a cheap, idempotent cleanup to its input as its first operation. This is not "extra work" — it is the mechanism that makes each layer independently invocable. A user can feed a raw stream-of-consciousness file directly to `run.py` and it will work. A user can call `tranche.py` with the same SOC and it will also work. The cleanup is idempotent: cleaning a clean input produces the same clean input.



A side-effect artifact (`cleanup\_log.txt`) records what was changed, or "No changes needed." This satisfies the visibility requirement without adding branching stages.



\### 1.4 Relation to the Original Design



The original white paper stated: \*"Recurring behaviors discovered in Layer 3 SHOULD be extracted downward into lower layers."\* These three patterns are exactly that discovery. They are not corrections to the architecture — they are natural extensions that the architecture anticipated. The core pipeline, workflow map, artifact registry, and hill-climb primitive remain unchanged. Only new wrapper layers are added above.



\---



\## SECTION 2: Technical Addendum to the Specification



\### 2.1 New CLI Wrappers



Three CLI entry points compose the core `run` command:



| Command | Purpose | Calls | Typical Use |

|---------|---------|-------|-------------|

| `pipeline run` | Single pass through one workflow map | (core engine) | Debugging, single-shot tasks |

| `pipeline iterate` | Multi-pass refinement | `run` in a loop, passing `--previous-attempt` | Iterative improvement of code or text |

| `pipeline tranche` | SOC burst into phases | `iterate` for each phase | Large feature development from wish list |



\#### 2.1.1 `pipeline run`



```

pipeline run --map <workflow\_map.txt> \\

&#x20;            --request <request\_text\_or\_file> \\

&#x20;            --input-folder <path> \\

&#x20;            \[--iteration <N>] \\

&#x20;            \[--skip-cleanup]

```



\- `--request`: A plain-text request or path to a `.txt` file.

\- `--input-folder`: Folder containing existing codebase (may be empty for greenfield).

\- `--iteration`: Pass number (default 1). Sets iteration context for prompt slots.

\- `--skip-cleanup`: Skip the input normalization stage (rare; only when input is known clean).



\#### 2.1.2 `pipeline iterate`



```

pipeline iterate --map <workflow\_map.txt> \\

&#x20;                --request <request\_text\_or\_file> \\

&#x20;                --input-folder <path> \\

&#x20;                --max-iterations <N> \\

&#x20;                \[--convergence-check <hash|llm>] \\

&#x20;                \[--skip-cleanup]

```



Behavior:

\- Runs `pipeline run` for iteration 1 through N.

\- After each run, assembles `previous\_attempt` from key output artifacts.

\- If `--convergence-check hash`: compares output hash to previous iteration; stops if identical.

\- If `--convergence-check llm`: asks LLM "has this converged?"; stops if yes.

\- Artifact paths include iteration number (e.g., `artifacts/v2/`).



\#### 2.1.3 `pipeline tranche`



```

pipeline tranche --soc-file <stream\_of\_consciousness.txt> \\

&#x20;                --map <workflow\_map.txt> \\

&#x20;                --input-folder <path> \\

&#x20;                \[--max-iterations <N>] \\

&#x20;                \[--skip-cleanup]

```



Behavior:

\- Reads SOC file.

\- Calls LLM (cheap model): "Break this into ordered delivery phases. Each phase should produce a working, testable system. Output as JSON array of {phase\_name, description}."

\- Writes `artifacts/tranche\_plan.json`.

\- For each phase in plan:

&#x20; - Constructs a focused request from the phase description.

&#x20; - Calls `pipeline iterate` with that request, current input folder, and `--max-iterations`.

&#x20; - Copies generated code to the next phase's input folder.

&#x20; - Proceeds to next phase.



\### 2.2 New Primitives Catalog



The following primitives are added to the primitive registry. All follow the same contract: explicit inputs, explicit outputs, one clear job.



| Primitive | Inputs | Outputs | Description |

|-----------|--------|---------|-------------|

| `scan\_folder` | folder\_path, exclude\_patterns (optional) | file\_paths (list) | Recursively discover all files in a folder |

| `profile\_file` | file\_path | file\_hash, size, line\_count, extension | Compute basic file metadata |

| `summarize\_file` | file\_path, system\_prompt | summary\_text | LLM-generated summary of a file's purpose and structure |

| `compute\_embedding` | text\_string, model\_name | embedding\_vector (float list) | Sentence-transformer or API embedding |

| `chunk\_file` | file\_path, chunk\_size (lines or tokens) | chunks (list of {content, start\_line, end\_line}) | Split file into contiguous chunks |

| `summarize\_chunk` | chunk\_text | summary\_text | LLM-generated summary of a single chunk |

| `store\_profile\_sqlite` | profile\_data (files + chunks), db\_path | db\_updated (bool) | Upsert into SQLite profile database |

| `incremental\_scan` | folder\_path, db\_path, exclude\_patterns | changed\_files, new\_files | Compare file hashes against DB; return only changed/new |

| `retrieve\_similar` | query\_embedding, db\_path, top\_k, table\_name | ranked\_results (list of {file\_path, score, summary}) | Cosine similarity search against profile DB |

| `plan\_changes` | request\_text, relevant\_file\_contexts, system\_prompt | change\_plan (JSON with file list, edit descriptions, new files) | LLM proposes specific changes |

| `apply\_change` | change\_plan, source\_folder | updated\_files (list of {path, new\_content}) | Apply planned edits to files |

| `analyze\_wishlist` | soc\_text, system\_prompt | tranche\_plan (JSON array of phases) | Burst a wish list into ordered delivery phases |



\### 2.3 SQLite Profile Database Schema



```sql

\-- File-level metadata

CREATE TABLE files (

&#x20;   file\_path TEXT PRIMARY KEY,

&#x20;   file\_hash TEXT NOT NULL,

&#x20;   size INTEGER NOT NULL,

&#x20;   line\_count INTEGER NOT NULL,

&#x20;   extension TEXT NOT NULL,

&#x20;   summary TEXT,

&#x20;   embedding BLOB,            -- stored as bytes (e.g., numpy array)

&#x20;   last\_profiled TIMESTAMP DEFAULT CURRENT\_TIMESTAMP

);



\-- Chunk-level metadata

CREATE TABLE chunks (

&#x20;   id INTEGER PRIMARY KEY AUTOINCREMENT,

&#x20;   file\_path TEXT NOT NULL REFERENCES files(file\_path),

&#x20;   start\_line INTEGER NOT NULL,

&#x20;   end\_line INTEGER NOT NULL,

&#x20;   content TEXT NOT NULL,

&#x20;   summary TEXT,

&#x20;   embedding BLOB,

&#x20;   last\_profiled TIMESTAMP DEFAULT CURRENT\_TIMESTAMP

);



\-- Index for similarity search (implementation-dependent)

\-- Option 1: In-application cosine similarity (no index needed)

\-- Option 2: SQLite extension (e.g., sqlite-vss) for vector index

```



\### 2.4 New Workflow Map Sections (Optional)



The workflow map format gains three optional sections:



```text

MAP: codebase\_improver\_map

VERSION: 1

DESCRIPTION: "Improve existing codebase given a request"



\# --- Existing sections unchanged ---

STAGES: stage\_cleanup\_input, stage\_retrieve\_relevant, stage\_plan\_changes, stage\_apply\_changes, stage\_validate

PRIMITIVES: ...

ARTIFACT\_REGISTRY: ...

VALIDATION\_RULES: ...



\# --- New optional sections ---



PROFILE\_ROOT: input/codebase/

PROFILE\_DB: artifacts/profile.sqlite

PROFILE\_EXCLUDE: \_\_pycache\_\_, node\_modules, .git, \*.pyc



OUTER\_LOOP:

&#x20; MAX\_ITERATIONS: 3

&#x20; CONVERGENCE\_CHECK: hash

&#x20; PREVIOUS\_ATTEMPT\_SOURCES:

&#x20;   - generated/

&#x20;   - artifacts/\*.txt



TRANCHE:

&#x20; PLAN\_FILE: artifacts/tranche\_plan.json

&#x20; PHASE\_INPUT\_TEMPLATE: "input/phase\_{phase\_number}"

&#x20; PHASE\_OUTPUT\_TEMPLATE: "generated/phase\_{phase\_number}"

```



These sections are optional. If absent, the pipeline runs as originally specified (no profiling, no outer loop, no tranching). If present, the runner reads them and adjusts behavior accordingly.



\### 2.5 Updated Artifact Registry



Additions to the artifact registry:



| Artifact Name | Location | Produced By | Consumed By |

|---------------|----------|-------------|-------------|

| `cleaned\_request.txt` | `artifacts/` | Stage 1 (cleanup) | All subsequent stages |

| `cleanup\_log.txt` | `artifacts/` | Stage 1 (cleanup) | Human audit |

| `profile.sqlite` | `artifacts/` | Profile stage | Retrieval stage |

| `relevant\_files.txt` | `artifacts/` | Retrieval stage | Planning stage |

| `change\_plan.json` | `artifacts/` | Planning stage | Apply stage |

| `tranche\_plan.json` | `artifacts/` | Tranche planner | Tranche runner |

| `validation\_report.txt` | `artifacts/` | Validation stage | Outer loop convergence check |



\### 2.6 Integration with Existing Stages



The codebase improvement workflow map uses these new primitives within the existing stage structure:



```

Stage 1: cleanup\_input

&#x20; Primitive: call\_llm (cheap model)

&#x20; Input: raw\_request.txt (or single-tranche request)

&#x20; Output: cleaned\_request.txt, cleanup\_log.txt

&#x20; Condition: skipped if --skip-cleanup flag set



Stage 2: retrieve\_relevant

&#x20; Primitives:

&#x20;   - incremental\_scan (profile any new/changed files)

&#x20;   - compute\_embedding (embed the cleaned request)

&#x20;   - retrieve\_similar (query profile DB)

&#x20; Input: cleaned\_request.txt, input/codebase/

&#x20; Output: relevant\_files.txt (top-K files with summaries)



Stage 3: plan\_changes

&#x20; Primitive: plan\_changes

&#x20; Input: cleaned\_request.txt, relevant\_files.txt (plus full content of top files)

&#x20; Output: change\_plan.json



Stage 4: apply\_changes

&#x20; Primitive: apply\_change

&#x20; Input: change\_plan.json, input/codebase/

&#x20; Output: updated files in generated/



Stage 5: validate

&#x20; Primitive: call\_llm (critic) + optional test runner

&#x20; Input: change\_plan.json, generated/ files

&#x20; Output: validation\_report.txt

```



\### 2.7 Example Usage Flows



\*\*Flow A: Quick micro-optimization on a single file\*\*



```bash

pipeline run --map codebase\_fix\_map.txt \\

&#x20;            --request "Optimize the database query in backend/db.py" \\

&#x20;            --input-folder ./my\_project/

```



\*\*Flow B: Iterative feature addition with convergence\*\*



```bash

pipeline iterate --map feature\_add\_map.txt \\

&#x20;                --request "Add user authentication with JWT" \\

&#x20;                --input-folder ./my\_project/ \\

&#x20;                --max-iterations 5 \\

&#x20;                --convergence-check llm

```



\*\*Flow C: Full tranche development from wish list\*\*



```bash

pipeline tranche --soc-file roadmap\_ideas.txt \\

&#x20;                --map full\_app\_map.txt \\

&#x20;                --input-folder ./my\_project/ \\

&#x20;                --max-iterations 3

```



\*\*Flow D: Standalone profiling + retrieval (no generation)\*\*



```bash

pipeline run --map profile\_only\_map.txt \\

&#x20;            --request "What does this codebase do?" \\

&#x20;            --input-folder ./my\_project/

```



This last flow uses only Stages 1–2 (cleanup + retrieval) and outputs a summary of the codebase without generating any new code.



\---



\### 2.8 Backward Compatibility



\- All existing workflow maps continue to work unchanged.

\- The new primitives are additive — they don't modify existing primitives.

\- The new CLI wrappers are optional — `pipeline run` remains the core.

\- The profile database is optional — if no `PROFILE\_ROOT` is set, the retrieval stage can fall back to full-file scanning or skip retrieval entirely.



\---



\*End of Addendum. Version 1.0 — June 17, 2026.\*

