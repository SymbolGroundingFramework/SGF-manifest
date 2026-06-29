# Synapedia Architecture Specification

## Version 1.3 — July 2026

### A Four-Layer Lexicon for Grounded Concept Definitions

### Substrate Layer of the Symbol Grounding Framework (SGF)

---

**Status:** Specification  
**Date:** 2026-07-01  
**Authors:** SGF Architecture Review Board  
**License:** Creative Commons Attribution 4.0 International  

---

## Table of Contents

1. Preamble
2. Definitions of Primitives
3. Postulates
4. Axioms
5. Theorems
6. Metaphysical Commitments
7. Identity Criteria
8. Deprecation and Versioning Protocol
9. Conflict Resolution for Inherited Event Scripts
10. The Four Layers
11. The 15 Semantic Roles
12. Canonical IDs
13. Event Sourcing and Authority
14. Grounding and Validation
15. Knowledge Packs
16. Scope and Limits
17. Verification Depth as a Policy Decision
18. Grounding Non-Physical Entities
19. Comparison to Existing Systems
20. Exemplaries
21. Proof of Concept Walkthrough
22. Appendices
23. References

---

## Section 1: Preamble

### 1.1 Name

This document specifies the **Synapedia Architecture**, the Substrate Layer of the SGF.

### 1.2 Purpose

Synapedia provides machine-addressable concept definitions for the purpose of grounding natural language claims into a structured, verifiable lexicon. It replaces the traditional separation of lexicon and ontology with a unified four-layer structure.

**Framing:** Synapedia is a **lexicon** — a new kind of machine-readable dictionary — not a knowledge graph. It does not store assertions about the world. It stores definitions. Truth, falsehood, and conflicting claims belong to the ABox (see Section 2.18).

**Architectural Innovation:** Synapedia collapses the traditional TBox/ABox divide by embedding active, hub-and-spoke event structures directly into concept definitions. In legacy semantic web systems, the TBox (schema) was frozen and could not capture time or change, while the ABox (instances) was chaotic and ungrounded. Synapedia resolves this by making the definition layer itself dynamic — events are native to the TBox, not bolted on as instance data.

### 1.3 Scope

This specification defines:

- The structural components of a Synapedia entry (Nodes, Edges, Layers, Synapses)
- The grammar of Canonical IDs
- The closed set of semantic roles
- The postulates and axioms that constrain the graph
- The validation rules that entries must satisfy
- The relationship between Synapedia and other SGF layers (ABox, Knowledge Packs, Frames)

This specification does **not** define:

- The transport protocol for Synapedia entries
- The query language for accessing Synapedia data
- The governance model for entry authorship
- The implementation roadmap (see Appendix A)

### 1.4 Conformance

An implementation must conform to all Axioms (Section 4) and all Postulates (Section 3). An implementation should conform to all validation rules (Section 13). An implementation may extend the specification only by adding Knowledge Packs; it must not modify the core structure.

### 1.5 Document Conventions

- **Must** indicates a mandatory requirement.
- **Should** indicates a recommended requirement.
- **May** indicates an optional feature.
- **Must not** indicates a prohibition.

---

## Section 2: Definitions of Primitives

### 2.0 What a Definition Is (and Is Not)

A **definition** in Synapedia is the complete set of structural elements — Lexical, Ontological, Mereological, and Perdurantist — that uniquely identifies a concept within its language and lemma-mate set. A definition is not a string. It is a graph.

**Lemma Collapse** is the systemic inability to reliably separate distinct conceptual senses when they share identical surface text. Every lexicon that lacks event-grounded definitions suffers from Lemma Collapse. Synapedia eliminates it by requiring a Perdurantist layer for every concept that has lemma-mates.

A Synapedia definition does the following:

- It **anchors** the concept to a surface form (lemma, part of speech).
- It **positions** the concept within a type hierarchy (IS-A parents).
- It **composes** the concept if composition is load-bearing for identity (mereology).
- It **discriminates** the concept from all others sharing its lemma (Perdurantist events).

A Synapedia definition does **not** do the following:

- It does not provide a natural language sentence that "explains" the concept (a gloss is optional, not definitional).
- It does not enumerate all properties of the concept (encyclopedic knowledge belongs in Knowledge Packs).
- It does not provide truth conditions for assertions using the concept (truth is the domain of the ABox).

**This is not a glossary.** In a glossary, a definition is a sentence that can be read by a human. In Synapedia, a definition is a machine-addressable graph structure with four layers, each of which is independently verifiable against the axioms of the system. A human-readable gloss may be attached to the Lexical layer for convenience, but it is not the definition. The definition is the structure.

### 2.1 Node

A **Node** is the fundamental unit of the Synapedia graph. Every Node has exactly one Canonical ID (Section 2.3) and belongs to exactly one Layer (Section 2.6).

**Constraint 2.1.1:** No two Nodes may share the same Canonical ID.

**Constraint 2.1.2:** Every Node that is not in the Prime Registry must have at least one outgoing IS-A Edge (Section 2.2.1).

**Constraint 2.1.3:** Every Node must satisfy the Foundational Grounding Axiom (Axiom II).

### 2.2 Edge

An **Edge** is a directed, labeled connection from one Node (the source) to another Node (the target). Every Edge has exactly one type drawn from the closed set defined in Table 2.2-1.

**Table 2.2-1: Allowed Edge Types**

| Category | Type | Direction | Inverse |
|---|---|---|---|
| Ontological | `IS-A` | child → parent | `HAS-SUBCLASS` (derived) |
| Mereological (Component) | `HAS-COMPONENT` | whole → part | `COMPONENT-OF` |
| Mereological (Member) | `HAS-MEMBER` | collection → member | `MEMBER-OF` |
| Mereological (Portion) | `HAS-PORTION` | mass → portion | `PORTION-OF` |
| Event (Synapse Internal) | The 15 Role types | See Section 11 | None |
| Historical/Trace | `SUPERSEDED-BY` | deprecated → replacement | `SUPERSEDES` |
| Cross-Lingual | `TRANSLATION-OF` | source → target | `TRANSLATION-OF` (symmetric) |

**Design Note 2.2.1 — IS-A Subsumption Typology:** The IS-A relation encompasses several subsumption modalities: taxonomic (biological kind), functional (purpose), professional (occupation), constitutive (material), and mereological (part-of-whole). A single `IS-A` edge type is used for all; an optional `subsumption_type` annotation may refine the relationship when needed. The core axiom of acyclicity applies regardless of subtype.

**Constraint 2.2.1:** No Edge may have a type outside this set. This is the Invariant Edge Constraint (Postulate III).

**Constraint 2.2.2:** `IS-A` Edges must form a directed acyclic graph. No cycles are permitted.

**Constraint 2.2.3:** `SUPERSEDED-BY` Edges must not form a cycle.

### 2.3 Canonical ID

A **Canonical ID** is a globally unique string identifier conforming to the following grammar:

```
canonical_id ::= "sgf:" language_tag "." lemma "." pos "." microgloss
language_tag ::= [a-z]{2} | [a-z]{3} | "xx"
lemma ::= [a-z][a-z0-9_]+
pos ::= "n" | "v" | "adj" | "adv" | "prep" | "conj" | "det" | "pron" | "intj" | "num" | "aux" | "part" | "prop"
microgloss ::= [a-z][a-z0-9_-]+
```

**Examples:** `sgf:en.wagon.n.horse_drawn_cargo`, `sgf:en.compose.v.create_music`, `sgf:en.beethoven.n.composer_1770`, `sgf:xx.prime.one.n.basic_primitive`.

