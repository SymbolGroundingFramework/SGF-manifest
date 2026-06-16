# Omega Implementers’ Guide v1.0 Final Candidate

File: 03-OMEGA-03_IMPLEMENTERS_GUIDE.md  
Layer: OMEGA (governance grammar)  
Status: Final Candidate

## 0. Relationship to the Omega spec family

This document specifies required static and runtime checks, profile enforcement, determinism, and safety-kernel behavior for Omega evaluators. It must be read together with:

- 03-OMEGA-01_LANGUAGE_SPEC.md (language model and primitives)  
- 03-OMEGA-02_FORMAL_GRAMMAR_SPEC.md (lexical grammar and EBNF)  
- 03-OMEGA-04_EXTENSION_GOVERNANCE.md (extension rules)

## C.1 What an Omega Evaluator Is

An Omega evaluator is a program that loads `.omega` specifications and evaluates proposed actions against them. The evaluator is called the Safety Kernel. Chapter 4 introduced that name and established its role as the canonical runtime: the program that stands between the execution layer and the Omega specification, returning a verdict for every proposed action. This appendix treats the Safety Kernel as the artifact the implementer is building and states precisely what that artifact must do.

The Safety Kernel exposes three operations: LOAD, EVALUATE, and REPORT. LOAD takes a specification and produces a compiled spec object or a structured parse error. EVALUATE takes a proposed action and a current state object and produces a verdict. REPORT defines the structure of that verdict. The three operations are described in full in Section C.2.

The Safety Kernel is profile-aware. A Strict-only implementation rejects Extended Profile constructs at parse time and is not required to load or evaluate them. A full implementation supports both profiles and enforces profile boundaries: Extended constructs that appear in a compilation unit declaring PROFILE Strict are rejected at parse time, not silently ignored. Profile declarations govern what the evaluator accepts; an evaluator that accepts everything regardless of the PROFILE directive is non-conformant.

The Safety Kernel is host-language-agnostic. The choice of implementation language is the implementer's own. The requirements in this appendix are stated in terms of structural behavior. Any language that provides the necessary structural primitives for parsing, tree walking, and predicate evaluation can host a conformant Safety Kernel.

---

## C.2 The Three Operations in Detail

### C.2.1 LOAD

**Input:** a path to a `.omega` file, or an in-memory specification string.

**Output:** a compiled spec object ready for evaluation, or a structured parse error carrying at minimum the line number, column number, and a description of the violation.

**What LOAD must do:**

1. Parse the input against the canonical EBNF in Appendix A Section A.10. Any token sequence that does not conform to the grammar must be rejected immediately. The rejection must be loud: a structured parse error is returned and no spec object is produced. Silent acceptance of malformed input is not permitted.

2. Resolve all named references: RuleIDs, EntityIDs, ContextIDs, ScopeIDs, SchemaIDs, and any other identifier that one part of the specification uses to refer to another. An unresolved reference is a load-time error. The error must identify the reference that could not be resolved and the location in the source where it appeared.

3. Validate cross-references between primitives. Every MUTATION_RULE's TARGET_REFERENCE must point to a SELF_REFERENCE_POINT defined within the loaded spec. Every GOVERNANCE_RULE's ENFORCEMENT_MODE must name a declared enforcement mode or implementation-recognized enforcement-mode identifier valid under the loaded spec, and that mode must resolve to exactly one class: permissive or prohibitive. Every STATE_TRANSITION's GOVERNED_BY must name a GOVERNANCE_RULE defined within the loaded spec. Every LEARNING_AXIOM's KNOWLEDGE_UPDATE_RULE must name a MUTATION_RULE defined within the same module. Cross-reference failures are load-time errors.

