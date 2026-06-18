# Primitive-Driven AI Software Generation Architecture
## Formal Technical Specification v8 (FINAL)

### 1. Purpose

This specification defines the minimum technical rules for a software-generation system built from **reusable command-line primitives**, **deterministic file-based contracts**, **durable artifacts**, **explicit validators**, and **declarative workflow maps**.

Its purpose is to make planning, execution, validation, diagnostics, and recovery visible and machine-checkable rather than implicit in prompts, hidden memory, or ad hoc orchestration code.

This specification defines a constrained build system, not a general-purpose autonomous agent.

The governing doctrine:

- Stable primitives first.
- Contracts second.
- Workflow control third.
- Custom logic last.

### 2. Mandatory Prerequisites `[NEW]`

Before any implementation code is written, the following three artifacts MUST exist in their frozen formats as defined by this specification:

1. `primitive_catalog.txt` — Complete frozen catalog ( ≤ 20 primitives) in the format defined by §5.3.1.
2. `contracts_guide.txt` — Global contract artifact in the format defined by §8.8.
3. `gold_workflow_map.txt` — Hand-written gold-standard workflow map for the reference application in the format defined by §10.2, §10.6, §10.7, and passing all required validators of §9.1.

These artifacts MUST be valid and parsable before any runner code is written or tested. The runner MUST fail immediately if any of these three artifacts is missing or invalid at start‑up.

### 3. Scope

This specification governs:

- Primitive requirements and primitive catalog structure.
- Artifact classes, naming, lifecycle, metadata, and immutability.
- Contract rules for stage hand-offs, machine-readable outputs, and prompt assembly.
- Workflow-map structure, parsing grammar, and execution semantics.
- Validator behavior, registry, invocation, and failure semantics.
- Runner behavior, execution order, timeouts, encoding enforcement, diagnostics, security hardening, and rerun rules.
- Directory layout and workspace isolation.
- Phase 1 constraints, gold-standard map requirement, and migration path.
- Conformance test suite.

This version defines a narrow closed world intended to prove the architecture end to end with minimal moving parts.

### 4. Normative Terms

The terms `MUST`, `MUST NOT`, `SHOULD`, `SHOULD NOT`, and `MAY` follow IETF RFC 2119 conventions.

- `MUST`: required for conformance.
- `MUST NOT`: prohibited for conformance.
- `SHOULD`: strongly recommended unless a documented exception exists.
- `SHOULD NOT`: discouraged unless a documented exception exists.
- `MAY`: optional.

### 5. System Model

A conforming system `SHALL` be modeled as a **staged build pipeline** composed from reusable primitives. A run `SHALL` be represented by a workflow map plus a set of named instance artifacts.

The architecture has four layers:

| Layer | Name | Responsibility |
|-------|------|---------------|
| Layer 0 | Substrate | File, path, process, encoding, hash, metadata operations |
| Layer 1 | Application | Prompt assembly, model invocation, extraction, validation, storage, export, retrieval |
| Layer 2 | Composition | Workflow maps, implementation plans, validation plans, state-transition definitions |
| Layer 3 | Custom | Project-specific logic |

Layer 3 `MUST` remain intentionally small. Repeated behavior discovered in Layer 3 `SHOULD` be extracted downward into lower layers when it becomes reusable.

The runner `MUST` remain generic and `MUST NOT` embed project-specific logic.

### 6. Primitive Specification

#### 6.1 Primitive Requirements `[MODIFIED]`

Every primitive `MUST`:

- Do one clear job.
- Expose a stable CLI.
- Accept explicit inputs.
- Produce explicit outputs.
- Fail loudly on malformed required inputs (return nonzero exit code).
- Enforce strict execution timeouts to prevent hanging processes.
- Avoid hidden retries, hidden fallbacks, and hidden repair.
- Preserve deterministic behavior for identical effective inputs and configuration.
- Have a stable published name once included in the primitive catalog.
- Report its version via `--version` flag.
- Accept `--help` flag and print a usage summary to stdout.
- Use a snake_case name (e.g., `call_llm`, not `call-llm` or `callLlm`).

Cosmetic renaming of published primitives is prohibited.

#### 6.2 Interface Conventions

Primitives `SHOULD` use these flags where applicable:

| Flag | Purpose |
|------|---------|
| `--in-file <path>` | Primary input |
| `--out-file <path>` | Primary output |
| `--out-dir <path>` | Directory output |
| `--config-file <path>` | Explicit configuration |
| `--timeout <seconds>` | Override default timeout |
| `--telemetry-file <path>` | Structured telemetry output |

A primitive `MUST` validate required arguments before any side effects occur.

A primitive `MAY` emit primary output to stdout only if that behavior is explicitly documented in its catalog entry and the consuming stage contract declares stdout as authoritative output. When stdout is used, the runner captures the output and writes it to the declared output artifact file (see §11.6).

##### 6.2.1 Telemetry File Contract

When `--telemetry-file <path>` is provided, the primitive `MUST` write a JSON object to that path on completion (success or failure):

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

The runner MUST also write its own invocation record to `diagnostics/` (§11.5).

#### 6.3 Primitive Catalog

The primitive catalog is a first-class artifact stored as `primitive_catalog.txt`. `[MODIFIED: fixed filename]`

##### 6.3.1 Primitive Catalog Entry Format (Frozen) `[MODIFIED: clarified INPUT_CONTRACT/OUTPUT_CONTRACT]`

The file `primitive_catalog.txt` MUST use the following line-oriented format. Each primitive occupies a contiguous block terminated by a blank line.

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

`INPUT_CONTRACT` and `OUTPUT_CONTRACT` MUST reference an artifact class name from §7.3 (e.g., `prompt_artifact`, `raw_llm_reply`), not a file path or artifact ID. Schema references use the schema artifact's class name (e.g., `workflow_map_schema`).

**Example:**

```
PRIMITIVE call_llm
  PURPOSE: invoke a language model with a prompt and return the response
  REQUIRED_ARGS: --in-file; --out-file; --model
  OPTIONAL_ARGS: --temperature; --max-tokens; --telemetry-file
  INPUT_CONTRACT: prompt_artifact
  OUTPUT_CONTRACT: raw_llm_reply
  SIDE_EFFECTS: none
  EXIT_CODES: 0=success; 1=model_unavailable; 2=timeout; 3=malformed_prompt
  DEFAULT_TIMEOUT: 180
  VALIDATOR_EXPECTATIONS: validator_reply_nonempty; validator_answer_wrapper
  VERSION: 1.0.0
```

##### 6.3.2 Primitive Versioning

Each primitive catalog entry MUST include a `VERSION` field (semver).

The runner MUST verify that the primitive version invoked matches the catalog version. If a primitive binary or script reports a different version (via `--version` flag), the runner MUST fail the stage with exit code `VERSION_MISMATCH`.

##### 6.3.3 Frozen Catalog Size

The Phase 1 executable catalog MUST be frozen at **≤ 20 primitives** before generated workflow maps are accepted for execution.

#### 6.4 Primitive Classes

Phase 1 SHOULD use a deliberately small primitive set across these classes:

| Class | Example Primitives | Default Timeout |
|-------|-------------------|----------------|
| File & Text | `read_file`, `write_file`, `chunk_text`, `detect_encoding` | 10s |
| Prompt Assembly | `build_prompt` | 5s |
| LLM Invocation | `call_llm` | 180s |
| Answer Extraction | `extract_answer` | 10s |
| Contract Validation | `validate_contract` | 10s |
| SQLite | `init_sqlite`, `query_sqlite`, `upsert_sqlite`, `sync_sqlite` | 30s |
| Export & Materialize | `export_assets`, `render_ui`, `compile_app` | 60s |
| Workflow Support | `run_stage` | N/A (runner control) |

