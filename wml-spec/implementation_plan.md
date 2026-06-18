# Fixed Implementation Plan

**Version 2.0.0 — Spec-Compliant**

---

## Executive Summary

This plan implements the primitive-driven architecture defined in the White Paper, Technical Specification v8, and Addendum. The system has three independently invocable wrapper layers:

```
pipeline tranche → pipeline iterate → pipeline run
```

All three layers normalize input at the boundary (defensive cleaning), produce explicit artifacts, and require no knowledge of layers above them.

---

## Phase 0: Prerequisites (Must Exist Before Any Code)

### Three Mandatory Artifacts

| Artifact | Format | Location |
|----------|--------|----------|
| `primitive_catalog.txt` | §6.3.1 — ≤20 primitives | `catalogs/primitive_catalog.txt` |
| `contracts_guide.txt` | §9.8 — all sections | `catalogs/contracts_guide.txt` |
| `gold_workflow_map.txt` | §11.7.1 — parser-validated | `maps/gold_workflow_map.txt` |

### Seven Canonical Schemas

| Artifact | Format | Location |
|----------|--------|----------|
| `validation_plan.txt` | §7.5.1 | `schemas/validation_plan.txt` |
| `state_model.txt` | §7.5.2 | `schemas/state_model.txt` |
| `current_inventory.txt` | §7.5.3 | `schemas/current_inventory.txt` |
| `api_contracts.txt` | §7.5.4 | `schemas/api_contracts.txt` |
| `ui_decomposition.txt` | §7.5.5 | `schemas/ui_decomposition.txt` |
| `reference_app_spec.txt` | §7.5.6 | `schemas/reference_app_spec.txt` |
| `workflow_map_schema.txt` | §7.5.7 | `schemas/workflow_map_schema.txt` |

---

## Phase 1: Core Pipeline (The Narrow Path)

### Primitive Catalog (15 Entries)

All primitives use `snake_case`, accept `--help`, `--version`, and `--telemetry-file`.

| # | Primitive | Class | Input Contract | Output Contract | Timeout |
|---|-----------|-------|----------------|-----------------|---------|
| 1 | `read_file` | File & Text | `file_path` | `text_artifact` | 10s |
| 2 | `write_file` | File & Text | `text_artifact` | `file_path` | 10s |
| 3 | `chunk_text` | File & Text | `text_artifact` | `chunk_list` | 10s |
| 4 | `detect_encoding` | File & Text | `file_path` | `encoding_info` | 5s |
| 5 | `build_prompt` | Prompt | `prompt_template` | `prompt_artifact` | 5s |
| 6 | `call_llm` | LLM | `prompt_artifact` | `raw_llm_reply` | 180s |
| 7 | `extract_answer` | Extraction | `raw_llm_reply` | `extracted_answer` | 10s |
| 8 | `validate_contract` | Validation | `any_artifact` | `validation_report` | 10s |
| 9 | `init_sqlite` | SQLite | `sqlite_schema` | `sqlite_db` | 30s |
| 10 | `query_sqlite` | SQLite | `sqlite_db` | `query_result` | 30s |
| 11 | `upsert_sqlite` | SQLite | `sqlite_db` | `upsert_result` | 30s |
| 12 | `sync_sqlite` | SQLite | `sqlite_db` | `sync_result` | 10s |
| 13 | `export_assets` | Export | `generated_artifacts` | `export_report` | 60s |
| 14 | `render_ui` | Export | `ui_decomposition` | `ui_assets` | 60s |
| 15 | `compile_app` | Export | `implementation_plan` | `app_bundle` | 60s |

### Project Structure

