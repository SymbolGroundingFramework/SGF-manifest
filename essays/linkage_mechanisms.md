# Same address, different bridges: linkage in a federated knowledge architecture

A grounded knowledge architecture has two responsibilities. The
first is to give every meaningful thing a stable address.
The second is to link those addresses to each other in ways
that survive being inspected, audited, and traversed by
machines.

The first problem is mostly solved by a unified address space.
A canonical_id format such as
`iso_lang.lemma.microgloss.pos.namespace` works for word senses
in a lexicon. The same format, with the namespace slot changed,
works for named entities in an encyclopedia, for rules in a
wisdom corpus, for entries in a domain-specific knowledge pack,
and for facts in a private organizational graph. One address
format, many artifacts. That part is the easy part once the
format is chosen and the minting algorithm is published.

The second problem is harder, and it is the part most
architectures get wrong. They assume that because every node
has the same kind of address, linking nodes is also one
operation. It is not. Linking nodes requires a mechanism that
matches the category gap being crossed. Two artifacts of the
same kind link one way. Two artifacts of different kinds link
another way. A concrete artifact and an abstract artifact link
a third way. Each of these is a real bridge mechanism with its
own architectural shape, and a system that uses the wrong
bridge for the wrong gap will silently fail to find what it is
looking for.

This essay describes the linkage mechanisms that the SGF
architecture currently uses, the category gaps each one is
designed to cross, and the discipline that determines which
mechanism applies when. The address space is shared. The
bridges specialize.

---

## The architectural commitment

A unified address space does not imply a single linkage
mechanism. That is the central claim, and it is worth saying
slowly.

Every node in the architecture's knowledge graph carries a
canonical_id in the same five-part format. That commitment is
load-bearing: it is what makes the architecture federated,
inspectable, and reproducible. Two parties running the same
pipeline against the same source corpus mint the same
canonical_ids without coordinating. A knowledge pack from one
organization interoperates with a knowledge pack from another
because their canonical_ids share a format. The address space
is the substrate.

But a shared address space is not, by itself, a complete
theory of how nodes link to each other. A canonical_id is a
unique identifier. It is also, in some cases, a complete
linkage mechanism. In other cases, it is only the handle on
either side of a bridge whose architecture lives elsewhere.

The distinction depends on the category gap being crossed.

Same-category linkage is when both nodes are the same kind of
artifact. Two lexicon entries. Two encyclopedia entries. Two
rules in the same wisdom corpus. Here the canonical_id is both
the address and the link. Federation by re-derivation handles
the case where two parties have different live IDs for the
same sense: each side bursts the other's ID into parts and
re-resolves through its own lexicon's cascade. Same kind of
artifact, same kind of matching, same kind of result. The
canonical_id is doing all the linkage work.

Cross-category linkage is when the two nodes are different
kinds of artifact. A situation described in prose linking to a
wisdom rule. An abstract principle linking to its concrete
instantiations. A named entity linking to its common-vocabulary
parent. A verb-event linking to its participants. Here the
canonical_id is still the handle on each side, but the link
itself cannot be reduced to ID matching. The categories are
different. The vocabularies are different. The shapes of the
nodes are different. A bridge is required.

A bridge, in this architecture, is a named mechanism that
matches across a specific category gap. Each bridge has a
shape. Each bridge has a discipline for when it applies. The
bridges are not interchangeable: using the wrong bridge for
the wrong gap is the predicate-explosion failure mode arriving
in a different costume.

---

## Five named bridges

Five linkage mechanisms cover the category gaps the SGF
architecture currently handles. They are listed below in
rough order of architectural depth: from the simplest case
(same-category identity) to the most structural (event-to-
participant role binding). Each bridge is named, described,
shown with the category gap it crosses, and shown with the
artifact pairs that use it today.

### Bridge 1: Same-type identity linkage

The simplest case. Both nodes are the same kind of artifact in
the same kind of namespace. The link is the canonical_id
itself.

In practice, two flavors exist. The strict flavor is exact
string match: two lexicon entries with byte-identical
canonical_ids are the same node. The federated flavor is
re-derivation: when two parties mint canonical_ids
independently and end up with non-identical live strings for
the same sense, the receiver bursts the sender's ID into its
five parts and runs them through its own lexicon's retrieval
cascade. The output is the receiver's equivalent canonical_id.
Different live strings. Same underlying sense. Linkage
accomplished by re-running the minting algorithm, not by
string equality.

This is the bridge described in detail in the lexicon article.
It is the bridge that gives the address space its federation
property. It works because both sides are the same kind of
artifact and the architecture knows how to re-derive an
artifact of that kind from its constituent parts.

