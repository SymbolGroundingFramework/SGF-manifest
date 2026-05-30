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

The Safety Kernel is profile-aware. A Strict-only implementation rejects Extended Profile constructs at parse time and is not required to load or evaluate them. A full implementation supports both profiles and enforces profile boundaries: Extended constructs that appear in a module declaring PROFILE Strict are rejected at parse time, not silently ignored. Profile declarations govern what the evaluator accepts; an evaluator that accepts everything regardless of the PROFILE directive is non-conformant.

The Safety Kernel is host-language-agnostic. The choice of implementation language is the implementer's own. The requirements in this appendix are stated in terms of structural behavior. Any language that provides the necessary structural primitives for parsing, tree walking, and predicate evaluation can host a conformant Safety Kernel.

---

## C.2 The Three Operations in Detail

### C.2.1 LOAD

**Input:** a path to a `.omega` file, or an in-memory specification string.

**Output:** a compiled spec object ready for evaluation, or a structured parse error carrying at minimum the line number, column number, and a description of the violation.

**What LOAD must do:**

1. Parse the input against the canonical EBNF in Appendix A Section A.10. Any token sequence that does not conform to the grammar must be rejected immediately. The rejection must be loud: a structured parse error is returned and no spec object is produced. Silent acceptance of malformed input is not permitted.

2. Resolve all named references: RuleIDs, EntityIDs, ContextIDs, ScopeIDs, SchemaIDs, and any other identifier that one part of the specification uses to refer to another. An unresolved reference is a load-time error. The error must identify the reference that could not be resolved and the location in the source where it appeared.

3. Validate cross-references between primitives. Every MUTATION_RULE's TARGET_REFERENCE must point to a SELF_REFERENCE_POINT defined within the loaded spec. Every GOVERNANCE_RULE's ENFORCEMENT_CONTEXT must point to a CONTEXT_RULE defined within the loaded spec. Every LEARNING_AXIOM's KNOWLEDGE_UPDATE_RULE must name a MUTATION_RULE defined within the same module. Cross-reference failures are load-time errors.

4. Perform static profile checks. If the module declares PROFILE Strict (or omits the PROFILE directive, which defaults to Strict per Appendix A Section A.2.3), the evaluator must reject any LOOP, WHILE, FOR, or user-defined FUNCTION construct that appears inside a policy-evaluation slot. Strict Profile constructs are defined in Appendix A Section A.2.1. Profile violations are load-time errors.

5. Verify required-field presence for each primitive. Appendix A Section A.6 specifies which fields are required and which are optional for each of the 13 primitives. A primitive call that omits a required field is a load-time error. A primitive call that includes an unknown field is also a load-time error; the grammar does not admit extension fields at the call site.

6. Detect cycles in MUTATION_RULE chains. A cycle exists when MUTATION_RULE A names MUTATION_RULE B in its TRANSFORM_ACTION chain and MUTATION_RULE B names MUTATION_RULE A, directly or transitively. Cyclic MUTATION_RULE chains are load-time errors.

7. Perform type-compatibility checks between PERCEPTION_MAP outputs and the GOVERNANCE_RULE predicates that consume them. If a GOVERNANCE_RULE predicate references a term whose type cannot be established from the available PERCEPTION_MAP output schemas or DATA_TYPE_SCHEMA declarations, that is a load-time error.

If LOAD succeeds, the resulting compiled spec object is the operand for all subsequent EVALUATE calls. The compiled spec object must be immutable after load. No field in it may be altered at runtime except through a properly authorized MUTATION_RULE invocation under the conditions specified in Section C.5.

### C.2.2 EVALUATE

**Input:** a proposed action descriptor; a current state object supplying the observable state variables available at evaluation time.

**Output:** a verdict object as defined in Section C.2.3.

**What EVALUATE must do:**

1. Identify the set of GOVERNANCE_RULEs in the loaded spec whose SCOPE matches the proposed action. If no rule's SCOPE matches, the evaluator must apply the default-deny policy: the action is rejected with a verdict of DENY, rule_id NULL, and a reason indicating no matching rule was found. Omega is fail-closed. An unmatched proposed action is never silently permitted.

2. For each matching GOVERNANCE_RULE, evaluate its PREDICATE against the current state object. Predicate evaluation proceeds according to the operational semantics for Boolean expressions and function calls defined in Appendix A Section A.6.

3. If the predicate evaluates to TRUE and the ENFORCEMENT_CONTEXT is permissive, emit ALLOW with the rule_id.

4. If the predicate evaluates to TRUE and the ENFORCEMENT_CONTEXT is prohibitive, emit DENY with the rule_id and a structured reason. The reason must identify which predicate clause failed and what the observed state was at the failure point.