```
pipeline/
├── runner/
│   ├── __init__.py
│   ├── main.py              # CLI: pipeline run (--iteration, --skip-cleanup)
│   ├── parser.py             # §11.2 workflow map parser
│   ├── executor.py            # §12.3 sequential executor
│   ├── validator_dispatch.py  # §10.3 validator implementations
│   ├── artifact_registry.py   # §11.6.1 path resolver
│   ├── run_workspace.py       # §8.1 workspace creation
│   ├── idempotency.py         # §14.3-14.4 run index + §14.4.1 canonicalization
│   ├── security.py            # §12.8 path containment, shell=False
│   └── telemetry.py           # §6.2.1 invocation records
├── primitives/                # 15 standalone executables
├── contracts/
│   ├── contracts_guide.txt    # §9.8
│   └── schemas/               # §7.5 frozen formats
├── maps/
│   ├── gold_workflow_map.txt  # Phase 0 reference map
│   └── templates/             # Phase 2+ map templates
├── artifacts/                 # §6.2.1 global standards
├── tests/
│   ├── conformance/           # §21.1 test suite
│   └── fixtures/
└── pyproject.toml
```

### Gold Workflow Map (Spec-Compliant)

```text
WORKFLOW_METADATA
  WORKFLOW_ID: reference_chat_app
  WORKFLOW_NAME: reference_chat_app
  WORKFLOW_VERSION: 1.0.0
  REFERENCE_APP: local_chat
  AUTHOR: pipeline_implementation_plan
  CREATED: 2026-06-18

GLOBAL_DEFAULTS
  ENCODING: utf-8
  LINE_ENDING: lf
  TIMEOUT: 180
  WORKING_DIR: default

ARTIFACT_REGISTRY
  ARTIFACT soc_raw | soc_raw.txt | input | artifacts/soc_raw.txt | external | stage_clean | none | temporary
  ARTIFACT soc_clean | soc_clean.txt | intermediate | artifacts/soc_clean.txt | stage_clean | stage_inventory | validator_soc_clean_presence | persistent
  ARTIFACT cleanup_log | cleanup_log.txt | diagnostic | artifacts/cleanup_log.txt | stage_clean | none | none | persistent
  ARTIFACT current_inventory | current_inventory.txt | intermediate | artifacts/current_inventory.txt | stage_inventory | stage_brainstorm | validator_inventory_keys | persistent
  ARTIFACT variation_set | variation_set.txt | intermediate | artifacts/variation_set.txt | stage_brainstorm | stage_critic | validator_variation_nonempty | persistent
  ARTIFACT intent | intent.txt | intermediate | artifacts/intent.txt | stage_clean | stage_critic; stage_consensus | validator_intent_presence | persistent
  ARTIFACT critique | critique.txt | intermediate | artifacts/critique.txt | stage_critic | stage_consensus | validator_critique_answer_wrapper | persistent
  ARTIFACT consensus | consensus.txt | intermediate | artifacts/consensus.txt | stage_consensus | stage_compile | validator_consensus_nonempty; validator_answer_wrapper | persistent
  ARTIFACT implementation_plan | implementation_plan.txt | intermediate | artifacts/implementation_plan.txt | stage_compile | stage_build | validator_plan_schema | persistent
  ARTIFACT impl_plan_schema | implementation_plan_schema.txt | schema | schemas/implementation_plan_schema.txt | external | none | none | persistent
  ARTIFACT generated_app | generated/ | output | generated/ | stage_build | stage_test; stage_export | validator_generated_presence | deliverable
  ARTIFACT test_report | test_report.txt | output | artifacts/test_report.txt | stage_test | stage_export | validator_test_report | persistent
  ARTIFACT final_output | final_output/ | output | generated/final_output/ | stage_export | none | validator_export_success | deliverable

STAGES
  STAGE stage_clean
    EPISTEMIC_TYPE: normalization
    NAME: Clean Input
    PRIMITIVE: call_llm
    INPUTS: soc_raw
    OUTPUTS: soc_clean; cleanup_log; intent
    DEPENDS_ON: none
    VALIDATORS: validator_soc_clean_presence
    FAILURE_POLICY: halt
    RETRY_POLICY: none
    TIMEOUT: 180
    WORKING_DIR: default

  STAGE stage_inventory
    EPISTEMIC_TYPE: normalization
    NAME: Load Current State
    PRIMITIVE: call_llm
    INPUTS: soc_clean
    OUTPUTS: current_inventory
    DEPENDS_ON: stage_clean
    VALIDATORS: validator_inventory_keys
    FAILURE_POLICY: halt
    RETRY_POLICY: none
    TIMEOUT: 180
    WORKING_DIR: default

  STAGE stage_brainstorm
    EPISTEMIC_TYPE: generation
    NAME: Generate Variations
    PRIMITIVE: call_llm
    INPUTS: current_inventory
    OUTPUTS: variation_set
    DEPENDS_ON: stage_inventory
    VALIDATORS: validator_variation_nonempty
    FAILURE_POLICY: halt
    RETRY_POLICY: none
    TIMEOUT: 180
    WORKING_DIR: default

  STAGE stage_critic
    EPISTEMIC_TYPE: evaluation
    NAME: Evaluate Variations
    PRIMITIVE: call_llm
    INPUTS: variation_set; intent
    OUTPUTS: critique
    DEPENDS_ON: stage_brainstorm
    VALIDATORS: validator_critique_answer_wrapper
    FAILURE_POLICY: halt
    RETRY_POLICY: none
    TIMEOUT: 180
    WORKING_DIR: default

  STAGE stage_consensus
    EPISTEMIC_TYPE: synthesis
    NAME: Merge Perspectives
    PRIMITIVE: call_llm
    INPUTS: critique; intent
    OUTPUTS: consensus
    DEPENDS_ON: stage_critic
    VALIDATORS: validator_consensus_nonempty; validator_answer_wrapper
    FAILURE_POLICY: halt
    RETRY_POLICY: none
    TIMEOUT: 180
    WORKING_DIR: default

  STAGE stage_compile
    EPISTEMIC_TYPE: generation
    NAME: Create Implementation Plan
    PRIMITIVE: call_llm
    INPUTS: consensus
    OUTPUTS: implementation_plan
    DEPENDS_ON: stage_consensus
    VALIDATORS: validator_plan_schema
    FAILURE_POLICY: halt
    RETRY_POLICY: none
    TIMEOUT: 180
    WORKING_DIR: default

  STAGE stage_build
    EPISTEMIC_TYPE: generation
    NAME: Build Application
    PRIMITIVE: compile_app
    INPUTS: implementation_plan
    OUTPUTS: generated_app
    DEPENDS_ON: stage_compile
    VALIDATORS: validator_generated_presence
    FAILURE_POLICY: halt
    RETRY_POLICY: none
    TIMEOUT: 60
    WORKING_DIR: default

  STAGE stage_test
    EPISTEMIC_TYPE: evaluation
    NAME: Run Tests
    PRIMITIVE: call_llm
    INPUTS: generated_app
    OUTPUTS: test_report
    DEPENDS_ON: stage_build
    VALIDATORS: validator_test_report
    FAILURE_POLICY: halt
    RETRY_POLICY: none
    TIMEOUT: 180
    WORKING_DIR: default

  STAGE stage_export
    EPISTEMIC_TYPE: additive
    NAME: Package Deliverables
    PRIMITIVE: export_assets
    INPUTS: test_report; generated_app
    OUTPUTS: final_output
    DEPENDS_ON: stage_test
    VALIDATORS: validator_export_success
    FAILURE_POLICY: halt
    RETRY_POLICY: none
    TIMEOUT: 60
    WORKING_DIR: default

EXECUTION_RULES
  ORDER: sequential
  MAX_PARALLEL: 1
  REFINEMENT_LOOP:
    ENTRY_STAGE: stage_brainstorm
    EXIT_STAGE: stage_consensus
    MAX_PASSES: 5
    CONVERGENCE_CHECK: hash

VALIDATION_RULES
  VALIDATOR validator_soc_clean_presence | file_presence | soc_clean | empty | required
  VALIDATOR validator_inventory_keys | required_keys | current_inventory | missing:primitives,schemas,api,ui | required
  VALIDATOR validator_variation_nonempty | file_presence | variation_set | empty | required
  VALIDATOR validator_critique_answer_wrapper | answer_block | critique | missing_answer_wrapper | required
  VALIDATOR validator_consensus_nonempty | file_presence | consensus | empty | required
  VALIDATOR validator_answer_wrapper | answer_block | consensus | missing_answer_wrapper | required
  VALIDATOR validator_intent_presence | file_presence | intent | empty | required
  VALIDATOR validator_plan_schema | schema_conformance | implementation_plan | implementation_plan_schema | required
  VALIDATOR validator_generated_presence | file_presence | generated_app | empty | required
  VALIDATOR validator_test_report | file_presence | test_report | empty | required
  VALIDATOR validator_export_success | file_presence | final_output | empty | required

FAILURE_RULES
  halt
```

