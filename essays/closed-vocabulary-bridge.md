# The Closed-Vocabulary Bridge: How to Match Wisdom to Situations at Scale

Every agentic AI system that accumulates wisdom — motivation rules, prior decisions, common-sense facts, design patterns, retrieved context — eventually hits the same wall: when you have ten thousand or a million pieces of wisdom and a fresh situation arrives, which pieces apply?

The naive answer is to embed both sides and match by similarity. That works at small scale. It fails everywhere else: a corpus past a few hundred entries produces false positives, false negatives, and a retrieval system that becomes more complex than the problems the wisdom was meant to solve. The matchmaker becomes harder than the match. Projects abandon themselves at this wall — Cyc with its hand-written predicates, ConceptNet with its embedding searches, every motivation-rule corpus that ever tried to grow past a thousand entries.

The Closed-Vocabulary Bridge is a structural answer. Instead of matching two unbounded natural-language spaces directly, introduce a finite named intermediate vocabulary that both sides are tagged with. The matching problem becomes a database join through the intermediate vocabulary. The intermediate vocabulary itself stays small — fifty to a few hundred classes at the top level, growing through hierarchy when scale demands it. The wisdom corpus that hangs off the vocabulary can be arbitrarily large because everything about it is automated: harvesting from public knowledge bases and the open web, embedding, clustering, class assignment, and per-situation classification all run without humans in the loop. The hard search problem becomes a tractable lookup whose cost is bounded by the vocabulary, not by the corpus.

The mechanism is three tables and two LLM calls per situation. A `problem_classes` table holds the finite named vocabulary, organized hierarchically. A `wisdom_class_bindings` bridge table maps each piece of wisdom to one or more classes with a strength weight. A `situation_classifier` call labels each new situation with one to five class IDs from the closed list. A SQL join returns the applicable wisdom. No BM25, no cross-encoders, no five-stage retrieval funnels. The closed-set assumption is doing the work.

Every matching system needs exactly one finite component, and the named vocabulary is the only viable candidate. The corpus must grow. The situations must remain free-form natural language. The classifier must handle the input the way it arrives. The vocabulary is the only place a designer can introduce a finite handle without breaking one of the other requirements. Once that constraint is taken seriously, the architecture has only one shape.

***

## The problem stated precisely

Three properties define the failure mode this pattern solves.

First, both sides are unbounded natural language. A piece of wisdom like "before deleting a confusing component during a refactor, find out why it exists" cannot be reduced to a fixed feature vector without losing what makes it useful. A situation like "the user is refactoring legacy code at 2am and proposes to strip out a module they don't understand" cannot be classified by keyword matching without missing the structural pattern that the wisdom was written to catch.

Second, the corpus grows. A useful wisdom corpus accumulates indefinitely. New rules surface as new failure modes appear. Old rules are kept because retiring them might lose context for cases that have not recurred recently but will recur eventually. Growth is structural, not optional. And the most valuable corpora — crowdsourced common-sense projects, technical postmortems harvested from the web, accumulated lessons from agent fleets — measure in millions of entries, not hundreds.

Third, the matching cost scales nonlinearly with corpus size. Embedding similarity at one thousand entries is acceptable; at one hundred thousand it is noise. Cross-encoders are accurate but cost N calls per query. LLM-as-judge funnels are accurate but cost more than the underlying task. The naive approaches all hit the same ceiling.

These three properties together — unbounded inputs, structural growth, nonlinear retrieval cost — define the class of problem. The same shape appears in retrieval-augmented generation, in common-sense knowledge bases, in case-based reasoning, in any system that maintains long-term wisdom. The pattern is not specific to one domain.

***

## The shape of the answer

The pattern's central move is to insert a finite intermediate between two infinite sides.

Three tables and one LLM operation form the architecture. The first table is the closed vocabulary itself. Call it `problem_classes`. Its rows are named with stable identifiers in snake_case — `external_api_boundary`, `concurrency_design`, `data_modeling_decision`, `legacy_refactor_judgment`, `security_perimeter`, `user_under_cognitive_load`. Each row carries a one-paragraph description and three to five concrete example situations. The vocabulary is finite. It is inspectable. It is editable. It is the closed set the rest of the system matches through.

