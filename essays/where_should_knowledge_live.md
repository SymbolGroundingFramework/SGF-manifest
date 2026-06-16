# Where Should Knowledge Live?
## A field map of AI storage substrates

There is an argument the AI field is currently incapable of having.

Every public conversation about AI's future treats one storage substrate as the answer and the others as obsolete. The LLM camp scales neural weights and treats symbolic AI as legacy. Yann LeCun walked away from Meta with a billion dollars to scale neural latents instead of weights, but kept the framing that one substrate will win. The vector-RAG industry pitches embeddings as the universal solvent. The semantic-web camp pitches RDF triples as sufficient. Each side argues the others have it wrong.

None of them is wrong about their substrate. All of them are wrong about the universal part.

Knowledge does not live in one place. Knowledge has heterogeneous storage needs, and the field's persistent search for the one substrate to rule them all is the architectural error that is keeping the conversation from making structural progress. The fix is not exotic. It is engineering hygiene applied to AI. Match substrate to job. Refuse to let any substrate reach outside its zone of competence. Accept that a serious system needs all of them in their proper lanes.

This essay walks through why.

## The hidden assumption

Five camps currently dominate the AI architectural conversation. Each is built on a different substrate, and each treats its substrate as the universal answer.

OpenAI, Anthropic, and Google scale neural weights. When they speak about AGI, the implicit story is that enough parameters trained on enough tokens will eventually produce systems that reason, know, and create. The story does not include a structured knowledge base. It does not include explicit world models. It includes weights, plus maybe some retrieval augmentation as a tactical patch.

Yann LeCun's new lab is built on the bet that LLMs are a dead end and JEPA-style latent prediction over physical-world video is the path forward. The substrate changes from token-predicting weights to latent-predicting weights, but the framing stays single-substrate. LeCun does not argue that JEPA should compose with symbolic systems. He argues that JEPA will eventually do everything important.

The vector database industry — Pinecone, Weaviate, Qdrant, the embedding-first knowledge layer of the modern AI stack — pitches embeddings as the universal way to store and retrieve knowledge. Their canonical example is RAG: chunk a document, embed each chunk, retrieve by similarity, hand to an LLM. The pitch is that this is sufficient for almost any knowledge task.

The symbolic AI camp — Wikidata, Cyc, custom RDF deployments, frame-based knowledge bases — treats triples and structured relations as the only substrate that can support trustworthy reasoning. They tend to dismiss neural substrates as fundamentally unauditable and therefore unsuitable for any application where being wrong has consequences.

Each camp publishes critique of the others. Read those critiques and a pattern jumps out: they all assume a single winning substrate exists to be found, and the disagreement is about which one. The hidden assumption is not just shared. It is the structure of the entire conversation.

That assumption is what this essay is going to challenge.

## The honest taxonomy

Five substrates are currently in play. Each has exactly one job it is natively good at. Outside that job, each has a sharp, structural failure mode.

**Neural weights** are native to fluent language continuation. They are the best technology humans have ever built for taking a prompt and producing prose that sounds right. They were never designed to store discrete verifiable facts, and they hallucinate consistently and confidently when asked to do so. The hallucination is not a bug that will be fixed by scaling. It is a property of the substrate. Weights store statistical patterns. A specific fact like "Beethoven was born in 1770" is not encoded anywhere as a retrievable item; it is smeared across billions of parameters as a high-probability token sequence. When that probability is high, the model gets it right. When the probability is low (a rare entity, an obscure date, a fact that appeared only a few times in training), the model invents something plausible. Both behaviors come from the same mechanism.

**Neural latents** (JEPA and its family) are native to predicting structure in continuous sensory streams. A JEPA-style model can watch a million hours of video and learn an internal representation that anticipates how objects move, fall, and interact. This is a real and important capability. It is also a different capability from symbolic knowledge storage. There is no place in JEPA's architecture where a discrete fact like "Beethoven was born in 1770" can live as an identifiable entity. The architecture cannot ingest the Wikipedia article on Beethoven and produce queryable facts. LeCun is explicit about this; he argues that symbolic knowledge is the wrong target and physical intelligence is the right one. He may be correct about his target. He cannot be correct that his target is the only target.