---

## Phase 2: Wrapper Layers

### `pipeline iterate` — Multi-Pass Refinement

```bash
pipeline iterate \
    --map <workflow_map.txt> \
    --request <request_text_or_file> \
    --input-folder <path> \
    --max-iterations <N> \
    [--convergence-check <hash|llm>] \
    [--skip-cleanup]
```

**Behavior:**
1. Call `pipeline run` for iteration 1 through N.
2. After each run, assemble `previous_attempt` from key artifacts in `generated/`.
3. If `--convergence-check hash`: compare output hashes → stop if identical.
4. If `--convergence-check llm`: ask model "has this converged?" → stop if yes.
5. Persist `refinement_state.json` for each iteration.
6. Artifact paths include iteration number (e.g., `artifacts/v2/`).

### `pipeline tranche` — SOC Burst into Phases

```bash
pipeline tranche \
    --soc-file <stream_of_consciousness.txt> \
    --map <workflow_map.txt> \
    --input-folder <path> \
    [--max-iterations <N>] \
    [--skip-cleanup]
```

**Behavior:**
1. Read SOC file.
2. Call `call_llm`: "Break this into ordered delivery phases."
3. Write `artifacts/tranche_plan.json`.
4. For each phase: construct focused request → call `pipeline iterate` → copy generated code to next phase input.

