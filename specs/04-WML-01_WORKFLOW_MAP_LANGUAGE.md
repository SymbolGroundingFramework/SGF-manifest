# Workflow Map Language (WML) Specification v1.0 Final Candidate

File: 04-WML-01_WML_SPEC.md
Layer: WML (workflow application grammar)
Status: Final Candidate


## 0. Executive summary

WML declares AI software workflows as machine-executable maps.
A workflow map composes a small, versioned catalog of
single-purpose CLI primitives (`call_llm`, `validate_contract`,
`read_file`, …) connected by frozen contracts. The runner
executes the map deterministically: given identical maps and
inputs, it produces identical traces (modulo bounded,
validator-gated LLM nondeterminism, which is treated as an
external function with a specified interface).

The model is one primitive among fifteen, not the substrate.
The map IS the application; source code is a derived, ephemeral
artifact.

A conforming implementation passes the conformance suite in
§21 and obeys the invariants in §6, the grammar in §12, and the
failure semantics in §14.


## 1. Scope and intent

WML is an engineering-grade grammar for declaring AI software
workflows as maps. A workflow map is the sole authoritative
declaration of execution control; the model is one primitive
among a small, frozen catalog, not the substrate of execution.

WML defines:

- a closed, versioned catalog of command-line primitives with
  frozen contracts;
- a deterministic composition grammar over those primitives;
- an artifact model in which intermediate outputs are immutable,
  addressable, and durable;
- a contract model with wrapper rules, validators, and fail-loud
  semantics;
- a runner contract: what a conforming WML runner MUST guarantee.

WML does **not**:

- redefine SGF Core or its roles;
- define a wire protocol. WML maps are data artifacts; their
  transport is profile-specific. HFF MAY carry WML maps across
  trust boundaries;
- govern runtime execution behavior. That is Omega's role. WML is
  the artifact Omega can inspect;
- replace autonomous agent orchestration. WML is a constrained
  build system, not a general-purpose autonomous agent;
- prescribe model architecture, model identity, or inference
  strategy;
- redefine how the model's internal reasoning occurs. It constrains
  the interface between the model and the rest of the system.

WML specifically does NOT claim:

- that it is a complete formal language with mathematical semantics.
  It is an engineering-grade grammar with a reference interpreter.
  The mathematical formalization is a Phase 1.5 milestone (§2.1);

- that the map generator is a compiler-compiler. The map generator
  is a **compiler** in WML. A compiler-compiler takes a grammar and
  produces a compiler; the map generator takes intent and produces
  programs (maps);

- that WML provides 99.999 % primitive coverage. No system in
  history has reached that level. The honest claim is a
  domain-bounded ceiling of 97–99 % for tractable software classes,
  with the irreducible 1–3 % being genuinely novel work;

- that WML is the only correct architecture for AI software
  generation. It is one architectural bet that makes a specific
  set of trade-offs (auditability, restartability, and
  inspectability over short-horizon speed on trivial tasks);

- that generated software is correct by virtue of the map parsing.
  Parsing guarantees structural correctness of the *generation
  process*. Semantic correctness of the generated content is a
  property of the primitives and their implementations, not of
  the map alone.

A conforming WML runner that parses a well-formed map and sees
all primitives wired correctly produces generation behavior that
follows from the grammar — not from the mood of the model.


## 2. Core claims (theses)

Six propositions form the architectural load-bearing structure.
They are stated without argumentation here; the arguments,
evidence, counterarguments, and rebuttals live in the narrative
documents.

**T1 · Composition Thesis.** AI software engineering is a problem
of composition over stable parts, not of character-level code
generation. When a small catalog of primitives with frozen
contracts covers the majority of what a system needs, the model's
highest-value contribution shifts from writing source code to
writing declarative maps that wire primitives together.

**T2 · Map Thesis.** The map IS the application. Source code is a
derived, ephemeral artifact. Modifications happen to the map;
code is regenerated from the map.

> **The inversion.** In today's AI coding tools, the artifact you
> edit is source code and the map is implicit in the conversation.
> In WML, the artifact you edit is the map, and source code is
> ephemeral. This is the same inversion that happened when
> structured programming replaced spaghetti code: the control flow
> moved from the programmer's head into the program's syntax.

**T3 · Orthodoxy Thesis.** The current agent-loop orthodoxy
conflates the model with the infrastructure, producing three
unrecoverable, architectural failure modes: nondeterministic
memory, non-restartable execution, non-auditable reasoning. These
are not capacity-linked and therefore not fixed by smarter
models.

**T4 · Formal-Systems Thesis.** WML has the structural shape of a
formal language: primitives as terminals, maps as programs, the
runner as the reference interpreter, contracts functioning
analogously to types, wrappers as control structures, templates
as macros. It has a frozen machine-parseable grammar; its
programs (workflow maps) are sentences in a formally specified
language; it has a reference interpreter that defines its
operational semantics; and its execution is deterministic on
identical inputs. Full PL-theory formalization (denotational
semantics, small-step operational semantics, type soundness
proofs) is Phase 1.5 — the natural next milestone, not a
precondition for WML's status as a formal language. WML meets the
same historical bar as FORTRAN, C, and JavaScript: recognized as
a formal language on the basis of a frozen grammar and reference
interpreter before their mathematical semantics were written.

**T5 · Primitive-Evolution Thesis.** WML is designed to grow its
own primitive catalog. Custom-generated code is inspected for
reuse; patterns that recur across runs are promoted to primitives
under the same frozen-contract discipline. Coverage shifts toward
a domain-bounded ceiling (97–99 % for tractable software classes;
the asymptote is strictly below 100 %).

**T6 · Self-Interpretation Thesis.** The map generator is itself
a workflow map; the runner executes both generator-maps and
generated-maps using the same grammar. The bootstrapping sequence
closes the improvement loop.

### 2.1 Open frontiers (Phase 1.5 formalization)

WML's current formalization delivers operational semantics
through the reference runner and the conformance suite. The
following are explicitly not yet present and are stated as
future milestones:

- **Formal grammar extraction** — derivation of a
  machine-readable ABNF / EBNF grammar (`workflow_map.abnf`)
  from the current hand-written schema in
  `workflow_map_schema.txt`;
- **Declarative typing judgments** — conversion of the runtime
  validator code into declarative typing rules of the form
  `Γ ⊢ artifact : class`;
- **Small-step operational semantics** — a formal reduction
  semantics `⟨map, state⟩ → ⟨map', state'⟩` replacing the
  implementation-defined behavior of the runner;
- **Static contract checker** — a type checker that runs before
  execution and rejects ill-composed maps without invoking any
  primitive;
- **Type soundness proofs** — progress and preservation
  theorems for the contract system;
- **Denotational semantics** — a mathematical meaning function
  `〚map〛 : T_in → T_out` for well-formed maps.

The conformance test suite in §21 already exercises operational
behaviour exhaustively; Phase 1.5 is the task of expressing that
behaviour in PL-theoretic form. The architecture is designed to
admit this formalization without breaking its operational
behaviour.

### 2.2 Falsifiable predictions

A claim that cannot fail is not a claim. Two public, attributable
predictions commit the architecture to empirical verification:

- **P1 (field adoption)** — within 24 months of this
  specification's publication, at least one major AI-coding
  vendor will publicly release a "workflow map" or "composition
  layer" structurally isomorphic to this architecture. Its
  existence alone confirms that thesis T2 has entered the field's
  design vocabulary.