4. Perform static profile checks. If the compilation unit declares PROFILE Strict (or omits the PROFILE directive, which defaults to Strict per Appendix A Section A.2.3), the evaluator must reject any LOOP, WHILE, FOR, recursion, mutable state, external I/O, unregistered host call, or user-defined FUNCTION construct that appears inside a policy-evaluation slot. Strict policy slots may call only registered Strict predicate functions that are pure, total over their declared input types, deterministic, side-effect-free, non-recursive, terminating by construction, and limited to declared observation inputs. Profile violations are load-time errors.

5. Verify required-field presence for each primitive. Appendix A Section A.6 specifies which fields are required and which are optional for each of the 13 primitives. A primitive call that omits a required field is a load-time error. A primitive call that includes an unknown field is also a load-time error; the grammar does not admit extension fields at the call site.

6. Detect cycles in the mutation authority graph. Nodes are mutable definitions addressable through SELF_REFERENCE_POINT. A direct edge exists from each MUTATION_RULE to its TARGET_REFERENCE. Derived authority edges include any mutation that can alter another mutation rule, approval policy, trust requirement, target reference, or governing rule. LOAD must reject cycles that allow a mutation path to weaken its own approval policy, expand its own target set, bypass its governing authority, or alter Constitutional targets.

7. Perform type-compatibility checks between PERCEPTION_MAP outputs and the GOVERNANCE_RULE predicates that consume them. If a GOVERNANCE_RULE predicate references a term whose type cannot be established from the available PERCEPTION_MAP output schemas or DATA_TYPE_SCHEMA declarations, that is a load-time error.

8. Resolve host bindings and bounded Extended slots. Every ActionID referenced by STATE_TRANSITION, MUTATION_RULE, or PERCEPTION_MAP must resolve to a host action descriptor or declared abstract action in the conformance environment. Every Extended policy-evaluation slot that uses Extended-only constructs must declare CONSTRAINT_SET, and every entry in that set must resolve to a RESOURCE_BOUND. Unknown action bindings, missing bounds, missing governing rules, undeclared perception outputs, unresolved identifiers, and type incompatibilities are load-time errors, not runtime UNKNOWN cases.

If LOAD succeeds, the resulting compiled spec object is the operand for all subsequent EVALUATE calls. The compiled spec object must be immutable after load. No field in it may be altered at runtime except through a properly authorized MUTATION_RULE invocation under the conditions specified in Section C.5.

### C.2.2 EVALUATE

**Input:** a proposed action descriptor; a current state object supplying the observable state variables available at evaluation time.

**Output:** a verdict object as defined in Section C.2.3.

**What EVALUATE must do:**

1. Match the proposed host action to candidate STATE_TRANSITION definitions by ACTION. If no STATE_TRANSITION matches the proposed host action, the evaluator returns DENY with reason kind no_matching_transition. The Safety Kernel authorizes or refuses host actions; it does not execute physical effects itself.

2. For each candidate STATE_TRANSITION, evaluate PRECONDITION against the current state object. A candidate whose PRECONDITION evaluates FALSE contributes no authorization. A candidate whose PRECONDITION cannot be evaluated because a declared live observation is unavailable contributes UNKNOWN.

3. For each candidate whose PRECONDITION evaluates TRUE, evaluate the GOVERNANCE_RULE named by GOVERNED_BY together with any other GOVERNANCE_RULEs whose SCOPE matches the proposed action.

4. Each evaluated GOVERNANCE_RULE produces a rule contribution according to the following table:

| Condition | Contribution |
|---|---|
| SCOPE does not match | no contribution |
| SCOPE matches and PREDICATE is FALSE | no contribution |
| SCOPE matches, PREDICATE is TRUE, and ENFORCEMENT_MODE class is permissive | ALLOW |
| SCOPE matches, PREDICATE is TRUE, and ENFORCEMENT_MODE class is prohibitive | DENY |
| SCOPE matches and a declared runtime observation is unavailable | UNKNOWN |
| SCOPE matches and Extended evaluation exceeds a governing RESOURCE_BOUND | UNKNOWN |