---

## Phase 3: Profiling Primitives (Addendum §2.2)

| Primitive | Inputs | Outputs | Description |
|-----------|--------|---------|-------------|
| `scan_folder` | folder_path, exclude_patterns | file_paths (list) | Recursively discover all files |
| `profile_file` | file_path | file_hash, size, line_count, extension | Compute basic file metadata |
| `summarize_file` | file_path, system_prompt | summary_text | LLM-generated summary |
| `compute_embedding` | text_string, model_name | embedding_vector (float list) | Sentence-transformer embedding |
| `chunk_file` | file_path, chunk_size | chunks (list) | Split file into contiguous chunks |
| `summarize_chunk` | chunk_text | summary_text | LLM summary of chunk |
| `store_profile_sqlite` | profile_data, db_path | db_updated (bool) | Upsert into SQLite profile DB |
| `incremental_scan` | folder_path, db_path | changed_files, new_files | Compare hashes, return changes |
| `retrieve_similar` | query_embedding, db_path, top_k | ranked_results | Cosine similarity search |
| `plan_changes` | request_text, relevant_contexts | change_plan (JSON) | LLM proposes specific changes |
| `apply_change` | change_plan, source_folder | updated_files | Apply planned edits |
| `analyze_wishlist` | soc_text, system_prompt | tranche_plan (JSON) | Burst wish list into phases |

---

## Build Order (Spec §20)

| Priority | Component | Why |
|----------|-----------|-----|
| 1 | `primitive_catalog.txt` (≤20 entries, §6.3.1) | Runner cannot start without it |
| 2 | `contracts_guide.txt` (§9.8) | All parsing/validation derives from it |
| 3 | `gold_workflow_map.txt` (hand-written, reference chat app) | Validates runner end-to-end |
| 4 | Runner skeleton (sequential dispatcher per §12.3) | Core engine |
| 5 | 15 primitive implementations (CLI, stdout/stderr, exit codes) | Runner dispatches these |
| 6 | Validator implementations (§10.3) | Gate progression |
| 7 | Canonical artifact formats (validation_plan.txt, state_model.txt) | Planning/validation artifacts |
| 8 | Idempotency index (`run_index.sqlite`) + run_id generator | Re-run safety |
| 9 | Conformance test suite (§21.1) | Gates Phase 1 completion |

---

## Exit Criteria

1. `primitive_catalog.txt` exists with ≤15 entries, all parsable
2. `contracts_guide.txt` exists with all required sections
3. `gold_workflow_map.txt` executes to `status=success`
4. All 39 conformance tests pass
5. Reference chat application generated end-to-end
6. All wrapper layers independently invocable