# RFC-001: The Wisdom Lattice (V2.2 - Final)

**A Standard for Harvesting, Embedding, and Retrieving Machine Wisdom**

**Status:** Proposed  
**Category:** Informational / Behavioral Standards  
**Author:** [Authors]  
**Date:** 2026-08-09  
**Supersedes:** V2.1, V2.0, and all prior drafts.

---

## ABSTRACT

The wisdom bottleneck is not harvesting—it is findability at scale. This RFC specifies the Wisdom Lattice: a three-component architecture (Harvest Pipeline, Retrieval Cascade, Behavioral Graph) for converting human behavioral text into retrievable, auditable machine wisdom. The Lattice resolves the central paradox that defeats naive RAG and LLM-only approaches: abstract wisdom has no home in vector space, but concrete anchors do. It anchors abstract rules to concrete, cross-domain instances so they can be retrieved through their instantiations. It uses a **two-source behavioral graph**—declared structural edges plus operationally discovered edges—so conflict resolution is correct from day one and refined by experience. The Lattice is not a replacement for the LLM; it is the constitutional layer that makes a brilliant advisor bounded by auditable, provenance-tracing, governable law.

---

## 1. THE THESIS

> Wisdom is not knowledge; it is a behavioral response pattern triggered by a structural situation. Retrieval is not semantic search; it is structural pattern-matching followed by deterministic cascaded filtering. The behavioral graph that governs conflict is the most load-bearing structure in the system. It must be **bootstrapped from declared structural properties** (inverse actions, incompatible desired states, trigger contradictions) and **continuously refined through operational experience** (novel situational conflicts discovered at retrieval time). Neither alone is sufficient.

---

## 2. THE PROBLEM: WHY THE LLM ALONE FAILS

The LLM alone has four structural liabilities that fine-tuning, prompting, and RLHF cannot fix:

1. **It cannot prove it applied your protocol.** A black box. No audit trail. Ask it to follow protocol X; it produces a plausible answer but you cannot verify X was actually considered and not overridden by a statistical association from a different context.

2. **It cannot trace provenance.** The LLM's wisdom is a statistical amalgam of everything it has read—textbooks, Reddit threads, FDA labels, blog rants. It cannot distinguish a verified guideline from a forum post.

3. **It cannot refuse structurally.** Guardrails are prompts—overridable by persuasion, jailbreak, or a user who seems insistent. There is no mechanism for "no" that the user cannot surpass.

4. **It cannot resolve priority deterministically.** When 500 rules apply, the LLM picks the statistically most probable combination, which may average three conflicting approaches. There is no deterministic "which wins here."

These are not bugs. They are the architecture of a next-token predictor. The Wisdom Lattice is the substrate that makes wisdom *visible, auditable, and governable* when failure is costly.

---

## 3. TERMINOLOGY

| Term | Definition |
|---|---|
| **Wisdom Node** | Atomic unit of the lattice: one rule, with Synapse fingerprint, behavioral skeleton, representation anchors, and evolving edges. |
| **Synapse (SGF)** | Verb-hub plus 15 role-bound spokes grounded in the Synapedia. Structural fingerprint. |
| **Representation Anchor** | Concrete, cross-domain, Level 1–2 instance sentence that embeds well, dragging the abstract rule into vector space. |
| **Behavioral Graph** | Nodes + edges. Edges are declared (structural) or discovered (situational). |
| **Master Hub Enum** | Closed, version-controlled set of canonical hub verbs grounded in the Synapedia, with a lifecycle (PROVISIONAL → STANDARD). |
| **Retrieval Cascade** | Ordered filter: graph routing → applicability gate → vector similarity on subset → context + graph traversal → LLM assembly. |
| **Lattice Lifecycle** | The states and transitions of a wisdom node: HARVEST → DRAFT → RETRIEVE → CONFIRM → GRADUATE → RETIRE. |

---

## 4. THE DERIVATION CHAIN (Why Each Component MUST Exist)

**Why the Synapse?** Abstract wisdoms share behavioral structure but zero semantic surface (milk, codebase, and a failing engine have the same "stabilize first" shape). Remove it; retrieval degenerates to keyword proximity that cannot bridge domains. The SGF 15-role grammar makes it cross-system interoperable and auditable.

**Why concrete anchors?** Abstract rules have no vector home. The anchor is the hook that drags the abstract rule into vector space. Remove them; retrieval cannot bridge the abstraction gap—abstract queries find nothing, concrete queries find the wrong thing.

