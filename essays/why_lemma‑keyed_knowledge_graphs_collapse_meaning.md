## Why Lemma‑Keyed Knowledge Graphs Collapse Meaning

### 1. The structural bug in lemma‑keyed graphs

A `lemma` is the base dictionary form of a word—the headword under which its other inflected forms are listed. It is a surface string that compresses multiple senses into a single token. Linguists call this **polysemy**: one token can carry several meanings, sometimes closely related, sometimes completely unrelated. In natural language, this is normal and recoverable from context; the words around a lemma narrow down which sense is intended.

A primary key, by contrast, exists to be a unique identifier. Its job is to point at exactly one thing. A lemma cannot do that job, because polysemy overloads it: the same string is simultaneously standing in for multiple, often unrelated meanings. Treating that overloaded string as a node identifier in a knowledge graph guarantees confusion; the graph will faithfully store the ambiguity as if it were a single concept.

A knowledge graph that uses lemma strings as node identifiers turns this compression into structure. When the primary key for a node is the lemma, every fact about every sense of that lemma is routed to the same object by default. The graph has no way, at the storage layer, to distinguish “this edge belongs to sense 1” from “this edge belongs to sense 3”; both terminate at the same node because both share the same key.

This produces lemma collapse. All senses of a compressed token accumulate on a single node, and the node’s incident edges become a mixture of unrelated or only loosely related facts. Downstream consumers now face a structural ambiguity: any query that targets that node sees a blended history of all senses, even if the consumer is only interested in one of them. The problem is not a missing feature; it is a direct consequence of the key design.

With lemma keys, “entity resolution” never actually resolves. It keeps guessing senses and stuffing those guesses into a key that cannot encode them. Each pipeline or team bakes its own disambiguation heuristics, but there is no single, shared, inspectable address that says “this mention refers to this sense.” The ambiguity lives in the primary key, so every attempt to “clean up” the graph is working against the substrate.

Common workarounds do not change this substrate. Systems append suffixes to lemmas, add `sense_id` attributes, or attach disambiguation flags on edges. These techniques annotate internal distinctions inside the merged node but leave identity keyed by the original lemma. Every new integration, ETL job, or query that does not re‑implement the disambiguation logic repeats the same error. The graph’s behavior remains that of a glorified string lookup: a `name` field backed by attached metadata, rather than a set of distinct, addressable concepts.

From an architectural standpoint, lemma‑keyed graphs are built to conflate senses. Any apparent correctness is the result of discipline and heuristics applied on top, not evidence that the substrate is sound.

### 2. Canonical IDs as sense‑level addresses

Fixing lemma collapse requires changing what the system treats as an identity key. Instead of using the lemma string, SGF introduces `canonical_id`s that encode sense‑level information directly into the address. A `canonical_id` is a structured identifier with fields for lemma, `microgloss`, part_of_speech, language, and optional namespace. Each combination names exactly one sense.

The `microgloss` is the disambiguating cut. It is a compact phrase that separates one sense from its lemma‑mates. Where a lemma compresses many meanings into a single surface form, `microgloss`es such as `financial_institution` or `river_edge` distinguish those senses explicitly. When combined with part_of_speech and language code, this yields addresses like `en.bank.financial_institution.noun` and `en.bank.river_edge.noun`. These are not stylistic variations; they are different coordinates in the system’s space of meaning.

In natural language, polysemy is not a problem because context does the disambiguation. The words around a lemma narrow down which sense is intended; “bank” near “loan” and “interest” is read differently from “bank” near “river” and “flood”. A lemma used as a node key in a knowledge graph does not have that surrounding context attached. The key is just the bare surface string. All facts routed to that node are treated as if they shared one meaning, even when they come from very different contexts. A `canonical_id` repairs this by packing a minimal amount of context into the identifier itself. The combination of lemma, `microgloss`, and part_of_speech encodes which sense the graph is talking about, so the key once again points at one meaning instead of many.

`Canonical_id`s live inside a core lexicon, not in isolation. The core lexicon is an `is_a` / `has_part` graph of sense‑level entries. Each entry knows its parents and, optionally, its parts. This means a `canonical_id` is both a unique address and a node in a structured concept graph. The lexicon can be traversed, validated, and extended; it is not a flat list of strings. When a system encounters an unfamiliar `canonical_id`, it can climb the `is_a` chain to a known ancestor, even if the exact child sense is new.

A bare lemma does not point to a single lexicon entry. At best, it retrieves a bucket of candidate senses: all the rows where that lemma appears as the headword. The system still has to choose one, using context or heuristics. A `canonical_id` is different. It is built so that it resolves to exactly one row in the lexicon. That row carries the specific gloss and relations for the sense being represented. When a `canonical_id` appears in the graph, there is no remaining question about which sense it denotes; the address and the lexicon entry are in one‑to‑one correspondence.

