\# CLAIMS — Record-Separated Key-Value Format



\*\*Understanding RSKV as a structured transcript format\*\*  

Version 1.0 — June 2026



\*\*\*



\## 1. Purpose



This document states the load-bearing claims behind RSKV.



It is not the syntax specification. It is the companion argument: why the format exists, what problem it solves, what assumptions it makes, and which claims are proven by the design versus which claims require empirical validation.



RSKV should be understood as a \*\*structured transcript format\*\* for LLM-mediated data exchange. It is not a universal serialization language.



\*\*\*



\## 2. Root Thesis



\*\*RSKV is a structured transcript format for LLM-mediated data exchange: it addresses the structured-output problem by prioritizing local line-by-line repetition over global syntax state.\*\*



LLM-oriented data exchange needs a format that is easy for models to generate, easy for humans to inspect, and easy for small programs to parse. RSKV provides a flat, line-oriented, record-separated key-value middle layer that is easier for LLMs to emit than heavily nested formats, more expressive than CSV for sparse multi-set data, and intentionally boring to parse.



The core wager is simple:



> If the structure is visible line by line, then the LLM, the human reader, and the parser can all follow the same document model.



\*\*\*



\## 3. Non-Universal Scope



RSKV does not claim to replace JSON, YAML, CSV, Protocol Buffers, Avro, Parquet, or relational databases.



It is designed for the zone where those formats become inconvenient:



\- LLM-generated structured output

\- Sparse records

\- Multi-set documents

\- Human-reviewable intermediate data

\- Prompt/context exchange

\- Script-friendly data extraction

\- Log-like structured output

\- Lightweight ETL handoff

\- Debuggable model-to-application payloads



RSKV is strongest when the data is shaped like named collections of records. It is weakest when the data requires deeply nested object graphs, compact binary encoding, dense analytics storage, or schema-first service contracts.



\*\*\*



\## 4. Primary Claims



| ID | Claim | Category | Evidentiary Status |

|---|---|---|---|

| T1 | RSKV reduces common LLM structured-output syntax failures without requiring constrained decoding. | Reliability | Design-inferred; benchmark-recommended |

| T2 | RSKV supports streaming record parsing with memory bounded by current parser state and current record. | Performance | Proven by design |

| T3 | RSKV supports sparse, variable-schema records without requiring null padding or fixed rectangular schemas. | Flexibility | Proven by data model |

| T4 | RSKV is readable, diffable, grep-able, and editable with ordinary text tools. | Usability | Proven by line orientation |

| T5 | RSKV is transport-friendly because it uses UTF-8 text, visible delimiters, normalized line handling, and a small printable escape set. | Transport Safety | Mostly proven by encoding rules |

| T6 | RSKV allows progressive rigor: users can start with simple records and later add schemas, metadata, validation, extensions, and stricter parser modes. | Evolvability | Proven by conformance model |

| T7 | RSKV is intentionally non-nested at the core, using flattening, multiple sets, references, or typed JSON fields when hierarchy is needed. | Design Constraint | Proven by scope |



\*\*\*



\## 5. Claim Chain



The argument for RSKV is a dependency chain.



```text

ROOT THESIS

RSKV solves a practical LLM structured-output problem by making structure

visible as local, repeated text patterns.



│

├── T1 Reliability

│   LLMs are better at repeating local line patterns than maintaining

│   global syntax state across nested structures.

│

├── T2 Performance

│   Because structure is line-oriented and boundaries are visible,

│   parsers can classify one line at a time and emit records incrementally.

│

├── T3 Flexibility

│   Because records are independent key-value maps, the format can carry

│   sparse and variable records without forcing a dense table shape.

│

├── T4 Usability

│   Because cells and boundaries are visible as ordinary lines, humans

│   can read, diff, grep, edit, and review the same structure the parser sees.

│

├── T5 Transport Safety

│   Because the format uses UTF-8 text, line normalization, and a small

│   escape set, it is predictable in logs, files, prompts, and wrappers.

│

├── T6 Evolvability

│   Because schema, metadata, validation, and extensions are optional,

│   the format can begin lightweight and become stricter over time.

│

└── T7 Design Constraint

&#x20;   Because nesting is excluded from the core, RSKV remains simple,

&#x20;   streamable, and LLM-friendly; hierarchy is handled by convention

&#x20;   or typed fields rather than by the core grammar.

```



\*\*\*



\## 6. T1 — Reliability



\### Claim



RSKV reduces common LLM structured-output syntax failures without requiring constrained decoding.



\### Rationale



