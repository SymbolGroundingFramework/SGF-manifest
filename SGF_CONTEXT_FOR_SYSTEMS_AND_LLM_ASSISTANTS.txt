# Symbol Grounding Framework Context for LLMs

Version: v3.6 lexicon architecture foundation  
Date: May 2026  
Purpose: This document provides architectural and doctrinal context for both human readers and AI assistants working on SGF specs, claim bundles, and examples.

## Fast orientation

The Symbol Grounding Framework (SGF) is an architecture for representing meaning as grounded, source-traceable, frame-aware, claim-bearing structures that can be stored, queried, audited, transported, and governed.

SGF does not claim to capture all human meaning, consciousness, experience, or truth. It captures the subset of meaning that can be grounded to identifiers, structured into Synapses, traced to sources, carried across trust boundaries, filtered by Trust Lenses, and admitted or refused by a receiver.

The current series has four publication-ready books:

1. **Napkin Pitch**: the compressed architectural vision.
2. **The Architecture of Meaning**: the substrate book. It explains Core Lexicon, Canonical IDs, Synapses, GLEAN, frames, groups, source traces, lexicon construction, and media/perception extensions.
3. **The Third Protocol**: the machine-to-machine protocol book. It explains HFF, AFP, capability exchange, sidecars, receiver sovereignty, federation, Knowledge Packs, Trust Lenses, Evidence Gates, walkthroughs, swarms, and the Global Ark.
4. **Omega: The Language of Governance**: the governance-language book. It explains why prose does not govern machines and defines Omega-Code as a typed grammar for rules, permissions, constraints, mutation, and self-amendment.

Other projects exist in the pipeline but are not yet publication-ready canon: the AI operating system, the domain-driving code factory, the cosmos book, and the epistemology/methodology book. Treat them as promising extensions, not as settled SGF v1.0 substrate.

## Series thesis

The SGF series argues that AI systems cannot become reliable coordinators merely by becoming more fluent. They need an architecture of meaning. That architecture must ground symbols, structure claims, preserve provenance, transport context, admit or refuse messages at boundaries, and govern action through typed rules rather than prose hope.

The series-level thesis:

```text
Machine intelligence becomes governable only when meaning becomes structured, grounded, transportable, auditable, and bounded by receiver authority.
```

The practical version:

```text
LLMs can generate language, but consequential systems need grounded objects, stable identifiers, proof traces, role grammar, protocol envelopes, act declarations, and governance constraints.
```

The substrate claim:

```text
Meaning needs atoms before it can become infrastructure.
```

The protocol claim:

```text
Meaning must be admissible before it can safely cross machine boundaries.
```

The governance claim:

```text
Machines cannot be governed by prose they cannot parse.
```

## Thesis vs claim

A **thesis** is the governing proposition of a system, book, chapter, or essay. It is the deepest statement of what the work is really saying.

A **claim** is a proposition the work argues, proves, supports, or uses. A book can have one central thesis and many claims.

A **secondary claim** is a load-bearing claim that supports the central thesis.

A **payload line** is a compressed claim that readers can remember and repeat.

For SGF work, distinguish:

- **system thesis**: what SGF as a whole proves;
- **book thesis**: what one volume proves;
- **chapter claim**: what one chapter changes in the reader’s belief state;
- **technical claim**: what the spec requires or permits;
- **payload line**: the memorable version of a claim.

## System thesis map

### SGF as a system

SGF’s thesis is that machine meaning can be made operationally grounded without pretending to solve all human meaning. SGF creates a substrate where symbols point to stable addresses, claims have internal role structure, evidence travels with claims, ambiguity is reported rather than hidden, and receivers decide what to admit.

### The Core Lexicon thesis

The Core Lexicon is SGF’s engineered stopping rule for semantic regress. It does not contain all meaning. It provides shared, inspectable addresses where explanation can stop for operational purposes. Non-core terms can travel only when they bring grounding material and a path back toward Core.

### The Synapse thesis

A Synapse is the smallest unit of meaning that still functions. Triples are too small because they break event structure into fragments. Prose is too loose because it hides roles, sources, and frames. The Synapse preserves the verb/event as hub and attaches participants through a closed role grammar.

### The GLEAN thesis

GLEAN is a court reporter, not a mind reader. It records what can be grounded, attaches proof, emits gaps when grounding fails, and refuses to fabricate structure to make messy source material look clean.

### The HFF thesis

HFF makes meaning portable by carrying SGF objects with the context required for hydration: lexicon material, provenance, hashes, signatures, frames, validity windows, profile declarations, and receipts.

### The AFP thesis

AFP adds illocution to meaning. Machines do not only exchange content; they perform acts with content. INFORM, REQUEST, COMMAND, PROMISE, REFUSE, ACK, and ERROR are not interchangeable.

### The Third Protocol thesis

The Third Protocol is the missing protocol layer for machine-to-machine meaning. TCP/IP moved bytes. HTTP moved documents. HFF + AFP move grounded meaning with receiver sovereignty.

### The Omega thesis

Omega exists because prose does not govern machines. Governance must become a typed, inspectable, enforceable language that specifies what a machine may do, when, under what authority, with what resources, and under what exceptions.

## Book thesis map

### Volume 0: Napkin Pitch

**Thesis:** SGF is the missing architecture that turns LLM fluency into grounded machine responsibility.

**Primary claim:** Language models are astonishing but structurally incomplete. They need grounding, Synapses, verifiable graphs, governance, and protocols before they can become reliable machine infrastructure.

**Function in the series:** compressed public-facing orientation. It gives the reader the whole architecture as a vivid, memorable map.

**Main payloads:**

- The system needs grounding before reasoning.
- The verb belongs at the center.
- Meaning needs an archive.
- Governance must say no.
- The architecture is public-domain infrastructure.

### Volume 1: The Architecture of Meaning

**Thesis:** Meaning needs a substrate: Core Lexicon, Canonical IDs, Synapses, frames, provenance, GLEAN, groups, links, and perceptual/media grounding.

**Primary claim:** The failures of vector-only RAG, brittle knowledge graphs, RDF predicate explosion, and hallucinated model prose share one root cause: machines lack grounded, structured, source-traceable atoms of meaning.

**Function in the series:** defines the substrate. This is the foundation on which HFF, AFP, Omega, AI OS, code factories, reasoning engines, and federation depend.

**Main payloads:**

- The symbol-grounding impossibility claim is too large.
- The grounding regress is categorically similar to Achilles and the tortoise: the paradox exposes missing convergence/stopping machinery, not impossibility.
- A paragraph is not knowledge merely because it is relevant.
- The verb could not be the edge. The verb had to be the hub.
- A Synapse is a grounded claim-bearing structure, not always a fact.
- The 15-role grammar keeps structure stable while vocabulary remains open.
- GLEAN records what can be grounded and emits gaps where grounding fails.

### Volume 2: The Third Protocol

**Thesis:** Machines need a protocol for admissible meaning across boundaries.

**Primary claim:** Machine-to-machine coordination cannot rely on prose, private APIs, or probabilistic interpretation. It requires HFF to carry grounded context, AFP to declare acts, capability exchange to discover compatibility, and receiver sovereignty to admit or refuse.

**Function in the series:** turns the substrate into infrastructure. It explains how SGF objects travel between machines, organizations, agents, swarms, and knowledge systems.

**Main payloads:**

- Probably understood is not a protocol.
- Meaning is not enough. Meaning must be admissible.
- Context is part of the message.
- Triples describe. Acts bind.
- The receiver is sovereign.
- A swarm that cannot refuse is a botnet.
- Governance protects interoperability, not permission.
- Protocols carry structure. Judgment remains outside the wire.

### Volume 3: Omega: The Language of Governance

**Thesis:** Prose does not govern machines; governance requires typed grammar.

**Primary claim:** When execution substrates move faster and more precisely than policy language, prose constraints fail. Omega-Code supplies the typed primitives needed to express context, time, resources, state, trust, governance, mutation, perception, learning, and meta-definition.

**Function in the series:** supplies the governance layer. SGF says what is. HFF carries it. AFP acts with it. Omega says what may be done.

**Main payloads:**

- The wound is the void between narrative policy and execution substrate.
- If the grammar has no primitive for a forbidden condition, the machine cannot halt on it.
- A rule embedded only in behavior is not a rule; it is behavior.
- Governance must be separable, inspectable, and enforceable.
- Omega says no through grammar, not vibes.

## Primary claims of SGF

