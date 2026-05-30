\# Omega Language Specification v1.0 Final Candidate



File: 03-OMEGA-01\_LANGUAGE\_SPEC.md  

Layer: OMEGA (governance grammar)  

Status: Final Candidate



\## 1. Scope and intent



Omega-Code is a typed governance language for self-governing systems. It defines how perception, identity, rules, and state change are expressed and evaluated so that proposed actions can be allowed, denied, or left unknown under explicit constraints.



Omega sits alongside the existing SGF stack:



\- SGF Core structures grounded meaning as Synapses, frames, and lexicon entries.

\- HFF transports SGF objects across trust boundaries.

\- AFP declares what acts are being performed with those objects.

\- Omega governs what may be done: it evaluates proposed actions and specification mutations against declarative constraints.



This document defines the Omega language model, primitive set, profiles, evaluator obligations, and its relationship to SGF, HFF, and AFP. Detailed lexical grammar, EBNF, evaluator behavior, and extension procedures are defined in:



\- 03-OMEGA-02\_FORMAL\_GRAMMAR\_SPEC.md  

\- 03-OMEGA-03\_IMPLEMENTERS\_GUIDE.md  

\- 03-OMEGA-04\_EXTENSION\_GOVERNANCE.md



\## 2. The Omega primitive set



Omega’s governance power comes from thirteen atomic primitives. These primitives are fixed at the Constitutional tier and cannot be altered or redefined by extensions.



\- CONTEXT\_RULE  

\- TEMPORAL\_RELATION  

\- RESOURCE\_BOUND  

\- ENVIRONMENT\_INTERFACE\_POINT  

\- DATA\_TYPE\_SCHEMA  

\- STATE\_TRANSITION  

\- TRUST\_ELEMENT  

\- GOVERNANCE\_RULE  

\- SELF\_REFERENCE\_POINT  

\- MUTATION\_RULE  

\- PERCEPTION\_MAP  

\- LEARNING\_AXIOM  

\- META\_DEFINITION\_RULE  



Each primitive has a well-defined role in the language:



\- CONTEXT\_RULE encodes where and to whom a governance specification applies.  

\- TEMPORAL\_RELATION expresses invariants and constraints over time.  

\- RESOURCE\_BOUND constrains computation and side effects to bounded cost envelopes.  

\- ENVIRONMENT\_INTERFACE\_POINT binds the specification to concrete external systems and sensors.  

\- DATA\_TYPE\_SCHEMA defines the types and shapes of data used in perception and decision.  

\- STATE\_TRANSITION expresses permissible changes in system state.  

\- TRUST\_ELEMENT binds identity, scope, revocation, and accountability into a unit of trust.  

\- GOVERNANCE\_RULE evaluates whether a proposed action is allowed, denied, or unknown under the current context.  

\- SELF\_REFERENCE\_POINT gives the system a stable pointer to its own specification.  

\- MUTATION\_RULE governs how and when the specification itself may be amended.  

\- PERCEPTION\_MAP defines how raw inputs become typed claims for governance to consume.  

\- LEARNING\_AXIOM constrains how trust weights and parameters may be updated based on observed behavior.  

\- META\_DEFINITION\_RULE governs extension of the Omega vocabulary, profiles, and composition patterns.



Field-level definitions and grammar productions for each primitive appear in 03-OMEGA-02\_FORMAL\_GRAMMAR\_SPEC.md.



\## 3. Profiles and decidability



Omega-Code operates under two formally defined profiles. The PROFILE directive at module level declares which profile a specification uses.



\### 3.1 Strict Profile



The Strict Profile is designed for policy-evaluation slots that must remain statically decidable.



\- Policy bodies admit only Boolean expressions, comparison operators, set-membership tests, and calls to functions whose return type is BOOLEAN.  

\- No loops, general recursion, or mutable state are permitted inside Strict policy bodies.  

\- Strict-profile specifications must be statically decidable under the canonical grammar.



\### 3.2 Extended Profile



The Extended Profile is designed for policy slots that require bounded general computation.



\- Policy bodies may use the full pseudocode meta-language (IF, loops, function definitions, recursion).  

\- All Extended-profile evaluation is governed by an explicit RESOURCE\_BOUND.  

\- If evaluation exceeds the declared bound, the result is UNKNOWN. UNKNOWN is a defined verdict, not an error; callers must handle it explicitly.



\### 3.3 Default profile



If no PROFILE directive appears in a module, the specification defaults to the Strict Profile.



Formal syntax and profile enforcement rules appear in 03-OMEGA-02\_FORMAL\_GRAMMAR\_SPEC.md and 03-OMEGA-03\_IMPLEMENTERS\_GUIDE.md.



\## 4. The Can–May–Do gate



Omega formalizes the coupling between perception, permission, and action as a syntactic gate.



\- PERCEPTION\_MAP answers CAN: it maps external signals and SGF state into typed claims about what the system can see.  

\- GOVERNANCE\_RULE answers MAY: it takes those claims, plus TRUST\_ELEMENT and CONTEXT\_RULE bindings, and returns ALLOW, DENY, or UNKNOWN for a proposed action.  

