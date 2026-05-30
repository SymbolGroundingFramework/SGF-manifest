# Omega Extension Governance v1.0 Final Candidate

File: 03-OMEGA-04_EXTENSION_GOVERNANCE.md  
Layer: OMEGA (governance grammar)  
Status: Final Candidate

## 0. Relationship to the Omega spec family

This document governs extensions to the Omega language: which elements sit at the Constitutional tier, how META_DEFINITION_RULE may be used to extend vocabulary and patterns, and how extensions are proposed, ratified, and revoked. It must be read together with:

- 03-OMEGA-01_LANGUAGE_SPEC.md (language model and primitives)  
- 03-OMEGA-02_FORMAL_GRAMMAR_SPEC.md (lexical grammar and EBNF)  
- 03-OMEGA-03_IMPLEMENTERS_GUIDE.md (evaluator behavior)

## D.1 The Constitutional Frame

A specification that defines a closed grammar without naming its amendment procedure invites the wrong reading. Closure plus silence reads as closure-and-fragmentation. Two implementers hit the same gap, neither sees a sanctioned path, both fork. The substrate the language was meant to provide collapses into dialects.

Omega does not have that problem. The amendment mechanism is `META_DEFINITION_RULE`, specified in Appendix A Section A.6.13 and discussed in A.11. The tier structure that distinguishes amendable provisions from unamendable ones is derived in Chapter 14 from the syntactic placement of `MUTATION_RULE`. The split between meta-primitives and object-primitives is named in Appendix A Section A.6. These three together compose a constitutional language: its growth is delegated through a named primitive, the primitives themselves sit at the Constitutional tier, and the four meta-primitives govern the rest.

What has been missing is a governance envelope around the public exercise of `META_DEFINITION_RULE`. The mechanism is in the spec. The procedure for using it on shared canonical vocabulary is what this appendix specifies. The honest declaration is that the spec voluntarily binds itself: it grants extension authority, but it grants it through a named procedure, with named layers, named limits, and named recovery paths.

## D.2 Extensions as META_DEFINITION_RULE Invocations

Every sanctioned extension to Omega is, formally, an invocation of `META_DEFINITION_RULE`. There is no parallel mechanism. An extension that bypasses `META_DEFINITION_RULE` is, by Chapter 14's distinction, a coup against the language rather than an amendment to it.

Each extension declaration must satisfy four conditions:

1. The declaration uses `META_DEFINITION_RULE`, with `TARGET_TYPE` naming the extensible category being enlarged (`ModalityType`, `ResourceTypeID`, `InteractionTypeID`, `TargetTypeID`, `MetricID`, `PropertyID`, or any other category Appendix A admits as extensible).
2. The declaration is scoped to a profile. No extension is implicitly global. A program that does not import the extension must continue to parse, validate, and execute identically to a program written before the extension existed.
3. The declaration is governance-checked. The trust elements and accountability chains that apply to primitive instances apply to extension declarations. A `GOVERNANCE_RULE` whose scope covers extension declarations may approve, reject, or return UNKNOWN on a candidate. UNKNOWN means the contract cannot decide, and the extension is provisional pending stewardship review.
4. The declaration is backward-compatible at the profile boundary. Removing the extension's import must restore the program to a parseable, executable state under the prior vocabulary.

These four conditions are the safety kernel for language evolution. They use the same PASS, REJECT, UNKNOWN vocabulary the rest of the spec uses for runtime governance. The fractal signature is preserved.

## D.3 Five Extension Layers and the Reach by Reversibility Map

Extensions are not uniform in cost. They differ along two axes: how much of Omega the extension touches (reach), and whether the extension can be deprecated without breaking dependent profiles (reversibility).

Five layers are named:

- **Composition pattern libraries.** Named, reusable composite structures, the SQL/JOIN analogy already drawn in Appendix A.7. Low reach, high reversibility. Lowest review threshold.
- **Domain ontologies.** Versioned vocabulary packages for specific application domains. Medium reach, high reversibility. Each domain ontology must declare its versioning scheme and a translation contract for cross-version interoperation.
- **Resource type extensions.** New cost dimensions beyond the canonical set in `RESOURCE_BOUND`. Medium reach, medium reversibility. Each resource type extension must specify monotonicity behavior with respect to existing cost calculations.
- **Proof protocol extensions.** Alternate verification regimes for `TRUST_ELEMENT`. High reach, low reversibility once trust elements depend on the regime in deployed profiles.
- **Modality extensions.** New entries in the `MODALITY` vocabulary of `CONTEXT_RULE`, including epistemic and deontic operators beyond the canonical set. High reach, low reversibility, and the hardest case. Each modality extension must include a semantic conservativity argument: the extension must not silently change the truth conditions of programs that do not import it.

