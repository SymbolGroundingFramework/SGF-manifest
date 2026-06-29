## What Is SGF?

**SGF — the Symbol Grounding Framework — is an open, public-domain system for grounded machine meaning.** It is the first complete stack that unifies four traditionally separate concerns into a single, coherent framework: a formal ontology, a verifiable knowledge graph, a governance language, and a wire protocol.

SGF answers a fundamental question that no prior system has fully addressed: *How can two machines that have never met exchange meaning — not just data — with confidence, without a central authority, and without custom integration?*

The answer is a framework built on six axioms, four layers, and a disciplined set of speech acts.

---

### The Four Layers

**1. A Formal Ontology**

The SGF Lexicon defines what can be said. It organizes all meaning along four orthogonal planes:

- **EXISTENCE** — entities, objects, substances, beings
- **EVENT / PROCESS** — actions, changes, occurrences
- **RELATION** — structural, causal, temporal connections
- **PROPERTY** — attributes that inhere in entities

These planes are not specializations of one another. They are distinct modes of being. Every statement in SGF tethers to exactly one plane.

The lexicon uses four foundational relation types to structure knowledge:

- **Mereology** — part-whole and type-subtype relationships
- **Topology** — spatial and temporal containment
- **Causality** — cause-effect and enablement chains
- **Dependence** — ontological grounding (e.g., an event depends on its participants)

This is not a flat taxonomy. It is a multi-axial space where every term has coordinates.

**2. A Verifiable Knowledge Graph**

Every statement in SGF carries its own:

- **Identity** — a unique, immutable Synapse ID
- **Dependencies** — prerequisite statements that must be satisfied
- **Cryptographic integrity** — a hash that binds content, dependencies, and identifier
- **Provenance** — who said it, when, and under what governance lineage

This means you can trust what you read without needing to trust the source. The statement itself carries the evidence of its own validity. Tampering is detectable. Missing dependencies are detectable. The graph is self-verifying.

**3. A Governance Language**

Meaning is not static. It evolves. SGF defines a clear lifecycle for every statement:

- **Creation** — a new statement enters the system
- **Update** — a statement is revised while preserving its lineage
- **Deprecation** — a statement is marked as no longer recommended
- **Retirement** — a statement is removed from active use

No central authority controls this process. Governance is distributed. Every participant follows the same rules for who can say what and how conflicts are resolved. The framework defines the rules of the game, not who plays it.

**4. A Wire Protocol**

The HFF (Hypergraph Framing Format) is the envelope that wraps every statement for transmission. It carries:

- The statement's identity and content
- The intended recipient scope
- The cryptographic proof of integrity
- The dependency declarations

The AFP (Act Framework Protocol) defines exactly thirteen acts that two machines can perform:

- **INFORM** — assert a statement
- **REQUEST** — ask for a statement
- **COMMAND** — direct an action
- **ADMIT** — accept a statement into local knowledge
- **REFUSE** — reject a statement with reason
- And eight others covering query, subscription, retraction, and governance operations

Two strangers can coordinate meaning in real time without prior integration. The protocol handles everything from a simple assertion to a multi-step negotiation.

---

### The Six Axioms

Every legitimate statement in SGF must satisfy these six axioms:

| # | Axiom | Meaning |
|---|-------|---------|
| 1 | **Identity** | Every statement has a unique, immutable identifier. No two distinct statements share the same ID. |
| 2 | **Grounding** | Every statement must tether to at least one entity in one of the orthogonal planes. All content ultimately traces to primitive referents. |
| 3 | **Dependency** | Every statement may declare dependencies on other statements. A statement cannot be considered valid unless its dependencies are satisfied and verified. |
| 4 | **Integrity** | Every statement has a cryptographic digest that binds its content, its dependencies, and its identifier. Any tampering breaks the digest. |
| 5 | **Sovereignty** | Every receiver has the sovereign right to ADMIT or REFUSE any statement according to its own local policies. No statement can force acceptance. |
| 6 | **Governance** | Every statement belongs to a governance lineage with clear rules for creation, update, deprecation, and retirement. No central authority is required. |

---

### What SGF Is Not

- SGF is **not** a database. It is a protocol for exchanging meaning.
- SGF is **not** a centralized registry. Governance is distributed.
- SGF is **not** a replacement for existing ontologies. It is a framework that can wrap and ground them.
- SGF is **not** a programming language. It is a specification that any language can implement.

---

### Why It Matters

Before SGF, machine meaning was fragmented. Ontologies defined what things are but could not verify claims. Knowledge graphs stored facts but could not prove their integrity. Protocols moved data but could not coordinate meaning. Governance was either absent or centralized.

SGF unifies all four. It is the first stack that lets two strangers exchange grounded meaning — with identity, proof, dependency resolution, receiver sovereignty, and a clear lifecycle — all without a central authority.

It is HTTP for semantics. It is DNS for meaning. It is the missing layer that makes machine-to-machine communication truly intelligent.

---

**SGF is open. It is public domain. It is ready to implement.**

---

## Repository Contents

This repository serves as the central manifest for SGF technical specifications and documentation.

### Documentation & Quick Starts

* **[SGF in a Nutshell](https://github.com/SymbolGroundingFramework/SGF-manifest/blob/main/SGF_IN_A_NUTSHELL.md)**: A high-level introduction to the framework.
* **[The Shape of Meaning](https://github.com/SymbolGroundingFramework/SGF-manifest/blob/main/THE_SHAPE_OF_MEANING.md)**: The white paper on the SGF that explains the reasons *why* behind the architecture.
* **[Technical Overview](https://github.com/SymbolGroundingFramework/SGF-manifest/blob/main/TECHNICAL_OVERVIEW.md)**: A deep dive into the architecture.
* **[Context for Systems & LLM Assistants](https://github.com/SymbolGroundingFramework/SGF-manifest/blob/main/SGF_CONTEXT_FOR_SYSTEMS_AND_LLM_ASSISTANTS.md)**: Context about SGF for prompting AI agents.
* **[Backstory](https://github.com/SymbolGroundingFramework/SGF-manifest/blob/main/BACKSTORY.md)**: The origin of SGF (excerpted from *The Architecture of Meaning*, Volume 1).

### Technical Specifications

* **[RFC specifications](https://github.com/SymbolGroundingFramework/SGF-manifest/tree/main/specs)**: Contains formal, RFC-style technical specifications for the SGF architecture.

### Book Series

You can access the full SGF six-volume book series in digital format (free) or via print:

* **[PDF Manuscripts](https://github.com/SymbolGroundingFramework/SGF-manifest/tree/main/books)**: Downloadable copies of all volumes.
* **[Amazon](https://www.amazon.com/dp/B0H3FGSPK6)**: Order physical print copies.

---

*License: This project is published under the [Apache 2.0 License](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2FSymbolGroundingFramework%2FSGF-manifest%2Fblob%2Fmain%2FLICENSE).*


