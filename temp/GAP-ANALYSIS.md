# OneShot Operation Lifecycle — Gap Analysis vs. Market Practice

> Companion to `OPERATION-LIFECYCLE.md` and the runnable `reference/lifecycle.mjs`.
> Method: for each pattern, state what OneShot's design actually does, cite the
> authoritative market standard, then give an honest verdict (Full / Partial)
> and any residual note.
>
> **Correction to §7 of the design doc:** that section claimed "10/10 satisfied."
> On first rigorous review that was too generous — several patterns were only
> partially met. OneShot's own rule — honest capability reporting — required the
> correction.
>
> **UPDATE — gaps now fixed:** Patterns 1 (atomic CAS), 2 (saga compensation),
> 3 (commit-decision anchor), 7 (idempotency replay), and 10 (plan validation)
> were remediated in `reference/lifecycle.mjs` and proven by the
> `reference/lifecycle.*.mjs` suite (**21/21 tests pass**: 11 unit in
> `lifecycle.test.mjs` + 10 fixture in `lifecycle.e2e.mjs`).
> Their sections carry a "**Full (fixed)**" verdict with the evidence. Patterns
> 4, 5, and 8 remain intentionally Partial (design choices / host-storage
> concerns), documented and not "fixed."

## Summary scoreboard

| # | Pattern | Verdict |
|---|---|---|
| 1 | Optimistic Concurrency Control | **Full** (atomic CAS added) |
| 2 | Saga / compensating transactions | **Full (fixed)** — reverse compensation on partial commit |
| 3 | Two-phase commit feel | **Full (fixed)** — commit-decision recovery anchor recorded |
| 4 | Unit of Work | **Partial** (single plan; intentional design choice) |
| 5 | Event sourcing / append-only audit | **Partial** (audit log; correct for OneShot) |
| 6 | Cooperative cancellation | **Full** (inherent cooperative limits noted) |
| 7 | Idempotency key / one-time token | **Full (fixed)** — receipt→result store replays |
| 8 | Secrets — write-only, never logged | **Partial** (redaction, not encryption; host concern) |
| 9 | CQRS-lite — draft vs published | **Full** (storage-tier separation) |
| 10 | JSON Patch / additive-over-replace | **Full (fixed)** — `validatePlan` gate before staging |

Net after fixes: **7 Full, 3 Partial** — and the 3 remaining Partials are
deliberate scope decisions (Unit of Work, Event sourcing, Secrets-at-rest), not
defects. All fixes are proven by `reference/lifecycle.e2e.mjs`.

## 1. Optimistic Concurrency Control — FULL (atomic CAS added)

- **OneShot:** `commit` re-reads the live stamp; if it moved since `plan`, it
  throws `ConflictError` and requires a re-plan. **Now** the engine also uses an
  atomic `host.casStamp(expected, next)` compare-and-swap when the host provides
  one, closing the TOCTOU window. (Proven: `lifecycle.e2e.mjs` "GAP OCC atomic"
  success and failure cases.)
- **Standard:** OCC uses a version/ETag and a compare-and-swap so a write only
  lands if the version is unchanged — the canonical way to avoid lost updates
  without locking.
- **Residual note:** atomicity is only as strong as the host's `casStamp`. The
  default (no CAS) path remains compare-then-write, which is safe for OneShot's
  single-tab model (`storage.js` serializes writes and blocks a second tab).

## 2. Saga / compensating transactions — FULL (fixed)

- **OneShot:** the working set is discardable and live state is untouched until
  `commit`. **Now**, if `commit` throws `PartialCommitError(applied)`, the engine
  runs `host.compensate(applied)` **in reverse order** and ends in a `rolled-back`
  terminal state with live state restored. (Proven: `lifecycle.e2e.mjs`
  "GAP saga: a partial commit is compensated in reverse"; also the honest
  no-compensate-hook case.)
- **Standard (Chris Richardson, microservices.io — "Saga"):** "a saga is a
  sequence of local transactions… If a local transaction fails… the saga
  executes a series of **compensating transactions** that undo the changes made
  by the preceding local transactions." Sagas deliberately lack ACID automatic
  rollback, so compensation must be explicit.

## 3. Two-phase commit feel — FULL (fixed)

- **OneShot:** `stage` (prepare to the working set) then `commit` (apply to live)
  gives a two-step prepare/apply shape. **Now** the engine records a
  `commit-decision` trace event *before* applying, giving a recovery anchor for an
  interrupted commit. (Proven: present in the happy-path and saga traces.)
- **Standard:** true 2PC has a *prepare* phase where every participant votes and
  a *commit* phase gated on unanimous vote, with a coordinator recovering
  in-doubt transactions.
- **Honest scope:** OneShot remains a single-resource staging model, not a
  multi-participant 2PC. The commit-decision anchor is the recovery affordance
  that was previously missing; full participant voting is still out of scope.


## 4. Unit of Work — PARTIAL (intentional design choice)

- **OneShot:** a `SafeOperation` carries one plan through one lifecycle.
- **Standard (Martin Fowler, PoEAA "Unit of Work"):** a UoW *accumulates* a set
  of business changes and flushes them as one atomic commit, tracking what changed.