5. The final verdict is computed from all contributions according to the following table:

| Final condition | Final verdict |
|---|---|
| No GOVERNANCE_RULE scope matches the proposed action | DENY with rule_id NULL and reason kind no_matching_rule |
| At least one scope matches but no rule contributes | DENY with reason kind no_rule_fired |
| One or more rules contribute | the highest numeric PRIORITY contribution wins |
| Equal-priority conflict | resolve by status order DENY > UNKNOWN > ALLOW |
| Equal-priority same-status tie | use lexicographic RuleID only to choose the reported rule_id |

6. The proposed host action is authorized only if a candidate STATE_TRANSITION has PRECONDITION TRUE and the final rule resolution for its governing rule set is ALLOW. Otherwise the evaluator returns DENY or UNKNOWN as determined by the finalization table.

7. If all static declarations are valid but the current state object lacks a required observation value for this EVALUATE call, the evaluator emits UNKNOWN with a gap_report identifying the missing live observation. The evaluator must not invent a value for the missing term, must not silently coerce it to FALSE, and must not emit ALLOW for a predicate whose live inputs are incomplete.

8. For Extended Profile evaluations, enforce RESOURCE_BOUND on predicate evaluation as declared in the specification (Appendix A Section A.2.2). If evaluation time or memory consumption exceeds the declared bound before the predicate resolves, the evaluator must halt evaluation of that predicate and emit UNKNOWN. The gap_report must identify the bound that was exceeded.

### C.2.3 REPORT

The verdict object produced by EVALUATE must have the following structure:

- **status:** one of ALLOW, DENY, or UNKNOWN. No other values are permitted.
- **rule_id:** the canonical RuleID of the GOVERNANCE_RULE that fired. If no rule matched and the verdict is the default-deny DENY, rule_id is NULL.
- **reason:** present if and only if status is DENY. A structured object identifying the denial kind, such as no_matching_transition, no_matching_rule, no_rule_fired, precondition_failed, prohibitive_rule_fired, or approval_required, and the observed state relevant to that denial. Reason must be machine-readable, not a free-text message.
- **gap_report:** present if and only if status is UNKNOWN. A structured object listing either (a) the terms that could not be observed, naming the PERCEPTION_MAP or state variable that was expected to supply them, or (b) the RESOURCE_BOUND that was exceeded, including the declared threshold and the measured value at the point of halt.

The verdict object is the complete output of a single EVALUATE call. The calling system must not rely on any side channel for verdict information. All decision-relevant data must be present in the verdict object.

---

## C.3 Conformance Requirements

### C.3.1 Acceptance Tests

A conformant Omega evaluator must:

- Accept all five example specifications in Appendix B (Sections B.1 through B.5) as syntactically valid. An evaluator that rejects any of these specifications at parse time is non-conformant.
- Produce the documented verdicts under the documented inputs for each example. Each example in Appendix B specifies expected verdicts for representative passing inputs, failing inputs, and edge cases. An evaluator that produces a verdict inconsistent with those documented is non-conformant.
- Reject all five negative snippets in Appendix A Section A.12.2, returning the rejection reason documented for each. An evaluator that accepts any of those snippets is non-conformant.
- Accept all three positive snippets in Appendix A Section A.12.1 as syntactically valid. An evaluator that rejects any of those snippets is non-conformant.

### C.3.2 Profile Enforcement

A Strict-only conformant evaluator must reject specifications declaring PROFILE Extended at the compilation-unit level. It is not required to support Extended Profile evaluation; its refusal to load an Extended spec is correct behavior, not a defect.

A full conformant evaluator must support both profiles and must enforce profile boundaries in both directions. Extended constructs appearing in a Strict-declared module must be rejected at parse time or load time. Strict policy slots may call only registered pure, total, deterministic, side-effect-free Boolean predicate functions or observation lookups. Strict constructs appearing in an Extended-declared module must be accepted and evaluated normally; the Extended Profile is a superset of the Strict Profile.

