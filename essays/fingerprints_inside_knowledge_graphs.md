# The Scout and the Judge
## Why content fingerprints belong inside knowledge graphs, but only as candidates

Vector similarity is the most powerful candidate-surfacing tool the modern AI toolkit has produced. It is also the most reliable way to silently corrupt a knowledge system if you give it the wrong job.

Two things are true at the same time. Embeddings make magic possible. A system can take "king" in English and "rey" in Spanish and notice they occupy nearly the same coordinate in semantic space. It can take a paraphrase of a sentence and surface the original. It can take a photo and find ten others depicting the same subject. None of this is possible with string equality or with symbolic matching alone. The expressive power is real, and it is what makes modern retrieval feel like a different generation of technology than what came before.

The same expressive power that lets a vector recognize "rey" as similar to "king" also lets it recognize "toil" as similar to "work." And "toil" is not "work." Toil carries hardship in its connotation. Work is neutral. Labor is formal and often economic. These three words share a vector neighborhood precisely because they share a domain. They are close cousins, not identical twins. If a knowledge system uses vector similarity to decide that "toil" and "work" are the same concept, it has destroyed a distinction that no future query can recover. The merge was silent. It will not show up in any error log. It will surface, much later, as confusion about why the system answers questions about labor history with strange undertones of hardship that nobody intended to encode.

This is the discipline most current AI systems are missing. The fix is not exotic. It requires accepting that similarity and identity are different questions that need different substrates, and then building the architecture that enforces the separation.

## The three identifiers

Inside the Symbol Grounding Framework, every concept in the lexicon carries three identifiers, and the spec is explicit that "the three identifiers serve different jobs, and the architecture breaks if they are collapsed." The three are easy to confuse and consequential to separate.

The **canonical_id** is the address. It looks like `en.bank.financial_business.noun.core` or `en.bank.aeronautic_maneuver.noun.core` — a structured string that encodes language, lemma, micro-gloss, part of speech, and namespace. It is stable, human-readable, and the agreed point of reference. Two systems that have both accepted the same canonical_id can interoperate. The canonical_id is the identity answer.

The **content_hash** is the byte-checker. It is a cryptographic digest — SHA-style — that answers exactly one question: did the bytes change? Two different texts produce wildly different hashes, even if they mean nearly the same thing. Two identical byte sequences produce identical hashes, even if the texts came from different sources. The content_hash is the integrity answer.

The **content_fingerprint** is the matchmaker. It is an 86-character Base64URL string produced by a specific pipeline: a multilingual embedding model converts text into a 1024-dimensional vector, that vector gets projected through 516 random hyperplanes to produce 516 bits, and those bits are encoded as the 86-character string. The pipeline is collision-tolerant by design. Two texts that mean nearly the same thing produce nearly identical fingerprints. Two texts that mean very different things produce mostly different fingerprints. The content_fingerprint is the similarity answer.

Three identifiers, three questions, no substitutability. The fingerprint is not a substitute identity, and using it as one breaks the architecture. The hash is not a substitute similarity, and using it as one finds zero matches across any natural-language corpus. The canonical_id is not a substitute fingerprint, and string-equality on canonical_ids fails the first time two systems coin slightly different IDs for the same concept.

This separation is what enables the rest of the architecture. It is also what most systems get wrong, by using one identifier for jobs the other two were built for.

## Similarity is not identity

The reason you cannot substitute the fingerprint for identity is not engineering. It is mathematics. Similarity and identity are different kinds of objects.

Identity is categorical. Two things either are the same thing or they are different things. There is no "60% the same." A claim that asserts identity is a claim that two references point to one underlying thing — that "Bonn" and "Bonn, Germany" name the same city, that "Beethoven" and "Ludwig van Beethoven" name the same composer, that two database rows with different keys belong to the same person. Identity claims are discrete decisions with downstream consequences. Once two things are identified, every future query treats them as one, and that decision is hard to reverse without rewriting the history of every claim that touched either of them.

Similarity is metric. Two things have a degree of similarity that can be measured on a continuous scale. "Toil" is more similar to "work" than to "elephant" but less similar to "work" than to "labor." Similarity is a number. It is useful for ranking, for retrieval, for surfacing candidates. It is structurally unsuited to making categorical decisions because the moment you binarize a similarity score with a threshold, you have introduced an arbitrary cutoff that the data does not support.

The Beethoven test makes this concrete. Imagine a system ingests an entry for "Ludwig van Beethoven" from one source and an entry for "L. v. Beethoven" from another. The fingerprints will be nearly identical because the encoder recognizes the semantic equivalence. A naive system uses the fingerprint match to decide these are the same concept and merges them under a single ID. Now consider what happens when a third source supplies an entry for "Beethoven" the surname, intended to refer to the family rather than the composer. The fingerprint of "Beethoven" is even closer to "Ludwig van Beethoven" than "L. v. Beethoven" was — both contain the full surname. The naive system silently merges the family with the composer. From this point forward, every claim about the Beethoven family applies, by entailment, to Ludwig van Beethoven personally. The damage is structural and undetectable from outside.

