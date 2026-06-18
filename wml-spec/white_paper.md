\# Beyond Prompting: A Primitive-Driven Architecture for Reliable AI Software Generation



\## Author intent



This paper describes an architecture in which most software generation is reduced to composing a small canonical set of reusable command-line primitives through deterministic plain-text workflow maps, with custom coding reserved for the minority of truly application-specific logic.



AI software generation is not failing primarily because models are too weak. It is failing because the systems around them are too loose, too improvised, and too eager to regenerate infrastructure that should already exist. The path to reliability is not a bigger prompt or a more theatrical agent loop. It is a small, stable architecture built from reusable primitives, explicit contracts, durable artifacts, and a workflow map that plugs the pieces together.



This paper argues for a minimal architecture with as few moving parts as possible. The goal is not to create the most general or most autonomous system. The goal is to create the fastest path to a stable system that can be assembled quickly, understood easily, debugged locally, restarted safely, and extended without rethinking everything from scratch.



The central design priority is straightforward: stable primitives first, contracts second, workflow control third, custom logic last. That order is the difference between a reusable build system and a prompt-driven improvisation machine.



\## The real problem



Most AI coding systems still make the same mistake. They ask the model to act as planner, parser, interface designer, state manager, code generator, repair loop, and orchestrator all at once. That mixes too many responsibilities into a single interaction and leaves too much of the system hidden in transient prompt behavior, invisible memory, undocumented tool assumptions, and operator habit.



The result is familiar. Infrastructure is regenerated from scratch. Output shapes drift because contracts are weak, implied, or underspecified. Parsing becomes brittle because the format was never frozen. Failures become hard to diagnose because important state lives in prompts, temporary files, tool behavior, or unwritten conventions rather than in visible artifacts.



A recurring lesson from implementation is that many failures are not deep failures of reasoning. They are boring failures of structure. A wrapper is missing. A section name drifts. A key-value shape changes. A required file is not produced. A validator has no clear place to run. That is not a model problem first. It is an architecture problem first.



The core claim of this paper is that a large share of software generation can be made more reliable by reducing it to a canonical catalog of reusable primitives, deterministic file-based contracts between stages, artifact-first planning and execution, a workflow map that wires primitives together, and limited custom code only for the truly application-specific remainder.



For a broad class of applications, most of the implementation effort can be represented as compositions of small, highly reusable CLI primitives. Application generation then becomes primarily a matter of identifying required artifacts, selecting the right primitive sequence, defining clear hand-offs, and generating or refining the remaining custom edge logic.



\## The architectural shift



The simplest reliable architecture is not built around one grand agent. It is built around a small toolchest of atomic command-line primitives and a map that composes them. Repeated infrastructure should be stabilized once and then reused, not regenerated every time a new application is requested.



This changes what the model is for. The model stops serving as planner, parser, repair engine, interface contract manager, and orchestration substrate all at once. Instead, it becomes one bounded component inside a larger system whose rules exist outside the model and survive across runs.



That is the architectural shift: stop generating infrastructure repeatedly, and start composing stable infrastructure deliberately.



\## Stable primitives first



The first priority is to define and build the primitive catalog before trying to build a sophisticated pipeline. The catalog should be treated as a parts library of durable components, not as an aspirational note file.



Each primitive should obey a few hard rules. It should do one clear job. It should expose a simple CLI. It should use explicit inputs and outputs, preferably file-based. It should fail loudly on malformed required inputs. It should keep a stable name over time rather than being renamed for cosmetic reasons.



As much as possible, every step, every task, and every transformation should be a CLI. Each primitive should take explicit input files and produce explicit output files. Hidden in-memory hand-offs should be treated as exceptions, not defaults.



This matters because most software generation repeatedly needs the same kinds of operations: reading text safely, writing files deterministically, detecting encoding, assembling prompts, calling an LLM, extracting an answer block, validating output shape, initializing SQLite, querying SQLite, exporting generated assets, rendering static UI, chunking, and capturing subprocess results. These are recurring infrastructure concerns, not one-off creativity.