The second table is the bridge. Call it `wisdom_class_bindings`. Its rows are many-to-many edges between pieces of wisdom and classes. Each edge carries a strength weight from zero to one. A rule about not deleting confusing code might be canonically bound to `legacy_refactor_judgment` with strength one and peripherally bound to `team_communication_context` with strength point six. The bridge is the join surface.

The third element is a small per-situation classifier. When a new situation arrives, the classifier sees the closed list of problem-class names and descriptions in its prompt and is asked to pick the one to five classes that apply. The classifier is one LLM call. Its output is structured: a list of class IDs with confidence values. The closed-set assumption — the model is choosing from a list, not searching open vocabulary — is what makes this reliable.

The lookup is a SQL join. Given the classifier's output, the system selects all wisdom rows bound to any of the matched classes, weighted by the strength column. The result is a manageable set of five to thirty applicable pieces of wisdom, ranked by relevance. No vector search ran. No cross-encoder fired. The matching problem became a database query.

The classifier does not need to be a categorical-only operation. The most robust implementations are hybrid. Each class in the vocabulary carries a rich one-paragraph description and three to five concrete example situations. Both the incoming situation and the class descriptions can be embedded, and the classifier's prompt can be augmented with the top-k nearest classes by embedding similarity rather than always presenting the full list. The model then makes a final closed-list selection from that shortlist. This preserves the categorical hinge that makes the system debuggable — every match still resolves to named class IDs that humans can read — while letting embeddings do the fast pre-filtering when the vocabulary grows beyond what fits comfortably in a single prompt. Pure-categorical and pure-embedding are the two endpoints; the practical sweet spot is the hybrid, where embeddings route attention through the classes but the classes remain the unit of meaning.

The cost profile inverts compared to embedding-based retrieval. Embedding retrieval pays high cost at every query and rebuilds indexes as the corpus grows. The Closed-Vocabulary Bridge pays bootstrap cost once, then pays only one cheap LLM classification call and one SQL join per query. Adding new wisdom is one embedding-to-nearest-class operation. No index rebuild required.

***

## Three worked situations

The corpus is two million pieces of wisdom assembled by automated harvesting: roughly one million entries imported from ConceptNet and ATOMIC, half a million extracted from a web crawl of technical postmortems and Stack Overflow accepted answers, four hundred thousand auto-extracted from a corpus of engineering, medical, and legal reference texts, and one hundred thousand generated by introspection passes over the running system's own logs. Each entry has a natural-language description of what it asserts and a natural-language description of when it applies. No human wrote any of them as wisdom rules; the harvesting passes auto-tagged them.

The vocabulary is one hundred forty top-level problem classes, derived by clustering the applies-when descriptions across the entire two-million-entry corpus. The vocabulary fits on three printed pages.

### Situation one: a developer refactoring legacy code

The system is helping a developer in a refactoring session. The developer says: "I don't understand what `legacy_event_router.py` does. Let me just delete it and rewrite from scratch."

The classifier returns three class IDs with confidence values:

- `legacy_refactor_judgment` — confidence 0.95
- `module_with_unknown_provenance` — confidence 0.87
- `user_under_cognitive_load` — confidence 0.62

The SQL join returns sixty-seven pieces of wisdom across the three classes. The top eight by binding strength weighted by class confidence:

- "Before deleting a complex component you don't understand, find someone who knows why it exists."
- "Code that looks redundant is often load-bearing for a case the original author handled."
- "A confusing module at the boundary of two subsystems is usually doing translation work that will need to be redone elsewhere."
- "Fatigue degrades the judgment that protects against irreversible changes."
- "When the urge to delete and rewrite is strong, the next-best move is to read every place that imports the target."
- "Components named with the word 'router' typically handle dispatch fan-out; deleting them shifts that responsibility elsewhere implicitly."
- "Refactors initiated from frustration produce worse outcomes than refactors initiated from understanding."
- "If a module has no tests, write tests against its observed behavior before changing it."

### Situation two: a clinician evaluating a cardiac discharge

The system is supporting a hospitalist preparing to discharge a sixty-eight-year-old patient admitted three days ago for atrial fibrillation with rapid ventricular response, now rate-controlled on a beta-blocker. The clinician notes the patient lives alone, has mild cognitive impairment, and the family is asking about same-day discharge.

The classifier returns four class IDs:

- `cardiac_transition_of_care` — confidence 0.93
- `anticoagulation_decision_point` — confidence 0.89
- `patient_with_diminished_self_advocacy` — confidence 0.78
- `discharge_against_optimal_timing_pressure` — confidence 0.71

