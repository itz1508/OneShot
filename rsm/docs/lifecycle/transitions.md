# Transition Reference

See `docs/architecture/lifecycle-state-machine.md`. Errors:
- `ILLEGAL_LIFECYCLE_TRANSITION` for any pair not in the legal set.
- `BUCKET_FROZEN` (A1) if the write attempts to mutate a frozen field after
  STORED.
