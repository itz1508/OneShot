# Threats & Mitigations (V1)

| Threat                       | Mitigation                                                 |
|------------------------------|------------------------------------------------------------|
| Path traversal via bucket ID | `FsStore._path` sanitises '/' to '_'                        |
| Archive bomb                 | Archives are OPAQUE in V1 (no auto-expand).                 |
| Oversized source             | `boundaries.max_source_bytes` fails closed                 |
| PDF with excessive pages     | `boundaries.max_pdf_pages`                                 |
| Permission-denied folders    | Counted in `skipped_permission_denied`; ingestion continues|

Fail-closed everywhere: unknown config keys abort load.