The SQL join returns the top wisdom across the four classes:

- "Atrial fibrillation discharges without confirmed anticoagulation plan re-present within thirty days at significantly elevated rates."
- "Cognitive impairment plus living alone predicts medication adherence failure unless a structured adherence support is in place."
- "Family pressure for early discharge is a documented contributor to inadequate transition planning; the request itself is a flag, not a green light."
- "Beta-blocker rate control without rhythm control leaves the underlying arrhythmia present and the stroke risk unchanged."
- "Same-day cardiac discharges should be paired with a forty-eight-hour follow-up call to detect adherence failure before it becomes readmission."
- "When the patient cannot articulate the medication regimen back to the clinician, the discharge is not safe regardless of clinical stability."
- "Document the anticoagulation conversation explicitly; absence of documentation is litigated as absence of conversation."

### Situation three: a negotiator preparing for a litigated-vendor meeting

The system is supporting a procurement lead preparing for a meeting with a major software vendor whose contract is up for renewal. The relationship has been litigated twice in the past five years over service-level disputes; the vendor's product is now embedded in critical operations and replacement cost is high. The negotiator's stated goal is "improve terms without escalating to litigation again."

The classifier returns four class IDs:

- `negotiation_under_high_switching_cost` — confidence 0.96
- `counterparty_with_litigation_history` — confidence 0.91
- `contract_renewal_in_asymmetric_dependency` — confidence 0.88
- `relationship_repair_alongside_term_negotiation` — confidence 0.74

The SQL join returns:

- "When switching cost is high and known to both sides, the leverage is in scope and service-level commitments, not in price."
- "Counterparties with litigation history read aggressive opening positions as preludes to the next dispute; the opening should be the most reasonable position you would actually accept."
- "Asymmetric dependency relationships negotiated under a transactional frame produce worse outcomes than the same relationships negotiated under a long-horizon frame."
- "Bring a documented list of past service failures and their business impact; concrete history beats abstract argument."
- "Offer the counterparty a credible path to a better future relationship; without it, they default to extracting maximum value now."
- "Litigated relationships repair only when both sides change behavior; one-sided concessions reset the same dynamic in eighteen months."
- "Reserve one substantive concession to offer in the closing third of the meeting; meetings that close without movement on both sides do not produce durable agreements."

### What the three situations share

In each case, the system ran exactly one LLM classification call against the same one-hundred-forty-class vocabulary, then exactly one SQL join. Total cost per query in each domain: one cheap LLM call and one database lookup. Total time: under half a second. The wisdom that fired came from different regions of the corpus — software engineering postmortems, medical reference texts, negotiation literature — but the matching architecture was identical.

The vocabulary stayed at one hundred forty classes whether the corpus had ten thousand entries or two million, and whether the situation was technical, clinical, or commercial. That is the architectural property the pattern delivers: a single matching surface that generalizes across domains because the structure of the matching, not the content of the wisdom, is what scales.

***

## How the corpus is harvested

The pattern requires no hand-authored wisdom. The corpus is built from sources that already exist at scale, all of them automated:

- **Crowdsourced common-sense knowledge bases.** ConceptNet, ATOMIC, Cyc's released subset, Wikidata, and similar projects contain millions of natural-language facts and rules of thumb. Each entry already has a context that functions as its applies-when description. Ingestion is one parse pass per source.

- **Public technical wisdom.** Stack Overflow accepted answers, technical blog postmortems, framework documentation gotchas, security advisories, and engineering best-practice repositories all contain wisdom paired with the situations that triggered it. Web harvesting at scale is standard infrastructure.

- **LLM-extracted wisdom from existing texts.** Books, papers, and long-form articles contain implicit wisdom that an extraction pass can lift into explicit rules. The pass is one LLM call per source passage, producing both the rule and its applies-when context. A library of engineering books yields tens of thousands of entries.

- **System introspection.** When an automated system encounters a failure mode and a fix, the post-mortem itself is a wisdom candidate. The system writes its own lessons. No human intervention required.

The vocabulary stays small because it has to fit in an LLM classifier's prompt. The corpus is harvested automatically at unlimited scale. This asymmetry is the architectural property that makes the pattern useful: the vocabulary is the scarce resource and is treated as such; the corpus is abundant and is treated as such.

***

## How the vocabulary is bootstrapped