**Constraint 2.3.1:** A Canonical ID, once assigned, is immutable. It must not be reassigned. This is the Reference Stability Postulate (Postulate IV).

**Constraint 2.3.2:** The microgloss component must uniquely identify the Node within the set of all Nodes sharing the same language_tag, lemma, and pos.

### 2.4 Lemma

A **Lemma** is the canonical surface form of a word in a given language. For nouns, the Lemma is the singular nominative form. For verbs, the Lemma is the infinitive form. For adjectives, the Lemma is the positive form. Exceptions are permitted for languages where these conventions do not apply, documented in a language-specific appendix.

### 2.5 Microgloss

A **Microgloss** is the shortest string that distinguishes this Node from all other Nodes sharing the same Lemma and part of speech within the same language.

**Rule 2.5.1:** A Microgloss must be between 1 and 4 words (inclusive), separated by underscores.

**Rule 2.5.2:** A Microgloss must not contain the Lemma string.

**Rule 2.5.3:** A Microgloss must satisfy the Microgloss Sufficiency Axiom (Axiom IV).

### 2.6 Layer

A **Layer** is one of four orthogonal categorical partitions of the Node set. Every Node belongs to exactly one Layer.

**Table 2.6-1: The Four Layers**

| Layer | Primary Content | Edge Types |
|---|---|---|
| `LEXICAL` | Lemma, POS, gloss, microgloss, embedding | None (terminal) |
| `ONTOLOGICAL` | IS-A parent references | `IS-A` only |
| `MEREOLOGICAL` | Part-whole composition | `HAS-COMPONENT`, `HAS-MEMBER`, `HAS-PORTION` |
| `PERDURANTIST` | Minimal discriminating Synapses | Synapse-internal Role Edges only |

**Constraint 2.6.1:** No Node may belong to more than one Layer.

**Constraint 2.6.2:** A Node's Layer is determined at creation and is immutable.

### 2.7 Synapse

A **Synapse** is a structured bundle of Edges representing a single event or state. It consists of:

1. A VerbHub Node (required, exactly one)
2. A set of Spokes (required, one or more)
3. Optionally, a set of Frame references

**Constraint 2.7.1:** A Synapse must contain at least one Spoke and at most 15 Spokes (one per Role type).

**Constraint 2.7.2:** No two Spokes in the same Synapse may use the same Role type.

**Constraint 2.7.3:** The VerbHub must be a Node in the Lexical Layer with a verb part of speech.

### 2.8 VerbHub

A **VerbHub** is the central Node of a Synapse. It determines the event type and constrains which Roles may be used. The VerbHub must be a Node with part of speech `v` and must be grounded (Axiom II).

### 2.9 Spoke

A **Spoke** is a single Role Edge within a Synapse. It connects the VerbHub to a participant Node via exactly one Role type. The participant Node must be a valid Synapedia Node.

### 2.10 Frame

A **Frame** is an optional metadata object that attaches to a Synapse to refine its interpretation without altering its structure. Frames are defined in Knowledge Packs, not in Synapedia.

### 2.11 Grounding

**Grounding** is the property of a Node having a valid directed path via IS-A Edges to either a Node in the Prime Registry or a fixed spacetime coordinate.

**Constraint 2.11.1:** Every Node must be grounded (Axiom II).

### 2.12 Prime Registry

The **Prime Registry** is the set of foundational Nodes that are given, not defined. The set is non-empty (Postulate I). Prime Registry Nodes have the language tag `xx` and have no IS-A parents.

### 2.13 Knowledge Pack

A **Knowledge Pack** is a signed, versioned bundle of SGF objects — Synapses, Groups, Frames — that attach to Synapedia Nodes via their Canonical IDs. Knowledge Packs do not modify Synapedia entries.

**Constraint 2.13.1:** A Knowledge Pack must not contain Nodes that claim to be in any Synapedia Layer.

**Constraint 2.13.2:** A Knowledge Pack must not add `IS-A` Edges to the Synapedia graph.

### 2.14 Lemma-Mate

Two Nodes are **Lemma-Mates** if they share the same Lemma and the same part of speech within the same language tag.

**Constraint 2.14.1:** No two Lemma-Mates may share the same Microgloss.

**Constraint 2.14.2:** No two Lemma-Mates may have identical Perdurantist layers. If they do, they are the same concept and must be merged.

### 2.15 SELF Reference

`SELF` is a reserved reference operator used within a Node's own Perdurantist layer. It resolves to the Canonical ID of the containing Node.

**Constraint 2.15.1:** `SELF` may only appear in the Perdurantist layer of a Node. It must not appear in any other context.

**Constraint 2.15.2:** `SELF` is not a Node. It has no Canonical ID, no Layer, and no properties.

**Constraint 2.15.3:** When a Synapse containing `SELF` is inherited by a child Node (via IS-A), `SELF` resolves to the child Node, not the parent.

### 2.16 Temporal Coordinate

A **Temporal Coordinate** is a value used in the `HAS_TIME` Role. It must be one of the following types:

- **Point:** An ISO 8601 datetime string. Precision may vary.
- **Interval:** A tuple `(start, end)` using ISO 8601 format.
- **Recurrence Pattern:** A string in a defined recurrence format (e.g., `"every_spring"`).
- **Calendrical Reference:** A Node reference to a time-related concept.

**Constraint 2.16.1:** A Temporal Coordinate must resolve to a specific time or range at query time.

**Constraint 2.16.2:** Temporal Coordinates are grounded through their relationship to standardized time scales, which are grounded in the Prime Registry via `time.n.physical_dimension`.

### 2.17 Event Identity

Two Synapses are the **same event** if and only if all of the following conditions hold:

1. **Same VerbHub:** Both Synapses use the same VerbHub Node (same Canonical ID).
2. **Same Role-Participant Mapping:** For every Role that appears in both Synapses, the participant Nodes are identical.
3. **Same Time:** Both Synapses have the same `HAS_TIME` value, or neither specifies one.
4. **Same Location:** If both specify `HAS_LOCATION`, the locations are the same Node.

**Constraint 2.17.1:** Event identity does not require identical Frames. Two Synapses with different Frame interpretations are the same event if the structural core matches.

**Constraint 2.17.2:** Two Synapses that are identical in structure but appear in different Knowledge Packs refer to the same event unless explicitly marked as distinct.

### 2.18 ABox (Assertional Box)

The **ABox** is the layer of SGF that stores claims — assertions about the world. Claims can be true, false, mistaken, deliberately deceptive, contradictory, or hypothetical. The ABox does not decide truth. It stores what was said, by whom, and under what conditions.

**Constraint 2.18.1:** The ABox references Synapedia Canonical IDs for all concept references. It does not define concepts.

**Constraint 2.18.2:** Synapedia does not reference the ABox. The relationship is one-way.

**Design Note 2.18.1 — Asymmetric Dependency Vector:**

The relationship between Synapedia and the ABox is strictly one-way:

```
       ┌────────────────────────────────────────────┐
       │         SYNAPEDIA (Definition Core)         │
       │  - Lexicon, Taxonomy, Mereology, Events     │
       └─────────────────────▲──────────────────────┘
                             │
                             │ (One-Way Lightweight Pointers)
                             │
       ┌─────────────────────┴──────────────────────┐
       │         ABox (Transaction Ledger)           │
       │  - Raw event streams, zero descriptive text │
       └────────────────────────────────────────────┘
```

The ABox contains no descriptive metadata. It stores only skeletal wire frames — Canonical IDs and role assignments — and hydrates meaning by referencing Synapedia on demand.

**Constraint 2.18.3:** A claim in the ABox may be contradicted by another claim. This is not an error. Truth is a negotiation that happens above both layers.