It does not work outside its category. Two artifacts of
different kinds, even if their canonical_ids happen to share a
language tag and a lemma, are not the same node. A lexicon
entry for the common-noun sense of "help" and an encyclopedia
entry for the Beatles song "Help!" are different artifacts in
different namespaces. They link to each other, but they link
through a different bridge.

### Bridge 2: IS_A traversal

When a node in one namespace needs to be grounded in another,
the bridge is the IS_A relation. The Beatles' "Help!" lives at
an encyclopedia ID and carries an IS_A link to the lexicon's
`song.music` entry. The encyclopedia entry for a particular
historical battle carries IS_A links to `battle.military`,
`event.historical`, and possibly several others. A
domain-specific knowledge pack entry for a regulatory clause
carries IS_A links to `clause.legal`, `regulation.administrative`,
and the relevant jurisdictional category. The named entity, the
domain-specific concept, and the historical event are each
grounded in common vocabulary through one or more IS_A links
back to the lexicon.

The bridge is asymmetric. The encyclopedia entry knows it IS_A
something in the lexicon. The lexicon entry does not need to
know which encyclopedia entries point to it. The graph is
walked downstream-to-upstream: from the specific to the
general, from the named to the categorical, from the
domain-specific to the common.

The bridge is also transitive. An encyclopedia entry for a
specific calico cat in a children's book points IS_A to the
lexicon's `calico_cat.domestic_feline.noun.core`, which itself
points IS_A through the lexicon to `mammal`, `animal`, and
eventually to the semantic primes. A machine walking the IS_A
chain from the named entity reaches bedrock without ever
leaving the canonical_id format. Same address space throughout.
Different namespaces along the way. The bridge is what makes
the journey traversable.

The IS_A bridge fails when the source artifact is too abstract
for any specific IS_A target. A wisdom rule like "take
precautions to avoid deterioration" does not IS_A any lexicon
entry. It does not IS_A any encyclopedia entry. It is not a
named entity, not a sense, not a thing. It is an
abstraction-of-pattern, and abstraction-of-pattern needs a
different bridge.

### Bridge 3: Closed-vocabulary bridge

The bridge for matching unbounded natural-language situations
to unbounded natural-language wisdom. Described in detail in
the companion essay on the closed-vocabulary bridge pattern; a
short summary is sufficient here.

The mechanism is a finite named intermediate vocabulary that
both situations and wisdom rules are tagged with. Situations
on one side, wisdom rules on the other side, and between them
a list of perhaps a hundred to a few hundred problem-class
names: `legacy_refactor_judgment`, `cardiac_transition_of_care`,
`negotiation_under_high_switching_cost`. Both sides are tagged
with class IDs from this closed list. Wisdom rules are tagged
at ingestion via embedding-to-nearest-class. Situations are
tagged at runtime via a single LLM classification call against
the closed list. The match is a SQL join through the
intermediate vocabulary.

What this bridge does that the other bridges cannot: it
matches across a category gap where neither side has a stable
identity. A situation is ephemeral. A wisdom rule is abstract.
Neither is a node in a permanent graph. The closed-vocabulary
bridge gives them both a place to attach so they can find each
other.

The bridge is structural, not similarity-based. Two situations
that share a class are connected through that class, even if
their surface vocabularies do not overlap. Two wisdom rules
that share a class are co-retrieved for any situation in that
class, even if their wording has nothing in common. The
matching is doing the work that BM25 and cosine similarity
cannot do, because BM25 and cosine similarity both require
shared vocabulary between source and target.

This bridge is what the wisdom layer of the SGF roadmap
requires. Without it, a wisdom corpus past a few thousand
entries becomes a retrieval problem that defeats the system
that owns it.

### Bridge 4: Instantiation embedding

The bridge for matching abstract artifacts to concrete
queries. Described in the companion closed-vocabulary essay
and worth restating here because it is the bridge most often
missed.

Abstract language describes patterns. Concrete language
describes content. Embedding models are trained on text whose
statistics are dominated by content. An abstract rule like
"take precautions to avoid deterioration" embeds into the
region of vector space that means "I am not about anything
specific," which is exactly the wrong region to live in if
you want to be retrieved by anything specific.

The fix is to embed the application, not the abstraction.
When an abstract rule is ingested, the system generates three
to five concrete instantiations of the rule across diverse
domains. The instantiations become the rule's embedding
payload. The abstract rule remains as the display text. The
vector that anchors the rule in retrieval space is the
embedding of the instantiation block, not the embedding of
the abstract rule itself.