The vocabulary is not designed top-down. It is derived bottom-up from the corpus by an automated pipeline:

1. **Embed.** Every applies-when description in the corpus is embedded using a standard embedding model.
2. **Cluster.** The embeddings are clustered using HDBSCAN or a similar density-based clusterer at a target count appropriate to the corpus size — one hundred forty classes for the two-million-entry example above.
3. **Name.** For each cluster, an LLM call reads the ten to twenty applies-when strings nearest the cluster centroid and produces three artifacts: a class name (snake_case identifier), a one-paragraph description, and three to five concrete example situations.
4. **Verify with hold-out.** A held-out slice of the corpus is run through the classifier against the proposed vocabulary. If the classifier returns confident assignments to specific classes (not "none of the above" or low-confidence spreads), the vocabulary is well-formed. If the classifier struggles, the clustering parameters are adjusted and the pipeline reruns.

The bootstrap is run once. It takes an hour of compute on a million-entry corpus. After that, the vocabulary is stable. New wisdom is added by automated embedding-to-nearest-class assignment. The vocabulary itself can evolve: a periodic re-clustering pass detects when accumulated new wisdom has formed a cluster that does not fit any existing class, and a new class is proposed automatically and reviewed by an operator before being added. An operator's role is small and infrequent — verify a vocabulary check once a quarter — not write rules.

***

## Unvaporing abstract rules: instantiation as embedding payload

Concrete rules embed well. Abstract rules do not.

A rule like "before deleting a complex component you do not understand, find someone who knows why it exists" is full of concrete nouns and verbs: deleting, component, understand, someone, exists. Its embedding lands in a region of vector space populated by other rules about code, components, and refactoring. Cosine similarity finds it cleanly when a refactoring situation arrives.

A rule like "take precautions to prevent valuable things from deteriorating" is full of meta-concepts: precautions, valuable, deteriorating. Each word names a shape of meaning rather than a content of meaning. The embedding lands in a region of vector space that is approximately equidistant from everything, because the rule does not commit to any concrete domain. The embedding is vaporous. Cosine similarity cannot find it reliably when a situation arrives, because no situation is described in those abstract terms — situations are described in concrete terms like "milk in the fridge" or "code before a refactor" or "database before a migration."

This is not a flaw of a particular embedding model. It is structural. Abstract language describes patterns; embedding models were trained on language describing content. The pattern has no location in concrete vector space because the pattern is precisely what is left when the concrete is stripped away. An abstract rule's embedding sits in the region of vector space that means "I am not about anything specific," which is the wrong region to live in if you want to be retrieved.

The fix is to embed the application, not the abstraction.

When an abstract rule is ingested, the system asks an LLM to generate three to five concrete instantiations of the rule across diverse domains. The instantiations become the rule's embedding payload. The rule itself remains as the display text — the thing that gets surfaced to the agent or user — but the vector that anchors it in retrieval space is the embedding of the instantiation block, not the rule.

For the rule "extract a domain-agnostic lesson from each specific learning," the ingestion pipeline generates an instantiation block such as:

- Putting milk back in the fridge avoids spoilage; the general lesson is to take preventive action against the deterioration of perishable resources.
- Saving a code file before closing the editor avoids loss; the general lesson is to commit work before transitions where context can be lost.
- Backing up a database before a schema migration avoids corruption; the general lesson is to preserve recoverable state before irreversible operations.
- Stretching before exercise avoids injury; the general lesson is to prepare a system before subjecting it to stress.
- Reading a contract before signing avoids regret; the general lesson is to gather information before commitments that cannot be undone.

This block embeds well. It contains milk, fridge, code, file, database, contract, exercise, signing — concrete nouns the embedding model knows where to put. When a new situation arrives that involves any of those concrete activities, the situation's embedding finds the instantiation block, and through it the abstract rule. The rule is retrieved not because anything in the situation resembles the rule's abstract words, but because the situation resembles one of the rule's concrete instantiations.

The architecture treats this as a two-field row. The `rule_text` field is the abstract display string. The `embedding_payload` field is the instantiation block. The embedding is computed over the payload. The display text is returned to the consumer.

The more abstract the rule, the more important the instantiation block. A concrete rule's payload can be the rule itself; the instantiations add little. An abstract rule's payload is almost entirely instantiations; the rule itself contributes little to the embedding. The system handles the abstraction spectrum smoothly because the payload composition shifts with abstraction level.

