# RFC-001: The Wisdom Lattice (V2.2 — Final)

**Status:** Proposed  
**Category:** Informational / Behavioral Standards  
**Author:** [Authors]  
**Date:** 2026-08-09  
**Replace:** V2.1

---

## ABSTRACT

The wisdom bottleneck is not harvesting—it is findability at scale. This RFC specifies the Wisdom Lattice: a three-component architecture (Harvest Pipeline, Retrieval Cascade, Behavioral Graph) for converting human behavioral text into retrievable, auditable machine wisdom. The Lattice resolves the paradox that defeats naive RAG and LLM-only approaches: abstract wisdom has no home in vector space, but concrete anchors do. It uses a **two-source behavioral graph**—declared structural edges plus operationally discovered edges—so conflict resolution is correct from day one and refined by experience. It is not a replacement for the LLM; it is the constitutional layer that makes a brilliant advisor bounded by auditable, provenance-tracing, governable law.

---

## 1. THE THESIS

> Wisdom is not knowledge; it is a behavioral response pattern triggered by a structural situation. Retrieval is not semantic search; it is structural pattern-matching followed by deterministic cascaded filtering. The behavioral graph that governs conflict is the most load-bearing structure in the system. It must be **bootstrapped from declared structural properties** (inverse actions, incompatible desired states, trigger contradictions) and **continuously refined through operational experience** (novel situational conflicts discovered at retrieval time). Neither alone is sufficient.

---

## 2. THE PROLEM: WHY THE LLM ALONE FAILS

The LLM alone has four structural liabilities that fine-tuning, prompting, and RLHF cannot fix:

1. **It cannot prove it applied your protocol.** A black box. No audit trail.
2. **It cannot trace provenance.** It cannot distinguish an FDA label from a forum post.
3. **It cannot refuse structurally.** Guardrails are prompt-based and overridable.
4. **It cannot resolve priority deterministically.** It averages, it does not adjudicate.

These are not bugs. They are architectural properties of next-token prediction. The Wisdom Lattice is the substrate that makes wisdom visible, auditable, and governable when failure is costly.

---

## 3. TERMINOLOGY

| Term | Definition |
|---|---|
| **Wisdom Node** | Atomic unit of the lattice: one rule, with Synapse fingerprint, behavioral skeleton, representation anchors, and evolving edges. |
| **Synapse (SGF)** | Verb-hub plus 15 role-bound spokes grounded in the Synapedia. Structural fingerprint. |
| **Representation Anchor** | Concrete, cross-domain, Level 1–2 instance sentence that embeds well. |
| **Behavioral Graph** | Nodes + edges. Edges are declared (structural) or discovered (situational). |
| **Master Hub Enum** | Closed, version-controlled set of canonical hub verbs grounded in the Synapedia, with a lifecycle (PROVISIONAL → STANDARD). |
| **Retrieval Cascade** | Ordered filter: graph routing → applicability gate → vector similarity on subset → context + graph traversal → LLM assembly. |
| **Lattice Lifecycle** | The states and transitions of a wisdom node: HARVEST → DRAFT → RETRIEVE → CONFIRM → GRADUATE → RETIRE. |

---

## 4. THE DERIVATION CHAIN

**Why the Synapse?** Abstract wisdoms share behavioral structure but zero semantic surface. Remove it; retrieval degenerates to keyword proximity.

**Why concrete anchors?** Abstract rules have no vector home. The anchor drags the rule into vector space. Remove them; retrieval cannot bridge the abstraction gap.

**Why the cascade?** A billion nodes cannot enter an LLM context or full vector index. The cascade keeps the LLM at 20 nodes. Each stage is cheaper than the last.

**Why the two-source behavioral graph?** Conflicts have two natures:
- **Structural** (declared): Opposing action sequences on the same problem conflict *by definition*.
- **Situational** (discovered): `OVER_PRECAUTION` and `STABILIZE_FIRST` conflict only when the actor is anxiety-prone. These can only be learned from retrieval.

Removing either source leaves the graph brittle or collision-dependent.

---

## 5. THE WISDOM NODE SCHEMA

*(As in V2.1 — unchanged. Abstraction ladder pre-generated, SGF Synapse grounded in Synapedia, `causal_logic` captured, `contextual_frame` first-class.)*

---

