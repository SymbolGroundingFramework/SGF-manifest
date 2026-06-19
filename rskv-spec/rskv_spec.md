

\# RSKV Specification  

\*\*Record-Separated Key-Value Format\*\*  

\*\*Version 1.0 — June 2026\*\*



\---



\## 1. Abstract



\*\*RSKV (Record-Separated Key-Value)\*\* is a lightweight, line-oriented text format for representing structured data as a collection of named \*\*sets\*\*, each containing a sequence of \*\*records\*\* composed of \*\*cells\*\* (key-value pairs).



RSKV is designed to be:



\- \*\*LLM-native\*\* — trivial for large language models to generate and consume with near-zero syntax errors

\- \*\*Human-readable\*\* — editable in any text editor, diff-able, grep-able, reviewable in code review

\- \*\*Parser-simple\*\* — implementable in 30–50 lines of code in any language, zero dependencies

\- \*\*Transport-safe\*\* — pure UTF-8, no control characters, survives JSON wrapping, logs, CLI pipes, email

\- \*\*Schema-flexible\*\* — sparse records, variable keys per row, optional typed schemas and metadata



RSKV fills the gap between \*\*CSV\*\* (single table, no types, quoting complexity) and \*\*JSON/XML/YAML\*\* (verbose, brittle LLM output, parsing overhead, significant whitespace).



\---



\## 2. Design Goals \& Non-Goals



\### 2.1 Goals



| Goal | Rationale |

|------|-----------|

| Reliable LLM generation | LLMs consistently emit `key: value` lines; fail at braces, quotes, indentation, commas |

| Streaming parse, O(1) memory | Line-by-line processing; no document buffering required |

| Multi-table native | Workbook-style documents without wrapper objects |

| Visible delimiters | `#SET:`, `---ROW---`, `#ENDSET` are grep-able and collision-resistant |

| Minimal escaping | Exactly 5 escape sequences; longest-first decode order eliminates ambiguity |

| Null ≠ empty ≠ missing | Three distinct states for data fidelity |



\### 2.2 Non-Goals



\- Nested/hierarchical structures (use `json` type or flatten)

\- Binary payloads (use `base64` type)

\- Schema enforcement (schema is advisory; consumers decide validation policy)

\- Replacement of CSV for dense columnar analytics (use MTSV/Parquet)

\- Replacement of JSON for complex object graphs



\---



\## 3. Data Model



| Concept | Description | Analogy |

|---------|-------------|---------|

| \*\*Document\*\* | Zero or more sets | Workbook / Database |

| \*\*Set\*\* | Named collection of records | Table / Sheet / Entity collection |

| \*\*Record\*\* | Unordered map of key → value | Row / Object / Entity |

| \*\*Cell\*\* | Single `key: value` line | Field / Column / Attribute |

| \*\*Schema\*\* | Optional `key:type` declarations | DDL / Type hints |

| \*\*Metadata\*\* | Optional set-level `key=value` pairs | Provenance / Lineage / Config |



\*\*Encoding:\*\* UTF-8 required. LF (0x0A) line endings; CRLF (0x0D 0x0A) tolerated and normalized.  

\*\*Forbidden unescaped in values:\*\* LF, CR.  

\*\*BOM:\*\* Optional UTF-8 BOM at document start; parsers may strip.



\---



\## 4. Document Structure



\### 4.1 Line Classification (Priority Order)



Every line matches exactly one category, tested in this order:



| Priority | Pattern | Category | Action |

|----------|---------|----------|--------|

| 1 | `^#SET:\\s\*(.+)$` | Set Header | Begin new set; capture name |

| 2 | `^#ENDSET$` | Set Terminator | Close current set (optional) |

| 3 | `^#SCHEMA:\\s\*(.+)$` | Schema Declaration | Parse schema for current set |

| 4 | `^#META:\\s\*(.+)$` | Metadata Declaration | Parse metadata for current set |

| 5 | `^---ROW---$` | Record Separator | Flush current record |

| 6 | `^.+?: .+$` | Cell | Split on first `: ` |

| 7 | `^#\[A-Z]+:\\s\*.\*$` | Extension Directive | Parse known / ignore unknown |

| 8 | `^\\s\*$` | Blank | Ignore |