A stable pipeline should therefore begin with a minimal useful toolbox, not a maximal one. Too many primitives create noise. Overly broad primitives turn into mini-frameworks. The right balance is a compact set of trusted building blocks that can be recombined across many workflows.



\## Artifacts as working memory



A stable pipeline needs durable artifacts, not hidden state. Intermediate outputs should be treated as visible working memory for the system.



These artifacts are not clutter. They are how the system remembers itself. They ground planning in the real present system, define contracts between stages, describe the target application and implementation path, and control execution, validation, and recovery.



A useful artifact family includes source inputs, schema artifacts, instance artifacts, workflow maps, implementation plans, validation plans, state-transition definitions, API contracts, dependency requirements, UI decomposition, concrete state models such as SQLite schemas, canonical outputs, diagnostics, and materialized deliverables. In practice, this often means concrete artifacts such as `currentinventory.txt`, `primitivecatalog.txt`, `contractsguide.txt`, `workflowmapschema.txt`, `workflowmap.txt`, `referenceappspec.txt`, `implementationplan.txt`, `validationplan.txt`, `apicontracts.txt`, `uidecomposition.txt`, and dependency requirement artifacts.



Not every project needs every artifact on day one. A minimal pipeline should start with only the artifacts necessary to keep control visible and hand-offs reliable. More artifacts should be added when they solve a real failure mode, not because they sound comprehensive.



One distinction matters especially: schema artifacts are not instance artifacts. Schema artifacts define the allowed shape of a document family and are reused across projects. Instance artifacts are project-specific documents written in those grammars. Without that distinction, each run quietly invents its own language.



One artifact deserves special emphasis: the implementation plan. It is the bridge between abstract architecture and actual code production. Without that bridge, an architecture can remain conceptually sound while still failing to produce a clear build order, file layout, and execution sequence.



\## Contracts second



After primitives, the next thing to stabilize is the contract layer. Without frozen contracts, a pipeline cannot trust its own parts.



Every stage must have explicit inputs and outputs. File boundaries are authoritative. Hidden in-memory contracts between stages are prohibited. Machine-consumable outputs must be deterministic and parseable. If a required contract is violated, the stage must fail loudly.



This means wrapper rules, section markers, key-value parsing rules, naming rules, validation rules, and failure policy should be treated as global law. A stage should succeed because it produced the exact declared artifact in the exact declared shape, not because a later stage managed to guess what it probably meant.



Parsers validate, extract, and stop. They do not guess. They do not reinterpret. They do not silently repair malformed output. If a contract fails, the system should preserve the raw reply, preserve the extracted partial artifact if one exists, write validation diagnostics, write execution diagnostics, and halt progression.



Required validations must run before progression. Missing required sections, missing answer blocks, empty critical artifacts, database write failures, missing required files, and nonzero subprocess exits should stop the stage and preserve diagnostics unless an explicit tolerance rule has been declared.



Human readers can often infer intent from malformed output. Pipelines should not have to.



\## Workflow control third



Once primitives exist and contracts are frozen, workflow control can be made explicit and minimal. The workflow map should be the single place where stage order, dependencies, inputs, outputs, validators, retries, and failure policy are declared.



This principle matters because control logic has a tendency to leak. It drifts into prompt wording, shell glue, operator habit, helper scripts, and undocumented conventions. That drift is one of the fastest ways for an apparently structured system to collapse back into improvisation.



A valid workflow map should define workflow metadata, global defaults, an artifact registry, stage declarations, execution rules, validation rules, and failure rules. The interpreter should read the map, verify prerequisites, run the declared primitive, validate the output, record diagnostics, and either advance or halt.



The workflow map is the assembly board of the system. The primitives are the parts. The map is how the parts get plugged together. The runner should remain generic. Project-specific logic should not be embedded in the runner itself.



\## The layer model



The architecture works best when organized into four layers.



Layer 0 contains substrate primitives. These are low-level operational tools for file detection, encoding checks, safe reads and writes, directory creation, subprocess execution, hashing, metadata generation, and deterministic capture of stdout, stderr, and exit codes. They are not glamorous, but they eliminate recurring low-level failure classes.