1. **Symbol grounding needs a stopping rule.** The regress problem does not prove that operational machine grounding is impossible. It proves that grounding cannot be left implicit. Like Achilles and the tortoise, the infinite decomposition sounds decisive until the missing convergence mechanism is supplied.
2. **Vectors are not enough.** Embeddings retrieve semantic proximity, not role structure, provenance, authority, or act type.
3. **Prose is not enough.** Prose carries ambiguity, ellipsis, quotation, dispute, implication, sarcasm, fiction, questions, commands, and missing context.
4. **Triples are not enough.** Subject-predicate-object fragments event structure and recreates predicate explosion.
5. **The verb belongs at the hub.** The event/relation/action sits at the center; participants attach through fixed roles.
6. **The role grammar must be closed.** Vocabulary can remain open, but the structural roles must stay stable.
7. **Every claim needs provenance.** A claim without source trace is not audit-ready.
8. **A Synapse is not always a fact.** It is a grounded claim-bearing structure whose epistemic, rhetorical, normative, or fictional status must be framed.
9. **Identity must not merge destructively.** SAME_AS is proof-bearing and reversible, not default destructive merge.
10. **Context-free facts are liquid knowledge.** Once a fact carries its own disambiguated structure, it can travel, combine, be filtered, be audited, and be corrected.
11. **Meaning must be admissible.** Transmission is not admission. A receiver may refuse a valid message.
12. **Security is layered.** Integrity, authenticity, authorization, freshness, and confidentiality are different questions.
13. **Governance must be typed.** Machines cannot obey what their grammar cannot represent.
14. **Judgment remains outside the wire.** Protocols prepare, recommend, coordinate, and record. Authority decides.
15. **Vocabulary is a lossless macro-compiler for thought.** Words compress cognitive scripts; decompression must preserve geometry.
16. **The lexicon must be a cycle-free DAG.** Lossless reversibility requires strict downward paths, no loops.
17. **Polyhierarchy prevents the Hierarchy Stranglehold.** Reality supports multiple valid IS_A parents; single inheritance forces false dilemmas.
18. **Orthogonal axes prevent predicate explosion.** The lexicon decomposes meaning along two orthogonal axes: Y-axis (IS_A, HAS_PART) for object logic and type structure; X-axis (VerbHub, 15 roles) for event logic and action. This dual-axis architecture enables the Bounded Complexity Theorem: fixed skeleton (closed grammar on both axes), open vocabulary (infinite lexicon growth via pointers). Attempting to map spatial composition using event predicates, or events using only ontological edges, creates infinite tangled webs.
19. **Function and purpose must be separated.** VerbHub carries mechanical action; HAS_REASON carries intent. Without this split, scalpel = box cutter.
20. **Asymmetric engagement prevents Schema Babel.** Pure matter, pure action, and dual-axis concepts engage only the axes they demand.
21. **The Prime Registry is the bedrock stopping rule.** Approximately 65 NSM primes serve as terminals. Paths must reach primes or be marked UNRESOLVED.
22. **Deferred resolution is the HTML of meaning.** Definitions are pointer patterns, not nested walls of text. SynapseGroups are forbidden in lexicon entries.
23. **UNRESOLVED is explicit ignorance, not failure.** A high-integrity map declares the boundaries of its own knowledge.
24. **The symbol grounding impossibility claim is an overclaim.** The argument that symbols cannot be grounded is the ancient infinite regress fallacy in new clothes: A needs proof B, B needs proof C, C needs proof D, forever. Taken literally, this would make mathematics, physics, chemistry, law, code, and engineering impossible—yet people board airplanes, use compilers, enforce contracts, and administer medicine. The regress paradox does not prove grounding is impossible; it proves that working systems require explicit stopping rules, not infinite chains. For machine-to-machine communication, the stopping rule is protocol admissibility, not metaphysical certainty.
25. **Operational grounding is not phenomenological grounding.** Machines do not need the totality of human embodiment, sensation, or lived experience to coordinate. They need enough shared structure for a receiver to know what is being referred to, what evidence supports it, what act is being performed, and whether local policy permits admission. The stop is not metaphysical certainty. It is an admissible address.

## Secondary claims and support claims

- **Microglosses prevent lemma collapse.** A lemma alone cannot identify sense.
- **Canonical IDs make machine interlingua possible.** Machines can pivot through shared sense-level addresses rather than translating prose.
- **Content fingerprints accelerate matching but do not prove identity.**
- **Embeddings are tools, not truth.** They route candidates; they do not adjudicate grounding.
- **GapReports are a feature, not a failure.** A system that reports uncertainty is safer than one that fabricates completion.
- **SynapseGroups let larger thought units remain addressable.**
- **Frames prevent category collapse.** Allegation, testimony, denial, rule, command, and fiction must not be flattened into one truth layer.
- **TrustLens prevents false universal truth.** Different source classes, perspectives, jurisdictions, and time horizons need different query lenses.
- **Knowledge Packs make knowledge portable.** Domain knowledge, laws, reference corpora, or lexicons can travel as signed bundles.
- **Sidecars make adoption practical.** Legacy systems can speak HFF/AFP through wrappers without a flag-day migration.
- **Capability exchange collapses the integration tax.** Compatibility becomes a protocol negotiation, not bespoke engineering per pair.
- **Receiver sovereignty prevents botnet behavior.** A valid command is not automatically admitted.
- **Versioning pain is irreducible.** It can be localized by separating wire format, act registry, capability schema, and contract/governance grammar.
- **Selective disclosure separates surfaces.** A receiver can see enough to verify admissibility without exposing every payload detail to every intermediary.

## Pain points SGF solves

- LLM hallucinations without proof traces.
- RAG systems that retrieve relevant prose but not structured knowledge.
- Vector-only systems that confuse topical similarity with identity or role structure.
- RDF/predicate explosion and triple shattering.
- Schema Babel and N-squared integrations.
- Entity-resolution collapse, especially with names, aliases, and homonyms.
- Context-window amnesia.
- Knowledge graphs that store strings but not source-bound meaning.
- False merges caused by local identifiers or private database keys.
- Legal/medical/financial audit failure when claims cannot be traced.
- Prose policy that cannot govern machines.
- Multi-agent systems stepping on each other’s state.
- Machine-to-machine messages that rely on probabilistic interpretation.
- Security designs that confuse signature with authority or truth.
- Swarms and agents that cannot refuse unsafe instructions.
- Knowledge packs or corpora imported as truth without source class, authority, or TrustLens.

## Architectural Failure Modes

SGF identifies and prevents four critical failure modes that plague naive lexicon and knowledge graph designs:

### Lemma Collapse

**Lemma Collapse** is a fatal routing error that occurs when a system treats a surface word (lemma) as if it were a unique concept, ignoring that the same lemma can hide entirely different structural realities.

Example: "bank" as lemma collapses `bank.river_edge.noun`, `bank.financial_institution.noun`, and `bank.storage_collection.noun` into one ambiguous node. A machine instructed to deconstruct "bank" will crash unless it is explicitly handed a Canonical ID with a microgloss.

**Prevention:** Canonical IDs with microglosses. Decompression always starts from a sense-level address, never from a bare lemma.

### Hierarchy Stranglehold

**Hierarchy Stranglehold** is the dead end where single-inheritance taxonomies force unnatural either/or choices, breaking reality's multiple valid perspectives.

Example: Forcing "tomato" to be exclusively `IS_A: fruit` (botanical truth) or exclusively `IS_A: vegetable` (culinary truth) creates a false dilemma. Reality supports both.

**Prevention:** Polyhierarchy on the Y-Axis. A concept may have multiple `IS_A` parents. The DAG constraint (no cycles) remains absolute, but multiple parents are explicitly allowed and encouraged where reality demands them.

### Schema Babel

**Schema Babel** occurs when a schema forces every concept to have every kind of structure, manufacturing false actions for static objects and false objects for pure events. No one can trust what any role or axis actually means.

Example: Forcing "archipelago" (a static spatial pattern of land and water) to have a VerbHub and event roles, or forcing "murder" (a pure event script: causing someone to die under specific conditions) to have HAS_PART relations as if it were a physical object.

**Prevention:** Asymmetric engagement on orthogonal axes. Concepts engage only the axes their geometry demands:
- **Pure Matter:** Y-Axis only (`IS_A`, `HAS_PART`) — spatial structures, compositions, static types
- **Pure Action:** X-Axis only (VerbHub, 15 roles) — event scripts, actions, state changes
- **Purposeful Objects:** Both axes — artifacts with composition (Y) and default action scripts (X)

The decompression procedure decides per Canonical ID which axis or axes to engage, driven by the concept's core script. Symmetry is not required; honesty is.

### Predicate Explosion

**Predicate Explosion** occurs when every new relation or nuance requires a new predicate or role, leading to infinite schema growth and N-squared integration costs.

**Prevention:** The Bounded Complexity Theorem. SGF uses a **fixed skeleton** (15 semantic roles, `IS_A`, `HAS_PART`, closed verb features) paired with **open vocabulary** (infinite lexicon growth via pointer logic). Complexity is pushed into the lexicon graph, not into the grammar.

## What makes SGF powerful

- **Fixed skeleton, open vocabulary.** The 15 roles stay stable; the lexicon can grow.
- **Meaning as addressable structure.** Claims, entities, sources, frames, groups, and acts become inspectable objects.
- **Operational grounding without metaphysical overclaim.** SGF does not need to solve consciousness to support machine coordination.
- **Portable context.** HFF carries the context needed to hydrate meaning elsewhere.
- **Receiver sovereignty.** The receiving system decides what enters its state.
- **Adoption path.** Sidecars let existing systems participate without rewriting the world.
- **Auditability.** SourceDocument, SourceSpan, ProofTrace, content hash, signatures, receipts, frames, and lifecycle state support reconstruction.
- **Federation.** Independent systems can share meaning without centralizing all knowledge.
- **Governance.** Omega gives policy a grammar machines can parse.
- **Future world.** SGF enables liquid knowledge, knowledge markets or libraries, federated graphs, safer swarms, governed agents, regulated machine action, and eventually Global Ark-like public knowledge infrastructure.

## Payload lines

- The stop is not metaphysical certainty. It is protocol admissibility.
- A paragraph is not knowledge merely because it is relevant.
- The verb could not be the edge. The verb had to be the hub.
- A Synapse is the smallest unit of meaning that still functions.
- Vectors retrieve vibe; Synapses preserve structure.
- Meaning is not enough. Meaning must be admissible.
- Probably understood is not a protocol.
- Context is part of the message.
- Triples describe. Acts bind.
- The receiver is sovereign.
- A swarm that cannot refuse is a botnet.
- Middleware translates for one relationship. A sidecar exposes a reusable protocol face.
- Governance protects interoperability, not permission.
- Prose does not govern machines.
- Protocols carry structure. Judgment remains outside the wire.
- Vocabulary is a compiler, not a cloud. Language compresses scripts into tokens; the lexicon decompiles them.
- The lexicon is a DAG, not a dictionary.
- Polyhierarchy is geometry, not compromise.
- Fixed skeleton, open vocabulary.
- Embeddings hunt; symbols decide.
- Function is what it does; purpose is why.
- Pure matter, pure action, or both—never fake it.
- The primes are bedrock, not metadata.
- Deferred resolution scales; inlining explodes.
- UNRESOLVED is honesty, not failure.
- The grounding impossibility claim proves too much. It would abolish math, law, and code.
- Grounding is admissible address, not metaphysical certainty.
- Operational grounding ≠ phenomenological grounding.
- Y-axis: what it is. X-axis: what happens. Never confuse them.