## 6. THE HARVEST PIPELINE

*(As in V2.1 — 5 LLM calls per node + 1 batch Graph Bootstrap call. Abstraction ladder pre-generated, not parametric.)*

---

## 7. THE RETRIEVAL CASCADE

*(As in V2.1 — the 3-layer applicability gate, orchestrator-declared fast path, deterministic filters, and a single LLM assembly call. Unchanged.)*

---

## 8. KEY DESIGN DECISIONS

### 8.1 Applicability Gate: 3-Layer Hybrid

Layer 1 — deterministic keyword match. Layer 2 — boolean logic composition (AND/OR/NOT). Layer 3 — LLM fallback on <20% of ambiguous candidates. Concrete, auditable, measurable.

### 8.2 Fast Path: Orchestrator-Declared Quality Tier

The fast/slow distinction is the `quality_tier` field from the DAG planner. No inference. No LLM call.

### 8.3 Behavioral Graph: Two-Source Bootstrap

**Phase A — Structural Declaration (zero LLM cost, pre-seeded at harvest)**

| Check | Method | Edge Type |
|---|---|---|
| **Action Inversion** | Two rules in the same problem-cluster whose action sequences are **circular permutations** of each other (A's last step is B's first, and vice versa) or whose **first step** matches but the **second step** triggers the other's `anti_triggers`. | `conflicts_with` |
| **Desired-State Exclusion** | Reachable states from `desired_state` are mutually exclusive (cold vs. warm, contained vs. exposed). | `conflicts_with` |
| **Trigger Contradiction** | A's `triggers` name a state that B's `anti_triggers` names, and vice versa. | `conditional_override` with provisional resolution |

Full action-sequence inversions are easy. Partial inversions are only declared conflict if they meet the second-step/anti-trigger criterion—everything else is a candidate for LLM-assisted classification during Phase B.

**Phase B — Operational Discovery (contextual JIT at retrieval)**

1. If assembly resolves a conflict without a declared edge, flag the pair.
2. Same pair collides in 5+ distinct query contexts → propose a `discovered` edge.
3. Tag with `provisional_resolution` extracted from the most common resolution path.
4. Promote to `VETTED` after 10+ clean resolutions or human review.

**Phase C — Hybrid Merge and Rare-Edge Backstop**

- Declared edges are ground truth. Discovered edges cannot override them.
- If a discovered edge contradicts a declared edge → `CROSS_TRUST_CONFLICT`, escalate to human review.
- **Rare-edge backstop: The Supreme Court Auditor.** Runs daily as a background task. Stratified sampling: 10% high-stakes nodes, 30% medium, 60% low. Uses the same Phase A structural checks (deterministic, cheap) to test up to 10,000 random pairs per run. Discovered conflicts enter Phase B's lifecycle as proposed `discovered` edges. This catches rare-but-catastrophic conflicts that operational learning would miss.

### 8.4 Abstraction Ladder: Pre-Generate at Harvest

As in V2.1. Six levels stored. Retrieval-time LLM call eliminated.

### 8.5 Master Hub Enum Lifecycle

PROVISIONAL → STANDARD → RETIRED. Governed by usage thresholds, hyponym check, semantic-similarity dedup.

---

## 9. THE LATTICE LIFECYCLE

```
  ┌─────────┐   harvest   ┌───────┐   retrieve   ┌──────────┐
  │ HARVEST │────────────▶│ DRAFT │─────────────▶│ RETRIEVE │
  └─────────┘             └───────┘              └──────────┘
                                │                      │
                                │                      │
                                ▼                      ▼
                          ┌──────────┐          ┌───────────┐
                          │  CONFIRM │◀─────────│ RETRIEVE  │
                          └──────────┘          └───────────┘
                                │
                                │ (retrieved N times, outcome improved)
                                ▼
                          ┌───────────┐     decay   ┌────────┐
                          │ GRADUATE  │────────────▶│ RETIRE │
                          └───────────┘             └────────┘
```

| State | Transitions |
|---|---|
| **HARVEST** | Raw wisdom text ingested. |
| **DRAFT** | Plausible but unvetted. Available for retrieval, flagged as unconfirmed. |
| **RETRIEVE** | Actively returned by the cascade. |
| **CONFIRM** | Human or policy review confirms the wisdom is correct and reliable. |
| **GRADUATE** | Promoted to `vetted` status. Full retrieval weight. Candidate for Omega rule. |
| **RETIRE** | Validity decay triggered, or superseded, or no longer retrieved. Archived, not deleted. |