Layer 1 contains atomic application primitives. These are the reusable building blocks that appear across many workflows: prompt assembly, LLM calls, answer extraction, answer validation, critique, revision from feedback, SQLite initialization, query and update operations, export helpers, retrieval helpers, and app-assembly utilities. They should be small, stable, independently testable, and exposed through simple CLIs.



Layer 2 contains composition and planning. This layer does not primarily perform transformations itself. It determines how transformations are allowed to happen. It derives workflow maps, assigns artifacts to stages, defines dependencies and stage boundaries, and creates the execution grammar the runner will follow.



Layer 3 contains project-specific custom logic. This is the remaining small percentage of domain rules, unusual integrations, bespoke validation, and application-specific behavior. This layer should stay intentionally small.



When project-specific logic becomes large, it is often a sign that recurring behavior should be extracted downward into more stable primitives, shared artifacts, or explicit contracts. The architecture improves over time not by making prompts larger, but by moving repeated behavior into more stable layers.



\## Execution loop



The architecture is most reliable when execution control is explicit and procedural.



A typical run begins by loading the global standards, including the current inventory, primitive catalog, contracts guide, and relevant schemas. It then loads the project-specific instance artifacts, validates required inputs, reads the workflow map to determine stage order and behavior, checks prerequisite and state-transition rules, runs the declared primitive for each ready stage, validates the outputs, and either advances or stops according to policy.



If validation passes, outputs are persisted and the workflow advances to the next ready state. If validation fails, diagnostics are preserved, the workflow moves to the appropriate failure or recovery state, and execution stops or awaits explicit intervention. This keeps planning, execution, validation, and recovery visible rather than buried in ad hoc control code.



Retries and hill-climbing may still exist, but they must be explicit workflow behavior rather than hidden interpreter behavior.



\## Artifact lifecycle and diagnostics



Reliable generation requires durable operational evidence. Diagnostics are durable artifacts, not console noise.



Each run should preserve run metadata such as timestamp, input snapshot, and prompt or workflow hash. It should preserve raw model outputs when LLM stages are used, extracted machine-readable outputs, validation reports, parse diagnostics, state snapshots or transition logs for blocked or failed workflows, and canonical outputs or materialized deliverables with stable naming rules and clear directory boundaries.



Artifact lifecycle should be explicit. The architecture should preserve raw replies, extracted artifacts, validation reports, diagnostics, and canonical outputs with clear boundaries for temporary artifacts, persistent artifacts, and generated deliverables.



Where practical, the system should support idempotent reruns by recognizing when the same inputs and workflow definition have already produced a valid result. At the same time, stale or failed artifacts should never be silently reused. Reuse should be explicit and reviewable.



A pipeline that cannot explain why it stopped, what it consumed, what it produced, and what contract failed is not yet a serious build system.



\## Why this improves reliability



This architecture improves reliability because it removes repeated infrastructure from the regenerate-everything loop and replaces it with stable reusable parts. It narrows large design problems into smaller auditable steps, strengthens contracts, makes debugging local and inspectable, and makes future applications easier to build because new work becomes composition over tested parts rather than regeneration of the same infrastructure.



It also shrinks the space where the model can hurt the system. Instead of repeatedly asking the model to invent infrastructure, preserve state, repair formatting, and orchestrate execution, the architecture moves those responsibilities into primitives, contracts, artifacts, validators, and workflow declarations that exist outside the model.



This architecture does not remove engineering judgment. It still requires a good primitive catalog, good contract design, and good workflow granularity. Weak decisions can still be operationalized very efficiently. The goal is not to eliminate judgment, but to make the system less dependent on invisible behavior and more dependent on visible structure.



\## Phase 1 constraints



This architecture is most useful when the first implementation is intentionally narrower than the long-term vision. Phase 1 should not optimize for maximum generality. It should optimize for a stable closed world that proves the approach end to end.



That means freezing a deliberately small primitive set rather than exposing the full catalog all at once. It means freezing a constrained subset of the workflow-map grammar even if the full schema allows future expansion. It means providing at least one hand-written gold-standard workflow map for a simple reference application so there is a canonical example of valid composition.



