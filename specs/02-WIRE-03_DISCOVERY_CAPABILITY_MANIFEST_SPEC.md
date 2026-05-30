# Discovery and Capability Manifest Specification v1.0 Final Candidate

File: 02-WIRE-03_DISCOVERY_CAPABILITY_MANIFEST_SPEC.md  
Layer: WIRE (discovery and capabilities)  
Status: Final Candidate

## Scope and intent

Discovery and Capability Manifests let SGF participants find each other, learn what each other can do, and decide whether to trust and talk to one another.

- SGF Core structures meaning.
- HFF carries SGF objects across trust boundaries.
- AFP declares acts over that meaning.
- Discovery tells participants **who is present**, **what versions and profiles they support**, **which lexicons and packs they can speak**, **where to send messages**, and **which trust anchors and limits apply**.

Discovery does not define SGF meaning and does not move payloads. It provides the metadata needed to *establish* HFF/AFP communication.

## Discovery location

Participants that support HTTP-based discovery should expose a capability manifest at:

```text
.well-known/graph
```

Other transports may define equivalent, profile-specific discovery locations. The manifest content remains the same logical structure.

## Capability Manifest fields

A Capability Manifest describes a single participant.

### Required fields

```text
participant_id
supported_sgf_versions
supported_hff_versions
supported_afp_versions
endpoints
```

- `participant_id` is the stable identifier for this participant.
- `supported_sgf_versions` lists SGF Core versions the participant can understand.
- `supported_hff_versions` lists HFF protocol versions it can speak.
- `supported_afp_versions` lists AFP protocol versions it supports.
- `endpoints` describes where to send HFF/AFP messages (for example, URLs, URIs, radio channels), with protocol and profile hints.

### Recommended fields

```text
supported_encoding_profiles
supported_lexicons
supported_knowledge_packs
capabilities
trust_anchors
auth_methods
rate_limits
max_payload_size
supported_act_types
supported_domain_profiles
```

- `supported_encoding_profiles` lists HFF encoding profiles (for example, JSON, CBOR) the participant accepts.
- `supported_lexicons` lists Core and domain lexicon releases it can hydrate.
- `supported_knowledge_packs` lists Knowledge Packs it recognizes by ID and version.
- `capabilities` describes functional roles (for example, vehicle, drone, trading engine, medical device, agentic assistant).
- `trust_anchors` identifies CA roots, key registries, or authority registries the participant trusts.
- `auth_methods` describes how the participant authenticates peers (for example, mTLS, signed HFF, OAuth at the gateway).
- `rate_limits` describes acceptable message rates for different classes of peers.
- `max_payload_size` sets upper bounds on message size.
- `supported_act_types` lists AFP act types the participant will accept (for example, accepts INFORM and REQUEST but not COMMAND).
- `supported_domain_profiles` lists domain-specific profiles (for example, automotive V2X, medical device, regulated transaction) the participant implements.

Manifests may include additional extension fields under namespaced keys. Extensions must not redefine the meaning of core fields.

## Broadcast scope and temporary identity

Some systems are mobile, short-lived, or privacy-sensitive. Discovery supports these cases through temporary identity and broadcast scopes.

Mobile participants may use:

```text
temporary_participant_id
recipient_scope
broadcast_scope
capability_manifest
trust_anchor
credential_or_certificate
expiry_window
replay_prevention
```

- `temporary_participant_id` provides a short-lived identifier instead of a permanent `participant_id`.
- `recipient_scope` identifies which receivers a message targets (for example, `vehicles_within_800m_ahead`).
- `broadcast_scope` describes a wider anonymous broadcast domain (for example, all vehicles in a region).
- `capability_manifest` can be carried or referenced to describe capabilities on the fly.
- `trust_anchor` and `credential_or_certificate` allow receivers to validate the temporary participant.
- `expiry_window` bounds how long the temporary identity and its manifest remain valid.
- `replay_prevention` specifies how receivers should treat replays (for example, nonce rules, cache duration).

### Recipient scope examples

Examples of `recipient_scope` strings include:

```text
vehicles_within_800m_ahead
drones_in_formation_alpha
robots_in_warehouse_zone_12
agents_in_contract_thread_TH-92
```

