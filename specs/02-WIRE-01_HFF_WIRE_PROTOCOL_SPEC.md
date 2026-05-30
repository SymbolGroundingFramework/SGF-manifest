# HFF Wire Protocol Specification v1.0 Final Candidate

File: 02-WIRE-01_HFF_WIRE_PROTOCOL_SPEC.md  
Layer: WIRE (transport)  
Status: Final Candidate

## Scope and intent

HFF is the wire protocol for moving SGF objects across trust boundaries.

- SGF Core defines what a grounded claim looks like (Synapses, frames, proof, lexicon).
- GLEAN defines how those structures are extracted from sources.
- HFF defines how those structures travel between machines so that a receiver can decide whether to admit them.

HFF does **not**:

- Redefine SGF Core or its roles.
- Dictate transport (HTTP, V2X radio, satellite, etc.).
- Decide what a receiver must do with a valid message; receiver sovereignty and safety policy live outside the wire.

HFF’s job is to carry “portable context”: enough structure, provenance, lexicon, and security material for a receiver who shares SGF and HFF to evaluate a message on arrival without private side agreements.

## Logical message model and encodings

An HFF message is a **logical object** with a fixed shape. Encodings are skins; they must not change meaning.

The canonical text encoding for HFF 1.0 is:

```text
application/hff+json
```

Other encodings may exist, for example:

```text
application/hff+cbor
application/hff+msgpack
application/hff+binary
```

An alternate encoding profile is conformant only if:

- It preserves the HFF logical message model.
- It declares its canonicalization rules and hash/signature byte conventions.
- It preserves lexical hydration semantics.
- It round-trips to canonical HFF JSON without semantic loss.

JSON is the **reference form** for debugging, audit, and cross-implementation comparison; binary profiles exist for constrained hardware and latency-sensitive deployments.

## Envelope fields

Every HFF message has a top-level **envelope** and a **payload**. The envelope carries identity, version, integrity, and security context. The payload carries SGF objects and, optionally, AFP acts.

### Required envelope fields

A conforming HFF 1.0 message must include:

```text
hff_version
encoding_profile
message_id
created_at
sender
payload
integrity
```

- `hff_version` identifies the HFF spec version (e.g., `1.0`).
- `encoding_profile` declares the actual byte encoding (canonical JSON, CBOR profile, etc.).
- `message_id` is a unique identifier for replay detection and receipts.
- `created_at` records when the message was formed, not when it is received.
- `sender` identifies the sending participant in a way that can be checked against Discovery manifests and trust anchors.
- `payload` carries SGF objects and acts.
- `integrity` carries hashes, signatures, and related security metadata.

### Recommended envelope fields

Most deployments should also include:

```text
recipient_ref
recipient_scope
expires_at
nonce
conversation_id
schema_version
sgf_core_version
core_lexicon_release
trust_anchor_ref
```

- `recipient_ref` addresses a specific receiver (ID or endpoint).
- `recipient_scope` addresses a class such as `vehicles_within_800m_ahead`.
- `expires_at` bounds freshness; messages past expiry must not be admitted.
- `nonce` and a receiver-side replay cache prevent simple replays inside the validity window.
- `conversation_id` ties related messages, especially when AFP is in use.
- `schema_version` and `sgf_core_version` identify which SGF/HFF definitions governed the payload.
- `core_lexicon_release` identifies the Core Lexicon version used to ground terms.
- `trust_anchor_ref` points at the trust root the receiver should use to evaluate keys and certificates.

### Communication patterns

HFF supports all common communication patterns:

- 1:1 and M:1 use `recipient_ref` to target a specific participant.
- 1:M and M:M use `recipient_scope` (and optionally group-related keys) to target a scoped broadcast or group.

Security profiles constrain how these patterns are used (for example, PUBLIC_SIGNED_BROADCAST with `recipient_scope` for emergency road alerts, HIGH_RISK_COMMAND plus CONFIDENTIAL_GROUP for weapon swarms). The admission pipeline—integrity, authenticity, authorization, freshness, confidentiality, and hydration—applies identically regardless of party count; only profiles and local policy differ.

## Payload content

The payload is an SGF-shaped bundle. It may contain:

```text
synapses
synapse_groups
synapse_links
synapse_group_links
frames
source_documents
proof_traces
gap_reports
lexicon_manifest
acts
```

- Synapses, groups, links, and frames carry structured meaning.
- SourceDocuments, SourceSpans, and ProofTraces carry provenance and derivation.
- GapReports make missing grounding explicit instead of silently fabricating structure.
- `lexicon_manifest` carries dependency material for non-core terms.
- `acts` are AFP acts when HFF is also carrying the act layer.

### Multi-act payloads

When an HFF message carries multiple AFP acts, the payload should include:

```text
payload.acts[]
```

Each act entry includes at least:

```text
act_id
illocution
payload_ref
ack_required
deadline
authority_required
```

AFP defines the vocabulary of `illocution`, conversation transitions, and receipt semantics; HFF simply carries these acts and ties them to the security envelope and SGF payload.

## Lexical hydration requirements

An HFF message must be **lexically hydratable** at the receiver.

- All SGF objects in the payload must use Canonical IDs from the Core Lexicon or from declared non-core lexicons.
- For non-core terms, the sender must include either:
  - Inline `lexicon_manifest` entries, or
  - References to external scoped lexicons with URI, version, hash, and signature.

If a receiver cannot hydrate a term from the Core Lexicon plus the manifests and references in the envelope, it must **refuse, quarantine, or request additional material**, rather than guessing.

Hydration is part of admissibility: a structurally valid HFF message that cannot be hydrated is **semantically invalid** for that receiver.

## Security envelope and the five questions

HFF separates five questions that are often collapsed:

| Layer           | Question                             |
|-----------------|--------------------------------------|
| Integrity       | Did the content change?              |
| Authenticity    | Who signed this message?             |
| Authorization   | Is that sender allowed to do this?   |
| Freshness       | Is this current, or a replay?        |
| Confidentiality | Who is allowed to read it?           |

Different fields and mechanisms answer different questions:

- **Integrity**: `content_hash`, `payload_hash`.
- **Authenticity**: `signature`, `key_id`, `trust_anchor_ref`.
- **Authorization**: AuthorityFrame referenced from acts and local policy.
- **Freshness**: `created_at`, `expires_at`, `nonce`, receiver’s replay cache, and `replay_window`.
- **Confidentiality**: `encryption_envelope`, `encryption_profile`, key references.

No single cryptographic primitive answers all five.

### Minimum security fields

For messages crossing trust boundaries, an HFF message should carry at least:

```text
sender_id
recipient_ref or recipient_scope
message_id
created_at
expires_at
nonce
schema_version
core_lexicon_release
payload_hash
content_hash
signature
key_id
trust_anchor_ref
canonicalization_profile
encoding_profile
```

High-risk machine coordination adds:

```text
authority_frame_id
risk_class
ack_required
safety_profile
receipt_policy
replay_window
revocation_check
```

### Signing rule

The sender signs the canonical bytes of the HFF logical message under the declared canonicalization and encoding profile.

A receiver verifying an HFF message should, in order:

```text
check schema and HFF version
check canonicalization profile
check payload_hash and content_hash
verify signature
check key validity and trust anchor
check expiry window and replay cache
hydrate lexicons for non-core terms
evaluate AuthorityFrame and local policy when acts request action
```

Messages that fail a required gate must be rejected or quarantined according to profile; they must not silently degrade into best-effort behavior.

### Late and stale messages

`expires_at` and any profile-specific `replay_window` define a validity window for admitting and acting on an HFF message.

- A message whose `expires_at` is in the past **MUST** be rejected or quarantined, even if it was originally part of a valid conversation.
- Late ACK, CONFIRM, or ERROR messages received after expiry **MAY** be logged for audit but **MUST NOT** trigger renewed execution or state changes.

In particular, stale PUBLIC_SIGNED_BROADCAST and HIGH_RISK_COMMAND messages must not be obeyed simply because they are freshly replayed and have valid signatures.

## Security profiles

HFF defines reusable **security profiles** that specify which gates are mandatory for a given kind of message. The profile decides which questions must be answered at the wire; local policy can always demand more.

### PUBLIC_SIGNED_BROADCAST

Use for public, integrity-sensitive broadcasts: emergency vehicle advisories, hazard warnings, public road alerts, public capability announcements.

Required:

```text
signature
key_id
trust_anchor_ref
created_at
expires_at
nonce
payload_hash
recipient_scope
```

Encryption is normally **not** used; confidentiality would defeat the purpose of a public broadcast. Anti-spoofing comes from signature verification, trust_anchor validation, expiry, replay prevention, and plausibility checks.

### CONFIDENTIAL_DIRECT

Use for financial, legal, medical, commercial, military, or other messages intended for specific recipients.

Required:

```text
signature
key_id
trust_anchor_ref
payload_hash
encryption_envelope
recipient_ref
created_at
expires_at
nonce
```

The `encryption_envelope` ensures that only authorized recipients can read the payload, independent of which transport is used.

### CONFIDENTIAL_GROUP

Use for swarms, fleets, teams, or organizations where a group is authorized to read the message.

Required:

```text
signature
key_id
trust_anchor_ref
payload_hash
encryption_envelope
recipient_scope
group_key_ref or key_distribution_ref
created_at
expires_at
nonce
```

Group membership, key rotation, and revocation are handled by the deployment’s trust infrastructure, not by HFF itself.

### HIGH_RISK_COMMAND