- **P2 (primitive evolution)** — within 24 months of deploying
  this architecture on 10 or more real projects, the primitive
  catalog will have grown by at least 50 % over its initial
  size, with every new primitive traceable to a specific observed
  reuse pattern from prior generated code.

If either prediction fails, the corresponding thesis (T2 or T5)
is refuted on its own terms.

### 2.3 Thesis dependency structure

The six theses form a strict, directed, acyclic dependency graph.
Every thesis connects to the bedrock by exactly one path; no
cycles exist.

    T3 (orthodoxy fails structurally)
     │
     ├── model conflated with infrastructure
     ├── three failure modes: nondeterministic memory,
     │   non-restartable execution, non-auditable reasoning
     └── failure modes are architectural, not capacity-linked
         │
         ▼
    T1 (composition bet)
         │
         ▼
    T2 (map is the application)
         │
         ▼
    T4 (engineering-grade grammar: WML)
         │
         ▼
    T5 (primitive evolution)
         │
         ▼
    T6 (self-interpretation)

Removing any node breaks all subsequent nodes.

### 2.4 Scope discipline (tractable vs. novel domains)

WML's claims are bounded to **tractable software classes**:

- CRUD applications;
- chat applications;
- data pipelines;
- form-driven applications;
- static sites;
- internal tools.

For these classes, the architecture delivers the four structural
properties (modifiability, auditability, restartability,
inspectability) as defaults, and the primitive catalog covers
the load-bearing 95–97 % of generation operations at the start.

Novel domains — GPU kernels, real-time control systems,
cryptographic protocols, novel rendering engines, and the long
tail of never-done-before work — fall outside the current bound.
Genuinely novel operations remain the irreducible 1–3 % by
design. WML explicitly does not currently claim universal
software engineering; it makes bounded claims in specified
domains and names the boundary.

The primitive catalog's ceiling is a domain-bounded 97–99 % for
tractable classes, not a universal 100 %. Unix has been growing
for fifty years, and teams still write custom shell scripts.
WML's asymptote mirrors Unix's — a principled ceiling below 100 %,
reached by construction.

### 2.5 Primitive evolution phases (T5 mechanism)

The architecture specifies three explicit phases for how the
primitive catalog grows. Each phase is independent; the
architecture functions at every phase, not only at completion.

**Phase 1 — manual inspection (works today).** The practitioner
runs the pipeline on multiple projects. The observability layer
preserves every artifact and diagnostic. After runs, the
practitioner reads diagnostics and identifies recurring patterns
in the 5 % custom code. A pattern that appears across three
projects (e.g., input sanitization in HTTP handlers) is
extracted as a new primitive with its own frozen contract and
added to the catalog. Phase 1 is operational.

**Phase 2 — semi-automated pattern detection (achievable).**
A meta-cognitive primitive runs on every diagnostic tree after
every run, flags candidate primitives to a human reviewer, and
the human approves or rejects. Approved candidates go through
the frozen-contract discipline and join the catalog.

**Phase 3 — fully automated (research thread).** The
meta-cognitive primitive proceeds through the validator gauntlet
without human approval. A conforming Phase 3 implementation MUST
enforce all of:

- (a) multiple successful applications of the observed pattern
  across different runs as evidence;
- (b) full validator-gauntlet pass under the frozen-contract
  discipline;
- (c) governance approval (Omega verdict or human review) before
  promotion;
- (d) ability to demote the primitive with rollback if
  post-promotion metrics show underperformance.

Phase 3 without these guardrails is a non-conformant extension.
Every new primitive MUST satisfy the same frozen-contract
discipline as existing primitives. The growth mechanism is the
same mechanism that built the catalog in the first place.


## 3. Bedrock axioms

The following maxims are load-bearing. Removing any one
undermines the thesis. Every normative rule in the remainder of
this specification can be traced to one or more of these maxims.

1. **Control logic that lives in prompts is not control logic —
   it is hope.**                                                       (§9)
2. **What recurs belongs in the toolchain, not in the prompt.**
                                                                       (§6)
3. **A primitive that cannot be versioned, timed out, and audited
   is not a tool — it is a liability.**                                (§6)
4. **The authoritative payload is the one the parser can verify;
   everything else is commentary.**                                    (§10)
5. **If the control flow is not in the map, it does not exist.**
                                                                       (§12)
6. **Architecture is structure, not implementation; the artifact
   that determines structure IS the architecture.**                    (§12)
7. **In any system, the component with the highest failure rate
   should have the smallest responsibility.**                          (§6)
8. **Formalization without implementation is fantasy;
   implementation without formalization is craft.**                    (§2.1)
9. **Engineering requires a toolchain.**                               (§6)
10. **The map is the application.**                                    (§12)

Section references in parentheses point to the normative rule
each axiom grounds.

### 3.1 Reconciliation: why treat a non-deterministic model as a
primitive

An AI engineer will read axiom 2 and ask: *"Why treat an
intrinsically non-deterministic model as a tool?"*

The model is non-deterministic. The contract surrounding it is
not. Every invocation of `call_llm` MUST return an artifact whose
shape the validator can check (for example, `<answer>` wrapper
presence, JSON schema conformance, required-key presence). The
failure mode therefore becomes a type error (wrong shape) rather
than a reasoning error (plausible but wrong content).

The system tolerates internal nondeterminism because it does not
depend on the model's internal reasoning; it depends only on the
validator-checked envelope of the output. The validator sees
either "envelope present and correct" (stage proceeds) or
"envelope missing or malformed" (stage fails with preserved
diagnostics). The model's internal state is irrelevant to the
system's invariants.

This is principled, not a workaround. It is the same trade-off
that every build system makes with external subprocesses: the
build system does not trust `gcc`'s internals; it trusts the exit
code and the output artifact. WML does the same thing with
`call_llm`.


## 4. Normative terms

The terms `MUST`, `MUST NOT`, `SHOULD`, `SHOULD NOT`, and `MAY`
follow IETF RFC 2119 conventions.

- `MUST`: required for conformance.
- `MUST NOT`: prohibited for conformance.
- `SHOULD`: strongly recommended unless a documented exception
  exists.
- `SHOULD NOT`: discouraged unless a documented exception
  exists.
- `MAY`: optional.


## 5. Invariants

Every conforming WML implementation MUST preserve the following:

```text
primitive_stability
artifact_immutability
contract_enforcement
map_authority
validator_gating
fail_loud
idempotency
auditability
restartability
workspace_isolation
security_hardening
```

These invariants are the operational load-bearing properties. Any
implementation whose behavior violates one is not conforming to WML.


## 6. Layer model

WML defines four layers. The layer structure prevents
infrastructure regeneration and keeps the primitive catalog
stable.

| Layer | Name         | Responsibility                                             |
|---|---|---|
| 0 | Substrate    | File, path, process, encoding, hash, metadata operations     |
| 1 | Application  | Prompt assembly, LLM invocation, extraction, validation,
                     storage, export, retrieval                                   |
| 2 | Composition  | Workflow maps, implementation plans, validation plans,
                     state-transition definitions                                 |
| 3 | Custom       | Project-specific logic                                       |

Layer 3 MUST remain intentionally small. Repeated behavior
discovered in Layer 3 SHOULD be extracted downward into lower
layers when it becomes reusable.

The runner is generic and MUST NOT embed project-specific logic.


## 7. Primitive specification

### 7.1 Requirements

Every primitive MUST:

- do one clear job;
- expose a stable CLI;
- accept explicit inputs;
- produce explicit outputs;
- fail loudly on malformed required inputs (return nonzero exit
  code);