The contract in D.2 is uniform across all five layers. The review burden is not. A composition pattern library is approvable by any party with a stewardship role. A modality extension requires a process closer to a constitutional convention.

## D.4 Unamendable Cores

The Constitutional tier of the spec is what no extension may touch. Per Chapter 14, the 13 primitive declarations themselves and the EBNF productions of the core grammar sit at the Constitutional tier. To these, Appendix D adds:

- The safety kernel pattern (PASS, REJECT, UNKNOWN as the universal verdict shape).
- The four meta-primitives' identities and their meta-level role. An extension may enlarge the vocabulary slots of meta-primitives. It may not redefine what they are.
- The two-profile structure (Strict and Extended), including the static-decidability requirement of Strict.
- This appendix itself.

These are the spec's voluntary self-binding. No `META_DEFINITION_RULE` invocation may target them. A specification that attempts such targeting is not a malformed extension. It is a different language wearing Omega's syntax.

## D.5 Standing, Proposal, Ratification, Predictive Impact Modeling

Standing to propose an extension is open. Any party may draft a `META_DEFINITION_RULE` invocation and circulate it. Standing to ratify an extension into the canonical vocabulary is not open. Ratification requires:

1. **A rationale record.** A structured artifact answering: what gap does this extension fill, what alternatives were considered, why this design. The rationale record becomes part of the canonical lineage. A ratified extension without a rationale record is malformed.
2. **Predictive impact modeling.** Before ratification, the candidate extension must be evaluated against the canonical worked-example corpus (Appendix B) and against any registered profile that declares a dependency on the extensible category. The evaluation produces a PASS, REJECT, or UNKNOWN verdict. UNKNOWN blocks ratification pending further analysis.
3. **Stewardship approval.** The threshold scales with the layer's position on the reach by reversibility map of D.3.

The separation of standing from ratification is load-bearing. Open proposal makes the canon legible. Closed ratification protects the substrate.

## D.6 Conflicts, Profile Compatibility, Emergency Revocation

Two ratified extensions may produce conflicting verdicts on the same construct. The resolution mechanism is the priority structure already specified in Appendix A: `GOVERNANCE_RULE` carries an optional numeric `PRIORITY` field with a default of 0; higher numeric values take precedence; when two firing rules share the same priority, conformant evaluators apply deterministic ordering by `RuleID` lexicographically. Extensions that anticipate conflict declare `PRIORITY` explicitly. The mechanism is unchanged for extensions; only its application is.

Profile compatibility is negotiated at load time. A program declares which extensions it depends on. A runtime that does not have the required extensions available rejects the program at load time with a structured diagnostic. Silent fallback is not permitted.

Emergency revocation pulls a ratified extension from the canonical vocabulary. The mechanism is `TRUST_ELEMENT REVOCATION_PROTOCOL`, applied to the extension's defining `META_DEFINITION_RULE`. Revocation requires a structured cause and produces a structured remediation path for affected profiles. Revocation is irreversible at the canonical level: a revoked extension may be reproposed only as a new extension with a new identifier and a new rationale record.

## D.7 Self-Reference Closure and Versioning

Appendix D itself sits at the Constitutional tier. The procedure specified here cannot be modified by the procedure specified here. A `META_DEFINITION_RULE` invocation that attempts to target Appendix D's clauses is rejected at parse time on the same structural grounds that reject targeting of the 13 primitive declarations.

Changes to Appendix D require a spec version increment. Extensions are versioned independently of the core, using semantic versioning. The stewardship method that governs ratifications, contested interpretations, and emergency revocations operates under the public-domain commitment stated in the series front matter and is documented at the canonical home of the architecture. The method is itself amendable only by passing through the method.

The procedure does not modify the procedure. The grammar of growth is the floor.
