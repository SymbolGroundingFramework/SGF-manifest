# A Grounded Substrate of Meaning for AI Systems

**By James Lee Stakelum**

The SGF Lexicon is an identifier-minting service for word meanings.
Given a lemma and a sentence of context, it returns a globally-
unique, human-readable, fully-disambiguated canonical ID for the
sense the writer intended. The ID is stable across runs, across
machines, and across time. Two organizations that run the pipeline
on the same Wiktionary dump mint identical IDs without sharing a
database, without calling an API, and without agreeing through a
central authority. The shared identifier space exists because the
pipeline exists, not because anyone owns it.

That is the load-bearing claim. The rest of what this article
describes -- the embedder cascade, the cross-encoder reranker, the
BM25 lexical layer, the optional LLM tiebreaker, the four named
retrieval policies, the closed seventeen-relation graph, the
audit-driven improvement loop -- is the machinery that makes those
identifiers reliable enough to build on.

Clone the repository. The bundled 72,000-sense development lexicon
is live within an hour on a normal laptop. Point the same pipeline
at a full Wiktionary dump and it builds out to roughly 1.7 million
senses on the same hardware over an overnight or multi-day run.
Same code, same architecture, same audit gate. Apache 2.0. No
attribution required. No API key. No cloud account.

WordNet exists. ConceptNet exists. Wiktionary exists. Every LLM
exists. None of them gives you what this gives you: a stable,
human-readable, machine-comparable identifier for every sense of
every word, derivable on any machine from open code and an open
dump. Most projects ship one piece of that. This ships all of it.
The rest of this article is the receipts.

---

## Why this exists

A lexicon is the floor a language-processing system stands on. If
the floor is missing, every layer above it improvises. LLMs
improvise so fluently that the improvisation is invisible. Until
you need reproducibility. Until you need to ground a token in
source text to a specific sense. Until you need to audit why the
system chose one interpretation over another. Until you need
behavior that is stable across runs and across model generations.
Then the missing floor shows up.

Modern AI systems have huge models and tiny substrates. The
substrate is where reproducibility lives. It is what an LLM looks
up against when fluency alone is not enough.

The SGF Lexicon is one of those substrates. Three properties
define it: it is machine-searchable by embeddings, it assigns a
globally-unique canonical identifier to every sense, and it
functions as a load-bearing component in a larger compilation
pipeline. A fourth property is a key contributor to the first
three: an optional LLM-driven improvement pass that sharpens the
lexicon's own microglosses and metadata.

## Why a lexicon, not just an LLM?

A reasonable engineer reading this far asks: if I want to know
what a word means, why not just ask GPT-4, Claude, Gemini, or
DeepSeek? Why do I need a lexicon database at all?

Because the lexicon is not a definitions lookup service. The
lexicon's job is to mint stable, globally-unique, human-readable
identifiers for the senses of words. An LLM cannot do that, no
matter how capable.

Consider what the lexicon returns for a query about "the river
bank":

```
en.bank.dry_sides_river.noun.core
```

That string has three properties no LLM call provides:

**It is identical across runs, machines, and time.** Two different
machines querying two different copies of the lexicon return the
same identifier. So do two queries to the same machine a year
apart. So would the same query run against a re-embedded lexicon
next year. Now ask GPT-4 and Claude to describe the river-edge
sense of `bank`. You get two semantically-similar but textually-
different descriptions. Run the same prompt next month. Different
again. None of those are usable as keys in a database, foreign
keys in a knowledge graph, or addressable targets in a federated
system. Only the canonical ID is.

**It is human-readable AND machine-comparable.** A reader can look
at `en.bank.dry_sides_river.noun.core` and know which sense it
points at without consulting any database. The microgloss is baked
into the identifier. At the same time, the identifier is a simple
string that any system can compare for equality, store as a key,
transmit over a network, or persist in a file. It combines the
legibility of a description with the discipline of an identifier.
WordNet has stable IDs (synset numbers) but they are opaque
integers locked to one specific resource. Wikidata has stable IDs
(Q-numbers) but they are centrally administered and require
constant API calls to resolve. The canonical ID is legible without
lookup and stable without central authority.

**It enables federation without shared infrastructure.** This is
the property most people miss, and it is the one that matters
most. Two machines that both run the SGF Lexicon pipeline can
communicate about word senses without sharing a database. Machine
A reads a document, identifies "the bank flooded," sends Machine
B the canonical ID `en.bank.dry_sides_river.noun.core`. Machine B
receives the ID and immediately knows which sense is meant,
because the ID is self-disambiguating. Neither machine needs to
call an API, sync a database, or trust a central registry. Each
machine, given the same Wiktionary dump and the same pipeline,
independently mints the same identifier. The shared identifier
space exists because the algorithm exists, not because anyone owns
it. No W3C ontology working group has to convene. No vendor has to
host the canonical registry. No standards body has to ratify the
schema. The pipeline IS the standard.

This is what knowledge graphs have always needed and almost never
had. Structured knowledge is impossible to do correctly without
identifiers that disambiguate. Cross-system federation is
impossible unless two machines can either share identifiers or
derive them by the same algorithm. The SGF Lexicon's canonical
IDs are derivable from open source code running on a freely-
available dump. Any organization can independently mint the same
IDs. Two organizations that have never talked to each other can
build systems that interoperate at the sense level on day one.

Asking an LLM "what does `bank` mean in this sentence?" gets you
a description. The description is correct, varies a bit each
call, depends on the model version, costs an API call, and is
unusable as a key. Asking the lexicon the same question gets you
a key. The key is the thing your downstream systems actually need
to do anything serious: store the sense in a knowledge graph,
federate it across machines, audit it across runs, compare results
across model generations, or build any system whose correctness
depends on stable identity.

The LLM is in the cascade for a different reason: it picks the
right sense when the cheap retrieval stages cannot decide. The
lexicon assigns the identifier. The LLM helps choose which
identifier applies. Different jobs, both necessary, neither
replaceable by the other.

## The stopping-rule problem

The symbol grounding problem has been declared unsolvable for thirty
five years. The classical argument is short. A symbol gets its
meaning from another symbol. That symbol needs grounding from
another. The chain continues forever. Taken literally, the regress
rules out the possibility that any finite symbolic system can ever
be truly grounded.

Taken literally, the same argument rules out mathematics. Every
proof rests on prior proofs. Every axiom is a symbol. Every
definition uses other defined terms. By the regress reading,
mathematics cannot work. And yet people board airplanes, sign
contracts, take medicine, and run compilers. Working systems do
not wait for infinite proof. They define stopping rules: places
where the recursion is allowed to end for operational purposes,
backed by evidence, governed by procedure, and inspectable on
demand.