- enforce strict execution timeouts to prevent hanging processes;
- avoid hidden retries, hidden fallbacks, and hidden repair;
- preserve deterministic behavior for identical effective inputs
  and configuration;
- have a stable published name once included in the primitive
  catalog;
- report its version via `--version` flag;
- accept `--help` flag and print a usage summary to stdout;
- use a `snake_case` name (e.g., `call_llm`, not `call-llm` or
  `callLlm`).

Cosmetic renaming of published primitives is prohibited.

### 7.2 Interface conventions

Primitives SHOULD use these flags where applicable:

| Flag                    | Purpose                      |
|---|---|
| `--in-file <path>`       | Primary input                |
| `--out-file <path>`      | Primary output               |
| `--out-dir <path>`       | Directory output             |
| `--config-file <path>`   | Explicit configuration       |
| `--timeout <seconds>`    | Override default timeout     |
| `--telemetry-file <path>`| Structured telemetry output  |

A primitive MUST validate required arguments before any side
effects occur.

A primitive MAY emit primary output to stdout only if that
behavior is explicitly documented in its catalog entry and the
consuming stage contract declares stdout as authoritative output.
When stdout is used, the runner captures the output and writes it
to the declared output artifact file (see §12.6).

#### 7.2.1 Telemetry file contract

When `--telemetry-file <path>` is provided, the primitive MUST
write a JSON object to that path on completion (success or
failure):

```json
{
  "primitive": "<name>",
  "version": "<semver>",
  "start_timestamp": "<iso8601>",
  "end_timestamp": "<iso8601>",
  "duration_seconds": <float>,
  "exit_code": <int>,
  "timeout_occurred": <bool>,
  "input_hashes": {"<flag>": "<sha256>"},
  "output_hashes": {"<flag>": "<sha256>"},
  "error_message": "<string|null>"
}
```

### 7.3 Primitive catalog

The primitive catalog is a first-class artifact stored as
`primitive_catalog.txt`.

#### 7.3.1 Catalog entry format (frozen)

The file `primitive_catalog.txt` MUST use the following
line-oriented format. Each primitive occupies a contiguous block
terminated by a blank line.

```
PRIMITIVE <primitive_name>
  PURPOSE: <one-sentence description>
  REQUIRED_ARGS: <flag1>; <flag2>; ...
  OPTIONAL_ARGS: <flag3>; <flag4>; ...
  INPUT_CONTRACT: <artifact_class_name>
  OUTPUT_CONTRACT: <artifact_class_name>
  SIDE_EFFECTS: <description_or_none>
  EXIT_CODES: <code>=<meaning>; <code>=<meaning>; ...
  DEFAULT_TIMEOUT: <seconds>
  VALIDATOR_EXPECTATIONS: <validator_id_1>; <validator_id_2>; ...
  VERSION: <semver>
```

`INPUT_CONTRACT` and `OUTPUT_CONTRACT` MUST reference an artifact
class name from §8.3, not a file path or artifact ID.

#### 7.3.2 Primitive versioning

Each catalog entry MUST include a `VERSION` field (semver).

The runner MUST verify that the primitive version invoked matches
the catalog version. If a primitive reports a different version
(via `--version`), the runner MUST fail the stage with exit code
`VERSION_MISMATCH`.

#### 7.3.3 Frozen catalog size

The Phase 1 executable catalog MUST be frozen at **≤ 20
primitives** before generated workflow maps are accepted for
execution.

### 7.4 Primitive classes

Phase 1 MUST prefer the smallest primitive set across these
classes:

| Class                  | Example primitives                                      | Default timeout |
|---|---|---|
| File & Text            | `read_file`, `write_file`, `chunk_text`, `detect_encoding` | 10s |
| Prompt Assembly        | `build_prompt`                                          | 5s  |
| LLM Invocation         | `call_llm`                                              | 180s |
| Answer Extraction      | `extract_answer`                                        | 10s |
| Contract Validation    | `validate_contract`                                     | 10s |
| SQLite                 | `init_sqlite`, `query_sqlite`, `upsert_sqlite`, `sync_sqlite` | 30s |
| Export & Materialize   | `export_assets`, `render_ui`, `compile_app`             | 60s |

### 7.5 Primitive discovery

The runner resolves each `PRIMITIVE` name to an executable path
in this order:

1. If environment variable `PRIMITIVE_HOME` is set, look for
   `<PRIMITIVE_HOME>/<primitive_name>`.
2. Otherwise, perform a system `$PATH` lookup via
   `shutil.which()` or equivalent.

Primitive executable names MUST exactly match the catalog
`PRIMITIVE` name (snake_case). If no executable is found, the
runner MUST halt with exit code `PRIMITIVE_NOT_FOUND`. Phase 1
does not support registries, containers, or remote invocation.


## 8. Artifact model

### 8.1 General rules

Artifacts are the authoritative working memory of the system.

Every artifact MUST be:

- named;
- persisted to disk;
- addressable by path;
- associated with a stage, a global role, or both;
- suitable for human inspection and machine consumption.

The runner MUST enforce schemas against instance artifacts
wherever a schema exists.

A workflow map is an instance artifact. A workflow-map schema is
a schema artifact.

### 8.2 Immutability law

Text and file artifacts MUST be strictly immutable once produced
and validated.

A stage MUST NOT overwrite or modify an existing artifact. If an
artifact requires modification, the stage MUST produce a new
artifact with a distinct ID (e.g., `code_v1` → `code_v2`).

The only exception is formal state (SQLite databases), which are
explicitly mutated via defined database primitives.

This immutability rule ensures:

- every artifact version is preserved for audit;
- downstream consumers are never surprised by silent overwrites;
- idempotency checks are straightforward (same inputs → same
  outputs → same artifacts);
- rollback is possible by reverting to a previous artifact
  version.

### 8.3 Artifact classes

The system SHALL recognize at least these artifact classes:

| Class         | Role                                                        |
|---|---|
| `Schema`      | Defines the shape of a document family; reused across runs  |
| `Input`       | External or prior-run artifact consumed by a stage          |
| `Intermediate`| Produced and consumed within a single run                   |
| `Output`      | Final deliverable of a successful run                       |
| `Diagnostic`  | Evidence of behavior (validation reports, raw replies, parse
                   errors, invocation records, telemetry)                      |
| `Deliverable` | Materialized application or bundle produced for export      |
| `State`       | Mutable formal state (SQLite databases)                     |
| `External`    | Provided outside the run, not produced by any stage         |

### 8.4 Standard artifact names

A conforming Phase 1 implementation SHOULD support at least:

| Name                        | Class         | Role                                        |
|---|---|---|
| `current_inventory.txt`     | `Schema`      | List of known primitives, schemas, contracts |
| `primitive_catalog.txt`     | `Schema`      | Full primitive definitions with contracts    |
| `contracts_guide.txt`       | `Schema`      | Hard rules for parsing, wrappers, failure    |
| `workflow_map_schema.txt`   | `Schema`      | Grammar for workflow map documents           |
| `workflow_map.txt`          | `Intermediate`| Current run's workflow composition           |
| `gold_workflow_map.txt`     | `Intermediate`| Hand-written gold-standard map               |
| `implementation_plan.txt`   | `Intermediate`| Build order, file layout, stage assignments  |
| `validation_plan.txt`       | `Schema`      | Declared validators per stage                |
| `state_model.txt`           | `Schema`      | Database schema and state definitions        |

### 8.5 Canonical artifact formats

The following canonical artifacts MUST follow the frozen formats
described below. Domain-specific artifacts such as
`reference_app_spec.txt`, `api_contracts.txt`, and
`ui_decomposition.txt` are specified separately in
`implementation_plan.md`.