**Example ABox synapse:**
```json
{
  "id": "abox:claim.20260628.001",
  "assertion": {
    "subject": "sgf:en.defendant.n.person_accused",
    "predicate": "sgf:en.drive.v.operate_vehicle",
    "object": "sgf:en.car.n.motor_vehicle",
    "manner": "sgf:en.speed_limit.n.legal_maximum"
  },
  "attribution": {
    "source": "testimony_001",
    "timestamp": "2026-06-28T14:30:00Z",
    "confidence": "claimed"
  }
}
```

### 2.19 The Orthogonal Dual-Axis Split

Synapedia organizes meaning across two independent geometric planes:

- **Y-Axis (Object/Material Logic):** Governs structural lineage (IS-A) and physical or conceptual composition (HAS-COMPONENT, HAS-MEMBER, HAS-PORTION). This axis tracks what things *are* and how they are *built*, independent of action or time. It covers the Lexical, Ontological, and Mereological layers.

- **X-Axis (Event/Action Logic):** Governs dynamic changes, behaviors, and situational occurrences using a centralized VerbHub bound to radiating Spokes. This axis tracks what things *do* and what happens to them. It covers the Perdurantist layer.

The two axes are orthogonal. A concept's identity is fully specified only when both axes are resolved. A wagon is not fully defined by its Y-axis position (vehicle, container, wheels, axle) — it requires its X-axis position (transports, pulls, rolls) to be distinguished from a cart or a sled.

**Constraint 2.19.1:** Every Node must have at least one axis populated. A Node with only a Lexical layer (no IS-A parents, no mereology, no events) is permitted only if it is in the Prime Registry.

---

## Section 3: Postulates

Postulates are constructional assumptions. They are not proved within the system.

### Postulate I — Existence of Primitives

There exists a non-empty set of Nodes called the Prime Registry. All other Nodes derive their Grounding from paths to this set.

### Postulate II — Categoricity

Every Node belongs to exactly one of the four Layers. No Node may belong to more than one Layer.

### Postulate III — The Invariant Edge Constraint (Edge Exclusivity)

The allowed Edge types are exactly those listed in Table 2.2-1. No Edge outside this set may exist. No Edge of one type may be interpreted as another.

While the vocabulary of nouns and verbs is infinitely open, the relational links connecting an event hub to its participants are permanently restricted to exactly 15 orthogonal semantic roles. This constraint is invariant. It cannot be extended, modified, or overridden by any Knowledge Pack or downstream system.

### Postulate IV — Reference Stability

A Canonical ID, once assigned, is immutable. It may not be reassigned to a different concept.

### Postulate V — Polyhierarchy Permission

A Node may have zero or more IS-A parents. No upper bound is imposed. No parent is primary.

### Postulate VI — Event Closure

All event information in Synapedia is expressed using exactly the 15 Role types defined in Section 11. The set is closed.

### Postulate VII — Graph Finitude

The Synapedia graph contains a finite number of Nodes and Edges. All graph algorithms terminate in finite time.

### Postulate VIII — Language Independence

The structural content of a Node (IS-A parents, Mereological Edges, Synapses) is language-independent. Two Nodes in different languages that refer to the same concept are connected by a `TRANSLATION-OF` Edge.

---

## Section 4: Axioms

Each axiom is a logical constraint that all entries must satisfy.

### Axiom I — Ontological Acyclicity

The directed graph formed by all `IS-A` Edges is strictly acyclic.

### Axiom II — Foundational Grounding

Every Node must have a path via `IS-A` Edges to either a Prime Registry Node or a fixed spacetime coordinate.

### Axiom III — Component Transitivity

The `HAS-COMPONENT` relation over the Component-Integral Whole axis is transitive. This transitivity does not extend to `HAS-MEMBER` or `HAS-PORTION`.

### Axiom IV — Microgloss Sufficiency

Within the set of all Nodes sharing the same language tag, Lemma, and part of speech, no two Nodes may share the same Microgloss. The function `microgloss: L → String` is injective.

### Axiom V — Event Minimality

No Synapse in a Node's Perdurantist layer may be removed while still maintaining disambiguation from all other Nodes sharing the same Lemma and part of speech.

### Axiom VI — Identity Uniqueness

No two distinct Nodes may share the same Canonical ID.

---

## Section 5: Theorems

### Theorem I — Grounding Chains Are Finite

Every grounding chain in the Synapedia graph has finite length.

*Proof:* By Axiom II, every Node has a path to a Prime Registry Node or spacetime coordinate. By Axiom I, the graph is acyclic. By Postulate VII, the graph is finite. Therefore, every path is finite.

### Theorem II — Lemma-Mate Separation

For any two distinct Lemma-Mate Nodes, their Perdurantist layers differ in at least one Synapse.

*Proof:* By Axiom IV, their Microglosses differ. By Axiom V, each Perdurantist layer is minimal. If the layers were identical, the Microglosses would need to differ based on lexical criteria alone, which contradicts the definition of Microgloss as a disambiguation key. Therefore, the layers must differ.

### Theorem III — No Orphan Definitions

Every Node that is not in the Prime Registry has at least one outgoing `IS-A` Edge.

*Proof:* By Axiom II, every Node must have a path to the Prime Registry via `IS-A` Edges. A Node with no outgoing `IS-A` Edges would have no such path unless it were itself a Prime Registry Node.

### Theorem IV — No ID Collisions

No two Nodes may share the same Canonical ID. Directly from Axiom VI.

### Theorem V — Deprecation Does Not Break Grounding

If a Node is deprecated and linked to a replacement via `SUPERSEDED-BY`, the deprecated Node remains grounded. The `SUPERSEDED-BY` Edge is not an `IS-A` Edge; existing `IS-A` paths remain unchanged.

---

## Section 6: Metaphysical Commitments

These commitments describe the philosophical stance of the architecture. They are not enforced by the system but motivate its design.

### 6.1 Perdurantism over Endurantism

Events are first-class citizens. A concept is defined not only by what it is, but by what it does and what happens to it. The Perdurantist layer is load-bearing, not decorative.

#### 6.1.1 Why "Perdurantist"?

The term is borrowed from the philosophical debate about persistence through time.

- **Endurantism** holds that an object is wholly present at every moment of its existence. A wagon *is* a wagon at every instant — the same four-wheeled thing. Change happens to it, but the object itself does not have temporal parts.
- **Perdurantism** holds that an object is spread out across time, having temporal parts (or "stages"). A wagon is not just the static thing at one moment — it is the sum of all its stages, including the events it participates in: being pulled, rolling, transporting cargo. The wagon *perdures* through those events.

Synapedia's Perdurantist layer captures the events, processes, and behaviors that define a concept — the temporal parts without which the concept cannot be distinguished from its lemma-mates. A wagon is not just a static vehicle with wheels; it *perdures* through being pulled, rolling, and transporting cargo. The name signals that our definitions are dynamic, not static.

The other three layers (Lexical, Ontological, Mereological) describe what the concept is *at a single snapshot* — its name, its categories, its parts. The Perdurantist layer describes what the concept *does* — its essential events, the roles it plays, the actions that make it *that* kind of thing rather than another.

### 6.2 Conceptual Realism

Concepts exist independently of their linguistic labels. Two Nodes in different languages that refer to the same concept share a `TRANSLATION-OF` edge. The concept itself is not bound to any language.

### 6.3 Minimalism

A definition is the smallest set of facts that uniquely identifies a concept within its lemma-mate set. Encyclopedic knowledge is not definition.

### 6.4 Fallibilism

Definitions may be wrong. They may be corrected through deprecation and replacement. No information is destroyed; the historical record is preserved.

