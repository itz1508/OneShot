# ADR 0003 — SHA-256 Fingerprint

**Status:** Carried forward from the governing spec.

Canonical bytes are hashed with SHA-256. The result lives in `bucket.hash.value`
and is reproducible from `canonical_dumps(bucket_dict_without_hash)`.
