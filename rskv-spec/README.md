# RSKV Specification

**Record-Separated Key-Value Format** — a lightweight, line-oriented format for LLM-mediated structured data exchange.

RSKV is a structured transcript format: easy for LLMs to generate, easy for humans to inspect, and easy for small programs to parse. It represents data as named sets, records, and `key: value` cells, using visible delimiters instead of braces, indentation, quoting, or nested syntax.

Repository folder: [rskv-spec](https://github.com/SymbolGroundingFramework/SGF-manifest/tree/main/rskv-spec)

## What is RSKV?

RSKV is designed for the boundary between language models and software systems.

A minimal RSKV document looks like this:

```text
#SET: users
#SCHEMA: id:int, name:str, plan:str
id: 1
name: Alice
plan: pro
---ROW---
id: 2
name: Bob
plan: free
```

The core model is simple:

- `#SET: name` starts a named collection.
- `key: value` adds a field to the current record.
- `---ROW---` separates records.
- `#SCHEMA:` optionally declares field types and column order.
- `#META:` optionally records provenance or operational metadata.
- `\N` represents explicit null.
- An empty value represents an empty string.
- A missing key represents an absent value.

## Why RSKV?

LLMs are often better at emitting repeated local patterns than maintaining global syntax state across deeply nested JSON, YAML, or XML.

RSKV leans into that strength. It avoids braces, commas, quotes, indentation semantics, and required nesting. The result is a format intended to be:

- LLM-friendly
- Human-readable
- Streamable
- Diffable
- Grep-able
- Parser-simple
- Schema-flexible
- Suitable for lightweight ETL and model-to-application handoff

RSKV is not intended to replace JSON, CSV, Parquet, Protocol Buffers, or databases. It is a text-first interchange format for sparse, reviewable, LLM-facing structured data.

## Repository contents

| File | Purpose |
|---|---|
| [`rskv_spec.md`](./rskv_spec.md) | Main RSKV 1.0 specification |
| [`claims.md`](./claims.md) | Claims document explaining the rationale, thesis, supporting claims, and design boundaries |
| [`essay.md`](./essay.md) | Medium-style essay introducing RSKV as a structured transcript format |
| [`rskv_to_sqlite.py`](./rskv_to_sqlite.py) | Utility for loading RSKV data into SQLite |
| [`sqlite_to_rskv.py`](./sqlite_to_rskv.py) | Utility for exporting SQLite data to RSKV |

## Quick primer for LLM output

Use this prompt fragment when asking an LLM to emit RSKV:

```text
Output only RSKV. Do not use Markdown, JSON, code fences, bullets, or commentary.

Start each collection with:
#SET: set_name

Write one field per line:
key: value

Separate records with:
---ROW---

Use #SCHEMA: after #SET: when field names and types are known.
Use #META: after #SCHEMA: only when provenance is useful.

Use \N for null.
Use an empty value after colon-space for an empty string.
Omit unknown or not-applicable fields.
Escape newlines as \n, backslashes as \\, a literal # at the start of a value as \#, and a literal ---ROW--- value as \---ROW---.
```

## Example

```text
#SET: people
#SCHEMA: id:int, name:str, role:str, notes:str
#META: source=example, version=1
id: 1
name: Alice
role: engineer
notes: Works on data pipelines
---ROW---
id: 2
name: Bob
role: analyst
notes: \N
```

## Python utilities

This folder includes two small Python utilities for SQLite interop.

### Convert RSKV to SQLite

```bash
python rskv_to_sqlite.py input.rskv output.db
```

### Convert SQLite to RSKV

```bash
python sqlite_to_rskv.py input.db output.rskv
```

Exact command-line options may vary depending on the script version. Run the scripts directly or inspect their argument handling for supported flags.

## Design boundaries

RSKV is strongest for:

- LLM-generated structured output
- Sparse records
- Multi-set documents
- Human-reviewable intermediate data
- Prompt and context exchange
- Lightweight ETL
- Logs and structured transcripts
- Database staging

RSKV is less natural for:

- Deep inline object graphs
- Compact binary transport
- Dense analytics storage
- High-throughput schema-first RPC contracts

Those cases can still be handled through conventions such as embedded `json` fields, `base64` fields, URI references, normalized sets, strict schemas, or downstream conversion to databases and columnar formats.

## Core concepts

### Sets

A set is a named collection of records.

```text
#SET: tickets
```

### Records

Records are separated by `---ROW---`.

```text
ticket_id: 1001
status: open
---ROW---
ticket_id: 1002
status: closed
```

### Cells

A cell is one `key: value` line. Parsers split on the first `: ` only.

```text
summary: User reported error: timeout after login
```

### Null, empty, missing

```text
name:        empty string
name: \N     explicit null
             missing key means absent
```

### Schema

Schemas are optional and advisory.

```text
#SCHEMA: id:int, name:str, active:bool, created_at:datetime
```

### Metadata

Metadata is optional and applies to the current set.

```text
#META: source=crm, version=2026-06-19, owner=data-eng
```

## Status

RSKV 1.0 is an initial specification draft intended for experimentation, review, and implementation.

The current collection includes:

- The formal specification
- A claims/rationale document
- An explanatory essay
- SQLite import/export utilities

## Suggested reading order

1. [`essay.md`](./essay.md) — start here for the motivation.
2. [`claims.md`](./claims.md) — read this for the design argument.
3. [`rskv_spec.md`](./rskv_spec.md) — read this for the normative format.
4. [`rskv_to_sqlite.py`](./rskv_to_sqlite.py) and [`sqlite_to_rskv.py`](./sqlite_to_rskv.py) — inspect these for practical interop.

## Relationship to the Symbol Grounding Framework (SGF)

RSKV is one component of the broader **Symbol Grounding Framework (SGF)** project.

SGF is a stack of languages, grammars, protocols, and tooling for grounded machine meaning:

1. **Core Lexicon** — sense-disambiguated concepts grounded in ~65 semantic primes.
2. **Synapses** — hub-and-spoke event structures with 15 fixed semantic roles for representing who did what to whom.
3. **HFF Wire Protocol** — a versioned, machine-to-machine message format that lets services exchange grounded semantics without prior integration contracts.
4. **AFP** — an act protocol (`INFORM`, `QUERY`, `COMMAND`, etc.) with receiver sovereignty.
5. **Omega** — a formal governance grammar with 13 primitives and a deterministic Safety Kernel.
6. **WML** — a workflow-map language for composing AI software from primitives.
7. **RSKV** — a lightweight record-separated key-value format for LLM-facing structured data exchange, prompt/output capture, structured transcripts, and simple ETL handoff.

Within SGF, RSKV is best understood as an **interchange and tooling format** rather than a semantic representation layer. It provides a simple, human-readable way to move structured records between LLMs, scripts, databases, examples, test fixtures, and documentation.

RSKV can be used to:

- Capture LLM outputs in a parseable text format.
- Store example records for SGF components.
- Exchange lightweight structured data between scripts.
- Convert records to and from SQLite.
- Represent test fixtures for workflows, protocols, and semantic transformations.
- Provide a readable staging format before data is converted into stricter SGF representations.

See also:

[Main repo for SGF](https://github.com/SymbolGroundingFramework/SGF-manifest/tree/main)

[Formal RFC specification for SGF](https://github.com/SymbolGroundingFramework/SGF-manifest/tree/main/specs)

## License

Add a license file before public reuse or distribution.

Suggested options:

- MIT for permissive software/spec reuse
- Apache-2.0 for permissive reuse with patent language
- CC-BY-4.0 for documentation-oriented reuse

## Author / Maintainer

Maintained as part of the Symbol Grounding Framework work.

Repository: [SymbolGroundingFramework/SGF-manifest](https://github.com/SymbolGroundingFramework/SGF-manifest)