A `canonical_id` is not the meaning itself; it is an address into a structured semantic neighborhood. The address can be wrong or misbound, but once it exists, the receiver has somewhere to stand: it can climb the `is_a` chain, inspect `has_part` structure, look up descriptive Synapses, apply a Trust Lens, and decide whether to admit or reject the claim. Without that address, the receiver is left juggling raw strings, vectors, or local codes with no common coordinate system.

This design does not invent more senses than the system already needs. It exposes the distinctions that were previously implicit in code, comments, or documentation and makes them first‑class objects. The number of `canonical_id`s grows with the number of true senses, not with arbitrary naming conventions. Where a suffix scheme might encode similar distinctions informally, `canonical_id`s enforce them under a stable, parseable format that can be shared across teams and machines.

This also clarifies the proper role of lemmas. They make good labels and search terms for human interfaces, but they are hostile as primary keys. They are optimized for human recall, not for machine identity. The design move is to keep lemmas in the UI and demote them from the storage and API contracts.

Once sense‑level addresses exist, every edge in the graph can target the correct sense rather than a blended lemma node. Facts about one sense attach to its `canonical_id`; facts about another sense attach to a different `canonical_id`. The graph stops treating lemmas as storage keys and starts treating them as labels over structured, addressable concepts. In a lemma‑keyed graph, every consumer that wants to act safely on the data must rebuild context locally: filter by domain, re‑interpret meanings, and re‑apply its own rules for which edges “really” apply. `Canonical_id`s push that context into the substrate once, so consumers can reuse a shared sense resolution instead of re‑implementing it.

`Canonical_id`s are reversible addresses: they can always be unpacked into lemma, `microgloss`, part_of_speech, and lexicon position. A bare lemma key cannot be reversed in this way; it requires re‑running disambiguation to recover which sense was intended. One behaves like an address, the other like a guess.

This is also where `canonical_id`s start to act as a machine interlingua. Different surface forms—different languages, local names, abbreviations, or camera‑derived labels—can all resolve, under declared profiles, to the same `canonical_id`. The protocol does not require everyone to share a human word; it requires them to share, or at least bridge, a stable address for meaning.

### 3. Identity as relations, not merges

Once senses have their own `canonical_id`s, identity becomes a relation over those addresses, not a side effect of node merging. SGF represents identity and near‑identity through explicit, typed edges such as `same_as`, `possibly_same_as`, and `different_from`. Each edge connects two `canonical_id`s and carries provenance, so the system can record who asserted the relationship and under what conditions.

This is structurally different from merging nodes. A merge destroys the ability to represent disagreement or context‑dependent identity. When two senses are merged into one node, there is no remaining place to store “source_a considers these equivalent; source_b does not.” Typed identity edges preserve both alignment and divergence. A `same_as` edge expresses strong identity; a `possibly_same_as` edge captures a tentative mapping; a `different_from` edge records a deliberate separation. Trust policies and `trust_lens` configurations can then decide which identity edges to honor for a given query.

Lemma‑keyed nodes collapse not only multiple senses but also multiple stances. The same node has to carry both “these two uses are equivalent” and “these two uses must be kept distinct”, with no structural place to separate them. `Canonical_id`s plus typed identity edges decouple sense from stance, so disagreement and alignment can both be represented explicitly instead of being averaged away.

Embeddings and content fingerprints sit alongside these structures as routing signals. A `content_fingerprint` is a semantic identifier derived from an embedding of a canonical description, compressed into a fixed‑length bitstring. It behaves like a locality‑sensitive hash: similar descriptions converge to similar fingerprints, so the system can recognize “this looks like the same concept” before doing any deeper work. An embedding can suggest candidate senses whose vectors lie near a given mention; a `content_fingerprint` can point to the specific `source_span` or canonical description that produced the signal. Neither is treated as a truth mechanism for identity. Embedding similarity measures distributional proximity, not legal or operational identity. Fingerprints identify artifacts, not abstract senses. SGF confines both to the candidate generation stage: they help decide which `canonical_id`s to consider, but the final identity decisions live in explicit edges and can be audited.

SGF separates three layers that are often conflated. A `content_hash` is cryptographic; it answers “did these bytes change?”. A `content_fingerprint` is semantic; it answers “does this description likely mean the same thing as that one?”. A `canonical_id` is symbolic; it answers “which exact sense in the lexicon does this system commit to?”. Identity decisions are made over `canonical_id`s, informed by fingerprints and supported by hashes, not the other way around.