| 9 | \*anything else\* | Invalid | Warn/skip (permissive) or error (strict) |



> \*\*Normative Rule:\*\* Cell parsing splits on the \*\*first occurrence of `: `\*\* (colon + space). Additional colons in the value are preserved. Lines starting with `#` containing `: ` are \*\*never\*\* cells.



\### 4.2 Set Lifecycle



```

\#SET: <name>          ← Set begins (name MUST be non-empty after trim)

\[#SCHEMA: ...]        ← Optional, must appear before any cell

\[#META: ...]          ← Optional, must appear after #SCHEMA if both present

\[#EXT: ...]           ← Optional extensions (after #META, before cells)

key1: value1          ← First record begins implicitly

key2: value2

\---ROW---             ← Record separator

key1: value3          ← Next record

...

\[---ROW---]           ← Trailing separator permitted, not required

\[#ENDSET]             ← Optional explicit close

\#SET: next\_name       ← Implicitly closes previous set

EOF                   ← Implicitly closes final set

```



\*\*Header Order Mandate:\*\* If both `#SCHEMA:` and `#META:` are present, they \*\*MUST\*\* appear in that order immediately after `#SET:` and before the first cell. Parsers in strict mode SHOULD reject misplaced header lines.



\*\*Duplicate Set Names:\*\* If a document contains multiple `#SET:` headers with the exact same name, parsers \*\*SHOULD\*\* treat subsequent occurrences as continuations (appends) to the existing set, preserving record order.



\### 4.3 Record Boundaries



\- First record starts after header block (no leading `---ROW---`)

\- Records separated by exactly one `---ROW---` line

\- Trailing `---ROW---` after last record: permitted, ignored

\- Empty set: zero records (valid)

\- Consecutive `---ROW---` with no cells between: no empty record created (ignored)



\---



\## 5. Cell Syntax



\### 5.1 Keys



\- \*\*Non-empty\*\*, case-sensitive strings

\- \*\*MUST NOT\*\* contain LF, CR, or the delimiter sequence `: `

\- Parsers \*\*MUST\*\* trim leading and trailing whitespace from the parsed key

\- \*\*SHOULD\*\* be unique per record; duplicate key behavior: last-write-wins (permissive), error (strict)

\- \*\*RECOMMENDED\*\* style: `lowercase\_with\_underscores` (ASCII letters, digits, underscore)

\- \*\*DISCOURAGED:\*\* Keys starting with `#` (visual confusion with directives). Parsers MUST accept them if followed by `: `.

\- Unicode permitted; portable schemas SHOULD restrict to ASCII



\### 5.2 Values



\- Arbitrary UTF-8 after escape decoding

\- \*\*Three distinct states:\*\*

&#x20; - `key: ` → empty string (`""`)

&#x20; - `key: \\N` → explicit null (absence of value)

&#x20; - Key absent from record → missing/undefined

\- The single space in `: ` is a delimiter, not part of the value. Subsequent spaces are preserved.

\- Additional colons, spaces, Unicode all permitted after first `: `



\---



\## 6. Escaping



Exactly five escape sequences. \*\*No others are defined.\*\*



| Encoded | Decoded | Purpose |

|---------|---------|---------|

| `\\n` | LF (0x0A) | Newline in value |

| `\\\\` | `\\` (0x5C) | Literal backslash |

| `\\N` | \*\*NULL\*\* | Explicit null sentinel |

| `\\#` | `#` (0x23) | Literal hash at line start |

| `\\---ROW---` | `---ROW---` | Literal record separator |



\### 6.1 Decode Order (Normative, Mandatory)



Implementations \*\*MUST\*\* apply in this exact sequence:



1\. \*\*Exact match `\\N`\*\* → null (special case: whole value is `\\N`)

2\. `\\---ROW---` → `---ROW---` (longest token first)

3\. `\\\\` → `\\`

4\. `\\n` → LF

5\. `\\#` → `#`



> \*\*Rationale:\*\* Longest-first prevents partial matches. Special-case `\\N` before backslash processing preserves null semantics.



\### 6.2 Generator Requirements



Generators \*\*MUST\*\* escape:

\- Every literal backslash → `\\\\`

\- Every literal LF → `\\n`

\- Explicit null → `\\N`

