# WML — Workflow Map Language

*An engineering-grade grammar for declaring AI software workflows as maps.*

---

## The pitch

WML lets you declare AI software as a workflow map (the "what") instead 
of prompting an agent to generate it (the "how"). The map is the 
application; source code is a derived, ephemeral artifact.

A workflow map composes fifteen versioned primitives (`call_llm`, 
`read_file`, `loop`, `if`, `assert`, …) connected by frozen contracts. 
The runner executes the map deterministically. If the map parses and the 
primitives are wired correctly, the generation behavior follows from the 
grammar — not from the mood of the model.

## The argument in one page

Most AI-coding tools treat the model as the substrate: the model is 
asked to generate code, reason about code, and decide what to do next, 
all in free-form character space. This conflates model with 
infrastructure and produces three structural failure modes: 
nondeterministic memory, non-restartable execution, non-auditable 
reasoning.

WML inverts this. The model becomes *one* primitive (`call_llm`) among 
fifteen. Control flow lives in the map, not in prompts. Every action is 
versioned, timed out, and audited. The runner enforces the grammar, not 
hope.

## Where to start

Start here: [CLAIMS.md](CLAIMS.md) — the argument in 2 minutes

Read the article: [the-map-is-the-app.md](the-map-is-the-app.md)

See also:

[White Paper](white_paper.md)

[Technical Specifications](tech_specs.md)

[Addendum](addendum.md)

[implementation Plan](implementation_plan.md)

[What Makes WML a Formal Language](what-makes-wml-a-formal-language.md)


## Relationship to the Symbol Grounding Framework (SGF)

WML is one component of its broader parent project, the **Symbol Grounding Framework (SGF)**.  

SGF is a multi-layer architecture for grounded machine meaning. It defines:

1. **Core Lexicon** of sense-disambiguated concepts grounded in ~65 semantic primes
2. Synapses: hub-and-spoke event structures with 15 fixed semantic roles
3. **Wire protocol** – a versioned, machine‑to‑machine message format that lets services exchange grounded semantics without prior integration contracts.
4. HFF: a wire format for sealed, signed, provenance-tracked meaning
5. AFP: an act protocol (INFORM, QUERY, COMMAND, etc.) with receiver sovereignty
6. **Omega**: a formal governance grammar with 13 primitives and a deterministic Safety Kernel
7. **WML** is a workflow-map language for composing AI software from primitives.

See also:

[Main repo for SGF](https://github.com/SymbolGroundingFramework/SGF-manifest/tree/main)

[Formal RFC specification for SGF](https://github.com/SymbolGroundingFramework/SGF-manifest/tree/main/specs)