### 6.5 Groundedness

Every concept must ultimately trace to either a primitive (Prime Registry) or a spatiotemporal location. There are no floating definitions.

### 6.6 Pluralism

A concept may have multiple valid IS-A parents. The system does not force a single taxonomic tree.

### 6.7 Claim Agnosticism

The system does not decide truth. Synapedia defines concepts; the ABox stores claims. Truth, falsehood, contradiction, and deception are all valid in the ABox. The system is structurally neutral toward the truth value of assertions.

---

## Section 7: Identity Criteria

### 7.1 The Identity Rule

Two candidate entries refer to the same concept if and only if all of the following conditions hold:

1. Same Lemma
2. Same part of speech
3. Same language tag
4. Same set of minimally discriminating Perdurantist Synapses

### 7.2 The One-Entry Rule

There must be exactly one entry in Synapedia for each distinct concept within a given language.

### 7.3 Synonymy and Cross-Lingual Identity

Two entries in different languages that refer to the same concept are not the same entry. They have different Canonical IDs and are connected by a `TRANSLATION-OF` edge.

### 7.4 Lemma-Mate Distinctness

Two Lemma-Mates must differ in at least one of: Microgloss, or one or more Synapses in the Perdurantist layer.

---

## Section 8: Deprecation and Versioning Protocol

### 8.1 Immutability of Canonical IDs

Once assigned, a Canonical ID is immutable. It never changes meaning.

### 8.2 Correction Protocol

**Step 1:** Mark the existing Node with status `DEPRECATED`. Create a deprecation record with reason, timestamp, and authority.

**Step 2:** Create a new Node with a new Canonical ID containing the corrected definition.

**Step 3:** Add a `SUPERSEDED-BY` edge from the deprecated Node to the replacement.

**Step 4:** Notify all registered Knowledge Packs that reference the deprecated ID.

### 8.3 Versioning

Synapedia as a whole is versioned at the graph level. Each version is identified by a hash of the entire Node and Edge set. Minor corrections to glosses or embeddings that do not affect the graph structure may be applied without a version increment.

### 8.4 Backward Compatibility

Deprecated IDs are never removed. Any system that relied on a deprecated ID will continue to function. The graph is append-only at the Node level.

---

## Section 9: Conflict Resolution for Inherited Event Scripts

### 9.1 The Problem

When a Node inherits from multiple IS-A parents, those parents may define conflicting Synapses in their Perdurantist layers.

### 9.2 Resolution Rules

Apply the following rules in order. The first rule that resolves the conflict is used.

**Rule 1 — Explicit Override:** If the Node itself defines a Synapse that directly contradicts an inherited Synapse, the Node's own definition wins.

**Rule 2 — Specificity:** If two parents define conflicting Synapses, the parent deeper in the IS-A hierarchy takes priority. Depth is measured as the length of the longest path from the parent to the Prime Registry.

**Rule 3 — Temporal Priority:** If two parents at the same depth define conflicting Synapses, the parent whose Node was created more recently takes priority.

**Rule 4 — Manual Annotation:** If none of the above rules produce a satisfactory result, a human annotator may add a `CONFLICT_RESOLUTION` annotation, which overrides all automatic resolution.

### 9.3 Non-Conflicting Inheritance

If two parents define different Synapses that do not share the same VerbHub, there is no conflict. Both are inherited.

---

## Section 10: The Four Layers

### 10.1 Lexical Layer

#### 10.1.1 Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `canonical_id` | String | Required | Must conform to Section 2.3 |
| `layer` | String | Required | Must be "LEXICAL" |
| `lemma` | String | Required | Canonical surface form |
| `pos` | String | Required | One of the defined POS tags |
| `microgloss` | String | Required | Short disambiguation string |
| `gloss` | String | Optional | Natural language definition (one sentence) |
| `embedding` | Float[] | Optional | Vector embedding |
| `examples` | String[] | Optional | Example sentences |
| `sourcing` | Object | Optional | Source metadata (see Section 13) |

#### 10.1.2 Constraints

**Constraint 10.1.1:** A Lexical Node must have no outgoing Edges.

**Constraint 10.1.2:** A Lexical Node must have a non-empty microgloss.

### 10.2 Ontological Layer

#### 10.2.1 Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `canonical_id` | String | Required | Must conform to Section 2.3 |
| `layer` | String | Required | Must be "ONTOLOGICAL" |
| `is_a` | String[] | Required | Array of parent Canonical IDs |
| `grounding_status` | Enum | Required | "GROUNDED" or "UNRESOLVED" |

#### 10.2.2 Constraints

**Constraint 10.2.1:** Every ID in the `is_a` array must correspond to an existing Node.

**Constraint 10.2.2:** The `is_a` Edges must not create a cycle (Axiom I).

**Constraint 10.2.3:** If `grounding_status` is "UNRESOLVED," the Node must be marked as provisional.

### 10.3 Mereological Layer

#### 10.3.1 Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `canonical_id` | String | Required | Must conform to Section 2.3 |
| `layer` | String | Required | Must be "MEREOLOGICAL" |
| `has_component` | String[] | Optional | Component part IDs |
| `has_member` | String[] | Optional | Member IDs |
| `has_portion` | String[] | Optional | Portion IDs |

#### 10.3.2 Constraints

**Constraint 10.3.1:** A Node must have at least one Mereological field populated to belong to this Layer.

**Constraint 10.3.2:** The `has_component` relation is transitive (Axiom III). The `has_member` and `has_portion` relations are not transitive.

**Design Note 10.3.1 — Operational Consequences of Mereological Transitivity:**

Because HAS-COMPONENT is transitive, a change to a component part propagates upward. If a wagon loses its wheels, the mereological rule automatically computes that the functional status of the whole is degraded — without requiring an external sensor event to declare the failure. This enables deterministic reasoning about system state from structural information alone.

**Constraint 10.3.3:** Mereology is optional. Most abstract concepts and persons do not need it.

### 10.4 Perdurantist Layer

#### 10.4.1 Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `canonical_id` | String | Required | Must conform to Section 2.3 |
| `layer` | String | Required | Must be "PERDURANTIST" |
| `essential_events` | Synapse[] | Required | Array of Synapses (at least 1, unless no Lemma-Mates exist) |
| `contingent_events` | Synapse[] | Optional | Historically significant but not definitional |
| `sourcing` | Object | Optional | Source metadata (see Section 13) |

#### 10.4.2 Constraints

**Constraint 10.4.1:** The `essential_events` array must contain at least one Synapse unless the Node has no Lemma-Mates.

**Constraint 10.4.2:** Every Synapse in `essential_events` must satisfy the Event Minimality Axiom (Axiom V).

**Constraint 10.4.3:** The `contingent_events` array is not subject to the Minimality Axiom.

### 10.5 Verbs and the Four Layers

Verbs are first-class Nodes following the same four-layer architecture with specific conventions.

#### 10.5.1 Lexical Layer (verb)

Standard fields. The microgloss for verbs should encode the core semantic frame: `compose.v.create_music`, `pull.v.exert_force`.

#### 10.5.2 Ontological Layer (verb)

Verbs have IS-A parents in a verb hierarchy organized by semantic domain:

- `compose.create_music` IS-A `create.v.bring_into_existence`
- `create.v.bring_into_existence` IS-A `act.v.do_something`
- `act.v.do_something` IS-A `event.v.happen`

**Constraint 10.5.1:** Verb IS-A edges imply event subsumption: if X IS-A Y, then any event of type X is also an event of type Y.

#### 10.5.3 Mereological Layer (verb)

Verbs typically have no mereology.

#### 10.5.4 Perdurantist Layer (verb)