#### 8.5.1 `validation_plan.txt` format

```
VALIDATION_PLAN:
  workflow_id: <workflow_id>
  version: <semver>

VALIDATORS:
  <validator_id> | <validation_type> | <target_artifact_id> | <failure_condition> | <severity>
  ...
```

#### 8.5.2 `state_model.txt` format

```
STATE_MODEL:
  version: <semver>

TABLES:
  <table_name>: <column_name> <type> [PRIMARY KEY] [NOT NULL] [DEFAULT <value>]; ...
  ...

INDEXES:
  <index_name> ON <table_name> (<column_name>, ...); ...
```

`type` MUST be one of `TEXT`, `INTEGER`, `REAL`, `BLOB`.

#### 8.5.3 `current_inventory.txt` format

```
CURRENT_INVENTORY:
  version: <semver>

SCHEMA_FILES:
  <filename>; ...

PRIMITIVE_CATALOG:
  <filename>

CONTRACTS_GUIDE:
  <filename>

OTHER_ARTIFACTS:
  <filename>: <purpose>; ...
```

#### 8.5.4 `workflow_map_schema.txt` format

```
WORKFLOW_MAP_SCHEMA:
  version: <semver>
  grammar_version: "phase1_2026"

REQUIRED_SECTIONS (in order):
  WORKFLOW_METADATA
  GLOBAL_DEFAULTS
  ARTIFACT_REGISTRY
  STAGES
  EXECUTION_RULES
  VALIDATION_RULES
  FAILURE_RULES

OPTIONAL_SECTIONS:
  TOLERANCE_RULES
  RUNTIME_NOTES
  DEPLOYMENT_TARGETS

SYNTAX:
  section_markers: UPPER_SNAKE_CASE on own line
  key_value_split: first colon
  lists: semicolon-separated, no trailing semicolon
  multi_line_values: NOT ALLOWED
  comments: lines starting with #
  pipe_delimiter: ALL registry entries MUST use pipe-delimited
                  format with single spaces around pipes
```

### 8.6 Implementation plan

`implementation_plan.txt` is a first-class artifact.

#### 8.6.1 Implementation plan format

```
FILE_LAYOUT:
  <relative_path>: <purpose>; <producing_stage>; <artifact_class>
  ...

STAGE_DECOMPOSITION:
  <stage_id>: <primitive>; <input_artifacts>; <output_artifacts>; <description>
  ...

ARTIFACT_PRODUCTION_ORDER:
  <artifact_id_1>; <artifact_id_2>; ...

DEPENDENCY_ORDERING:
  <stage_id_1> -> <stage_id_2>; ...

BUILD_SEQUENCE_ASSUMPTIONS:
  - <assumption_1>
  ...

OPEN_QUESTIONS:
  - <question_1>
  ...
```

A system with architectural artifacts but no implementation plan
is under-specified for nontrivial execution.

### 8.7 Artifact metadata

Every persistent artifact record SHOULD capture at least:

| Field                      | Description                                              |
|---|---|
| `artifact_id`              | Unique identifier                                        |
| `artifact_class`           | From §8.3 classification                                 |
| `relative_path`            | Path within run workspace                                |
| `producing_stage`          | Stage ID that created this artifact                      |
| `creation_timestamp`       | When artifact was written                                |
| `last_validation_status`   | `pass`, `fail`, or `untested`                           |
| `content_hash`             | SHA-256 hex-encoded lowercase hash of artifact content   |
| `version`                  | Monotonically increasing (`v1`, `v2`, …)                 |

#### 8.7.1 Content hash algorithm

All content hashes MUST use SHA-256, hex-encoded, lowercase.


## 9. Directory layout and workspace isolation

### 9.1 Run workspace

Every execution MUST occur within a unique `runs/<run_id>/`
workspace.

#### 9.1.1 Run ID generation

```
run_<utc_timestamp_iso8601_no_punct>_<short_hash>
```

Example: `run_20260617T235023Z_a1b2c3d4`

`short_hash` = first 8 characters of SHA-256(concatenated input
artifact paths).

### 9.2 Required subdirectories

| Directory                        | Contents                                                     |
|---|---|
| `runs/<run_id>/artifacts/`       | Persistent named instance and schema artifacts               |
| `runs/<run_id>/temp/`            | Intermediate stage-local files                               |
| `runs/<run_id>/generated/`       | Materialized deliverables and final code outputs             |
| `runs/<run_id>/runtime/`         | Mutable run-support assets (SQLite databases, config)        |
| `runs/<run_id>/diagnostics/`     | Validation reports, raw LLM outputs, parse diagnostics       |

### 9.3 Directory separation rules

- `artifacts/` — immutable, validated artifacts.
- `temp/` — stage-local intermediates, deleted after each
  successful stage; preserved on failure.
- `generated/` — final deliverables.
- `runtime/` — mutable state (SQLite databases).
- `diagnostics/` — evidence from failures and validation.

### 9.4 Diagnostics file requirements

Each run MUST preserve at minimum:

- `runs/<run_id>/diagnostics/run_metadata.txt`;
- `runs/<run_id>/diagnostics/validation_<stage_id>.txt` per
  validated stage.

### 9.5 `run_metadata.txt` format

```
RUN_ID: <run_id>
TIMESTAMP: <iso8601>
INPUT_HASH: <sha256>
WORKFLOW_MAP_HASH: <sha256>
PRIMITIVE_CATALOG_HASH: <sha256>
CONTRACTS_GUIDE_HASH: <sha256>
STATUS: success | failed | partial
REUSED_FROM_RUN: <previous_run_id | none>
```


## 10. Contract model

### 10.1 General contract law

Every stage MUST declare:

- input artifacts;
- output artifacts;
- validation requirements;
- failure behavior.

File boundaries are authoritative. Hidden in-memory contracts
between stages are prohibited.

Machine-consumable outputs MUST be deterministic and parseable.

### 10.2 Rationale: why the `<answer>` wrapper and not JSON

LLMs are stochastic functions. The cheapest reliable envelope for
a model's authoritative payload is a well-known token pair the
parser can scan for, rather than demanding the model emit
well-structured JSON on every call.

- `<answer>` lets the model include human-readable commentary
  outside the authoritative block (useful for debugging);
- JSON would force the model into rigid structural emission,
  which fails on a significant fraction of calls;
- structured-outputs APIs constrain capability and vendor-lock
  the pipeline to a specific provider;
- enforcing wrapper discipline produces a single, localizable
  failure mode ("missing wrapper") which the validator catches
  immediately — turning a reasoning error into a type error.

This is the principled choice, not the pragmatic one. It is why
the model's nondeterminism becomes the runner's determinism.

### 10.3 Authoritative output wrapper

Where LLM-generated machine-readable output is consumed
downstream, the authoritative machine payload MUST appear inside:

- Opening tag: `<answer>`
- Closing tag: `</answer>`

Content outside the authoritative wrapper MUST be treated as
non-authoritative for machine parsing.

### 10.4 Structural text rules

- Section markers MUST appear on their own lines.
- Key-value parsing MUST split on the first colon only.
- Required keys MUST be declared and validated.
- Duplicate keys MUST fail unless the contract explicitly permits
  repetition.
- UTF-8 SHOULD be the default encoding.
- Line endings SHOULD be normalized to LF where practical.

### 10.5 Parser behavior

Parsers MUST validate, extract, and stop.

Parsers MUST NOT:

- guess intended structure;
- silently reinterpret malformed structure;
- repair malformed output through a second model call;
- continue after required contract failure.

### 10.6 Prompt assembly contracts

Prompts are Layer 2 artifacts and MUST be assembled hierarchically
via the `build_prompt` primitive from five sections:

| Section       | Purpose                                 |
|---|---|
| Big Picture   | High-level goal                       |
| Context       | Current state, inputs, constraints    |
| Standards     | Craft knowledge from `contracts_guide` |
| Task          | Specific instruction                  |
| Output Format | Exact wrapper, section markers, keys  |

The prompt template MUST be stored as a file and referenced by
path. The `build_prompt` primitive accepts
`--template-file <path>`. This five-section structure is a
convention; `--template-file` allows domain-specific overrides.

### 10.7 Stage success conditions

A stage MUST NOT be marked successful unless all:

1. required outputs exist;
2. required outputs match their declared contract shape;
3. all `severity=required` validators pass;
4. required subprocesses exit successfully (code 0) unless a
   tolerance rule allows otherwise;
5. no timeout violation occurred.

### 10.8 Stop-worthy contract failures

The following MUST fail the stage unless an explicit tolerance
rule applies:

- missing required sections;
- missing answer blocks;
- empty critical artifacts;
- missing required files;
- duplicate keys where disallowed;
- schema conformance failure;
- database write failure;
- export failure;
- nonzero subprocess exit;
- required-validator failure;
- timeout violation;
- version mismatch;
- encoding violation.

### 10.9 Contracts guide format (frozen)

```
PARSING_RULES
  ENCODING: utf-8
  LINE_ENDING: lf
  SECTION_MARKER_PATTERN: ^[A-Z_]+$
  KEY_VALUE_SPLIT: first_colon
  DUPLICATE_KEY_POLICY: fail_unless_list

ANSWER_WRAPPER
  OPEN_TAG: <answer>
  CLOSE_TAG: </answer>
  AUTHORITATIVE: true

PROMPT_ASSEMBLY_SECTIONS
  BIG_PICTURE: required
  CONTEXT: required
  STANDARDS: required
  TASK: required
  OUTPUT_FORMAT: required

STAGE_SUCCESS_CONDITIONS
  1. required_outputs_exist
  2. output_contract_conformance
  3. required_validators_pass
  4. subprocess_exit_success
  5. no_timeout_violation

FAILURE_CONDITIONS_STOP_WORTHY
  - missing_required_section
  - missing_answer_block
  - empty_critical_artifact
  - ...
```

`contracts_guide.txt` is global law and MUST be considered
authoritative over `GLOBAL_DEFAULTS` for all parsing rules.


## 11. Validation model

### 11.1 General rules

Validators MUST be declared, not implied.

Required validators (`severity=required`) MUST run before
progression and gate the stage. Optional validators
(`severity=optional`) MAY fail without halting progression;
their diagnostics are preserved.

A validator MAY check: file presence, nonempty output, required
sections, required answer blocks, required keys, allowed values,
schema conformance, referential artifact consistency, database
write success, export success, content hash agreement,
immutability.

### 11.2 Validator registry format (frozen)

```
VALIDATOR <validator_id> | <validation_type> | <target_artifact_id> | <failure_condition> | <severity>
```

`validation_type` ∈

```
file_presence | answer_block | required_keys | schema_conformance |
db_write_success | export_success | referential_consistency |
content_hash | allowed_values
```

`severity` ∈ `required | optional`.

### 11.3 Validator invocation contract

Validators are runner-internal dispatch functions, not external
executables. The runner dispatches each declared `VALIDATION_RULE`
by:

1. resolving `target_artifact_id` to its absolute path via
   `ARTIFACT_REGISTRY`;
2. invoking the built-in validator function for the declared
   `validation_type`;
3. passing the resolved path, `failure_condition` predicate, and
   `contracts_guide.txt` path;
4. returning a validator result
   `{passed: bool, message: str, failed_rules: list}`.

Required validators that fail → stage fails.
Optional validators that fail → diagnostic emitted, stage
continues.

Custom validator types MAY be added but MUST be declared in
`contracts_guide.txt`.


## 12. Workflow-map specification

### 12.1 Role

The workflow map is the sole authoritative declaration of
workflow control.

Stage order, dependencies, inputs, outputs, validators, retries,
tolerance rules, and failure policy MUST be declared in the
workflow map and MUST NOT be hidden across prompts, scripts,
wrappers, or operator habits.

### 12.2 Frozen grammar subset (Phase 1)

The following syntax rules are frozen for Phase 1. Generators and
runners MUST reject any deviation.

- Section markers: `UPPER_SNAKE_CASE` on own line.
- Key-value pairs: `KEY: value` (split on first colon only).
- Lists: semicolon-separated, no trailing semicolon.
- Multi-line values: NOT ALLOWED in Phase 1.
- Comments: lines starting with `#` are ignored.
- Blank lines: ignored.
- Keywords are case-sensitive.
- Registry entries use pipe-delimited format with single spaces
  around pipes.

Required top-level sections (exact order):

```
WORKFLOW_METADATA
GLOBAL_DEFAULTS
ARTIFACT_REGISTRY
STAGES
EXECUTION_RULES
VALIDATION_RULES
FAILURE_RULES
```

Optional sections after required:

```
TOLERANCE_RULES
RUNTIME_NOTES
DEPLOYMENT_TARGETS
```

### 12.3 Workflow metadata requirements

`WORKFLOW_METADATA` MUST define at least: workflow ID, workflow
name, workflow version, reference application identifier, authoring
source, creation timestamp.

### 12.4 Global defaults

`GLOBAL_DEFAULTS` MUST NOT override explicit stage declarations or
`contracts_guide.txt`.

### 12.5 Artifact registry entry format (frozen)

```
ARTIFACT <artifact_id> | <name> | <kind> | <path> | <produced_by> | <consumed_by> | <validation_binding> | <persistence>
```

`kind` ∈ `input | intermediate | output | diagnostic | schema`.
`persistence` ∈ `temporary | persistent | deliverable`.

### 12.6 Stage declaration format (frozen)

```
STAGE <stage_id>
  NAME: <human_readable_name>
  PRIMITIVE: <primitive_name>
  INPUTS: <artifact_id_1>; <artifact_id_2>; ...
  OUTPUTS: <artifact_id_3>; <artifact_id_4>; ...
  DEPENDS_ON: <stage_id_1>; <stage_id_2>; ... | none
  VALIDATORS: <validator_id_1>; <validator_id_2>; ... | none
  FAILURE_POLICY: halt | continue_under_tolerance <tolerance_rule_id>
  RETRY_POLICY: none | explicit <retry_policy_id>
  TIMEOUT: <seconds> | default
  WORKING_DIR: <relative_path> | default
```

Empty line terminates the stage block.

#### 12.6.1 Default token resolution

For any stage field that specifies `default`, resolution proceeds:

1. stage-declared explicit value (if not `default`);
2. `GLOBAL_DEFAULTS` value for that key;
3. primitive catalog `DEFAULT_*` field;
4. hard-coded runner fallback.

If no level provides a value, the runner MUST halt with
`MISSING_DEFAULT_REQUIRED`.

### 12.7 Failure rules

`FAILURE_RULES` MUST define allowed failure actions.

Allowed in Phase 1:
- `halt`;
- `continue_under_tolerance <rule_id>`.

Silent recovery actions are prohibited.

### 12.8 Tolerance rules

```
TOLERANCE <rule_id> | <scope> | <condition> | <action>
```