Exact semantics of scopes are domain-profile specific, but they must be precise enough for receivers to decide whether they are in scope.

## Trust evaluation

Publishing a Capability Manifest does not itself entitle a participant to be trusted.

- Receivers **MUST** evaluate `trust_anchors`, credentials, and, where applicable, revocation status before treating a manifest as trusted for any role.
- Implementations **SHOULD** treat mismatches between manifest claims (such as capabilities or roles) and observed behavior as grounds for downgrading or revoking trust.
- Domain profiles decide how to classify participants (for example, friend, neutral, enemy) and which roles they are allowed to exercise.

In adversarial scenarios (for example, prank emergency broadcasters or hostile swarm nodes), receivers rely on Discovery manifests plus HFF security to refuse acts from participants whose manifests and keys are not trusted for the claimed roles.

## Relationship to SGF, HFF, and AFP

Discovery is the **prelude** to SGF communication:

- SGF defines the meaning structures that will be exchanged.
- HFF defines how those structures travel.
- AFP defines what acts are being performed with that meaning.
- Discovery defines how participants find each other and what protocol surface they offer.

A typical flow:

1. A receiver fetches or receives a Capability Manifest.
2. It checks `participant_id`, supported versions, encoding profiles, lexicons, and `trust_anchors`.
3. It decides whether this participant is eligible to communicate under local policy.
4. If eligible, it uses `endpoints` and the declared profiles to establish HFF/AFP exchange.

Discovery does not override receiver sovereignty. A participant may publish a manifest; other participants remain free to ignore it.

## Minimal manifest example (conceptual)

A minimal manifest for a vehicle might include:

```text
participant_id
supported_sgf_versions
supported_hff_versions
supported_afp_versions
endpoints
supported_encoding_profiles
supported_lexicons
trust_anchors
supported_act_types
supported_domain_profiles
```

This is enough for nearby receivers to know:

- which protocol versions they can use,
- which lexicons and packs they can reference,
- where to send HFF messages,
- which act types the vehicle will understand,
- which `trust_anchors` govern its keys.

Discovery plus HFF/AFP allows strangers to coordinate without bespoke API documents. The manifest replaces informal integration docs with a machine-readable declaration of protocol, capability, and trust surface.

## Trust anchors, authentication, and key binding

Capability Manifests describe which trust anchors and authentication methods a participant uses; HFF messages carry concrete keys and signatures.

- `trust_anchors` in a manifest **MUST** be sufficient for receivers to validate the certificates or public keys referenced by `key_id` and `trust_anchor_ref` in HFF messages from that participant.
- `auth_methods` **MUST** accurately describe how participants authenticate each other at the transport or HFF layer (for example, mTLS on a given endpoint, signed HFF over an unauthenticated transport, or a gateway that terminates higher-level auth).
- Receivers **SHOULD** cache manifests for performance, but **MUST** re-check revocation status and any domain-specific constraints before trusting a manifest for high-risk decisions.

Identity strength:

- Messages that can cause high-risk physical, financial, or safety effects (for example, HIGH_RISK_COMMAND or equivalent domain profiles) **MUST NOT** be admitted based solely on `temporary_participant_id` without a strong credential binding to a trusted anchor, unless a domain profile explicitly allows this and defines additional safeguards.
- Long-lived identities bound to attestations or authority registries SHOULD be preferred for high-risk commands and regulated transactions.

This binding between Discovery manifests and HFF keys ensures that manifest declarations are not purely advisory: they are anchored to the same trust fabric that secures messages on the wire.

---

## 7. Normative references

This specification defines the Discovery and Capability Manifest used to describe participants, capabilities, and related metadata.

For related specifications:

- 01-SUBSTRATE-01_SGF_CORE_SPEC.md  
  Logical model for the SGF objects referenced in capability descriptions.

- 02-WIRE-01_HFF_WIRE_PROTOCOL_SPEC.md  
  HFF wire transport protocol used to move manifests and related messages.

- 02-WIRE-02_AFP_PROTOCOL_SPEC.md  
  AFP protocol used to request, advertise, and negotiate capabilities.

- 03-OMEGA-01_LANGUAGE_SPEC.md  
  Omega governance language overview for deployments that govern capability use and admission.