The PROFILE directive is the authoritative source for profile determination. If no PROFILE directive is present, the specification operates under the Strict Profile (Appendix A Section A.2.3).

### C.3.3 Determinism

For the same loaded spec and the same input state, an evaluator must produce identical verdicts on every call. Verdict determinism is required for replayability and audit. A DENY verdict against a given proposed action on Tuesday must be reproducible against the same input on Friday, given the same loaded spec and the same state object.

Any caching, indexing, parallelization, or domain-specific optimization (see Section C.6) must preserve this determinism guarantee. Non-deterministic optimizations are not permitted.

### C.3.4 v1.0 Conformance Artifact Status

The v1.0 Final Candidate conformance target is the behavior specified by the four Omega RFC documents. A reference implementation is not required for conformance; the specification is the normative artifact.

An implementation claiming conformance must document its host bindings, implementation registries, and enforcement-mode classifications sufficiently for another implementer to reproduce LOAD, EVALUATE, and REPORT behavior against the same input. Companion artifacts may later define canonical registry serializations, expanded conformance vectors, and non-normative reference implementations; those artifacts are not required to satisfy the v1.0 language contract unless a later version explicitly incorporates them.

---

## C.4 The Static Checks Required at Load Time

The following checks must all pass before a spec object is produced. Each failed check produces a structured load-time error and no spec object.

1. **Grammar parse.** The source must conform to the canonical EBNF in Appendix A Section A.10. Every production rule must match. Errors carry line and column of the first non-conforming token.

2. **Reference resolution.** Every named reference in the spec (RuleID, EntityID, ContextID, ScopeID, SchemaID, BoundID, ActionID, and any identifier appearing in a TARGET_REFERENCE, ENFORCEMENT_MODE, GOVERNED_BY, CONSTRAINT_SET, or KNOWLEDGE_UPDATE_RULE field) must resolve to a definition, host binding, or conformant implementation registry entry available to the loaded spec. Forward references are permitted if the loaded unit is the complete module; dangling references are not.

3. **Profile compliance.** For compilation units declaring PROFILE Strict (or defaulting to Strict), no LOOP, WHILE, FOR, recursion, mutable state, external I/O, unregistered host call, or user-defined FUNCTION construct may appear inside a predicate body, condition body, or transform-action body. Strict predicate calls must resolve to registered Strict predicates that are pure, total, deterministic, side-effect-free, non-recursive, terminating by construction, and limited to declared observation inputs. These constructs are enumerated in Appendix A Section A.5.2 and A.5.3. Profile-violating constructs are errors, not warnings.

4. **Required-field presence per primitive.** Each of the 13 primitives has a defined set of required fields and optional fields, as specified in Appendix A Section A.6. A call that omits a required field or includes a field not defined in the grammar for that primitive is a load-time error.

5. **MUTATION_RULE authority graph check.** The evaluator must construct the mutation authority graph. Nodes are mutable definitions addressable through SELF_REFERENCE_POINT. Direct edges connect each MUTATION_RULE to its TARGET_REFERENCE. Derived authority edges include any mutation that can alter another mutation rule, approval policy, trust requirement, target reference, or governing rule. The evaluator must reject cycles that allow a mutation path to weaken its own approval policy, expand its own target set, bypass its governing authority, or alter Constitutional targets. The error must identify the cycle by listing the RuleIDs and SELF_REFERENCE_POINTs involved.

6. **Type-compatibility check.** The types of values produced by PERCEPTION_MAP output schemas and DATA_TYPE_SCHEMA definitions must be compatible with the types consumed by the GOVERNANCE_RULE predicates that reference them. A GOVERNANCE_RULE predicate that applies a comparison operator to a term whose type is not comparable (for example, comparing a structured schema type to an integer literal with the less-than operator) is a load-time error.

