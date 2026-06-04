# The Symbol Grounding Framework (SGF)

## What is the SGF?
The Symbol Grounding Framework (SGF) is an architecture for turning language and data into grounded, source‑traceable, frame‑aware claims, so machine meaning becomes something you can govern, audit, and move safely across systems and trust boundaries. Instead of stuffing paragraphs into prompts or vector stores, SGF smelts each clause into a Synapse—a hub‑and‑spoke event packet with a verb at the center and up to 15 fixed roles for agent, patient, time, place, instrument, reason, and so on—backed by a Core Lexicon of sense‑level Canonical IDs, proof traces, and explicit gaps. Over the “Third Protocol” (HFF/AFP) and the Omega governance language, those grounded claims travel between machines as admissible meaning plus typed acts, enabling zero‑prior‑integration coordination, conflict‑aware knowledge graphs, and AI systems that can answer what they did, what they knew when they did it, and why that action was allowed.

## What's in this repository?
*This repository contains the technical specifications and full, free PDF manuscripts for the SGF architecture.

You will find formal RFC-style technical specifications for the SGF in the `./specs`/ folder. 

You can grab all the books in the SGF book series for free in the `./books` folder, or order print copies on [Amazon](https://www.amazon.com/dp/B0H3FGSPK6).

*To understand why this framework was built, begin here, with the preface to **The Architecture of Meaning** (Volume 1 of the SGF Book Series):*

After you finish reading this, the [SGF_IN_A_NUTSHELL.md](https://github.com/SymbolGroundingFramework/SGF-manifest/blob/main/SGF_IN_A_NUTSHELL.md) will give you a quick overview.

And then, the [TECHNICAL_OVERVIEW.md](https://github.com/SymbolGroundingFramework/SGF-manifest/blob/main/TECHNICAL_OVERVIEW.md) will give you a deeper understanding.

And after that, the [SGF_CONTEXT_FOR_SYSTEMS_AND_LLM_ASSISTANTS.md](https://github.com/SymbolGroundingFramework/SGF-manifest/blob/main/SGF_CONTEXT_FOR_SYSTEMS_AND_LLM_ASSISTANTS.md) will give you additional insights.

***
The digital age was built at the mouth of a river whose source it never found.

Downstream, the machinery works. Packets move. Pages render. Databases answer. Models speak. The infrastructure is astonishing. TCP/IP standardized how machines exchange bytes. HTTP standardized how machines exchange documents. SQL standardized how machines ask tables questions. Cloud platforms standardized how machines rent one another's compute.

But the river carrying all of it, the river of meaning, still enters the machine world as mud.

Prose. Labels. Embeddings. Schema names. Predicates. Strings.

The machines move the containers. They do not understand the cargo.

Once the verb becomes the edge, the vocabulary of connections becomes infinite. Every domain invents its own predicates. Every company names the same relation differently. Synonym chaos blooms. Schema wars begin. The semantic layer collapses back into translation work—and so, the layer remained empty.

That absence has a cost. I call it the Babel Tax. Every time two systems need to share knowledge, engineers map schemas, negotiate vocabularies, write adapters, and pray the edge cases do not matter. The work looks like integration. The failure is deeper. The systems are not exchanging meaning. They are exchanging strings and asking humans to keep the meanings aligned.

Then generative AI arrived and made the failure louder.

Large language models are astonishing. They translate, summarize, classify, draft, explain, improvise, and write code. They can produce fluent answers in a tone so confident that the confidence itself becomes part of the illusion.

But the words still float. The model has no inspectable structure underneath the sentence. It can say "the dog bit the man" and "the man bit the dog" with equal fluency, because it has no durable place where agent, patient, event, proof, and source must be pinned down.

I did not begin by trying to solve that problem. I was writing code. The code was supposed to make language models more useful. That was all. No manifesto. No book series. No architecture of meaning. I was building, testing, breaking, revising, and noticing that the same kind of failure kept returning in different clothes.

Some small failures stay with me.

One day, I tried to recall a line from a song: *"When I know more of tactics than a novice in a nunnery."* I asked one of the industry's most advanced language models to identify the source. It confidently attributed the line to Shakespeare’s *Romeo and Juliet*. It was wrong. The words belong to the Major-General song in Gilbert and Sullivan’s *The Pirates of Penzance*.

More recently, I asked that same top-ranked model about the filmography of Gene Wilder. It asserted that Wilder starred in *The Russia House* alongside Sean Connery—a fabrication.

These failures are funny in the way a crack in a bridge is funny. The model did not fail because the questions were difficult; it failed because the answers lacked a grounded structure. There was no durable object called "the claim," no proof trace, and no verifiable source. There was simply no way to separate the statistical probability of the words from the reality they purported to describe.

The industry’s response to hallucinations is retrieval-augmented generation (RAG). The logic is simple: *Feed the model better documents. Keep the facts nearby. Let the model answer from the retrieved text rather than its internal weights.*

That helps. But it does not solve the problem. The model that hallucinated those answers uses web search as RAG whenever its internal knowledge is insufficient. Yet, despite these 'safety' mechanisms, the architecture clearly does not work well enough for anything that actually matters, like medicine or law.

Raw prose carries ambiguity into the retrieval layer. A retrieved paragraph is still just prose. It is laden with pronouns, ellipses, nested quotations, disputed claims, and missing context. It can truthfully report that a defendant said, "I am innocent," without making the defendant innocent. It can state a falsehood merely to illustrate a common misconception.

A paragraph is not knowledge merely because it is relevant. It is just more noise that hasn't been parsed into structure.

That was the first turn upstream.

Raw prose was not enough; the facts have to be structured. RDF triples were the obvious candidate. Subject, predicate, object. Clean. Minimal. Already known. But the structure failed the same test the Semantic Web had failed at scale. Real claims do not always fit into three boxes. Force that into triples and the meaning does not vanish; it leaks into conventions, custom predicates, blank nodes, reification, and application logic. The verb was in the wrong place. It could not be the edge; it had to be the hub.

That is where the Synapse appeared.

The event sits at the center. The participants attach around it through a finite set of roles. The vocabulary remains open because the hub anchors into an underlying lexicon. The grammar remains closed because the spokes do not need to name every possible relation in the world. They only need to answer the recurring questions that meaning asks: who acted, what changed, what moved, who experienced, who received, who benefited, where, when, from where, to where, how, with what, because of what, for what reason, with what attribute.

That structure was not chosen because it was elegant. It survived because alternatives broke.

Too few roles lose meaning. Too many roles recreate the predicate explosion. Every candidate role had to pass through the Gauntlet. Could it be decomposed into existing roles? Was it really a role, or was it a frame, a link, a proof trace, a literal value, or a group relation? Did it carry weight across legal prose, biography, history, instruction, command, causation, transfer, perception, emotion, and motion? If it failed, it was cut.

The set that survived became the 15-role grammar.

That was the second turn upstream.

The Synapse solved the shape of a claim, but it exposed the problem of endpoints. A spoke cannot point to the string "bank" and hope the receiver guesses correctly. A financial bank, the bank of a river, and a banking maneuver in flight are not the same thing. A machine cannot federate meaning through naked strings.

Meaning needed addresses.

That led to Canonical IDs and the Core Lexicon.

One book mattered early: Anna Wierzbicka’s *What Did Jesus Mean?* Wierzbicka is the architect of the Natural Semantic Metalanguage (NSM), a decades-long linguistic project built on the premise that all human languages share a small, irreducible set of universal "semantic primes." These are indivisible concepts—like *do*, *happen*, *good*, and *because*—that act as the basic building blocks of human thought. She was essentially searching for the periodic table of meaning. By deconstructing the dense parables of the *Sermon on the Mount* into strict NSM primes, she proved that the vast explosion of human vocabulary could be compiled down into a highly constrained bedrock of conceptual atoms. Her work did not hand me the architecture I was seekeing, but it made one possibility impossible to ignore: complex meaning can be systematically factored downward toward simpler semantic ground. Wierzbicka showed me the exact direction to dig.

That idea kept working on me. Consider the word *wagon*. A wagon is a platform with wheels and a hitch for pulling, used for carrying things. The word *wagon* is a shortcut—a way to avoid saying all of that every time. Which means vocabulary is a compression algorithm. It lets us communicate complex thoughts compactly by agreeing on labels for bundles of simpler concepts.

And if vocabulary is compression, then we should be able to run the algorithm in reverse! We can decompress! We can take each term in a lexicon and map it to its parent components, and map those components to *their* parent components, and keep going—layer after layer—until we hit bedrock. Wierzbicka's research suggests that bedrock exists: roughly sixty-five semantic primes common to every human language her team has studied. If we could build that map—the full decompression tree from every word down to its primes—we would have compiled a map to meaning itself. We would have found grounding.

For decades, philosophers have argued that machine "symbol grounding" is impossible. While they accept that humans ground meaning through physical senses, they claim we cannot trust a machine’s symbols because a machine is trapped in an infinite regress: a symbol can only be grounded by another symbol, which must be grounded by another, forever.

This is simply the ancient infinite regress fallacy in new clothes. It is identical to the paradox of Achilles and the tortoise: a seemingly flawless logical argument that proves motion is impossible, exposing only a missing account of convergence. If it were true that we cannot trust symbols without infinite proof, mathematics and physics would be useless. Math is symbols. Physics is symbols. Yet we still get on airplanes. Working systems avoid paralysis by defining where their symbols stop.

The academics have confused biological grounding—the phenomenological reality that a hot stove hurts—with operational grounding. A machine does not need to feel pain to safely communicate and coordinate action with another machine. The "impossibility" of machine symbol grounding is a massive overclaim. Meaning does not need biology; it needs an engineered stopping rule.

I began calling the architecture I was building the *Symbol Grounding Framework* (SGF). SGF provides that engineered stopping rule, shattering the infinite regress. We do not have to guess what a word means, and we do not need global committees to debate it. We just run the decompression algorithm until we hit the 65 Natural Semantic Metalanguage (NSM) primes. That is the bedrock. The regress terminates.

But building this decompression map by hand would take a lifetime. I needed an open, massive vocabulary to act as the raw material. I chose Wiktionary—a free, open-source dictionary containing over 1.7 million terms. I wrote code to ingest it, to map the definitions into a massive hierarchy, and to assign a unique, structural address to every single definition.

These addresses are Canonical IDs. A Canonical ID is not a random label. It is a structured address into a lexicon. It identifies a specific sense of a term by appending a microgloss to the root lemma. The microgloss does the work the bare word cannot do. It says which bank, which charge, which discharge, which claim. For example, the root word "bank" is split into `bank.financial_business`, `bank.water_edge`, `bank.save_money`, and `bank.aeronautic_maneuver`.

By assigning these unique Canonical IDs, I realized I could solve the problem of Schema Babel. When someone downloads the open-source Lexicon, they don't have to perfectly align their database schemas with mine. Using cosine similarity search against vector embeddings of the Canonical Descriptions, their system can automatically map their internal terms to my Canonical IDs. The IDs become a universal machine interlingua. 

And if a term doesn't exist in the 1.7-million-word Core Lexicon? The system allows users to mint local "Micro-Lexicons" for domain-specific jargon, linking them back to the Core Lexicon via `IS_A` or `HAS_PART` edges. When these systems need to communicate, they don't have to transmit their entire proprietary dictionary—they only transmit the specific custom Canonical IDs used in that message, along with the links back to the shared public ground. 

That was the third turn upstream.

This architecture—using a hierarchical lexicon grounded in irreducible semantic primes for vocabulary, a crystalline hub-and-spoke structure with the verb at the center and 15 semantic roles for grammar, and Canonical IDs to link them—solves one of the oldest and most stubborn problems in both linguistics and computer science: the interface between syntax and semantics.

This architecture is the operational periodic table for meaning.

Once meaning had an atom and the atom had grounded endpoints, another absence became visible. The architecture demanded a rigorous mechanism to forge this structure out of raw source material. That process became GLEAN.

GLEAN does not begin with raw chaos. It begins after preprocessing has created a CleanTextBundle. Citations, footnotes, tables, exhibits, code blocks, sidebars, and artifacts are mapped rather than casually destroyed. Then GLEAN registers source spans, maps entities, builds discourse context, drafts clause maps, generates claim candidates, makes extraction decisions, assembles Synapses and SynapseGroups, attaches frames and proof, emits gaps where grounding fails, and prepares the result for exchange.

GLEAN is a court reporter, not a mind reader.

That sentence changed the architecture.

A court reporter records what was said, who said it, where it was said, and under what frame. A court reporter does not decide whether the defendant is guilty. A court reporter does not make testimony true by recording it. A court reporter does not silently repair contradictions because the transcript would read more smoothly.

The graph needed the same discipline.

This required breaking what I call the Property Trap. If two valid sources disagree on a birth year, a flat schema forces the system to delete one truth to make room for another. SGF refuses to do this. By treating every attribute as a first-class Synapse event, conflicting claims can coexist safely in the graph, each carrying its own proof trace. The database does not decide what is true before it stores the fact. Truth is resolved at query time, not ingestion time.

A Synapse is not always a fact. My earliest language sometimes called Synapses facts because the first examples were encyclopedic: Beethoven was a composer; Guadalcanal was a campaign; a sonata premiered in a year. But the architecture quickly outgrew that word. A Synapse can carry testimony, allegation, denial, opinion, hypothesis, command, question, request, promise, rule, motivation, constraint, invariant, or governance law.

A Synapse is better understood as a grounded claim-bearing structure.

That insight forced the next layer. Claims need frames.

A command is not an assertion. A question is not an assertion. A rule is not merely a fact. A motivation can guide behavior without binding absolutely. A governance law can bind behavior strongly. A specific rule can be defeated by a stronger rule under emergency conditions. A particular rule can be generalized into a cross-domain insight, but the generalized rule must be marked as derived.

That is why the architecture now contains ActFrame, PropositionalFrame, NormativeFrame, GeneralizationFrame, PerspectiveFrame, TrustLens, and ReasoningContext. These are not ornaments. They are repairs against known failure modes.

The truth that a witness said "the car never slowed down" is not the same as the truth that the car never slowed down. The truth that a jury returned a verdict is not the same as the truth of the world described by the verdict. The rule "put the milk away" remains a good rule even when "leave the burning house" defeats it in context. The generalized lesson "avoid preventable loss when preservation is cheap and safe" is not what the milk rule literally said. It is a derived proposition and must carry its own trace.

That was the fourth turn upstream.

Once meaning could be grounded, framed, and traced, it could travel.

Machines could exchange Synapses.

For decades, machine-to-machine communication required developers to write bespoke APIs, negotiate schemas, and pre-integrate their systems. The Babel Tax was absolute. If a warehouse robot, a medical system, and a logistics platform had never met before, they could not talk.

SGF eliminates that barrier. Because meaning is structured by the Synapse grammar and grounded by Canonical IDs, a machine can send a message containing terms the receiver has never seen. If the sender uses domain-specific jargon, they simply mint a local micro-lexicon entry on the fly. By tying that new concept back to the public Core Lexicon using `IS_A` or `HAS_PART` edges, they provide a map to bedrock. They include that tiny micro-lexicon in the message.

The receiving machine uses those tethers to automatically ground the new concepts. The machines can coordinate with zero prior integration.

I call this *The Third Protocol*. TCP/IP moved bytes. HTTP moved documents. The Third Protocol moves governable meaning.

To make this operational, the architecture introduces HFF (Hub Fact Format) as the wire protocol to carry the payloads and micro-lexicons, and AFP (Act and Federation Protocol) to handle the conversation layer. A machine can INFORM, REQUEST, ADVISE, QUERY, COMMAND, PROMISE, ACCEPT, REFUSE, CONFIRM, ACK, or return ERROR. Those acts do not change the 15-role grammar. They live in ActFrame and AFP. The Synapse remains the payload structure.

That was the fifth turn upstream.

But this is exactly where the architecture becomes dangerous.

A signed message from one machine to another can move vehicles, reroute drones, trigger workflows, deny access, approve shipments, or coordinate systems that have never met before. HFF must therefore carry hashes, signatures, keys, trust anchors, timestamps, expiry windows, nonces, replay protection, schema versions, and lexicon releases.

But authentication only proves what was sent and who signed it. It does not prove that the receiver should act. A system that can receive zero-integration commands from the outside world must have an absolute right to refuse them. Authority, safety policy, and governance still have to decide.

That led to what I call *Omega*.

Machines need rules. Some rules are defaults. Some are constraints. Some are non-negotiable. Some apply only under exceptions. Some expire. Some can be delegated. A language model cannot be trusted to improvise those boundaries out of statistical vibes. Governance needs a grammar.

Omega is that grammar. It is not the subject of this volume, but its necessity appears as soon as meaning becomes portable and machines can act on it.

The same is true of the AI operating system. A system that stores grounded knowledge, exchanges it, reasons over it, learns from it, and acts under rules needs more than a model and tools. It needs memory, provenance, motivations, constraints, governance, and a stable substrate. That work belongs to another volume. This book lays the ground it needs.

Looking back, the sequence feels more orderly than it was.

I did not know the Synapse was waiting when I was chasing hallucinations. I did not know the Core Lexicon was waiting when I was thinking about roles. I did not know HFF was waiting when I was thinking about Synapses. I did not know Omega was waiting when I was thinking about HFF. I did not know the AI operating system was waiting when I was thinking about Omega.

Each layer exposed the absence of the next.

That is why the code had to wait. Code is one implementation. Architecture is the thing the implementation serves. If the architecture is right, it can be written in Python, Rust, C++, SQL, a graph database, a relational database, a file-backed engine, or something not yet built. If the architecture is wrong, no implementation saves it.

The work felt like following the Nile upstream. For centuries the river was known by its force before its source was known. The delta, the floodplains, the cities, the trade routes, the civilizations watered by it, all of that was visible downstream. But the question remained: where does this begin? Explorers followed the river through maps, reports, swamps, kingdoms, errors, and false sources until Lake Victoria finally came into view.

Symbol grounding felt like that.

The visible river was everywhere: language, databases, schemas, knowledge graphs, search engines, legal documents, medical records, contracts, code, songs, sensor streams, and machine commands. The downstream machinery used meaning constantly, but the source was missing. I followed the current backward through hallucination, retrieval, triples, roles, lexicons, proof traces, protocols, governance, and rules. At each bend, the river exposed the next absence.

The explorers searching for the source of the Nile found Lake Victoria. I did not find a lake. I found a shape. A shape with the verb at the center. Roles around it. Meaning grounded in a lexicon. Claims tied to sources. Gaps preserved instead of hidden. Rules framed by authority. Machines able to exchange not only bytes or documents, but meaning.

This book is the test. It does not claim to contain the final truth of the universe. It claims something smaller and more demanding: that a finite grammar of grounded, claim-bearing structures can become the missing semantic substrate for machines. It defines the Synapse, the lexicon, the proof traces, the frames, the limits, and the wire.

The map is not the river. But a good map changes what can be built along its banks.
