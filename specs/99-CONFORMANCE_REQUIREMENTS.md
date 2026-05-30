# SGF Conformance Requirements v1.0 Final Candidate

## SGF Core conformance

A conforming SGF Core implementation must:

1. represent Synapses as one VerbHub plus many role-bound Spokes;
2. enforce the closed 15-role set;
3. preserve Synapse IDs distinct from Canonical IDs;
4. distinguish content_hash from content_fingerprint;
5. preserve SourceDocument, SourceSpan, or equivalent source/proof trace for exported objects;
6. support GapReport or equivalent failure reporting;
7. support SynapseGroup or equivalent addressable grouping;
8. preserve identity links without destructive merge by default;
9. preserve time/state/authority/provenance distinctions;
10. export SGF objects through HFF-compatible logical structure when crossing trust boundaries.

## GLEAN conformance

A conforming GLEAN implementation must:

1. ingest CleanTextBundle, not raw source directly;
2. preserve source span mapping;
3. perform entity and lexicon mapping before final Synapse assembly;
4. create candidate/extraction-decision trace or equivalent audit trail;
5. emit GapReports instead of fabricating missing grounding;
6. attach proof/provenance to produced SGF objects;
7. preserve quoted, reported, denied, hypothetical, and command/request/question structures without flattening them into world facts.

## HFF conformance

A conforming HFF implementation must:

1. declare HFF version and encoding profile;
2. preserve the HFF logical message model;
3. include lexicon hydration data for non-core terms;
4. include content hashes;
5. sign messages crossing trust boundaries when authenticity matters;
6. support replay prevention when used in live systems;
7. reject or quarantine invalid signatures, expired messages, hash mismatches, and missing required lexicons.

## AFP conformance

A conforming AFP implementation must:

1. distinguish act type from semantic role;
2. support single-act and multi-act envelopes;
3. support structured ERROR;
4. validate authority for command/cancel/high-risk acts;
5. distinguish ACK from ACCEPT and CONFIRM.

## Extension conformance

Extensions must:

1. use a namespace;
2. declare schema version;
3. declare field meanings with microglosses;
4. avoid redefining core Synapse grammar;
5. avoid adding core semantic roles;
6. include ExtensionManifest inline or by signed reference.

## Security profile conformance

A conforming HFF implementation that claims security-profile support must:

1. distinguish integrity, authenticity, authorization, freshness, and confidentiality;
2. never treat hash alone as proof of sender identity;
3. verify signatures against declared trust anchors;
4. reject or quarantine replayed or expired messages;
5. support signed public broadcast where confidentiality is not intended;
6. support encrypted direct or group delivery where confidentiality is required;
7. require AuthorityFrame and safety policy checks for high-risk commands.



## Multi-act and regulated transaction conformance

A conforming implementation that supports multi-act bundles must declare and enforce `bundle_atomicity_policy`.

A conforming implementation that supports regulated transactions must:

1. support idempotency keys or replay-safe transaction references;
2. distinguish signed instruction from executed transaction;
3. support approval policy and receipt policy;
4. validate authority, account, venue, and compliance context outside the message syntax;
5. reject duplicate execution of the same validly signed transaction instruction.