7. **Cross-reference structural integrity.** Every MUTATION_RULE's TARGET_REFERENCE must name a SELF_REFERENCE_POINT. Every GOVERNANCE_RULE's ENFORCEMENT_MODE must resolve to a valid enforcement-mode identifier with exactly one class, permissive or prohibitive. Every STATE_TRANSITION's GOVERNED_BY must name a GOVERNANCE_RULE. Every STATE_TRANSITION's REVERSION_PROTOCOL must name a declared protocol identifier. Every LEARNING_AXIOM's CONSTRAINT_SET entries must each name a RESOURCE_BOUND. Every LEARNING_AXIOM's KNOWLEDGE_UPDATE_RULE must name a MUTATION_RULE in the same module. These structural bindings are validated at load time, not at evaluation time.

8. **Extended bound binding.** In the Extended Profile, every policy-evaluation slot that uses Extended-only constructs must include CONSTRAINT_SET, and every listed bound must resolve to a RESOURCE_BOUND. Missing CONSTRAINT_SET or unresolved bounds are load-time errors.

9. **Constitutional target rejection.** TARGET_TYPE_ID and the formal self-reference target categories are Constitutional. A META_DEFINITION_RULE that attempts to add, remove, or reinterpret TARGET_TYPE_ID, grammar primitives, parser/compiler elements, primitive definitions, Appendix D, or the Constitutional tier is a load-time error.

**Registry and host-binding obligations.** LOAD relies on implementation registries where the source names a host-provided action, predicate, enforcement mode, target type, protocol identifier, or resource metric. A conformant implementation must make those registries available to the loader and must reject missing or malformed entries at load time when referenced by the loaded specification.

At minimum, a host action descriptor records the identifier, argument signature, return type if any, side-effect class, determinism class, permitted profile or profiles, and resource-bound behavior. An enforcement-mode entry records the identifier, exactly one class of permissive or prohibitive, verdict contribution behavior, and any approval dependency. A Strict predicate entry records the identifier, input types, Boolean output, purity, totality, determinism, termination basis, and allowed observation inputs. A target-type entry records the identifier, Constitutional or extensible status, permitted access protocols, and mutation eligibility. A protocol identifier entry records the identifier, domain, expected inputs and outputs if applicable, and profile compatibility. A resource metric entry records the identifier, unit, threshold comparison semantics, and deterministic measurement rule. The v1.0 language contract requires these obligations but does not require a particular registry serialization format.

---

## C.5 The Runtime Checks Required at Evaluation Time

The following checks must execute during every EVALUATE call. They are not optional and cannot be deferred.

1. **Transition matching.** Before rule evaluation begins, the evaluator must match the proposed host action to candidate STATE_TRANSITION.ACTION values. A proposed action with no matching transition returns DENY with reason kind no_matching_transition.

2. **Precondition and predicate evaluation against state.** For each candidate transition and matching GOVERNANCE_RULE, the evaluator walks the Boolean expression tree and resolves each term against the current state object, following the operational semantics in Appendix A Section A.6. Boolean sub-expressions are evaluated with the precedence defined in Appendix A Section A.10.

3. **Rule contribution and PRIORITY resolution.** Rules whose SCOPE does not match produce no contribution. Matching rules whose PREDICATE evaluates FALSE produce no contribution. Matching rules whose PREDICATE evaluates TRUE contribute ALLOW or DENY according to the ENFORCEMENT_MODE class. Matching rules with missing live observations or exceeded Extended bounds contribute UNKNOWN. If multiple rules contribute, the rule with the highest PRIORITY value determines the outcome. Equal-priority conflicts resolve by status order DENY > UNKNOWN > ALLOW. Equal-priority same-status ties use lexicographic RuleID only to select the reported rule_id.

