# AFP Protocol Specification v1.0 Final Candidate

File: 02-WIRE-02_AFP_PROTOCOL_SPEC.md  
Layer: WIRE (acts and conversations)  
Status: Final Candidate

## Scope and intent

AFP is the act and conversation layer that sits on top of HFF.

- SGF Core structures grounded claims as Synapses, frames, and groups.
- HFF transports those SGF objects across trust boundaries.
- AFP declares **what is being done** with that content: inform, request, command, propose, accept, refuse, cancel, confirm, and so on.

HFF moves meaning. AFP acts with meaning.

AFP does not redefine SGF semantic roles. AFP act types are about illocutionary force and conversation state, not about who did what to whom inside a Synapse.

## Act types

AFP defines a closed set of act types for v1.0:

```text
INFORM
ADVISE
REQUEST
QUERY
COMMAND
PROMISE
PROPOSE
ACCEPT
REFUSE
CANCEL
CONFIRM
ACK
ERROR
```

These are illocution labels, not SGF roles.

- `INFORM` conveys information without requesting action.
- `ADVISE` recommends or warns.
- `REQUEST` asks another participant to perform an action.
- `QUERY` asks for information.
- `COMMAND` directs another participant to act, under authority.
- `PROMISE` commits the sender to a future action.
- `PROPOSE` offers a course of action or agreement for consideration.
- `ACCEPT` agrees to a proposal or request.
- `REFUSE` declines or rejects an act or proposal.
- `CANCEL` withdraws a prior act or proposal.
- `CONFIRM` records completion or verifies state.
- `ACK` acknowledges receipt, not agreement.
- `ERROR` reports protocol or validation failure.

## Single-act envelope

A single-act AFP message is carried inside an HFF payload but can be described at the AFP layer as having the following required fields:

```text
afp_version
afp_message_id
thread_id
sender_id
illocution
payload_ref
hff_payload
security_envelope
```

- `afp_version` identifies the AFP spec version (e.g., `1.0`).
- `afp_message_id` is the identifier for this act-level message within a thread.
- `thread_id` ties this act into an ongoing conversation or transaction.
- `sender_id` identifies the sender at the act layer (aligned with HFF `sender`).
- `illocution` is one of the AFP act types.
- `payload_ref` points to the SGF payload (Synapse, group, or bundle) that this act concerns.
- `hff_payload` is the enclosing HFF message or a reference to it.
- `security_envelope` points to or embeds the HFF integrity and security fields.

Recommended fields:

```text
recipient_ref
recipient_scope
conversation_transition
ack_required
deadline
authority_required
priority
```

- `recipient_ref` targets a specific participant.
- `recipient_scope` targets a class or broadcast scope.
- `conversation_transition` labels the state transition this act intends in the conversation.
- `ack_required` declares whether an ACK or CONFIRM is expected.
- `deadline` declares when a response or action is no longer useful.
- `authority_required` signals that AuthorityFrame validation is required before acting.
- `priority` hints at scheduling and queueing importance.

## Multi-act envelope

A single HFF message may carry multiple AFP acts that share a security envelope and transport cost. In that case, the AFP layer uses:

```text
acts[]
```

Each act in `acts[]` should include:

```text
act_id
illocution
conversation_transition
payload_ref
authority_required
ack_required
deadline
```

- `act_id` uniquely identifies the act within the message.
- `illocution` is the act type.
- `conversation_transition` describes how this act moves the conversation.
- `payload_ref` ties the act to specific SGF content.
- `authority_required` flags that authority must be validated before obeying.
- `ack_required` requests acknowledgment or confirmation.
- `deadline` sets timing expectations.

AFP allows senders to bundle related acts into one HFF message (for example, INFORM + REQUEST + ADVISE in an emergency broadcast) while keeping each act addressable and auditable.

## Conversation transitions

Act types describe *what* is being done. Conversation-transition labels describe *how the conversation state changes*.

AFP defines the following conversation-transition labels:

```text
PROPOSE
COUNTER
ACCEPT
EXECUTE
CONFIRM
REFUSE
ESCALATE
CANCEL
EXPIRE
ERROR
```

Act types and conversation transitions are related but not identical.

Examples:

- A `PROPOSE` act usually carries `conversation_transition = PROPOSE`.
- An `ACCEPT` act usually carries `conversation_transition = ACCEPT`.
- A `COMMAND` act might carry `conversation_transition = EXECUTE`.
- A `REFUSE` act carries `conversation_transition = REFUSE`.
- An `ERROR` act carries `conversation_transition = ERROR`.

Illegal transitions (for example, `EXECUTE` without any prior `ACCEPT` when a profile requires it) must return a structured `ERROR` act that explains which rule was violated.

## Deadlines, expiry, and incomplete conversations

