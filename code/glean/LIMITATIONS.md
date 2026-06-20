# GLEAN v1.1 — Known Limitations and Quality Criteria

This document lists the twelve disambiguation rules that govern what a
"good" synapse looks like, and their enforcement tier in v1.1.

## Three enforcement tiers

- **HARD** — structurally enforced. A synapse that violates this is
  rejected at compile time.
- **WARN** — flagged in the audit log. Synapse is still written.
- **ASPIRE** — the LLM framing mode tries; deterministic mode does not
  attempt. Not flagged.

## The twelve rules

### Rule 1 — Pronouns become named entities. WARN.

`he`, `she`, `it`, `they` should be replaced by the specific entity they
refer to. v1.1 resolves pronouns by proximity in entity_census.py. When
proximity finds no antecedent, the pronoun is logged as a GHOST mention
but not rejected.

### Rule 2 — Definite articles become full canonical entities. WARN.

`the company`, `that person`, `this report` should resolve to specific
named entities. v1.1 makes a best effort; unresolved cases are flagged.

### Rule 3 — Relative time references become absolute. ASPIRE.

`yesterday`, `soon`, `recently` should become specific dates. v1.1 does
not perform this rewrite. Document-anchor support is planned for v1.2.

### Rule 4 — Relative location references become absolute. ASPIRE.

`here`, `there`, `nearby` should resolve to named places. Same status
as Rule 3.

### Rule 5 — One verb per fact. HARD.

Compound sentences are split. Each root verb produces one synapse. v1.1
enforces this structurally via the `_is_clause_root` check in
clause_to_synapse.py.

### Rule 6 — No unresolved comparatives. ASPIRE.

`bigger`, `best`, `more efficient` should be reframed against an
explicit comparison target. v1.1 does not do this. The
`HAS_ATTRIBUTE` spoke captures the comparative form as a surface; a
downstream stage can refine.

### Rule 7 — No idioms or metaphors. WARN.

LLM framing mode sets `rhetorical_mode=metaphor` when it detects
figurative language. Deterministic mode does not detect metaphor and
treats all clauses as `straight`.

### Rule 8 — No questions or commands. WARN.

Questions and imperatives are not standard fact-statements. v1.1 still
compiles them but the framing layer should set
`statement_type=question` or `statement_type=command` (LLM mode only).
Deterministic mode treats them as factual.

### Rule 9 — Explicit causality. WARN.

`Because of this, X happened` requires that "this" be resolved. v1.1
captures `HAS_CAUSE` and `HAS_REASON` when prepositions like "because
of," "due to," "owing to" appear. Implicit causal chains across
sentences are not resolved.

### Rule 10 — No undefined acronyms. ASPIRE.

`CBE`, `SEC`, `IRS` without expansion. v1.1 detects all-caps tokens
of 2-5 letters and flags them for review when no expansion is found
in the document. Not rewritten.

### Rule 11 — Attributed claims preserve their source. HARD (in framing).

This is the most important rule. v1.1 enforces it via the
attribution-first POV detection in framing.py:

- If the predicate is a reporting verb (`said`, `claimed`, `alleged`,
  ...), the subject of that verb is the POV speaker.
- The clause's `statement_type` becomes `reported_claim`.
- The default POV (`author`) is used ONLY when no reporting pattern is
  found.

This means "Beethoven moved to Vienna" has POV=author. "Haydn claimed
Beethoven was a difficult student" has POV=Haydn with
statement_type=reported_claim.

### Rule 12 — Modality is preserved. HARD.

`might`, `could`, `would`, `must` all set `verb_modality` to
`epistemic` or `deontic` and `statement_type` to `speculative` where
hedging is present. v1.1 enforces this in the deterministic framing
path.

## Three additional v1.1-specific notes

### Literal-entity threshold

Years (4-digit, range 1000-2099) and small integers (0-1000) become
node-worthy literals with canonical IDs of the form `lit.year.1792`
and `lit.int.9`. Specific calendar dates ("December 17, 1770"), large
numbers, decimals, money, and percentages stay as `target_surface` on
their spoke, with no entity node created.