## Common misunderstandings to avoid

- Do not say SGF solves the philosophical symbol grounding problem. Say SGF solves the operational grounding problem for machine communication by providing explicit stopping rules at shared, inspectable addresses.
- Do not say SGF makes hallucination impossible. Say SGF makes unsupported claims visible, traceable, rejectable, or quarantinable.
- Do not say signatures prove truth. They prove signed bytes under a key.
- Do not say fingerprints prove identity. They support candidate matching and hydration.
- Do not say every Synapse is a fact. It is a claim-bearing structure.
- Do not say AFP act types are semantic roles.
- Do not treat QUARANTINE as a core AFP act.
- Do not add new core roles for every relation.
- Do not treat Omega as a mere policy checklist. It is a governance grammar.
- Do not treat the Global Ark as already built.
- Do not treat future AI OS or code factory material as SGF v1.0 canon.

## Canon locks

Use these terms and structures unless the user explicitly asks to discuss older drafts.

- Use **Core Lexicon**, not Axiom Lexicon.
- Use **Synapse** for the atomic claim-bearing structure: one VerbHub plus many role-bound Spokes.
- Do not call every Synapse a fact. A Synapse may carry a factual claim, testimony, allegation, denial, opinion, hypothesis, command payload, question payload, request payload, promise payload, rule, motivation, directive, constraint, invariant, governance law, or fictional proposition.
- Use the closed SGF Core 1.0 role set of **15 semantic roles**.
- Do not add core roles such as HAS_STIMULUS, HAS_PURPOSE, HAS_RESULT, HAS_VALUE, HAS_WHOLE, HAS_CONDITION, HAS_PATH, or HAS_PROVENANCE.
- Use **PropositionalFrame**, **NormativeFrame**, **ActFrame**, **GeneralizationFrame**, **PerspectiveFrame**, **TrustLens**, and **ReasoningContext** to carry distinctions that do not belong in the role set.
- Use **AFP act types**: INFORM, ADVISE, REQUEST, QUERY, COMMAND, PROMISE, PROPOSE, ACCEPT, REFUSE, CANCEL, CONFIRM, ACK, ERROR.
- Do not use ASSERTION or QUESTION as AFP act types. They may appear as propositional payload kinds in the core spec, not as AFP illocutions.
- Treat QUARANTINE as a receiver disposition or handling state unless a domain profile explicitly defines a wrapper. QUARANTINE is not a core AFP act.
- Use HFF canonical text encoding: `application/hff+json`.
- Alternative HFF encodings such as `application/hff+cbor`, `application/hff+msgpack`, or `application/hff+binary` are only conformant if they preserve the HFF logical message model, declare canonicalization/hash/signature byte rules, preserve LexiconManifest hydration, and round-trip to canonical JSON without semantic loss.
- Signatures prove canonical bytes were signed by a key. They do not prove truth, authority, safety, or wisdom.
- A content hash proves content integrity. A content fingerprint supports semantic matching and hydration. A fingerprint does not prove identity.
- SGF Core is backend-neutral. It may be implemented in graph databases, relational databases, document stores, object stores, embedded databases, files, custom memory structures, or hybrids.

## The foundational claim

SGF’s operational answer to the symbol grounding problem is the stopping rule.

The regress problem begins with a simple demand. If A is accepted as true, A needs proof. Suppose B is the proof. But B cannot support A unless B is also true, so B needs proof. Suppose C is the proof of B. But C now needs proof as well. The chain continues: D must prove C, E must prove D, and so on without end. If the demand is taken literally, nothing can ever be proven, because every proof arrives needing another proof behind it.

The logic looks clean. The conclusion is unusable.

The pattern is familiar. Achilles never catches the tortoise if motion is described as an infinite sequence of remaining intervals. First Achilles must reach the place where the tortoise was. By then the tortoise has moved. Achilles must reach the next place. By then the tortoise has moved again. The sequence can be subdivided forever. The reasoning appears impeccable. The conclusion is false. Achilles catches the tortoise. The runner reaches the finish line. The paradox does not abolish motion. It exposes a missing account of convergence.

The grounding regress has the same character. If every symbol must be grounded by another symbol, and that symbol by another, then no symbol can ever be grounded. Taken literally, that argument proves too much. It would make mathematics, physics, chemistry, law, code, engineering, and ordinary language unusable. Their notations would point only to other notations, and no finite procedure would explain why action is warranted. Yet people board airplanes, use compilers, trust equations, administer medicine, enforce contracts, and build bridges. Working systems avoid paralysis by defining where their symbols stop, what evidence binds those stops, and what procedures govern use.

This does not make the original symbol grounding problem trivial. A system that manipulates symbols according to formal rules does not acquire meaning merely because the manipulations are fluent. A dictionary that defines every word in terms of other words can become a closed room. A model that predicts tokens can produce impressive sentences while leaving the receiver unsure which entity, sense, authority, source, time window, or action boundary the sentence refers to. The problem is real.

The overclaim begins when the real problem becomes an impossibility claim.

SGF makes the stopping rule explicit. The Core Lexicon provides shared, inspectable addresses for meaning. Non-core terms can travel, but they must bring mini-lexicon entries and IS_A tethers back toward Core. The stop is not metaphysical certainty. It is protocol admissibility. Machines do not need the totality of human meaning to coordinate. They need enough grounded structure to make the receiver’s next act admissible.

Operational grounding is not phenomenological grounding. A human may learn “hot” through pain, embodiment, memory, and danger. A robot does not need to feel pain to refuse a movement that violates a thermal safety threshold. A clinical system does not need to experience illness to bind a lab value to a medical category. Machine-to-machine grounding requires enough shared structure for a receiver to know what is being referred to, what evidence supports the reference, what act is being performed, and whether local policy permits admission.

### Mini-essay: The Stopping Rule

The symbol grounding impossibility claim is too large.

Its strongest form depends on a regress: a symbol must be grounded by something outside itself; that ground must also be grounded; the next ground must be grounded again; the chain continues forever. The argument sounds rigorous because every step asks a fair question. What supports A? B. What supports B? C. What supports C? D. If the demand is never allowed to stop, nothing can be grounded.

But that conclusion proves too much. The same style of argument would make mathematics, physics, chemistry, law, code, engineering, and ordinary language unusable. Equations are symbols. Statutes are symbols. Chemical formulas are symbols. Source code is symbols. People still board airplanes, use compilers, trust bridges, administer medicine, and enforce contracts because working systems do not wait for infinite proof. They define finite stopping rules, evidence standards, authority chains, and procedures for use.

The pattern is the same as Achilles and the tortoise. The race can be decomposed into infinitely many remaining intervals, but Achilles still arrives. The paradox does not prove motion impossible. It exposes the need for a better account of convergence. The grounding regress does not prove operational machine grounding impossible. It exposes the need for a better account of where machine definitions stop.

SGF supplies that account. The Core Lexicon gives machines shared, inspectable addresses. Canonical IDs identify sense-level meaning. Microglosses disambiguate lemma-mates. IS_A chains prevent circular definition. Non-core terms travel with mini-lexicon entries and their path back toward Core. The receiver does not have to believe the claim, admit the term, or execute the act. The receiver only has enough grounded structure to inspect the proposal and decide.

The stop is not metaphysical certainty. It is protocol admissibility.

The mistake is to treat grounding as one thing. Human grounding includes embodiment, sensation, memory, pain, and lived consequence. Operational grounding for machine coordination is a narrower, solvable problem that does not require phenomenological grounding, embodiment, or lived human experience. A thermal sensor does not need to feel pain to enforce a safety threshold. A clinical system does not need to experience illness to bind a lab value to a category. Machines do not need the totality of human meaning to coordinate—they need enough shared structure to make the receiver's next act admissible.

## SGF Core invariants

Every conforming SGF implementation must preserve:

- **Identity**: entities, senses, instances, sources, and Synapses have stable references.
- **Structure**: meaning is represented by VerbHubs, Spokes, roles, frames, links, and groups rather than floating prose.
- **Provenance**: exported objects carry SourceDocument, SourceSpan, ProofTrace, or equivalent audit material.
- **Time**: the system distinguishes world time, document/order time, system ingestion time, validity windows, and lifecycle state where applicable.
- **State**: claims and objects can be asserted, disputed, retracted, superseded, hypothetical, fictional, or otherwise framed without destructive overwrite.
- **Authority**: the system distinguishes who said something, who signed something, who is authorized to act, and which authority governs a rule or claim.
- **Composition**: Synapses can connect to Synapses and groups can connect to groups without exploding the role vocabulary.

## Core Lexicon

The Core Lexicon is the shared grounding substrate for common meaning. It is a **compiled artifact**: given the same dictionary snapshot, Prime Registry, and pipeline configuration, any party should be able to rebuild it and match its structure and content hash.

The Core Lexicon is not merely a dictionary. It is a **sense-level Directed Acyclic Graph (DAG)** with canonical identifiers, microglosses, part-of-speech information, source traces, **IS_A relations forming a polyhierarchy**, optional HAS_PART/PART_OF relations, optional descriptive Synapses, and optional media/perceptual assets.

The project basis is a large open lexicon derived from Wiktionary-scale open dictionary material, roughly on the order of 1.7 million entries/senses, then bootstrapped into sense-level LexiconEntry records.

### The Decompression Map as Lossless Reversal

The Core Lexicon functions as a **reversible decompression map** for vocabulary. Language vocabulary is a high-density, lossless macro-compression codec: humans "zip" massive logical structures into single-word tokens to transmit them through the slow serial interface of speech.