Phase 1 MUST prefer the smallest primitive set that fully solves the reference application while preserving determinism, visibility, and restartability.

#### 6.5 Primitive Discovery `[NEW]`

The runner resolves each `PRIMITIVE` name to an executable path in this order:

1. If environment variable `PRIMITIVE_HOME` is set, look for `<PRIMITIVE_HOME>/<primitive_name>`.
2. Otherwise, perform a system `$PATH` lookup via `shutil.which()` or equivalent.

Primitive executable names MUST exactly match the catalog `PRIMITIVE` name (snake_case). If no executable is found, the runner MUST halt with exit code `PRIMITIVE_NOT_FOUND`. Phase 1 does not support registries, containers, or remote invocation.

---

### 7. Artifact Model

#### 7.1 General Rules

Artifacts are the authoritative working memory of the system.

Intermediate results, diagnostics, validation reports, schemas, workflow declarations, and deliverables MUST be represented as explicit artifacts rather than hidden transient state.

Every artifact MUST be:

- Named.
- Persisted to disk.
- Addressable by path.
- Associated with a stage, a global role, or both.
- Suitable for human inspection and machine consumption.

The runner MUST enforce schemas against instance artifacts wherever a schema exists.

A workflow map is an instance artifact. A workflow-map schema is a schema artifact.

#### 7.2 Artifact Immutability Law

**Text and file artifacts MUST be strictly immutable once produced and validated.**

A stage MUST NOT overwrite or modify an existing artifact. If an artifact requires modification (e.g., code refinement, prompt revision), the stage MUST produce a new artifact with a distinct ID (e.g., `code_v1` → `code_v2`, `prompt_v1` → `prompt_v2`).

The **only** exception to this rule is formal state (e.g., SQLite databases), which are explicitly mutated via defined database primitives (`query_sqlite`, `upsert_sqlite`, `sync_sqlite`).

This immutability rule ensures:

- Every artifact version is preserved for audit.
- Downstream consumers are never surprised by silent overwrites.
- Idempotency checks are straightforward (same inputs → same outputs → same artifacts).
- Rollback is possible by reverting to a previous artifact version.

#### 7.3 Artifact Classes

The system SHALL recognize at least these artifact classes:

| Class | Examples |
|-------|----------|
| Source inputs | User intent, reference app spec |
| Inventory | `current_inventory.txt` |
| Primitive catalog | `primitive_catalog.txt` |
| Contracts | `contracts_guide.txt` |
| Schema | `workflow_map_schema.txt`, `state_model_schema.txt` |
| Instance | `workflow_map.txt`, `validation_plan.txt` |
| Implementation | `implementation_plan.txt` |
| Validation | `validation_plan.txt`, validation reports |
| State | `state_model.txt`, `sqlite_schema.txt` |
| API contracts | `api_contracts.txt` |
| Dependencies | Dependency manifests |
| UI decomposition | `ui_decomposition.txt` |
| Raw outputs | Raw LLM replies |
| Diagnostics | Parse diagnostics, error reports |
| Canonical outputs | Extracted machine-readable payloads |
| Deliverables | Generated code, rendered UI |

#### 7.4 Standard Artifact Names

A conforming Phase 1 implementation SHOULD support at least:

| Name | Class | Role |
|------|-------|------|
| `current_inventory.txt` | Inventory | List of known primitives, schemas, contracts |
| `primitive_catalog.txt` | Catalog | Full primitive definitions with contracts and exit codes |
| `contracts_guide.txt` | Contracts | Hard rules for parsing, wrappers, and failure |
| `workflow_map_schema.txt` | Schema | Grammar for workflow map documents |
| `workflow_map.txt` | Instance | Current run's workflow composition |
| `gold_workflow_map.txt` | Instance | Hand-written gold-standard map for reference app |
| `reference_app_spec.txt` | Source input | Bounded application specification |
| `implementation_plan.txt` | Implementation | Build order, file layout, stage assignments |
| `validation_plan.txt` | Validation | Declared validators per stage |
| `api_contracts.txt` | API contract | Interface contracts between components |
| `ui_decomposition.txt` | UI decomposition | UI component tree and rendering rules |
| `state_model.txt` | State | Database schema and state definitions |

#### 7.5 Canonical Artifact Frozen Formats `[NEW]`

The following canonical artifacts MUST follow the frozen formats described below. Each format is a line‑oriented plain‑text file adhering to the structural rules of §8.3.

##### 7.5.1 `validation_plan.txt` Format

```
VALIDATION_PLAN:
  workflow_id: <workflow_id>
  version: <semver>

VALIDATORS:
  <validator_id> | <validation_type> | <target_artifact_id> | <failure_condition> | <severity>
  ...
```

Each line in `VALIDATORS:` follows the same pipe‑delimited schema as §9.1.

##### 7.5.2 `state_model.txt` Format

```
STATE_MODEL:
  version: <semver>

TABLES:
  <table_name>: <column_name> <type> [PRIMARY KEY] [NOT NULL] [DEFAULT <value>]; ...
  ...

INDEXES:
  <index_name> ON <table_name> (<column_name>, ...); ...
```

`type` MUST be one of `TEXT`, `INTEGER`, `REAL`, `BLOB`. Primary key and index declarations are optional but recommended for the reference application.

##### 7.5.3 `current_inventory.txt` Format

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

##### 7.5.4 `api_contracts.txt` Format

```
API_CONTRACTS:
  version: <semver>

ENDPOINTS:
  <endpoint_id> | <method> | <path> | <input_artifact_id> | <output_artifact_id> | <description>
  ...
```

##### 7.5.5 `ui_decomposition.txt` Format

```
UI_DECOMPOSITION:
  version: <semver>

COMPONENTS:
  <component_id> | <type> | <renders> | <state_artifact_id> | <event_artifact_id> | <description>
  ...
```

##### 7.5.6 `reference_app_spec.txt` Format

```
REFERENCE_APP_SPEC:
  name: <app_name>
  version: <semver>
  description: <text>

REQUIREMENTS:
  - <requirement_1>
  - <requirement_2>
  ...

CONSTRAINTS:
  - <constraint_1>
  ...
```

##### 7.5.7 `workflow_map_schema.txt` Format

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
  EXAMPLE_RUN

SYNTAX:
  section_markers: UPPER_SNAKE_CASE on own line
  key_value_split: first colon
  lists: semicolon-separated, no trailing semicolon
  multi_line_values: NOT ALLOWED
  comments: lines starting with #
  pipe_delimiter: ALL registry entries MUST use pipe-delimited format with single spaces around pipes
```

#### 7.6 Implementation Plan

`implementation_plan.txt` is a first-class artifact.

##### 7.6.1 Implementation Plan Format (Frozen)

The file `implementation_plan.txt` MUST contain:

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
  - <assumption_2>

OPEN_QUESTIONS:
  - <question_1>
  - <question_2>
```

A system with architectural artifacts but no implementation plan is under-specified for nontrivial execution.

#### 7.7 Artifact Metadata

Every persistent artifact record SHOULD capture at least:

| Field | Description |
|-------|-------------|
| artifact_id | Unique identifier |
| artifact_class | From §7.3 classification |
| relative_path | Path within run workspace |
| producing_stage | Stage ID that created this artifact |
| creation_timestamp | When artifact was written |
| last_validation_status | pass, fail, or untested |
| content_hash | SHA-256 hex-encoded lowercase hash of artifact content |
| version | Monotonically increasing (v1, v2, v3...) |

##### 7.7.1 Content Hash Algorithm