4. **RESOURCE_BOUND enforcement for Extended Profile.** For any predicate that admits Extended Profile constructs (because the loaded spec declares PROFILE Extended and the predicate contains loops or user-defined function calls), the evaluator must track execution cost against the RESOURCE_BOUND declared in the loaded spec. If the bound is exceeded, predicate evaluation is halted immediately and the verdict for that rule is UNKNOWN. The halt must not produce a partial or corrupted state.

5. **UNKNOWN emission for dynamic unobservable state.** If all declarations and types are valid but a predicate term cannot be resolved because the current state object lacks the required live observation value, the evaluator must emit UNKNOWN for that predicate. The gap_report must name the specific observation that could not be resolved. The evaluator must not substitute a default value for an unobservable term, because doing so would convert a genuine information gap into a false verdict.

6. **Verdict packaging.** The evaluator must construct the verdict object as defined in Section C.2.3 before returning. All required fields must be populated. A verdict object missing its reason field when status is DENY, or missing its gap_report field when status is UNKNOWN, is a malformed verdict and the implementation is non-conformant.

7. **Fail-closed default for unmatched proposed actions.** If no GOVERNANCE_RULE in the loaded spec matches the proposed action's scope, the evaluator must return DENY with rule_id NULL and reason kind no_matching_rule. If at least one scope matches but no rule contributes, the evaluator must return DENY with reason kind no_rule_fired. There is no ALLOW-by-default. The default-deny policy is structural: it is not configurable and it cannot be disabled.

8. **Postcondition verification.** After an authorized host action reports completion, the POSTCONDITION of the selected STATE_TRANSITION is a verification predicate. If the postcondition evaluates FALSE, the evaluator or reporting layer emits a structured violation. If it cannot be evaluated because a declared live observation is unavailable, the report status for that verification is UNKNOWN. REVERSION_PROTOCOL, if present, names host remediation behavior and does not guarantee physical rollback.

---

## C.6 What Implementations May Optimize

An implementation may depart from naive sequential evaluation in the following bounded ways. In every case, the requirement is that the externally observable output, specifically the verdict object returned by EVALUATE, is identical to what a canonical sequential evaluation would produce.

- **Bytecode compilation of loaded specs.** An implementation may compile the parsed spec into an internal representation (bytecode, decision tree, jump table, or any other form) during LOAD, provided the compiled representation faithfully models the structure and semantics of the source. Parse once, evaluate many is the intended use pattern.
- **Caching and predicate memoization.** An implementation may cache the results of predicate evaluations that are deterministic with respect to their input state. Memoized results must be invalidated whenever the state or the loaded spec changes. Stale cache entries that produce incorrect verdicts violate the determinism requirement.
- **Indexing for scope matching.** An implementation may build an index over GOVERNANCE_RULE SCOPE declarations during LOAD to accelerate the matching step in EVALUATE. The index must be complete: no matching rule may be omitted from evaluation due to an indexing error.
- **Parallel evaluation across independent rules.** An implementation may evaluate independent GOVERNANCE_RULEs in parallel, provided PRIORITY resolution ordering is preserved before the final verdict is issued. Parallelism that causes a lower-priority rule's verdict to overwrite a higher-priority rule's verdict is non-conformant.
- **Hot-reload of specifications.** An implementation may support reloading a spec while the Safety Kernel is running, provided the reload is transactional. The transition from the old spec to the new spec must be atomic from the perspective of the calling system: no proposed action may be evaluated against a partially loaded state. EVALUATE must use either the old spec or the new spec entirely, never a mixture of both.
- **Domain-specific optimizations.** An implementation may apply domain-specific evaluation strategies (for example, spatial indexing for predicates that involve geographic bounds, or interval-tree structures for TEMPORAL_RELATION predicates) provided the verdict produced is identical to the canonical evaluation. If a domain-specific optimization would produce a different verdict in any case, it must not be applied.

---

## C.7 What Implementations Must Not Do

The following behaviors are prohibited in a conformant implementation. They are listed here because each represents a plausible optimization or defensive shortcut that appears harmless but violates the guarantees the Safety Kernel is required to provide.