The missing piece in most AI systems today is exactly that
stopping rule. When an LLM produces the token "bank," there is
no operational stop. The token points to a vector. The vector
points to a region of space. The region is shared with every
other sense of bank, every related concept, every loose
association the model picked up in training. There is no
inspectable address. There is no place the regress is allowed
to end.

The SGF Lexicon is one engineered answer to that gap. A canonical
ID is a finite, structured, human-readable address. It identifies
a specific sense, not a lemma. It is derivable, not assigned by
fiat. Two parties running the same pipeline against the same
source produce the same address. The address is the stop.

This is not a claim that the philosophical problem is solved.
It is not. Phenomenal experience, embodied meaning, the felt
sense of what red looks like or what loss feels like: none of
that is in the lexicon and none of that is what the lexicon is
for. What the lexicon provides is the operational version of
the problem, narrower and tractable. Machines coordinating with
machines do not need to share phenomenal experience. They need
to share addresses they can both resolve. The stop is not
metaphysical certainty. The stop is an inspectable, derivable,
federation-capable address that both parties can independently
recover.

The rest of this article is what that stop looks like in code:
how the address is structured, how it gets minted, how it stays
stable, and how two parties who have never coordinated end up at
the same address for the same sense.

## What is new here

Lexical resources exist. WordNet exists. ConceptNet exists.
Wiktionary exists. Each is valuable for what it does. The
combination this lexicon ships in one package is: machine-
searchable by embedding cosine, register-aware (slang, vulgar,
poetic, dated, archaic, specialist), grouped by content-identity
so that synonyms reroute the right way, filterable by a
configurable policy, addressed by stable canonical identifiers,
and auditable against a falsifiable self-retrieval gate. The
specific combination, packaged as one open pipeline, is what
this lexicon contributes.

The combination matters more than any single property. A
register-aware lexicon without canonical IDs cannot be referenced
durably. A canonical-ID lexicon without an audit gate cannot prove
it is queryable. An audited lexicon without policy filtering returns
slurs alongside their neutral synonyms. A policy-filtered lexicon
without content-identical grouping cannot reroute "kiddo" to
"children." Each property reinforces the others. Removing any one
of them collapses the substrate.

## Built for scale, packaged for GitHub

This is a pipeline, not a precomputed artifact. The repository ships
with a 72,000-sense development build sourced from Simple English
Wiktionary. That fixture is small enough to clone, run, and iterate
on in minutes on a normal laptop. It is sized to fit in a GitHub
repository.

The full English Wiktionary contains roughly 1.7 million senses.
Anyone can run the same pipeline against the full dump and produce
the full lexicon. The architecture is designed to scale to that size
on commodity hardware: the embedder cascade gates by coverage so a
partial embedder never silently corrupts results; the improvement
loop is idempotent and incremental so an interrupted run resumes
without redoing finished work; the cross-encoder reranker is
stateless so it never bottlenecks on dataset size. None of these
are design choices that work at 72,000 and break at 1.7 million.
They are choices that work at 1.7 million and remain inexpensive at
72,000.

This also means the lexicon is reproducible in the strict sense.
Clone the repository, point the pipeline at a specific Wiktionary
dump date, and any researcher anywhere builds bit-for-bit the same
lexicon. The factory is the artifact; the lexicon produced by any
single run is the output of one configuration of that factory.

## What a grounded substrate looks like

The lexicon is a SQLite database. Every row is a sense: one
specific meaning of one word. A polyseme like "bank" produces
multiple rows: the river-edge sense, the financial-institution
sense, the verb sense of tilting an aircraft.

Each row carries a stable identifier, structured metadata, and one
or more embedding vectors. The lexicon ships with a search server
that loads those embeddings into RAM once at boot and answers
queries in tens of milliseconds.

That is the shape of the substrate. The properties on top of it
are what follows.

## Machine-searchable by embeddings

A modern AI system that wants to ground a token in prose to a
lexicon sense does the obvious thing: it embeds the surrounding
context and searches for the nearest sense by cosine similarity.
This works because the lexicon precomputes an embedding for every
sense.

The lexicon supports three embedders out of the box: a small
diagnostic English embedder (bge-small, 384 dimensions), a large
production English embedder (bge-large, 1024 dimensions), and a
cross-language embedder (bge-m3) for multilingual builds. You can
populate one, two, or all three.

The search server introspects which embedders are populated and
runs a coverage-gated cascade. If you populated bge-large on the
full lexicon, the server uses it. If you populated it on only
3.5% of senses, the server detects that as partial coverage,
excludes it from automatic selection, and falls back to whichever
embedder has complete coverage. A half-built embedder never
silently corrupts query results.

Two precision layers sit above the bi-encoder cosine search. A
cross-encoder reranker rescores the top candidates when the
top-1/top-2 margin is tight. An LLM tiebreaker, opt-in, handles the
remaining hard cases by sending the top candidates to a configured
LLM and asking it to pick one. Each layer fires only when the prior
layer leaves a tight margin. The cheap path stays cheap when it is
confident.

The lexicon also ships a falsifiable self-retrieval audit. The
audit is two tests, not one. Test 1 asks "given my embedding, can
I find myself in the top-1 position among senses sharing my
lemma?" That validates monolingual disambiguation. Test 2 asks
"given my embedding without a lemma filter, are my top-K nearest
neighbors all members of my synonym cluster, or do unrelated
senses appear in the top?" That validates that the embedding is
semantically anchored well enough for cross-language federation,
where the lemma filter is not available. Both tests are
automatable and run in under a minute on a 72,000-sense build.
Grounding without an audit is just hope; with an audit that
covers both monolingual disambiguation and cross-lingual
anchoring, the lexicon can show its own queryability as a number.

## How a microgloss gets minted: one sense, end to end

The verbal description above can stay abstract. A worked example
makes the mechanism concrete.

Take the verb sense of `bank` that means "tilt an aircraft into
a turn." The lexicon needs a microgloss for it. Eight candidate
strategies generate eight candidate strings, in parallel, from
the sense's gloss, examples, synonyms, antonyms, and the cluster
of its lemma-mates. Sample candidates: `tilt_aircraft_into_turn`,
`bank_in_flight`, `roll_aircraft_axis`, `incline_wings_turn`,
`maneuver_lateral_axis`, plus three fallbacks generated from the
definition skeleton.

Each candidate is then scored under three reference embedders
in parallel: `bge-m3-v1` (multilingual, the federation reference),
`bge-large-en-v1` (high-quality English), and `bge-small-en-v1`
(lightweight diagnostic). Under each embedder, four tests run
against the candidate. The first test is self-retrieval: when
the lexicon is queried for the candidate string, does the target
sense come back at top-1? The second test is sibling
disambiguation: when the lexicon retrieves matches, does the
target sense beat the other senses sharing the same lemma -- the
financial-institution `bank`, the riverbank `bank`, the storage
`bank`? The third test is example-sentence retrieval: when the
lexicon is queried with the sense's own original example
sentences, does the target sense still come back at top-1? The
fourth test is cluster-centroid anchoring: when the candidate is
embedded under the multilingual reference, does it land near the
centroid of the close-cousin cluster? That last test is what
establishes the microgloss is anchored well enough for
cross-language federation. The four tests are named T1, T2, T3,
and T4 in the code and the spec for short reference.