**Why the cascade?** A billion nodes cannot enter an LLM context or a full vector index. The cascade keeps the LLM at 20 nodes and the vector store at ~10K. Each stage is deterministic and cheaper than the last.

**Why the two-source behavioral graph?** Conflicts have two natures:
- **Structural (declared):** A rule with "stabilize before diagnose" and a rule with "diagnose before stabilize" addressing the same problem conflict *by definition.* This is deterministically knowable at harvest.
- **Situational (discovered):** `OVER_PRECAUTION` and `STABILIZE_FIRST` conflict only when the actor is anxiety-prone; `STRATEGIC_DELAY` overrides `ACT_IMMEDIATELY` only when the system is stable. These cannot be pre-declared for all contexts; they emerge from retrieval collisions.

Removing either source leaves the graph either brittle (cold-start, gaps, rare-edge misses) or empty-and-collision-dependent. The lattice requires both.

---

## 5. THE WISDOM NODE SCHEMA

```json
{
  "---IDENTITY---": "",
  "id": "unique_slug_from_name",
  "name": "STABILIZE_PRIMARY_FIRST",
  "cognitive_order": 1,
  "layer": "posture",
  "rule_type": "CONSTITUTIONAL",
  "strength": 0.95,

  "---ABSTRACTION_LADDER (pre-generated, stored 6x)---": "",
  "abstraction_ladder": {
    "level_1_operational": "On a 737 with #1 engine failure, pitch up immediately, bank into the live engine, then confirm airspeed.",
    "level_2_type": "When an engine fails on a multi-engine aircraft, maintain control before diagnosis.",
    "level_3_domain": "In an aviation emergency, stabilize the aircraft before resolving the cause.",
    "level_4_domain_abstract": "In any crisis, stabilize the primary system before diagnosing.",
    "level_5_cross_domain": "In any stressful situation, secure the fundamentals before attending to details.",
    "level_6_universal": "Before you can solve a problem, you must first survive the situation it creates."
  },

  "---STRUCTURAL_FINGERPRINT (SGF Synapse)---": "",
  "synapse": {
    "canonical": {
      "hub": "STABILIZE_FIRST_THEN_DIAGNOSE",
      "roles": {
        "HAS_AGENT": "OPERATOR_IN_CRISIS",
        "HAS_PATIENT": "PRIMARY_SYSTEM_UNDER_STRESS",
        "HAS_CAUSE": "SUDDEN_STATE_CHANGE",
        "HAS_TIME": "AT_ONSET",
        "HAS_REASON": "PREVENT_SECONDARY_FAILURE"
      }
    },
    "raw": {
      "hub": "PITCH_UP_KEEP_HEADING",
      "roles": {
        "HAS_AGENT": "PILOT",
        "HAS_PATIENT": "AIRCRAFT_WITH_ENGINE_FAILURE"
      }
    }
  },

  "---BEHAVIORAL_SKELETON---": "",
  "behavioral_skeleton": {
    "problem": "Crisis induces panic and premature diagnosis, worsening the initial failure.",
    "desired_state": "Primary system stabilized before diagnosis or communication.",
    "causal_logic": "Panic compresses the operator's attention window, causing them to bypass stabilization and jump to diagnosis. Premature diagnosis consumes cognitive bandwidth needed for flight control. Stabilization restores attention window, enabling accurate diagnosis.",
    "action_sequence": ["stabilize_physical_threat", "orient_to_actual_state", "decide_next_phase"],
    "triggers": ["sudden_loss", "immediate_threat", "operator_in_panic"],
    "anti_triggers": ["routine_checklist", "threat_already_contained", "delay_would_cause_more_harm"]
  },

  "---REPRESENTATION_ANCHORS---": "",
  "concrete_anchors": [
    {"text": "A pilot with a failed engine must maintain control before diagnosing.", "domain": "aviation"},
    {"text": "A parent with a terrified child must calm the child before explaining.", "domain": "human_relations"},
    {"text": "A codebase atrophies if you defer refactoring; stabilize the build first.", "domain": "software_eng"},
    {"text": "A doctor with a bleeding patient must stop the bleeding before ordering tests.", "domain": "medicine"}
  ],

  "---CONTEXTUAL_FRAME---": "",
  "contextual_frame": {
    "urgency": ["routine", "elevated", "emergency"],
    "stakes": ["low", "medium", "critical"],
    "expertise_level": ["layman", "novice", "expert"],
    "compliance_audit_required": false,
    "jurisdiction": "*"
  },

  "---APPLICABILITY---": "",
  "domain": ["aviation", "emergency_medicine", "software_reliability", "parenting"],
  "applies_when": "System is under active threat and the operator is entering a panic state.",
  "anti_applies_when": "System is already stable, or immediate action would violate a jurisdictional constraint.",

  "---LIFECYCLE_AND_PROVENANCE---": "",
  "status": "vetted",
  "epistemic_status": "CONFIRMED_BY_EXPERT",
  "source_provenance": {
    "origin": "Aviation Safety Manual",
    "authority": "FAA Advisory Committee",
    "empirical_basis": "Documented accident investigations"
  },
  "genesis_rationale": "Harvested from cold-chain logistics wisdom, generalized through cross-domain transfer.",
  "validity_decay": { "last_confirmed": "2026-08-01", "half_life_days": 1095 }
}
```