**Vector embeddings** are native to similarity and proximity. They are unmatched at finding the nearest neighbor of a query in a learned representation space. They cannot encode relationships between items beyond geometric closeness. The sentence "Beethoven taught Czerny who taught Liszt" embeds to a single point that captures the sentence's overall semantic shape and loses the predicate structure entirely. An embedding cannot answer "who did Liszt's teacher's teacher influence?" because the named roles — teacher, student, influence — have no representation in the vector. Embeddings are perfect at surfacing candidate matches. They are catastrophic when asked to decide what is true.

**Triples and synapses** (the symbolic substance layer — Wikidata, Cyc, RDF, frame KBs, and the Symbol Grounding Framework I'll mention at the end) are native to claim-bearing structures with provenance, semantic roles, temporal scope, and authority. Every claim is discrete. Every claim has a source. Every claim is editable, traceable, reversible. They are the only substrate that can answer "what is true, by whom, when, with what evidence?" They are also unwieldy as a user-facing surface; nobody wants to query a knowledge graph directly through SPARQL when they could ask a question in English.

**Raw prose** is native to human reading and bulk storage. It preserves maximum fidelity to the original source. It is programmatically opaque without translation into one of the other substrates. Every other substrate above is, in some sense, an attempt to make prose programmatically accessible without losing too much of what made the prose worth keeping.

### The Beethoven test

The cleanest way to see the substrates' differences is to give each one the same task and watch what happens.

Take the Wikipedia article on Beethoven. Try to encode it in each substrate.

The LLM substrate ingests the article into training and produces fluent continuations about Beethoven on demand. It can write a confident paragraph about his life. It cannot tell you which sentence in the article asserted his birth year. It cannot be updated when new scholarship revises a date — the only update path is retraining. It will confidently invent facts that were never in the article when prompted in the wrong way. The information is in there somewhere but it is not addressable.

The JEPA substrate cannot ingest the article at all. JEPA's input is video, not text. There is no architectural path for symbolic facts to enter JEPA's latent space. You could film someone reading the article aloud, and JEPA would learn embeddings that predict what visual frame comes next, not what fact follows from what.

The vector embedding substrate chunks the article into pieces and embeds each chunk as a point in similarity space. A query "when was Beethoven born?" embeds to a nearby region, retrieves the chunk most similar to the query, and hands the chunk to an LLM to author an answer. The vector decided what was relevant; the LLM decided what to say. No symbolic check intervened anywhere. The chain of reasoning is not auditable because there is no chain — just two opaque transforms and a paragraph at the end.

The synapse (or RDF triple) substrate parses the article into discrete claims. Beethoven HAS_BIRTH_DATE 1770-12-17. Beethoven HAS_BIRTH_PLACE Bonn. Beethoven HAS_OCCUPATION composer. Each claim carries its source paragraph, its confidence level, its temporal scope, and the relations that link it to other claims. You can ask "when was Beethoven born?" and get a specific answer with provenance. You can update the answer when new scholarship revises it without touching the rest. You cannot fluently render the result without help from another substrate.

The raw prose substrate stores the article as the article. Maximum fidelity, zero programmatic access.

Five substrates, one input, five fundamentally different outcomes. The substrates are not competing for the same job. They are solving different problems with the same input. The architectural error is pretending any one of them could solve all the problems.

## Why scale cannot fix this

The obvious objection at this point is that the failure modes I just named are temporary engineering gaps that will go away with enough scale. The hallucination problem has been getting better. JEPA is a new architecture and might evolve to handle more. Vector retrieval keeps improving.

The objection is wrong, and it is wrong for a specific reason. The failure modes are not engineering gaps. They are structural properties of the substrates themselves.

Hallucination has been the dominant LLM failure mode for five years through three orders of magnitude of parameter scaling. GPT-3 hallucinated, GPT-4 hallucinated, GPT-5 hallucinates. Each generation hallucinates less in the common case and continues to hallucinate fluently in the rare case. The pattern is not "scale eliminates hallucination." The pattern is "scale shifts hallucination to the long tail and makes it more confident-sounding." This is what you would expect from a substrate that stores statistical patterns rather than discrete facts. More patterns means better common-case behavior. Long-tail facts never get enough density to be stable.

Vector RAG's multi-hop reasoning weakness persists across embedding model generations because it is structural. A vector represents a single point. A multi-hop chain represents a sequence of typed relations. Improving the embedding model improves the quality of the single point. It cannot give the single point the structure of a chain. The improvement curve flattens at the structural ceiling.

JEPA's inability to encode symbolic facts is architectural in the strictest sense. There is no place in the JEPA architecture for a discrete fact to live. You could scale JEPA to a trillion parameters and you would still not be able to ask it "when was Beethoven born?" because the question does not map to any operation the architecture can perform. The substrate cannot answer questions it was not built to encode.

Knowledge graphs' weak user-facing surfaces have been a known problem since RDF was published in 1999. SPARQL queries do not feel like English. The structural rigidity that makes triples queryable and auditable is the same rigidity that makes them unreadable to humans without translation. Improving the query language helps at the margin; it does not change the substrate's structural mismatch with how humans communicate.

The pattern across all four cases is the same. Each substrate's data structure encodes a specific KIND of question. Data structures cannot encode questions they were not built for. Scale amplifies what a substrate already does well; it does not give a substrate capabilities its data structure cannot represent.

Rich Sutton's "bitter lesson" gets quoted at this point: hand-engineered structure always loses to scale, doesn't it? The bitter lesson is about hand-engineered KNOWLEDGE — features, ontologies, expert systems that try to encode domain expertise. It is not about hand-engineered ARCHITECTURE. The principle of matching substrate to job is architectural. It tells you where scale earns its keep (fluent continuation, similarity, physical prediction) and where it does not (truth, provenance, attribution, audit). Scale has had five years to produce trustworthy attribution at scale and has not. That is not a temporary gap; it is the structural ceiling of the neural substrate. The bitter lesson is fully compatible with substrate discipline. The discipline is what tells you where to spend the scale.

## The composition that works

If no single substrate can do all the jobs, the question becomes: how do they compose?

The answer turns out to be unsurprising. Each substrate gets the job it is good at. The layers stack. The composition routes around every substrate's structural ceiling by using a different substrate for the work that hits it.

The pattern, stated cleanly: vectors at the gateway, symbols at the substance layer, neural world models for sensorimotor prediction when the task requires it, LLMs as the rendering surface.

**Vectors at the gateway** handle the question "where in the system should this query be routed?" and the related question "what existing entry resembles this new one?" Embedding the user's question and retrieving the K nearest candidate concepts is what vectors do natively. The vector layer never decides truth. It decides what to look at next. The result is a small set of candidate hubs that the next layer can investigate.

**Symbols at the substance layer** handle the question "what is true, by whom, when, with what evidence?" This is where triples or synapses or frames do their work. Every claim is discrete, attributable, auditable, reversible. The symbolic layer is the authority on what is true in the system. Nothing beneath it can override its judgment.

**Neural world models** (JEPA-family, when the task is sensorimotor) handle the question "what physical state comes next?" These earn their place in the composition when the application involves reasoning about physical dynamics — robotics, autonomous vehicles, video understanding. For pure-knowledge applications, this layer is not needed.

**LLMs as the rendering surface** handle the question "how do I express these retrieved facts as prose a human wants to read?" The LLM receives a bundle of facts from the symbolic layer and transcribes them into natural language. It is forbidden, by architectural rule, to invent facts. If it has nothing to transcribe, it says so. The LLM is in its native lane — fluent generation from structured input — and is denied the lane (authoring truth) where it produces hallucination.

The composition has a property worth naming. In a typical RAG-plus-knowledge-graph-plus-LLM stack, the LLM is the final authority on what the answer says, and the knowledge graph is treated as enrichment that the LLM may use or ignore. The composition described here inverts that posture. The symbolic substance layer is the authority. The LLM transcribes. Vectors route. Each layer has explicit permission to do certain things and explicit prohibition against others. The architectural rules are the difference between a system that hallucinates less and a system that cannot hallucinate by construction.

This is not science fiction. Partial implementations exist. Shopify uses LSH-based fingerprinting plus product clustering plus Universal Product IDs internally — the gateway-plus-substance pattern at commercial scale. Academic projects are integrating symbolic constraints into JEPA latents (the RbJEPA and RiJEPA papers from earlier this year); the neural camp is starting to admit it needs symbolic grounding. The composition pattern is rare in public discourse and rarer in production, but it is not exotic. The engineering is straightforward. The discipline is what is hard.

## The architectural fallacy

The question this essay opened with deserves an answer. Why has the field not converged on composition, when composition so clearly addresses the failure modes of every substrate that participates in it?

The honest answer has two parts. The technical part: each camp's flagship demos succeed inside their substrate's zone of competence; the failures appear at the edges, where the substrate has been pushed outside its zone. From inside a camp, the failures look like engineering gaps that the next training run will fix. They never do, but they keep looking that way.

The institutional part is less flattering. The most-credentialed people in any field have a structural reason to defend the substrate their reputation was built on. LeCun built his career on neural architectures; his current bet stays neural even as it pivots from weights to latents. Sam Altman built his reputation on scaled weights; he cannot pivot to a composition story without ceding the narrative he sold investors. Demis Hassabis built DeepMind on reinforcement learning and game-playing; the substrate he scales is the one that brought him status. None of them are stupid. All of them are bound. The pattern of an obvious-in-retrospect architectural truth being denied by the most-credentialed people for institutional reasons is the most common pattern in the history of science.

The "AGI race" is framed as substrate-versus-substrate — neural versus symbolic, weights versus latents, generative versus retrieval. The actual progress would come from composition. The composition has almost no public champions because composition is not a substrate; it is a discipline. There is no camp to lead, no flagship demo to ship, no narrative to sell investors that doesn't involve picking a winner. The investment opportunity is asymmetric precisely because everyone is optimizing their part and nobody is optimizing the composition.

Knowledge has heterogeneous storage needs. No single substrate can answer every question about knowledge, because the questions themselves are structurally different. The pursuit of one universal substrate is the pursuit of a thing that cannot exist. The field's persistence in pursuing it is the architectural error.

## Coda

The discipline of matching substrate to job is broader than any one implementation, and the principle matters more than any brand. But principles without working examples are easy to dismiss, so naming an example matters.

I spend my time building a project called the Symbol Grounding Framework — SGF — which is one possible implementation of the symbolic substance layer in the composition described above. It uses closed semantic roles, federation-grade provenance metadata, and a content-fingerprint protocol that lets the substance layer interoperate with vector gateways across languages and modalities. There is a spec, there is code, and the discipline of "vectors at the gateway, symbols at the substance, neither blurs into the other" is baked into the architecture as a primitive rather than bolted on as middleware.

SGF is one possible answer to the symbolic-substance role. Wikidata, Cyc, custom RDF, and frame KBs are others. What matters is that some explicit, auditable, role-typed claim substrate fills the substance layer in any serious system. The brand matters less than the principle. The principle is that knowledge has heterogeneous storage needs and the discipline of matching substrate to job is what separates a system that scales gracefully from one that hallucinates fluently.

The trick is not to pick a winner. The trick is to put every substrate in its lane and let them compose.


