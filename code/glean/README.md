# GLEAN v1.1 — Prose-to-Synapse Compiler

End-to-end pipeline that compiles natural-language prose into a structured
synapse store grounded in the SGF lexicon.

## What changed in v1.1

- Attribution-first POV: the subject of a clause is no longer assumed to be
  the speaker. POV stays `author` unless a reporting verb appears.
- Three-class epistemic: `proven_fact`, `reported_claim`, `speculative`.
- Quote-type detection (direct vs indirect vs none).
- Literal entities: years (4-digit, 1000-2099) and small ints (0-1000) become
  navigable nodes with `lit.year.<n>` / `lit.int.<n>` canonical IDs.
- Specific calendar dates, large numbers, money, percent stay as
  `target_surface` on the spoke, not nodes. Avoids the property-graph trap.
- Possessive stripping, noise filtering, sequence-similarity alias merging.
- spaCy model fallback chain (lg -> md -> sm).
- Dependency-to-role mapping externalized to `dep_to_role.json`.
- POS Rosetta in `pos_rosetta.json`.
- Reporting verbs in `reporting_verbs.txt`.
- Determiner-scope negation flips polarity ("no surviving letter").

## Files

```
sgf.toml                     Configuration (paths, embedder, LLM, cascade)
sgflib.py                    Shared library: config, LexiconClient, embedder
                             singleton, LLM client, MDKV parser
sgf_cli.py                   CLI for ad-hoc lookups and status
entity_census.py             Stage 4: identify and cluster entities
clause_to_synapse.py         Stage 7: build synapses from clauses
framing.py                   Stage 9: attach rhetorical/POV/modality frames
synapse_grouper.py           Stage 11: cluster synapses into groups
synapse_store.py             Stage 10: SQLite schema and writer
compile_document.py          Top-level orchestrator (runs all stages)
beethoven.txt                Sample document (full biography)
dep_to_role.json             spaCy dependency -> closed 15-role mapping
pos_rosetta.json             spaCy POS -> SGF pos_simple mapping
reporting_verbs.txt          Verbs that trigger attribution-based POV
LIMITATIONS.md               The 12 disambiguation rules + enforcement tiers
README.md                    This file
glean_info_bundle.md         Architecture document (thesis, claim chain, FAQ)
```

## Install

```
pip install spacy huggingface_hub tokenizers onnxruntime-directml numpy
python -m spacy download en_core_web_sm
```

(Replace `onnxruntime-directml` with `onnxruntime-gpu` for NVIDIA or
plain `onnxruntime` for CPU-only.)

If you also want the small spaCy model swapped for a larger one for
better NER, edit `[spacy].model` in `sgf.toml` and:

```
python -m spacy download en_core_web_lg
```

## Configure

Edit `sgf.toml`. The defaults assume:

- Lexicon DB at `D:/lexicon/sgf_lexicon.db`
- Synapse store at `D:/lexicon/synapses.db`
- Default embedder `bge-large-en-v1`
- Local LLM endpoint at `http://localhost:8080/v1/chat/completions`

Move the lexicon to another drive: change one path. Switch embedders:
change one string.

## Sanity-check the config first

```
python sgf_cli.py check-config
python sgf_cli.py status
```

`check-config` validates the toml structure. `status` opens the lexicon
and reports row counts by embedding method.

## Quick one-target lookup

```
python sgf_cli.py lookup Beethoven --context "Beethoven moved to Vienna in 1792."
python sgf_cli.py lookup bank --context "We deposited money at the bank."
python sgf_cli.py lookup bank --context "We sat on the bank under the willow."
python sgf_cli.py lookup car --pos noun --context "Tom's car was red."
```

Add `--json` for machine-readable output. Add `--no-llm` to disable the
step-3 LLM rerank if you don't have a local LLM running yet.

## End-to-end compile

```
python compile_document.py --input beethoven.txt --doc-id beethoven_001
```

This runs every stage in order:

1. `entity_census` -> `beethoven_001.entity_map.json`
2. `clause_to_synapse` -> `beethoven_001.synapses.json`
3. `framing` -> `beethoven_001.synapses_framed.json`
4. `synapse_grouper` -> `beethoven_001.groups.json`
5. `persist` -> rows in `D:/lexicon/synapses.db`

Add `--framing-mode llm` to invoke the LLM for richer frames. Default is
deterministic (no LLM call, faster).

Add `--no-persist` to skip the final DB write (useful during debugging).

Add `--verbose` for more output.

Add `--workdir D:/test1/work` to control where intermediate JSONs land.

## Inspect the synapse store

```
python synapse_store.py status
```

Or open the DB directly:

```
sqlite3 D:/lexicon/synapses.db
sqlite> SELECT preferred_canonical, lexicon_canonical_id, lookup_decision_level
        FROM entity WHERE doc_id='beethoven_001';
sqlite> SELECT predicate_surface, polarity, statement_type FROM synapse
        WHERE doc_id='beethoven_001';
sqlite> SELECT s.predicate_surface, sp.role, sp.target_surface
        FROM synapse s JOIN synapse_spoke sp USING (synapse_id)
        WHERE doc_id='beethoven_001' ORDER BY synapse_id, spoke_index;
```

## Per-stage debugging

Each stage is a standalone script. You can re-run any stage in isolation:

```
python entity_census.py --input beethoven.txt \
                        --output work/em.json --doc-id beethoven_001 --verbose

python clause_to_synapse.py --input beethoven.txt \
                            --entity-map work/em.json \
                            --output work/syn.json --doc-id beethoven_001

python framing.py --synapses work/syn.json --source beethoven.txt \
                  --output work/framed.json --mode deterministic

python synapse_grouper.py --synapses work/framed.json \
                          --output work/groups.json
```

## Design principles

- Deterministic-first. The LLM is a refiner, not a generator.
- Standalone scripts. Each stage is testable in isolation.
- Config-driven. No hardcoded paths.
- Embedder loaded once. Module-level singleton in `sgflib.get_embedder`.
- MDKV for LLM output. Not JSON. LLMs produce MDKV reliably.
- Provenance everywhere. Every synapse stores source_doc_id, source
  clause_id, source span. Audit trail is the default.
- Closed grammar. The 15 semantic roles are imported from
  `sgflib.ROLES`. Synapse-store INSERTs that use any other role are
  rejected at write time.

## Known v1 limitations

- English only. Multilingual is v2 (BGE-M3 added as another embedding method).
- Pronoun resolution is proximity-based. Long-range coreference can be wrong.
- Sarcasm and irony detection require LLM mode. Deterministic mode assumes
  straight rhetorical mode for all synapses.
- The 41-dimension verb-feature space is stubbed; v1 emits only the
  basic 6 (tense, aspect, mood, voice, polarity, modality).
- Cross-document entity resolution does not run during compile. Each
  document gets its own micro-lexicon. Reconciliation across docs is
  a separate downstream stage.
- The Coverage Gate is read from config but not enforced in v1.
- Negation detection catches `neg` dependency children of the verb ("did
  not move") but misses determiner-scope negation ("no surviving letter
  confirms"). LLM framing mode catches both. Deterministic mode catches
  only the first kind.
- Quality of NER and alias clustering depends on the spaCy model. The
  default `en_core_web_sm` is fast but mediocre on uncommon names. For
  better entity extraction, install `en_core_web_lg` and update
  `[spacy].model` in `sgf.toml`.

## Next steps

After v1 is stable, the natural extensions are:

- Cross-document entity reconciliation (run after multiple docs compiled)
- Query layer (SPARQL-like or Cypher-like over the synapse store)
- Reasoning engine (rule-based inference over groups)
- Multilingual via BGE-M3
- Federation across SGF systems via the Stranger Rule

See `glean_info_bundle.md` for the architectural rationale.