**Key design decisions**

| Decision | Rationale |
|---|---|
| **Abstraction ladder is pre-generated, stored 6x** | Eliminates the retrieval-time LLM call. Template-mode assembly becomes robust, real-time capable. |
| **Synapse uses closed 15-role SGF grammar, hubs grounded in Synapedia** | Cross-system interoperable, auditable, prevents hub synonymy fragmentation. |
| **`causal_logic` field captures the mechanism, not just the procedure** | Distinguishes wisdom from a checklist. |
| **`contextual_frame` is first-class** | Enables correct presentation and gating in emergency/critical/regulated contexts. |
| **Edges drawn from two sources (declared + discovered)** | Solves both the cold-start and rare-edge problem. |

---

## 6. THE HARVEST PIPELINE

**Goal:** transform raw text into a fully populated Wisdom Node.  
**Cost:** 5 LLM calls per node + 1 batch graph-placement call. Abstraction ladder pre-generated.

### Step 1: Domain and Context Classification (1 LLM call)
Classify domain, urgency, stakes, compliance_audit_required, jurisdiction.

### Step 2: Synapse Extraction (1 LLM call, constrained by master hub enum)
Extract raw (original) and canonical (SGF 15-role / Synapedia) Synapses. Hub chosen from the closed enum. Minted hubs start as `PROVISIONAL` and follow the lifecycle (§8.5).

### Step 3: Behavioral Skeleton (1 LLM call)
Extract problem, desired_state, causal_logic, action_sequence, triggers, anti_triggers.

### Step 4: Abstraction Ladder + Concrete Anchors (1 LLM call)
Generate all 6 levels AND 5–10 concrete anchors. Store both.

### Step 5: Graph Bootstrap (batch, deterministic seed + LLM refinement)

Apply the declared-structural checks (Action Inversion, Desired-State Exclusion, Trigger Contradiction — see §8.3 for precise definitions) against the existing corpus. LLM-assisted edge classification is **refinement** for ambiguous cases, not the primary mechanism.

---

## 7. THE RETRIEVAL CASCADE

**Principle:** The intelligence never touches the full corpus. Each stage filters by the cheapest operation first, the most expensive last.

```
QUERY: "My codebase is rotting because we keep deferring small refactors."
  │
  ▼
[Stage 0] FAST PATH GATE (deterministic, from orchestrator declaration)
  quality_tier = orchestrator field (FAST / STANDARD / STRATEGIC).
  If FAST → skip lattice, use LLM directly. If STANDARD/STRATEGIC → proceed.
  No inference; trusted from the DAG planner.
  │
  ▼
[Stage 1] SITUATION ANALYSIS (1 LLM call)
  Extract SGF Synapse + contextual_frame (urgency, stakes, expertise) + domain,
  target abstraction level. Output: structured situation descriptor.
  │
  ▼
[Stage 2] STRUCTURAL ROUTING (no LLM, graph index)
  Navigate centroid tree by canonical Synapse. 1B → 100K.
  │
  ▼
[Stage 3] APPLICABILITY GATE (3 layers, mostly deterministic)
  Layer 1: exact keyword match between `applies_when`/`anti_applies_when`
           and the situation descriptor state fields. No LLM.
  Layer 2: Boolean logic composition (AND/OR/NOT) evaluated against
           the situation state vector. Deterministic.
  Layer 3: If Layers 1+2 yield `UNCERTAIN` (keyword overlap on both
           applies and anti-applies), escalate ONLY that single candidate
           to an LLM call. <20% of candidates. 100K → 10K.
  │
  ▼
[Stage 4] SYNAPSE SIMILARITY (no LLM, vector subset)
  Embed query canonical Synapse. Cosine against the surviving 10K.
  Keep top 50. 10K → 50.
  │
  ▼
[Stage 5] CONTEXT + GRAPH TRAVERSAL (no LLM, metadata filter + graph DB)
  Filter top 50 by contextual_frame. For survivors, pull declared AND
  discovered edges: conflicts + resolutions, complements, overrides,
  override_by, refined edges. 50 → 10–20, now orchestrated.
  │
  ▼
[Stage 6] LLM ASSEMBLY (1 LLM call)
  Generate the appropriate abstraction level (pre-generated, so this is
  a selection, not a generation). Pick best concrete anchor. Resolve
  conflicts using stored resolution logic. Output: structured guidance.
```