\- Literal `---ROW---` appearing as a value → `\\---ROW---`

\- Literal `#` at \*\*start of value\*\* (after `: `) → `\\#` (defensive; prevents misinterpretation if value lines are extracted)



Generators \*\*MUST NOT\*\* emit any quoting mechanism. RSKV has no quotes.



\### 6.3 Strict Mode Escaping



In \*\*strict mode\*\*, parsers \*\*MUST\*\* raise an error upon encountering an unknown escape sequence (e.g., `\\t`, `\\x`, `\\u`). In \*\*permissive mode\*\* (default), unknown sequences \*\*MUST\*\* be preserved literally.



\---



\## 7. Schema Declaration



\### 7.1 Syntax



```

\#SCHEMA: key1:type1, key2:type2, key3:type3

```



\- Comma-separated `key:type` pairs; optional spaces around commas

\- Keys SHOULD match record keys

\- Key order in schema \*\*IS\*\* the canonical column order for tabular export



\### 7.2 Standard Types



| Type | Encoding | Coercion Target |

|------|----------|-----------------|

| `str` | Unicode text | String |

| `int` | Decimal digits, optional sign | 64-bit signed integer |

| `float` | Decimal with optional exponent | IEEE 754 double |

| `bool` | `true` / `false` (lowercase) | Boolean |

| `date` | `YYYY-MM-DD` (ISO 8601) | Calendar date |

| `datetime` | `YYYY-MM-DDTHH:MM:SSZ` (ISO 8601 UTC) | Timestamp with timezone |

| `json` | JSON text as RSKV string value | Parsed JSON object/array |

| `base64` | RFC 4648 base64 text | Byte array |



\*\*JSON Serialization Rule:\*\* Generators \*\*MUST\*\* emit `json` values as a single-line string with escaped newlines (`\\n`). Multi-line JSON blocks violate the one-cell-per-line rule.



\### 7.3 Type Suffixes (Advisory)



Consumers MAY recognize suffixes after a colon in the type token:



| Suffix | Meaning | Example |

|--------|---------|---------|

| `:pk` | Primary key hint for DB loading | `id:int:pk` |

| `:idx` | Index hint | `email:str:idx` |

| `:tz` | Timezone-aware datetime | `ts:datetime:tz` |



\*\*Parsing rule:\*\* Base type = substring before first `:` in type token. Unknown suffixes ignored.



\### 7.4 Null \& Coercion Semantics



\- `\\N` decodes to \*\*null\*\* before any type coercion

\- Null \*\*MUST NOT\*\* be coerced to `false`, `0`, `""`, `{}`, `\[]` by default

\- Coercion failure: Preserve raw decoded string; emit validation warning/error per consumer policy

\- Schema is \*\*advisory\*\*; records may omit schema keys (→ null/absent) or include extra keys



\---



\## 8. Metadata Declaration



\### 8.1 Syntax



```

\#META: key1=value1, key2=value2, key3=value3

```



\- Comma-separated `key=value` pairs; optional spaces around commas

\- Values are plain text; no typing in core RSKV

\- If a metadata value requires commas or structure, use application convention (URL-encode, JSON, or separate set)



\### 8.2 Standard Metadata Keys (Reserved)



| Key | Purpose | Example |

|-----|---------|---------|

| `source` | Origin system | `hr`, `api-gateway`, `manual` |

| `version` | Schema/data version | `3`, `2026-06-19` |

| `batch` | Batch identifier | `2026-06-19-001` |

| `owner` | Responsible team/person | `data-eng`, `alice@example.com` |

| `created\_at` | ISO 8601 timestamp | `2026-06-19T13:09:00Z` |

| `checksum` | Content hash | `sha256:abc123...` |

| `encoding` | Value encoding hint | `base64`, `gzip+base64` |



\---



\## 9. Parsing Algorithm (Normative)



\### 9.1 State Machine