A verb's Perdurantist layer defines its **role constraints** — the minimal set of roles required for a well-formed Synapse.

Example — `compose.v.create_music`:

```json
{
  "canonical_id": "sgf:en.compose.v.create_music",
  "layer": "perdurantist",
  "lexical": { "lemma": "compose", "pos": "v", "microgloss": "create_music" },
  "ontological": { "is_a": ["sgf:en.create.v.bring_into_existence"] },
  "perdurantist": {
    "core_roles": ["HAS_AGENT", "HAS_THEME"],
    "permitted_roles": ["HAS_TIME", "HAS_LOCATION", "HAS_INSTRUMENT", "HAS_MANNER", "HAS_REASON"],
    "essential_events": []
  }
}
```

**Constraint 10.5.2:** A Synapse using a given VerbHub must include all roles listed in `core_roles`.

**Constraint 10.5.3:** A Synapse using a given VerbHub must not include any role not listed in `core_roles` or `permitted_roles`.

**Constraint 10.5.4:** Verb Nodes may have an empty `essential_events` array. The verb's definition is given by its role constraints, not by events about the verb itself.

### 10.6 Stative Concepts — Adjectives and Properties

Stative concepts — adjectives, adverbs, and other property terms — require a different treatment in the Perdurantist layer.

#### 10.6.1 Lexical Layer (adjective/adverb)

Standard lexical layer. Part of speech is `adj` or `adv`.

#### 10.6.2 Ontological Layer (adjective)

Adjectives have IS-A parents in a property hierarchy:

- `red.adj.color_red` IS-A `color.adj.chromatic_property` IS-A `property.adj.perceptual_attribute` IS-A `quality.n.abstract_attribute`

#### 10.6.3 Perdurantist Layer (adjective)

Adjectives define **characteristic situations** in which the property is manifested, rather than events in the standard sense.

Example — `red.adj.color_red`:

```json
{
  "canonical_id": "sgf:en.red.adj.color_red",
  "layer": "perdurantist",
  "lexical": { "lemma": "red", "pos": "adj", "microgloss": "color_red" },
  "ontological": { "is_a": ["sgf:en.color.adj.chromatic_property"] },
  "perdurantist": {
    "characteristic_situations": [
      {
        "hub": "sgf:en.appear.v.present_visually",
        "spokes": {
          "HAS_THEME": ["sgf:en.ripe_tomato.n.object_with_property"],
          "HAS_ATTRIBUTE": ["SELF"]
        }
      }
    ]
  }
}
```

**Constraint 10.6.1:** A Node with POS `adj` or `adv` must use `characteristic_situations` instead of `essential_events`.

**Constraint 10.6.2:** A Node with POS `adj` or `adv` must not use `essential_events`.

**Constraint 10.6.3:** The same Event Minimality axiom (Axiom V) applies: no characteristic situation may be removed while still maintaining disambiguation from lemma-mates.

---

## Section 11: The 15 Semantic Roles

### 11.1 Purpose

The 15 semantic roles form the closed grammar for all event representation. They are the only allowed Role types for Synapse Spokes.

### 11.2 Role Definitions

| # | Role Name | Category | Definition | Example |
|---|---|---|---|---|
| 1 | `HAS_AGENT` | Core | Deliberate initiator of the action. Must be sentient. | "He **drove** the wagon." → AGENT: he |
| 2 | `HAS_PATIENT` | Core | Entity that undergoes change of state. | "He **broke** the axle." → PATIENT: axle |
| 3 | `HAS_THEME` | Core | Entity moved, located, or held. No state change. | "He **loaded** grain onto the wagon." → THEME: grain |
| 4 | `HAS_EXPERIENCER` | Core | Entity that experiences non-deliberately. | "He **felt** the wagon lurch." → EXPERIENCER: he |
| 5 | `HAS_RECIPIENT` | Core | Entity that receives the Theme. | "He **gave** the reins to the teamster." → RECIPIENT: teamster |
| 6 | `HAS_BENEFICIARY` | Core | Entity for whose benefit the action is performed. | "He **built** a wagon for the farmer." → BENEFICIARY: farmer |
| 7 | `HAS_TIME` | Circumstance | Temporal coordinate of the event. | "He **departed** at dawn." → TIME: dawn |
| 8 | `HAS_LOCATION` | Circumstance | Spatial region where the event occurs. | "He **parked** the wagon near the barn." → LOCATION: barn |
| 9 | `HAS_SOURCE` | Circumstance | Initial state or location of the Theme. | "He **drove** from the farm." → SOURCE: farm |
| 10 | `HAS_DESTINATION` | Circumstance | Final state or location of the Theme. | "He **drove** to the market." → DESTINATION: market |
| 11 | `HAS_MANNER` | Circumstance | Manner in which the event is executed. | "He **rode** the wagon slowly." → MANNER: slowly |
| 12 | `HAS_INSTRUMENT` | Circumstance | Non-sentient tool used to perform the action. | "He **hitched** the horses with a harness." → INSTRUMENT: harness |
| 13 | `HAS_CAUSE` | Circumstance | Inanimate trigger of a state change. | "The axle **broke** from the weight." → CAUSE: weight |
| 14 | `HAS_REASON` | Circumstance | Unified motivational ground (reason + purpose). | "He **went** to the market to sell grain." → REASON: sell_grain |
| 15 | `HAS_ATTRIBUTE` | Circumstance | Event-result property assigned to a participant. | "He **painted** the wagon red." → ATTRIBUTE: red |

### 11.3 Constraints

**Constraint 11.3.1:** No Synapse may use a Role type outside this set.

**Constraint 11.3.2:** No two Spokes in the same Synapse may use the same Role type.

**Constraint 11.3.3:** A Circumstance Role may be omitted. A Core Role may be omitted only if the event type does not logically require it.

**Constraint 11.3.4:** `HAS_AGENT` must only connect to a sentient Node.

**Constraint 11.3.5:** `HAS_INSTRUMENT` must only connect to a non-sentient Node.

**Constraint 11.3.6:** `HAS_CAUSE` must connect to a non-sentient Node or force of nature. For deliberate actions, use `HAS_REASON`.

### 11.4 Reason-Purpose Unification

`HAS_REASON` is a unified role covering both backward-looking motive and forward-looking purpose. When the distinction is necessary, Frames refine the interpretation. The role grammar stays stable; the nuance lives in the frame.

---

## Section 12: Canonical IDs

### 12.1 Grammar

Already specified in Section 2.3. This section provides additional rules.

### 12.2 Assignment Rules

**Rule 12.2.1:** A Canonical ID is assigned at Node creation. It is never changed.

**Rule 12.2.2:** The microgloss must be chosen so that it is unique among lemma-mates.

**Rule 12.2.3:** The microgloss should be as short as possible while maintaining uniqueness.

**Rule 12.2.4:** No two Canonical IDs may differ only in case.

### 12.3 Reserved IDs

| ID | Purpose |
|---|---|
| `sgf:xx.self.n.self_reference` | Used in Synapses to refer to the Node itself |
| `sgf:xx.unk.n.unknown` | Used when a participant is unknown |
| `sgf:xx.null.n.null_reference` | Used when a participant is intentionally absent |
| `sgf:xx.any.n.any_reference` | Used in query patterns as a wildcard |

---

## Section 13: Event Sourcing and Authority

### 13.1 Purpose

Events in the Perdurantist Layer are not declarations of metaphysical truth. They are **sourced anchors** — established consensus identifiers drawn from authoritative references. This section defines how sources are recorded, what counts as authoritative, and how sourcing metadata is structured.

### 13.2 Authoritative Sources

The following are considered authoritative sources for Synapedia events:

- Wikipedia articles and infoboxes (for historical figures, artifacts, events)
- Wikidata properties and statements (for structured data)
- Academic taxonomies and ontologies (for biological species, chemical compounds)
- Standard reference works (dictionaries, encyclopedias) where they represent consensus

### 13.3 Sourcing Metadata Structure

Each Perdurantist entry MAY include a `sourcing` block:

```json
"sourcing": {
  "events": [
    {
      "event": "sgf:en.transport.v.carry_cargo",
      "source": "https://en.wikipedia.org/wiki/Wagon",
      "accessed": "2026-06-28",
      "confidence": "high"
    }
  ],
  "global_note": "All events sourced from Wikipedia unless otherwise noted."
}
```

**Fields:**

| Field | Type | Required | Description |
|---|---|---|---|
| `events` | Object[] | Yes | Per-event source records |
| `global_note` | String | No | Note applying to all events |

Each event record:

| Field | Type | Required | Description |
|---|---|---|---|
| `event` | String | Yes | Canonical ID of the event verb |
| `source` | String | Yes | URI or citation of the source |
| `accessed` | Date | Yes | Date the source was accessed |
| `confidence` | Enum | Yes | `high`, `medium`, or `low` |

### 13.4 Sourcing Guidelines

- For physical objects and artifacts: Wikipedia article, standard reference.
- For historical figures: Wikipedia infobox (birth date, death date, profession, notable achievement).
- For biological species: established taxonomic databases (e.g., GBIF, ITIS).
- For abstract concepts: consensus definitions from authoritative dictionaries or ontologies.
- For fictional entities: the work-of-origin publication event (e.g., *A Study in Scarlet*, 1887, London).

### 13.5 Updating Sources

When a source is updated or a better source becomes available, the Synapedia entry is updated via deprecation and replacement (Section 8). The sourcing metadata is updated to reflect the new authority.

---

## Section 14: Grounding and Validation

### 14.1 Grounding Verification Algorithm

1. If Node is in the Prime Registry, return GROUNDED.
2. If Node has an attached spacetime coordinate, return GROUNDED.
3. Perform BFS along all outgoing `IS-A` Edges.
4. If any reachable Node is in the Prime Registry or has a spacetime coordinate, return GROUNDED.
5. Otherwise, return UNGROUNDED.

### 14.2 Acyclicity Verification

Perform topological sort of the full IS-A graph. If it succeeds, pass. If it fails (cycle detected), fail and report the cycle.

### 14.3 Microgloss Sufficiency Verification

Group all Nodes by (language_tag, lemma, pos). For each group, check that all Microglosses are unique. If any duplicate is found, fail with the duplicate pair.

### 14.4 Event Minimality Verification

For each Synapse in a Perdurantist Node's `essential_events`:

1. Temporarily remove the Synapse.
2. Compare the reduced set against each Lemma-Mate.
3. If the reduced set is identical to any Lemma-Mate's essential events, then the removed Synapse is necessary — it must be kept.
4. If the reduced set is not identical to any Lemma-Mate's essential events, then the removed Synapse is unnecessary — fail.

### 14.5 Semantics of Grounding — Design Note

Grounding is a **referential guarantee**, not a truth guarantee. A grounded Node has a definite address in the graph and a path to primitives or spacetime. It does not guarantee real-world existence (fictional entities are grounded via a `fictional_entity` branch), nor does it guarantee that any assertion using the concept is true (truth belongs to the ABox). Grounding guarantees only that the concept is not defined in terms of undefined concepts — no infinite regress, no floating definitions.

---

## Section 15: Knowledge Packs

### 15.1 Structure

| Field | Type | Required | Description |
|---|---|---|---|
| `pack_id` | String | Required | Globally unique identifier |
| `version` | String | Required | Semantic version |
| `signature` | String | Required | Digital signature |
| `authority` | String | Required | Signing entity |
| `references` | String[] | Required | Array of Canonical IDs |
| `content` | Object[] | Required | Array of SGF objects |

### 15.2 Relationship to Synapedia

**Constraint 15.2.1:** A Knowledge Pack must not contain Nodes that claim to be in any Synapedia Layer.

**Constraint 15.2.2:** A Knowledge Pack must not add `IS-A` Edges to the Synapedia graph.

**Constraint 15.2.3:** A Knowledge Pack may define additional Synapses using the same 15 Role grammar.

**Constraint 15.2.4:** A Knowledge Pack may reference any valid Canonical ID, including deprecated IDs.

---

## Section 16: Scope and Limits

### 16.1 What Synapedia Provides

1. Machine-addressable concept definitions with unique, stable identifiers.
2. A grounded type hierarchy (IS-A) tracing to primitives or spacetime.
3. Compositional structure (mereology) where load-bearing.
4. Minimal event definitions that disambiguate concepts from lemma-mates.
5. A closed grammar of 15 semantic roles for event representation.
6. A reference substrate that other layers can point to with no ambiguity.
7. Sourced event anchors that represent consensus definitions, not ultimate truth.

### 16.2 What Synapedia Does Not Provide

1. **Truth values for propositions.** Truth is the domain of the ABox.
2. **Temporal reasoning beyond event ordering.** That is the domain of the Inference layer.
3. **Probabilistic or uncertain knowledge.** Synapedia entries are categorical.
4. **Normative or deontic reasoning.** That is the domain of Knowledge Packs.
5. **Natural language generation or parsing.** Synapedia is not a language model.
6. **Encyclopedic knowledge.** Synapedia is minimal by design.
7. **Inference or deduction.** That is the domain of the Reasoning layer.

### 16.3 Boundary with the ABox

The ABox uses Canonical IDs from Synapedia to refer to concepts. The relationship is one-way: the ABox references Synapedia; Synapedia does not reference the ABox. Claims in the ABox may be contradictory, false, or deliberately deceptive. Synapedia does not resolve this.

### 16.4 Boundary with Knowledge Packs

Knowledge Packs attach additional structure to Synapedia Nodes. They are signed, versioned, and domain-specific. They are not part of Synapedia.

---

## Section 17: Verification Depth as a Policy Decision

### 17.1 The Problem

Synapedia defines concepts with multiple layers of structure, but how deeply a downstream system compares two entries is not fixed by the lexicon. It is a **policy decision** governed by the consequence of error.

Every comparison begins with the same foundation: **lemma + part of speech + embedding**. The embedding provides a location in multi-dimensional vector space of meaning. It is the universal address system — it works across languages, across lexicons, and across ontologies that do not share the same Canonical IDs. Without the embedding, two systems using different lexicons cannot even find each other's concepts.

The question is: once the embedding has brought us to the right neighborhood, how much structural verification do we need before we are confident enough to act?

### 17.2 The Role of Embeddings in All Depths

At every depth, the comparison starts with the same three signals:

- **Lemma** — filters to the exact word form (or its cross-lingual equivalent via `TRANSLATION-OF` edges).
- **Part of speech** — filters to the correct usage (noun vs. verb vs. adjective).
- **Embedding** — provides a location in vector space that captures synonymy, domain, and usage patterns.

The lemma is not usable when crossing languages (a French word and an English word have different lemmas), but the embedding works across languages because it is trained on multilingual corpora. For most ordinary searches — finding an equivalent word meaning — the lemma + POS + embedding is sufficient.

The deeper layers (Ontological, Mereological, Perdurantist) do not replace the embedding. They **augment** it. They provide structural evidence that the embedding alone cannot guarantee. By going deeper into Synapedia — examining the parent terms, the parts, the events, and the parents of the parents — we gain much greater confidence that two concepts are truly equivalent, not just nearby in vector space.