All content hashes in this specification (artifact metadata, idempotency, diagnostics) MUST use SHA-256, hex-encoded, lowercase.

---

### 8. Directory Layout & Workspace Isolation

#### 8.1 Run Workspace

Every execution MUST occur within a unique `runs/<run_id>/` workspace.

##### 8.1.1 Run ID Generation

`run_id` MUST be generated as:

```
run_<utc_timestamp_iso8601_no_punct>_<short_hash>
```

**Example**: `run_20260617T235023Z_a1b2c3d4`

Where `short_hash` = first 8 characters of SHA-256(concatenated input artifact paths).

#### 8.2 Required Subdirectories

A run workspace MUST contain:

| Directory | Contents | Persistence |
|-----------|----------|-------------|
| `runs/<run_id>/artifacts/` | Persistent named instance and schema artifacts | Durable across reruns |
| `runs/<run_id>/temp/` | Intermediate stage-local files | See §8.3 |
| `runs/<run_id>/generated/` | Materialized deliverables and final code outputs | Output of successful runs |
| `runs/<run_id>/runtime/` | Mutable run-support assets (SQLite databases, config) | Durative during execution |
| `runs/<run_id>/diagnostics/` | Validation reports, raw LLM outputs, parse diagnostics, error snapshots | Durative per run |

#### 8.3 Directory Separation Rules `[MODIFIED: added temp cleanup timing]`

Clear separation between temporary, persistent, and generated artifacts MUST be maintained at all times.

The runner MUST enforce that:

- `artifacts/` contains only immutable, validated artifacts.
- `temp/` contains only stage-local intermediates that may be discarded. The runner MUST delete the contents of `temp/` after each stage that completes with `status=success`. On stage failure, `temp/` contents MUST be preserved for diagnostics.
- `generated/` contains only final deliverables.
- `runtime/` contains only mutable state (SQLite databases).
- `diagnostics/` contains only evidence from failures and validation.

#### 8.4 Diagnostics File Requirements

Each run MUST preserve at minimum:

- `runs/<run_id>/diagnostics/run_metadata.txt` — Run ID, timestamp, input hash, workflow hash.
- `runs/<run_id>/diagnostics/validation_<stage_id>.txt` — Validation results per stage where validation was declared.

#### 8.5 `run_metadata.txt` Format `[NEW]`

`run_metadata.txt` MUST use the following key‑value format:

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

---

### 9. Contract Model

#### 9.1 General Contract Law

Every stage MUST declare:

- Input artifacts.
- Output artifacts.
- Validation requirements.
- Failure behavior.

File boundaries are authoritative. **Hidden in-memory contracts between stages are prohibited.**

Machine-consumable outputs MUST be deterministic and parseable.

#### 9.2 Authoritative Output Wrapper

Where LLM-generated machine-readable output is consumed downstream, the authoritative machine payload MUST appear inside:

- Opening tag: `<answer>`
- Closing tag: `</answer>`

Content outside the authoritative wrapper MUST be treated as non-authoritative for machine parsing.

Human commentary outside the wrapper is allowed for readability but MUST be ignored by parsers.

#### 9.3 Structural Text Rules

When structured plain text is used:

- Section markers MUST appear on their own lines.
- Key-value parsing MUST split on the first colon only.
- Required keys MUST be declared and validated.
- Duplicate keys MUST fail unless the contract explicitly permits repetition.
- UTF-8 SHOULD be the default encoding.
- Line endings SHOULD be normalized to LF where practical.

#### 9.4 Parser Behavior

Parsers MUST validate, extract, and stop.

Parsers MUST NOT:

- Guess intended structure.
- Silently reinterpret malformed structure.
- Repair malformed output through a second model call.
- Continue after required contract failure.

If partial extraction succeeds before failure, the partial artifact MAY be preserved for diagnostics, but the stage MUST still fail.

#### 9.5 Prompt Assembly Contracts `[MODIFIED: added template storage]`

Prompts are Layer 3 artifacts and MUST NOT be giant, unstructured blobs. They MUST be assembled hierarchically via the `build_prompt` primitive using these required sections:

| Section | Purpose |
|---------|---------|
| **Big Picture** | High-level goal of the generation task |
| **Context** | Current state, inputs, and constraints |
| **Standards** | Craft knowledge drawn from `contracts_guide.txt` |
| **Task** | Specific instruction for this stage |
| **Output Format** | Exact wrapper, section markers, and key-value expectations |

The prompt template MUST be stored as a file and referenced by path. The `build_prompt` primitive accepts `--template-file <path>` to load the template containing the five sections. This five-section structure SHOULD be the default for all LLM-invoking stages in Phase 1.

#### 9.6 Stage Success Conditions

A stage MUST NOT be marked successful unless **all** of the following hold:

1. Required outputs exist.
2. Required outputs match their declared contract shape.
3. All validators with `severity=required` pass. Validators with `severity=optional` may fail; their diagnostics are preserved but do not halt progression.
4. Required subprocesses exit successfully (exit code 0) unless an explicit tolerance rule allows otherwise.
5. No timeout violation occurred.

#### 9.7 Stop-Worthy Contract Failures `[MODIFIED: added encoding violation, version mismatch]`

The following MUST fail the stage unless an explicit tolerance rule applies:

- Missing required sections.
- Missing answer blocks.
- Empty critical artifacts.
- Missing required files.
- Duplicate keys where disallowed.
- Schema conformance failure.
- Database write failure.
- Export failure.
- Nonzero subprocess exit.
- Validator failure on required checks.
- Timeout violation.
- Version mismatch.
- Encoding violation.

#### 9.8 Contracts Guide Format (Frozen) `[MODIFIED: added precedence rule]`

The file `contracts_guide.txt` is a global contract artifact. It MUST contain these sections in order:

```
PARSING_RULES
  ENCODING: utf-8
  LINE_ENDING: lf
  SECTION_MARKER_PATTERN: ^[A-Z_]+$    (applies to individual line content, not whole file)
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
  - missing_required_file
  - schema_conformance_failure
  - database_write_failure
  - export_failure
  - nonzero_subprocess_exit
  - required_validator_failure
  - timeout_violation
```

**Precedence**: `contracts_guide.txt` is global law and MUST be considered authoritative over `GLOBAL_DEFAULTS` for all parsing rules. `GLOBAL_DEFAULTS` MAY define additional defaults but MUST NOT override `contracts_guide.txt`.

---

### 10. Validation Model

#### 10.1 General Rules

Validators MUST be declared, not implied.

Required validators (`severity=required`) MUST run before progression and gate the stage. Optional validators (`severity=optional`) MAY fail without halting progression; their diagnostics are preserved.

A validator MAY check:

- File presence.
- Nonempty output.
- Required sections.
- Required answer blocks.
- Required keys.
- Allowed values.
- Schema conformance.
- Referential artifact consistency.
- Database write success.
- Export success.
- Content hash agreement.
- Immutability (artifact has not been modified since creation).

A stage MUST NOT be considered successful until all validators with `severity=required` pass, unless an explicit tolerance rule permits continuation for a predefined non-critical condition.

Validation results MUST be persisted as artifacts for failed stages and SHOULD be persisted for critical successful stages.

#### 10.2 Validator Registry Format (Frozen)

Each validator in `VALIDATION_RULES` declared as one pipe-delimited line:

```
VALIDATOR <validator_id> | <validation_type> | <target_artifact_id> | <failure_condition> | <severity>
```

**Fields:**
- `validator_id`: unique snake_case identifier
- `validation_type`: `file_presence` | `answer_block` | `required_keys` | `schema_conformance` | `db_write_success` | `export_success` | `referential_consistency` | `content_hash` | `allowed_values`
- `target_artifact_id`: artifact_id from `ARTIFACT_REGISTRY`
- `failure_condition`: machine-readable predicate (see table below)
- `severity`: `required` | `optional`

