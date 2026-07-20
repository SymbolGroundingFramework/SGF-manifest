\# Synapedia Search Server



A standalone HTTP search server for the Synapedia lexicon. Loads the

lexicon's embedding matrix once at boot; every downstream tool

(Synapedia adapter, ad-hoc queries, custom integrations) talks to it

over HTTP and gets answers in tens of milliseconds.



This bundle is \*\*standalone\*\*. You do not need the full Synapedia Lexicon

Pipeline bundle to run it. You only need a built `synapedia.db` to

point it at.



\*\*License:\*\* Apache 2.0. Free to use, modify, redistribute, including

commercially. No attribution required (though appreciated).



\---



\## What you get



| File | Purpose |

|---|---|

| `search\_server.py` | FastAPI HTTP daemon (orchestration layer) |

| `syn\_search\_adapter.py` | Ontology‑aware semantic search client (v0.7.0) |

| `bm25\_score.py` | BM25 lexical scoring + cascade decisions |

| `reranker.py` | Cross‑encoder reranker (BGE rerankers, lightweight) |

| `lemma\_resolver.py` | Surface‑form‑to‑lemma resolution |

| `llm\_tiebreaker.py` | LLM‑of‑last‑resort tiebreaker |

| `llm\_kv\_parser.py` | Tolerant `<answer>` + KV parser |

| `llm\_wrapper.py` | Single‑file LLM caller (OpenRouter + Ollama) |

| `search\_config.toml` | The config file — edit this |



\---



\## Architecture — Three Matching Levels



The server implements a four‑stage cascade that is consumed by the

adapter's three‑level matching pipeline:



```

Client                        Server

──────                        ──────

syn\_search\_adapter.py  ───>  search\_server.py

&#x20;                                │

&#x20; L1. Cosine + Lemma/POS  <────  Stage 1. Cosine retrieval

&#x20;                                │

&#x20; L2. Ontology‑Slot       <────  Stage 2. Cross‑encoder reranker

&#x20;     Matching                    Stage 3. BM25 lexical scoring

&#x20;                                │

&#x20; L3. Ancestor            <────  Stage 4. LLM tiebreaker (opt‑in)

&#x20;     Propagation

```



Each server stage fires only when the prior stage's margin is tight.

The cheap path stays cheap when it is confident.



\### Deeper structural scoring (L2 / L3)



The adapter fetches hypernyms and parts via `/definition` and computes

a weighted structural overlap score:



```

HEAD       = 0.5  (core entity, with synonym expansion)

IS\_A       = 0.3  (hypernym / category match)

HAS\_PART   = 0.2  (part match)

MODIFIER   = bonus (capped at 0.1)

```



At L3, ancestor propagation walks the hypernym chain (up to 3

generations) to catch inherited structural matches.



\---



\## Quickstart



\### 1. Install dependencies



```bash

\# Core requirements

pip install fastapi uvicorn pydantic numpy tomli



\# For text search (ONNX embedding)

pip install onnxruntime tokenizers huggingface\_hub



\# For the search adapter

pip install requests

```



\### 2. Start the server



```bash

python search\_server.py --lexicon /path/to/synapedia.db

```



The server loads the lexicon and all embeddings into memory at boot.

Typical load time: \~10 seconds for 185K senses.



\### 3. Query via the adapter



```bash

\# Basic search (all three levels)

python syn\_search\_adapter.py "titanium torque driver"



\# L1 only (pure vector search)

python syn\_search\_adapter.py "titanium torque driver" --levels 1



\# With custom ancestor depth

python syn\_search\_adapter.py "steel wrench" --levels 3 --ancestor-depth 3

```



\### 4. Query directly via curl



```bash

\# Health check

curl http://localhost:8400/health



\# Text search

curl -X POST http://localhost:8400/search \\

&#x20; -H "Content-Type: application/json" \\

&#x20; -d '{"text": "river bank", "k": 5}'



\# Lemma lookup

curl -X POST http://localhost:8400/lookup/lemma \\

&#x20; -H "Content-Type: application/json" \\

&#x20; -d '{"lemma": "bank", "pos": "noun"}'



\# Canonical-ID lookup

curl -X POST http://localhost:8400/lookup/canonical \\

&#x20; -H "Content-Type: application/json" \\

&#x20; -d '{"canonical\_id": "en.bank.financial\_institution.noun.synapedia\_wordnet"}'



\# Full definition (with hypernyms + parts)

curl -X POST http://localhost:8400/definition \\

&#x20; -H "Content-Type: application/json" \\

&#x20; -d '{"canonical\_id": "en.bank.financial\_institution.noun.synapedia\_wordnet"}'

```



\---



\## Configuration



One file: `search\_config.toml`. It sits in the bundle directory next

to the Python files. Open it, edit values, save, restart the server.



\*\*Lookup order (server reads the first that exists):\*\*