The instantiation block is generated automatically. The ingestion pipeline includes a "generate five concrete instantiations of this rule across diverse domains" step that runs once per rule at ingestion time. The cost is one LLM call per rule added, paid once. The benefit is permanent: the rule becomes retrievable through concrete vector-space anchors.

This mechanism also explains how the bottom-up vocabulary derivation handles abstract rules during clustering. The clustering operates over the embeddings of the payload blocks, not over the raw rule text. Abstract rules cluster correctly because their payloads contain concrete language. A cluster of rules whose payloads all involve "preventive action against future loss" might end up named `preventive_judgment` or `loss_prevention_decision` — a class name that captures the abstract pattern even though no individual rule's abstract text would have clustered cleanly with the others.

The same instantiation move applies in the other direction: the class descriptions themselves benefit from concrete examples. The vocabulary bootstrap step that produces a one-paragraph description of each class also produces three to five concrete example situations for that class. Those example situations are the embedding payload for the class description, when classes need to be embedded for shortlisting. Both sides of the bridge — wisdom and vocabulary — handle abstraction the same way: by anchoring abstract content to concrete instantiations.

The principle generalizes. Anywhere an LLM-era system needs to embed something abstract, the system should embed the abstract item's concrete instantiations, not the abstract item itself. The abstraction is the label on the cluster of instances. The instances are what live in vector space. The matching happens through the instances and surfaces the abstraction.

This is how human experts already work. A doctor does not retrieve "preserve recoverable state before irreversible operations" when ordering a baseline EKG before cardiac surgery. The doctor retrieves the prior cases where a baseline mattered, and the abstract principle is the silent throughline. The instances are remembered and matched; the abstraction is the label. The architecture mirrors the cognitive operation.

***

## Why the closed-set assumption is doing the work

The intermediate is a closed list of finite size, not an open vocabulary. That single architectural decision carries the rest of the pattern.

A closed list changes what the LLM is being asked to do. In open retrieval, the model must produce a query that surfaces relevant items from an unbounded corpus — a task language models are not reliable at. In closed-list selection, the model must pick from a list shown directly in its context — a task language models are extremely reliable at. The cognitive operation is recognition, not generation.

The closed list also makes the system inspectable. The hundred-forty class names can be read in fifteen minutes. Two million wisdom entries cannot be read in any amount of time. The closed list is where diagnosis, debugging, and correction happen. When the system is making mistakes, the diagnosis starts with the vocabulary: are the classes well-named? Are there overlaps? Are there gaps? The questions are concrete because the vocabulary is concrete. The wisdom itself does not need inspection at scale — it only needs to be addressable through the vocabulary, and addressability is a join, not a read-through.

The closed list bounds growth. New wisdom is forced to find a home in the existing vocabulary, or to motivate the addition of a new class. Either path requires an explicit, automated decision. The system cannot accumulate wisdom that nobody can find, because every piece of wisdom must be addressable through the vocabulary or it is not retrievable at all.

The closed list is the structural pressure that prevents the failure mode that ends most wisdom-corpus projects. The corpus cannot become larger than the vocabulary that addresses it.

***

## Scaling to a million pieces of wisdom

A flat vocabulary of one hundred classes is sufficient for corpora up to a few hundred thousand entries. Past that, the wisdom per class becomes too large for the binding-strength weights alone to rank usefully. The pattern then nests.

Classes have a `parent_class_id` column. A situation can be classified at multiple levels of granularity simultaneously — `software_architecture` → `concurrency` → `shared_state_coordination` is three classifications in one. The classifier is run once per level, choosing from the children of the previously selected class. The selection narrows until the leaf level returns a tractable set of applicable wisdom.

The hierarchy mirrors how human expert knowledge organizes itself: domain to subdomain to specialty to niche. A corpus of ten million rules might use four levels of nesting with thirty top-level classes, fifteen to twenty subclasses each, ten sub-subclasses each, and five to ten sub-sub-subclasses each. Total leaf classes in the tens of thousands. Each classification call against five to thirty siblings. Each level cheap.

The hierarchy also enables the same wisdom to participate at multiple levels of specificity. A rule about defensive coding might bind canonically to a leaf class `input_validation_at_external_boundaries` and peripherally to a higher class `external_boundary_design`. A situation classified at the parent level retrieves the rule via the peripheral binding. A situation classified at the leaf level retrieves it via the canonical binding. Both retrievals are correct; the difference is the strength weight.