- **Scope decision:** OneShot tracks one plan, not an accumulating change-set.
  Chaining (proven in tests) runs the *same* loop repeatedly — several operations
  — rather than batching several edits into one atomic flush. This is a deliberate
  per-operation model, not a defect.
- **If ever required:** add a change-set accumulator that flushes once.

## 5. Event sourcing / append-only audit — PARTIAL (correct as audit)

- **OneShot:** every phase appends a row to `trace[]` (sequence, time,
  operation, message, status) and the run is kept in history.
- **Standard:** an *event-sourced* system stores state **as** an ordered log of
  events and can **rebuild** current state by replaying them; an *audit log* is
  a side record that is not authoritative for state.
- **Scope decision:** OneShot's trace is an audit log, not an event source —
  workspace state is stored directly (IndexedDB), not derived by replaying the
  trace. This is the correct model for OneShot; do not *claim* event sourcing.

## 6. Cooperative cancellation — FULL (inherent limits noted)

- **OneShot:** `pause`/`stop` are honored only inside `_checkpoint()`, so a long
  operation is held at a consistent boundary and the working set can resume or
  be discarded. (Proven: pause/resume and stop tests.)
- **Standard:** Go `context` cancellation and .NET `CancellationToken` are the
  canonical cooperative-cancellation idioms — cancellation is *checked* at safe
  points, not forced mid-instruction.
- **Inherent limit (shared by all cooperative schemes):** a host step that never
  calls `checkpoint()` cannot be interrupted. Document that host steps must
  checkpoint inside loops.

## 7. Idempotency key / one-time token — FULL (fixed)

- **OneShot:** `receipt = digest(plan)` is a stable, order-independent token
  issued at plan time. **Now** an optional `idempotency` store (Map-like) maps
  `receipt → result`: on a repeated receipt the engine replays the stored result
  and skips staging/commit entirely; a new plan gets a new receipt and commits
  normally. (Proven: `lifecycle.e2e.mjs` "GAP idempotency".)
- **Standard (Stripe — "Idempotent requests"; IETF draft-ietf-httpapi-
  idempotency-key-header is **expired**, so Stripe is the living reference):** a
  client-generated key lets the server "safely retry… without… performing the
  same operation twice"; the server saves the result and **replays it** on a
  repeated key, and errors if a reused key carries different parameters.
- **Residual note:** because the key *is* the plan digest, "same key + different
  params" cannot collide (different plan ⇒ different receipt). If an external,
  caller-supplied key is ever introduced, add the explicit mismatch check Stripe
  describes.

## 8. Secrets — write-only, never logged — PARTIAL (host/storage concern)

- **OneShot:** `maskSensitive` strips configured keys from every *published
  snapshot* and the trace, so secrets are not echoed back. (Proven: masking test.)
- **Standard (OWASP Secrets Management Cheat Sheet):** secrets must never be
  logged; avoid hardcoding; encrypt in transit and at rest; secrets should be
  non-retrievable after creation where possible.
- **Scope decision:** OneShot *redacts on output* but does not *encrypt* a secret,
  and the raw value still exists in the in-memory plan and in whatever the host
  persists to the working set. Redaction ≠ encryption at rest. This is a
  host/storage responsibility, not the reference engine's.
- **If ever required:** keep sensitive values out of the persisted working set
  entirely (reference, don't copy), and treat `maskSensitive` as output hygiene,
  not storage security.

## 9. CQRS-lite — draft vs published separation — FULL

- **OneShot:** the working set and the live state are distinct tiers; `stage`
  writes only the working set and `commit` is the single go-live moment. This
  mirrors OneShot's existing `draft`/`saved` split.
- **Standard:** CQRS separates the write (command) model from the read (query)
  model; the "lite" form is a draft/staging area separated from the published
  state.
- **Verdict:** the separation is real and proven (decline/stop leave live
  untouched). Full for the "lite" scope claimed.

## 10. JSON Patch / additive-over-replace — FULL (fixed, validation)

- **OneShot:** `relink` performs additive, structure-preserving edits and the
  design prefers add/remove over replace. **Now** a `host.validatePlan(plan)` hook
  runs during planning and can throw `ValidationError` to block staging — the plan
  is validated before it is ever applied. (Proven: `lifecycle.e2e.mjs`
  "GAP validation".)
- **Standard:** RFC 6902 JSON Patch is the interoperable format for describing a
  set of operations (add/remove/replace/move/…) applied to a document.
- **Honest scope:** OneShot still expresses changes as host-defined plan objects,
  not as an RFC 6902 array. The *validation-before-apply* discipline — the safety
  property that matters — is now enforced; full RFC 6902 portability remains a
  choice, not a requirement.

## Bottom line

The lifecycle is **sound and honestly bounded**. After the fixes, **7 of 10
patterns are Full**; the 3 remaining Partials (Unit of Work, Event sourcing,
Secrets-at-rest) are deliberate scope decisions, not defects, and each names the
exact path if OneShot later needs the full pattern. Every fix is proven by
the `reference/lifecycle.*.mjs` suite — **21/21 tests pass** — so nothing here
is overclaimed.