---

## 10. EDGE CASES

*(As in V2.1 — with the rare-edge backstop moved into the graph construction section and explicitly specified in §8.3.)*

---

## 11. VALIDATION PLAN (Prioritized)

This plan is concrete, measurable, and ordered by value-per-effort.

### 11.1 Applicability Gate Accuracy (Week 1–2)

- Take the 850-wisdom corpus. Have one expert label 50 node-pairs as `conflict / complement / unrelated`.
- Run the Phase A structural checks against those 50 pairs. Report precision/recall of the deterministic conflict detector.
- Measure the LLM fallback (Layer 3) accuracy on the ambiguous cases.

### 11.2 Behavioral Graph Edge Quality (Week 3–4)

- After Phase A, measure what fraction of declared edges survive human review (detect over-broad declarations).
- After Phase B, measure the accuracy of `provisional_resolution` against expert-labeled resolutions on 50 collisions.

### 11.3 Wisdom Retrieval Correctness (Week 5–8)

- Build a 100-query test set with expert-judged gold-standard answers.
- Run the cascade. Measure Precision@3, Recall@3, conflict-response accuracy, abstraction-level correctness.
- This is the headline result. It requires the most expert time (10–20 hours).

### 11.4 Operative Validity (Week 9–12)

- Run 50 tasks twice: once with `STABILIZE_PRIMARY_FIRST` retrieved, once suppressed.
- Compare downstream DAG success rates.
- **Commitment:** We publish the first operative validity measurement within 90 days of the reference implementation reaching 1,000 production queries.

### 11.5 Scaling Tests (Ongoing)

- Synthetic corpus at 10K, 100K, 1M nodes. Measure cascade latency at each scale. Validate O(log N).

---

## 12. WHY THIS IS NOT OVER-ENGINEERING

**Is this a sledgehammer for a walnut?** For low-stakes, creative, exploratory tasks—brand messaging, brainstorming, poetry, generic ad copy—**yes, absolutely over-engineered.** The LLM alone is sufficient. The fast path gate (§8.2) ensures the lattice never burdens them.

The lattice is justified exactly where the cost of a wrong, unauditable decision exceeds the cost of the substrate.

> **Note:** The table below is a *logic model*, not a cost model. The actual break-even point depends on deployment-specific factors (query volume, domain criticality, infrastructure costs). We will publish validated cost data after the reference implementation is deployed.

| Scenario | Cost of a wrong, unauditable LLM decision | Lattice per-query cost (illustrative) | Break-even (illustrative) |
|---|---|---|---|
| Surgery recall guidance | $5M–$50M liability + regulatory action | ~$0.01/query | 5–50 wrong decisions |
| Aviation checklist for autonomous systems | $1B+ single incident; certification requires audit trail | Same | 1 incident |
| Financial trading risk rule | $M+ per bad trade | Same | 100–1000 trades |
| Internal code review assistant | N/A | N/A | Never (fast path) |

---

## 13. WHAT THIS ENABLES — THE COMPANION

Current copilots retrieve information. The Wisdom Lattice enables a Companion that:

- Remembers past decisions and rationale (through the graph).
- Argues against you when you're about to violate a ratified principle.
- Reconciles conflicting advice—because it has encountered those conflicts before.
- Knows when to say "I don't know" (structured GapReport, not hallucination).
- Improves over time: situational conflicts learned, effective wisdoms promoted, stale ones retired.

The difference between a copilot and a mentor is not computational power—it is the accumulation of experience. The self-refining graph is that mechanism.

---

## 14. OPEN PROBLEMS (Honest Acknowledgment)

1. **JIT conflict detection accuracy.** The in-context check uses an LLM or co-satisfiability heuristic. Accuracy at industrial scale is unmeasured. Validation plan §11.1 addresses this.
2. **Operative validity.** The per-node effectiveness score is a proxy. True causal attribution requires counterfactual A/B (§11.4), which is expensive and policy-gated.
3. **Hub lifecycle pressure.** The is-inside check + usage thresholds manage growth, but the semantic-threshold tuning for "novel vs synonym