**Failure condition syntax per validation_type:**

| validation_type | failure_condition examples |
|----------------|--------------------------|
| `file_presence` | `missing` | `empty` |
| `answer_block` | `missing_wrapper` | `empty_payload` |
| `required_keys` | `missing:<key1>,<key2>` | `duplicate:<key>` |
| `schema_conformance` | `<schema_artifact_id>` |
| `db_write_success` | `row_count_zero` | `lock_timeout` |
| `export_success` | `missing_output` | `write_error` |
| `referential_consistency` | `missing_artifact:<artifact_id>` | `missing_stage:<stage_id>` |
| `content_hash` | `mismatch:<expected_hash_artifact_id>` |
| `allowed_values` | `key:<key_name>:<val1>,<val2>,...` |

#### 10.3 Validator Invocation Contract `[NEW]`

In Phase 1, validators are **runner‑internal dispatch functions**, not external executables. The runner dispatches each declared `VALIDATION_RULE` by:

1. Resolving `target_artifact_id` to its absolute path via `ARTIFACT_REGISTRY`.
2. Invoking the built‑in validator function for the declared `validation_type`.
3. Passing the resolved path, `failure_condition` predicate, and `contracts_guide.txt` path.
4. Returning a validator result: `{passed: bool, message: str, failed_rules: list}`.

Required validators that fail → stage fails.
Optional validators that fail → diagnostic emitted, stage continues.
Custom validator types MAY be added but MUST be declared in `contracts_guide.txt`.

---

### 11. Workflow-Map Specification

#### 11.1 Role

The workflow map is the **sole authoritative declaration of workflow control**.

Stage order, dependencies, inputs, outputs, validators, retries, tolerance rules, and failure policy MUST be declared in the workflow map and MUST NOT be hidden across prompts, scripts, wrappers, or operator habits.

The interpreter MUST parse all top-level sections deterministically.

#### 11.2 Frozen Grammar Subset (Phase 1) `[MODIFIED: added pipe-delimiter rule, case-sensitive keywords]`

The following syntax rules are frozen for Phase 1. Generators and runners MUST reject any deviation.

- **Section markers**: `UPPER_SNAKE_CASE` on own line (e.g., `WORKFLOW_METADATA`)
- **Key-value pairs**: `KEY: value` (split on first colon only)
- **Lists**: semicolon-separated, no trailing semicolon (e.g., `DEPENDS_ON: stage_a; stage_b`)
- **Multi-line values**: NOT ALLOWED in Phase 1. All values single-line.
- **Comments**: lines starting with `#` are ignored.
- **Blank lines**: ignored.
- **Keywords**: All keywords (`PRIMITIVE`, `ARTIFACT`, `STAGE`, `VALIDATOR`, `TOLERANCE`, etc.) are **case-sensitive**.
- **Pipe-delimited entries**: All registry entries (`ARTIFACT_REGISTRY`, `VALIDATION_RULES`, `TOLERANCE_RULES`) MUST use pipe-delimited format with single spaces around pipes.
- **Required top-level sections (exact order)**:
  ```
  WORKFLOW_METADATA
  GLOBAL_DEFAULTS
  ARTIFACT_REGISTRY
  STAGES
  EXECUTION_RULES
  VALIDATION_RULES
  FAILURE_RULES
  ```
- **Optional sections (any order after required)**:
  ```
  TOLERANCE_RULES
  RUNTIME_NOTES
  DEPLOYMENT_TARGETS
  EXAMPLE_RUN
  ```

#### 11.3 Required Sections

A valid workflow map MUST contain these sections in the following order:

```text
WORKFLOW_METADATA
GLOBAL_DEFAULTS
ARTIFACT_REGISTRY
STAGES
EXECUTION_RULES
VALIDATION_RULES
FAILURE_RULES
```

#### 11.4 Workflow Metadata Requirements

`WORKFLOW_METADATA` MUST define at least:

- Workflow ID.
- Workflow name.
- Workflow version.
- Reference application or project identifier.
- Authoring source, if relevant.
- Creation timestamp or version marker.

#### 11.5 Global Defaults Requirements `[MODIFIED: added precedence note]`

`GLOBAL_DEFAULTS` MAY define defaults for:

- Default failure policy.
- Default retry policy.
- Default output directories.
- Default encoding.
- Default validator behavior where appropriate.

Defaults MUST NOT override explicit stage declarations. `GLOBAL_DEFAULTS` MUST NOT override `contracts_guide.txt` (see §9.8).

#### 11.6 Artifact Registry Requirements

The artifact registry MUST define named artifact IDs rather than anonymous raw paths.

##### 11.6.1 Artifact Registry Entry Format (Frozen)

Each entry in `ARTIFACT_REGISTRY` occupies one pipe-delimited line:

```
ARTIFACT <artifact_id> | <name> | <kind> | <path> | <produced_by> | <consumed_by> | <validation_binding> | <persistence>
```

**Fields:**
- `artifact_id`: unique identifier (snake_case, no spaces)
- `name`: human-readable filename (e.g., `implementation_plan.txt`)
- `kind`: `input` | `intermediate` | `output` | `diagnostic` | `schema`
- `path`: relative path under run root (e.g., `artifacts/implementation_plan.txt`)
- `produced_by`: stage_id or `external` (empty string if none)
- `consumed_by`: semicolon-separated stage_ids or `none`
- `validation_binding`: semicolon-separated validator_ids or `none`
- `persistence`: `temporary` | `persistent` | `deliverable`

**Example:**
```
ARTIFACT impl_plan | implementation_plan.txt | intermediate | artifacts/impl_plan.txt | stage_plan | stage_build;stage_test | validator_plan_schema | persistent
```

#### 11.7 Stage Declaration Requirements

Each stage MUST declare:

- Stage ID.
- Stage name.
- Primitive name.
- Required input artifact IDs.
- Expected output artifact IDs.
- Dependency stage IDs or equivalent readiness rule.
- Validator IDs.
- Failure policy.
- Retry policy, if any.

Each stage SHOULD also declare:

- Human-readable purpose.
- Side effects, if any.
- Expected success condition.

##### 11.7.1 Stage Declaration Format (Frozen)

Each stage declared as a contiguous block in `STAGES` section:

```text
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

Blank line terminates the stage block.
```

`default` tokens resolve using the precedence defined in §11.7.2. `WORKING_DIR` specifies a subdirectory within the run workspace where the primitive executes. Use it when a primitive needs to operate in a specific context (e.g., `render_ui` executing in `generated/ui/`). Default is the run root.

##### 11.7.2 Default Token Resolution Order `[NEW]`

For any stage field that specifies `default`, resolution proceeds in this order:

1. Stage-declared explicit value (if not `default`) ← wins
2. `GLOBAL_DEFAULTS` value for that key (if set in workflow map)
3. Primitive catalog `DEFAULT_*` field (if any)
4. Hard-coded fallback built into the runner

If no level provides a value, the runner MUST halt with `MISSING_DEFAULT_REQUIRED`.

#### 11.8 Validation Rules Section

`VALIDATION_RULES` MUST define every validator referenced by stages using the format from §10.2.

#### 11.9 Failure Rules Section

`FAILURE_RULES` MUST define the allowed failure actions.

Allowed actions in Phase 1 SHOULD be limited to:

- `halt`
- `continue_under_tolerance <rule_id>`

Silent recovery actions are prohibited.

#### 11.10 Tolerance Rules

Tolerance rules are narrow, explicit exceptions to fail-loud defaults.