It also means using a constrained map-generation prompt that consumes user intent, the primitive catalog, the contracts guide, the schema rules, and the canonical example, and then emits only valid workflow maps inside that allowed subset. Generated workflows should not be considered runnable until validator-backed acceptance has occurred.



These constraints are not a retreat from the architecture. They are the architecture applied correctly at the start.



\## Minimal viable pipeline



The architecture should favor a minimal end-to-end pipeline before it grows into a larger framework. The first working version does not need every possible primitive or artifact class. It needs a narrow path that can run reliably.



A practical minimal pipeline might include a small Layer 0 file-and-process toolkit, a small Layer 1 LLM toolkit for prompt assembly, model call, answer extraction, and answer validation, a contracts guide that freezes wrappers and fail-loud behavior, a workflow-map schema plus one concrete workflow map, a generic runner that dispatches primitives and stops on failure, and a small diagnostics and provenance trail for each run.



That is enough to prove the architecture. It is also enough to avoid one of the most common traps: building an elaborate orchestration system before the core parts are trustworthy.



\## Recommended migration path



A practical migration path from an existing pipeline is straightforward.



First, complete the current stage-based system and make sure it works end to end. Second, add missing artifacts wherever reliability remains weak, especially in inventory, contracts, validation, state, API, dependency, and interface decomposition. Third, extract repeated logic into stable CLI primitives. Fourth, define and freeze the workflow-map grammar used by the early runner. Fifth, build the abstraction engine as a generic runner that reads workflow maps and executes the declared sequence without embedding project-specific logic. Sixth, add constrained workflow-map generation inside the frozen Phase 1 contract set.



This path matters because the architecture should grow from the real system rather than from a fantasy rewrite.



\## Reference application role



A local chat application is an ideal proof of concept because it exercises several important parts of the architecture at once: user interface rendering, local backend behavior, LLM calls, local speech recognition, optional text-to-speech, persistence, and the user interaction loop. It is complex enough to validate the architecture, but bounded enough to implement.



Its real value is not that it is flashy. Its value is that it tests whether the workflow map, contract system, primitive catalog, artifact family, and diagnostics model actually function together as a coherent build system rather than as disconnected ideas.



\## Risks and cautions



This architecture has real risks. Too many primitives can create noise. Overly broad primitives can become mini-frameworks. Weak contracts can undermine the whole system. Stale inventory can mislead planning. Extra stages can waste cycles. Over-abstraction can slow delivery. A weak workflow-map subset can create the illusion of control while still permitting drift.



A runner that silently retries, silently repairs, or silently guesses can destroy trust even if it occasionally produces useful-looking output. For that reason, the architecture should prefer the smallest primitive set, the smallest stage set, and the smallest rule set that fully solves the current problem while preserving determinism, visibility, and restartability.



\## Build philosophy



The long-term value of this architecture is not that it can generate code from prompts. Many systems can do that. Its value is that it can reduce software generation to explicit composition over stable parts.



Build the smallest stable toolbox first. Freeze the contracts those tools obey. Make the workflow map the only source of orchestration truth. Keep prompts thin. Keep custom logic at the edge. Add artifacts when they clarify control. Add primitives when they eliminate repeated work. Resist hidden retries, vague interfaces, and broad stages that do too much.



The result is a pipeline that is quicker to assemble, easier to inspect, easier to repair, and easier to reuse. It does not depend on the model to remember the system. The system remembers itself.



\## Closing claim



The core question for AI software generation is not whether one model can build one app from one prompt. The better question is how much of the build process can be reduced to explicit composition over stable parts with clear interfaces and visible checkpoints.



The answer proposed here is deliberately modest but powerful: build a stable pipeline from a small toolbox of prebuilt CLI primitives, freeze the contracts those primitives obey, use a workflow map as the single place where those building blocks are plugged together, treat artifacts as visible working memory, and keep custom logic thin and local.



That is the primitive-driven architecture for reliable AI software generation.



The natural next document is the technical specification, where these principles become exact rules for primitive interfaces, contract formats, artifact classes, workflow grammar, validators, and runner behavior.