```

States: OUTSIDE\_SET, INSIDE\_SET(header), INSIDE\_SET(records)



OUTSIDE\_SET:

&#x20; #SET: name     → flush, enter INSIDE\_SET(header), init set

&#x20; #ENDSET        → ignore (orphan)

&#x20; other          → invalid line



INSIDE\_SET(header):

&#x20; #SET: name     → flush record, flush set, enter INSIDE\_SET(header) for new set

&#x20; #ENDSET        → flush record, flush set, enter OUTSIDE\_SET

&#x20; #SCHEMA: ...   → parse schema (error if after first cell)

&#x20; #META: ...     → parse meta (error if before #SCHEMA when both present)

&#x20; #EXT: ...      → extension line (ignore unknown in permissive)

&#x20; ---ROW---      → enter INSIDE\_SET(records), flush empty (ignored)

&#x20; key: value     → enter INSIDE\_SET(records), parse cell

&#x20; blank          → ignore



INSIDE\_SET(records):

&#x20; #SET: name     → flush record, flush set, enter INSIDE\_SET(header) for new set

&#x20; #ENDSET        → flush record, flush set, enter OUTSIDE\_SET

&#x20; ---ROW---      → flush record

&#x20; key: value     → parse cell, add to current record

&#x20; #EXT: ...      → extension/unknown (ignore in permissive)

&#x20; blank          → ignore



EOF:

&#x20; flush current record, flush current set

```



\### 9.2 Flush Operations



\- \*\*Flush record:\*\* If current record non-empty, append to current set's record list; clear record

\- \*\*Flush set:\*\* Finalize set in document map; clear set context



\### 9.3 Error Handling Modes



| Mode | Invalid Lines | Misplaced Headers | Coercion Failures | Duplicate Keys | Unknown Escapes |

|------|---------------|-------------------|-------------------|----------------|-----------------|

| \*\*Permissive\*\* (default) | Warn, skip | Warn, process | Warn, keep string | Last-write-wins | Preserve literal |

| \*\*Strict\*\* | Error | Error | Error | Error | Error |

| \*\*Lax\*\* | Silent skip | Silent ignore | Silent ignore | First-write-wins | Preserve literal |



\### 9.4 Heuristic Recovery (LLM Output)



If an LLM emits unescaped newlines in a value (breaking the single-line cell rule), subsequent lines will lack `: ` and be classified as Invalid. Permissive parsers \*\*SHOULD\*\* discard these orphan lines. Implementations \*\*MAY\*\* attempt heuristic recovery (e.g., indent continuation), but this is non-normative.



\---



\## 10. Conformance Levels



Implementations declare conformance level:



| Level | Required Features |

|-------|-------------------|

| \*\*Core\*\* | `#SET:`, `#ENDSET`, `---ROW---`, `key: value`, 5 escapes, null/empty/missing distinction |

| \*\*Core+Schema\*\* | Core + `#SCHEMA:`, type parsing, optional coercion, column order preservation |

| \*\*Core+Meta\*\* | Core+Schema + `#META:`, metadata parsing |

| \*\*Extended\*\* | Core+Meta + one or more extensions (`#INDEX:`, `#CONTINUE:`, `#ENCODE:`, `#COMPRESS:`, `#VALIDATE:`, `#PROVENANCE:`, `#ENCRYPT:`) |



\*\*Notation:\*\* `RSKV/1.0 Core+Schema`, `RSKV/1.0 Extended`



\---



\## 11. Extensions (Reserved)



Lines matching `^#(\[A-Z]+):` not in core are \*\*extensions\*\*. Placement: in header block after `#META:`, unless extension spec defines otherwise.



| Extension | Syntax | Purpose |

|-----------|--------|---------|

| `#INDEX:` | `#INDEX: key1,key2` | Consumer index hints |

| `#CONTINUE:` | `#CONTINUE: set\_name` | Append to existing set (streaming LLM output) |

| `#ENCODE:` | `#ENCODE: base64\\|gzip+base64` | Next record values encoded |

| `#COMPRESS:` | `#COMPRESS: gzip` | Entire following set compressed |

| `#VALIDATE:` | `#VALIDATE: schema\_url` | External schema reference |

| `#PROVENANCE:` | `#PROVENANCE: source\_id` | Audit trail |

| `#ENCRYPT:` | `#ENCRYPT: aes256` | Encrypted payload |



\*\*Unknown extensions:\*\* Ignore with warning (permissive) or error (strict).



\---



\## 12. LLM Integration Profiles



\### 12.1 LLM Output Profile (Model → System)



\*\*System Prompt Fragment:\*\*



