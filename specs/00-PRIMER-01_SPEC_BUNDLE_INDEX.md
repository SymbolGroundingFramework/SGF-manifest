# SGF / Third Protocol / Omega Specification Stack v1.0

File: 00-PRIMER-01_SPEC_BUNDLE_INDEX.md  
Layer: PRIMER  
Status: Final Candidate

This package defines the specification stack for:

- SGF Core (substrate for grounded meaning)
- The Third Protocol (wire and act layers: HFF, AFP, Discovery/Capabilities)
- Omega (governance language)

The books in the `books/` folder explain the concepts. This `specs/` folder is the canonical home of the formal specifications.

## 1. Files by layer

### 1.1 Substrate (01-SUBSTRATE-*)

Logical meaning model and ingestion.

| File | Purpose |
| --- | --- |
| `01-SUBSTRATE-01_SGF_CORE_SPEC.md` | Logical meaning model for grounded claim-bearing structure (Synapses, frames, Core Lexicon integration) |
| `01-SUBSTRATE-02_LEXICON.md` | Core Lexicon logical data model, canonical IDs, and grounding relations |
| `01-SUBSTRATE-03_GLEAN_PROCESS_SPEC.md` | GLEAN ingestion process from CleanTextBundle into SGF objects |
| `99-KNOWLEDGE_PACK_SPEC.md` | Versioned, signed Knowledge Pack bundles for SGF-compatible knowledge and lexicons |

### 1.2 Wire and acts (02-WIRE-*)

Transport and act layers over SGF Core.

| File | Purpose |
| --- | --- |
| `02-WIRE-01_HFF_WIRE_PROTOCOL_SPEC.md` | HFF wire transport of SGF objects across trust boundaries |
| `02-WIRE-02_AFP_PROTOCOL_SPEC.md` | AFP act and conversation protocol over HFF |
| `02-WIRE-03_DISCOVERY_CAPABILITY_MANIFEST_SPEC.md` | Participant and capability discovery manifest |

Non-normative support documents (simulation scenarios, protocol test suites, walkthroughs) live under `support/` and reference these specs.

### 1.3 Omega governance language (03-OMEGA-*)

Typed governance grammar for what may be done.

| File | Purpose |
| --- | --- |
| `03-OMEGA-01_LANGUAGE_SPEC.md` | Omega language model, primitive set, profiles, evaluator obligations, and relationship to SGF/HFF/AFP |
| `03-OMEGA-02_FORMAL_GRAMMAR_SPEC.md` | Canonical lexical grammar, keyword set, and EBNF for Omega-Code |
| `03-OMEGA-03_IMPLEMENTERS_GUIDE.md` | Required static and runtime checks for Omega evaluators, profile enforcement, and determinism requirements |
| `03-OMEGA-04_EXTENSION_GOVERNANCE.md` | Extension and versioning governance for Omega primitives, vocabulary, and composition patterns |

Worked examples for Omega live in `support/03-OMEGA_WORKED_EXAMPLES.md`.

### 1.4 Cross-cutting documents (99-*)

Shared policies and examples that apply across layers.

| File | Purpose |
| --- | --- |
| `99-CONFORMANCE_REQUIREMENTS.md` | Conformance requirements across substrate, wire, and Omega |
| `99-EXAMPLES.md` | Compact worked examples across the SGF and protocol stack |
| `99-VERSIONING_POLICY.md` | Versioning, extensions, and compatibility policy for the spec stack |
| `99-KNOWLEDGE_PACK_SPEC.md` | Knowledge Pack packaging spec (also referenced from the substrate layer) |

## 2. Layer boundary

```text
Substrate (01-SUBSTRATE-*):
  Core Lexicon, Synapses, frames, GLEAN, Knowledge Packs.

Wire and acts (02-WIRE-*):
  HFF wire transport, AFP acts, Discovery/Capability Manifest.

Omega (03-OMEGA-*):
  Typed governance grammar (Omega-Code) for what may be done.

Cross-cutting (99-*):
  Conformance, examples, versioning, and shared packaging.
```

## 3. Governing principles

- SGF is a substrate for grounded, claim-bearing structures, not a total container for all meaning.
- Synapse grammar is fixed: one VerbHub plus many role-bound Spokes.
- The 15 semantic roles are closed in SGF Core 1.0. [file:371]
- GLEAN consumes CleanTextBundle, not raw text. [file:371]
- HFF moves meaning; AFP acts with meaning. [file:375][file:373]
- Omega governs what may be done through typed grammar, not prose. [file:377]
- Storage and query execution are backend-neutral. [file:371]
- Provenance, proof, perspective, trust, and gaps are part of the model, not afterthoughts. [file:371]