- **Must not silently accept malformed specifications.** Parse errors must be returned as structured errors. An implementation that accepts a malformed spec by ignoring the offending construct is not forgiving; it is non-conformant. The calling system must be informed of every load-time failure.
- **Must not invent UNKNOWN verdicts to avoid complex predicates.** UNKNOWN is reserved for dynamic absence and boundedness cases: all declarations and types are valid, but the current state object lacks a required live observation, or RESOURCE_BOUND is exceeded in Extended Profile evaluation. Unresolved declarations, unknown actions, missing governing rules, missing bounds, missing extensions mentioned by the spec, unknown enforcement modes, and type errors are load-time errors, not runtime UNKNOWN cases.
- **Must not modify a loaded spec at runtime except through formal MUTATION_RULE invocation.** The compiled spec object produced by LOAD is immutable except when a MUTATION_RULE fires under its declared CONDITION and APPROVAL_POLICY. Implementations that patch the spec object directly, outside the MUTATION_RULE pathway, violate the structural integrity of the governance layer.
- **Must not provide a mode that disables PROFILE enforcement.** There is no debug mode, compatibility mode, or legacy mode in which PROFILE Strict constructs are accepted alongside Extended Profile constructs without a governing PROFILE directive. Profile enforcement is not optional.
- **Must not provide a mode that bypasses RESOURCE_BOUND enforcement in Extended Profile.** RESOURCE_BOUND enforcement is not a performance feature that can be disabled in production. It is a safety property. An implementation that allows Extended Profile predicates to run without bound has removed the termination guarantee that makes Extended Profile safe to deploy. There is no legitimate reason to bypass this enforcement.
- **Must not return multiple verdicts for a single EVALUATE call.** The EVALUATE operation produces exactly one verdict object per call. An implementation that returns a list of per-rule verdicts without resolving them via PRIORITY has not completed the evaluation; it has offloaded a required step to the calling system.

---

## C.8 The Conformance Checklist

An implementer may use the following checklist to verify that their Safety Kernel is conformant. Each item references the section of this appendix or of Appendix A or B where the requirement is formally stated.

**LOAD behavior**

- [ ] The parser accepts all three positive snippets in Appendix A Section A.12.1 without error.
- [ ] The parser rejects all five negative snippets in Appendix A Section A.12.2 with the reasons documented there.
- [ ] A missing required field in any primitive call produces a structured load-time error. (Appendix A Section A.6; this appendix Section C.4.4)
- [ ] An unresolved named reference produces a structured load-time error naming the reference and its source location. (Section C.4.2)
- [ ] A mutation authority graph cycle that can weaken approval, expand targets, bypass governing authority, or alter Constitutional targets produces a load-time error listing the cycle. (Section C.4.5)
- [ ] A PROFILE Strict compilation unit that contains LOOP, WHILE, FOR, recursion, mutable state, external I/O, unregistered host calls, or user-defined FUNCTION in a policy-evaluation slot is rejected at parse time or load time. (Section C.4.3; Appendix A Section A.2.1)
- [ ] Every Strict predicate function call resolves to a registered pure, total, deterministic, side-effect-free, non-recursive, terminating predicate limited to declared observation inputs. (Section C.4.3; Appendix A Section A.2.1)
- [ ] A compilation unit with no PROFILE directive is treated as PROFILE Strict. (Appendix A Section A.2.3)
- [ ] A Strict-only implementation rejects compilation units declaring PROFILE Extended. (Section C.3.2)
- [ ] All cross-reference structural bindings are verified at load time: MUTATION_RULE TARGET_REFERENCE to SELF_REFERENCE_POINT, STATE_TRANSITION GOVERNED_BY to GOVERNANCE_RULE, LEARNING_AXIOM CONSTRAINT_SET entries to RESOURCE_BOUNDs, LEARNING_AXIOM KNOWLEDGE_UPDATE_RULE to a same-module MUTATION_RULE, and GOVERNANCE_RULE ENFORCEMENT_MODE resolution to a valid classified enforcement-mode identifier. (Section C.4.7)
- [ ] Every ActionID referenced by STATE_TRANSITION, MUTATION_RULE, or PERCEPTION_MAP resolves to a host action descriptor or declared abstract action. (Section C.2.1)
- [ ] Every referenced host action, enforcement mode, Strict predicate, target type, protocol identifier, and resource metric resolves to a registry entry with the minimum fields required by Section C.4.
- [ ] Extended policy-evaluation slots using Extended-only constructs declare CONSTRAINT_SET and every listed bound resolves to a RESOURCE_BOUND. (Section C.4.8)
- [ ] META_DEFINITION_RULE cannot extend TARGET_TYPE_ID, grammar primitives, parser/compiler elements, primitive definitions, Appendix D, or the Constitutional tier. (Section C.4.9)
- [ ] Static absence is rejected at load time and is never deferred to runtime UNKNOWN. (Section C.2.1; Section C.7)