***

## Applications beyond motivation rules

Any time a system needs to match items from one unbounded natural-language space to items in another, and the corpus is expected to grow without bound, the Closed-Vocabulary Bridge is the right shape of architecture.

**Common-sense knowledge bases.** Cyc spent forty years attempting to encode common-sense facts in formal logic and built a retrieval engine over a corpus of millions. The retrieval problem broke the project. The same corpus, organized through a Closed-Vocabulary Bridge of perhaps two thousand hierarchical problem classes, would be retrievable at any scale because the matching cost is bounded by the vocabulary, not by the corpus. Forty years of accumulated wisdom would become usable in a way it has never been usable.

**Pluggable expertise modules — a knowledge-pack app store.** When the corpus is filtered to wisdom about a specific domain — legal reasoning, medical decision-making, financial judgment, negotiation tactics, scientific peer review, regulatory compliance — the result is a "pluggable brain" for that domain. The same matching architecture surfaces legal-reasoning wisdom for a contract review situation and surfaces medical-reasoning wisdom for a diagnosis-support situation. The vocabulary tells the system which brain to consult; the bridge returns the wisdom from that brain. One agent can be a lawyer, a doctor, a negotiator, or a scientist by swapping which subset of the corpus is bound to the active vocabulary.

The economic shape of this is a knowledge-pack app store. A pack is a self-contained bundle: a domain vocabulary, a wisdom corpus harvested and tagged against that vocabulary, a manifest describing scope and provenance, and the bridge table that joins them. Pack examples write themselves once the pattern is seen: an offshore-drilling operations pack covering well-control decisions, blowout-preventer judgment, and crew-change safety protocols; an emergency-department triage pack covering rapid acuity assessment, atypical presentations, and disposition decisions; a cross-border M&A pack covering jurisdiction-specific antitrust thresholds, foreign-investment review regimes, and integration-planning failure modes; a cardiac-surgery pack covering pre-operative risk stratification, intra-operative decision points, and post-operative complication recognition; a pharmaceutical-development pack covering trial-design judgment, regulatory-submission failure modes, and post-market surveillance signals; a derivatives-trading-risk pack covering position-sizing under fat-tailed distributions, counterparty-exposure judgment, and liquidity-crisis playbooks. Each pack is built by harvesting from domain-specific sources — peer-reviewed literature, regulatory filings, post-mortems, case databases, professional handbooks — and installing into an agent is a matter of registering the pack's vocabulary and binding table alongside the agent's existing ones. The agent gains a new expertise the moment the pack is loaded. Vendors of professional knowledge — publishers, professional societies, regulatory bodies, consulting firms — become the natural producers and curators of these packs. The same architecture that makes wisdom retrievable at scale makes wisdom packagable as a product.

**Retrieval-augmented generation.** Current RAG architectures embed documents and search by similarity. The result is brittle: small wording changes in queries produce different retrievals, and the matching has no inspectable structure. A RAG system architected around a Closed-Vocabulary Bridge would be more accurate because the classifier picks from a known list, more debuggable because the classes are inspectable, and more maintainable because new documents are tagged by a clear automated operation rather than disappearing into vector geometry.

**Case-based reasoning.** Already uses something close to this pattern but typically without the bottom-up vocabulary derivation. Adding the clustering bootstrap lets these systems scale beyond the small corpora they are currently practical for.

**Personal knowledge management.** The wisdom corpus is your accumulated notes, web clippings, and documents. The situation is what you are currently working on. The classifier picks from a closed list of life or work domains. The bridge returns the notes that apply. This is the architecture every "second-brain" tool wants and almost none implement.

Wherever the matching problem currently looks like "embed everything and search by similarity," the Closed-Vocabulary Bridge is a candidate replacement. The change in cost profile and the gain in inspectability are usually worth the bootstrap.

***

## Three FAQs

### How is this different from a tag system or a controlled vocabulary?

A tag system or controlled vocabulary is the same surface idea applied to documents. The Closed-Vocabulary Bridge is specifically designed for LLM-era systems where one side is wisdom and the other side is situations described in free-form natural language.

First, the vocabulary is derived bottom-up by clustering the wisdom side's natural-language descriptions. Traditional controlled vocabularies are designed top-down by domain experts and frequently fail to match how items are actually used. The bottom-up derivation produces vocabularies that fit the corpus because they came from the corpus.