The error was not in the embedding model. The embedding model did exactly what it was supposed to do — it placed semantically related strings at nearby coordinates. The error was in using a metric to make a categorical decision. No improvement to the embedding model fixes this. No threshold tuning saves you. The substrate is wrong for the job.

Identity decisions require an authority capable of authoring categorical judgments with provenance, with the ability to be revised, and with explicit grounds. Vectors do not have that capability and cannot acquire it. They are not categorical objects. The architecture has to acknowledge this difference, not engineer around it.

## The scout and the judge

The disciplined version of the architecture is simple to state. Use vectors as scouts. Use symbols as judges. Never confuse the roles.

The scout's job is to surface candidates. When a new entry arrives at the system, the scout asks "do we have anything that looks like this already?" The answer is a list of candidates, not a verdict. The candidates are cheap to produce, fast to compare, and tolerant of fuzziness — exactly what vector similarity is good at. A fingerprint check across a corpus of millions of entries can return its top-K candidates in milliseconds. That is the scout earning its keep.

The judge's job is to adjudicate identity. Looking at the candidates the scout surfaced, the judge decides: same concept (merge), synonymous concept (create a SYNONYM_OF relation), translated concept (create a TRANSLATION_OF relation), related but distinct concept (create some other authored relation), or genuinely new concept (mint a new canonical_id). The judge's decisions are authored, traceable, and contestable. They are expressed in a structured grammar with closed semantic roles, with explicit provenance, with confidence levels, with temporal scope. The judge speaks the language of the symbolic substance layer.

Both roles are necessary. The scout without the judge produces silent merging — the failure mode RAG systems exhibit when they let embedding proximity decide what is true. The judge without the scout produces brittle string-matching that fails the first time two systems coin slightly different identifiers for the same thing — the failure mode traditional knowledge graphs exhibit when they have no way to bridge across naming conventions. Together they produce a system that scales across languages and modalities without losing its primary virtue.

The discipline requires architectural rules, not just convention. In production systems under deployment pressure, convention drifts. The temptation to "just use the fingerprint as the ID this once" or "let the LLM decide what counts as a match" is constant. Conventions break under pressure. Architectural rules do not, because the architecture refuses to compile the violation. The scout layer must be FORBIDDEN from authoring identity claims. The judge layer must be FORBIDDEN from skipping its adjudication step. The rendering layer must be FORBIDDEN from inventing facts. Each prohibition closes a door that would otherwise stay open and eventually get used.

This sounds like overhead at small scale. It is. At small scale you can hold the whole system in your head and catch each substrate violation as it happens. The discipline pays for itself at scale, when the system grows past the point where any single person can audit it. By the time you notice that "toil" and "work" have been silently merged across a graph of millions of entries, the damage is irreversible. Every downstream reasoning step has assumed the merge. The traceability you would need to undo it doesn't exist, because the merge happened in a layer that doesn't record its decisions.

The discipline costs nothing to enforce when the system is new and small. It costs everything to retrofit after the system has grown.

## One protocol, six modalities

The pipeline that produces the content_fingerprint has a property worth naming. Once you accept the scout role as architecturally distinct, the LSH pipeline behind the scout becomes a universal protocol that works across modalities with one back-end and many front-ends.

The math is straightforward. Take any high-dimensional vector. Project it through a fixed set of random hyperplanes. Record which side of each hyperplane the vector falls on. Encode the resulting bits as a compact string. Two similar vectors produce nearly identical strings. Two distant vectors produce mostly different strings. The fingerprint is a small, comparable, fast-to-index summary of the vector's semantic position.

The pipeline is modality-agnostic at every step except the first. The upstream encoder is what changes. For text in any language, use a multilingual embedding model — BGE-M3 or a similar BGE-family encoder that maps languages onto a shared coordinate space. For images, use a CLIP-family encoder or DINOv2. For audio, use CLAP or Wav2Vec2. For video, use V-JEPA encoders or VideoCLIP. For long documents, use BGE-M3 or E5 with appropriate chunking. Every encoder produces a vector. Every vector feeds the same LSH back-end. Every back-end emits the same 86-character Base64URL fingerprint.

The same downstream infrastructure works across all modalities. The same indexes. The same dedup queues. The same candidate-surfacing APIs. The same federation protocols. An image fingerprint and a text fingerprint are not directly comparable — they live in different coordinate spaces because they came from different encoders — but the INFRASTRUCTURE that consumes them is identical. This is the substrate-agnostic property: the scout's mechanism does not depend on what the scout is scouting.

What makes the protocol federation-grade is the Exact Profile Contract. The SGF spec pins down every parameter of the pipeline: the embedding model name, model version, dimensionality, pooling method, normalization scheme, the projection method, the bit depth, and the random seed used to generate the hyperplanes. Two independent implementations that lock the same profile produce comparable fingerprints across machines, organizations, and continents. Two implementations with different profiles produce mutually unintelligible output that happens to share the same format. The contract is the discipline that makes federation possible.