5. If multiple rules match and produce conflicting verdicts, resolve by PRIORITY. Higher-priority rules take precedence. The PRIORITY field is defined as part of GOVERNANCE_RULE in Appendix A Section A.6.8. Ties in priority that cannot be resolved structurally are a specification error; the implementer may treat them as a load-time warning and define a deterministic tiebreak (for example, lexicographic ordering of rule_id), but must document the behavior.

6. If the state required by a predicate cannot be observed because no PERCEPTION_MAP in the loaded spec supplies the needed term, the evaluator must emit UNKNOWN with a gap_report identifying the missing observation. The evaluator must not invent a value for the missing term, must not silently coerce it to FALSE, and must not emit ALLOW for a predicate whose inputs are incomplete.

7. For Extended Profile evaluations, enforce RESOURCE_BOUND on predicate evaluation as declared in the specification (Appendix A Section A.2.2). If evaluation time or memory consumption exceeds the declared bound before the predicate resolves, the evaluator must halt evaluation of that predicate and emit UNKNOWN. The gap_report must identify the bound that was exceeded.

### C.2.3 REPORT

The verdict object produced by EVALUATE must have the following structure:

- **status:** one of ALLOW, DENY, or UNKNOWN. No other values are permitted.
- **rule_id:** the canonical RuleID of the GOVERNANCE_RULE that fired. If no rule matched and the verdict is the default-deny DENY, rule_id is NULL.
- **reason:** present if and only if status is DENY. A structured object identifying (a) which clause of the predicate evaluated to FALSE or could not be resolved, and (b) the value of each state variable observed at the point of failure. Reason must be machine-readable, not a free-text message.
- **gap_report:** present if and only if status is UNKNOWN. A structured object listing either (a) the terms that could not be observed, naming the PERCEPTION_MAP or state variable that was expected to supply them, or (b) the RESOURCE_BOUND that was exceeded, including the declared threshold and the measured value at the point of halt.

The verdict object is the complete output of a single EVALUATE call. The calling system must not rely on any side channel for verdict information. All decision-relevant data must be present in the verdict object.

---

## C.3 Conformance Requirements

### C.3.1 Acceptance Tests

A conformant Omega evaluator must:

- Accept all five example specifications in Appendix B (Sections B.1 through B.5) as syntactically valid. An evaluator that rejects any of these specifications at parse time is non-conformant.
- Produce the documented verdicts under the documented inputs for each example. Each example in Appendix B specifies expected verdicts for representative passing inputs, failing inputs, and edge cases. An evaluator that produces a verdict inconsistent with those documented is non-conformant.
- Reject all four negative snippets in Appendix A Section A.12.2, returning the rejection reason documented for each. An evaluator that accepts any of those snippets is non-conformant.
- Accept all three positive snippets in Appendix A Section A.12.1 as syntactically valid. An evaluator that rejects any of those snippets is non-conformant.

### C.3.2 Profile Enforcement

A Strict-only conformant evaluator must reject specifications declaring PROFILE Extended at the module level. It is not required to support Extended Profile evaluation; its refusal to load an Extended spec is correct behavior, not a defect.

A full conformant evaluator must support both profiles and must enforce profile boundaries in both directions. Extended constructs appearing in a Strict-declared module must be rejected at parse time. Strict constructs appearing in an Extended-declared module must be accepted and evaluated normally; the Extended Profile is a superset of the Strict Profile.

The PROFILE directive is the authoritative source for profile determination. If no PROFILE directive is present, the specification operates under the Strict Profile (Appendix A Section A.2.3).

### C.3.3 Determinism

For the same loaded spec and the same input state, an evaluator must produce identical verdicts on every call. Verdict determinism is required for replayability and audit. A DENY verdict against a given proposed action on Tuesday must be reproducible against the same input on Friday, given the same loaded spec and the same state object.

Any caching, indexing, parallelization, or domain-specific optimization (see Section C.6) must preserve this determinism guarantee. Non-deterministic optimizations are not permitted.

---

## C.4 The Static Checks Required at Load Time

The following checks must all pass before a spec object is produced. Each failed check produces a structured load-time error and no spec object.

1. **Grammar parse.** The source must conform to the canonical EBNF in Appendix A Section A.10. Every production rule must match. Errors carry line and column of the first non-conforming token.

2. **Reference resolution.** Every named reference in the spec (RuleID, EntityID, ContextID, ScopeID, SchemaID, BoundID, and any identifier appearing in a TARGET_REFERENCE, ENFORCEMENT_CONTEXT, CONSTRAINT_SET, or KNOWLEDGE_UPDATE_RULE field) must resolve to a definition within the loaded spec. Forward references are permitted if the loaded unit is the complete module; dangling references are not.