The bridge is between the abstract artifact and its concrete
anchors. The artifact has a canonical_id. The instantiation
block has no canonical_id; it is the embedding payload, an
internal field on the artifact's row. When a concrete situation
arrives, the situation's embedding finds the instantiation
block, and through the block the abstract rule is surfaced.
The rule was found not because anything in the situation
resembled the abstract rule's words, but because the situation
resembled one of the rule's concrete instantiations.

This bridge applies wherever an artifact's natural description
is more abstract than the queries it expects to answer. Wisdom
rules are the canonical case. So are design principles,
common-sense generalizations, ethical norms, and the
meta-cognitive rules described in the 3x5 OS architecture.
Any artifact whose value is its abstraction needs an
instantiation bridge to be retrievable.

### Bridge 5: Semantic role binding

The bridge for linking events to their participants. SGF's
seventeen canonical relations are the bridge: IS_A and
HAS_PART for the ontological dimension, the fifteen semantic
roles (HAS_AGENT, HAS_PATIENT, HAS_THEME, HAS_EXPERIENCER,
HAS_RECIPIENT, HAS_BENEFICIARY, HAS_TIME, HAS_LOCATION,
HAS_SOURCE, HAS_DESTINATION, HAS_MANNER, HAS_INSTRUMENT,
HAS_CAUSE, HAS_REASON, HAS_ATTRIBUTE) for the event dimension.

A synapse is a verb hub with role-bound spokes. The verb is a
lexicon entry: its canonical_id is the address of an event
sense. Each spoke is another canonical_id: the address of
whatever participates in that event in that role. A claim that
"Alice gave Bob a book on Tuesday" is one synapse: the verb
hub is `give`, the spokes are HAS_AGENT pointing at Alice,
HAS_RECIPIENT pointing at Bob, HAS_THEME pointing at the
specific book, HAS_TIME pointing at Tuesday. Every spoke is a
canonical_id. Every relation name is one of the closed
seventeen.

The bridge is structural in a way the other four are not. The
other bridges connect two nodes. The semantic-role bridge
connects an event to N participants through N distinct
relations, each one of which is itself part of a closed
vocabulary. The closure is what prevents predicate explosion:
no matter how many events, how many participants, how many
synapses, the relation vocabulary stays at seventeen.

The bridge fails when someone wants to add a new relation
("HAS_PURPOSE," "HAS_TITLE," "HAS_JOB") to express something
the seventeen do not cover. The discipline is to refuse: the
expressiveness must come from composition of synapses at the
discourse layer, not from extending the relation vocabulary.
That refusal is the architectural commitment that distinguishes
SGF from every ontology project that tried to scale and
collapsed under the weight of its own relation set.

---

## What the five bridges share

All five bridges share three properties. They are worth naming
because they define what a bridge in this architecture is, and
they distinguish bridges from the similarity-based matching
they replace.

**They match through structure, not through similarity.** This
is the load-bearing claim. Same-type identity matches by
shared address. IS_A matches by traversal along a typed edge.
Closed-vocabulary matches by shared tags in a finite list.
Instantiation embedding matches concrete anchors that exist
specifically to be matched. Semantic roles match by binding
participants to a closed relation set. None of the bridges
rely on cosine similarity, BM25 keyword overlap, or any other
unsupervised measure of resemblance between source and target.
Similarity is used inside some bridges as a shortlisting
mechanism (the closed-vocabulary bridge can use embeddings to
preselect candidate classes when the vocabulary is large), but
the load-bearing matching is always structural.

**They are inspectable.** A human reading the architecture can
point at any bridge and ask: which two categories does it
connect? What is its mechanism? What does it look like in
storage? Every bridge has answers to those questions in plain
language. A bridge whose answer is "embedding similarity finds
the right node somehow" is not, in this architecture, a
bridge. It is an unverified hypothesis.

**They are bounded.** The number of bridges is small, and each
bridge has a small named vocabulary at its center: the
canonical_id format for same-type identity, the seventeen
relations for IS_A and semantic roles, the hundred-or-so
problem classes for the closed-vocabulary bridge, the three
to five instantiations per rule for the instantiation bridge.
Boundedness is what makes the architecture survive scale. A
corpus of two million wisdom rules is still tractable because
the bridge in front of it has a hundred handles, not two
million.

These three properties together -- structural, inspectable,
bounded -- are what distinguish a bridge from a guess. The
architecture commits to bridges. It does not commit to
guesses.

---

## The design discipline

When a new artifact type is added to the knowledge stack, the
architectural question is not "how do we extend the
canonical_id format." The format is universal. The question
is, "which existing bridge serves the category gap, or do we
need to identify a new bridge?"

The question has a recipe.