Each embedder produces a verdict: passed or failed, plus a margin.
The candidate's combined score is the weighted sum of the three
per-embedder scores -- 0.50 for the multilingual reference, 0.30
for English-large, 0.20 for English-small -- plus an agreement
bonus: +0.15 if all three embedders pass it, +0.05 if two of
three do, -0.10 if only one does, -0.20 if none do. A candidate is
admissible only when at least two of the three embedders pass it
AND when T4 passes under the multilingual reference. Among the
admissible candidates, the one with the highest combined score is
the winner. It becomes the sense's microgloss. The canonical ID
for the sense locks in. The pipeline moves on.

The reason this matters: an earlier version of the pipeline
minted microglosses deterministically, taking the first candidate
that passed a single embedder's audit. That version produced
minted microglosses like `participle_past_tense` and `feeling_hot`
because the first candidate that survived locally was not always
the candidate that would survive across embedders or across
languages. The tournament corrects for that by making the
federation contract the gate, not a post-hoc audit. A microgloss
that does not survive under three embedders is not a microgloss
that will federate. The mint refuses to ship it.

The small set of senses for which no candidate passes the
admissibility gate are left at provisional tier with a stub
microgloss and queued for the LLM improver, which is the next
section. Roughly one half of one percent of senses fall into this
bucket on the Simple English development build (about 72,000
senses). The residue rate on a full English build has not yet
been measured. The point is that the residue is known and
counted rather than absorbed into an unmeasured shrug.

## LLM-driven gloss improvement

Dictionary glosses are weak embedding inputs. They were written for
human readers, often in a single sentence stripped of context, and
they rarely disambiguate well against close cousins. The embedding
of a Wiktionary gloss for `bank (river edge)` is decent but not
sharp. The embedding of a gloss for `cancer` is too close to the
embeddings of `leukemia` and `tumor` to be useful for fine-grained
disambiguation.

The lexicon's improvement pass addresses this. For each sense in a
frequency-prioritized frontier, the pipeline shows an LLM the
sense's lemma-mates (other senses sharing the same word), its
embedding cousins (other senses crowded around it in embedding
space), and any prior self-retrieval failures the audit recorded.
The LLM rewrites the microgloss so it disambiguates against those
specific competitors, and fills four metadata axes (register,
temporal status, social status, specificity) under a controlled
vocabulary. The new microgloss gets re-embedded with the production
embedder. The sense gets re-audited.

The LLM call goes through a small adapter that the operator wires
up once. Any LLM works: OpenAI, DeepSeek, a local model, an
in-house endpoint. The prompts use a two-layer envelope contract
where the LLM puts its answer between `<answer>...</answer>` tags
and any reasoning between `<comments>...</comments>` tags. Parsing
is deterministic; no regex acrobatics.

The pass is incremental and idempotent. Improve the top 100 lemmas
today; come back next week and improve the top 5,000; come back
later and target only the senses that still fail the audit. Each
run extends the prior work rather than redoing it. The lexicon
gets sharper over time without ever requiring a from-scratch
rebuild.

The syntax is a single command:

```
python improve_lexicon.py --target sgf_lexicon.db \
    --llm-wrapper llm_wrapper.py --top-lemmas 1000
```

The same adapter (`llm_wrapper.py`) is the LLM entry point for all
LLM-using stages: microgloss improvement, semantic-relation
harvesting, and the optional search-time tiebreaker. You wire it
up once. Every LLM call in the pipeline goes through the same
file.

The provisional generator that produces microglosses before the
LLM improver runs is being extended to iterate over a fixed
sequence of candidate strategies and self-audit each candidate
against the two retrieval tests, accepting the first short
candidate that passes a robust threshold and falling back to a
scored tournament across longer candidates when the short ones
do not pass cleanly. Same input plus same code produces the same
microgloss on any machine, so canonical IDs minted by the
provisional generator alone are deterministic across machines
and across time. The LLM improver becomes targeted refinement on
the small minority of senses where the deterministic generator
cannot produce a robust microgloss from the available source
data, rather than restoration of thin defaults across the whole
lexicon.

## Policy-driven retrieval

The search server does not just return raw similarity matches. It
applies a configurable policy that filters and reshapes results
before the client sees them. Four named policies ship out of the
box:

- **`snap_to_standard`** (default). Rewrites slang and dated terms
  to their content-identical standard form. A query that matches
  `kiddo` returns `children`. A query that matches `pops` returns
  `father`. Specialist terms are preserved: `leukemia` stays
  `leukemia`, not `cancer`. Slurs and offensive vocabulary are
  excluded.

- **`snap_to_neutral`**. Same idea, but instead of dropping slurs
  and offensive terms, it substitutes them with their content-
  identical neutral equivalent. A query hitting a slur returns the
  group's neutral standard form. If no neutral substitute exists
  in the lexicon for a marked sense, a configurable failure mode
  decides what to do: drop, return the original unchanged, or
  return a placeholder tagged `excluded_by_policy`. This is the
  policy for general-audience search interfaces that prefer a
  graceful answer over a refusal.

- **`preserve_register`**. Matches the source's metadata profile.
  Useful when compiling slang-heavy first-person prose: `kiddo`
  stays `kiddo`, not `children`. Specialist preservation still
  applies. Slurs still excluded.

- **`research_unfiltered`**. All senses, all tiers, no rewrites,
  no exclusions. For lexicon authors inspecting the raw record.

Policies are overridable per query, both at the named-policy level
and at the individual-knob level. A caller can switch policies
(`--policy preserve_register`), re-include filtered content
(`--include-social offensive`), or override the maturity-tier floor
(`--min-tier embedded_v1`). The retrieval brain lives in the
server; the client just asks for what it wants.

## Why the LLM gets the final say

The lexicon does not encode pragmatics. It records that `darlin'`
is informal, southern American, and affectionate. Stable, auditable,
structured facts.

What it does not record, and cannot, is when those facts add up to
warm rapport versus paternalism versus harassment.

The example below is one I can speak to directly. I live in
Louisiana, the deep South. This is not outsider speculation about a
speech community I observe from the outside. It is the speech
community I live in. The example uses one ordinary word from my
neighborhood to illustrate why a structured lexicon cannot, and
should not, encode the situational rules that govern its use.