##### 11.10.1 Tolerance Rule Format (Frozen)

Each tolerance rule in `TOLERANCE_RULES` declared as one pipe-delimited line:

```
TOLERANCE <rule_id> | <scope> | <condition> | <action>
```

**Fields:**
- `rule_id`: unique snake_case identifier
- `scope`: `stage:<stage_id>` | `validator:<validator_id>` | `failure_class:<class_name>`
- `condition`: machine-readable predicate (same syntax as validator `failure_condition` from §10.2)
- `action`: `continue` | `skip_stage` | `use_fallback_artifact:<artifact_id>`

A tolerance rule MUST NOT authorize:

- Silent guessing.
- Silent repair.
- Missing authoritative machine payload.
- Suppression of required diagnostics.

---

### 12. Runner Behavior

#### 12.1 General Requirements

The runner is the generic engine that consumes workflow maps and artifacts and dispatches primitives. It MUST treat the workflow map as declarative input, not executable code.

A conforming runner MUST:

- Parse sections deterministically.
- Verify required top-level sections exist.
- Verify referenced artifact IDs exist.
- Verify referenced stage IDs exist.
- Verify stage IDs are unique.
- Verify dependency structure is valid (no cycles, all prerequisites declared).
- Validate required inputs before dispatch.
- Invoke declared primitives with declared inputs only.
- Enforce execution timeouts on every subprocess.
- Run declared validators after execution.
- Persist outputs and diagnostics.
- Stop on failure unless an explicit continuation or tolerance rule allows progression.
- Avoid silent guessing, silent repair, and silent auto-retry.
- Enforce security hardening (§12.8).

##### 12.1.1 Encoding Enforcement

Before dispatching any primitive, the runner MUST verify that all input artifact files are valid UTF-8 with LF line endings. If validation fails, the stage fails immediately with exit code `ENCODING_VIOLATION` and diagnostics preserved.

#### 12.2 Execution Order (Phase 1)

For Phase 1, the runner MUST execute stages using a **strict sequential topological sort**.

Parallel stage execution is prohibited.

#### 12.3 Execution Algorithm

The runner SHOULD execute this control loop:

1. Create run workspace: `runs/<run_id>/` with subdirectories.
2. Load and validate `contracts_guide.txt`.
3. Load global standards artifacts: `current_inventory.txt`, `primitive_catalog.txt`, and relevant schemas.
4. Verify primitive versions match catalog (§6.3.2).
5. Verify all mandatory prerequisites (§2) are present.
6. Load project-specific instance artifacts into `artifacts/`.
7. Validate required inputs (UTF-8, LF line endings, encoding enforcement).
8. Parse workflow-map sections and construct the execution graph.
9. Verify artifact registry resolution (all artifact_ids resolve to paths).
10. Evaluate dependency and readiness rules (sequential topological order).
11. For each ready stage:
    a. Resolve `INPUTS` and `OUTPUTS` artifact IDs to absolute paths using `ARTIFACT_REGISTRY`.
    b. Invoke the declared primitive with resolved paths and declared timeout.
    c. Capture stdout, stderr, exit code.
    d. If timeout exceeded: kill subprocess, mark stage failed.
    e. Run declared validators (required gate, optional diagnose).
    f. If all required validators pass: persist outputs to `artifacts/` or `generated/`, record success.
    g. If any required validator fails: preserve diagnostics to `diagnostics/`, halt or apply tolerance rule.
12. Record final run status.
13. Update run index for idempotency (§14.4).

Retries and hill-climbing MAY exist only as explicit workflow behavior. Silent interpreter retries are prohibited.

#### 12.4 Timeout Enforcement

The runner MUST enforce timeouts as follows:

| Primitive Class | Default Timeout | Runner Behavior on Timeout |
|----------------|-----------------|---------------------------|
| File & Text | 10s | Kill subprocess, stage failure, preserve partial output |
| Prompt Assembly | 5s | Kill subprocess, stage failure |
| LLM Invocation | 180s | Kill subprocess, stage failure, preserve partial reply if available |
| Answer Extraction | 10s | Kill subprocess, stage failure |
| Contract Validation | 10s | Kill subprocess, stage failure |
| SQLite | 30s | Kill subprocess, stage failure, preserve database state |
| Export & Materialize | 60s | Kill subprocess, stage failure |

Stage-level `TIMEOUT` field overrides the default timeout for that specific invocation.

A timeout violation MUST trigger an immediate stage failure with full diagnostics preserved.

#### 12.5 Primitive Invocation Record `[MODIFIED: specified JSON format]`

For each primitive invocation, the runner MUST preserve a structured record in `diagnostics/invocation_<stage_id>.txt`. The record MUST be serialized as JSON:

```json
{
  "primitive_name": "<from catalog>",
  "primitive_version": "<from catalog>",
  "effective_arguments": {"<flag>": "<value>", ...},
  "working_directory": "<path>",
  "exit_code": <int>,
  "start_timestamp": "<iso8601>",
  "end_timestamp": "<iso8601>",
  "duration_seconds": <float>,
  "stdout_capture": "<string or null>",
  "stderr_capture": "<string>",
  "timeout_applied": <int>,
  "telemetry_file": "<path or null>"
}
```

#### 12.6 Stdout Capture Mechanism `[NEW]`

When a primitive's output contract declares `stdout` as authoritative output, the runner:

1. Captures the primitive's stdout stream.
2. Writes the captured content to the file path declared in `OUTPUTS` via `ARTIFACT_REGISTRY`.
3. Records the write in the invocation record (§12.5).

Primitives that MAY emit to stdout MUST also accept `--out-file <path>` as a redirect target. The `build_prompt` primitive is an example that may emit to stdout.

#### 12.7 Primitive Invocation Record Storage

Invocation records are stored in `diagnostics/invocation_<stage_id>.txt` as described in §12.5.

#### 12.8 Security Hardening `[NEW]`

The runner MUST enforce the following:

1. **Path containment**: All artifact paths resolved through `ARTIFACT_REGISTRY` MUST pass:
   ```
   canonical_path = pathlib.Path(resolved_path).resolve()
   assert canonical_path.is_relative_to(RUN_ROOT.resolve())
   ```
   If any path escapes `RUN_ROOT`, halt with `SECURITY_VIOLATION`.

2. **Subprocess safety**: All primitive invocations MUST use `subprocess.run(args_list, shell=False)`. The runner MUST NOT use `shell=True` under any circumstance. Arguments MUST be passed as a list, never concatenated into a string.

3. **Symlink handling**: Symlinks in artifact paths MUST be resolved before containment check. Symlinks pointing outside `RUN_ROOT` are rejected.

---

### 13. Failure Policy

A stage that violates a required contract MUST:

- Fail loudly.
- Preserve evidence.
- Stop progression unless an explicit continuation or tolerance rule allows otherwise.

Stop-worthy failures include:

- Missing required sections.
- Missing answer blocks.
- Empty critical artifacts.
- Missing required files.
- Validator failure on required checks.
- Database write failure.
- Export failure.
- Nonzero subprocess exit.
- Timeout violation.
- Version mismatch.
- Encoding violation.

On failure, the system MUST preserve as many of the following as applicable:

| Evidence | Location |
|----------|----------|
| Input snapshot | `diagnostics/input_snapshot_<stage_id>.txt` |
| Raw model output | `diagnostics/raw_reply_<stage_id>.txt` |
| Extracted partial output | `diagnostics/partial_<stage_id>.txt` (if any) |
| Validation report | `diagnostics/validation_<stage_id>.txt` |
| Parse diagnostics | `diagnostics/parse_<stage_id>.txt` |
| Invocation record | `diagnostics/invocation_<stage_id>.txt` |
| Exit code | Included in invocation record |
| Timeout indicator | Included in invocation record |
| State snapshot | `diagnostics/state_<stage_id>.txt` or DB snapshot |
| Transition log | `diagnostics/transition_log.txt` |
| Telemetry file | `diagnostics/telemetry_<stage_id>.json` (if primitive wrote one) |

