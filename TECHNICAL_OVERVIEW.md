# Symbol Grounding Framework (SGF)

SGF (Symbol Grounding Framework) is an architecture for representing and transporting grounded, source-traceable, frame-aware claims so that machine meaning becomes governable, auditable, and interoperable across systems and trust boundaries.

SGF does not try to capture all human meaning or solve consciousness; it defines the subset of meaning that can be grounded to identifiers, structured into Synapses, traced to sources, carried across trust boundaries, filtered by Trust Lenses, and admitted or refused by a receiver.

SGF treats language as vocabulary plus grammar: the Lexicon and Canonical IDs provide a shared vocabulary of senses, and a hub-and-spoke format called Synapses provide a fixed grammar of events and roles that tie those senses into inspectable structure.

SGF exists because current LLM + RAG stacks can read anything and say anything, but they cannot tell you exactly what they know, where it came from, or why they answered the way they did. SGF turns language into grounded, structured, auditable, transportable, admissible, and governed machine meaning, and it is the substrate an AI operating system like SGF OS stands on.

***

## Author
SGF was originally authored by **James Lee Stäkelum**.

For contact details, see [Contact and community](#contact-and-community) at the end of this document.

## What makes SGF different

### Core substrate / KGs / lexicon

**1. Pragmatic fix for the Semantic Web failure**  
SGF delivers what the Semantic Web aimed for but never achieved at scale: a shared semantic layer where independent systems exchange grounded meaning, not just strings—without a central vocabulary committee or ontology board. The heavy lifting is done by compute and LLM extraction, not human annotators.

**2. Synapses: events as hub‑and‑spoke grammar**  
SGF’s basic unit of meaning is a Synapse: a hub‑and‑spoke event object with a verb at the center and up to 15 fixed semantic roles as spokes (agent, patient, instrument, time, place, goal, etc.). Each spoke points to a Canonical ID in the lexicon, so a Synapse captures “who did what to whom, when, where, why, and how” in one crystalline structure instead of scattering it across many unrelated edges. A simple request like “Please pass the salt” collapses to a Synapse such as `PASS(AGENT:you, PATIENT:salt, GOAL:me)`, and longer documents are smelted into thousands of such Synapses with provenance, frames, and timestamps. In other words, a Synapse is SGF’s event structure: one object that binds a verb‑like predicate, its 15 roles, and stance/provenance into a single packet.

**3. Finite grammar for claims that kills edge explosion**  
Every claim is a Synapse: a verb at the hub with 15 fixed semantic roles as spokes, and each role points to a Canonical ID in the lexicon instead of an ad hoc predicate. This hub‑and‑spoke structure stops the infinite edge explosion that makes traditional knowledge graphs unmanageable. Traditional RDF‑style triples encourage an open‑ended explosion of predicates (`hasAuthor`, `writtenBy`, `creatorOf`, etc.), which then have to be aligned by hand or with brittle heuristics; SGF’s closed role inventory turns that into a simple conformance problem.

**4. Canonical IDs that encode sense, not just labels**  
Canonical IDs are structured addresses (lemma.microgloss.part_of_speech with an optional [.namespace] ending), so lemma-mates such as “bank” the riverbank (`en.bank.water_edge.noun`), “bank” the financial institution (`en.bank.financial_institution.noun`), “bank” saving money (`en.bank.save_money.verb`), and “bank” the aeronautic maneuver (`en.bank.aeronautic_maneuver.verb`) are different machine addresses, not overloaded strings. Sense is explicit, inspectable, and stable across systems.

**5. Mini-lexicons that travel with the message**  
Terms outside the shared core live in scoped mini-lexicons (business, domain, corpus, document), and each term links back into the core lexicon so every sense ultimately grounds the same way. When a system sends a message that uses out-of-core terms, it includes the necessary slice of the relevant mini-lexicon, so the receiver can interpret them immediately. If you can send the message, you can send the vocabulary needed to understand it.

**6. Lexicon as reversible decompression, and as a knowledge graph**  
SGF treats vocabulary as compression: the Core Lexicon is an IS_A/HAS_PART DAG that can “unzip” lemmas and microglosses down toward semantic primes. Concepts are nodes with typed relations, not just word entries, so the lexicon itself is a traversable knowledge graph rather than a static list of definitions.

***

### Interlingua, language, modalities

**7. A machine interlingua built from addresses, not sentences**  
SGF’s “interlingua” is not an ideal middle language; it is a stable address for meaning. Canonical IDs give concepts, entities, events, and actions coordinates in the graph, so `cat`, `gato`, `chat`, a camera binding, and a local code can all resolve—under profiles and evidence—to the same semantic place without forcing everyone into a single human sentence.

**8. Machine-to-machine language interoperability without chasing perfect prose translation**  
SGF breaks language into vocabulary and structure: the Lexicon and Canonical IDs capture senses as a graph, and Synapses/SynapseGroups capture “who did what to whom” in a hub‑and‑spoke format. Different human languages map their phrases into the same substrate, so a Japanese system and a German system can talk about the same concept or event via shared IDs and roles, even if their surface sentences never match. Fluency still belongs to MT/LLM models; SGF’s job is to give machines a shared meaning layer to coordinate on. Multilingual embeddings and content fingerprints act as a compass to find the right sense across languages; Canonical IDs remain the address and the thing that actually travels.

**9. ID-native, multimodal protocol**  
The same protocol and lexicon handle text, sensor data, and perception: cameras and sensors resolve observations to Canonical IDs with confidence and evidence pointers, and other machines use those IDs under their own policies. Meaning travels as grounded IDs and Synapses, not as private labels or raw pixels.

***

### Grounding, ingestion, and safety (RAG pain points)

**10. Operational symbol grounding, not metaphysical hand‑waving**  
SGF treats the classic “symbol grounding problem” as an overclaim and gives machines what they actually need: operational grounding sufficient for coordination, audit, and disagreement, without pretending to solve consciousness or total human meaning.

**11. Knowledge lives in structure, not parametric vibes**  
Corpora are smelted into Synapses, frames, groups, ProofTraces, and Gaps. Facts, testimony, rules, hypotheses, and commands become first‑class structured objects with provenance and uncertainty, not just paragraphs stuffed into a prompt.

**12. GLEAN: court reporter, not mind reader**  
The ingestion pipeline records who said what, where, and under what frame, preserving contradictions and gaps instead of “fixing” them. It creates structured evidence; it does not silently convert messy prose into fake certainty.

**13. Claims ledger, not a fragile “database of facts”**  
SGF does not overwrite history when sources disagree. It stores a ledger of claims: each assertion becomes a Synapse tied to its source, timestamp, and hash. Contradictions are preserved and resolved at query time using Trust Lenses and policy, so systems can reason over disagreement, audit how beliefs changed, and avoid the “last write wins” amnesia that breaks safety and forensics.

**14. Hard separation of artifacts and knowledge**  
SGF splits storage into an Artifact Store (raw documents, hashes, chain-of-custody) and a Knowledge Store (Synapses). Every Synapse must trace back to a verifiable artifact; unanchored facts are structurally invalid. Proof and reasoning are separated so the graph never “forgets” what came from where, even under adversarial conditions.

**15. Coverage Gates and dignified refusal instead of confident nonsense**  
SGF enforces a Coverage Gate on ingestion: if too much of a document’s vocabulary is out of lexicon, the pipeline halts or mints explicit “ghost” placeholders instead of hallucinating structure. The system would rather say “I don’t know” than contaminate the graph, which is exactly what safety‑critical domains (fleets, drones, surgical robots) need.

**16. Frames that stop everything from collapsing into “facts”**  
Every claim carries a frame (act, propositional, normative, perspective, etc.), so testimony, rules, fiction, and commands never collapse into a single truth layer. The system can distinguish “the witness said X” from “X is true” from “X is a rule” from “X is a motivation.”

**17. Time‑aware truth instead of frozen properties**  
SGF separates entities from claims and models temporal axes explicitly, preserving conflicts instead of overwriting them. “Was once alleged,” “was once true,” and “is true now” are distinct objects, avoiding the property trap where databases silently upgrade historical snapshots into eternal facts.

**18. Identity as reversible structure**
SGF treats identity as reversible structure, not a destructive merge. Instead of smashing records into a single golden node, SGF mints SAME_AS and DIFFERENT_FROM edges with confidence, temporal scope, and provenance. This lets the system climb beyond a Level‑1 “archive of isolated facts” into Level‑3 Cathedrals, where facts cluster around entities—without ever destroying the original witnesses.

***

### Transport, federation, and OS-level coordination

**18. Machine‑to‑machine semantic coordination with no prior integration**  
Over HFF and AFP, systems that only share keys and a base lexicon can exchange Synapses and understand each other without bespoke APIs or ontology summits. This is the “third protocol” after TCP/IP (bytes) and HTTP (documents): a protocol for transporting grounded meaning across trust boundaries.

**19. Receiver sovereignty and Evidence Gates by default**  
SGF bakes in receiver‑side Evidence Gates, sidecars, and Knowledge Packs so each system decides what to admit, under which trust lenses, and with what proof requirements. Federation is not “whoever sends JSON wins”; admission is governed, explicit, and auditable.

***

### LLM posture and OS architecture

**20. Vector Confinement: embeddings only route, never decide truth**  
In SGF, vectors are hunting dogs, not judges. Embeddings are used to route and disambiguate, then discarded; all truth, reasoning, and audit live in the symbolic layer with explicit proof and grounding, not in cosine similarity or latent “vibes”.

**21. LLM as small reasoner and mouth, never the brain**  
SGF systems never use the LLM as the knowledge store. The graph is the brain; the LLM is the interface and local reasoning helper. The architecture enforces “never use the model as a database; never use the core to write prose” as a structural rule, not a suggestion.

**22. An AI OS with a small, stable kernel**  
SGF OS (the AI operating system that rides on this substrate) is built with a tight, boring kernel—execution, memory tiers, wire, and rule enforcement—while all behavioral evolution lives in Synapses, Omega rules, plans, and knowledge packs. You change how it thinks by changing governed data and rules, not by constantly mutating the kernel.

**23. An AI OS that behaves like a continuous, Jungian mind**  
Using SGF, temporal memory, Foundry‑style execution, and retrospective learning, SGF OS behaves like a long‑lived mind: it accumulates not just facts but insights, forges cross‑domain generalizations, tracks its own motivations and rules over time, and can explain how those evolved.

***

### Governance and self-governance

**24. Governance as a small, typed language, not vibes**  
Omega provides a compact grammar of governance primitives—constraints, defaults, exceptions, delegations, expiries, and more—so authority, policy, and emergency overrides are explicit, inspectable objects, separate from application code and prompts.

**25. The first machine-checkable implementation of Hohfeld’s eight governance primitives**  
In 1913, Wesley Hohfeld dissected legal reasoning into eight irreducible relations (rights, duties, privileges, no‑rights, powers, liabilities, immunities, disabilities). For more than a century, systems and logics only implemented the “permissions” half. Omega implements all eight as a compact language: it distinguishes what agents may do from what agents may change, and it can express rules about changing rules (immunity, disability, amendment) as first‑class, machine‑checkable objects.

**26. From static policy engines to reflexive self-governance**  
Most policy systems can say “this action is allowed/forbidden,” but they cannot formally express who is allowed to change the rules themselves, under what conditions, and who is immune from that power. Omega’s full set of governance primitives closes that gap, so fleets, drones, factory bots, and agents can evolve their own rules under explicit constitutional constraints instead of relying on ad hoc admin scripts.

**27. From clever reader to self‑auditing institution**  
RAG stacks buy more tokens to read more text. SGF stacks build a judicature: a system that can answer “What did you do, what did you know when you did it, and why did you think that was allowed?” with a finite proof trace instead of a log of prompts.

***

## How this relates to RAG and LLM-centric stacks

Every knowledge system hits the Impossibility Triangle of fluency, scale, and factuality; you can pick two. The dominant architecture of this era—Retrieval-Augmented Generation (RAG)—selects fluency and scale by chunking documents, embedding them into vector space, retrieving text by proximity, and asking a large language model to guess the answer.

SGF inverts the economics and the posture:

- RAG is cheap to ingest (chunk + embed) but expensive and probabilistic at query time (long prompts, latent-space guesses, no structural proof).  
- SGF is expensive to ingest (token-heavy smelting into Synapses) but cheap and deterministic at query time (graph traversal with proof traces and gaps).  
- RAG is ideal for transient, single-document, style-heavy workloads. SGF is designed for durable memory, cross-document causal reasoning, safety-critical decisions, and federation across trust boundaries.

In SGF systems, vectors route; Synapses (event grammar), frames, and Omega decide.

***

## Relationship to RDF and OWL

RDF and OWL gave the web a shared syntax for assertions and a rich ontology language for class reasoning. SGF starts one level lower, at ingestion, and one level more concrete, at events: it treats each clause as a Synapse (a hub‑and‑spoke event structure with a verb‑like predicate at the hub and 15 fixed roles as spokes) and each document as a ledger of grounded claims. A simple one‑clause sentence usually compiles to a single Synapse; a complex sentence with multiple clauses compiles to multiple Synapses. When multiple Synapses form a single unit of thought—a paragraph, a step in an argument, a small proof—they are grouped into SynapseGroups with explicit link types. Larger lines of reasoning are built from groups of groups.

In many real deployments, RDF graphs suffer predicate explosion (`hasAuthor`, `writtenBy`, `creatorOf`, …)—an ever-growing edge vocabulary—and ontology-alignment work that scales quadratically with the number of systems. SGF directly addresses this by using a closed, 15-role grammar for events and a shared Core Lexicon with Canonical IDs (lemma + microgloss + part of speech). Roles are fixed; only the IDs vary. Integration becomes a compliance check against a known grammar instead of a never-ending predicate-mapping exercise.

For many single-system use cases, RDF/OWL are sufficient; SGF becomes compelling when you need event-centric reasoning, reversible identity, and zero-config federation across many independent graphs. RDF/OWL reasoners are open-world by design (missing facts are treated as “unknown”), which is ideal for web-scale discovery but awkward for compliance and safety logic; SGF’s Synapses and reasoners are closed-world by default, matching the way contracts, policies, and safety checks actually behave (“if it is not in the graph, it is not known or allowed”).

RDF/OWL can model events, collections and arguments via custom patterns (event nodes, named graphs, reification), but they do not standardize a canonical event packet or “unit of thought” in the core specs. SGF makes both explicit: Synapses are the atomic events, SynapseGroups are the molecules of thought, and ProofTraces and governed decisions are built from groups-of-groups. That hierarchy is part of the grammar and the wire protocol, not an ad-hoc convention. In SGF, every relationship is a Synapse with full provenance and temporal scope — there is no “cheap” tier of bare edges — so anything that later becomes contested or safety-critical already carries its audit trail.

SGF is not a replacement for RDF/OWL; it is a more opinionated substrate for event‑centric, governed meaning. An SGF graph can be exported into RDF, and OWL ontologies can describe classes and constraints over SGF’s Canonical IDs and roles. SGF’s distinctive contribution is in the Synapse shape, the lexicon‑backed IDs, the identity/rollback machinery, and the explicit hierarchy of groups, not in re‑inventing description logics.

Because SGF attaches embeddings and content fingerprints to Canonical IDs (lemma + microgloss + part of speech) in the Core Lexicon, it can pivot from one surface form to semantically neighboring senses (work, toil, labor; cold, chilly, frigid) with cheap vector lookups and string-level fingerprint checks. RDF/OWL can model equivalence once declared, but they do not standardize a global sense inventory or embedding-native navigation across labels.

This same Canonical-ID layer makes it straightforward to hop across multiple knowledge graphs as if they were one. An SGF deployment can combine a document-derived graph, a world-knowledge graph seeded from Wikipedia, the Lexicon graph itself, an open common-sense graph, and domain-specific graphs (for example, a legal graph for Louisiana law). Because every Synapse is grounded to the Core Lexicon, meanings are already mapped to each other; embeddings and content fingerprints provide the pivot when surface forms differ. Query, reasoning, hypothesis, and argument engines can traverse Synapses across all of these stores using shared Canonical IDs and fingerprints, instead of hand-building pairwise mappings or negotiating separate schemas and label vocabularies for each KG.

***

## Why not just a property graph?

Property‑graph databases (often called labeled property graphs) fix some performance issues of RDF by letting you store properties directly on nodes and edges, but they still treat edge labels as arbitrary strings. The edge explosion problem persists (`SOLD`, `PURCHASED`, `TRANSFERRED`, each with different property sets), and there is no standard set of roles or canonical event packet. SGF is not a graph database; it is a semantic contract you can implement inside any graph or storage engine: 15 fixed roles, Synapse hubs as n‑ary events, Canonical IDs, and governance semantics that stay the same no matter which backend you choose.

## Why not just RAG?

Every knowledge system hits the Impossibility Triangle: fluency, scale, and factuality; you can pick two. The dominant architecture of this era—Retrieval-Augmented Generation (RAG)—picks fluency and scale by chunking documents, embedding them, retrieving text by similarity, and asking an LLM to guess the answer. This is ideal for small corpora, single-document questions, and style-heavy workloads.

SGF inverts the economics and the posture. It pays a high ingestion cost up front—smelting each clause into a Synapse with a fixed 15-role grammar—and then answers questions via cheap, deterministic graph traversals with proof traces and explicit gaps. RAG is cheap to start but expensive per query; SGF is expensive to start but cheap and auditable at query time, and it becomes compelling when you need cross-document causal reasoning, safety-critical decisions, or durable institutional memory.

RAG and GraphRAG keep knowledge in text chunks and use vectors and prompts as the truth mechanism. SGF keeps knowledge in grounded Synapses, frames, and Omega constraints; vectors only route. A RAG stack adds a clever reader on top of a landfill of documents. An SGF stack turns those documents into a self-auditing mind that can prove what it knows, what it did, and why.

## Why not just put everything in the LLM?

End‑to‑end ML stacks treat the model as the library and the judge: facts live in weights, and “truth” is whatever the network emits under a prompt. That gives fluent answers but no durable place where agent, patient, event, proof, and source are pinned down. Retrieval helps, but a retrieved paragraph is still prose; it can report a claim, quote a denial, restate a wrong answer, or ask a question without asserting its premise. A paragraph is not knowledge merely because it is relevant. SGF treats the LLM as a court reporter, not an oracle: models help smelt prose into Synapses, but long‑term knowledge lives in a verifiable graph with contradictions preserved, proof traces, and governance rules that can stop unsafe actions. You can swap models without erasing what the organization knows or how it proved it.

Never use the model as a database.

***

## Repository layout

This repository is organized into three main kinds of artifacts:

- `specs/`  
  Core SGF specification documents: substrate (SGF Core), GLEAN, HFF, AFP, discovery/capability, Knowledge Packs, conformance, examples, and related specs.

- `claims/`  
  Topic-level claim bundles for SGF concepts. Each topic in `claims/index.yaml` has one Markdown bundle capturing:
  - Thesis  
  - Primary, secondary, and technical claims  
  - Claim graph and claim chains  
  - Evidence anchors, boundaries, and reusable prose lines  

- `books/`  
  Manuscript sources for the SGF book series:
  - Prime: *Napkin Pitch*  
  - Volume 1: *The Architecture of Meaning*  
  - Volume 2: *The Third Protocol*  
  - Volume 3: *Omega: The Language of Governance*  
  - Volume 4: *The Grounded Mind*  
  - Volume 5: *The Sovereign Machine*  

Additional supporting materials (brainstorm transcripts, red-team reports, patch notes, and versioning policy) live alongside the core specs and claims to document design rationale and evolution.

***

## Status

Right now this repo is primarily **architecture, specs, and claims**, not a full reference implementation.

Early code (for example, microgloss generation and lexicon bootstrapping scripts) is being developed and will be released under Apache 2.0 as it stabilizes. The intent is for SGF to be implementable in any language or stack; you do not need to wait for an “official” codebase to start building on the architecture.

***

## Claims library structure

The claims library is organized by architectural family:

- Series architecture  
- Grounding and lexicon  
- Synapse grammar  
- Frames and interpretation  
- Evidence and ingestion  
- Identity, storage, and time  
- Transport, acts, and security  
- Admission, federation, and adoption  
- Omega governance  
- Conformance, failure modes, and horizon  

Each bundle lives at:

```text
claims/<family>/<topic-id>.md
```

and follows the v0.3 claim-bundle template defined in `SGF_claim_bundle_template_spec_v0.3.md`.

***

## License and openness

The **SGF architecture** itself – the concepts, protocols, formats, grammars, and operating-system designs described in this repo and in the book series – is dedicated to the public domain. You do not need permission to use it, extend it, or build products on it. No fees, no patent claims, no architectural tollbooth.

Any **reference implementations and sample code** in this repository are released under the Apache 2.0 license. You can use, modify, and ship that code, including in commercial systems, subject to the standard Apache 2.0 terms and patent peace.

The **books and prose** (the specific words, diagrams, and explanations) remain copyrighted in the usual way. You are free to re-express the architecture in your own words, write your own implementations, and build your own products without citing the books or this repo.

For the full statement of intent, including the public-domain dedication of the architecture and the planned governance gauntlet, see `GOVERNANCE_AND_LICENSE.md`.

***

## Style and tone

SGF writing should be clear, direct, and operational. The goal is to transmit meaning that machines and humans can inspect, reconstruct, and argue with, not to sound impressive.

Bad example (banned style):

> “As RenownedThinker once opined, and LaterScholar later echoed, and several other noteworthy experts in the field have since convincingly argued, it can be stated, though not with absolute certainty, nevertheless with some reasonable amount of confidence, that, as a generality, felines have an innate dread of canines.”

Good SGF version:

> “Most cats are afraid of most dogs.”

Guidelines:

- Prefer short, sharp sentences over foggy, overqualified ones. If a claim can be said plainly, say it plainly.  
- Avoid name-dropping and status-signaling jargon; they hide the structure of the idea instead of exposing it.  
- Use concrete payload lines and mechanisms (“what changes in the world, for whom, under what conditions”) rather than abstract flourishes.  

Citations are tools, not decorations:

- Cite sources when it helps a reader verify, reconstruct, or go deeper on a claim.  
- Do not pile up references to make a simple point look weighty.  
- Truth does not become truer because more names are attached to it, and failing to credit the first person who ever noticed a pattern is not treated as theft in this repo; what matters is being honest about what you know and how it can be checked.  

***

## Evidence and proof

SGF cares about whether a claim is true enough, grounded enough, and structured enough to support safe coordination and governance. It does not require academic ceremony.

- Peer review is useful when it adds scrutiny; it is not a prerequisite for ideas to be considered here.  
- Formal proofs are welcome when available, but many useful structures were used for centuries before anyone wrote a proof. What matters is whether something works, can be inspected, and can be challenged.  
- In this repo, the key questions are:  
  - Can a claim be grounded and traced to sources or observations?  
  - Can another person or system reconstruct the reasoning using SGF structures (Synapses, frames, TrustLens, evidence)?  

When in doubt, write as if you are explaining the system to a strong engineer who has no patience for ceremony but cares deeply about correctness and reproducibility.

***

## Contact and community

For questions, collaborations, or implementation discussions:

- Email (project): symbolgrounding@proton.me  
- Email (author): JamesLeeStakelum@proton.me  
- LinkedIn: https://www.linkedin.com/in/james-lee-st%C3%A4kelum-38440122/

If a call is useful, we can move to Microsoft Teams or another conferencing tool after an initial email exchange.