Consider `darlin'` in two contexts. In a Waffle House in Mobile,
a waitress refilling coffee uses it as a conventional friendly
address. She uses the same word with the next ten customers
regardless of their age or gender, and nobody at the counter blinks.
In a Manhattan corporate boardroom, a senior executive uses the
same word to a junior colleague being handed a report, and it
reads completely differently. It can land as condescension, as a
power-asymmetry signal, or as something a workplace would flag as
inappropriate. Same word. Same dictionary entry. Two contexts.
Two readings.

The lexicon cannot encode which reading applies. The Waffle House
and the boardroom are not properties of the word; they are
properties of the situation the word is being used in. A waitress
using it in a boardroom would land differently than a waitress
using it in a Waffle House. An executive using it in a Waffle House
on a Saturday morning to an old friend over hash browns would land
differently than the same executive using it in the boardroom on
Monday. The situation rules, not the word.

This is also why temporal labels are slippery. `Darlin'` is current
in the Deep South in 2026. The same word in the same context in
Manhattan reads as either Southern affectation or period-piece
dialogue. Sixty or seventy years ago it was unmarked across most of
the English-speaking United States. Encoding it as globally "dated"
would misdescribe the speech of millions of people who use it every
day. Encoding it as globally "current" would miss the marked-feeling
it carries outside its home dialect region. Neither single label is
right.

Capturing every regional nuance is structurally hard for any
reference work. Static metadata flags are a coarse instrument for
phenomena that vary by region, era, setting, and speaker.
Individual glosses inherited from the source dictionary will
sometimes label a word in ways that fit one speech community
better than another. The architecture's response is to make
sources, rewrites, and metadata fully inspectable. Anyone running
the pipeline can re-improve glosses against their own corpus,
override specific entries for their own deployment, or fork the
lexicon for their own speech community. The lexicon is auditable
and forkable. It does not claim to be the final word.

Judging which reading of a context-sensitive word applies in a
given situation is the kind of thing an LLM does well and a
lexicon should not try to do at all. LLMs have read millions of
novels, plays, screenplays, dialogues, transcripts, and social
media posts. They cannot articulate the rules, and shouldn't,
because articulating them produces the wrong rules. But the
patterns are baked into their weights from all that reading.
Given context, an LLM picks the right sense not because it has a
lookup table but because it has internalized the statistics of
how people actually talk.

That is what the optional LLM tiebreaker is for. It fires only on
the residual hard cases, when the cheaper retrieval stages leave
the top candidates close in score and divergent in their structured
metadata, and it brings world knowledge to bear on exactly the
questions the lexicon refuses to answer.

The cascade is built around this division of labor. Cosine
retrieval and the cross-encoder reranker answer "which senses are
semantically near the query?" A lexical signal (BM25-style) over
the retained candidates answers "do the actual words overlap?" Each
stage is honest about what it knows and silent about what it does
not. The LLM is honest about something different: it knows context,
it knows pragmatics, it knows the unspoken rules of who says what
to whom under which circumstances. It is also the slowest and most
expensive layer, which is why the cascade saves it for last and
never calls it at all when the cheaper layers are confident.

A lexicon that pretended to encode pragmatic rules would be a
lexicon that aged badly and got the hard cases wrong. A lexicon
that hands those cases to the layer that can actually reason about
them stays clean, stays honest, and gets the right answer more
often.

## The structure of a canonical ID

Every sense in the lexicon has a canonical ID with the same
five-piece shape:

```
en.bank.dry_sides_river.noun.core
en.bank.building_keep_borrow.noun.core
en.bank.act_plane_turning.verb.core
```

The language scopes ambiguity (English has its own `bank`s, French
has its own `banc`s). The lemma anchors the surface form. The
microgloss disambiguates senses sharing the lemma; it IS the
disambiguator, baked right into the ID. The part-of-speech
distinguishes word categories. The namespace separates audiences
(general, medical, legal, technical).

The ID is self-disambiguating because the microgloss carries
enough meaning to read the ID and know what it points at. The
river sense and the financial sense are distinct strings before
either one gets looked up.

The ID also outlives any particular embedding model. Re-embed the
lexicon with a new embedder next year; the IDs stay the same. The
embedder is just the index used to find the right ID; the ID
itself is anchored to the lemma, microgloss, and POS, none of
which depend on the embedder. That is what lets a knowledge graph
store edges as canonical-ID pairs and still mean something five
years from now.

## The decompression map: from address to traceable bedrock

The stopping-rule section earlier in this article made a strong
claim: the canonical ID is the operational stop for the symbol
grounding regress. That claim is half-true as the lexicon
stands today.

The canonical ID gives a machine an inspectable address.
`en.wagon.cart_pulled_by_animal.noun.core` is a real string,
disambiguated from every other sense of wagon, derivable on any
machine running the pipeline. That is the floor the rest of the
argument rests on.

What the floor does not yet do is *terminate*. A machine that
lands on the address has stopped on a string, but the string does
not yet trace down to bedrock. The half of the stopping-rule
claim that remains is the trace.

Language is a lossless macro-compiler for thought. When a speaker
says wagon, the speaker compresses an entire structural concept
-- a platform with an axle, wheels mounted on the axle, a hitch
that lets it be pulled by an animal or a machine, the function of
moving cargo -- into a five-letter token. The token is fast to
transmit. The reconstruction is implicit. Listeners decompress
the token in their own heads because they share the structure
that wagon points at.

A dictionary is not the decompression. A dictionary is a lossy
approximation that defines complex words using other complex
words. Pail points to bucket. Bucket points to pail. The loop is
the failure mode. The structural decomposition leaks out at
every step. Machines that walk dictionary definitions land in
circles, not on bedrock.

The decompression map is what fixes this. Every lexicon entry
gets a small attached graph of typed edges to other entries.
Three edge kinds carry the structural load:

- **IS_A** is the taxonomic spine. `calico_cat IS_A
  domestic_cat`, `domestic_cat IS_A cat`, `cat IS_A feline`,
  `feline IS_A mammal`, `mammal IS_A animal`, on down. The spine
  is polyhierarchic where reality demands it -- tomato is
  legitimately `IS_A fruit` (botanical) and `IS_A vegetable`
  (culinary), both true, neither suppressing the other -- but the
  graph stays a DAG. No cycles. Every chain must terminate.
- **HAS_PART** is the compositional decomposition. `wagon
  HAS_PART wheel`, `wagon HAS_PART axle`, `wagon HAS_PART
  platform`, `wagon HAS_PART hitch`. Each component is itself a
  lexicon entry with its own decompression. Pointers, not
  inlined definitions. The lexicon stays flat at any given
  node; depth comes from following the edges.
- **The semantic roles** carry default scripts where they apply.
  `strawberry HAS_ATTRIBUTE red_color`. `strawberry
  HAS_ATTRIBUTE sweet_flavor`. `wagon HAS_INSTRUMENT pulling`.
  Not every entry needs every role; the roles attach when the
  concept's structure demands them.