`deadline` at the act level and HFF `expires_at` together define a validity window for an act.

- If no ACCEPT, REFUSE, CONFIRM, or ERROR is received before `deadline` (or `expires_at`, whichever is stricter), the sender **MAY** emit an EXPIRE act and **MUST** treat the original act as no longer actionable.
- Late ACCEPT or CONFIRM received after the validity window **MUST NOT** resurrect an expired or cancelled act. An implementation **MAY** treat such late responses as new proposals or simply REFUSE.
- Domain profiles with long communication delays (for example, deep-space probes) must choose deadlines and expiry windows appropriate to their latency, but those windows are still hard bounds for action.

Participants **MUST NOT** assume success from silence. Absence of CONFIRM means there is no protocol guarantee that the act was executed.

## Conversation failure modes

Conversations can fail because a counterparty stops responding (network loss, busy system, adversarial disappear), or because it sends inconsistent or malformed acts mid-thread.

Implementations:

- **SHOULD** track conversation state and emit ERROR or EXPIRE when a required response is missing or an illegal transition occurs.
- **MUST NOT** treat missing responses as implicit ACCEPT or CONFIRM.
- **MAY** implement retries and ESCALATE to human operators or safe-mode behavior as defined by domain profiles.

## Binding AFP to HFF security

AFP acts are always evaluated under the security context of the enclosing HFF message.

- Each AFP act’s `security_envelope` **MUST** correspond to exactly one HFF message whose security profile is appropriate for the act’s `illocution` and risk_class (when present).
- If HFF validation fails for a message (for example, schema error, invalid signature, untrusted `trust_anchor_ref`, expiry, replay, missing required lexicon), the AFP layer **MUST NOT** treat any contained acts as valid inputs to a reasoning graph or actuator.
- When HFF validation fails, implementations **SHOULD** emit an AFP `ERROR` act with a structured error reason that indicates the failure class, such as:
  - `HFF_SIGNATURE_INVALID`
  - `HFF_EXPIRED`
  - `HFF_REPLAY_DETECTED`
  - `HFF_UNTRUSTED_ANCHOR`
  - `HFF_MISSING_LEXICON`
  - `HFF_UNSUPPORTED_PROFILE`

Domain profiles may refine the error code taxonomy, but they must not reinterpret an HFF-layer failure as successful AFP ACCEPT or CONFIRM.

## Authority and safety

AFP is where **act type** and **authority** meet.

- `COMMAND`, `CANCEL`, high-risk `REQUEST`, and any act with real-world effect must be validated against an AuthorityFrame before execution.
- Authority is act-specific: a sender may be authorized to `INFORM` but not to `COMMAND`, or to command only within specific domains or jurisdictions.

The AuthorityFrame, interpreted under local policy, decides whether an authenticated sender is allowed to issue a specific act in a specific context. Signature alone is never sufficient for obedience.

## Receipts and acknowledgments

AFP distinguishes several receipt-related acts:

- `ACK` confirms that a message was received and parsed. It does **not** indicate agreement or execution.
- `CONFIRM` records that an act was completed or that a claimed state has been verified.
- `REFUSE` indicates that an act or proposal was rejected.
- `ERROR` reports protocol failure, invalid transition, missing lexicon, missing authority, validation failure, or unsafe action.

This separation lets systems distinguish:

- delivery vs. agreement,
- agreement vs. successful execution,
- refusal vs. technical error.

## Relationship to HFF and SGF

AFP acts always travel inside HFF messages.

- HFF provides the envelope: identity, integrity, freshness, confidentiality, and transport.
- AFP provides the illocution and conversation structure.
- SGF provides the meaning of the payload and AuthorityFrame.

An implementation that supports AFP must:

1. Parse AFP act types and conversation transitions.
2. Tie each act to SGF payload objects via `payload_ref`.
3. Tie each act to HFF security context via `security_envelope`.
4. Enforce authority and safety rules appropriate to the act type and domain.

AFP leaves storage, scheduling, and policy to the implementation; it standardizes the structure of acts so that different systems can coordinate using a shared conversation grammar.

---

## 8. Normative references

This specification defines the AFP act and conversation protocol that operates over HFF.

For related specifications:

- 01-SUBSTRATE-01_SGF_CORE_SPEC.md  
  Logical model for SGF Synapses, frames, and frames used as AFP payloads.

- 02-WIRE-01_HFF_WIRE_PROTOCOL_SPEC.md  
  HFF wire transport protocol that carries AFP messages.

- 02-WIRE-03_DISCOVERY_CAPABILITY_MANIFEST_SPEC.md  
  Discovery and capability manifests that describe AFP-capable endpoints.

- 03-OMEGA-01_LANGUAGE_SPEC.md  
  Omega governance language overview for deployments that govern AFP acts with Omega-Code.