\- STATE\_TRANSITION is DO: it applies permitted changes to system state when MAY is ALLOW.



The sequence CAN → MAY → DO is structural, not conventional. Under the formal grammar:



\- A GOVERNANCE\_RULE that requires predicates not supplied by any PERCEPTION\_MAP is rejected at load time.  

\- A STATE\_TRANSITION that is not justified by at least one applicable GOVERNANCE\_RULE with verdict ALLOW is invalid.  



Specifications that attempt to evaluate MAY without CAN, or DO without MAY, are non-conformant. The grammar and evaluator rules enforce this at load and evaluation time.



\## 5. Evaluator model and safety kernel



An Omega evaluator is the non-probabilistic engine that loads and executes Omega specifications. It runs outside the probabilistic substrate of the governed system.



At minimum, a conformant evaluator must:



\- Parse modules according to the canonical grammar in 03-OMEGA-02\_FORMAL\_GRAMMAR\_SPEC.md.  

\- Enforce profile rules at load time, rejecting any construct that violates the declared profile.  

\- Implement a safety kernel that returns a universal verdict shape (ALLOW, DENY, UNKNOWN or PASS, REJECT, UNKNOWN) for each proposed action.  

\- Ensure determinism: given the same loaded specification and the same input state, repeated evaluations must produce identical verdicts.  

\- Enforce structural checks defined for the primitives, including:

&#x20; - MUTATION\_RULE acyclicity.  

&#x20; - Type compatibility between PERCEPTION\_MAP outputs, DATA\_TYPE\_SCHEMA definitions, and GOVERNANCE\_RULE predicates.  

&#x20; - Presence of all required fields and absence of undefined fields in each primitive invocation.  



Strict-only evaluators may reject Extended-profile modules entirely. Full evaluators must support both profiles and must enforce boundaries between them.



Detailed evaluator behavior, load-time checks, and runtime checks are defined in 03-OMEGA-03\_IMPLEMENTERS\_GUIDE.md.



\## 6. Governance of the specification itself



Omega includes reflexive primitives for self-governance:



\- SELF\_REFERENCE\_POINT gives the system a stable identifier for its own specification so that rules about rule changes can target a concrete object.  

\- MUTATION\_RULE specifies who may change which rules, under what conditions, and which STATE\_TRANSITIONs those changes may induce.  

\- LEARNING\_AXIOM constrains how trust weights, parameters, or thresholds may adapt over time based on observed behavior.  

\- META\_DEFINITION\_RULE governs how new vocabulary slots, composition patterns, or domain-specific rule schemas may be introduced.



Certain elements of the language sit at an unamendable Constitutional tier:



\- The thirteen primitive declarations.  

\- The core grammar productions.  

\- The two-profile structure and Strict decidability requirement.  

\- The safety kernel’s three-valued verdict shape.  

\- The extension-governance rules themselves.



No META\_DEFINITION\_RULE may target these Constitutional elements. A specification that attempts to do so is not an Omega extension; it is a different language.



The full extension governance procedure, including rationale records, predictive impact modeling, stewardship thresholds, and emergency revocation, is defined in 03-OMEGA-04\_EXTENSION\_GOVERNANCE.md.



\## 7. Relationship to SGF, HFF, and AFP



Omega is designed to operate on SGF-modeled systems and to govern actions expressed through the Third Protocol:



\- PERCEPTION\_MAP consumes SGF Synapses, frames, and external telemetry via ENVIRONMENT\_INTERFACE\_POINT and DATA\_TYPE\_SCHEMA.  

\- GOVERNANCE\_RULE evaluates proposed changes expressed as STATE\_TRANSITIONs over SGF objects and external resources.  

\- TRUST\_ELEMENT binds SGF identities (agents, organizations, keys) to specific scopes, credentials, revocation procedures, and accountability chains.  

\- HFF and AFP carry Omega-relevant state (for example, AuthorityFrame, ReasoningContext, risk classifications) into and out of the governed system; Omega verdicts determine whether AFP acts may be executed.



Omega does not replace SGF or the protocols. SGF represents what is. HFF moves meaning. AFP acts with meaning. Omega governs what may be done with those capabilities.



\## 8. Normative references and examples



This language specification defines the logical model and integration points. For full implementation and conformance:



\- 03-OMEGA-02\_FORMAL\_GRAMMAR\_SPEC.md defines the canonical lexical grammar, keyword set, and EBNF.  

\- 03-OMEGA-03\_IMPLEMENTERS\_GUIDE.md defines required static and runtime checks for evaluators.  

\- 03-OMEGA-04\_EXTENSION\_GOVERNANCE.md defines how the language may grow while preserving its Constitutional core.  

\- `support/03-OMEGA\_WORKED\_EXAMPLES.md` provides non-normative but recommended test cases that every evaluator should be able to parse and evaluate.



An Omega implementation is considered conformant when a deterministic evaluator can:



\- Load the canonical grammar.  

\- Accept the positive example specifications and reject the documented negative snippets.  

\- Produce the documented verdicts for the worked examples given the same inputs and state.