The IS_A chains terminate at semantic primes. This is the second
load-bearing claim, and it borrows from work that predates the
lexicon by decades. The Natural Semantic Metalanguage program,
led by Anna Wierzbicka and her collaborators, proposes that
human languages converge on roughly sixty-five irreducible
concepts: substantives like *someone* and *something*, actions
like *do* and *happen*, cognitive verbs like *think* and *know*,
perceptual verbs like *see* and *hear*, and a small set of
relational and temporal primitives. These primes are not further
definable in their own language without circularity. They are
where decomposition stops because there is no further down to
go. The lexicon stands on that work. The primes are not
something this project invented; they are a half-century of
careful linguistic research that this project is putting to
operational use.

Every IS_A chain that lands on a prime has fully decompressed.
Every chain that fails to land at a prime is marked UNRESOLVED
rather than hidden. Honest gaps beat invisible ones. A machine
that encounters an UNRESOLVED entry knows it has reached the
edge of the lexicon's grounded knowledge, and can refuse to
act, ask for more context, or proceed cautiously with full
disclosure of the gap.

That is what closes the loop on the stopping-rule claim. The
canonical ID is the address. The IS_A path to primes is the
trace. Together they make the stop operational instead of
aspirational. A machine that lands on `calico_cat` can now walk
down to bedrock and back up through composition, attributes,
and default scripts. Vocabulary stops being opaque tokens and
becomes a navigable structure.

The map also opens a second door, less obvious but important.
If a separate knowledge graph (encyclopedic claims, scientific
facts, organizational records) uses the same canonical IDs,
then every lexicon entry becomes a hyperlink into that graph. A
robot that has just identified a calico cat in a photograph can
resolve to the canonical ID, walk the IS_A spine up to mammal
for abstract reasoning, and pivot through the same ID into
encyclopedic entries about feline behavior, longevity, breed
genetics, or whatever else the connected graph carries. The
lexicon and the encyclopedia speak the same address vocabulary.
The pivot is a lookup, not a search.

Now the hard part. Building the decompression map cannot be
fully deterministic the way canonical ID minting is. The
minting algorithm reads structured Wiktionary fields and
produces a canonical address through a federated tournament
with deterministic audit gates. The decompression map needs an
LLM to read each entry's gloss and example sentences and
propose IS_A parents, HAS_PART components, and role-bound
spokes. Two different LLMs will produce two different graphs.
The same LLM run twice will produce slightly different graphs.

The answer is the same pattern the microgloss tournament
already uses, applied at a higher layer. The decompression map
gets built in passes:

1. **Provisional pass.** One or more LLMs propose IS_A parents,
   HAS_PART components, and the role-bound spokes. Marked as
   `decompression_provisional`.
2. **Audit pass.** Every IS_A chain must terminate at a prime
   within a bounded number of hops. No cycles. Every HAS_PART
   component must itself be a lexicon entry. Failed chains get
   flagged for review.
3. **Federation pass.** Multiple LLMs propose; consensus claims
   are locked into the backbone; disputed claims are recorded
   with their proposers as separate hypotheses. Same federation
   discipline as the microgloss tournament, applied to a
   different artifact.
4. **Hill-climbing pass.** Audit failures get re-proposed,
   periphery gaps get filled, the structural backbone gets
   polished. The decompression map improves over time without
   ever needing to be rebuilt from scratch.

Not every claim in the map needs to converge. The IS_A backbone
must -- two builders that disagree about whether `calico_cat
IS_A mammal` are both wrong, and the audit catches it. The
compositional skeleton should mostly converge. The role-bound
spokes can vary, because reasonable observers can disagree
about which attributes are essential and which are incidental.
The lexicon already handles gradient agreement at the
microgloss tier (content-identical, close-cousin, topically
related). The decompression map extends the same idea to its
own layer: strict on the backbone, looser on the periphery,
explicitly marked which is which.

The map does not ship in the current pipeline. The architecture
is sketched; the audit gates are designed; the code is for
later. What this article is delivering is the architecture and
the code for the layer below. Anyone with the resources and the
time can take that floor and build the decompression layer on
top of it. A serious effort -- a research group, a crowdsourced
build, a well-resourced organization -- could produce a
high-quality, audited map for a major language in a measured
number of months, with the residual gaps marked UNRESOLVED
rather than hidden. That is not this project's claim for
V1. It is V2, and it is the use case that the V1 floor is sized
to support.

## Custom vocabularies and federation without coordination

A reasonable next question: what about words and terms specific
to my business, industry, profession, or document corpus? Product
names. People. Companies. Places. Internal jargon. Account types.
Region codes. None of that is in the general lexicon.

The fifth piece of the canonical ID is for exactly this. The
`.namespace` slot at the end of every ID separates the general-
audience core lexicon from the custom vocabularies any
organization can build on top of it.

The general lexicon entries all end with `.core`:

```
en.bank.dry_sides_river.noun.core
en.indemnification.protection_against_loss.noun.core
```

Domain-specific entries live in their own namespace:

```
en.indemnification.acme_warranty_clause_4_2.noun.acme_legal
en.lab_result.fasting_glucose_morning_draw.noun.acme_hospital
en.bonded.tier_3_warehouse_zone.adj.acme_logistics
```

None of these collide with the core lexicon. None of these
collide with each other. Each namespace is a private mini-lexicon
built by the same pipeline pointed at the organization's own
corpus instead of (or alongside) Wiktionary. Custom namespaces
are yours. They do not ship with the core. They do not get pushed
to anyone else's machine. The pipeline that mints them runs on
your hardware, against your documents, under your control.

So far this looks like a fork-and-extend story. Here is where it
gets stronger.

**Two companies can communicate about word senses without
coordinating on a lexicon.** The canonical ID is not an opaque
hash or a numeric integer assigned by central authority. It is a
structured string: language, lemma, microgloss, part of speech,
namespace, separated by dots. That structure is the federation
key. Burst the ID on dots, and you have everything you need to
re-resolve the sense on a different machine.

One preliminary, because the federation contract is precise about
what it requires. The tournament that mints a microgloss scores
each candidate against the lexicon's own cluster of close-cousin
senses. The cluster for `bank` in a Simple English Wiktionary
build (about 72,000 senses) is small. The cluster for the same
sense in a full English Wiktionary build (about 1.7 million
senses) is large. The tournament can pick a different winner in
each case, because the test "does this candidate disambiguate
against its siblings" produces different scores against
different sibling sets. For local use either build is fine. For
federation -- the case where two parties need to mint the same
canonical ID for the same sense without coordinating -- the same
source build matters as much as the same embedders. Full English
Wiktionary is the recommended substrate for federation-grade
builds. Simple English is the right starting point for
experimentation, learning the architecture, and any deployment
that is intentionally local. The federation contract is about
the embedders AND the source corpus. Both have to match.