### 17.3 Three Natural Depths

**Depth 1 — Lemma + Embedding (Ordinary Search)**

Compare only the lexical layer: lemma, part of speech, and embedding vector. Fast, cheap, suitable for exploration and casual browsing. This is what ordinary human conversation does most of the time — we hear a word, our brain activates the nearest concept via distributional similarity, and we move on. It works because the consequence of ambiguity is low; we can clarify in the next sentence.

*Example:* A customer browsing a hardware catalog types "screwdriver." The system returns all screwdriver SKUs. If the customer meant "Phillips head" and the system returns "flat head," the cost is a minor correction.

**Depth 2 — Structural Alignment (One Level Deep)**

Compare the immediate Ontological, Mereological, and Perdurantist layers slot by slot. The system examines:

- IS-A parents (what kind of thing is this?)
- HAS-COMPONENT parts (what does it consist of?)
- Essential events (what does it do?)
- HAS-ATTRIBUTE values (what properties does it have?)

Every populated slot must match. Empty slots are wildcards. This depth is required for purchase commitments, safety-critical parts, and most procurement.

*Example — The NASA Screwdriver:* A procurement officer needs a flight-qualified torque driver — the kind used on the Mars mission. A vendor offers a titanium torque driver with a red anodized collar. Depth 1 (lemma + embedding) would match "torque driver" to "torque driver" and return a candidate. But Depth 2 reveals that the requirement has `HAS_ATTRIBUTE: operating_environment = vacuum` and `HAS_REASON: use_case = aerospace_assembly`, while the offered part has `HAS_ATTRIBUTE: operating_environment = atmospheric`. The GapReport documents the mismatch. The officer does not guess. The system proves the difference.

*Example — RFP with 200 Line Items:* A procurement department issues an RFP with 200 line items, each specifying required features, certifications, and performance thresholds. Depth 2 alignment runs on every line item simultaneously, producing a compliance matrix. Items that pass all slots get a ProofTrace. Items that fail get a GapReport showing exactly which slot failed. Human review is needed only for the exceptions.

**Depth 3 — Full Hierarchy Traversal (Parents of Parents)**

Traverse two or more generations of IS-A parents. Compare not just the immediate parents, but the parents of the parents. This catches cases where the immediate parent does not match, but the grandparent does.

*Example:* "Bell-bottom hip huggers" might not match "trousers" directly (different microgloss), but both are `IS-A` `lower_body_garment`. Depth 3 finds the connection that Depth 2 would miss.

Depth 3 is rarely needed for product identification — the definitional events at the entry level usually suffice. But it becomes important when:

- The lexicon is sparse (few entries exist for the domain)
- The domain has deeply nested hierarchies (biological taxonomy, military specifications)
- Two systems use different granularity in their ontologies (one has "vehicle" as a parent, the other has "land_vehicle")

### 17.4 Policy, Not Technology

How deep should we go? It is a **policy decision**, not a one-size-fits-all technical limit. The same system can enforce different depths for different contexts:

- A luxury watch retailer might set Depth 2 for every purchase, because the return cost is high.
- A grocery delivery service might stay at Depth 1 for most items, reserving Depth 2 only for items with allergen or dietary restrictions.
- A defense contractor might require Depth 3 for any part that touches flight hardware.

The policy must be **published transparently** to all parties in a verification exchange. The customer (or procurement officer) must know what depth was used and what it guarantees.

**Constraint 17.4.1:** The depth policy must be published transparently to all parties in a verification exchange.

**Constraint 17.4.2:** The depth policy must be recorded in the ProofTrace or GapReport for every comparison.

### 17.5 Summary Table

| Depth | What Is Compared | Speed | Confidence | When to Use |
|---|---|---|---|---|
| 1 | Lemma + POS + Embedding | Fast (~200ms) | Low | Browsing, exploration, low-stakes queries |
| 2 | Immediate Ontological, Mereological, Perdurantist layers | Moderate (~500ms) | High | Purchase commitments, safety-critical parts, RFP matching |
| 3 | Full hierarchy traversal (parents of parents) | Slower (~1-2s) | Very High | Sparse lexicons, deep taxonomies, cross-ontology alignment |

---

## Section 18: Grounding Non-Physical Entities

### 18.1 Fictional Entities

Fictional entities do not exist in physical reality but still require grounded definitions.

**Grounding strategy:**
1. IS-A chain: `fictional_character.n.imaginary_person` IS-A `fictional_entity.n.imaginary_thing` IS-A `abstract_entity.n.non_physical_thing`
2. Work-of-origin spacetime coordinate: the publication date and location of the work in which the character first appeared.

**Example — Sherlock Holmes:**
- IS-A: `fictional_character.n.imaginary_person`
- Spacetime coordinate: (1887, London) — publication of *A Study in Scarlet*
- Sourcing: Conan Doyle canon, authoritative scholarship

This is not a claim that Holmes existed in London. It is a claim that his definition originates there.

### 18.2 Abstract Concepts

Abstract concepts (justice, freedom, love, gravity) are grounded via:
1. IS-A parent: `abstract_entity.n.concept`
2. Consensus definition: drawn from authoritative dictionaries, encyclopedias, or philosophical reference works
3. Perdurantist events: only if needed for disambiguation

### 18.3 Mathematical Objects

Mathematical objects (numbers, sets, functions) are grounded via:
1. IS-A parent: `abstract_entity.n.mathematical_object`
2. Formal definition: drawn from standard mathematical references
3. No spacetime coordinate — mathematical objects have no physical origination point

---

## Section 19: Comparison to Existing Systems

| System | Grounded | Closed Grammar | Minimality | IS-A Hierarchy | Event-Centric |
|---|---|---|---|---|---|
| WordNet | No | Yes (limited) | No | Yes (shallow) | No |
| Wikidata | Partial | No | No | Yes (via P31/P279) | No |
| FrameNet | No | No | No | No | Partial |
| Cyc | No | No | No | Yes | No |
| DBPedia | Yes (URI) | No | No | Partial | No |
| **Synapedia** | **Yes** | **Yes (15 roles)** | **Yes (Axiom V)** | **Yes (acyclic)** | **Yes (Perdurantist)** |

**Key differentiators:**
- Synapedia is the only system that requires events to be part of the definition.
- Synapedia is the only system with a closed, bounded predicate set.
- Synapedia enforces minimality algorithmically — no other system does this.
- Synapedia is the only system that explicitly separates definition (TBox) from assertion (ABox).

**Predicate Explosion** is the systemic failure that occurs when an ontology allows an unbounded set of relationship types. In systems with open predicate spaces (Wikidata, RDF/OWL), any developer can invent new properties. This causes schema fragmentation, reasoning slowdown, and cross-graph incompatibility. Synapedia prevents Predicate Explosion by permanently restricting relational edges to exactly 15 invariant semantic roles (Postulate III — The Invariant Edge Constraint).

---

## Section 20: Exemplaries

### 20.1 Wagon

**Canonical ID:** `sgf:en.wagon.n.horse_drawn_cargo`

Full entry exercises all four layers, includes mereology, polyhierarchy (vehicle + container), and multiple events. Demonstrates that mereology belongs only when composition is load-bearing.

### 20.2 Beethoven

**Canonical ID:** `sgf:en.beethoven.n.composer_1770`

Proper name for a unique individual. Minimal discriminating events (exactly three):

1. Birth: `HAS_TIME: 1770`, `HAS_LOCATION: Bonn`
2. Death: `HAS_TIME: 1827`, `HAS_LOCATION: Vienna`
3. Author: `HAS_THEME: sgf:en.symphony_no_9.n.beethoven_op_125`