Use for commands that can move vehicles, drones, weapons, robots, medical devices, money, or critical infrastructure.

Required:

```text
signature
key_id
trust_anchor_ref
payload_hash
authority_frame_id
risk_class
safety_profile
ack_required
receipt_policy
created_at
expires_at
nonce
replay_window
revocation_check
```

Encryption is recommended unless signed public command broadcast is explicitly required by the domain profile.

High-risk receivers must not act merely because a message is authentic. They must also validate authority, local policy, safety constraints, mission state, and current world state before obeying.

## Encryption envelope

When confidentiality is required, HFF uses an **encryption envelope** within the message structure.

Recommended fields:

```text
encryption_profile
encrypted_payload_ref
content_key_ref
recipient_key_refs
key_agreement_profile
encrypted_fields
unencrypted_headers
```

- `encryption_profile` identifies the cryptographic suite and mode.
- `encrypted_payload_ref` points to the encrypted bytes (inline or external).
- `content_key_ref` and `recipient_key_refs` describe how content keys are distributed.
- `encrypted_fields` and `unencrypted_headers` clarify which parts of the message remain visible for routing and profile selection.

HFF does not mandate a single cryptographic library; implementations must use modern, audited primitives and declare them in `encryption_profile`.

## Cryptographic profiles and downgrade resistance

HFF does not mandate a single global cryptographic suite, but high-risk and regulated deployments MUST adopt a declared cryptographic profile and enforce it consistently.

At minimum:

- Implementations **MUST NOT** use deprecated or known-weak algorithms or key sizes in any profile that carries HIGH_RISK_COMMAND or CONFIDENTIAL_* messages.
- Implementations **SHOULD** define one or more named cryptographic profiles (for example, `HFF_CRYPTO_PROFILE_1`) that specify:
  - key types and minimum key sizes,
  - signature algorithms,
  - hash algorithms,
  - key-agreement and encryption algorithms where `encryption_envelope` is used.
- Each HFF message carrying a profile-sensitive payload SHOULD declare its cryptographic profile in `encryption_profile` or a profile-specific header, so receivers can enforce local policy.

Downgrade resistance:

- When a sender and receiver have previously communicated using a given combination of `schema_version`, `sgf_core_version`, and `core_lexicon_release` under a particular `trust_anchor_ref`, receivers **SHOULD NOT** silently accept messages from the same sender key that claim materially older schema or lexicon versions without an explicit local-policy decision.
- Implementations **SHOULD** treat unexpected version regressions from a previously-seen key as lower-trust and MAY require additional validation, quarantine, or operator review.


## Receiver decision rule

Before admitting any HFF/AFP message into a reasoning graph or taking real-world action, a receiver should answer, in order:

```text
Is the message well-formed under the declared schema and HFF version?
Do hashes match the payload?
Is the signature valid under a trusted key?
Is the message fresh (expiry and replay checks)?
Is the sender authorized for the requested act and risk class?
Can all terms be hydrated from known lexicons and manifests?
Does local policy allow this action?
Does the safety profile pass given current mission and world state?
Does the action remain plausible given sensor data and context?
```

Failure at any required step must result in rejection, quarantine, or downgrade according to profile. A signed, fresh, well-formed message is a **candidate** for admission, not an instruction to obey.

## Examples (normative structure, non-normative content)

HFF examples in the spec should mirror compact patterns rather than catalog every domain.

- A **vehicle emergency broadcast**: a PUBLIC_SIGNED_BROADCAST message with multiple AFP acts (INFORM, REQUEST, ADVISE) and an open `recipient_scope` for nearby vehicles.
- A **weapon or high-risk actuator command**: a HIGH_RISK_COMMAND message with CONFIDENTIAL_DIRECT or CONFIDENTIAL_GROUP, an AuthorityFrame reference, and a safety profile that must pass before action.

In all cases, HFF proves what was sent and who signed it. It never claims that the content is true, current, authorized, or safe to act on. Those questions are answered by SGF, AFP, Discovery, local policy, and governance layers, not by the wire itself.

---

## 9. Normative references

This specification defines the HFF wire protocol for transporting SGF objects across trust boundaries.

For related specifications:

- 01-SUBSTRATE-01_SGF_CORE_SPEC.md  
  Logical model for SGF Synapses, frames, and Core Lexicon integration.

- 01-SUBSTRATE-02_LEXICON.md  
  Core Lexicon data model, canonical IDs, and grounding relations.

- 02-WIRE-02_AFP_PROTOCOL_SPEC.md  
  Act and conversation layer over HFF.

- 02-WIRE-03_DISCOVERY_CAPABILITY_MANIFEST_SPEC.md  
  Participant and capability discovery manifest.

- 03-OMEGA-01_LANGUAGE_SPEC.md  
  Omega governance language overview for deployments that govern HFF/AFP with Omega-Code.