Profile lock-in is real and worth naming. Once a pipeline is in production with millions of fingerprints, changing the embedding model invalidates every existing fingerprint and requires re-indexing the world. The Exact Profile Contract is both the strength (federation works) and the constraint (migration is expensive). The discipline is to lock the profile, version it explicitly, allow side-by-side profiles during transitions, and accept that fingerprint regeneration is an infrequent but real cost of progress. The constraint is real and engineering-manageable.

The technique underneath this — locality-sensitive hashing over learned embeddings — is decades old. SimHash, cross-modal hashing, multilingual entity matching with BERT, MUVERA from Google Research, Shopify's product clustering — many systems use LSH as retrieval optimization or as a candidate generation step inside a larger pipeline. What is rarer is the architectural framing: treating the fingerprint as a universal scout protocol explicitly paired with a federation-grade symbolic substance layer that refuses to let similarity decide identity. The technique is old. The integration discipline is what makes the protocol portable.

## What this lets you do

The scout-and-judge pattern is not specific to SGF. It is portable across any symbolic knowledge architecture that wants to scale gracefully without losing auditability. The pattern transfers cleanly to systems that already exist.

Wikidata has spent fifteen years building a multilingual knowledge graph with manually curated cross-language entity links. The labor cost is enormous; many languages remain undersupplied because no curator has time to bridge them. A fingerprint scout layer over Wikidata's lexical labels would surface candidate cross-language matches automatically, leaving curators to adjudicate rather than to discover. The judge layer is already there — Wikidata's curation discipline is the judge — and the scout would multiply the curators' reach without changing how they decide.

Cyc has a similar opportunity. Sixty thousand concepts authored over forty years, with a constant problem of detecting when a new concept proposed by a knowledge engineer duplicates or overlaps an existing one. A fingerprint scout over Cyc's English glosses would surface candidate overlaps at proposal time, before the duplicate enters the ontology. The Cyc judge layer (the knowledge engineers, their review process) is the adjudicator. The scout would catch duplicates before they ossify.

Any RDF store with a multilingual labeling problem has the same shape. The pattern is portable because it requires only two pieces from the host system: an addressable symbolic identifier per concept, and an authoring process that can decide identity claims. Most serious symbolic systems have both. They just don't have the scout that bridges across origin languages, formats, and naming conventions. The fingerprint pipeline provides exactly that.

The historical problems symbolic knowledge graphs have struggled with — multilingual entity matching, multi-modal content integration, cross-source deduplication — all reduce to the same shape. "We have entries from different origins; are they the same or different?" String matching cannot answer this reliably. Vector similarity can answer the candidate version but cannot decide the identity version. The scout-and-judge pattern solves all three problems with the same infrastructure, because the scout's role is the same regardless of the origin (language, modality, source) and the judge's role is the same regardless of the source.

This is what lets a symbolic knowledge graph stay symbolic — auditable, attributable, reversible — while scaling to global deployment across languages and modalities. Without the scout, the graph cannot discover what it should be merging. Without the judge, the graph silently corrupts itself with merges nobody authored.

## Coda

Disciplined use of similarity is what lets symbolic knowledge graphs scale without losing their primary virtue. The trick is not to add vectors. The trick is to add vectors and refuse them authority. Most systems get one half right.

The Symbol Grounding Framework is one implementation of this discipline, with the three-identifier separation baked into the spec as a primitive. The fingerprint pipeline, the Exact Profile Contract, the synapse grammar with closed semantic roles — these are the SGF expression of a pattern that is broader than any one system. Wikidata could adopt it. Cyc could adopt it. Any symbolic substance layer with a need for federation could adopt it.

The pattern is portable. The discipline is what matters. The brand matters less.

The trick, one more time: add vectors, refuse them authority. The scout surfaces candidates. The judge decides what is true. Neither does the other's job. The system that holds this line scales gracefully. The system that doesn't, corrupts itself silently and never notices until the damage is irreversible.

## Relation to symbol grounding

This essay describes an architectural pattern that emerged from work on the Archimedes Lever intent compiler and the broader Symbol Grounding Framework project. The pattern is offered to the public domain. The technical details (three-identifier separation, 86-character Base64URL fingerprints, 516-hyperplane LSH projection, Exact Profile Contract) are drawn from the SGF Core Specification; the cross-modal extension to images, audio, video, and documents is the natural generalization of the same pipeline with modality-appropriate encoders. The scout-and-judge pattern described here is part of a larger collection of design patterns that orbit the Symbol Grounding Framework (SGF) — an open architecture for machine meaning. SGF resources, including RFC-style technical specifications and free PDF editions of the six-volume book series, are available at the SGF GitHub repository and at symbolgrounding.io.

## Further reading

To explore the Symbol Grounding Framework further:

SGF Book Series
[https://www.amazon.com/dp/B0H3FGSPK6](https://www.amazon.com/dp/B0H3FGSPK6)

GitHub
[https://github.com/SymbolGroundingFramework/SGF-manifest](https://github.com/SymbolGroundingFramework/SGF-manifest)

SGF made simple
[https://symbolgrounding.io](https://symbolgrounding.io)

The GitHub repository includes the SGF overview, RFC-style technical specifications, and free PDF editions of all six books in the SGF series, so the architecture can be read, debated, implemented, and improved without a paywall.