LLMs often perform better when asked to emit repeated local patterns than when asked to maintain global syntax state. RSKV exploits that tendency by making the basic unit of generation a single line:



```text

key: value

```



The model does not need to manage nested braces, commas, quote balancing, indentation, or trailing separators. It mostly needs to repeat field lines and insert explicit row or set boundaries.



\### Supporting Claims



| ID | Supporting Claim | Status |

|---|---|---|

| T1.1 | A cell is one local syntactic unit: `key: value`. | Spec-defined |

| T1.2 | A record boundary is explicit: `---ROW---`. | Spec-defined |

| T1.3 | A set boundary is explicit: `#SET:` and optionally `#ENDSET`. | Spec-defined |

| T1.4 | RSKV has no quotes, no comma separators, no indentation significance, and no required nested structure. | Spec-defined |

| T1.5 | The escape system is small and deterministic. | Spec-defined |

| T1.6 | Precise first-pass LLM validity rates require benchmark evidence across models, prompts, data shapes, and output sizes. | Benchmark-needed |



\### Boundary



RSKV does not prove that every LLM will always generate valid output. The defensible claim is that RSKV removes many common structural failure modes from the output language.



\*\*\*



\## 7. T2 — Performance



\### Claim



RSKV supports streaming record parsing with memory bounded by current parser state and current record.



\### Rationale



An RSKV parser does not need to build a complete document tree before producing useful output. It reads one line, classifies it, updates state, and flushes records at visible boundaries.



The core loop is conceptually:



```text

read line

classify line

update state

accumulate cell or flush record

repeat

```



\### Supporting Claims



| ID | Supporting Claim | Status |

|---|---|---|

| T2.1 | Line classification can be performed one line at a time. | Spec-defined |

| T2.2 | The parser state can be modeled as outside set, inside header, or inside records. | Spec-defined |

| T2.3 | `---ROW---` flushes the current record when one exists. | Spec-defined |

| T2.4 | `#SET:`, `#ENDSET`, and EOF provide set-level closure events. | Spec-defined |

| T2.5 | Implementations can yield records incrementally instead of buffering the whole document. | Design-inferred |

| T2.6 | Indefinite streams of complete records are possible, though final document-level validation may still require EOF or explicit closure. | Design-inferred |



\### Boundary



RSKV is streamable by structure, but a particular implementation can still choose to buffer sets or whole documents for convenience.



\*\*\*



\## 8. T3 — Flexibility



\### Claim



RSKV supports sparse, variable-schema records without requiring null padding or fixed rectangular schemas.



\### Rationale



An RSKV record is an independent map of keys to values. Records in the same set may share a common shape, but they are not required to.



This makes RSKV suitable for data that evolves, such as event streams, extracted entities, LLM tool outputs, logs, partial records, and mixed observations.



\### Supporting Claims



| ID | Supporting Claim | Status |

|---|---|---|

| T3.1 | A record is a collection of key-value cells. | Spec-defined |

| T3.2 | Schema is optional and advisory. | Spec-defined |

| T3.3 | Records may omit schema keys. | Spec-defined |

| T3.4 | Records may contain extra keys. | Spec-defined |

| T3.5 | Empty string, explicit null, and missing key are distinct states. | Spec-defined |

| T3.6 | Schema key order can provide canonical column order for tabular export. | Spec-defined |



\### Three-Value Logic



RSKV preserves three states that are often collapsed by weaker interchange conventions:



```text

key:        → present with empty string

key: \\N     → present with explicit null

missing key → absent / undefined

```



This matters for ETL, database loading, validation, audit trails, and semantic interpretation.



\*\*\*



\## 9. T4 — Usability



\### Claim



RSKV is readable, diffable, grep-able, and editable with ordinary text tools.



\### Rationale



RSKV exposes structure directly in the document text. A person can read the same units the parser reads: sets, records, and cells.



A record is not hidden inside braces or indentation. It is a contiguous group of lines.



\### Supporting Claims



| ID | Supporting Claim | Status |

|---|---|---|

| T4.1 | One field per line makes changes easy to see in diffs. | Design-inferred |

| T4.2 | `#SET:` makes document sections easy to scan. | Spec-defined |

| T4.3 | `---ROW---` makes record boundaries visible. | Spec-defined |

| T4.4 | Field names can be searched with ordinary text tools. | Design-inferred |

| T4.5 | The absence of indentation significance reduces copy/paste fragility. | Design-inferred |

| T4.6 | The absence of quotes reduces manual escaping overhead. | Design-inferred |