**LLM calls per retrieval:** 2 (Stages 1 and 6).  
**Graph operations:** 2. **Vector operations:** 1 on a subset.

### Worked Walkthrough

**Query:** "My codebase is rotting because we keep deferring small refactors."

1. Stage 0: quality_tier = STANDARD → proceed.
2. Stage 1: Synapse = `[HAS_AGENT: DEV_TEAM, HUB: DEFER_MAINTENANCE, HAS_PATIENT: CODEBASE, HAS_CAUSE: TIME_PRESSURE, HAS_REASON: PRESERVE_VELOCITY]`. Urgency=elevated, stakes=high.
3. Stage 2: Centroid tree → `software_eng / DEFER / CODEBASE` → 90K.
4. Strike 3: Layer 1 + 2 filter → 7K.
5. Stage 4: cosine on 7K → top 50.
6. Stage 5: Context filter → 12 survivors. Edge traversal pulls `CONFLICTS_WITH: OVER_PRECAUTION_PARADOX` (declared, resolution = use simple revert), `COMPLEMENTS: SMALL_BATCH_IMPLEMENTATION`.
7. Stage 6 (LLM assembly): "Your codebase is in a degradation spiral. Governing wisdom: `STABILIZE_PRIMARY_FIRST` — revert to last stable build before analyzing the backlog. Apply `SMALL_BATCH` to prevent recurrence. Caution: this conflicts with `OVER_PRECAUTION` — use a simple revert first, then plan the systemic fix."

---

## 8. KEY DESIGN DECISIONS

### 8.1 Applicability Gate: 3-Layer Hybrid (Concrete)

- **Layer 1 — Exact keyword match.** `applies_when` parsed into keywords (e.g., "under_active_threat", "operator_in_panic"). The situation descriptor fields are checked for exact keyword presence. Zero LLM, auditable, deterministic.
- **Layer 2 — Boolean logic composition.** `applies_when` clauses become boolean expressions (AND, OR, NOT). Evaluated against the situation state vector. Deterministic.
- **Layer 3 — LLM fallback, only for ambiguity.** If Layers 1+2 yield `UNCERTAIN` (keyword overlap on both applies and anti-applies), escalate that single candidate. Typically <20% of candidates.

### 8.2 Fast Path Gate: Orchestrator-Declared Quality Tier

The slow/fast distinction is now **declared** by the DAG planner, not inferred at retrieval. It is the `quality_tier` field already present in the pipeline (FAST/STANDARD/STRATEGIC). No inference, no LLM call, no ambiguity.

### 8.3 Behavioral Graph: Two-Source Bootstrap

The graph is **bootstrapped from structural declaration, refined by operational discovery.** Neither alone is sufficient.

**Phase A — Structural Declaration (at harvest, zero LLM cost)**

The following three checks are deterministic and run at harvest time against every existing node in the same problem-cluster. They are the ground-truth seed for the graph.

**Check 1: Action Inversion**

Precise definition:

```
Action Inversion is declared when two rules address the same
`problem` AND one of the following holds:

1. Full inversion: one rule's `action_sequence` is the exact reverse
   of the other's. (Example: [stabilize, orient, decide] vs
   [decide, orient, stabilize].) Conflict is declared without further
   analysis.

2. Leading-step inversion: both rules share the same first action,
   but their second actions are mutually exclusive — specifically,
   the second action of one rule matches a value that the other
   rule names in its `anti_triggers`. (Example: first action =
   "stabilize" for both; rule A's second action = "orient",
   rule B's second action = "immediately diagnose", and rule B's
   `anti_triggers` includes "operator is in orientation state".)
   Conflict is declared.

3. Partial overlap with incompatible tail: both rules share the first
   50% of their `action_sequence`, but diverge into mutually exclusive
   `desired_state` values. (Example: both start [stabilize, orient],
   but rule A ends in "diagnosis at leisure" while rule B ends in
   "immediate decisive action".) Conflict is declared with a
   provisional resolution based on the situation-dependent override
   stated in either rule's `conditional_override` when present.

All other pairings are deferred to LLM-assisted classification
in Phase B (operational discovery) — they are not declared as
conflicts at harvest.
```

**Check 2: Desired-State Exclusion**

Reachable states from `desired_state` are compared. If they are mutually exclusive (e.g., "cold" vs. "warm", "contained" vs. "exposed"), a `conflicts_with` edge is declared.

**Check 3: Trigger Contradiction**

If rule A's `triggers` name a state that rule B's `anti_triggers` name (and vice versa), a `conditional_override` edge is declared, with a provisional resolution being whichever rule has the higher `cognitive_order` or the more specific `domain`.

These checks are deterministic, auditable, and work from day one with the existing 850-wisdom corpus.

**Phase B — Operational Discovery (contextual JIT at retrieval)**

1. On every retrieval, after Stage 5, if the assembly step resolves a conflict between two wisdoms that has no declared edge, flag the pair.
2. If the same pair collides in 5+ distinct query contexts, propose a `discovered` edge.
3. Tag the proposed edge with a `provisional_resolution` extracted from the most common way the conflict was resolved in prior contexts.
4. Promote to `VETTED` after 10+ further retrievals resolve cleanly, or after human review.

**Phase C — Hybrid Precedence and Rare-Edge Backstop**

- **Precedence:** Declared edges are ground truth. Discovered edges cannot override a declared edge; they supplement.
- If a discovered edge contradicts a declared edge, flag a `CROSS_TRUST_CONFLICT` and escalate to human review.
- **Cold start:** Day one includes Phase A edges. The system is already correct on structural conflicts.
- **Rare-edge auditor (background task):**

```
§8.3 Phase C — Rare-Edge Auditor

Frequency: Once daily, background task.
Sampling: Stratified by stakes.
  - 10% of samples from high-stakes nodes
  - 30% from medium-stakes
  - 60% from low-stakes
Method: For each sampled pair, run the Phase A structural checks
  (Action Inversion, Desired-State Exclusion, Trigger Contradiction).
  If any check fires, create a proposed edge with the reason.
Compute budget: Maximum 10,000 pair-checks per run.
Promotion: Same lifecycle as Phase B discovered edges
  (provisional → vetted after 10+ clean retrievals or human review).
```

### 8.4 Abstraction Ladder: Pre-Generate at Harvest

The full 6-level ladder is generated once per node at harvest. Storage cost rises ~5x, but it eliminates the retrieval-time LLM call, makes template-mode assembly robust, and simplifies the retrieval pipeline. At billion-node scale, JSON compression and columnar storage make this space addressable.

### 8.5 Master Hub Enum Lifecycle

| Stage | Criteria |
|---|---|
| **PROVISIONAL** | Minted when no existing hub matches. Appears in ≥3 distinct domains. |
| **STANDARD** | After 10+ nodes use it across 3+ distinct domains. |
| **RETIRED** | <3 usages after 90 days, or superseded by a stronger, more general hub. |

The is-inside check: a new hub proposal must either be a hyponym of an existing hub or justify a genuinely orthogonal action family. Semantic-similarity dedup: if >0.9 similarity to an existing STANDARD hub, map to the existing one.

---

## 9. THE LATTICE LIFECYCLE

A wisdom node progresses through a deterministic lifecycle. This map describes how a rule is born, lives, and dies in the system.

```
      HARVEST ──▶ DRAFT ──▶ RETRIEVE ──▶ CONFIRM ──▶ GRADUATE ──▶ RETIRE
        │         │            │             │            │           │
        │         │            ▼             │            │           │
        │         └────────▶ (retrieved)     │            │           │
        │                     │ failed QA   │            │           │
        │                     ▼              │            │           │
        │                  (re-draft)        │            │           │
        │                                    │            │           │
        │◀────────── (validity decay) ◀─────│◀───────────│◀──────────│
```