```markdown

Output ONLY RSKV. No markdown, no commentary, no code fences.



Rules:

\- Start each table with: #SET: table\_name

\- One "key: value" per line (space after colon required)

\- Separate records with: ---ROW---

\- Include #SCHEMA: key:type,... when types are known

\- Include #META: key=val,... when provenance useful

\- Escape newlines as \\n, backslashes as \\\\, null as \\N

\- Escape literal # at value start as \\#, literal ---ROW--- as \\---ROW---

\- No quotes. No blank lines. Keys: snake\_case.

\- Multiple sets allowed.

```



\### 12.2 LLM Input Profile (System → Model)



\*\*Guidelines for RSKV as LLM Context:\*\*



\- Use distinct sets for distinct context types (`#SET: user`, `#SET: tickets`, `#SET: policy`)

\- Include `#SCHEMA:` when it aids interpretation

\- Keep records small enough for local attention

\- Place instructions \*\*outside\*\* RSKV unless RSKV is the full payload

\- Treat RSKV from untrusted sources as untrusted data



\---



\## 13. MIME Type \& File Identification



| Property | Value |

|----------|-------|

| \*\*File extension\*\* | `.rskv` |

| \*\*MIME type\*\* | `application/rskv` (provisional; IANA registration pending) |

| \*\*Content sniffing\*\* | First non-blank line matches `^#SET:` |

| \*\*Magic bytes\*\* | None (text format) |



\---



\## 14. ABNF Grammar (Normative)



```

rskv-doc       = \*( rskv-set )



rskv-set       = set-header \[ schema-line ] \[ meta-line ] \*( ext-line ) \*( record \[ row-sep ] ) \[ set-end ]



set-header     = "#SET:" SP set-name LF

set-name       = 1\*( %x21-7E / UTF8-2 / UTF8-3 / UTF8-4 )  ; printable non-LF, non-CR



set-end        = "#ENDSET" LF



schema-line    = "#SCHEMA:" SP schema-spec LF

schema-spec    = schema-field \*( "," \[SP] schema-field )

schema-field   = schema-key ":" schema-type

schema-key     = 1\*( key-char )

schema-type    = 1\*( ALPHA / DIGIT / "\_" / "-" / ":" )



meta-line      = "#META:" SP meta-spec LF

meta-spec      = meta-field \*( "," \[SP] meta-field )

meta-field     = meta-key "=" meta-value

meta-key       = 1\*( meta-key-char )

meta-key-char  = %x21-2B / %x2D-7E / UTF8-2 / UTF8-3 / UTF8-4  ; printable except ',', '='

meta-value     = \*( %x20-7E / UTF8-2 / UTF8-3 / UTF8-4 )



ext-line       = "#" token ":" \[SP] \*( %x20-7E / UTF8-2 / UTF8-3 / UTF8-4 ) LF



row-sep        = "---ROW---" LF



record         = \*( cell LF )

cell           = key ": " value



key            = 1\*( key-char )

key-char       = %x21-39 / %x3B-7E / UTF8-2 / UTF8-3 / UTF8-4  ; printable except ':', LF, CR



value          = \*( escaped / safe-char )

escaped        = "\\\\" ( "n" / "\\\\" / "N" / "#" / "-" "-" "R" "O" "W" "-" "-" "-" )

safe-char      = %x20-7E / UTF8-2 / UTF8-3 / UTF8-4  ; printable except backslash



token          = 1\*( ALPHA / DIGIT / "\_" / "-" )

SP             = %x20

LF             = %x0A

CR             = %x0D

```



> \*\*Note:\*\* The parser's normative rule is "split on first `: `". ABNF is descriptive; it does not override the split rule. Key whitespace trimming is a parser step post-split.



\---



\## 15. Validation Test Suite (Normative Requirements)



A conforming implementation \*\*MUST\*\* pass tests for:



| Category | Test Cases |

|----------|------------|

| \*\*Null semantics\*\* | `key: ` → `""`; `key: \\N` → null; missing key → absent |

| \*\*Escape decoding\*\* | `\\n`, `\\\\`, `\\N`, `\\#`, `\\---ROW---` in isolation and combination |

| \*\*Decode order\*\* | `\\\\n` → `\\n` (not LF); `\\---ROW---` before `\\\\` |