3. **Profile compliance.** For modules declaring PROFILE Strict (or defaulting to Strict), no LOOP, WHILE, FOR, or FUNCTION construct may appear inside a predicate body, condition body, or transform-action body. These constructs are enumerated in Appendix A Section A.5.2 and A.5.3. Profile-violating constructs at parse time are errors, not warnings.

4. **Required-field presence per primitive.** Each of the 13 primitives has a defined set of required fields and optional fields, as specified in Appendix A Section A.6. A call that omits a required field or includes a field not defined in the grammar for that primitive is a load-time error.

5. **MUTATION_RULE topology check.** The directed graph of MUTATION_RULE chains must be acyclic. The evaluator must perform a cycle detection pass over all MUTATION_RULEs in the loaded spec. Any cycle is a load-time error. The error must identify the cycle by listing the RuleIDs involved.

6. **Type-compatibility check.** The types of values produced by PERCEPTION_MAP output schemas and DATA_TYPE_SCHEMA definitions must be compatible with the types consumed by the GOVERNANCE_RULE predicates that reference them. A GOVERNANCE_RULE predicate that applies a comparison operator to a term whose type is not comparable (for example, comparing a structured schema type to an integer literal with the less-than operator) is a load-time error.

7. **Cross-reference structural integrity.** Every MUTATION_RULE's TARGET_REFERENCE must name a SELF_REFERENCE_POINT. Every GOVERNANCE_RULE's ENFORCEMENT_CONTEXT must name a CONTEXT_RULE. Every STATE_TRANSITION's REVERSION_PROTOCOL must name a declared protocol identifier. Every LEARNING_AXIOM's CONSTRAINT_SET entries must each name a RESOURCE_BOUND. These structural bindings are validated at load time, not at evaluation time.

---

## C.5 The Runtime Checks Required at Evaluation Time

The following checks must execute during every EVALUATE call. They are not optional and cannot be deferred.

1. **Scope matching.** Before predicate evaluation begins, the evaluator must determine which GOVERNANCE_RULEs apply to the proposed action by checking each rule's SCOPE. Only matching rules are evaluated. Rules whose SCOPE does not match are not evaluated; they produce no verdict contribution for this call.

2. **Predicate evaluation against state.** For each matching GOVERNANCE_RULE, the evaluator walks the predicate expression tree and resolves each term against the current state object, following the operational semantics in Appendix A Section A.6. Boolean sub-expressions are evaluated with short-circuit behavior only if the specification's profile permits it; in the Strict Profile, all predicate terms must resolve before a final verdict is issued.

3. **PRIORITY resolution among matching rules.** If multiple GOVERNANCE_RULEs match the proposed action and produce differing verdicts, the rule with the highest PRIORITY value determines the outcome. The PRIORITY field is a non-negative integer; higher values indicate higher precedence. All PRIORITY comparisons are numerical. The evaluator must resolve conflicts before returning a verdict; it may not return multiple conflicting verdicts.

4. **RESOURCE_BOUND enforcement for Extended Profile.** For any predicate that admits Extended Profile constructs (because the loaded spec declares PROFILE Extended and the predicate contains loops or user-defined function calls), the evaluator must track execution cost against the RESOURCE_BOUND declared in the loaded spec. If the bound is exceeded, predicate evaluation is halted immediately and the verdict for that rule is UNKNOWN. The halt must not produce a partial or corrupted state.

5. **UNKNOWN emission for unobservable state.** If a predicate term cannot be resolved because no PERCEPTION_MAP in the loaded spec produces the required observation, the evaluator must emit UNKNOWN for that predicate. The gap_report must name the specific term that could not be resolved. The evaluator must not substitute a default value for an unobservable term, because doing so would convert a genuine information gap into a false verdict.

6. **Verdict packaging.** The evaluator must construct the verdict object as defined in Section C.2.3 before returning. All required fields must be populated. A verdict object missing its reason field when status is DENY, or missing its gap_report field when status is UNKNOWN, is a malformed verdict and the implementation is non-conformant.

