# HTTP API

| Method | Path                                   | Purpose                                            |
|--------|----------------------------------------|----------------------------------------------------|
| GET    | /healthz                               | liveness + schema version                          |
| GET    | /v1/buckets/                           | list bucket IDs                                    |
| POST   | /v1/buckets/                           | ingest text/pasted/stdin content                   |
| GET    | /v1/buckets/{bucket_id}                | read a bucket                                      |
| POST   | /v1/buckets/{bucket_id}/transition     | legal lifecycle transition (`{"to": "STATE"}`)     |
| POST   | /v1/buckets/{bucket_id}/activate       | sugar for transition → `ACTIVATED`                 |
| POST   | /v1/buckets/{bucket_id}/release        | sugar for transition → `RELEASED`                  |
| GET    | /v1/buckets/{bucket_id}/replay         | replay envelope (read-only, derived readiness)     |
| GET    | /v1/buckets/{bucket_id}/snapshot       | bounded, derived Snapshot (budget_unit, budget_value, reduce) |
| GET    | /v1/buckets/{bucket_id}/export         | canonical JSON bytes                               |
| GET    | /v1/buckets/{bucket_id}/classification | current work classification                        |
| PUT    | /v1/buckets/{bucket_id}/classification | set work classification                            |
| GET    | /v1/buckets/{bucket_id}/execution      | current execution-state record                     |
| PUT    | /v1/buckets/{bucket_id}/execution      | set execution-state record                         |
| GET    | /v1/events/{bucket_id}                 | append-only lifecycle events                       |
| GET    | /v1/prov/{bucket_id}                   | W3C PROV-JSON projection                           |

### Errors (structured error codes)

| Code                             | HTTP | When                                                     |
|----------------------------------|------|----------------------------------------------------------|
| `UNSUPPORTED_SCHEMA_VERSION`     | 400  | request references an unknown bucket `schema_version`    |
| `BUCKET_NOT_FOUND`               | 404  | no bucket with the given ID                              |
| `ILLEGAL_LIFECYCLE_TRANSITION`   | 409  | `(from, to)` pair not in the legal set                   |
| `BUCKET_FROZEN`                  | 409  | mutation of an A1 frozen field after `STORED`            |
| `VALIDATION_FAILED`              | 422  | input does not conform to the canonical schema           |
| `BOUNDARY_VIOLATION`             | 413  | input exceeds a configured boundary                      |
| `SUMMARY_UNAVAILABLE`            | 409  | source exceeds Snapshot budget and `reduce=null`         |
| `SNAPSHOT_BUILD_FAILED`          | 422  | SummaryProvider returned text exceeding the budget       |
| `INVALID_BUDGET`                 | 422  | unknown `budget_unit` or `reduce` mode                   |