**EVALUATE behavior**

- [ ] The evaluator accepts all five example specifications in Appendix B and produces the documented verdicts under the documented inputs. (Section C.3.1)
- [ ] A proposed action with no matching STATE_TRANSITION returns DENY with reason kind no_matching_transition. (Section C.5.1)
- [ ] A proposed action whose SCOPE matches no GOVERNANCE_RULE returns DENY with rule_id NULL and reason kind no_matching_rule. (Section C.5.7)
- [ ] A proposed action with at least one matching scope but no contributing rule returns DENY with reason kind no_rule_fired. (Section C.5.7)
- [ ] A proposed action governed by multiple GOVERNANCE_RULEs with differing verdicts resolves by PRIORITY, equal-priority conflicts resolve by DENY > UNKNOWN > ALLOW, and the evaluator returns a single verdict. (Section C.5.3)
- [ ] A predicate term with a declared source but no live value in the current state returns UNKNOWN with a gap_report naming the missing observation. (Section C.5.5)
- [ ] Extended Profile predicate evaluation that exceeds its RESOURCE_BOUND returns UNKNOWN with a gap_report naming the exceeded bound. (Section C.5.4)
- [ ] The evaluator never returns ALLOW for an action matched by a prohibitive ENFORCEMENT_MODE, regardless of optimization state. (Section C.2.2)
- [ ] The evaluator authorizes a host action only through a STATE_TRANSITION whose PRECONDITION is TRUE and whose GOVERNED_BY rule resolution returns ALLOW. (Section C.2.2)
- [ ] POSTCONDITION is treated as post-action verification, not as a physical guarantee made by the Safety Kernel. (Section C.5.8)

**REPORT structure**

- [ ] Every verdict object carries status, rule_id, and (when applicable) reason and gap_report. (Section C.2.3)
- [ ] A DENY verdict always carries a structured reason identifying a denial kind and the observed state relevant to that denial. (Section C.2.3)
- [ ] An UNKNOWN verdict always carries a gap_report. The gap_report is never empty. (Section C.2.3)
- [ ] No verdict object carries status values other than ALLOW, DENY, or UNKNOWN. (Section C.2.3)

**Profile and determinism**

- [ ] For the same loaded spec and same input state, EVALUATE returns the same verdict on every call. (Section C.3.3)
- [ ] Any caching, indexing, or parallel optimization does not alter the verdict relative to canonical sequential evaluation. (Section C.6)
- [ ] PROFILE enforcement cannot be disabled by any runtime flag, environment variable, or configuration option. (Section C.7)
- [ ] RESOURCE_BOUND enforcement in Extended Profile cannot be disabled by any runtime flag, environment variable, or configuration option. (Section C.7)

An implementation that passes every item on this checklist under the conditions specified is a conformant Omega Safety Kernel.
