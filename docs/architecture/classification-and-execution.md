# Work Classification & Execution State

These two concepts live **outside** the bucket lifecycle (spec §9, §10). They
are independent of each other and of the lifecycle state machine.

## Work Classification (`rsm.classification`)

| Value              | Meaning                                       |
|--------------------|-----------------------------------------------|
| `STORE`            | Passive archive. No outstanding work.         |
| `REVIEW`           | A human review is required.                   |
| `REVIEW_TODO`      | Review found outstanding tasks.               |
| `READY_EXECUTION`  | Ready for downstream execution.               |

Changing classification does **not** mutate frozen bucket fields (A1).
Classification is per-bucket and lives on the daemon service; V1 does not
persist auxiliary records across restarts.

## Execution State (`rsm.execution`)

Keyed by `bucket_id`. Status enum: `NOT_STARTED` → `IN_PROGRESS` →
`COMPLETE | FAILED`. Each task has its own status (`PENDING`, `IN_PROGRESS`,
`COMPLETE`, `FAILED`, `SKIPPED`).

Rules:

- Bucket content remains authoritative.
- Execution completion does **not** automatically close the bucket.
- RSM does not execute the work; it only records progress against the bucket.