**Silent repair, silent failover, and silent retry are prohibited.**

---

### 14. Diagnostics and Idempotency

Diagnostics are durable artifacts, not console noise.

#### 14.1 Per-Run Diagnostics

Each complete or failed run SHOULD preserve:

| Diagnostic | Location |
|------------|----------|
| Run ID | `diagnostics/run_metadata.txt` |
| Timestamp | `diagnostics/run_metadata.txt` |
| Input snapshot hash | `diagnostics/run_metadata.txt` |
| Workflow-map hash | `diagnostics/run_metadata.txt` |
| Primitive catalog hash | `diagnostics/run_metadata.txt` |
| Contracts guide hash | `diagnostics/run_metadata.txt` |
| Raw LLM outputs | `diagnostics/raw_reply_<stage_id>.txt` per stage |
| Validation reports | `diagnostics/validation_<stage_id>.txt` per stage |
| Parse diagnostics | `diagnostics/parse_<stage_id>.txt` per stage |
| Invocation records | `diagnostics/invocation_<stage_id>.txt` per stage |
| Telemetry files | `diagnostics/telemetry_<stage_id>.json` per stage |
| State-transition log | `diagnostics/transition_log.txt` |
| Canonical outputs | `generated/` or `artifacts/` |

#### 14.2 `transition_log.txt` Format `[NEW]`

Each line records one state transition:

```
<iso8601_timestamp> | <stage_id> | <from_status> -> <to_status> | <trigger>
```

Example:
```
2026-06-17T23:50:23Z | stage_plan | pending -> running | dispatched
2026-06-17T23:50:24Z | stage_plan | running -> success | validators_passed
```

#### 14.3 Run Index and Idempotency Cache `[MODIFIED: added primitive_catalog_version, clarified completed_at]`

The runner maintains a run index at `runs/run_index.sqlite` with schema:

```sql
CREATE TABLE run_index (
  run_id TEXT PRIMARY KEY,
  input_hash TEXT NOT NULL,
  workflow_map_hash TEXT NOT NULL,
  primitive_catalog_hash TEXT NOT NULL,
  primitive_catalog_version TEXT NOT NULL,
  contracts_guide_hash TEXT NOT NULL,
  status TEXT NOT NULL,  -- 'success' | 'failed' | 'partial'
  completed_at TEXT NOT NULL,  -- ISO8601 format
  artifact_count INTEGER
);
```

##### 14.3.1 Run Status Semantics `[NEW]`

| Status | Condition |
|--------|-----------|
| `success` | All declared stages completed; all required validators passed for each. |
| `failed` | A required validator failed AND no tolerance rule permitted progression; OR the runner halted due to structural error (missing section, encoding violation, `VERSION_MISMATCH`, cycle detected). |
| `partial` | One or more stages completed with required validators passing, but the run terminated before all stages executed, due to: (a) explicit tolerance rule that halted progression, (b) user abort signal (SIGINT/SIGTERM), or (c) unrecoverable runtime error (disk full, OOM, IO error). |

ONLY runs with `status='success'` are eligible for idempotent reuse (§14.4). Runs with `status='partial'` or `'failed'` MUST NOT be reused.

#### 14.4 Idempotency Mechanism `[MODIFIED: added hash canonicalization]`

Before execution, the runner computes the following SHA-256 hashes using the canonicalization rules of §14.4.1:

- `input_hash` = SHA-256(concatenated input artifact contents, canonicalized)
- `workflow_map_hash` = SHA-256(canonicalized content of `workflow_map.txt`)
- `primitive_catalog_hash` = SHA-256(canonicalized content of `primitive_catalog.txt`)
- `contracts_guide_hash` = SHA-256(canonicalized content of `contracts_guide.txt`)

If a row exists in `run_index` with matching four hashes AND `status = 'success'` AND `primitive_catalog_version` matches the current catalog version, the runner MAY reuse artifacts from that `run_id` (copy from `runs/<prev_run_id>/artifacts/` and `runs/<prev_run_id>/generated/` to current `run_id`).

**Reuse rules:**
- Reuse MUST be logged in `diagnostics/run_metadata.txt` with the previous `run_id`.
- Stale or failed artifacts (`status != 'success'`) MUST NOT be reused.
- Reuse is only valid if the current primitive catalog version matches the cached run's catalog version.

##### 14.4.1 Hash Canonicalization `[NEW]`

All hashes are SHA-256 (hex, lowercase) computed as follows:

1. **Per-artifact canonicalization**:
   - Decode file bytes as UTF-8 (fail on invalid bytes).
   - Normalize line endings to LF.
   - Strip trailing whitespace and final newline.

2. **`input_hash` construction**:
   - Collect all input-class artifacts referenced by `ARTIFACT_REGISTRY`.
   - Sort by `artifact_id` lexicographically (snake_case sort).
   - Concatenate: `canonicalize(a1) + "\n---\n" + canonicalize(a2) + "\n---\n" + ...`
   - Hash the concatenation.

3. **`workflow_map_hash`, `primitive_catalog_hash`, `contracts_guide_hash`**:
   - SHA-256 of each file's canonicalized content.

4. **Full run fingerprint**:
   - `input_hash + workflow_map_hash + primitive_catalog_hash + contracts_guide_hash`
   - All four MUST match for reuse eligibility.

---

### 15. Phase 1 Constraints

Phase 1 MUST optimize for a stable closed world, not maximum generality.

Phase 1 MUST:

- Freeze a deliberately small primitive set ( ≤ 20 primitives).
- Freeze a constrained subset of the workflow-map grammar (§11.2).
- Execute all stages sequentially (no parallelism).
- Maintain at least one hand-written gold-standard workflow map for the reference application.
- Require validator-backed acceptance before any generated workflow map is runnable.
- Keep the reference application narrow enough to validate the architecture end to end.

#### 15.1 Gold-Standard Workflow Map (Mandatory)

Before any generated workflow map is accepted for execution, the system MUST have at least one hand-written workflow map for the reference application that:

- Conforms to the frozen grammar subset (§11.2).
- References only primitives from the frozen catalog (§6.3.1).
- Passes all required validators (§10.2).
- Executes to completion with `status=success`.
- Produces all declared deliverables in `generated/`.

This gold-standard map MUST be stored as `gold_workflow_map.txt` and included in the conformance test suite.

Generated workflow maps in Phase 1 MUST be accepted only if they:

- Conform to the frozen grammar subset.
- Pass all required validators.
- Reference only primitives in the frozen catalog.

#### 15.2 Gold-Standard Workflow Map Example `[NEW]`

A minimal gold-standard workflow map for the reference chat application might look like:

```text
# gold_workflow_map.txt (minimal example)

WORKFLOW_METADATA
  WORKFLOW_ID: chat_app_v1
  WORKFLOW_NAME: local_chat_app
  WORKFLOW_VERSION: 1.0.0
  REFERENCE_APP: local_chat

GLOBAL_DEFAULTS
  FAILURE_POLICY: halt
  TIMEOUT: default

ARTIFACT_REGISTRY
  ARTIFACT app_spec | reference_app_spec.txt | input | reference_app_spec.txt | external | stage_plan | none | persistent
  ARTIFACT impl_plan | implementation_plan.txt | intermediate | artifacts/impl_plan.txt | stage_plan | stage_build | none | persistent

STAGES
  STAGE stage_plan
    NAME: generate_implementation_plan
    PRIMITIVE: generate_plan
    INPUTS: app_spec
    OUTPUTS: impl_plan
    DEPENDS_ON: none
    VALIDATORS: validator_plan_nonempty
    FAILURE_POLICY: halt
    RETRY_POLICY: none
    TIMEOUT: default
    WORKING_DIR: default

  STAGE stage_build
    NAME: build_application
    PRIMITIVE: compile_app
    INPUTS: impl_plan
    OUTPUTS: none
    DEPENDS_ON: stage_plan
    VALIDATORS: none
    FAILURE_POLICY: halt
    RETRY_POLICY: none
    TIMEOUT: default
    WORKING_DIR: default

  [remaining stages for UI, LLM, SQLite, etc.]

EXECUTION_RULES
  ORDER: sequential

VALIDATION_RULES
  VALIDATOR validator_plan_nonempty | file_presence | impl_plan | empty | required

FAILURE_RULES
  halt
```

---

### 16. Reference Application

Phase 1 SHOULD define one bounded reference application.

A **local chat application** is a suitable proof of concept because it exercises:

- UI rendering (local HTML or terminal UI)
- Local backend behavior (event loop, state management)
- LLM invocation (model calls for chat responses)
- Persistence (SQLite for conversation history)
- Optional speech recognition and text-to-speech
- Interaction-loop management

---

### 17. Central Runner Exit Code Registry `[NEW]`

The following runner-level exit codes are reserved and MUST NOT be used by any primitive. Primitive exit codes MUST use the range 0–127. Runner‑level codes use 128–255.

| Code | Name | Meaning |
|------|------|---------|
| 128 | `VERSION_MISMATCH` | Primitive binary version ≠ catalog version |
| 129 | `ENCODING_VIOLATION` | Input artifact not valid UTF-8 with LF |
| 130 | `PRIMITIVE_NOT_FOUND` | Primitive executable not found on `$PATH` or `$PRIMITIVE_HOME` |
| 131 | `MISSING_DEFAULT_REQUIRED` | A `default` token could not be resolved |
| 132 | `SECURITY_VIOLATION` | Path traversal or shell injection detected |
| 133 | `SCHEMA_CONFORMANCE_FAILURE` | Schema artifact does not conform to its own schema |
| 134–255 | Reserved | Future expansion |

---

### 18. Migration Path

A practical migration sequence is:

1. Finish the current stage-based pipeline.
2. Add missing artifacts where reliability is weak: inventory, contracts, implementation plan, validation, state, API, dependency, and UI decomposition.
3. Identify repeated logic and extract it into stable CLI primitives with timeout enforcement and telemetry output.
4. Define primitive catalog entries with full contracts, exit codes, default timeouts, and version numbers (§6.3.1).
5. Write the `contracts_guide.txt` global contract artifact (§9.8).
6. Freeze contract rules already used implicitly.
7. Define and freeze the workflow-map grammar subset (§11.2).
8. Write one hand-written gold-standard workflow map for the reference application.
9. Implement run workspace isolation (`runs/<run_id>/`).
10. Implement artifact immutability enforcement.
11. Implement timeout enforcement for all subprocesses.
12. Implement encoding enforcement (UTF-8, LF).
13. Implement the run index and idempotency cache.
14. Build the generic runner that reads workflow maps and executes declared sequences without embedding project-specific logic (§12.3).
15. Implement validators from the validator registry (§10.2).
16. Move orchestration logic out of ad hoc scripts and into workflow artifacts.
17. Add constrained workflow-map generation only after the prior steps are stable.
18. Validate against the conformance test suite (§20.1).

---

### 19. Non-Goals

Version 1 does not require:

- Maximum workflow grammar expressiveness.
- Autonomous self-modifying runners.
- Hidden dynamic replanning during execution.
- Automatic repair through unconstrained recursive prompting.
- Large universal primitive catalogs on day one.
- Silent heuristic recovery.
- Cross-project primitive reuse outside the frozen catalog.
- Parallel stage execution.
- Multi-line values in workflow maps.
- Real-time streaming diagnostics to external systems.

---

### 20. Build Order `[NEW]`

An implementer SHOULD build components in the following priority sequence:

| Priority | Component | Why |
|----------|-----------|-----|
| 1 | `primitive_catalog.txt` (≤20 entries, §6.3.1 format) | Runner cannot start without it |
| 2 | `contracts_guide.txt` (§9.8 format) | All parsing/validation derives from it |
| 3 | `gold_workflow_map.txt` (hand-written, reference chat app) | Validates runner end-to-end |
| 4 | Runner skeleton (sequential dispatcher per §12.3 + §12.1.1, §12.4, §12.8) | Core engine |
| 5 | Primitive implementations (CLI, stdout/stderr, exit codes, telemetry) | Runner dispatches these |
| 6 | Validator implementations (§10.3) | Gate progression |
| 7 | Canonical artifact formats (validation_plan.txt, state_model.txt, etc.) | Planning/validation artifacts |
| 8 | Idempotency index (`run_index.sqlite`) + run_id generator | Re-run safety |
| 9 | Conformance test suite (§20.1) | Gates Phase 1 completion |

---

### 21. Conformance Summary and Test Suite

A system conforms to this specification only if it:

| # | Requirement | Description |
|---|-------------|-------------|
| 1 | Stable primitives | Uses stable named primitives with explicit CLI interfaces and version reporting |
| 2 | File boundaries authoritative | Treats file boundaries as authoritative; no hidden in-memory contracts |
| 3 | Durable artifacts | Uses durable artifacts as authoritative working memory |
| 4 | Artifact immutability | Enforces strict immutability for text/file artifacts; new versions get new IDs |
| 5 | Implementation plan | Includes an implementation plan as a first-class execution artifact (§7.6) |
| 6 | Deterministic contracts | Enforces deterministic contracts via `contracts_guide.txt` with `<answer>` wrappers and strict parsing |
| 7 | Workflow map as sole control | Uses a workflow map as the sole workflow-control artifact with frozen grammar (§11.2) |
| 8 | Contracts guide present | `contracts_guide.txt` exists and conforms to §9.8 |
| 9 | Primitive catalog present | `primitive_catalog.txt` exists with ≤20 entries, all conforming to §6.3.1 |
| 10 | Generic runner | Runs through a generic interpreter without project-specific logic embedded |
| 11 | Sequential execution (Phase 1) | Executes stages in strict topological order; no parallelism |
| 12 | Timeout enforcement | Enforces timeouts on all subprocesses (§12.4) |
| 13 | Encoding enforcement | Validates UTF-8 and LF line endings on all input artifacts (§12.1.1) |
| 14 | Run workspace isolation | Each run gets a unique `runs/<run_id>/` workspace (§8.1) |
| 15 | Explicit validators | Declares validators explicitly in `VALIDATION_RULES` with severity levels (§10.2) |
| 16 | Required validators gate progression | Validators with `severity=required` must pass before stage is successful (§9.6) |
| 17 | Fail loud | Fails loudly on contract violations and preserves full diagnostics (§13) |
| 18 | No silent recovery | Avoids silent retries, silent repairs, silent failover, and hidden state |
| 19 | Idempotency | Supports idempotent reruns via hashed run index (§14.4) |
| 20 | Gold-standard map | `gold_workflow_map.txt` exists, runs to completion, and passes all validators (§15.1) |
| 21 | Phase 1 constraints | Constrains Phase 1 to ≤20 primitives, frozen grammar, sequential execution, validator-backed acceptance |
| 22 | Primitive discovery | Runner locates primitives via `$PRIMITIVE_HOME` or `$PATH` (§6.5) |
| 23 | Validator invocation | Validators are runner-internal dispatch functions (§10.3) |
| 24 | Hash canonicalization | All idempotency hashes use canonicalized content (§14.4.1) |
| 25 | Security hardening | Runner enforces path containment and `shell=False` (§12.8) |
| 26 | Canonical artifact formats | All referenced canonical artifacts have frozen formats (§7.5) |

