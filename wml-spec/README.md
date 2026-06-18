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

Current AI-coding tools treat the model as the substrate: the model is 
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
[white_paper.md](white_paper.md)
[tech_specs.md](tech_specs.md)
[addendum.md](addendum.md)
[implementation_plan.md](implementation_plan.md)
[what-makes-wml-a-formal-language.md](what-makes-wml-a-formal-language.md)

## Part of SGF

WML is a sub-project of the **Symbol Grounding Framework (SGF)**, an 
architecture for grounded machine meaning at a different altitude — 
meaning representation, admissible wire protocols, and governance 
grammar. See [the umbrella repo](../) for the full SGF context. WML and 
SGF are sibling sub-projects: they share a commitment to structured, 
grounded computation, but they operate on different layers of the stack.


