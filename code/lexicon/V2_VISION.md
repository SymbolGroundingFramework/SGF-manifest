# V2 Vision: The Lexicon as a Miniature Structured Encyclopedia

**Status:** Vision document. No code. No commitment.
**Date:** This is forward-looking; capture the idea while the context is fresh.

---

## The thesis

The V1 lexicon (what just shipped) is a sense dictionary with grounded
canonical IDs, embeddings, and a navigation graph of IS_A / HAS_PART /
15 SGF roles. It does its job: it grounds words to senses, and it
gives GLEAN a substrate to compile prose against.

But it is not yet an encyclopedia. A lexicon entry for `president`
knows the word exists, knows it IS_A leader, knows a one-sentence
microgloss. It does not know:

- Presidents *lead* countries (HAS_AGENT pattern with verb `lead`)
- Presidents are *elected* (HAS_PATIENT pattern with verb `elect`)
- Presidents *serve* terms (HAS_AGENT pattern with verb `serve`,
  HAS_THEME `term`)
- Presidents *sign* bills, *veto* legislation, *appoint* officials

That structural knowledge sits in the gloss text and example
sentences, but it is not extracted, not queryable, not navigable.

V2 changes this. The lexicon becomes encyclopedic by running each
sense's gloss + examples through the same prose-to-synapses extractor
GLEAN already uses for documents.

---

## The shared sub-component (the architectural payoff)

GLEAN today runs four stages on prose: `entity_census`,
`clause_to_synapse`, `framing`, `synapse_grouper`. These four are not
GLEAN-specific. They are a generic prose-to-structured-meaning
extractor.

Factor them into a shared library (working name `synapse_extractor`).
Two consumers, same code:

```
                      synapse_extractor (shared)
                              |
              +---------------+---------------+
              |                               |
      GLEAN compile_document        Lexicon Phase 2C
      (essays, PDFs, articles)      (per-sense glosses + examples)
              |                               |
              v                               v
      synapses.db (per document)      lexicon_descriptive_synapse
      synapse_group, group_def        lexicon_descriptive_group (?)
```

Same closed grammar (17 SGF relations). Same framing layer. Same
audit gates. Only the input source and the output target differ.

This is more than a refactor. It is recognition that GLEAN and the
lexicon are doing the same fundamental operation in two different
contexts.

---

## The doctrine question

SGF doctrine today says "SynapseGroups are forbidden in lexicon
entries." V2 will need to engage with this directly.

The probable refinement:

> Lexicon entries may carry descriptive Synapses about the concept
> they define. They may carry conceptual SynapseGroups (typical-event
> bundles for the concept). They may NOT carry instance-level
> SynapseGroups (facts about specific named individuals). Instance
> facts live in the synapse store; concept structure lives with the
> concept.

Whether this refinement is approved is up to the SGF authors. The V2
work should not begin until that question is settled in doctrine.

---

## What V1 does and does not do

**V1 does (shipped today):**

- Grounds every Wiktionary sense with a canonical_id and microgloss
- Computes bge-small (diagnostic) and bge-large (production)
  embeddings
- Runs four-criterion self-retrieval audit as a ship gate
- Discovers content-identical clusters and picks standard forms
- Harvests IS_A, HAS_PART, and the 15 SGF roles via an LLM
- Resolves relation targets by embed-and-filter against the lexicon's
  own embeddings
- Validates against a strict 17-relation allowlist; drops
  hallucinations

**V1 does NOT do (deferred to V2):**

- Extract descriptive synapses from glosses or example sentences
- Carry conceptual SynapseGroups for typical-event bundles per
  concept
- Share extraction code with GLEAN's document compiler
- Represent instance-level facts (HAS_TITLE, HAS_JOB, etc.) —
  intentionally; those are GLEAN's job, not the lexicon's

---

## V2 implementation sketch (not committing)

If V2 happens, the rough shape:

1. **Extract `synapse_extractor` from GLEAN** as its own pip-installable
   library. GLEAN's `compile_document.py` becomes a thin wrapper.
2. **Add lexicon-side tables:**
   - `lexicon_descriptive_synapse(wiktionary_source_id, hub_canonical_id,
     polarity, modality, ...)`
   - `lexicon_descriptive_spoke(synapse_id, role, target_canonical_id, ...)`
   - `lexicon_descriptive_group(group_id, group_kind, ...)` (if doctrine
     permits)
   - `lexicon_descriptive_group_member(group_id, synapse_id, ...)`
3. **Add a Phase 2C friendly runner** `extract_encyclopedic.py` that
   walks the top-N frontier and runs the extractor against each
   sense's gloss + harvested example sentences.
4. **Decide the audit-gate question.** Working answer: descriptive
   synapses are queryable structure, not embedding-text input. The
   microgloss stays the retrieval anchor. Self-retrieval audit still
   tests "can each sense's microgloss find itself," because that is
   what cosine retrieval consumers care about.
5. **Update doctrine** if the refinement above is approved.

---

## Why this is worth doing

- **Real-world encyclopedia.** A lexicon that knows the structural
  content of its own concepts becomes a substrate for general
  reasoning, not just word-sense lookup.
- **One extractor, two consumers.** Builds shared muscle. Improvements
  to entity_census or framing benefit both GLEAN and the lexicon.
- **The 17 relations stay closed.** No new role types needed. The
  encyclopedic content is composed inside the existing grammar.
- **Honest layering.** Concept structure with concepts. Instance facts
  with instances. The boundary becomes a feature, not an awkward
  silence about HAS_TITLE.

---

## Why this is V2, not V1.1

- Touches doctrine.
- Requires a clean factoring of GLEAN's internals.
- Changes the lexicon's identity ("dictionary" -> "encyclopedia").
- Adds new schema tables and a new pipeline phase.

That is a deliberate architectural step, not a feature add. Ship V1
first. Live with it. Then come back to this when the V1 lexicon has
been used enough to know which encyclopedic content actually matters.

---

## Where to start when V2 begins

Three files mark the natural extension points in V1. Search for
`TODO V2:` to find them. They are intentionally light — pointers, not
half-built features.
