# ADR 0004 — Folder Ingest Identity (A3)

**Status:** Carried forward and binding.

A folder produces one parent bucket whose `full_content` is the canonical
manifest JSON and whose metadata holds `source_count`, `unsupported_count`,
`opaque_count`, `skipped_permission_denied`, `max_depth_observed`, and
`deterministic_ordering = "sorted_posix_path_ascending"`. Each supported child
file is a child bucket with `provenance.derived_from = <parent bucket_id>`.
Parent `hash.value` is SHA-256 of the canonical manifest bytes.