This honors the "rules should not be brittle" principle by classifying
literals by structural pattern (4-digit number in a year range, integer
in a small range), not by hardcoded surface forms.

### POS Rosetta

`pos_rosetta.json` maps spaCy POS tags to the SGF `pos_simple`
vocabulary. The lexicon's POS column stays as-is. The Rosetta lives in
the GLEAN bundle and is loaded on demand. To change the mapping, edit
the JSON; no code change required.

### Nested-reality POV

v1.1 supports one POV layer per synapse, but the schema
(`pov_layer` field) is designed to accept nested layers. A future v1.2
will write one synapse per layer: the discourse layer (the document
author) AND the character layer (Beethoven, when "Beethoven said X").
For v1.1, only the closest layer is written.

## v1.1 mid-stream additions (June 2026)

These were added after the initial v1.1 ship to bring the entity census
closer to the full pipeline vision (entity map -> alias -> adjacent text
harvest -> embed -> lookup -> mint -> CCE -> AST -> burst -> dedup).

### Multi-pass alias clustering

`EntityCensus.process()` now runs `_pass3_cluster` in a loop (capped at 5
iterations) until no more merges happen. This lets transitive chains like
`Ludwig` -> `Ludwig van Beethoven` -> `Beethoven` collapse into one
cluster even when the merges depend on each other.

### Adjacent-text harvest

A new `_pass5b_harvest_context` runs after the possessive pass. For each
non-literal entity it finds the FIRST occurrence of the LONGEST surface
form among its mentions, then captures that sentence plus one neighbor
on each side as `Entity.context_text`. The context becomes the embedding
input at lookup time, so the local discourse, not the bare surface,
drives the sense-selection score.

### Recursive possessive chains

`_pass5_possessive_chains` now delegates anonymous-entity creation to a
`_get_or_create_anonymous_entity` helper. Because every `poss` dep in the
doc is walked, multi-link chains (e.g. "Beethoven's father's house")
emerge naturally; no special-case code is needed beyond what spaCy's dep
parse already gives us.

## Roadmapped, not in v1.1

### Clause-relationship AST (v1.2)

The `clause_to_synapse` step still emits one synapse per root verb. The
planned v1.2 IR layer will tag each clause with both its English surface
and its canonical_id, and the AST burst step will run between clause
extraction and synapse loading. Until then, cross-clause structure must
be recovered downstream.

### Synapse content fingerprint dedup (v1.4)

The "burst into synapses" step in v1.1 can write near-duplicate synapses
when the same fact appears twice in a doc with slightly different
wording. The lexicon's content fingerprint scheme (1024-bit simhash, the
same design we are calibrating for senses) will be extended to synapses
in v1.4. Until then, dedup is heuristic and may leave near-duplicates.

### Layered lexicons (config stub only in v1.1)

`sgf.toml` accepts a `[lexicons]` table listing core / domain / corpus /
document layers. Only the core layer and document-mint layer are wired
in v1.1. The schema is stable; the resolver fan-out across all four
layers ships in v1.3.

## What deterministic mode catches reliably

- Possessive stripping ("Beethoven's" -> "Beethoven")
- Alias clustering ("Beethoven" merges into "Ludwig van Beethoven")
- Multi-pass alias clustering for transitive merges
- Pronoun resolution within a few sentences of the antecedent
- Reporting-verb POV assignment ("Haydn said" -> POV=Haydn)
- Determiner-scope negation ("no surviving letter")
- Hedging detection ("perhaps", "may", "some scholars believe")
- Year-granularity temporal literals (1792, 1770)
- Small-integer literals (9 symphonies)
- Adjacent-text context harvest for embedding input
- Recursive possessive chains via stacked spaCy `poss` deps

## What deterministic mode misses (LLM mode catches)

- Sarcasm and irony detection
- Metaphor detection
- Verb aspect refinement beyond simple/progressive
- Mood detection (subjunctive, conditional)
- Long-range coreference (pronoun whose antecedent is 5+ sentences back)
- Verbatim quote vs paraphrase distinction in the middle of a
  reported-speech sentence
- Compound spelled numbers beyond two-tens (e.g. "one hundred and
  twelve")