1\. `--policy PATH` CLI flag

2\. Bundle directory (`search\_config.toml` next to the server)

3\. `\~/.glean/search\_config.toml`



\### Three sections



```toml

\[retrieval]

\# What the search engine returns and how it ranks.

\# Named policies: snap\_to\_standard, snap\_to\_neutral,

\#                 preserve\_register, research\_unfiltered

\# embedder cascade, audience tier, register/temporal filters.

default\_policy = "snap\_to\_standard"



\[search\_pipeline]

\# Server-side four-stage cascade (cosine, reranker, BM25, LLM).

\# Stages 2-4 are disabled by default; only cosine runs.

reranker.mode = "never"

bm25.mode = "never"

llm\_tiebreak.mode = "when\_tight"



\[client\_pipeline]

\# Mirror of \[search\_pipeline] for CLI use. Disabled by default.

```



Per-request overrides: send a `policy\_overrides` field in the JSON

body of any `/search` call. That is where per-call tweaks belong;

the TOML is for defaults.



\---



\## Embedding model



The server uses a single embedder: \*\*BGE-large-en-v1.5\*\* (Xenova ONNX

build, 1024 dimensions, CLS pooling + L2 normalization).



\- ONNX repo: `Xenova/bge-large-en-v1.5`

\- Tokenizer repo: `BAAI/bge-large-en-v1.5`

\- Vectors are stored as BLOB columns in `synapedia\_entry.embedding`

\- The same model is used at query time for embedding search strings



No fallback cascade is needed — this model covers 99%+ of the lexicon.



\---



\## Namespace awareness (definition tier preference)



The server applies authority‑based preference bonuses at query time.

When multiple sources define the same lemma+POS, the most authoritative

source appears first in results:



| Source | `definition\_tier` | Tier bonus |

|---|---|---|

| WordNet | `CORE\_ONTOLOGY` | +0.15 |

| Wikipedia | `CORE\_KNOWLEDGE` | +0.10 |

| Wiktionary | `LEXICAL\_EXTENSION` | +0.05 |

| Document claim | `CLAIMED` | 0.00 |

| Derived | `INFERRED` | -0.05 |

| LLM guess | `PROVISIONAL` | -0.10 |

| Unknown | `GHOST` | -0.20 |



Both WordNet and Wiktionary entries are retained in the database.

No deduplication occurs. The preference is applied at query time only.



\---



\## Endpoints



| Path | Method | Purpose |

|---|---|---|

| `/health` | GET | Server status, embedders, cascade, tier distribution |

| `/policies` | GET | List named policies and their settings |

| `/search` | POST | Embed query, cascade through stages, return results |

| `/batch\_search` | POST | Embed multiple queries at once, search each |

| `/lookup/lemma` | POST | All senses of a lemma |

| `/lookup/canonical` | POST | One sense by canonical\_id |

| `/definition` | POST | Full definition with hypernyms + parts |

| `/embed` | POST | Embed a query text (returns vector, no search) |

| `/reload` | POST | Reload lexicon from DB in background |



\---



\## Auth



\- Loopback bind (`127.0.0.1`, `localhost`): no auth.

\- Non-loopback bind (`0.0.0.0`, LAN IP): a 24-char base32 token is

&#x20; auto-generated to `\~/.glean/auth.toml` on first boot. Pass it via

&#x20; the `X-API-Key` header.



\---



\## LLM adapter



`llm\_wrapper.py` is a single-file LLM caller supporting both OpenRouter

(cloud) and Ollama (local). Edit the global settings at the top of the

file to set your API key and default model, then verify:



```bash

python llm\_wrapper.py --self-test

```



The adapter (`syn\_search\_adapter.py`) uses this wrapper for ontology

extraction and tiebreaking.



\---



\## Building the lexicon



This bundle does NOT include the lexicon-build pipeline. To build a

`synapedia.db` to point this server at, use the \*\*Synapedia Lexicon

Pipeline\*\* bundle (separate repository). That bundle ingests Wiktionary,

WordNet, and Wikipedia dumps and produces the database this server

consumes.



\---



\## Files in this bundle



```

search\_server.py              FastAPI orchestration daemon

syn\_search\_adapter.py         Ontology-aware search client (v0.7.0)

bm25\_score.py                 BM25 scoring + cascade decisions

reranker.py                   Cross-encoder reranker (lightweight)

lemma\_resolver.py             Surface-form-to-lemma resolution

llm\_tiebreaker.py             LLM-of-last-resort tiebreaker

llm\_kv\_parser.py              <answer>/<comments> envelope parser

llm\_wrapper.py                Single-file LLM caller

search\_config.toml            THE config file -- edit this

requirements.txt              Pinned-ish dependencies

README.md                     This file

LICENSE                       Apache 2.0

NOTICE                        Copyright + third-party model attributions

```