| \*\*Strict mode escapes\*\* | Unknown escape (`\\t`) → error (strict) / preserve (permissive) |

| \*\*Delimiter collision\*\* | Value containing `#SET:`, `---ROW---`, `: `, `# ` |

| \*\*Unicode\*\* | Keys/values with Unicode (émoji, CJK, RTL) |

| \*\*Line endings\*\* | LF, CRLF, mixed |

| \*\*Boundary conditions\*\* | Empty set, empty record, no trailing `---ROW---`, no `#ENDSET` |

| \*\*Header order\*\* | Valid order, reversed order (strict vs permissive), misplaced in records |

| \*\*Duplicate keys\*\* | Last-write-wins (permissive), error (strict) |

| \*\*Duplicate sets\*\* | Append behavior for repeated `#SET: name` |

| \*\*Schema coercion\*\* | Valid/invalid per type; null handling; suffix stripping |

| \*\*JSON type\*\* | Single-line escaped JSON; multi-line rejection |

| \*\*Sparse records\*\* | Omitted schema keys, extra keys |

| \*\*Extensions\*\* | Unknown `#EXT:` ignored (permissive) / error (strict) |

| \*\*BOM handling\*\* | UTF-8 BOM at start |

| \*\*Key trimming\*\* | ` key : value` → key=`key` |

| \*\*Limits\*\* | Max line length, max set/record counts enforced |



\---



\## 16. Security Considerations



\- \*\*RSKV is a serialization format, not a trust boundary.\*\*

\- Consumers \*\*MUST\*\* validate before: SQL execution (use parameters), HTML rendering, file writes, tool invocation, privileged operations

\- Implementations \*\*SHOULD\*\* enforce limits: max line length (default 64 KiB), max sets (1000), max records/set (1M), max key length (256), max decoded value length (1 MiB), max schema fields (1000)

\- Decoded `json`/`base64` fields: handle malformed payloads safely

\- No executable content in RSKV; but treat all free-form text as untrusted application data



\---



\## 17. Implementation Guidance (Non-Normative)



\### 17.1 Streaming Parser Pattern



```

for each line:

&#x20; classify line

&#x20; if SET\_HEADER: yield previous set, start new

&#x20; if ROW\_SEP: yield current record

&#x20; if CELL: accumulate in current record

&#x20; if EOF: yield final record and set

```

Yields `(set\_name, record\_dict)` tuples with O(1) memory.



\### 17.2 Database Load Pattern



```

parse → coerce\_types(schema) → validate(optional) → executemany(INSERT)

```

Map types: `int→INTEGER`, `float→REAL`, `bool→INTEGER(0/1)`, `date/datetime/json→TEXT`, `base64→BLOB`, `str→TEXT`.



\### 17.3 Round-Trip Fidelity



Generators SHOULD preserve:

\- Schema key order → column order

\- Record order → insertion order

\- Original string values when coercion fails

\- Null/empty/missing distinction



\---



\## 18. Comparison Summary



| Feature | RSKV | JSON | CSV | MTSV | YAML |

|---------|------|------|-----|------|------|

| Multi-table | ✅ | ✅ | ❌ | ✅ | ✅ |

| Sparse rows | ✅ | ✅ | ❌ | ❌ | ✅ |

| Types in-band | ✅ | ❌ | ❌ | ✅ | ❌ |

| Streaming parse | ✅ | ❌ | ✅ | ✅ | ❌ |

| LLM reliability | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |

| Human readable | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |

| Parser complexity | Trivial | Low | Low | Low | Medium |

| Diff-friendly | ✅ | ⚠️ | ✅ | ✅ | ⚠️ |

| Escape complexity | 5 rules | Complex | Hellish | Minimal | Indentation |



\*\*RSKV vs MTSV:\*\* Complementary. MTSV = wide, uniform, columnar, analytics. RSKV = sparse, variable, row-oriented, LLM I/O, entity data.



\---



\## 19. Examples



\### 19.1 Minimal



```

\#SET: colors

hex: #FF0000

name: Red

\---ROW---

hex: #00FF00

name: Green

```



\### 19.2 Full Features