7. **Fail-closed default for unmatched proposed actions.** If no GOVERNANCE_RULE in the loaded spec matches the proposed action's scope, the evaluator must return DENY with rule_id NULL. There is no ALLOW-by-default. The default-deny policy is structural: it is not configurable and it cannot be disabled.

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
- **Must not invent UNKNOWN verdicts to avoid complex predicates.** UNKNOWN is reserved for two cases: genuinely unobservable state (a PERCEPTION_MAP does not supply the required term) and RESOURCE_BOUND exceedance in Extended Profile evaluation. An implementation that returns UNKNOWN on a predicate it finds computationally inconvenient is misusing the verdict type and hiding what should be a conformance failure or an implementation defect.
- **Must not modify a loaded spec at runtime except through formal MUTATION_RULE invocation.** The compiled spec object produced by LOAD is immutable except when a MUTATION_RULE fires under its declared CONDITION and APPROVAL_POLICY. Implementations that patch the spec object directly, outside the MUTATION_RULE pathway, violate the structural integrity of the governance layer.
- **Must not provide a mode that disables PROFILE enforcement.** There is no debug mode, compatibility mode, or legacy mode in which PROFILE Strict constructs are accepted alongside Extended Profile constructs without a governing PROFILE directive. Profile enforcement is not optional.
- **Must not provide a mode that bypasses RESOURCE_BOUND enforcement in Extended Profile.** RESOURCE_BOUND enforcement is not a performance feature that can be disabled in production. It is a safety property. An implementation that allows Extended Profile predicates to run without bound has removed the termination guarantee that makes Extended Profile safe to deploy. There is no legitimate reason to bypass this enforcement.
- **Must not return multiple verdicts for a single EVALUATE call.** The EVALUATE operation produces exactly one verdict object per call. An implementation that returns a list of per-rule verdicts without resolving them via PRIORITY has not completed the evaluation; it has offloaded a required step to the calling system.

---

## C.8 The Conformance Checklist

An implementer may use the following checklist to verify that their Safety Kernel is conformant. Each item references the section of this appendix or of Appendix A or B where the requirement is formally stated.

**LOAD behavior**

- [ ] The parser accepts all three positive snippets in Appendix A Section A.12.1 without error.
- [ ] The parser rejects all four negative snippets in Appendix A Section A.12.2 with the reasons documented there.
- [ ] A missing required field in any primitive call produces a structured load-time error. (Appendix A Section A.6; this appendix Section C.4.4)
- [ ] An unresolved named reference produces a structured load-time error naming the reference and its source location. (Section C.4.2)
- [ ] A cyclic MUTATION_RULE chain produces a load-time error listing the cycle. (Section C.4.5)
- [ ] A PROFILE Strict module that contains a LOOP, WHILE, FOR, or FUNCTION in a predicate body is rejected at parse time. (Section C.4.3; Appendix A Section A.2.1)
- [ ] A module with no PROFILE directive is treated as PROFILE Strict. (Appendix A Section A.2.3)
- [ ] A Strict-only implementation rejects modules declaring PROFILE Extended. (Section C.3.2)
- [ ] All cross-reference structural bindings are verified at load time: MUTATION_RULE TARGET_REFERENCE to SELF_REFERENCE_POINT, GOVERNANCE_RULE ENFORCEMENT_CONTEXT to CONTEXT_RULE, LEARNING_AXIOM CONSTRAINT_SET entries to RESOURCE_BOUNDs. (Section C.4.7)

**EVALUATE behavior**

- [ ] The evaluator accepts all five example specifications in Appendix B and produces the documented verdicts under the documented inputs. (Section C.3.1)
- [ ] A proposed action whose SCOPE matches no GOVERNANCE_RULE returns DENY with rule_id NULL. (Section C.5.7)
- [ ] A proposed action governed by multiple GOVERNANCE_RULEs with differing verdicts resolves by PRIORITY and returns a single verdict. (Section C.5.3)
- [ ] A predicate term with no supplying PERCEPTION_MAP returns UNKNOWN with a gap_report naming the missing term. (Section C.5.5)
- [ ] Extended Profile predicate evaluation that exceeds its RESOURCE_BOUND returns UNKNOWN with a gap_report naming the exceeded bound. (Section C.5.4)
- [ ] The evaluator never returns ALLOW for an action matched by a prohibitive ENFORCEMENT_CONTEXT, regardless of optimization state. (Section C.2.2)

**REPORT structure**

- [ ] Every verdict object carries status, rule_id, and (when applicable) reason and gap_report. (Section C.2.3)
- [ ] A DENY verdict always carries a structured reason identifying the failing predicate clause and the observed state at failure. (Section C.2.3)
- [ ] An UNKNOWN verdict always carries a gap_report. The gap_report is never empty. (Section C.2.3)
- [ ] No verdict object carries status values other than ALLOW, DENY, or UNKNOWN. (Section C.2.3)

**Profile and determinism**

- [ ] For the same loaded spec and same input state, EVALUATE returns the same verdict on every call. (Section C.3.3)
- [ ] Any caching, indexing, or parallel optimization does not alter the verdict relative to canonical sequential evaluation. (Section C.6)
- [ ] PROFILE enforcement cannot be disabled by any runtime flag, environment variable, or configuration option. (Section C.7)
- [ ] RESOURCE_BOUND enforcement in Extended Profile cannot be disabled by any runtime flag, environment variable, or configuration option. (Section C.7)

An implementation that passes every item on this checklist under the conditions specified is a conformant Omega Safety Kernel.