`scope` ∈ `stage:<id> | validator:<id> | failure_class:<name>`.
`action` ∈ `continue | skip_stage | use_fallback_artifact:<id>`.

A tolerance rule MUST NOT authorize silent guessing, silent
repair, missing authoritative payload, or suppression of required
diagnostics.


## 13. Runner behavior

### 13.1 Requirements

A conforming runner MUST:

- parse sections deterministically;
- verify required top-level sections exist;
- verify referenced artifact and stage IDs;
- verify stage IDs are unique;
- verify dependency structure is valid (acyclic);
- validate required inputs before dispatch;
- invoke declared primitives with declared inputs only;
- enforce execution timeouts on every subprocess;
- run declared validators after execution;
- persist outputs and diagnostics;
- stop on failure unless an explicit tolerance rule applies;
- avoid silent guessing, silent repair, silent auto-retry;
- enforce security hardening (§13.8).

#### 13.1.1 Encoding enforcement

Before dispatching any primitive, the runner MUST verify all
input artifact files are valid UTF-8 with LF line endings.
Failure → stage fails with `ENCODING_VIOLATION`.

### 13.2 Execution order (Phase 1)

Strict sequential topological sort. Parallel execution is
prohibited.

### 13.3 Execution algorithm

1. Create run workspace `runs/<run_id>/`.
2. Load and validate `contracts_guide.txt`.
3. Load `current_inventory.txt`, `primitive_catalog.txt`, and
   relevant schemas.
4. Verify primitive versions (§7.3.2).
5. Verify mandatory prerequisites are present.
6. Load instance artifacts into `artifacts/`.
7. Validate encoding (§13.1.1).
8. Parse workflow map and construct execution graph.
9. Verify artifact registry resolution.
10. Evaluate dependencies (topological order).
11. For each ready stage:
    a. Resolve `INPUTS`/`OUTPUTS` artifact IDs to absolute paths.
    b. Invoke the declared primitive with resolved paths and
       declared timeout.
    c. Capture stdout, stderr, exit code.
    d. On timeout: kill subprocess, mark stage failed.
    e. Run declared validators.
    f. If all required pass: persist outputs, record success.
    g. If any required fail: preserve diagnostics, halt or apply
       tolerance rule.
12. Record final run status.
13. Update run index (§15.3).

Retries and hill-climbing MAY exist only as explicit workflow
behavior. Silent interpreter retries are prohibited.

### 13.4 Timeout enforcement

| Class                | Default | Behavior on timeout                                |
|---|---|---|
| File & Text          | 10s     | Kill subprocess, preserve partial output           |
| Prompt Assembly      | 5s      | Kill subprocess, stage fail                        |
| LLM Invocation       | 180s    | Kill subprocess, preserve partial reply if any     |
| Answer Extraction    | 10s     | Kill subprocess                                    |
| Contract Validation  | 10s     | Kill subprocess                                    |
| SQLite               | 30s     | Kill subprocess, preserve database state           |
| Export & Materialize | 60s     | Kill subprocess                                    |

Stage-level `TIMEOUT` field overrides defaults.

### 13.5 Primitive invocation record

The runner MUST preserve a structured JSON record in
`diagnostics/invocation_<stage_id>.txt`:

```json
{
  "primitive_name": "...",
  "primitive_version": "...",
  "effective_arguments": {...},
  "working_directory": "...",
  "exit_code": 0,
  "start_timestamp": "...",
  "end_timestamp": "...",
  "duration_seconds": 0.0,
  "stdout_capture": null,
  "stderr_capture": "",
  "timeout_applied": 0,
  "telemetry_file": null
}
```

### 13.6 Stdout capture

When a primitive's output contract declares stdout as
authoritative, the runner captures stdout and writes it to the
declared output path, recording the write in §13.5.

### 13.7 Primitive invocation record storage

Invocation records are stored in
`diagnostics/invocation_<stage_id>.txt` as described in §13.5.

### 13.8 Security hardening

The runner MUST enforce:

1. **Path containment.** All artifact paths resolved through
   `ARTIFACT_REGISTRY` MUST satisfy:

   ```python
   canonical_path = pathlib.Path(resolved_path).resolve()
   assert canonical_path.is_relative_to(RUN_ROOT.resolve())
   ```

   Violation → halt with `SECURITY_VIOLATION`.

2. **Subprocess safety.** All invocations MUST use
   `subprocess.run(args_list, shell=False)`. The runner MUST NOT
   use `shell=True`.

3. **Symlink handling.** Symlinks MUST be resolved before
   containment check. Symlinks pointing outside `RUN_ROOT` are
   rejected.


## 14. Failure policy

A stage that violates a required contract MUST:

- fail loudly;
- preserve evidence;
- stop progression unless an explicit continuation or tolerance
  rule applies.

On failure, the system MUST preserve as many as applicable:

| Evidence                | Location                                          |
|---|---|
| Input snapshot          | `diagnostics/input_snapshot_<stage_id>.txt`       |
| Raw model output        | `diagnostics/raw_reply_<stage_id>.txt`            |
| Extracted partial output| `diagnostics/partial_<stage_id>.txt`              |
| Validation report       | `diagnostics/validation_<stage_id>.txt`           |
| Parse diagnostics       | `diagnostics/parse_<stage_id>.txt`                |
| Invocation record       | `diagnostics/invocation_<stage_id>.txt`           |
| State snapshot          | `diagnostics/state_<stage_id>.txt` or DB snapshot |
| Transition log          | `diagnostics/transition_log.txt`                  |
| Telemetry file          | `diagnostics/telemetry_<stage_id>.json`           |

Silent repair, silent failover, and silent retry are prohibited.


## 15. Diagnostics and idempotency

### 15.1 Per-run diagnostics

Each run SHOULD preserve:

- `run_metadata.txt` (Run ID, timestamp, input hash, workflow
  hash, primitive catalog hash, contracts guide hash);
- `raw_reply_<stage_id>.txt` per LLM stage;
- `validation_<stage_id>.txt` per validated stage;
- `parse_<stage_id>.txt` per parsed stage;
- `invocation_<stage_id>.txt` per invocation;
- `telemetry_<stage_id>.json` per primitive invocation;
- `transition_log.txt` covering every state transition;
- canonical outputs in `generated/` or `artifacts/`.

### 15.2 `transition_log.txt` format

```
<iso8601_timestamp> | <stage_id> | <from_status> -> <to_status> | <trigger>
```

### 15.3 Run index

```sql
CREATE TABLE run_index (
  run_id TEXT PRIMARY KEY,
  input_hash TEXT NOT NULL,
  workflow_map_hash TEXT NOT NULL,
  primitive_catalog_hash TEXT NOT NULL,
  primitive_catalog_version TEXT NOT NULL,
  contracts_guide_hash TEXT NOT NULL,
  status TEXT NOT NULL,
  completed_at TEXT NOT NULL,
  artifact_count INTEGER
);
```

#### 15.3.1 Run status semantics

| Status    | Condition                                                               |
|---|---|
| `success` | All declared stages completed; all required validators passed for each. |
| `failed`  | A required validator failed AND no tolerance rule permitted progression;
              OR the runner halted due to structural error.                           |
| `partial` | One or more stages completed, but the run terminated before all stages
              executed (explicit tolerance halt, user abort, unrecoverable runtime     |
              error).                                                                 |

ONLY runs with `status='success'` are eligible for idempotent
reuse.

### 15.4 Idempotency mechanism

Before execution, the runner computes SHA-256 hashes:

- `input_hash` from concatenated input artifact contents (§15.4.1
  canonicalization);