\### Boundary



Human-readable does not mean self-validating. Production consumers still need parsers, validators, limits, and security checks.



\*\*\*



\## 10. T5 — Transport Safety



\### Claim



RSKV is transport-friendly because it uses UTF-8 text, visible delimiters, normalized line handling, and a small printable escape set.



\### Rationale



RSKV is designed to survive ordinary text-handling environments: files, logs, terminals, prompts, email bodies, CLI pipes, and JSON wrappers. It avoids binary framing and forbids raw line breaks inside values.



\### Supporting Claims



| ID | Supporting Claim | Status |

|---|---|---|

| T5.1 | RSKV documents are UTF-8 text. | Spec-defined |

| T5.2 | LF is canonical, while CRLF is tolerated and normalized. | Spec-defined |

| T5.3 | Raw LF and CR are forbidden inside values. | Spec-defined |

| T5.4 | Literal newlines inside values are represented with an escape. | Spec-defined |

| T5.5 | Literal backslashes are represented with an escape. | Spec-defined |

| T5.6 | Explicit null is represented with `\\N`. | Spec-defined |

| T5.7 | Literal `#` at the start of a value and literal `---ROW---` can be escaped. | Spec-defined |

| T5.8 | RSKV can be carried inside JSON strings predictably, though normal JSON string escaping still applies. | Design-inferred |



\### Boundary



Transport-friendly does not mean transport-magical. If RSKV is placed inside another format, that outer format’s escaping rules still apply.



\*\*\*



\## 11. T6 — Evolvability



\### Claim



RSKV allows progressive rigor: users can start with simple records and later add schemas, metadata, validation, extensions, and stricter parser modes.



\### Rationale



LLM workflows often begin as prototypes and mature into production pipelines. RSKV supports that path by keeping the core format small while allowing optional structure around it.



A minimal RSKV document can contain only sets, records, and cells. A richer document can include schema, metadata, conformance levels, extension directives, validation rules, and implementation limits.



\### Supporting Claims



| ID | Supporting Claim | Status |

|---|---|---|

| T6.1 | Core RSKV requires only set headers, record separators, cells, escapes, and null handling. | Spec-defined |

| T6.2 | `#SCHEMA:` adds type hints and canonical column order. | Spec-defined |

| T6.3 | `#META:` adds provenance and operational context. | Spec-defined |

| T6.4 | Strict, permissive, and lax modes support different validation postures. | Spec-defined |

| T6.5 | Unknown extensions can be ignored in permissive mode or rejected in strict mode. | Spec-defined |

| T6.6 | Conformance levels let implementations declare supported features. | Spec-defined |



\### Boundary



Schema is advisory by default. If an application requires hard schema enforcement, that enforcement belongs to the consuming system or a strict validation profile.



\*\*\*



\## 12. T7 — Design Constraint



\### Claim



RSKV is intentionally non-nested at the core.



\### Rationale



The lack of nesting is not an omission. It is a simplifying constraint that protects RSKV’s main advantages: predictable generation, streamability, readability, and parser simplicity.



When hierarchy is necessary, RSKV favors one of four approaches:



\- Flatten the structure into fields.

\- Split related entities into multiple sets.

\- Use reference keys between sets.

\- Place structured payloads inside a typed `json` field.



\### Supporting Claims



| ID | Supporting Claim | Status |

|---|---|---|

| T7.1 | Core RSKV records are flat key-value maps. | Spec-defined |

| T7.2 | Multiple sets can represent related entity collections. | Spec-defined |

| T7.3 | JSON fields can carry nested structures when needed. | Spec-defined |

| T7.4 | Avoiding core nesting keeps the parser simple and stream-oriented. | Design-inferred |



\### Boundary



If the primary data model is a deep object graph, JSON, XML, Protocol Buffers, or another hierarchical format may be more appropriate.



\*\*\*



\## 13. Counterclaims



| Counterclaim | Rebuttal |

|---|---|

| JSON with constrained decoding can solve structured output more rigorously. | Constrained decoding is valuable when available. RSKV solves a different problem: improving unconstrained or lightly constrained text generation while remaining simple to inspect, stream, and parse. The two approaches can also be combined. |

| CSV is simpler for dense tables. | Correct. CSV is often better for dense rectangular data. RSKV is better when data is sparse, multi-set, metadata-bearing, null-sensitive, or generated by LLMs. |

| YAML is human-readable too. | YAML is readable, but significant whitespace, implicit typing, and indentation-sensitive structure can make generated output harder to validate and recover. RSKV avoids indentation semantics entirely. |