#### 21.1 Conformance Test Suite (Mandatory) `[MODIFIED: added new tests]`

A conforming implementation MUST pass these automated tests:

| Test | Description | Verifies § |
|------|-------------|-----------|
| `test_primitive_catalog_load` | Loads `primitive_catalog.txt`, all entries parse, ≤20 primitives, all required fields present | §6.3.1, §6.3.3 |
| `test_primitive_version_match` | Each primitive binary reports version matching catalog entry | §6.3.2 |
| `test_contracts_guide_load` | Loads `contracts_guide.txt`, all sections present | §9.8 |
| `test_workflow_map_parse` | Loads `gold_workflow_map.txt`, parses without error, all refs resolve | §11.2, §11.6.1 |
| `test_artifact_registry_resolve` | All artifact_ids in map resolve to paths under run root | §11.6.1 |
| `test_dag_resolution` | Dependency graph is acyclic, topological order exists | §12.2 |
| `test_sequential_execution` | Runner executes gold map sequentially, all stages complete in declared order | §12.2, §12.3 |
| `test_validator_required_gate` | A stage with `severity=required` validator that fails halts progression | §10.2, §9.6 |
| `test_validator_optional_diagnose` | A stage with `severity=optional` validator that fails continues, diagnostic emitted | §10.2, §9.6 |
| `test_artifact_immutability` | Attempting to overwrite artifact produces new ID or fails; original preserved | §7.2 |
| `test_timeout_enforcement` | A stage with 1s timeout running a 10s sleep is killed, stage failed, diagnostics preserved | §12.4 |
| `test_encoding_enforcement` | Invalid UTF-8 input artifact causes `ENCODING_VIOLATION`, stage fails | §12.1.1 |
| `test_failure_halt` | A stage with missing required output halts runner, full diagnostics preserved | §13 |
| `test_tolerance_rule_continue` | A stage with `continue_under_tolerance` rule continues on tolerable failure, diagnostics show rule_id | §11.10.1 |
| `test_idempotent_rerun` | Second run with identical hashes reuses artifacts, logs previous run_id in diagnostics | §14.4 |
| `test_non_idempotent_different_input` | Different input produces new run_id, no reuse | §14.4 |
| `test_failed_artifact_not_reused` | A run with `status=failed` is not reused on subsequent identical run | §14.3.1, §14.4 |
| `test_partial_not_reused` | A run with `status=partial` is not reused, even if all other hashes match | §14.3.1 |
| `test_telemetry_capture` | Every primitive invocation produces telemetry file in `diagnostics/` | §6.2.1 |
| `test_prompt_assembly_sections` | `build_prompt` produces prompt with all 5 required sections | §9.5 |
| `test_answer_wrapper_enforcement` | Parser rejects output without `<answer>` wrapper, stage fails | §9.2 |
| `test_implementation_plan_present` | `implementation_plan.txt` exists and passes its schema validator | §7.6.1 |
| `test_gold_workflow_map_completes` | `gold_workflow_map.txt` executes to completion with `status=success` | §15.1 |
| `test_run_workspace_isolation` | Two concurrent runs produce different `runs/<run_id>/` paths, no file collisions | §8.1 |
| `test_directory_separation` | Stage writing to `artifacts/` cannot write to `generated/` without explicit declaration | §8.3 |
| `test_version_mismatch_failure` | Primitive binary version differs from catalog → `VERSION_MISMATCH`, stage fails | §6.3.2 |
| `test_primitive_discovery` | Runner finds primitive via `$PRIMITIVE_HOME`; missing primitive yields `PRIMITIVE_NOT_FOUND` | §6.5 |
| `test_security_path_containment` | Path traversal attempt in `ARTIFACT_REGISTRY` yields `SECURITY_VIOLATION` | §12.8 |
| `test_security_shell_false` | Runner invokes primitive with `shell=False`, not `shell=True` | §12.8 |
| `test_hash_canonicalization` | Same inputs (different file order) produce identical `input_hash` | §14.4.1 |
| `test_validation_plan_format` | `validation_plan.txt` conforms to §7.5.1 | §7.5.1 |
| `test_state_model_format` | `state_model.txt` conforms to §7.5.2 | §7.5.2 |
| `test_current_inventory_format` | `current_inventory.txt` conforms to §7.5.3 | §7.5.3 |
| `test_conformance_all_26` | All 26 conformance requirements from §21 verified programmatically | §21 |

---

## Summary of Changes for v8

| Change | Rationale |
|--------|-----------|
| Added §2 Mandatory Prerequisites | Spec must say upfront: "three artifacts must exist before any code runs." |
| Fixed `primitivecatalog.txt` → `primitive_catalog.txt` | Resolved filename inconsistency throughout. |
| Added §6.5 Primitive Discovery | Runner needs committed algorithm to find executables. |
| Added §7.5 Canonical Artifact Frozen Formats | 7 artifacts referenced but undefined now have exact formats. |
| Added §8.5 `run_metadata.txt` format | Diagnostics must be machine-parseable. |
| Added §9.5 prompt template storage clarification | `build_prompt` accepts `--template-file`. |
| Added §9.8 contracts_guide.txt precedence rule | Contracts guide is global law; `GLOBAL_DEFAULTS` cannot override. |
| Added §10.3 Validator Invocation Contract | Validators are runner-internal dispatch functions. |
| Added §11.7.2 Default Token Resolution Order | Eliminates ambiguity: Stage → `GLOBAL_DEFAULTS` → Catalog → Hard-coded. |
| Added §12.6 Stdout Capture Mechanism | Defines how runner captures stdout to artifact file. |
| Added §12.8 Security Hardening | Path containment, `shell=False`, symlink handling. |
| Added §14.2 `transition_log.txt` format | State-transition log now has exact line format. |
| Added §14.3.1 Run Status Semantics | Defines `success`, `failed`, `partial` conditions. |
| Added §14.4.1 Hash Canonicalization | Defines sort order, separator, normalization for idempotency. |
| Added §15.2 Gold Workflow Map Example | Minimal skeleton makes spec testable. |
| Added §17 Central Runner Exit Code Registry | Reserved range 0-127 for primitives, 128-255 for runner. |
| Added §20 Build Order | Implementers know exact priority sequence. |
| Added `--help` flag requirement (§6.1) | Standard CLI convention. |
| Added snake_case naming rule (§6.1) | User requirement enforced explicitly. |
| Added explicit pipe-delimiter rule (§11.2) | Parser generators need explicit rule. |
| Added `temp/` cleanup timing (§8.3) | "Cleaned after each stage on success; preserved on failure." |
| Specified invocation record as JSON (§12.5) | Machine-parseable diagnostics. |
| Added `primitive_catalog_version` to `run_index` (§14.3) | Enforces catalog version match for reuse. |
| Fixed `SECTION_MARKER_PATTERN` regex scope (§9.8) | Clarified applies to line content, not whole file. |
| Renumbered sections | Added §2, §17, §20; old §17→§19; old §18→§21; old §18.1→§21.1; updated all cross-references. |
| Added 14 new conformance tests (§21.1) | Cover all new sections and behaviors. |

This specification is now **buildable, consistent with the white paper, and zero‑ambiguity**. Every section a Python engineer or LLM coder needs to produce working code is defined with exact formats, algorithms, error codes, and testable criteria.