- `workflow_map_hash` from `workflow_map.txt`;
- `primitive_catalog_hash` from `primitive_catalog.txt`;
- `contracts_guide_hash` from `contracts_guide.txt`.

If a row exists in `run_index` with matching four hashes AND
`status = 'success'` AND matching catalog version, the runner MAY
reuse artifacts from that run.

Reuse rules:

- reuse MUST be logged in `diagnostics/run_metadata.txt`;
- stale or failed artifacts MUST NOT be reused;
- catalog version must match.

#### 15.4.1 Hash canonicalization

All hashes are SHA-256 (hex, lowercase) computed as:

1. **Per-artifact canonicalization:**
   - decode bytes as UTF-8 (fail on invalid bytes);
   - normalize line endings to LF;
   - strip trailing whitespace and final newline.

2. **`input_hash` construction:**
   - collect input-class artifacts referenced by
     `ARTIFACT_REGISTRY`;
   - sort by `artifact_id` lexicographically;
   - concatenate with `"\n---\n"` separators;
   - hash.

3. **`workflow_map_hash`, `primitive_catalog_hash`,
   `contracts_guide_hash`:** SHA-256 of each file's canonicalized
   content.

4. **Full run fingerprint:** all four MUST match for reuse
   eligibility.


## 16. Mandatory prerequisites

Before any implementation code is written, the following three
artifacts MUST exist in their frozen formats:

1. `primitive_catalog.txt` — ≤ 20 entries in §7.3.1 format.
2. `contracts_guide.txt` — in §10.9 format.
3. `gold_workflow_map.txt` — hand-written gold-standard map in
   §12.2 format passing all required validators of §11.

These artifacts MUST be valid and parsable before any runner code
is written or tested. The runner MUST fail immediately if any of
these three artifacts is missing or invalid at start-up.

### 16.1 Minimal conforming example

The following minimal gold map demonstrates that the grammar is
non-empty:

```
WORKFLOW_METADATA
  WORKFLOW_ID: minimal_gold
  WORKFLOW_NAME: minimal_example
  WORKFLOW_VERSION: 1.0.0
  REFERENCE_APP: example

GLOBAL_DEFAULTS
  ENCODING: utf-8
  LINE_ENDING: lf
  TIMEOUT: 180

ARTIFACT_REGISTRY
  ARTIFACT raw_request | request.txt | input | input/request.txt | external | stage_greet | none | persistent
  ARTIFACT greeting | greeting.txt | output | artifacts/greeting.txt | stage_greet | none | validator_greeting_present | deliverable

STAGES
  STAGE stage_greet
    NAME: produce_greeting
    PRIMITIVE: call_llm
    INPUTS: raw_request
    OUTPUTS: greeting
    DEPENDS_ON: none
    VALIDATORS: validator_greeting_present
    FAILURE_POLICY: halt
    RETRY_POLICY: none
    TIMEOUT: 180
    WORKING_DIR: default

EXECUTION_RULES
  ORDER: sequential

VALIDATION_RULES
  VALIDATOR validator_greeting_present | file_presence | greeting | empty | required

FAILURE_RULES
  halt
```

A conforming runner on this map, given `input/request.txt`
containing "Greet the world", produces
`artifacts/greeting.txt` containing `<answer>Hello, World!</answer>`
(with optional commentary), status `success`, and a complete
diagnostics tree.


## 17. Central runner exit code registry

| Code      | Name                           | Meaning                                   |
|---|---|---|
| 128       | `VERSION_MISMATCH`             | Primitive binary version ≠ catalog version |
| 129       | `ENCODING_VIOLATION`           | Input artifact not valid UTF-8 with LF     |
| 130       | `PRIMITIVE_NOT_FOUND`          | Primitive executable not found             |
| 131       | `MISSING_DEFAULT_REQUIRED`     | A `default` token could not be resolved    |
| 132       | `SECURITY_VIOLATION`           | Path traversal or shell injection detected |
| 133       | `SCHEMA_CONFORMANCE_FAILURE`   | Schema artifact malformed                  |
| 134–255   | Reserved                       | Future expansion                           |

Primitives MUST use 0–127. Runner MUST use 128–255.


## 18. Phase 1 constraints

Phase 1 MUST optimize for a stable closed world, not maximum
generality.

Phase 1 MUST:

- freeze a deliberately small primitive set (≤ 20 primitives);
- freeze the grammar subset (§12.2);
- execute all stages sequentially;
- maintain at least one hand-written gold-standard workflow map;
- require validator-backed acceptance before any generated
  workflow map is runnable;
- keep the reference application narrow enough to validate the
  architecture end to end.

### 18.1 Gold-standard map (mandatory)

Before any generated workflow map is accepted for execution, the
system MUST have at least one hand-written workflow map for the
reference application that:

- conforms to §12.2;
- references only primitives from the frozen catalog;
- passes all required validators;
- executes to completion with `status=success`;
- produces all declared deliverables in `generated/`.

Stored as `gold_workflow_map.txt`, included in the conformance
test suite.


## 19. Non-Goals

Phase 1 does not require:

- maximum grammar expressiveness;
- autonomous self-modifying runners;
- hidden dynamic replanning during execution;
- automatic repair through unconstrained recursive prompting;
- large universal primitive catalogs on day one;
- silent heuristic recovery;
- parallel stage execution;
- multi-line values in workflow maps;
- real-time streaming diagnostics.


## 20. Build order

| Priority | Component                                              | Why                              |
|---|---|---|
| 1        | `primitive_catalog.txt` (≤ 20, §7.3.1 format)          | Runner cannot start without it   |
| 2        | `contracts_guide.txt` (§10.9 format)                   | Parsing and validation derive    |
| 3        | `gold_workflow_map.txt` (hand-written)                 | End-to-end validation            |
| 4        | Runner skeleton (§13.3)                                | Core engine                      |
| 5        | Primitive implementations                              | Runner dispatches these          |
| 6        | Validator implementations (§11.3)                      | Gate progression                 |
| 7        | Canonical artifact formats (§8.5)                      | Planning and validation artifacts|
| 8        | Idempotency index + run_id generator                   | Re-run safety                    |
| 9        | Conformance test suite (§21.1)                         | Gates Phase 1 completion         |


## 21. Conformance summary and test suite

A system conforms to this specification only if it:

| #  | Requirement                     | Description                                               |
|---|---|---|
| 1  | Stable primitives               | Uses stable named primitives with explicit CLI and versions |
| 2  | File boundaries authoritative   | Treats file boundaries as authoritative; no hidden          |
|    |                                 | in-memory contracts                                         |
| 3  | Durable artifacts               | Uses durable artifacts as authoritative working memory      |
| 4  | Artifact immutability           | Strict immutability for text/file artifacts; new versions   |
|    |                                 | get new IDs                                                 |
| 5  | Implementation plan             | Includes an implementation plan as a first-class artifact   |
| 6  | Deterministic contracts         | Enforces deterministic contracts via `contracts_guide.txt`  |
| 7  | Workflow map as sole control    | Uses a workflow map as the sole workflow-control artifact   |
| 8  | Contracts guide present         | `contracts_guide.txt` exists and conforms to §10.9          |
| 9  | Primitive catalog present       | `primitive_catalog.txt` exists with ≤ 20 entries conforming |
|    |                                 | to §7.3.1                                                   |
| 10 | Generic runner                  | Runs through a generic interpreter without embedded         |
|    |                                 | project-specific logic                                      |
| 11 | Sequential execution (Phase 1)  | Executes stages in strict topological order                 |
| 12 | Timeout enforcement             | Enforces timeouts on all subprocesses (§13.4)               |
| 13 | Encoding enforcement            | Validates UTF-8 and LF on all input artifacts (§13.1.1)     |
| 14 | Run workspace isolation         | Each run gets a unique `runs/<run_id>/` workspace (§9.1)    |
| 15 | Explicit validators             | Declares validators explicitly with severity levels (§11.2) |
| 16 | Required validators gate        | `severity=required` validators must pass before stage       |
|    | progression                     | success                                                     |
| 17 | Fail loud                       | Fails loudly on contract violations; preserves full         |
|    |                                 | diagnostics (§14)                                           |
| 18 | No silent recovery              | Avoids silent retries, repairs, failover, and hidden state  |
| 19 | Idempotency                     | Supports idempotent reruns via hashed run index (§15.4)     |
| 20 | Gold-standard map               | `gold_workflow_map.txt` exists, runs to completion, passes  |
|    |                                 | all validators                                              |
| 21 | Phase 1 constraints             | ≤ 20 primitives, frozen grammar, sequential execution,      |
|    |                                 | validator-backed acceptance                                 |
| 22 | Primitive discovery             | Resolves primitives via `$PRIMITIVE_HOME` or `$PATH` (§7.5) |
| 23 | Validator invocation            | Validators are runner-internal dispatch functions (§11.3)   |
| 24 | Hash canonicalization           | Idempotency hashes use canonicalized content (§15.4.1)      |
| 25 | Security hardening              | Runner enforces path containment and `shell=False` (§13.8)  |
| 26 | Canonical artifact formats      | All referenced canonical artifacts have frozen formats      |
|    |                                 | (§8.5)                                                      |

### 21.1 Conformance test suite (mandatory)

A conforming implementation MUST pass these automated tests:

| Test                                  | Description                                                       | Verifies |
|---|---|---|
| `test_primitive_catalog_load`         | Loads `primitive_catalog.txt`, all entries parse, ≤ 20 primitives, all required fields | §7.3.1 |
| `test_primitive_version_match`        | Each primitive reports version matching catalog entry             | §7.3.2 |
| `test_contracts_guide_load`           | Loads `contracts_guide.txt`, all required sections present        | §10.9 |
| `test_workflow_map_parse`             | Loads `gold_workflow_map.txt`, parses without error, all refs resolve | §12.2, §12.5 |
| `test_dag_resolution`                 | Dependency graph is acyclic, topological order exists             | §13.2 |
| `test_sequential_execution`           | Runner executes gold map sequentially in declared order           | §13.2, §13.3 |
| `test_validator_required_gate`        | Stage with `severity=required` validator that fails halts progression | §11.2, §10.7 |
| `test_validator_optional_diagnose`    | Stage with `severity=optional` validator that fails continues, diagnostic emitted | §11.2, §10.7 |
| `test_artifact_immutability`          | Attempting to overwrite artifact produces new ID or fails; original preserved | §8.2 |
| `test_timeout_enforcement`            | 1 s timeout running a 10 s sleep is killed, stage failed, diagnostics preserved | §13.4 |
| `test_encoding_enforcement`           | Invalid UTF-8 input artifact causes `ENCODING_VIOLATION`, stage fails | §13.1.1 |
| `test_failure_halt`                   | Stage with missing required output halts runner, full diagnostics preserved | §14 |
| `test_tolerance_rule_continue`        | Stage with tolerance rule continues on tolerable failure, diagnostics name rule | §12.8 |
| `test_idempotent_rerun`               | Second run with identical hashes reuses artifacts, logs previous run_id | §15.4 |
| `test_non_idempotent_different_input` | Different input produces new run_id, no reuse                     | §15.4 |
| `test_failed_artifact_not_reused`     | Run with `status=failed` is not reused                            | §15.3.1, §15.4 |
| `test_partial_not_reused`             | Run with `status=partial` is not reused                           | §15.3.1 |
| `test_telemetry_capture`              | Every primitive invocation produces telemetry file in `diagnostics/` | §7.2.1 |
| `test_contract_enforcement`           | Parser rejects output without `<answer>` wrapper; prompt assembly produces all 5 sections | §10.6 |
| `test_implementation_plan_present`    | `implementation_plan.txt` exists and passes its schema validator  | §8.6.1 |
| `test_gold_workflow_map_completes`    | `gold_workflow_map.txt` executes to `success`                     | §18.1 |
| `test_run_workspace_isolation`        | Two concurrent runs produce different `runs/<run_id>/`, no collisions | §9.1 |
| `test_directory_separation`           | Stage writing to `artifacts/` cannot write to `generated/` without declaration | §9.3 |
| `test_version_mismatch_failure`       | Primitive version differs from catalog → `VERSION_MISMATCH`       | §7.3.2 |
| `test_primitive_discovery`            | Runner finds primitive via `$PRIMITIVE_HOME`; missing yields `PRIMITIVE_NOT_FOUND` | §7.5 |
| `test_security_hardening`             | Path traversal in `ARTIFACT_REGISTRY` yields `SECURITY_VIOLATION`; runner uses `shell=False` | §13.8 |
| `test_hash_canonicalization`          | Same inputs with different file order produce identical `input_hash` | §15.4.1 |
| `test_canonical_artifact_formats`     | `validation_plan.txt`, `state_model.txt`, `current_inventory.txt` conform to §8.5 | §8.5 |
| `test_conformance_all_26`             | All 26 conformance requirements from §21 verified programmatically | §21 |

Twenty-nine tests. Each maps to one or more section references.
A conforming implementation MUST pass all twenty-nine.


## 22. Relationship to SGF, HFF, and Omega

WML is a peer layer to SGF substrate, wire, and governance layers:

- **SGF Core** structures meaning; WML declarations can reference
  that meaning. A stage's output may be a Synapse-bounded
  artifact; contracts between stages can carry SGF-grounded
  content.
- **HFF** may carry WML maps across trust boundaries as data
  payloads. WML itself does not prescribe a wire transport.
- **Omega** can govern WML execution. Which primitives may run,
  under what conditions, with what authority and trust — these
  questions are in Omega's domain. A WML map is an addressable
  input to a governance check.

WML does not depend on SGF to be read or executed — the grammar
is self-contained. SGF infrastructure can, however, inspect and
govern WML execution when both are present.


## 23. Normative references

For related specifications in the SGF family:

- `01-SUBSTRATE-01_SGF_CORE_SPEC.md`
- `01-SUBSTRATE-02_LEXICON.md`
- `02-WIRE-01_HFF_WIRE_PROTOCOL_SPEC.md`
- `02-WIRE-02_AFP_PROTOCOL_SPEC.md`
- `02-WIRE-03_DISCOVERY_CAPABILITY_MANIFEST_SPEC.md`
- `03-OMEGA-01_LANGUAGE_SPEC.md`
- `03-OMEGA-02_FORMAL_GRAMMAR_SPEC.md`

For WML companion specifications:

- `04-WML-02_WML_EXTENSIONS_SPEC.md` — WML composable wrappers
  (`pipeline iterate`, `pipeline tranche`) and the
  codebase-profiling primitive catalog.

For narrative and argumentative context:

- `claims.md` — six theses, dependency DAG, honesty audit.
- `white_paper.md` — architectural intent and migration path.
- `the-map-is-the-app.md` — full thesis article.
- `implementation_plan.md` — build roadmap and domain artifacts.
- `what-makes-wml-a-formal-language.md` — defense of WML's status
  as a formal language.