| Protocol Buffers, Avro, and Parquet are faster or smaller. | Correct for many production data systems. RSKV is text-first and optimized for LLM I/O, debugging, prompt exchange, lightweight ETL, and human review. |

| Lack of nesting is a limitation. | Yes, intentionally. RSKV keeps the core grammar flat and handles hierarchy through flattening, multiple sets, references, or typed JSON fields. |

| A new format creates adoption burden. | True. RSKV should be positioned as a lightweight convention for LLM-mediated structured text, not as a universal replacement for established formats. |

| Plain key-value text already exists. | RSKV formalizes the missing parts: named sets, record boundaries, escaping, null semantics, schema hints, metadata, conformance levels, and parser behavior. |



\*\*\*



\## 14. Evidence Posture



RSKV’s claims fall into three classes.



| Class | Meaning | Examples |

|---|---|---|

| Spec-defined | The claim follows directly from the syntax or normative parser behavior. | `#SET:` begins a set; `---ROW---` separates records; `\\N` represents null. |

| Design-inferred | The claim is a reasonable consequence of the design but depends on implementation or usage context. | Grep-ability, diff-friendliness, practical parser simplicity, JSON-wrapper predictability. |

| Benchmark-needed | The claim requires empirical testing across models, prompts, datasets, and output lengths. | Exact LLM syntax-error rates, first-pass validity percentages, latency comparisons, constrained decoding comparisons. |



The claims document should not present benchmark-needed claims as established facts. Strong empirical claims should be added only when backed by reproducible tests.



\*\*\*



\## 15. Validation Understanding



A reader understands RSKV if they can explain why these cases matter:



\- Empty string, explicit null, and missing key are distinct.

\- Cell parsing splits on the first `: ` only.

\- `---ROW---` separates records but does not create empty records by itself.

\- `#SET:` starts a new set and may implicitly close the previous one.

\- `#ENDSET` is optional.

\- `#SCHEMA:` is advisory and must appear before `#META:` when both are present.

\- `#META:` describes the current set.

\- Backslashes, newlines, nulls, leading hashes, and literal row separators require defined escapes.

\- Unknown extensions can be tolerated or rejected depending on parser mode.

\- Duplicate keys require defined behavior.

\- Unicode text is valid.

\- CRLF input should normalize to LF.

\- Strict mode and permissive mode serve different use cases.

\- RSKV data is not trusted merely because it is parseable.

\- Consumers must validate before database writes, HTML rendering, tool invocation, file writes, or privileged operations.



\*\*\*



\## 16. One-Page Mental Model



```text

DOCUMENT

├── SET: users                    ← #SET: users

│   ├── SCHEMA                    ← #SCHEMA: id:int, name:str

│   ├── META                      ← #META: source=hr

│   ├── RECORD 1                  ← implicit start

│   │   ├── id: 1

│   │   └── name: Alice

│   ├── ROW SEPARATOR             ← ---ROW---

│   ├── RECORD 2

│   │   ├── id: 2

│   │   └── name: Bob

│   └── END SET                   ← #ENDSET optional

│

└── SET: events                   ← #SET: events

&#x20;   ├── RECORD 1

&#x20;   │   ├── event: login

&#x20;   │   └── user\_id: 42

&#x20;   └── ...

```



The parser sees:



```text

Line → Classify → State Transition → Accumulate or Emit → Repeat

```



The LLM sees:



```text

Start Set → Emit Field Lines → Separate Records → Repeat

```



The human sees:



```text

Named Section → Records → Fields

```



All three views align because RSKV makes structure visible in the text itself.



\*\*\*



\## 17. Positioning Statement



RSKV is not “better than JSON” in general. It is better than JSON for a specific class of LLM-mediated structured text tasks where flat records, visible boundaries, sparse fields, streaming parse, and human review matter more than nested object expressiveness.



RSKV is not “better than CSV” in general. It is better than CSV when the data is not a single dense rectangular table.



RSKV is not “better than binary schema-first formats” in general. It is better when inspectability, copy/paste transport, prompt inclusion, and simple scripting matter more than compactness or maximum throughput.



The most accurate summary is:



> RSKV is a small, line-oriented, record-separated key-value format for reliable LLM-facing structured data exchange.



\*\*\*



\## 18. Final Claim



RSKV’s central architectural claim is this:



> \*\*Make the document structure visible as repeated lines, and the same representation becomes easier for LLMs to generate, easier for humans to review, and easier for parsers to stream.\*\*



That is the reason RSKV exists.

