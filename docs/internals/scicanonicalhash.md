# scicanonicalhash — deterministic hashing

!!! info "Internal package"
    Its hashes power versioning (`scidb`) and lineage (`scihist`) for you — you
    rarely call it directly. This page describes what it guarantees.

`scicanonicalhash` produces stable, deterministic hashes of arbitrary Python
objects. These hashes are the basis of SciStack's versioning, cache keys, and
reproducibility — "has this changed?" decisions throughout the stack reduce to a
hash comparison.

## What it owns

- **Content hashing** — `canonical_hash(value)` returns a 16-character hex string
  (the first 64 bits of SHA-256). It is *structural*: lists hash in order, dicts
  hash independent of key order, and numpy arrays hash by content **plus dtype and
  shape**.
- **Record IDs** — `generate_record_id(...)` derives the content-addressed IDs
  that `scidb` uses to version saved variables.
- **Function hashing** — the basis for the 64-character function hash that lineage
  uses to tell whether a function's *behavior* changed (it hashes compiled
  bytecode, so reformatting or re-commenting does not change it).

Every higher layer leans on these guarantees. For how they surface, see
[Versioning & Content Hashing](../concepts/hashing.md).