Second, neither the vocabulary derivation nor the ongoing wisdom tagging requires human labor at scale. Clustering runs automatically. Class naming is one LLM call per cluster. New-wisdom tagging is an automated embedding-to-nearest-class assignment. Traditional controlled vocabularies require human tagging by content producers, which does not scale past tens of thousands of entries.

Third, the classifier on the situation side is an LLM call against a closed list, not a keyword matcher or a faceted search. The model is doing semantic recognition against a fixed inventory, which is one of the things models are most reliable at. Traditional controlled vocabularies require manual tagging or string-match indexing, neither of which generalizes to situations described in free-form natural language.

Fourth, the bridge table is many-to-many with strength weights, so a single piece of wisdom can be peripherally relevant to several classes without being canonically tied to any of them. Traditional tag systems usually require single-class assignment or unweighted multi-class assignment, which loses the relevance gradient.

### Will this scale to multimodal inputs — code, images, sensor data?

Yes, with one extension. The classifier becomes multimodal. The closed vocabulary remains a list of named, described classes. A code snippet is shown to the classifier alongside the class list; the classifier produces class IDs. An image is shown to a vision-capable classifier alongside the class list; same output shape. The bridge table and the wisdom corpus do not change. The classification step is where modality matters; the lookup step is modality-agnostic.

### What happens when the vocabulary is wrong?

It will be wrong, repeatedly. The vocabulary is a hypothesis about how the problem space carves up, and hypotheses fail.

Vocabulary mistakes are diagnosable. When the system produces poor matches, the cause is usually traceable to one or two specific classes that are too broad, too narrow, or wrongly bounded. The class definitions can be read alongside the misclassified situations and the boundary problem is usually obvious. This is not possible with embedding-based retrieval, where the cause of a bad retrieval is buried in vector geometry.

Vocabulary mistakes are repairable without rebuilding the system. Renaming a class is a metadata change. Splitting a class is two metadata operations plus an automated rebinding pass over the affected wisdom. Merging two classes is the reverse. Adding a class is a one-row insert plus an automated rebinding pass. None of these operations require re-embedding the corpus from scratch or rebuilding an index. The system continues running during repair.

The vocabulary improves over time through use. Errors surface, corrections are made, and the vocabulary converges on what the corpus and the situation space actually need. This is the opposite of embedding-based systems, where the embeddings are largely opaque and improvement requires changing the embedding model or the retrieval algorithm.

***

## A foundational instance: the Symbol Grounding Framework

The pattern is not new in the abstract. It has been independently arrived at, at a deeper layer of the meaning stack, by the Symbol Grounding Framework — an architecture for machine meaning that resolves the same class of problem one floor below wisdom retrieval, at the level of words, senses, and events.

SGF identifies the same failure mode this essay identifies, in a different domain. Knowledge graphs keyed by lemma strings collapse: the lemma "bank" routes river-edges and financial institutions to the same node because the key is a surface string with no sense-level structure. SGF replaces the lemma key with a Canonical ID — a structured address with fields for language, lemma, microgloss, and part of speech — and the collapse goes away. The Canonical IDs sit in a Core Lexicon organized as a hierarchical DAG, with finite primes at the bottom serving as the grounding floor. Every concept resolves to a sense-level address or is explicitly marked UNRESOLVED. The same architectural commitment the Closed-Vocabulary Bridge makes at the wisdom layer, SGF makes at the lexical layer, and it recurs at four nested scales within SGF itself.

- **Primes.** A finite set of about sixty-five irreducible semantic primitives — based on the Natural Semantic Metalanguage research program — serves as the grounding floor. Every concept must reach the primes by a finite IS_A path or be marked UNRESOLVED. The primes are the closed set that terminates decompression.
- **Canonical IDs.** A structured, finite address space for word senses. The lemma is the unbounded surface; the contexts in which a word is used are unbounded; the Canonical IDs are the finite bridge between them.
- **Semantic roles.** Fifteen universal roles — HAS_AGENT, HAS_PATIENT, HAS_INSTRUMENT, HAS_LOCATION, and so on — close the edge vocabulary of event structures. Predicates in legacy RDF graphs were unbounded and produced the "predicate explosion" that stalled the Semantic Web; SGF's closed role inventory prevents the explosion by structural fiat.
- **The Core Lexicon DAG.** New mentions either resolve to existing Canonical IDs or are admitted through a micro-lexicon whose IS_A chains climb back into the shared graph. The Lexicon is the closed bridge between local terminology and global meaning.

