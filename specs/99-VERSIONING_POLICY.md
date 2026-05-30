# SGF Versioning and Extension Policy v1.0 Final Candidate

## Semantic versioning

Use:

```text
MAJOR.MINOR.PATCH
```

Major versions may change conformance behavior.

Minor versions may add optional fields, profiles, examples, or extensions without breaking conformance.

Patch versions fix errors, clarify language, or add non-normative examples.

## Published version rule

If using an official published spec version, cite:

```text
spec_id
version
uri
content_hash
signature
```

## Extension rule

Small extensions may include inline ExtensionManifest.

Large extensions should publish external ExtensionSchema by URI, version, hash, and signature.

Extension fields should declare:

```text
field
type
microgloss
namespace
scope
core_anchor
```

## Hash rule

Hashes use canonical bytes:

```text
canonical JSON
sorted keys
no insignificant whitespace
UTF-8
SHA-256
lowercase hex with sha256: prefix
```

The hash covers content, not URL.

## Encoding evolution

New encodings must preserve the HFF logical message model and define canonicalization/hash/signature rules.