These three synapses are sufficient to distinguish this Beethoven from any other entity named "Beethoven" in the lexicon. No biography is needed. Encyclopedic depth is deferred to Knowledge Packs. Empty mereology is valid. Double-grounded (Prime Registry + spacetime).

### 20.3 Tomato

**Canonical ID:** `sgf:en.tomato.n.edible_red_fruit`

Polyhierarchy from different perspectives (botanical fruit + culinary vegetable). Empty `essential_events` is valid when microgloss suffices. Mereology is natural for organic entities.

### 20.4 Bank (Financial vs. River)

**IDs:** `sgf:en.bank.n.financial_institution` and `sgf:en.bank.n.river_edge`

Lemma-mate disambiguation via microgloss + events. Radically different IS-A parents. The acid test for homonymy handling.

### 20.5 Amphibious Vehicle

**ID:** `sgf:en.amphibious_vehicle.n.land_and_water`

Conflict resolution for inherited events. Most polyhierarchy does not produce true conflicts; both events are inherited without issue. Demonstrates explicit override when needed.

### 20.6 Mortgage

**ID:** `sgf:en.mortgage.n.property_loan_agreement`

Abstract concept defined entirely by events (create, pledge, repay, foreclose). No physical grounding; no mereology. Demonstrates that abstract concepts can be fully defined by their event lifecycle.

### 20.7 Theodore Roosevelt (multiple)

**IDs:** `sgf:en.theodore_roosevelt.n.president_1858`, `sgf:en.theodore_roosevelt.n.industrialist_1831`, etc.

Demonstrates proper-name disambiguation via minimal sourced events (birth, death, profession, notable achievement). Sourcing from Wikipedia infoboxes.

---

## Section 21: Proof of Concept Walkthrough

### 21.1 Proposition: "Beethoven composed Symphony No. 9 in 1824."

**Step 1 — Lookup:** The ABox contains a synapse referencing `sgf:en.compose.v.create_music` with `HAS_AGENT: sgf:en.beethoven.n.composer_1770`, `HAS_THEME: sgf:en.symphony_no_9.n.beethoven_op_125`, `HAS_TIME: "1824"`.

**Step 2 — Synapedia Verification:** The Perdurantist layer of Beethoven contains a matching Synapse. The Perdurantist layer of Symphony No. 9 contains a matching Synapse (with roles reversed).

**Step 3 — Validation:** All axioms are satisfied:
- Axiom I: No cycles in IS-A paths.
- Axiom II: Both nodes have paths to Prime Registry. Beethoven additionally has spacetime coordinates.
- Axiom IV: Microglosses are unique.
- Axiom V: Removing any single Synapse from Beethoven would not lose disambiguation (no other lemma-mate exists), but if there were a second identical entry, the minimality constraint would apply.
- Axiom VI: No ID collisions.

**Step 4 — Query:** "Who composed Symphony No. 9?" → Retrieve Symphony's Perdurantist layer, find `compose` Synapse, read `HAS_AGENT`. → Return "Beethoven."

**Step 5 — Boundary:** "Did Beethoven write any other symphonies?" → Cannot be answered from Synapedia alone. Requires a Knowledge Pack with full catalog.

---

## Section 22: Appendices

### Appendix A: Bootstrapping Plan

Synapedia cannot be built all at once. The following phased plan defines the minimum viable set of entries.

#### Phase 0: The Prime Registry (50 entries)

Candidates (adapted from NSM primes and additional primitives):

- Self/Other: `i.n.self_reference`, `you.n.interlocutor`, `someone.n.person`, `something.n.entity`
- Actions: `do.v.perform_action`, `happen.v.occur_event`, `move.v.change_location`, `make.v.create_thing`
- Qualities: `good.adj.desirable`, `bad.adj.undesirable`, `big.adj.large_size`, `small.adj.little`
- Relations: `before.preptime_sequence`, `after.preptime_sequence`, `because.conj.causal_link`
- Time/Space: `time.n.dimension`, `place.n.location`, `now.n.present_moment`, `here.n.this_place`
- Logic: `not.conj.negation`, `maybe.conj.possibility`, `can.n.ability`

#### Phase 1: High-Level Categories (100 entries)

`person.n.human_individual`, `animal.n.living_creature`, `object.n.physical_thing`, `artifact.n.human_made`, `event.n.occurrence`, `action.n.deliberate_act`, `state.n.condition`, `place.n.location`, `time.n.interval`, `relation.n.connection`.

#### Phase 2: Core Verbs and Event Types (200 entries)

Motion, creation, communication, possession, perception, cognition, core states. Each verb defined with its role constraints (core_roles, permitted_roles).

#### Phase 3: Concrete Objects (300 entries)

Body parts, tools, vehicles, buildings, clothing, food, furniture. Each with minimal Perdurantist events and mereology where load-bearing.

#### Phase 4: Abstract Concepts (200 entries)

Institutions, relationships, agreements, emotions, quantities, properties.

#### Phase 5: Proper Names (100 entries)

Major historical figures, places, works of art.

**Total initial target:** approximately 1,000 entries.

**Constraint A.1:** No entry in a later phase may reference an entry from a later phase. Dependencies must respect phase order.

### Appendix B: Reserved IDs

As specified in Section 12.3.

---

## Section 23: References

- Wierzbicka, A. (1996). *Semantics: Primes and Universals*. Oxford University Press.
- Goddard, C. (2018). *Ten Lectures on Natural Semantic Metalanguage*. Brill.
- Miller, G. A. (1995). "WordNet: A Lexical Database for English." *Communications of the ACM*, 38(11), 39-41.
- Baker, C. F., Fillmore, C. J., & Lowe, J. B. (1998). "The Berkeley FrameNet Project." *Proceedings of COLING-ACL*.
- Lenat, D. B. (1995). "Cyc: A Large-Scale Investment in Knowledge Infrastructure." *Communications of the ACM*, 38(11), 33-38.
- Vrandečić, D., & Krötzsch, M. (2014). "Wikidata: A Free Collaborative Knowledge Base." *Communications of the ACM*, 57(10), 78-85.
- Symbol Grounding Framework (2025-2026). *SGF Architecture Specification Series*. SGF-ARC.

---

**Document changelog:**

- v1.0 (2026-06-01): Initial release.
- v1.1 (2026-06-28): Added Section 2.18 (ABox), Section 13 (Event Sourcing and Authority), Section 18 (Grounding Non-Physical Entities), Section 19 (Comparison to Existing Systems), Section 23 (References). Added examples for Theodore Roosevelt (Section 20.7). Added Section 6.7 (Claim Agnosticism). Added Section 11.4 (Reason-Purpose Unification). Reframed the system as a lexicon throughout.
- v1.2 (2026-06-28): Added Section 6.1.1 (Why "Perdurantist"). Added Section 17 (Verification Depth as a Policy Decision) with NASA screwdriver and RFP examples. Clarified the role of embeddings at all depths. All v1.1 content preserved in full. No content removed.
- v1.3 (2026-07-01): Added Section 2.19 (The Orthogonal Dual-Axis Split). Added "Lemma Collapse" to Section 2.0. Added "Predicate Explosion" to Section 19. Renamed Postulate III to "The Invariant Edge Constraint (Edge Exclusivity)" with expanded language. Added Design Note 10.3.1 (Operational Consequences of Mereological Transitivity). Replaced Section 20.2 with tighter Beethoven example (3 explicit synapses). Added Design Note 2.18.1 (Asymmetric Dependency Vector diagram). Added "Collapsing the TBox/ABox Divide" framing to Section 1.2. All v1.2 content preserved in full. No content removed.

---

*End of Synapedia Architecture Specification v1.3*