```

\#SET: users

\#SCHEMA: id:int:pk, username:str, email:str, active:bool, created:datetime

\#META: source=hr,version=3,batch=2026-06-19

id: 1

username: alice

email: alice@example.com

active: true

created: 2026-01-15T09:30:00Z

\---ROW---

id: 2

username: bob

email: bob@example.com

active: \\N

created: 2026-02-20T14:00:00Z

\#ENDSET

```



\### 19.3 Sparse / Variable Schema



```

\#SET: events

event: login

user\_id: 42

ip: 192.168.1.5

\---ROW---

event: purchase

user\_id: 42

amount: 29.99

currency: USD

\---ROW---

event: logout

user\_id: 42

session\_duration\_sec: 900

```



\### 19.4 Escaping \& Complex Values



```

\#SET: articles

\#SCHEMA: id:int, title:str, body:str, tags:str

id: 1

title: RSKV Intro

body: Line 1\\nLine 2\\nPath: C:\\\\Users\\\\Alice

tags: spec,format,serialization

\---ROW---

id: 2

title: Edge Cases

body: A value with \\#SET: not a header.\\nAnd \\---ROW--- not a delimiter.

tags: escaping

```



\### 19.5 JSON \& Base64 Types



```

\#SET: events

\#SCHEMA: id:int, payload:json

id: 1

payload: {"action":"login","success":true}

\---ROW---



\#SET: files

\#SCHEMA: id:int, name:str, data:base64

id: 1

name: hello.txt

data: SGVsbG8sIFJTS1Yh

```



\### 19.6 LLM Input Context



```

\#SET: customer

\#SCHEMA: id:int, name:str, plan:str

id: 123

name: Acme Corp

plan: enterprise



\#SET: recent\_tickets

\#SCHEMA: ticket\_id:int, status:str, summary:str

ticket\_id: 5001

status: open

summary: Billing page times out

\---ROW---

ticket\_id: 5002

status: closed

summary: Password reset completed

```



\---



\## 20. Quick Reference Card



```

\#SET: table\_name              ← Start set (required)

\#SCHEMA: k1:t1, k2:t2         ← Optional schema (advisory types, column order)

\#META: k1=v1, k2=v2           ← Optional metadata (provenance)

\#INDEX: k1,k2                 ← Extension: index hints

key1: value1                  ← Cell (split on FIRST ": ")

key2: Line 1\\nLine 2          ← Escaped newline

key3: C:\\\\Path\\\\File          ← Escaped backslash

key4: \\N                      ← Explicit NULL

key5:                         ← Empty string

\\#SET: not a header           ← Escaped literal #

\\---ROW---                    ← Escaped literal delimiter

\---ROW---                     ← Record separator

\#ENDSET                       ← Optional set terminator

\#SET: next\_table              ← Next set (implicit close previous)

```



\*\*Core Rules:\*\*

1\. One `key: value` per line

2\. Split on first `: ` only

3\. `#SCHEMA` before `#META` if both present

4\. `\\N` = null, `key: ` = empty string, missing key = absent

5\. `#ENDSET` optional; `---ROW---` separates records

6\. Unknown `#EXT:` lines ignored (permissive)

7\. No quotes, no indentation significance, no nesting

8\. Keys trimmed; colons forbidden in keys



\---



\## 21. Versioning \& Evolution



\- \*\*Version format:\*\* `RSKV/MAJOR.MINOR` (this spec: `RSKV/1.0`)

\- \*\*Backward compatibility:\*\* Minor versions only add optional features; never break Core parsing

\- \*\*Extension mechanism:\*\* `#EXT:` lines for vendor/future features

\- \*\*Deprecation policy:\*\* Core features never removed; only elevated to higher conformance level



\---



\## 22. References



\- RFC 3629 — UTF-8

\- RFC 4648 — Base64

\- RFC 8259 — JSON

\- ISO 8601 — Date/time formats

\- PostgreSQL `COPY` format — `\\N` null convention

\- MTSV Specification — Complementary tabular format



\---



\## 23. Changelog



| Version | Date | Notes |

|---------|------|-------|

| 1.0 | 2026-06-19 | Initial standard release. Core syntax, escaping, schema, metadata, conformance levels, LLM profiles, ABNF, security, validation suite defined. |



\---



\*End of Specification — RSKV 1.0\*





