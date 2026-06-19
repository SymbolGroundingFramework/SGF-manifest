\# RSKV: A Structured Transcript for the LLM Boundary



Every era of computing develops its own boundary formats.



The database era gave us rows and tables. The web era gave us JSON. The configuration era gave us YAML. The analytics era gave us columnar formats. The LLM era has a different boundary problem: we keep asking probabilistic text generators to emit deterministic structured data.



That is an awkward fit.



Large language models can explain concepts, summarize documents, extract fields, classify records, generate plans, and transform data. But the moment we ask them to return “valid JSON only,” we often shift the task from semantic reasoning to syntax maintenance. The model must not only know the answer; it must also balance braces, close arrays, escape quotes, place commas correctly, and preserve structure across a long generation.



RSKV — Record-Separated Key-Value — starts from a different premise.



Instead of forcing an LLM to behave like a compiler, RSKV formalizes a pattern language models already handle well:



```text

key: value

```



One line. One field. Repeat.



RSKV is not trying to be a universal serialization language. It is better understood as a structured transcript format for LLM-mediated data exchange: a flat, line-oriented middle layer that is easier for models to generate than deeply nested JSON, more expressive than CSV for sparse multi-record data, and intentionally boring to parse.



\## The structured output problem



The industry has mostly approached LLM structured output as a control problem.



If a model cannot reliably produce JSON, constrain the decoder. If it forgets a comma, compile a grammar. If it emits trailing commentary, wrap the call in retry logic. These techniques are useful, and in many production systems they are the right choice.



But they do not remove the underlying mismatch.



JSON is a tree format. YAML is indentation-sensitive. XML is verbose and nested. CSV is rectangular and quote-sensitive. These formats were not designed around the strengths and failure modes of language models. They were designed for browsers, configuration files, documents, databases, and data exchange between deterministic programs.



LLMs are different. They are strongest when producing local, repeated patterns. They are weaker when asked to maintain invisible global state over long spans of text.



RSKV leans into that asymmetry.



A minimal RSKV document looks like this:



```text

\#SET: users

id: 1

name: Alice

plan: pro

\---ROW---

id: 2

name: Bob

plan: free

```



There are only three things to notice:



```text

\#SET: users

```



starts a named collection.



```text

key: value

```



adds a field to the current record.



```text

\---ROW---

```



separates one record from the next.



That is the core model: sets, records, and cells.



\## A structured transcript



The phrase “structured transcript” matters.



A transcript is linear. It unfolds in order. You can stream it, read it, diff it, paste it into an issue, inspect it in a terminal, or recover from partial output. A structured transcript keeps those advantages while adding enough machine-readable shape to be useful.



RSKV documents are made of named sets. Each set contains records. Each record contains key-value cells.



```text

\#SET: tickets

\#SCHEMA: ticket\_id:int, status:str, summary:str

ticket\_id: 5001

status: open

summary: Billing page times out

\---ROW---

ticket\_id: 5002

status: closed

summary: Password reset completed

```



To a human, this looks like a plain text table written vertically.



To a parser, it is a simple state machine.



To an LLM, it is a pattern: emit field lines, separate rows, continue.



That alignment is the point. The human, the model, and the parser all see essentially the same structure.



\## Escaping without ceremony



Most serialization formats become complicated at the edges: quotes inside strings, newlines inside fields, nulls, delimiters inside values, embedded markup, encoding boundaries.



RSKV keeps the escape system deliberately small.



There are five core escapes:



```text

\\n          newline

\\\\          literal backslash

\\N          explicit null

\\#          literal # at the start of a value

\\---ROW---  literal row separator

```



There is no quoting mechanism. A value is just the text after the first colon-space delimiter:



```text

note: This value contains: several: colons

```



The parser splits on the first `: ` and preserves the rest.



That one rule eliminates a surprising amount of complexity. A model does not need to decide whether to quote a string. A human does not need to visually parse nested punctuation. A small script does not need a full JSON or YAML parser just to recover fields.



\## Null, empty, and missing



One of RSKV’s most important features is not syntactic. It is semantic.



Many ad hoc text formats collapse important distinctions. RSKV keeps three states separate:



```text

name:        empty string

name: \\N     explicit null

&#x20;            missing key

```



These are not the same thing.



An empty string may mean “the field was present, but blank.” A null may mean “the field was known to have no value.” A missing key may mean “the field was not observed, extracted, or applicable.”



That distinction matters in data pipelines. It matters when loading databases. It matters when evaluating extraction quality. It matters when a downstream system needs to know whether an LLM intentionally returned nothing or simply omitted a field.



CSV has difficulty expressing this cleanly. JSON can express it, but at the cost of object syntax. RSKV makes it visible in the line format itself.



\## Sparse records are normal



CSV assumes a rectangular table. Every row belongs to the same set of columns, even when most of those columns are empty.



LLM output often does not look like that.



Suppose a model is extracting events from text:



```text

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



These are all events, but they do not share the same fields. A login has an IP address. A purchase has an amount and currency. A logout has a duration.



RSKV treats that as normal.



A schema can be added when useful:



```text

\#SCHEMA: event:str, user\_id:int, amount:float, currency:str

```



But the schema is advisory by default. Consumers decide whether to enforce it, warn on deviations, preserve raw strings, or accept extra fields.



That is a practical stance for LLM systems. Early in a pipeline, flexibility is valuable. Later, validation may become necessary.



\## Streaming by design



RSKV is line-oriented, so it can be parsed line by line.



The parser does not need to hold an entire document in memory. It only needs to know the current set, the current record, and a small amount of header state.



Conceptually:



```text

read line

classify line

if #SET: start set

if key: value accumulate field

if ---ROW--- emit record

repeat