Because this compression is lossless, SGF can reverse it: any macro can be deconstructed back into its parent concepts without losing structural integrity. Traditional dictionaries fail at this reversibility because they are **lossy algorithms** that define complex words using other complex words (*Pail = Bucket, Bucket = Pail*), creating infinite circular loops that leak geometry at every step.

The Core Lexicon is a **deterministic, lossless unzipping process** that forms a strict DAG, moving exclusively downward toward physical reality through the Prime Registry.

### Orthogonal Axes: Y-Axis and X-Axis Decomposition

The lexicon decomposes meaning along **two orthogonal axes** to prevent predicate explosion and enable bounded complexity:

**Y-Axis (Object Logic / Lexicon Plane):**
- Defines what a thing *is* and what it is *made of*
- Uses `IS_A` (polyhierarchic, allowing multiple parents) and `HAS_PART` / `PART_OF`
- Captures type structure, composition, and taxonomy
- Example: `calico_cat IS_A domestic_cat IS_A cat IS_A mammal IS_A animal → primes`
- Example: `bicycle HAS_PART wheel, frame, pedal`

**X-Axis (Event Logic / Synapse Plane):**
- Defines mechanical action and event structure
- Uses VerbHub (the event/action) + 15 closed semantic roles
- `HAS_REASON` separates mechanical *function* (what it does) from intended *purpose* (why it's used)
- Example: `scalpel` — VerbHub: CUT, HAS_INSTRUMENT: blade, HAS_REASON: surgical_procedure
- Example: `box_cutter` — VerbHub: CUT, HAS_INSTRUMENT: blade, HAS_REASON: open_packaging

**Asymmetric Engagement** (preventing Schema Babel):
- **Pure Matter**: Y-axis only (e.g., `archipelago`, `forest` — spatial arrangements with no default action)
- **Pure Action**: X-axis only (e.g., `murder`, `theft` — event scripts with no physical parts)
- **Purposeful Objects**: Both axes (e.g., `wagon`, `hammer`, `mortgage` — composition + default scripts)

The decompression procedure decides per Canonical ID which axis or axes to engage, driven by the concept's core script, not by forcing every concept into both structures.

**Language as Compiler**: Vocabulary compresses complex cognitive scripts into single tokens for transmission through the slow serial interface of speech. The lexicon is the decompiler: it reverses that compression losslessly by following pointer chains down orthogonal axes until every branch terminates at primes or is marked UNRESOLVED.

**Deferred Resolution (The HTML of Meaning)**: Definitions are flat pointer patterns, not nested expansions. When defining `wagon`, the system points to `wheel` via `HAS_PART` but does not inline the definition of wheel. This keeps local geometry flat and allows the lexicon to scale. SynapseGroups are forbidden in lexicon entries; they belong to discourse-level structures.

Required or core LexiconEntry concepts:

- `canonical_id`
- `lexicon_scope` or `lexicon_id`
- `namespace_id`
- `language_tag` or `iso_lang_code`
- `lemma`
- `part_of_speech`
- `microgloss`
- `grounding_status` (`GROUNDED` or `UNRESOLVED`)

Recommended concepts:

- `content_fingerprint`
- `is_a_core`
- `is_a_chain`
- `gloss`
- `example_sentence`
- `synonyms`
- `source_refs`
- `version`
- `authority_frame_id`
- `content_hash`
- `status`

The lemma is the surface form. The microgloss disambiguates the lemma from its lemma-mates. It does not need to disambiguate the term from the entire universe of language; it needs to identify which sense of a shared lemma is intended. A term like “bank” needs a microgloss that separates financial institution from river edge, not an essay about all possible banking metaphors.

Non-core lexicons extend the Core Lexicon:

- domain or industry lexicons,
- business or organization lexicons,
- corpus lexicons,
- document lexicons,
- temporary mission lexicons,
- product or device lexicons.

Non-core entries exported across trust boundaries should include an IS_A bridge to the nearest Core Lexicon ancestor. If no bridge is known, unresolved grounding must be declared rather than hidden.

### The Prime Registry: Bedrock Stopping Rule

The **Prime Registry** is SGF's bedrock stopping rule. It contains approximately **65 semantic primes** based on Natural Semantic Metalanguage (NSM) research. These primes are irreducible concepts that point directly to **universal physical constants and human sensorimotor reality**. They serve as the **final machine code of thought**.

**Categories of Primes:**

- **Substantives:** I, YOU, SOMEONE, SOMETHING, PEOPLE, BODY
- **Actions and Events:** DO, HAPPEN, MOVE
- **Cognition:** THINK, KNOW, WANT, FEEL
- **Perception:** SEE, HEAR, TOUCH
- **Evaluation:** GOOD, BAD
- **Logic and Relations:** NOT, MAYBE, CAN, BECAUSE, IF
- **Space:** WHERE, HERE, ABOVE, BELOW, INSIDE, NEAR, FAR, SIDE
- **Time:** WHEN, NOW, BEFORE, AFTER
- **Quantification:** ONE, TWO, SOME, ALL, MANY, MUCH
- **Intensifiers:** VERY, MORE

Primes in the Prime Registry:
- Have **no further lexical decomposition** within the lexicon
- Serve as **terminals** in `IS_A` chains
- Map directly to physical, sensorimotor, or temporal interfaces where possible (MOVE → motor control, TOUCH → tactile channels, BEFORE/AFTER → temporal ordering, WHERE → spatial coordinates)
- Are represented as protected Canonical IDs with `grounding_status = GROUNDED`
- Function as docking points where symbolic paths terminate and operational grounding begins

The 65 Primes serve as the final machine code of thought because they either dock to physical constants and sensorimotor reality, or stand as the simplest cross-lingual abstractions the system is allowed to trust without further decomposition.

### Polyhierarchy and the Hierarchy Stranglehold

SGF's `IS_A` structure is explicitly **polyhierarchic**. A sense may have **multiple `IS_A` parents** without violating the geometry. This avoids the **Hierarchy Stranglehold**—the dead end where single-inheritance trees force unnatural either/or choices and break reality's multiple valid perspectives.

**Examples of polyhierarchy in action:**
- An **amphibious vehicle** may be `IS_A: car` and `IS_A: boat` simultaneously
- A **tomato** may be `IS_A: fruit` (botanical classification) and `IS_A: vegetable` (culinary classification)
- A **mortgage** may be `IS_A: debt_instrument` and `IS_A: real_estate_contract` and `IS_A: secured_loan`

Polyhierarchy lets reality's multiple perspectives coexist without forcing false singularity. The DAG constraint remains absolute: **no `IS_A` cycles are permitted**. Cycle detection runs during lexicon builds and rejects any edge that would introduce a cycle.

### Grounding Status: GROUNDED vs UNRESOLVED

Every LexiconEntry has a `grounding_status`:

- **`GROUNDED`**: At least one finite `IS_A` path (and possibly multiple paths due to polyhierarchy) to primes exists through the DAG
- **`UNRESOLVED`**: No path to primes can be found, or geometry is broken, purely abstract, culturally opaque, or would require cycles

**UNRESOLVED is explicit ignorance, not failure.** A high-integrity decompression map prevents machine hallucination by formally mapping the boundaries of its own knowledge. The algorithm does not fabricate paths when grounding fails; it declares uncertainty.

Entries marked `UNRESOLVED`:
- Are either excluded from Core entirely, or
- Included with an explicit `UNRESOLVED` marker and **barred from serving as `IS_A` parents**
- May still be useful for domain work but cannot anchor other concepts' grounding

This safety valve ensures the lexicon remains auditable: every `GROUNDED` entry can demonstrate a finite path to primes; every ungroundable concept is explicitly flagged.

### Core Lexicon Bootstrapping Overview

The Core Lexicon is built through a reproducible pipeline that operationalizes the reversible semantic compression theory:

**Step 0: Ingest and Sense Extraction**
- Ingest dictionary snapshot (e.g., Wiktionary dump at specific date)
- Extract senses, assign provisional Canonical IDs with microglosses
- Build **Canonical Descriptions** (lemma + microgloss + POS + gloss + hypernyms + synonyms + examples)
- Compute embeddings and `content_fingerprint` under **Exact Profile Contract**

**Step 1: Build the `IS_A` DAG**
- Collect parent candidates from dictionary hypernyms and embedding similarity
- Map candidates to senses via Canonical IDs
- Score candidates by lexical evidence, structural coherence, and advisory similarity
- Add `IS_A` edges with **DAG constraints** (no cycles) and **polyhierarchy support** (multiple parents allowed)

**Step 2: Add Ontological Structure**
- Add `HAS_PART` / `PART_OF` relations for type-level composition
- Keep behavior and purpose out of parts (those belong in Synapses and default scripts on the X-axis)
- Maintain separation of concerns between Y-axis structure and X-axis events

**Step 3: Grounding Checks via Prime Registry**
- Search for paths to primes by following `IS_A` edges upward
- Respect the DAG; do not introduce cycles or fabricate shortcuts
- Assign `grounding_status`: `GROUNDED` if at least one finite path to primes exists, `UNRESOLVED` otherwise
- Respect the **Coverage Gate**: embeddings hunt for candidates, symbols and Prime Registry paths decide grounding

**Step 4: Canonical `isa_chain` and Release Packaging**
- Derive one canonical `isa_chain` path per sense (shortest path, preferred upper-ontology parents)
- The underlying DAG with polyhierarchy remains intact; `isa_chain` is a convenience projection
- Assemble **LexiconRelease manifest** with signature and content hash
- Export and freeze (Core Lexicon becomes read-only for that release)

The full bootstrapping cookbook is in Appendix X.

### LexiconRelease Manifest

A Core Lexicon release includes a **LexiconRelease manifest** with:

- `lexicon_id`, `lexicon_scope` (`core` reserved for Core), `version`, `uri`
- `content_hash` (cryptographic hash over canonical export)
- `signature` (issuer's signature over that hash)
- `source_basis` (dictionary snapshot ID and date)
- `pipeline_version`, `patch_set_version`, `prime_set_version`
- `language_coverage` (languages included in this release)
- `issued_at`, `issuer`

Any implementation that claims to use a Core release should be able to reconstruct it from the recipe and match the hash. The Core Lexicon is a **compiled artifact**, not hand-crafted ontology.

## Canonical IDs

A Canonical ID identifies a sense-level LexiconEntry. It should be treated as a structured identifier, not only a dotted printable string. Recommended logical components include:

- language tag,
- lemma,
- microgloss,
- part of speech,
- namespace or lexicon scope.

The printable form is useful for human reading and debugging, but conforming exchange should not rely on parsing dotted strings when structured fields are available. The important point is not the punctuation. The important point is that machines share a stable address for meaning.

A Canonical ID is a machine interlingua. It is not a perfect human translation layer. It lets machines in different languages, organizations, or domains point to the same sense-level meaning. It supports cross-language pivoting when the lexicon build uses multilingual embeddings and cross-language evidence, but SGF does not claim that it solves all natural-language translation.

## Content hash and content fingerprint

SGF distinguishes content integrity from semantic proximity.

- `content_hash` proves that bytes or content did not change. It is a cryptographic integrity check.
- `content_fingerprint` supports semantic matching, lookup, hydration, and candidate retrieval. It is a locality-sensitive projection of an embedding.

### Exact Profile Contract

A `content_fingerprint` may be produced from an embedding of a **Canonical Description** (structured text combining lemma + microgloss + part of speech + gloss + hypernyms + synonyms + example sentences), then projected or encoded under a declared profile.

An **Exact Profile Contract** must declare:
- embedding model (e.g., multilingual sentence encoder)
- dimensionality (e.g., 1024 dimensions)
- pooling method
- normalization
- projection/hash method (e.g., 516 hyperplanes)
- bit depth
- seed or projection contract
- encoding (e.g., Base64URL)
- profile version

Different profiles are not comparable. Fingerprints computed under different profiles cannot be directly compared for similarity.

### Advisory Role Only

**Embeddings and fingerprints are advisory tools.** They propose candidate parents, retrieve similar senses, and accelerate matching. They **never override symbolic constraints, cycle checks, or grounding rules**.

In the bootstrapping pipeline:
- Embeddings hunt for candidate parents
- Symbolic graph structure and Prime Registry paths decide grounding
- Fingerprints accelerate candidate retrieval
- DAG constraints and `IS_A` logic determine final parentage

Fingerprints are useful for narrowing candidates. They do not prove identity. Identity requires lexicon evidence, manifests, source traces, proof, and receiver-side admission.

The canonical rule: **Embeddings are tools, not truth. They route candidates; they do not adjudicate grounding.**

## Synapse

A Synapse is SGF’s atomic unit of structured meaning.

```text
Synapse = one VerbHub + many role-bound Spokes
```

Required fields:

- `synapse_id`
- `hub`
- `spokes`
- `proof_trace_id`

Recommended frame and state references:

- `temporal_frame_id`
- `act_frame_id`
- `propositional_frame_id`
- `validation_state_id`
- `authority_frame_id`
- `lifecycle_state_id`
- `profile_context_id`

The VerbHub required fields are:

- `verb_canonical_id`
- `actuality_status`

Recommended verb fields include:

- `verb_content_fingerprint`
- `verb_features`
- `polarity`
- `modality`
- `voice`
- `tense`
- `aspect`
- `mood`
- `verb_grounding_trace_id`

A Spoke required fields are:

- `role`
- `target_type`
- `target_ref`

Allowed target types include:

- `LEXICON_ENTRY`
- `DOCUMENT_ENTITY`
- `BUSINESS_ENTITY`
- `INSTANCE`
- `TYPED_LITERAL`
- `PLACEHOLDER`
- `GHOST`
- `SYNAPSE`
- `SYNAPSE_GROUP`

Spokes can point to other Synapses or SynapseGroups. This is how meaning nests without exploding the number of primitive roles.

## The 15 semantic roles

SGF Core 1.0 has a closed role set. These roles form the **X-Axis (Event Logic)** of the orthogonal axes architecture. They operate on Synapses (claim-bearing structures about specific events), while the **Y-Axis (Object Logic)** operates on LexiconEntry type definitions using `IS_A` and `HAS_PART`.

The 15 roles are:

```text
HAS_AGENT
HAS_PATIENT
HAS_THEME
HAS_EXPERIENCER
HAS_RECIPIENT
HAS_BENEFICIARY
HAS_TIME
HAS_LOCATION
HAS_SOURCE
HAS_DESTINATION
HAS_MANNER
HAS_INSTRUMENT
HAS_CAUSE
HAS_REASON
HAS_ATTRIBUTE
```

These roles answer recurring structural questions: who acts, who or what is affected, what is moved or considered, who experiences, who receives, who benefits, when, where, from where, to where, how, with what, because of what cause, for what reason, and with what attribute.

Do not solve every relation by inventing new roles. If a meaning does not fit the 15 roles, first consider whether it belongs in:

- a TypedLiteral,
- a LexiconEntry,
- a SynapseLink,
- a SynapseGroup,
- a ProofTrace,
- a SourceDocument or SourceSpan,
- an ActFrame,
- a PropositionalFrame,
- a NormativeFrame,
- a GeneralizationFrame,
- a PerspectiveFrame,
- a TrustLens,
- a ReasoningContext,
- a domain profile,
- or an extension namespace.

## Verb dimensions and the 3-tier Verb Engine

Verbs are the hubs of Synapses. Verb features encode the event’s internal geometry.

The substrate prose describes a 3-tier Verb Engine:

- **Standard**: around 10 dimensions, enough for general web/chat use. Includes basic tense, aspect, polarity, and related features.
- **High-Fidelity**: around 20 dimensions, adding features such as evidentiality and volition. Used for legal, medical, and other high-stakes domains where the difference between “he said” and “I observed” matters.
- **Archival**: around 41 dimensions, adding deep linguistic features such as obviation, clusivity, and directionals. Used when preserving linguistic nuance matters.

Downsampling is possible. Upsampling is not. If a pipeline only extracts low-fidelity verb features, it cannot later recover the evidential, volitional, or directional distinctions it failed to capture.

The exact 41-feature list is an implementation/profile detail unless a specific verb-feature profile declares it. Do not treat the tier system as a reason to add core semantic roles. Verb features belong on the VerbHub or associated frames.

## Frames

Frames describe what the fixed Synapse grammar is carrying. They do not add semantic roles.

### ActFrame

ActFrame is the general SGF frame for communicative and coordination acts. It can carry illocution, payload reference, sender, recipient or scope, deontic type, actuality status, authority frame, proof trace, temporal frame, priority, deadline, acknowledgement requirement, and conversation ID.

ActFrame is broader than assertion. Commands, questions, requests, promises, advice, refusals, confirmations, and acknowledgements are acts even when they are not assertions.

### PropositionalFrame

PropositionalFrame classifies claim-bearing content. Starter propositional kinds include:

- `FACTUAL_CLAIM`
- `TESTIMONY`
- `ALLEGATION`
- `DENIAL`
- `OPINION`
- `PHILOSOPHICAL_THESIS`
- `HYPOTHESIS`
- `ASSERTION`
- `COMMAND_PAYLOAD`
- `QUESTION_PAYLOAD`
- `REQUEST_PAYLOAD`
- `PROMISE_PAYLOAD`
- `RULE`
- `MOTIVATION`
- `DIRECTIVE`
- `CONSTRAINT`
- `INVARIANT`
- `CAPABILITY`
- `GOVERNANCE_LAW`
- `FICTIONAL_PROPOSITION`

### NormativeFrame

NormativeFrame is used when a proposition shapes behavior. Normative kinds include:

- `ADVISORY`
- `DEFAULT_RULE`
- `DUTY`
- `PROHIBITION`
- `PERMISSION`
- `EXCEPTION`
- `OVERRIDE_RULE`
- `META_RULE`
- `CONSTRAINT`
- `INVARIANT`
- `GOVERNANCE_LAW`
- `OMEGA_RULE`

### GeneralizationFrame

GeneralizationFrame marks when a specific claim, rule, example, or episode becomes a generalized proposition. Generalized rules are derived unless the source explicitly states the general rule. This prevents specific examples from silently becoming universal laws.

### PerspectiveFrame

PerspectiveFrame records the point of view, speaker, claimant, witness, author, institution, philosophy, or authority from which a claim is made. It is mandatory for legal testimony, journalism, opinion, philosophical systems, scientific debate, and multi-source reasoning.

### TrustLens

TrustLens is a query-time and reasoning-time filter. It can filter by source class, epistemic status, derivation type, authority tier, confidence, jurisdiction, time horizon, contradiction policy, and whether opinion or testimony is allowed to behave as a world fact.

TrustLens is how SGF lets multiple perspectives coexist without collapsing them into one false “truth” layer.

### ReasoningContext

ReasoningContext binds a query or task to its trust lens, domain profile, corpus scope, time horizon, purpose, and output policy.

## Source, proof, and evidence

SGF separates:

- what the world claim says,
- who asserted it,
- where it came from,
- what status it has,
- which reasoning lens is being applied.

Key objects:

- **SourceDocument**: source type, title, locator, publisher, author/originator, publication/file date, retrieved time, jurisdiction, content hash, license/access policy.
- **SourceSpan**: where in the source the evidence appears, including document, span type, character range, page, section, quote.
- **ProofTrace**: source spans, extractor ID, extractor version, run ID, derivation type, validation events, creation time.
- **GapReport**: explicit report when grounding, role assignment, reference resolution, source span, frame determination, confidence threshold, preprocessing artifact, or lexicon bridge fails.

Gaps should be reported. They should not be hidden by fabricating structure.

## Synapse composition

SGF composes meaning through links and groups:

- **SynapseLink** connects one Synapse to another. It is not a Spoke role.
- **SynapseGroup** represents larger thought units: paragraphs, clauses, arguments, event clusters, timelines, definitions, method/result groups, contradiction groups, narrative arcs, and other addressable aggregations.
- **SynapseGroupMembership** records group membership and sequence.
- **SynapseGroupLink** connects groups to groups. It is not a Spoke role.

This composition system is how SGF builds larger structures without turning every relation into a new predicate or role.

## Identity

SGF treats identity as proof-bearing and reversible. `SAME_AS` is not destructive merge and is not transitive by default.

Recommended identity relations:

- `SAME_AS`
- `POSSIBLY_SAME_AS`
- `DIFFERENT_FROM`
- `INSTANCE_OF`
- `ALIAS_OF`
- `MENTIONS`

AmbiguityCluster represents unresolved identity and must not silently unwrap to the top candidate.

Instances are distinct from concepts. “Tom lives in a red brick house” must not attach “red brick” to the universal concept `house`. It should mint or resolve an instance and attach attributes to the instance, with an `INSTANCE_OF` or `IS_A` relation to the concept.

## Planes

Implementations should distinguish:

- `claim_plane`
- `evidence_plane`
- `identity_plane`
- `lexicon_plane`
- `reasoning_plane`

Default fact queries search the claim plane. Audit and legal explanation queries may traverse the evidence plane.

## GLEAN

GLEAN is the process that turns a CleanTextBundle into SGF objects. It does not ingest raw text directly.

Boundary:

```text
RawSourceArtifact
-> Preprocessing / Scrubbing
-> CleanTextBundle
-> GLEAN
-> SGF objects
```

GLEAN is a court reporter, not a mind reader. It records what can be grounded. It does not pretend to read minds, resolve every ambiguity, or capture total meaning.

Canonical stage contract:

1. Preprocessing produces CleanTextBundle and SourceArtifactMap.
2. Create GLEAN RunPlan.
3. Register SourceDocument and SourceSpans.
4. Build DocumentStructureMap.
5. Build draft EntityMap / DocumentLexicon.
6. Classify discourse mode.
7. Build draft DiscourseMap, ReferenceMap, ArgumentMap, MethodFrame, or NarrativeArc as needed.
8. Build draft ClauseMap.
9. Refine EntityMap.
10. Refine DiscourseMap.
11. Generate ClaimCandidates.
12. Apply GranularityPolicy and create ExtractionDecisions.
13. Assemble Synapses.
14. Assemble SynapseLinks.
15. Assemble SynapseGroups and memberships.
16. Assemble SynapseGroupLinks.
17. Create or finalize GapReports and Ghosts.
18. Attach ProofTrace, ValidationState, TemporalFrame, ActFrame, PropositionalFrame, NormativeFrame, GeneralizationFrame, PerspectiveFrame, AuthorityFrame, LifecycleState, and ProfileContext as applicable.
19. Run consistency checks.
20. Run reconstruction or round-trip checks when required.
21. Prepare LexiconManifest and HFF export readiness.

If older prose conflicts with the GLEAN specification, the GLEAN specification controls.

GLEAN must preserve quoted, reported, denied, hypothetical, fictional, command, request, and question structures without flattening them into world facts.

## Formal artifacts

Code, MIDI, equations, DNA, telemetry, Omega-Code, structured logs, and similar artifacts require adapters. Preserve the artifact. Extract SGF claim-bearing structures about the artifact. Do not pretend that formal artifacts are ordinary prose inputs.

## HFF: Hub Fact Format / wire protocol

HFF transports SGF objects across trust boundaries. HFF does not redefine SGF Core. It packages SGF objects, frames, lexicon manifests, provenance, hashes, signatures, receipts, and errors.

Canonical text encoding:

```text
application/hff+json
```

Required envelope fields:

- `hff_version`
- `encoding_profile`
- `message_id`
- `created_at`
- `sender`
- `payload`
- `integrity`

Recommended envelope fields:

- `recipient_ref`
- `recipient_scope`
- `expires_at`
- `nonce`
- `conversation_id`
- `schema_version`
- `sgf_core_version`
- `core_lexicon_release`
- `trust_anchor_ref`

Payload may contain:

- Synapses,
- SynapseGroups,
- SynapseLinks,
- SynapseGroupLinks,
- frames,
- SourceDocuments,
- ProofTraces,
- GapReports,
- LexiconManifest,
- AFP acts.

Every HFF message must be lexically hydratable. Non-core terms must include inline LexiconManifest entries or references to external scoped lexicons with URI, version, hash, and signature.

HFF security separates five questions:

- Integrity: did the content change?
- Authenticity: who signed this message?
- Authorization: is that sender allowed to perform this act?
- Freshness: is this message current, or a replay?
- Confidentiality: who is allowed to read it?

Security profiles include:

- `PUBLIC_SIGNED_BROADCAST`
- `CONFIDENTIAL_DIRECT`
- `CONFIDENTIAL_GROUP`
- `HIGH_RISK_COMMAND`
- `REGULATED_TRANSACTION`

Receivers must reject or quarantine messages when message IDs or nonces replay, expiry fails, signatures fail, keys are revoked or untrusted, payload hashes mismatch, or required lexicon/schema hashes fail.

HFF proves what was sent and who signed it. It does not prove that the action should be taken. Vehicles, drones, robots, weapons, factory systems, and medical devices must also check AuthorityFrame, risk class, local policy, safety profile, and current world state before acting.

## AFP: Act and Federation Protocol

AFP is the act and conversation layer over HFF.

```text
HFF moves meaning.
AFP acts with meaning.
```

AFP act types:

```text
INFORM
ADVISE
REQUEST
QUERY
COMMAND
PROMISE
PROPOSE
ACCEPT
REFUSE
CANCEL
CONFIRM
ACK
ERROR
```

Act types are not SGF semantic roles.

Single-act AFP envelope required fields:

- `afp_version`
- `afp_message_id`
- `thread_id`
- `sender_id`
- `illocution`
- `payload_ref`
- `hff_payload`
- `security_envelope`

Recommended fields:

- `recipient_ref`
- `recipient_scope`
- `conversation_transition`
- `ack_required`
- `deadline`
- `authority_required`
- `priority`

Multi-act messages use `acts[]`. Each act should include act ID, illocution, conversation transition, payload reference, authority requirement, acknowledgement requirement, and deadline.

Conversation-transition labels include:

- `PROPOSE`
- `COUNTER`
- `ACCEPT`
- `EXECUTE`
- `CONFIRM`
- `REFUSE`
- `ESCALATE`
- `CANCEL`
- `EXPIRE`
- `ERROR`

AFP act types and conversation-transition labels are related but not identical.

ACK confirms receipt, not agreement. ACCEPT accepts a proposal or request. CONFIRM records completion or state verification. REFUSE rejects an act or proposal. ERROR reports protocol failure, invalid transition, missing lexicon, missing authority, validation failure, or unsafe action.

## Discovery and capability manifests

Discovery lets participants announce identity, capabilities, versions, lexicons, endpoints, trust anchors, and limits. It does not define SGF meaning. It tells participants how to find and evaluate one another.

Recommended discovery location:

```text
.well-known/graph
```

Required manifest fields:

- `participant_id`
- `supported_sgf_versions`
- `supported_hff_versions`
- `supported_afp_versions`
- `endpoints`

Recommended fields:

- `supported_encoding_profiles`
- `supported_lexicons`
- `supported_knowledge_packs`
- `capabilities`
- `trust_anchors`
- `auth_methods`
- `rate_limits`
- `max_payload_size`
- `supported_act_types`
- `supported_domain_profiles`

Mobile systems may use temporary participant IDs, recipient scopes, broadcast scopes, capability manifests, trust anchors, credentials/certificates, expiry windows, and replay prevention.

Example recipient scopes:

- `vehicles_within_800m_ahead`
- `drones_in_formation_alpha`
- `robots_in_warehouse_zone_12`
- `agents_in_contract_thread_TH-92`

## Knowledge Packs

Knowledge Packs are versioned, signed bundles of SGF-compatible knowledge and/or lexicons.

Examples:

- Core Lexicon release,
- industry lexicon,
- Louisiana law pack,
- New Orleans municipal code pack,
- Wikipedia-derived factual reference pack,
- company corpus pack,
- common-sense physics pack.

Required package fields:

- `knowledge_pack_id`
- `version`
- `issuer`
- `issued_at`
- `source_class`
- `content_hash`
- `signature`
- `sgf_core_version`

Recommended fields:

- description,
- jurisdiction,
- authority tier,
- epistemic default,
- publisher trust model,
- recommended TrustLens,
- known limitations,
- license,
- dependencies,
- lexicon manifest.

Source classes include factual reference, legal authority, regulatory authority, scientific literature, testimony record, opinion/editorial, philosophical system, policy position, simulation output, fictional world, and mixed corpus.

Do not merge pack claims into local truth without preserving source class, provenance, authority, and recommended TrustLens.

## The Third Protocol

The Third Protocol is the procedure by which machines make meaning admissible to one another.

Its core claim: the internet’s first two great protocols moved bytes and documents. The third moves meaning. Meaning moves as infrastructure only when it has shared structure no pairing has to invent.

Main concepts:

- **Boundary discipline**: the protocol governs what happens when meaning crosses from one machine world into another.
- **Admissibility**: meaning is not enough; meaning must be admissible to the receiver.
- **Receiver sovereignty**: a valid message may still be refused.
- **Sidecar path**: a service can adopt HFF/AFP by running a sidecar that speaks protocol on one face and legacy API on the other.
- **Capability exchange**: participants discover supported versions, encodings, lexicons, acts, profiles, endpoints, and trust anchors before exchanging payloads.
- **Selective disclosure**: protocol structure, proof material, content payload, and policy-visible receipt are separable surfaces.
- **Trust Lenses**: receivers inspect claims through declared epistemic filters.
- **Evidence Gate**: mined or crowd-sourced claims must pass source, proof, grounding, contradiction, and admission checks before entering a graph.
- **Preparation/decision boundary**: the protocol can prepare, recommend, record, and coordinate; authority decides.

Important lines:

- Probably understood is not a protocol.
- Meaning is not enough. Meaning must be admissible.
- Context is part of the message.
- Triples describe. Acts bind.
- Middleware translates for one relationship. A sidecar exposes a reusable protocol face.
- The receiver is sovereign.
- A swarm that cannot refuse is a botnet.
- Governance protects interoperability, not permission.
- Versioning pain is irreducible; it is localized or not.
- Protocols carry structure. Judgment remains outside the wire.

## Sidecars

The sidecar is the near-term adoption mechanism. It lets an existing service participate in HFF/AFP without rewriting its internals.

A sidecar:

- maps local identifiers to Core/domain/business lexicons,
- wraps legacy API responses as HFF,
- receives HFF/AFP and translates admitted messages into local API calls,
- enforces receiver policy before action,
- preserves receipts and audit trails,
- allows read-only deployment before write/action deployment.

Middleware translates for one relationship. A sidecar exposes a reusable protocol face.

## Federation, swarms, and the Global Ark

SGF does not require one central brain. Federation lets independently governed systems exchange grounded Synapses, Knowledge Packs, queries, capabilities, and receipts while preserving local sovereignty.

The Third Protocol enables:

- vehicles exchanging emergency broadcasts and lane-opening requests,
- drones forming a Trust Galaxy and dividing tasks,
- warehouse robots admitting or refusing movement instructions,
- software agents negotiating commitments,
- regulated transactions with idempotency, receipts, and authority checks,
- federated knowledge queries across organizations,
- knowledge packs sold, shared, or open-sourced as portable liquid knowledge,
- a Global Ark or computable earth as a long-term possibility.

Do not oversell Global Ark as already built. It is a consequence space and future research/build direction.

## Media, perception, and “What One Image Knows”

SGF can attach media and perceptual grounding material to LexiconEntry records or to source/proof objects. Media bytes do not need to live inside the knowledge graph. SGF specifies the logical reference, hash, provenance, media metadata, and optional embedding/fingerprint links. Physical storage may be SQL BLOB, object store, file system, content-addressed store, archive, package-local file, CDN, or external URI.

LexiconMediaAsset support is optional for SGF Core conformance. If claimed, it should include media type, MIME type, URI/locator or retrieval reference, content hash, license, and source attribution.

PerceptualGroundingProfile support is optional. If claimed, it should identify modality, sensor/model profile, confidence/proof metadata, and emit GapReport or Ghost when grounding thresholds fail.

Media and embeddings are routing aids, not proof of world truth.

## Omega governance language

Omega is the grammar of governance. It exists because prose does not reliably govern machines. A paragraph of policy floating above code cannot halt a machine whose execution substrate has no type for the forbidden condition.

Omega-Code is a typed governance language. It compiles human policy into structural constraints that a system can inspect, audit, and enforce.

The 13 atomic Omega primitive names are:

```text
CONTEXT_RULE
TEMPORAL_RELATION
RESOURCE_BOUND
ENVIRONMENT_INTERFACE_POINT
DATA_TYPE_SCHEMA
STATE_TRANSITION
TRUST_ELEMENT
GOVERNANCE_RULE
SELF_REFERENCE_POINT
MUTATION_RULE
PERCEPTION_MAP
LEARNING_AXIOM
META_DEFINITION_RULE
```

Omega’s core thesis:

- Prose does not hold.
- Governance must be separable from the system it governs.
- A rule embedded only in behavior is not a rule; it is behavior.
- Governance requires a typed specification layer.
- Omega says no through grammar, not vibes.

Omega is complementary to SGF and HFF:

- SGF structures what is meant.
- HFF carries structured meaning.
- AFP declares machine acts.
- Omega governs what may be done.

## Conformance requirements

SGF Core conformance requires implementations to:

1. represent Synapses as one VerbHub plus many role-bound Spokes;
2. enforce the closed 15-role set;
3. preserve Synapse IDs distinct from Canonical IDs;
4. distinguish content_hash from content_fingerprint;
5. preserve source/proof trace for exported objects;
6. support GapReport or equivalent failure reporting;
7. support SynapseGroup or equivalent addressable grouping;
8. preserve identity links without destructive merge by default;
9. preserve time/state/authority/provenance distinctions;
10. export SGF objects through HFF-compatible logical structure when crossing trust boundaries.

GLEAN conformance requires CleanTextBundle input, source span mapping, entity and lexicon mapping before final Synapse assembly, candidate/extraction-decision trace, GapReports instead of fabricated grounding, proof/provenance attachment, and preservation of quoted/reported/denied/hypothetical/command/request/question structures.

HFF conformance requires version and encoding declarations, HFF logical model preservation, lexicon hydration for non-core terms, content hashes, signatures where authenticity matters, replay prevention in live systems, and rejection/quarantine of invalid signatures, expired messages, hash mismatches, and missing required lexicons.

AFP conformance requires distinguishing act type from semantic role, supporting single-act and multi-act envelopes, structured ERROR, authority validation for command/cancel/high-risk acts, and distinguishing ACK from ACCEPT and CONFIRM.

Extensions must use namespaces, declare schema version, declare field meanings with microglosses, avoid redefining core Synapse grammar, avoid adding core semantic roles, and include ExtensionManifest inline or by signed reference.

## What SGF does not claim

SGF does not claim:

- to solve consciousness,
- to capture all human meaning,
- to make machines feel,
- to prove truth from signatures,
- to make hallucination impossible in every component,
- to replace domain expertise,
- to replace legal, clinical, fiduciary, or moral judgment,
- to certify radio protocols, autonomous vehicles, medical devices, or aviation systems by itself,
- to require one database backend,
- to require one embedding model,
- to centralize all knowledge,
- to make every receiver accept every valid message.

SGF claims a bounded operational result: machines can exchange grounded, structured, source-traceable, inspectable meaning sufficient for receiver-side admission, refusal, audit, and action under policy.

## Current publication boundary

Treat the following as publication-ready canon:

- Core Lexicon / Canonical IDs / microgloss / IS_A / LexiconManifest.
- Synapse grammar with VerbHub and 15 role-bound Spokes.
- Frames: ActFrame, PropositionalFrame, NormativeFrame, GeneralizationFrame, PerspectiveFrame, TrustLens, ReasoningContext.
- SourceDocument, SourceSpan, ProofTrace, GapReport.
- GLEAN as CleanTextBundle-to-SGF process.
- HFF wire protocol.
- AFP act/conversation layer.
- Discovery and Capability Manifest.
- Knowledge Packs.
- Receiver sovereignty and admission pipeline.
- Omega-Code and 13 governance primitives.

Treat the following as pipeline/future-work unless the user provides newer canon:

- AI operating system / cognitive kernel.
- Domain-driving code factory.
- Cosmos book / Logos cosmology.
- Full reasoning engine product.
- Query engine product.
- Truth Market as economic mechanism.
- APEX chain as embodied robotics pipeline.
- Hardware accelerator implementation.
- Global Ark as deployed world infrastructure.

These future systems may be discussed as consequences or research directions, but do not treat them as finished SGF v1.0 substrate.

## Style and writing guidance for LLMs

When writing about SGF for James:

- Use serious architect voice.
- Avoid PhD throat-clearing and name-dropping.
- Avoid hype, VC bait, and carnival-barker language.
- Do not use “as we will see,” “in the previous chapter,” “in the next book,” or similar self-referential signposting.
- Do not over-explain to the reader. Trust the reader’s intelligence.
- Make claims boldly but bound them carefully.
- Prefer structural mechanism over metaphor.
- If using a metaphor, cash it out immediately in architecture.
- Avoid old synthetic-draft tells such as “delve,” “unlock,” “seamless,” “transformative,” “landscape,” “crucially,” “notably,” “key takeaway,” and “it is important to note.”
- Body chapters use poet-engineer voice. Appendices use technical architect voice.

## Short version for a model

SGF is a substrate for grounded machine meaning. It represents claims as Synapses: one VerbHub plus role-bound Spokes drawn from a closed 15-role set. Endpoints ground through the Core Lexicon, Canonical IDs, microglosses, IS_A chains, and LexiconManifests. Non-core terms travel only with scoped lexicon material or signed references. GLEAN turns CleanTextBundle inputs into SGF objects with source traces, proof, frames, links, groups, and GapReports. HFF transports SGF objects across trust boundaries. AFP declares what act is being performed with that meaning. Capability manifests let strangers negotiate versions, lexicons, encodings, acts, endpoints, and trust anchors. Receivers remain sovereign: valid messages may still be refused. Omega is the complementary governance language that compiles prose policy into typed constraints. The architecture does not claim total human meaning or consciousness. It claims operational grounding sufficient for admission, refusal, audit, and action under policy.

## Glossary

**ActFrame**: SGF frame for communicative and coordination acts. Carries illocution, payload reference, sender, receiver/scope, authority, proof, time, and conversation metadata.

**AFP**: Act and Federation Protocol. The act/conversation layer over HFF. It declares what a machine is doing with meaning: INFORM, ADVISE, REQUEST, QUERY, COMMAND, PROMISE, PROPOSE, ACCEPT, REFUSE, CANCEL, CONFIRM, ACK, or ERROR.

**AmbiguityCluster**: structure for unresolved identity ambiguity. It prevents a system from silently choosing the top candidate as truth.

**AuthorityFrame**: frame or authority reference used to determine whether an actor is authorized to issue a claim, act, command, rule, or transaction.

**Canonical ID**: structured identifier for a sense-level LexiconEntry. A machine address for meaning.

**Capability Manifest**: discovery document that declares participant identity, supported SGF/HFF/AFP versions, endpoints, encodings, lexicons, knowledge packs, trust anchors, limits, and supported acts.

**CleanTextBundle**: preprocessed, scrubbed, source-mapped input that GLEAN can process. GLEAN does not ingest raw source directly.

**Content fingerprint**: semantic matching/hydration aid derived under a declared profile. It does not prove identity.

**Content hash**: integrity hash proving content bytes or content representation did not change.

**Core Lexicon**: shared sense-level grounding lexicon. Built from large open dictionary material and organized with Canonical IDs, microglosses, IS_A relations, optional HAS_PART/PART_OF relations, source traces, and optional descriptive Synapses.

**Core role set**: the closed set of 15 SGF semantic roles.

**Evidence Gate**: receiver-side or graph-side admission procedure for mined claims, checking source, proof, grounding, contradiction, policy, and trust before admission.

**GapReport**: explicit report that grounding, role assignment, source span, frame classification, reference resolution, confidence threshold, or lexicon bridge failed.

**GeneralizationFrame**: frame marking that a specific claim, rule, example, or episode has been generalized into a broader proposition.

**GLEAN**: process that turns CleanTextBundle input into SGF objects. Court reporter, not mind reader.

**Global Ark**: future consequence space for federated public or shared knowledge infrastructure. Not a finished SGF v1.0 product.

**HFF**: Hub Fact Format / wire protocol. Transports SGF objects across trust boundaries with context, provenance, lexicon manifests, hashes, signatures, profiles, and receipts.

**Illocution**: declared act type or communicative force in AFP or ActFrame.

**Knowledge Pack**: versioned, signed bundle of SGF-compatible knowledge and/or lexicons.

**LexiconEntry**: sense-level lexicon object with canonical ID, lemma, microgloss, part of speech, language/scope, grounding status, source and optional fingerprint.

**LexiconManifest**: manifest carrying or referencing the lexicon entries required to hydrate non-core terms in an HFF message or exported SGF bundle.

**Microgloss**: compact disambiguator distinguishing one sense of a lemma from its lemma-mates.

**NormativeFrame**: frame for behavior-shaping propositions such as duties, permissions, prohibitions, exceptions, constraints, invariants, and Omega rules.

**Omega-Code**: typed governance language for expressing machine-readable constraints, permissions, temporal relations, resource bounds, state transitions, trust elements, mutation rules, perception maps, learning axioms, and meta-definition rules.

**Operational grounding**: grounding sufficient for a receiver to identify references, inspect evidence, determine the act, and decide admission under policy. Distinct from human phenomenological grounding.

**PerspectiveFrame**: frame recording point of view, claimant, witness, author, institution, stance, audience, and legal/domain context.

**ProofTrace**: provenance and derivation record connecting SGF objects to source spans, extractors, runs, validation events, and creation time.

**PropositionalFrame**: frame classifying what kind of proposition is being carried: factual claim, testimony, allegation, denial, opinion, hypothesis, assertion, command payload, question payload, rule, directive, invariant, etc.

**Receiver sovereignty**: principle that a receiver may refuse, quarantine, downgrade, or require more proof for a message even if the message is syntactically valid and correctly signed.

**ReasoningContext**: query/task context specifying TrustLens, domain profile, corpus scope, time horizon, purpose, and output policy.

**Sidecar**: adoption mechanism that wraps a legacy service. It speaks HFF/AFP externally and maps to local APIs internally.

**SourceDocument**: source artifact metadata for where a claim came from.

**SourceSpan**: precise location within a source document that supports a claim or extraction.

**Spoke**: role-bound argument attached to a VerbHub in a Synapse.

**Synapse**: one VerbHub plus many role-bound Spokes, with proof trace. The atomic SGF claim-bearing structure.

**SynapseGroup**: addressable grouping of Synapses into larger thought units such as arguments, timelines, paragraphs, definitions, contradiction groups, event clusters, or narrative arcs.

**SynapseLink**: relationship between Synapses. Not a semantic role.

**The Third Protocol**: HFF + AFP + capability exchange + receiver sovereignty as the protocol layer for machine-to-machine meaning.

**TrustLens**: query/reasoning filter that controls which source classes, epistemic statuses, authority tiers, derivation types, jurisdictions, confidence levels, and contradiction policies apply.

**VerbHub**: center of a Synapse. Carries the action/event/relation canonical ID and verb features.

## SGF 2.0 Horizon: Structural Addressability
SGF 1.0 structures operational meaning. It does not claim to exhaust all human meaning. The future SGF 2.0 research horizon asks how far structural addressability can go. Some meanings resist first-order structure: irony, grief, metaphor, aesthetic force, legal open texture, moral salience, narrative pressure, embodied experience, music, image, and temporal reinterpretation. Their resistance does not prove structure impossible. It proves the first structure was too small. SGF 1.0 already prepares the extension seams: SourceSpan preserves source, ProofTrace records derivation, GapReport names what was not captured, SynapseGroup holds larger units, PerspectiveFrame records standpoint, TrustLens governs interpretation, GeneralizationFrame marks derived meaning, and ExtensionManifest protects the core. The goal is not to flatten human meaning into database rows. The goal is to make more kinds of meaning structurally addressable while keeping source intact, gaps visible, interpretations framed, and authority bounded. Meaning is not protected by remaining unstructured. It is protected by being transformed honestly.


# Ingestion, Identity, and Composition Mechanics

The following mechanical rules govern how SGF handles the messy realities of data ingestion, identity resolution, conflicting evidence, and complex discourse. These are strict architectural boundaries, not mere guidelines.

**1. The Property Trap and Reification**
- **The Trap:** Treating attributes (like birthdate or diagnosis) as static database columns creates the "Property Trap." When an update occurs, the previous value is overwritten, destroying the historical state and its provenance.
- **The Biographer’s Dilemma:** When two valid sources conflict (e.g., Source A says 1770; Source B says 1772), a flat schema forces the system to delete one truth to make room for another. 
- **The Solution:** Reification. The system promotes the attribute into a first-class Synapse node (e.g., an event of "Birth"). Both claims coexist safely as parallel Synapses without schema drift. The system never overwrites evidence to make the filing cabinet look neater.

**2. The Court Reporter Contract & Truth at Query Time (The Volta)**
- **The Rule:** The ingestion layer is a witness, not a judge. It does not improve testimony, complete implications, or resolve truth. It records exactly *what* was said, by *whom*, and with what *source*.
- **The Volta:** The database does not decide what is true before it stores the fact. Truth is resolved at *query time*, not *ingestion time*. The Reasoning Engine applies a Trust Lens (e.g., Recency, Authority, Consensus) to the claim ledger to select the trusted value. The Ark stores the evidence and lets the user choose their lens.

**3. The Centroid Tradeoff (Meaning-Mates)**
- **The Rule:** When ingesting a new term (e.g., "procure"), the system faces a parametric choice: snap it to an existing Canonical ID (e.g., `en.buy`) to prioritize compression, or mint a new ID to preserve the author's exact stylistic choice. 
- **The Impact:** This is not a cosmetic database tuning issue. It is a governed choice that dictates the Big-O traversal complexity of all future queries. The system does not lazily compress synonyms; it evaluates the "codon bias" based on the exact profile contract of the domain.

**4. The Disambiguation Funnel**
- **The Rule:** Identity collisions occur when distinct physical entities share identical semantic descriptions (e.g., a hardcover vs. paperback edition of *The Great Gatsby*). SGF prevents false merges using a three-stage defense-in-depth funnel:
  1. **The Net (Fingerprint / Prefix Match):** Fast, cheap grouping of related concepts to narrow candidates from billions to a handful.
  2. **The Sieve (Discriminator Fields):** Hard ontological metadata (ISBN, SKU, serial number) is checked. If discriminators differ, the collision is resolved immediately.
  3. **The Gavel (Vectors / Hamming Distance):** The expensive, final fallback full-vector check, used only when metadata is ambiguous.
- **The Law:** Vectors propose. Fingerprints cluster. Metadata verifies.

**5. Ghost Nodes**
- **The Rule:** When a source describes an entity that is too vague to generate a unique semantic fingerprint or resolve to an existing ID (e.g., "The tall man left"), the system does not crash, nor does it force a premature identity merge.
- **The Solution:** The system mints a provisional **Ghost node**—a translucent identifier marking the presence of an ambiguous concept. The Ghost persists until additional data or metadata resolves the ambiguity, at which point it is replaced by a concrete fingerprint.

**6. Composition Mechanics (Links and Groups)**
- **The Rule:** Complex thought must never be forced into the 15 hub-and-spoke roles. You cannot invent a sixteenth role for `HAS_RESULT`, `HAS_PURPOSE`, or `CONTRADICTS`.
- **The Solution:** 
  - **SynapseLinks:** The primitive edge connecting two atomic Synapses (e.g., `SUPPORTS`, `CONTRADICTS`, `PRECEDES`, `CAUSES`).
  - **SynapseGroups:** An addressable boundary around multiple Synapses to represent discourse geometry (e.g., an `EPISODE`, `ARGUMENT`, `TIMELINE`, or `PARAGRAPH`).
- **The Law:** Atoms remember. Links and groups let atoms think. Do not put discourse geometry into the semantic role grammar.

**7. The Frame Attachment Rule**
- **The Rule:** The Synapse atom only records *what* was claimed. *How* that claim should be interpreted is handled entirely by attaching a "Frame."
- **The Solution:** To represent a lie, a hypothetical, or a legal constraint, you do not change the Synapse's internal structure. You attach an `EpistemicStatus` (e.g., `REPORTED`, `ASSERTED`, `INFERRED`, `DISPUTED`), a `PerspectiveFrame`, or a `NormativeFrame`.
- **The Law:** Frames classify how a Synapse should be interpreted. They do not redefine the substrate. A factual truth and a hallucinated lie have the exact same Synapse structure; they differ only in their attached Frames and ProofTraces.