The mechanism is federation by re-derivation. The receiver bursts
the sender's canonical ID into its five parts, treats those parts
as a search query, and runs them through its own lexicon's
cascade -- cosine retrieval, cross-encoder reranker, BM25 layer,
optional LLM tiebreak. Out the other end comes the receiver's
equivalent canonical ID. Different string. Same meaning. Neither
machine has to have run the same improver, called the other's
API, or trusted a central registry. The shared infrastructure is
the algorithm, not the data.

There is a faster path when both parties happen to have run the
same provisional pipeline against the same source dump. The
deterministic provisional microgloss minter produces identical
IDs on both machines for the same sense, character for character.
The lexicon preserves both the provisional ID and the live
(possibly improved) ID per sense, so even after the LLM improver
runs, the provisional ID is available as a deterministic
federation fallback. In that case federation collapses to a
string-equality check; no search needed. The general case is the
interesting one, because it is what makes federation work when
the two parties have not coordinated on anything except the
algorithm itself: company A might mint
`en.bank.water_edge_sloped.noun.core`, company B might mint
`en.bank.sloping_land_river.noun.core`, same sense, different
live IDs, and the receiver's search recovers the equivalence in
milliseconds.

**Messages carry only the exceptions.** When both machines have a
lexicon derived from open Wiktionary, the shared vocabulary of
roughly 1.7 million general English senses is already on both
sides. A message about a contract dispute does not need to embed
definitions for `indemnification` or `contract` or `dispute`;
both machines can resolve those locally. What the message carries
are the canonical IDs themselves, plus mini-lexicon stubs for any
custom-namespace terms the receiver does not yet have. A
`.acme_legal` namespace entry travels alongside the message as a
small attached payload; the next message can omit it because the
receiver has cached it. The data segment of a federation message
is therefore small even for documents about complex specialized
topics. Most of what is being communicated is implicit in the
shared lexicon. Only the proprietary terms travel.

**The same federation pattern extends across languages.** Two
organizations running the pipeline against Wiktionary dumps in
different languages can communicate about the same senses by
exchanging canonical IDs from their respective lexicons. The
receiver bursts the sender's ID into its constituent parts and
runs them through its own lexicon's search using a multilingual
embedder. For senses with cross-lingual analogues in both
lexicons, the receiver lands on its equivalent canonical ID. The
lemmas differ across languages. The microglosses differ across
languages. The IDs differ across languages. The shared sense is
what the search algorithm is asked to find, and the multilingual
embedder is what finds it. This is operational cross-lingual
sense alignment, achieved by combining established multilingual
embedding research with the structured-ID-as-cue protocol
described here. The embedding technology is mature and excellent;
this pipeline uses it without modification. The contribution is
that cross-lingual sense alignment becomes a property of an open,
derivable, federation-capable lexicon, available to anyone
running the pipeline, without coordinated translation tables or
a central multilingual ontology. The next section describes the
version of this property that gets cached: for high-volume use,
the runtime search collapses to a table lookup.

**Synonymy is gradient. The lexicon treats it as such.** Three
tiers of relatedness are maintained per sense: content-identical
(strict substitutability, used for snap_to_neutral substitution),
close-cousin family (same meaning family at different intensities
or registers, used for embedding cluster anchoring), and
topically related (same conceptual scene but distinct referents,
used to detect over-generic microglosses). Different downstream
consumers reach for different tiers. The lexicon does not pretend
a single binary boundary exists.

Cluster boundaries themselves are calibrated empirically, not
guessed. The pipeline ships with a small set of hand-labeled
anchor pairs spanning vehicles, temperature, lighting, emotions,
specialist terms, and regional variants. At build time, the
calibration step measures the cosine distance between each
anchor pair, then sets the cluster-membership threshold to the
value that best separates content-identical and close-cousin
pairs from topically-related-but-distinct pairs. Two machines
running the build with the same anchor set and the same embedder
produce identical thresholds, so the cluster boundaries
themselves are part of the deterministic federation contract.

**The protocol is documented.** The full machine-to-machine
federation protocol, including the canonical-ID bursting format,
the mini-lexicon stub schema, and an outline for the trust
extension covering acceptance of custom-namespace entries from
third-party counterparties, is documented in a draft
specification in the SGF repository. Publishing the protocol is
what makes the federation argument concrete instead of
aspirational.

Cross-organizational structured knowledge has historically been
hard for two related reasons. The first is that meaning across
systems requires identifiers that disambiguate; the second is
that getting independent organizations to agree on a shared
identifier vocabulary is a coordination problem that often does
not converge. Earlier efforts (RDF, OWL, the broader Semantic
Web program, and several generations of enterprise ontology
work) addressed parts of this and produced real results in some
domains, but the coordination cost has limited adoption at the
scale originally envisioned. The SGF Lexicon offers a working
solution to both problems together: every party mints its own
IDs, every party publishes the algorithm that derives them, and
every message carries enough structure in the IDs themselves to
resolve across non-identical lexicons. Two organizations that
have never talked to each other can build systems that
interoperate at the sense level on day one.

## Cross-lingual sense alignment as a precomputed table

The federation section above describes how two organizations
running the pipeline on Wiktionary dumps in different languages
can resolve each other's canonical IDs at runtime: burst the
sender's ID into its parts, run a multilingual-embedder search
against the receiver's lexicon, land on the receiver's
equivalent ID. That works. It is a search, and searches take
time.

For the high-volume machine-to-machine case there is a faster
path. Build the lookup once and cache the result. The same
multilingual embedder (`bge-m3-v1`, the federation reference)
that powers the runtime search can be run offline, sense by
sense, to populate a cross-lingual alignment table. For each
sense in the source language, store the resolved canonical ID
in every target language the operator cares about. English
`en.cat.domestic_feline.noun.core` maps to German
`de.katze.haus_katze.noun.core`, French `fr.chat.felin_domestique
.noun.core`, Japanese `ja.neko.kateinaikoneko.noun.core`, and so
on. One table, one row per concept, one column per language.

Two paths to building such a table.

The eager path runs the alignment for every sense ahead of
time. Substantial offline work; large output; ready instantly
when a query arrives. This is the right shape for an
organization with the resources and the motivation, or for a
crowdsourced public effort that produces alignments anyone can
download and use without re-running the build.

The lazy path is opportunistic. Every time the runtime
federation path actually resolves a sense from language A to
language B, write the result back to a cache table. Over time
the cache fills with the senses that traffic actually demands,
which is almost certainly a small fraction of the full
lexicon. The cache becomes a workload-shaped alignment table
without anyone having to plan it.