Treating identity as relations rather than merges has direct operational consequences. It allows one system to assert `same_as` between its local `canonical_id`s and another system’s, while an auditor can inspect the exact chain of assertions that led to that mapping. It allows a graph to encode that two senses are similar enough for search but must remain distinct for governance. And it avoids the irreversible damage that comes from hard‑merging nodes based on heuristics that may later be revised.

In SGF, identity links live in a `same_as` table rather than in destructive node merges. Each row records which `canonical_id`s are being aligned, which `content_fingerprint` evidence supported the link, and which policy tier approved it. Lemma‑keyed graphs have no such separation: the act of linking and the act of collapsing meaning happen at the same node.

### 4. Why the substrate must change

A knowledge graph keyed by lemma strings is not suffering from incidental bugs; it is mis‑specified at the substrate. The primary key dictates what the system treats as “one thing”. When the primary key is the lemma, the system’s notion of “one thing” is the compressed surface string, not the sense. No amount of downstream heuristics can remove that conflation while the identity key remains unchanged.

Heuristics can decorate the surface. Additional attributes like `sense_id`, flags on edges, embedding‑driven disambiguation, or custom naming conventions can reduce the number of visible errors, but they do not alter the fact that every access path still routes through a lemma‑keyed node. Each new integration or consumer must re‑implement the same compensating logic to avoid inheriting the collisions baked into the core. The result is a network of local patches over a shared ambiguity.

In a lemma‑keyed graph, entity resolution is structurally under‑specified and permanently open‑ended. Pipelines keep inferring senses from context, only to pack those guesses back into a key that cannot express them. Every consumer repeats the exercise in its own way. Switching to `canonical_id`s as the unit of identity is the minimal substrate change that removes this ambiguity. When each sense has its own `canonical_id`, and that `canonical_id` becomes the node key, the graph can represent as many senses as it needs without collapsing them into a single object.

Lemmas then return to their proper role. They become labels and search terms, not keys. Identity decisions become explicit `same_as` / `possibly_same_as` / `different_from` edges, not irreversible merges. Embeddings and fingerprints assist routing but cannot silently overwrite governance. `Canonical_id`s provide reversible, sense‑level addresses; lemma keys remain ambiguous strings.

This change can be introduced incrementally, but it cannot be deferred indefinitely. A graph can first attach `canonical_id`s to existing lemma‑keyed nodes, then progressively migrate queries, APIs, and storage layouts to treat `canonical_id` as the primary key and lemma as an attribute. During this transition, systems can still serve legacy consumers while new consumers adopt the sense‑level substrate. The direction of travel, however, is one‑way: a graph that aspires to governable meaning cannot remain keyed by overloaded words.

### 5. The foundations of symbol grounding

The design choice between lemma keys and `canonical_id`s is not a minor schema tweak. It is a boundary between two kinds of systems. Lemma‑keyed knowledge graphs remain, at their core, glorified string lookup tables: they store labels and rely on downstream context to guess what those labels mean each time they are used. Sense‑level `canonical_id`s, backed by a Core Lexicon and explicit identity relations, turn meaning into a first‑class object that can be addressed, decompressed, audited, and shared.

The concepts described here belong to the broader Symbol Grounding Framework (SGF). Modern large language models act as probabilistic, untethered generation engines; they can read anything and say anything, but they do not define what a word means or how a claim should be stored. SGF provides the formal architecture required to bridge the gap between ambiguous human tokens and deterministic machine execution. The Lexicon supplies vocabulary as compression and decompression. Synapses supply grammar as a fixed role skeleton. `Canonical_id`s join the two and prevent the collapse of meaning that lemma keys encode by default.

Whether compiling software logic, extracting facts from unstructured prose, or governing kinetic systems, SGF forces probabilistic outputs through strict, auditable epistemic gates. A claim does not become part of the substrate just because a model emitted it; it must be grounded to `canonical_id`s, structured into Synapses, and admitted under explicit policies. The goal of the Symbol Grounding Framework is not merely to enable artificial cognition, but to mandate machine governance and safety through absolute structural integrity at the level of meaning.

#### Further reading

To explore the Symbol Grounding Framework further:

- **SGF Book Series**  
  https://www.amazon.com/dp/B0H3FGSPK6  

- **GitHub**  
  https://github.com/SymbolGroundingFramework/SGF-manifest  

- **SGF made simple**  
  https://symbolgrounding.io  

The GitHub repository includes the SGF overview, RFC‑style technical specifications, and free PDF editions of all six books in the SGF series, so the architecture can be read, debated, implemented, and improved without a paywall.