```



This gives RSKV a natural streaming shape. A parser can yield records as soon as it sees a row separator. A new `#SET:` can implicitly close the previous set. An optional `#ENDSET` can make closure explicit. EOF can flush the final record.



That makes the format useful for more than prompt responses. It can work in logs, command-line tools, extraction jobs, eval harnesses, batch transforms, and model-to-application pipes.



RSKV is not a columnar analytics format, and it should not pretend to be one. If the destination is DuckDB, Parquet, Postgres, or a warehouse, RSKV is better seen as a staging or interchange layer:



```text

LLM output

&#x20;   ↓

RSKV

&#x20;   ↓

validate and coerce

&#x20;   ↓

database / warehouse / parquet

```



That is a feature, not a failure. Boundary formats do not have to be final storage formats.



\## Progressive rigor



LLM workflows often begin as prompts and become pipelines.



At first, you might only need this:



```text

\#SET: contacts

name: Alice

email: alice@example.com

\---ROW---

name: Bob

email: bob@example.com

```



Later, you may want types:



```text

\#SCHEMA: name:str, email:str, active:bool

```



Then provenance:



```text

\#META: source=crm, version=3, batch=2026-06-19

```



Then validation policy:



```text

strict mode: reject duplicate keys

permissive mode: warn and keep going

lax mode: silently skip invalid lines

```



RSKV supports that progression. The core remains small, but disciplined systems can layer on schema, metadata, conformance levels, extensions, and validation suites.



This is important because LLM architectures tend to evolve. A format that is only good for quick demos fails when the workflow becomes operational. A format that requires a full schema registry on day one fails before the prototype even starts.



RSKV aims for the middle path.



\## What about nesting?



The obvious objection is that real data is nested.



That is true. RSKV’s answer is not to make nesting part of the core grammar. Its answer is to model hierarchy intentionally.



There are several options.



For occasional nested payloads, use a JSON field:



```text

\#SET: events

\#SCHEMA: id:int, event:str, payload:json

id: 1

event: purchase

payload: {"user":{"id":42},"items":\[{"sku":"A1","qty":2}]}

```



For shallow structures, flatten the keys:



```text

\#SET: customers

id: 1

name: Alice

address.city: Mobile

address.state: AL

```



For real object graphs, use multiple sets and references:



```text

\#SET: customers

customer\_id: 42

name: Alice



\#SET: orders

order\_id: 1001

customer\_id: 42

total: 29.99



\#SET: order\_items

order\_id: 1001

line\_no: 1

sku: A1

qty: 2

```



For knowledge graphs, use nodes and edges:



```text

\#SET: nodes

node\_id: n1

type: person

label: Alice

\---ROW---

node\_id: n2

type: company

label: Acme Corp



\#SET: edges

source: n1

predicate: works\_for

target: n2

```



In other words, RSKV does not deny hierarchy. It refuses to make inline hierarchy the default. That keeps the core grammar flat, streamable, and friendly to language models.



\## What about binary data?



RSKV is text-first, but it can carry binary payloads through base64 fields:



```text

\#SET: files

\#SCHEMA: id:int, name:str, media\_type:str, data:base64

id: 1

name: hello.txt

media\_type: text/plain

data: SGVsbG8sIFJTS1Yh

```



That checks the representational box. But base64 is not compact binary transport. For large files, a better pattern is to store a reference:



```text

\#SET: files

id: 1

name: training-video.mp4

uri: s3://bucket/videos/training-video.mp4

sha256: 9f86d081884c7d659a2feaa0c55ad015

size\_bytes: 482991204

```



RSKV can describe binary objects well. It should not be mistaken for an efficient binary container.



\## Transport safety



A practical LLM boundary format must survive the boring places where text travels: logs, terminals, CLI pipes, copied snippets, email bodies, JSON wrappers, and issue trackers.



RSKV is designed for that environment.



It uses UTF-8. It tolerates common line endings. It forbids raw line breaks inside values. It uses visible delimiters. Its escapes are printable. It has no magic bytes and no binary framing.



That does not mean outer formats disappear. If you put RSKV inside a JSON string, JSON’s escaping rules still apply. But RSKV’s own grammar is predictable, which makes wrapping and unwrapping easier to reason about.



Again, the goal is not cleverness. The goal is boring reliability.



\## Security is still your job



Parseable does not mean safe.



An RSKV document may contain SQL fragments, HTML, file paths, shell commands, JSON payloads, base64 blobs, or tool arguments. The format does not make any of those safe.



Consumers still need limits, validation, escaping, parameterized SQL, safe rendering, size caps, schema checks, and tool-call controls.



This is especially important at the LLM boundary. RSKV makes structured output easier to process. It does not turn untrusted text into trusted data.



\## Where RSKV fits



RSKV is strongest when you need structured output that is:



\- Generated by an LLM

\- Reviewed by a human

\- Parsed by a small program

\- Streamed line by line

\- Sparse or variable in shape

\- Split into multiple logical sets

\- Easy to paste into prompts, logs, or issues

\- Later loaded into a database or validation pipeline



It is not the best choice for every job.



Use JSON when the natural shape is a nested object tree and you already have robust JSON tooling.



Use CSV when the data is a simple dense table.



Use Parquet or a warehouse format for analytics storage.



Use Protocol Buffers or Avro when you need compact schema-first service contracts.



Use RSKV when the boundary itself is textual, iterative, inspectable, and LLM-facing.



\## The architectural claim



The central claim behind RSKV is simple:



> Make the document structure visible as repeated lines, and the same representation becomes easier for LLMs to generate, easier for humans to review, and easier for parsers to stream.



That is why RSKV exists.



It is not a grand theory of serialization. It is a small answer to a very common problem: getting useful structured data across the boundary between language models and software systems without making either side work harder than necessary.