| State | Transitions |
|---|---|
| **HARVEST** | Raw wisdom text ingested into the system. |
| **DRAFT** | Plausible but unvetted. Available for retrieval, flagged as unconfirmed. |
| **RETRIEVE** | Actively returned by the cascade. If retrieved but fails QA (e.g., produces a wrong resolution), it re-enters DRAFT for revision. |
| **CONFIRM** | Human or policy review confirms the wisdom is correct and reliable. |
| **GRADUATE** | Promoted to `vetted` status. Full retrieval weight. Candidate for Omega rule. |
| **RETIRE** | Validity decay triggered, or superseded, or never retrieved after a defined period. Archived, not deleted (SCD Type 2). |

---

## 10. EDGE CASES

| Edge Case | Mechanism |
|---|---|
| **Novel situation (no structural match)** | Stage 2 returns <5 candidates. Fallback: rerun at 5-6 abstraction level; request more context; return `UNCLASSIFIED`—never force a hallucinated match. |
| **Ambiguous query (multiple Synapses)** | Run Stages 2–5 for both, take union, present both result sets with disambiguation note. |
| **No-edge conflict during assembly** | Template mode returns both as `UNRESOLVED_DIALECTIC` with a request to add a resolution. LLM mode asks the LLM to resolve as if the edge existed, then logs for edge promotion. |
| **Repeated conflict across contexts** | Same pair flagged 5+ times → `discovered` edge proposed in Phase B. |
| **Wisdom used but outcome degraded** | `outcome_score` below threshold after N runs → flagged for `EPISTEMIC_REVIEW`. |
| **Rare-but-catastrophic edge** | Rare-Edge Auditor (§8.3 Phase C) samples high-stakes pairs daily, independent of retrieval. |
| **Malicious wisdom injection** | Nodes with `epistemic_status: GHOST` or high `compliance_audit_required` hard-filtered from auto-application, require human review. |
| **Rapidly decaying knowledge** | `validity_decay.half_life_days` determines retirement; re-confirmation requires human `last_confirmed` update. |
| **New domain entry** | `DOMAIN_ENTRY_CALIBRATION` seeds sparse lattice; `UNCLASSIFIED` fallback covers transition. |
| **Governance failure** | Retrieved rule passes through Omega-style check before action. If blocked, action refused regardless of retrieval confidence. |
| **Synonym minting spike** | >5 PROVISIONAL hubs >0.9 similar → merge, run is-inside check, create canonical choice. |

---

## 11. VALIDATION PLAN

Every load-bearing claim must be measurable. This plan is ordered by cost-to-criticality ratio.

### 11.1 Applicability Gate Accuracy (Week 1–2) — Highest Priority

- Take the 850-wisdom corpus. Have one expert label 50 node-pairs as `conflict / complement / unrelated`.
- Run the Phase A structural checks against those 50 pairs. Report precision/recall of the deterministic conflict detector.
- Measure the LLM fallback (Layer 3) accuracy on the ambiguous cases.

### 11.2 Behavioral Graph Edge Quality (Week 3–4)

- After Phase A, measure what fraction of declared edges survive human review (detect over-broad declarations).
- After Phase B, measure the accuracy of `provisional_resolution` against expert-labeled resolutions on 50 collisions.

### 11.3 Wisdom Retrieval Correctness (Week 5–8) — Headline Result

- Build a 100-query test set with expert-judged gold-standard answers.
- Run the cascade. Measure Precision@3, Recall@3, conflict-response accuracy, abstraction-level correctness.
- This requires the most expert time (10–20 hours).

### 11.4 Operative Validity (Week 9–12, contingent on production)

- Run 50 tasks twice: once with `STABILIZE_PRIMARY_FIRST` retrieved, once suppressed.
- Compare downstream DAG success rates.
- **Commitment:** We publish the first operative validity measurement within 90 days of the reference implementation reaching 1,000 production queries.

### 11.5 Scaling Tests (Ongoing)

- Synthetic corpus at 10K, 100K, 1M nodes. Measure cascade latency at each scale. Validate O(log N).

### 11.6 Validation Prioritization

The experiments are ordered by cost-to-criticality ratio:

1. §11.1 (Applicability gate accuracy): 1 week. Highest priority. Validates the Stage 3 gate on the existing 850-node corpus with 50 expert-labeled node pairs.
2. §11.3 (Retrieval correctness): 2–3 weeks. The headline result. Requires a 100-query gold standard from domain experts.
3. §11.2 (Graph edge quality): 2 weeks. Runs in parallel with §11.3.
4. §11.5 (Scaling tests): 1 week. Synthetic corpus at 10K/100K/1M.
5. §11.4 (Operative validity): 3+ months, requires production deployment. Deferred until the reference implementation ships.

§11.1 and §11.5 should be completed before broad publication; the rest can be published as work-in-progress results.

---

## 12. WHY THIS IS NOT OVER-ENGINEERING

Is this a sledgehammer for a walnut? For **low-stakes, creative, exploratory tasks** — brand messaging, brainstorming, poetry, generic ad copy — **yes, absolutely over-engineered.** The LLM alone is sufficient. The fast path gate (§8.2) ensures the lattice never burdens them.

The lattice is justified exactly where **the cost of a wrong, unauditable decision exceeds the cost of the substrate.** The break-even analysis below is a *logic model*, not a cost model. Actuals depend on query volume, domain criticality, and infrastructure costs. Validated cost data will be published after the reference implementation reaches 1,000 production queries.

| Scenario | Cost of a wrong, unauditable LLM decision | Lattice per-query cost (illustrative) | Break-even (illustrative) |
|---|---|---|---|
| Surgery recall guidance | $5M–$50M liability + regulatory action | ~$0.01/query | 5–50 wrong decisions |
| Aviation checklist for autonomous systems | $1B+ single incident; certification requires audit trail | Same | 1 incident |
| Financial trading risk rule | $M+ per bad trade | Same | 100–1000 trades |
| Internal code review assistant | N/A | N/A | Never (fast path) |

The lattice is the simplest architecture that survives the specified edge cases and the legal-auditability requirement. The causal mechanism that makes it work is explicit: the cascade filters deterministically; the graph resolves conflicts from declared plus discovered knowledge; the anchors bridge the abstraction gap. That is engineering, not mysticism.

---

## 13. WHAT THIS ENABLES — THE COMPANION

Current copilots retrieve information. The Wisdom Lattice enables a **Companion** that:

- **Remembers** past decisions and their rationale (through the graph).
- **Argues against you** when you're about to violate a principle you've ratified.
- **Reconciles conflicting advice** by surfacing resolution logic—because it has encountered those conflicts before, in similar situations.
- **Knows when to say "I don't know"** — and produces a structured GapReport rather than a hallucinated guess.
- **Improves over time** — the graph learns situational conflicts; effective wisdoms are promoted; stale ones are retired.

The difference between a copilot and a mentor is not computational power—it is the *accumulation of experience*. The self-refining graph is the mechanism for that accumulation.

---

## 14. OPEN PROBLEMS

1. **JIT conflict detection accuracy.** The in-context check uses an LLM or co-satisfiability heuristic. Its accuracy at industrial scale is not yet measured. The validation plan (§11.1) addresses this, but the numbers are unknown.
2. **Operative validity.** The per-node effectiveness score is a proxy. True causal attribution (did this wisdom *cause* the improved outcome?) requires counterfactual A/B (§11.4), which is expensive and gated by policy. We propose it for the top-20 wisdoms, top-5 task types.
3. **Hub lifecycle pressure.** The is-inside check + usage thresholds manage growth, but the algorithm for deciding "genuinely novel" vs "synonym" requires semantic-threshold tuning. Calibration against the 850-node corpus is the short-term fix.
4. **Adversarial presence in JIT edge promotion.** What if a pair of rules should conflict but JIT never catches it because both are always overridden before reaching assembly? The Rare-Edge Auditor (Phase C) is the backstop, but its coverage is not yet validated.
5. **Ineffability boundary.** The lattice captures the behavioral core of wisdom, but some wisdom is *ineffable* — it resides in taste, judgment, or embodied experience that resists compression into Synapses. The lattice does not attempt to capture this, and it must be said plainly: this is a limitation, not a feature.

---

## 15. CONCLUSION

The Wisdom Lattice is the simplest architecture that survives the specified edge cases, scales to a billion nodes, and provides auditability and governance in high-stakes domains. It is buildable from day one with the existing 850-wisdom corpus, and it improves through operation.



---

*This is an Informational RFC. Reference implementation is Apache 2.0 open source. No vendor lock-in. The architecture is the standard, not the code.*