First, name the artifact. An encyclopedia entry. A wisdom
rule. A common-sense proposition. A piece of organizational
documentation. A sensor reading. A medical case record. Each
of these is a category of artifact with its own internal
structure and its own typical retrieval needs.

Second, identify the category gaps the new artifact participates
in. An encyclopedia entry's gaps: same-kind to other
encyclopedia entries (Bridge 1), cross-kind down to the lexicon
(Bridge 2). A wisdom rule's gaps: same-kind to other wisdom
rules (Bridge 1, within the wisdom corpus), abstract-to-concrete
to its instantiations (Bridge 4), unbounded-to-unbounded to
situations (Bridge 3), and possibly down to the lexicon for
abstract concepts that have lexicon entries (Bridge 2). A
sensor reading's gaps: same-kind to other readings (Bridge 1),
participant-binding to whatever event the reading is part of
(Bridge 5).

Third, check whether existing bridges serve each identified
gap. If they do, the new artifact integrates without extending
the architecture: it gets canonical_ids in its own namespace,
it gets tagged with the relevant existing bridge mechanisms,
and it joins the federated knowledge graph at no architectural
cost. This is the case for most new artifacts.

Fourth, only if an existing bridge does not serve a gap, ask
whether a new bridge is required. New bridges are rare and
expensive. They are added only when the category gap cannot be
honestly served by any of the five existing bridges. When a
new bridge is required, the discipline is to design it with
the same three properties: structural, inspectable, bounded.
A new bridge that fails any of the three is not a bridge worth
adding.

This discipline is what keeps the architecture finite under
arbitrary corpus growth. The address space is unbounded. The
artifacts are unbounded. The corpora are unbounded. But the
bridges are bounded, and the bridges are what make the rest
traversable.

---

## Why this matters

The architecture commits to bounded matching machinery in
front of unbounded knowledge. Every other system that grew
into machine-scale knowledge corpora collapsed at exactly this
point. Cyc spent forty years assembling common-sense facts and
then could not retrieve them because the matching engine ran
out of architectural runway. ConceptNet has millions of
entries that almost nobody can query at scale. The Semantic
Web's RDF vocabulary exploded into thousands of predicates
because there was no closure discipline. Every knowledge graph
project of meaningful scale eventually faces the same wall:
the corpus grew faster than the retrieval architecture could
follow.

The bridge taxonomy is the response. The architecture commits
to a finite, named, inspectable set of linkage mechanisms in
front of an unbounded knowledge graph. New knowledge enters
through the bridges. New retrieval queries find their answers
through the bridges. The bridges are the architecture; the
knowledge graph is the data. Growth in the data does not
require growth in the architecture.

This is the same architectural commitment that the SGF Lexicon
makes at the level of word senses (federated canonical_ids,
seventeen closed relations, bounded grammar). It is the same
commitment the closed-vocabulary bridge makes at the level of
wisdom retrieval (hundred-class intermediate, bounded
matching). It is the same commitment SGF makes at the level of
machine-to-machine meaning (HFF, AFP, bounded protocol
vocabulary). The pattern recurs because the underlying
discipline recurs: in a world where the data is unbounded, the
architecture has to do the bounding.

The lever is not the model. The lever is the structure.

---

## Companion essays

This essay assumes familiarity with three related pieces and
sits alongside them in a coordinated set:

- The lexicon article describes Bridge 1 (same-type identity
  via canonical_id and federated re-derivation) and Bridges 2
  and 5 (IS_A and semantic roles via the seventeen closed
  relations) in detail. It establishes the canonical_id format
  and the federation contract that the other bridges rely on.

- The closed-vocabulary bridge essay describes Bridge 3
  (closed-vocabulary bridge for wisdom-to-situation matching)
  and Bridge 4 (instantiation embedding for abstract-to-
  concrete matching) in detail. It also articulates the
  recursion pattern that this essay names architecturally: the
  same shape of move appears at multiple layers of the stack.

- The 3x5 OS essay describes the operating system that uses
  all five bridges together as the linkage layer of a
  cognitive architecture. The 3x5 OS motivation rules corpus
  is the canonical case for Bridges 3 and 4. The 3x5 OS
  belief graph is the canonical case for Bridges 1, 2, and 5.

Each essay stands on its own. The four essays together
describe a coherent architectural commitment: a unified
address space, a closed set of bridges, an unbounded knowledge
graph, and the design discipline that keeps the whole stack
finite under arbitrary growth.

The architecture is not the bridges. The architecture is the
discipline that decides when each bridge applies and when no
existing bridge will do. The bridges are how the discipline
expresses itself in storage and in code.