Why this is useful: the table makes cross-lingual sense
alignment a constant-time lookup instead of a multi-stage
search, and the lookup is inspectable. A receiver that
resolves `en.indemnification.protection_against_loss.noun.core`
to its German equivalent does so via a row in a table, not via
the output of a model. The mapping can be reviewed,
challenged, corrected, versioned, and signed. None of those
properties hold for an LLM translation of the same word.

The honest claim. This is not better natural-language
translation than what an LLM does for human readers. LLMs are
excellent at producing fluent prose in a target language. What
they are not designed for is grounded, auditable, sense-level
correspondence between two specific lexicon entries. The
alignment table is the grounded version: every word in the
target language points back to a specific canonical ID,
inspectable, derivable, and stable across runs. The use case
is not translation for humans; it is reliable machine-to-
machine communication where both sides need to know exactly
which sense the other side is referring to. For that case, a
precomputed alignment beats a runtime model call every time.

The same machinery extends from bilingual to fully
multilingual. Add a column per language. The table grows
linearly, not combinatorially: every language aligns against
the multilingual embedding space, not against every other
language pairwise. One hundred languages is one hundred
columns, not ten thousand language pairs. Adding a new
language is an additive operation, not a coordination problem.

The alignment table does not ship in the current pipeline. The
runtime federation path described above is what V1 supports.
The precomputed table is a use case the architecture is sized
to enable, and one that benefits the most from a serious
build effort by an organization or community willing to spend
the compute. The architectural pieces are in place for any
language pair the upstream pipeline supports: the embedders,
the canonical IDs, the search algorithm. Adding a new language
requires the per-language loader work named in the scope
section later in this article. Once that loader exists, the
alignment work is the running of it.

## One floor in a larger pipeline

The SGF Lexicon is not a standalone product. It is one stage in a
larger compilation pipeline I call GLEAN, a prose-to-synapse
compiler that reads natural language and emits structurally typed
knowledge graphs.

GLEAN parses prose. For each meaningful token, it asks the lexicon
to ground that token to a canonical ID using the surrounding
context. The lexicon returns the ID, structured metadata, and a
relation profile. GLEAN assembles those grounded senses into
synapses: a verb hub with role-bound spokes that say who did what
to whom, where, when, by what means, why.

The grammar of those relations is closed by design. Seventeen
canonical relation types: IS_A, HAS_PART, six core thematic roles
(agent, patient, theme, experiencer, recipient, beneficiary), and
nine context roles (time, location, source, destination, manner,
instrument, cause, reason, attribute). No HAS_PURPOSE. No
HAS_TITLE. No HAS_JOB. No HAS_USAGE. Adding more relation types is
the predicate-explosion failure mode that has killed many
knowledge-graph projects. The closed grammar is the discipline
that prevents schema babel.

The fifteen semantic roles are not arbitrary, and they are not
original to this project. Linguistic work going back to
Fillmore's case grammar and the thematic-roles tradition that
followed established a small, recurring set of role categories
that human languages reach for again and again: who did the
thing, who it was done to, what was being affected, who
experienced it, who received it, who benefited, where, when,
how, by what means, why, with what attributes. Different
researchers proposed slightly different lists; the family
resemblance is the constant.

The fifteen that this project uses were not chosen by theory.
They were arrived at mechanistically. The procedure: take a
large body of natural-language text, attempt to decompose every
clause into a verb hub and its role-bound participants, and
record which roles a given decomposition needs. The first
twelve roles handle the bulk of the work. The thirteenth,
fourteenth, and fifteenth close coverage gaps that the first
twelve leave open. A sixteenth role was tried and was not
needed; every clause that initially seemed to demand one
factored cleanly into the existing fifteen. If a future
counterexample turns up that genuinely requires a sixteenth
role, the architecture allows it. Until then, fifteen is
treated as a commitment, not a guess.

Expressiveness comes from composition, not from more relation
types. "Theodore Roosevelt was president" is not a HAS_TITLE
relation in the lexicon; it is a synapse group at the discourse
layer composed of multiple synapses using only the 17 canonical
relations. The lexicon stays bounded. The discourse layer above it
gets the expressiveness.

This is the architectural commitment: the lexicon is the floor;
GLEAN is one of the floors above it. Changes to the lexicon do not
break GLEAN. Changes to GLEAN do not require lexicon changes. The
layering is intentional and worth the discipline.

GLEAN is itself one component of a larger framework called SGF
(Symbol Grounding Framework). SGF does not claim to solve the
philosophical symbol grounding problem, the consciousness
problem, or universal meaning representation. It is an
engineering proposal: an architecture for machine-to-machine
meaning that is grounded enough to audit, structured enough to
govern, and traceable enough to disagree with. The lexicon
described in this article is the vocabulary substrate. The
Synapse format is the grammar of events and roles. The Omega
governance language sits above both. Together they constitute
SGF's answer to a practical question: how do machines coordinate
on meaning across trust boundaries, without a central authority
and without confident hallucination? The lexicon stands on its
own. The rest of SGF is documented in the SGF repository for
readers who want the broader architecture.

## What this is not

It is worth naming the boundaries directly.

This is not a dictionary for humans. The microglosses are written
to disambiguate senses for machine retrieval, not to teach
vocabulary to a language learner.

This is not yet an encyclopedia. A lexicon entry for "president"
currently knows the word exists, knows it IS_A leader, and carries
a one-sentence microgloss. It does not know that presidents lead
countries, are elected, serve terms, sign bills, or veto
legislation. That structural knowledge lives in the prose of
dictionary definitions and example sentences, but it has not yet
been extracted into queryable form. That work is V2.

This is English-Wiktionary today, not yet a multilingual pipeline.
The federation reference embedder is multilingual, so the
embedding side of the federation contract carries over across
languages. The upstream ingest does not yet: the loader, the
inflection detector, and several of the tournament candidate
strategies are built around English-language conventions. A
proper Japanese, Chinese, Arabic, Hebrew, or Finnish build needs
a per-language loader pass, a per-language inflection-marker
study, and a per-language audit of the candidate strategies
that assume English word boundaries. That work is on the
roadmap. It is not done today.

This is not a record of pronunciation, etymology, register-as-
prosody, regional dialect axes, or gendered grammatical forms.
The lexicon carries four metadata flags (register,
temporal_status, social_status, specificity) and a closed
seventeen-relation graph. Those cover what the downstream
compiler needs. Linguistic phenomena outside that scope are
not represented. Some of them belong in other tools; some of
them will become extensions later.

This is not a complete solution to any problem. It is a substrate.
A substrate is only useful in proportion to what gets built on top
of it.

## Roadmap: a federated address space for grounded knowledge

Consider a query about the Beatles song "Help!". The lexicon
described in this article will not find it. That is not a
defect. A sense-level lexicon for common vocabulary is not the
place where named entities live. Songs, films, books, people,
places, products, events, organizations, laws -- none of those
are in scope for a Wiktionary-derived lexicon, and none of those
should be. The lexicon's job is common-vocabulary senses. Other
kinds of meaning need other artifacts.