At each scale, the move is the same: a finite named set sits between two unbounded sides, lookup proceeds by structural address rather than by similarity, and unresolvable cases are marked explicitly rather than fabricated. SGF demonstrates the pattern at the layer where meaning itself is stored. The Closed-Vocabulary Bridge demonstrates it at the layer where wisdom is matched to situations. The two are the same architectural commitment applied at different layers of the same stack.

The instantiation-embedding mechanism described earlier — pinning abstract rules to concrete examples so their embeddings have somewhere to live — is structurally the same move SGF makes when it requires every Canonical ID to carry a microgloss and an IS_A chain into a concrete neighborhood. A bare lemma is vaporous in the same way a bare abstract rule is vaporous. A Canonical ID with its microgloss and lexical parents is anchored in the same way an abstract rule with its instantiation block is anchored. The same diagnosis, the same fix, at different scales.

A Closed-Vocabulary Bridge built on top of SGF inherits a grounded substrate: situations, wisdom, and problem classes can all be expressed in terms of Canonical IDs and Synapses rather than raw natural language. The classifier's job becomes easier because the inputs are already structured. The bridge table's keys become more durable because Canonical IDs are reversible addresses with stable identity, while raw strings are not. The full stack — primes, Canonical IDs, roles, Lexicon, then wisdom classes on top — forms a layered architecture where each layer's closed vocabulary makes the next layer's matching possible.

For readers who want the foundational layer worked out in full, SGF is offered as a public architecture with open specifications, a GitHub repository, and a six-volume book series. The framework defines the Lexicon, the Synapse grammar, the wire protocol that moves meaning between systems, and the governance language that enforces constraints over both. The Closed-Vocabulary Bridge in this essay sits naturally on top of that substrate as one application among many.

***

## The deeper principle

Match through structure, not through similarity.

When two unbounded spaces need to be matched, the temptation is to find a measure of similarity that works on both sides and to match by the measure. This is the natural move because it requires no design. The structure of the problem is left implicit and the matching is delegated to the measure.

The opposite move is to introduce explicit structure between the two sides — a finite vocabulary, a named taxonomy, a controlled set of intermediates — and to require both sides to be tagged with elements from the structure. The matching becomes a join through the structure. The structure carries the design decisions explicitly, where they can be debugged.

Database design has known this since the relational model. Knowledge representation has known this since the early ontology work. Library science has known this since the Dewey Decimal System. Each of those disciplines learned, in its own time and at its own cost, that structured intermediates beat similarity matching when the corpora become large enough to matter.

The Closed-Vocabulary Bridge is the LLM-era instance of the same principle. The intermediate is a list of named classes. The tagging on both sides is automated by clustering and by LLM classification. The join is SQL. The structure is the architecture, and the architecture is what scales.

The same principle applies one level deeper, inside the embedding layer itself. Abstract concepts have no native location in concrete vector space; they need to be anchored by their instantiations to become retrievable. The instantiation block is a structured intermediate between the abstraction and its embedding, the same shape of move at a different scale. Match through structure, not through similarity, all the way down. Where the closed vocabulary sits between the corpus and the situations, the instantiation block sits between an abstract rule and its embedding. The pattern recurs because the underlying problem recurs: unbounded meaning, finite handles.

Intelligence does not need to grow to handle a million pieces of wisdom; the architecture around the intelligence needs to provide the structure that makes the million tractable. When the structure is right, a small model with a small classifier and a small database can do what a giant model with megabytes of context and embedded vectors cannot.

The lever is not the model. The lever is the structure.

---


*This essay describes a design pattern that emerged from work on the Archimedes Lever intent compiler and a prior motivation-rule project. The pattern is offered to the public domain. The wisdom examples in the three worked situations are paraphrased composites assembled to illustrate the matching behavior; they are not quotations from a specific source and should not be read as citations. The pattern described here is part of a larger collection of design patterns that orbit the Symbol Grounding Framework (SGF) — an open architecture for machine meaning. SGF resources, including RFC-style technical specifications and free PDF editions of the six-volume book series, are available at the SGF GitHub repository (github.com/SymbolGroundingFramework/SGF-manifest) and at symbolgrounding.io.*