The architectural commitment is that all of them share one
address space. The canonical_id format is the same whether the
address points at a common-vocabulary sense, a named entity, a
common-sense rule, or a domain-specific concept. Different
artifacts, one addressing convention, federated by the same
re-derivation property the lexicon already uses.

Several sources of grounded knowledge are on the roadmap. Each
is built with the same minting algorithm pointed at a different
source corpus. Each ships with its own namespace. Each grounds
back to the lexicon through `IS_A` and the other 16 canonical
relations.

**The encyclopedia layer.** GLEAN, the prose-to-synapse compiler
this lexicon already grounds, pointed at Wikipedia. Article
titles get canonical_ids in an encyclopedia namespace. Article
claims become synapses using the 17 closed relations. Each
synapse node is itself a canonical_id, either a lexicon entry
for common vocabulary or an encyclopedia entry for named
entities. The Beatles' "Help!" lives at an encyclopedia ID. The
common-noun sense of "help" lives at a lexicon ID. An `IS_A`
link from the song to the lexicon's `song.music` entry grounds
the named entity back to common vocabulary. A query about the
Beatles routes to the encyclopedia; a query about helping a
neighbor routes to the lexicon. Same address format. Two
grounding sources, side by side.

The same GLEAN pass turned inward enriches the lexicon itself.
Every lexicon entry's gloss and seeded example sentences,
compiled into synapses and attached back to the entry, turns
the lexicon from a dictionary into a miniature structured
encyclopedia: every concept carries the typical synapses that
characterize it. The work is real, the architecture is the
same, the shipping is queued.

**The common-sense layer.** Open-source common-sense knowledge
collections (the kind that record propositions like "stepping
off a sidewalk into heavy traffic can injure or kill you" and
"hot stoves should not be touched") get the same treatment.
Each common-sense claim becomes a synapse. The nodes are
canonical_ids. The relations are the same 17. The result is a
grounded corpus of pragmatic world knowledge that a robot, an
agent, or a reasoning system can navigate without having to
learn it experientially or be shown millions of images of
streets and stoves. Prose, mined into synapses, becomes a form
of programming without programming. The robot does not have to
get hit by a car to learn the rule. The rule is downloadable.

**Domain-specific knowledge packs.** The same minting algorithm
pointed at a focused source corpus produces a knowledge pack:
the civil and criminal codes of a jurisdiction, the regulatory
framework of an industry, the scientific literature of a
subfield, the medical reference for a specialty, the internal
documentation of an organization. Each pack ships with its own
namespace, its own canonical_ids, and its own synapses, all
grounded back to the lexicon through IS_A links and the other
canonical relations. A receiver downloads the pack, validates
the federation contract, and now has grounded knowledge in that
domain that interoperates with everything else built on the
same address space.

**Organizational and corpus-specific knowledge.** GLEAN pointed
at an organization's own documents -- PDFs, internal wikis,
contracts, manuals, runbooks, transcripts -- produces the
private equivalent of a knowledge pack. Same minting algorithm,
same canonical_id format, private namespace. The organization's
proprietary meaning becomes grounded structure that its own
systems can navigate, audit, and reason over. Nothing leaves
the organization unless the organization chooses to export
it. The architecture is the same; the data stays where it
belongs.

What all of them share is the property the V1 lexicon
establishes: **federation by re-derivation across a unified
address space**. Two parties holding different combinations of
artifacts can still communicate at the sense level. The lexicon
they share is the common ground. The encyclopedia, the
common-sense corpus, the knowledge packs, and the private
organizational graphs are specializations on top of that ground.
A query can navigate across them in hops -- lexicon to
encyclopedia to knowledge pack to private graph -- because every
node is a canonical_id with a known format, and every link is
one of the 17 canonical relations. The combined navigability is
larger than any single artifact.

One nuance about the canonical_id as a linkage mechanism. When
two artifacts of the same kind link to each other -- two lexicon
entries, two encyclopedia entries -- the canonical_id is the
link. String equality, or its embedder-tolerant federation
cousin, does the work. When two artifacts of different kinds
link -- a situation described in prose to an abstract wisdom
rule, an abstract principle to its concrete instantiations, a
named entity to its common-vocabulary parent -- the canonical_id
is still the stable handle, but the linkage itself requires a
bridge mechanism specific to the category gap being crossed.
The lexicon's IS_A relations are one such bridge. The
closed-vocabulary bridge pattern for matching abstract wisdom to
concrete situations is another. The instantiation-as-embedding-
payload mechanism for retrieving abstract rules through their
concrete anchors is a third. These bridges, together with the
canonical_id format, are the linkage architecture of the broader
knowledge stack. They are addressed in companion essays alongside
this one.

This is what the V1 lexicon is the floor for. The lexicon
described in this article is the substrate. What gets built on
top of it -- by this project, by collaborators, by independent
groups, by anyone who shows up -- depends on who builds. The
minting algorithm, the federation contract, the audit
discipline, and the closed grammar are the architectural
contributions that survive across every layer. V2 is named
here so that V1's design choices can be understood as
load-bearing for what comes next. V1 stands on its own; the
roadmap exists so that V1's adopters know what they are
positioning themselves for.

## Closing

The substrate is the floor a language-processing system stands on.
The SGF Lexicon is what one of those floors looks like when it is
designed for AI from the start: stable identifiers, machine-
queryable embeddings, structured metadata, a closed-grammar
relation graph, an audit gate, an LLM-driven improvement loop, and
a search server that knows when to cascade.

It is free, open source, and runs locally. The repository ships
with a 72,000-sense development lexicon that comes alive within
an hour of cloning. Pointing the pipeline at a full Wiktionary
dump builds out to roughly 1.7 million senses on the same hardware
over an overnight or multi-day run. The dev fixture is for
experimenting and iterating; the full build is for shipping.
There is no license to sign, no credit required, no API key needed
for the core build. Anyone can take the code, customize it for
their own corpus, and ship a domain-specific lexicon (medical,
legal, scientific, financial, or any other) using the same
architecture.

The SGF Lexicon is part of the larger SGF (Symbol Grounding
Framework) project, which aims to build the foundations for
grounded AI reasoning. The lexicon stands on its own. You do not
need the rest of SGF to use it. You do not need to subscribe to
its architecture or its philosophy. If the missing floor is
something you have noticed in your own systems, this is one
attempt at building it.

---

*The SGF Lexicon Pipeline source, spec, and roadmap are on GitHub.
The architectural spec (`SGF_LEXICON_PIPELINE.md`) documents every
decision and its reasoning. The forward-looking V2 vision lives in
`V2_VISION.md`.*
