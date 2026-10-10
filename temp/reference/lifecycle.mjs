// OneShot — Safe Operation Lifecycle: runnable reference for the SINGLE SAFE
// OPERATION (the main active workflow). Sandbox copy under temp/reference/.
//
// This proves §1 of OPERATION-LIFECYCLE.md. It re-expresses the safe-mutation
// discipline in OneShot's own vocabulary and reuses OneShot's existing
// primitives (EventTarget + frozen snapshots, cooperative checkpoints,
// structuredClone). It copies NO external tool API names or data models.
//
// The one workflow: resolve -> plan+receipt -> [gate] -> stage -> commit -> terminal.
// relink / masking / chaining are variations of this same spine.

const TERMINAL = new Set(['live', 'stopped', 'conflict', 'failed', 'rolled-back']);
const EDGES = {
  idle: ['resolving', 'failed'],
  resolving: ['planning', 'failed'],
  planning: ['planned', 'failed'],
  planned: ['awaiting-confirmation', 'staging', 'live', 'failed'],
  'awaiting-confirmation': ['staging', 'failed'],
  staging: ['staged', 'failed'],
  staged: ['committing', 'failed'],
  committing: ['live', 'conflict', 'compensating', 'failed'],
  compensating: ['rolled-back', 'failed'],
};
const WORKING = new Set(Object.keys(EDGES));

// Thrown by a host commit()/engine when the live state moved after planning.
export class ConflictError extends Error {
  constructor(message = 'The live state changed after this plan was made. Re-plan from the current state.') {
    super(message);
    this.name = 'ConflictError';
  }
}

// Thrown by a host commit() that applied some steps and then failed partway.
// Carries `applied` (the steps already applied) so the engine can compensate.
// This is the saga pattern: on partial failure, run compensating actions.
export class PartialCommitError extends Error {
  constructor(applied = [], message = 'The commit failed partway; compensating actions are required.') {
    super(message);
    this.name = 'PartialCommitError';
    this.applied = applied;
  }
}

// Thrown by a host validatePlan() when the plan is not safe/allowed to proceed.
export class ValidationError extends Error {
  constructor(message = 'The plan failed validation and was not staged.') {
    super(message);
    this.name = 'ValidationError';
  }
}

const stopSignal = Symbol('oneshot.stop');

// --- Receipt: a stable, order-independent digest of the plan -----------------
function fnv1a(text) {
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, '0');
}
function stable(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value) ?? 'null';
  if (Array.isArray(value)) return `[${value.map(stable).join(',')}]`;
  return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${stable(value[k])}`).join(',')}}`;
}
export function digest(plan) { return fnv1a(stable(plan)); }

// --- Write-only masking: sensitive values never leave in a snapshot/trace ----
export function maskSensitive(value, sensitive) {
  if (Array.isArray(value)) return value.map(item => maskSensitive(item, sensitive));
  if (value && typeof value === 'object') {
    const out = {};
    for (const [key, item] of Object.entries(value)) {
      out[key] = sensitive && sensitive.has(key) ? '•' : maskSensitive(item, sensitive);
    }
    return out;
  }
  return value;
}

function deepFreeze(value) {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    for (const item of Object.values(value)) deepFreeze(item);
    Object.freeze(value);
  }
  return value;
}

// --- Safe relink: one unambiguous positioning rule over { id, next } nodes ----
export function relink(chain, { id, position, anchorId = null }) {
  if (!Array.isArray(chain)) throw new TypeError('chain must be an array of { id, next }');
  const order0 = chain.map(node => node.id);
  const nextMap = new Map(chain.map(node => [node.id, node.next ?? null]));
  if (!nextMap.has(id)) throw new Error(`Unknown node: ${id}`);
  if (position === 'follow' && !nextMap.has(anchorId)) throw new Error(`Unknown anchor: ${anchorId}`);
  if (position === 'follow' && anchorId === id) throw new Error('A node cannot follow itself.');

  const pointedTo = new Set([...nextMap.values()].filter(Boolean));
  const heads = order0.filter(nodeId => !pointedTo.has(nodeId));
  if (heads.length !== 1) throw new Error('The chain must have exactly one entry point before relinking.');
  const walk = [];
  const seen = new Set();
  for (let cursor = heads[0]; cursor; cursor = nextMap.get(cursor)) {
    if (seen.has(cursor)) throw new Error('The chain already contains a cycle.');
    seen.add(cursor);
    walk.push(cursor);
  }
  if (walk.length !== nextMap.size) throw new Error('The chain has unreachable nodes.');

  const order = walk.filter(nodeId => nodeId !== id);
  if (position === 'lead') order.unshift(id);
  else if (position === 'tail') order.push(id);
  else if (position === 'follow') order.splice(order.indexOf(anchorId) + 1, 0, id);
  else throw new Error(`Unknown position: ${position}`);

  const rebuilt = new Map();
  order.forEach((nodeId, index) => rebuilt.set(nodeId, index + 1 < order.length ? order[index + 1] : null));
  return order0.map(nodeId => ({ id: nodeId, next: rebuilt.get(nodeId) }));
}

// The lifecycle engine. The caller supplies a `host` with the domain work; this
// class supplies the safe, auditable, resumable frame around it.
//
// host contract (all optional unless noted):
//   resolve(input)                      -> gathered prerequisites
//   plan(resolved)             (required)-> a JSON-serializable plan object
//   validatePlan(plan)                  -> throw ValidationError to block staging (JSON Patch gap)
//   needsConfirmation(plan)             -> boolean (default: options.destructive)
//   stage(plan, ctx)                    -> write to the WORKING set only (never live)
//   commit(plan, stamp, ctx)   (required)-> apply to LIVE state; throw ConflictError on drift,
//                                         or PartialCommitError(applied) to trigger compensation
//   compensate(applied, ctx)            -> undo applied steps in reverse (saga); called on PartialCommitError
//   casStamp(expected, next)            -> atomic compare-and-swap; returns boolean (OCC gap)
//   readStamp()                         -> current live-state stamp
// options:
//   sensitive: string[]                 -> keys masked from every published snapshot
//   destructive: boolean                -> require the confirmation gate
//   idempotency: Map-like store         -> receipt -> result; replays a completed plan (idempotency gap)
// ctx (given to stage/commit): checkpoint(), event(), finding(), progress().
export class SafeOperation extends EventTarget {
  constructor(host, options = {}) {
    super();
    if (!host || typeof host.plan !== 'function' || typeof host.commit !== 'function') {
      throw new TypeError('A SafeOperation host must provide plan() and commit().');
    }
    this._host = host;
    this._sensitive = options.sensitive instanceof Set ? options.sensitive : new Set(options.sensitive || []);
    this._destructive = options.destructive === true;
    this._idempotency = options.idempotency ?? null;
    this._state = { id: crypto.randomUUID(), status: 'idle', trace: [], findings: [], stamp: null, receipt: null, plan: null, result: null, progress: { done: 0, total: 0 } };
    this._active = false;
    this._pauseRequested = false;
    this._stopRequested = false;
    this._wake = null;
    this._confirmResolve = null;
    this._confirmReject = null;
    this.snapshot = this._publish();
  }

  _publish() {
    const masked = { ...this._state, plan: maskSensitive(this._state.plan, this._sensitive), result: maskSensitive(this._state.result, this._sensitive) };
    this.snapshot = deepFreeze(structuredClone(masked));
    this.dispatchEvent(new CustomEvent('update', { detail: this.snapshot }));
    return this.snapshot;
  }

  _event(operation, message, status = 'running') {
    this._state.trace.push({ sequence: this._state.trace.length + 1, time: new Date().toISOString(), operation, message, status });
    this._publish();
  }

  _finding(severity, message) { this._state.findings.push({ severity, message }); this._publish(); }

  _advance(to) {
    const from = this._state.status;
    if (!EDGES[from] || !EDGES[from].includes(to)) throw new Error(`Illegal transition ${from} -> ${to}.`);
    this._state.status = to;
    this._publish();
  }

  async _checkpoint() {
    if (this._stopRequested) throw stopSignal;
    if (this._pauseRequested) {
      this._statusBeforePause = this._state.status;
      this._state.status = 'paused';
      this._event('pause', 'Held at a safe boundary. The working set is consistent and can resume or be discarded.', 'paused');
      while (this._pauseRequested && !this._stopRequested) {
        await new Promise(resolve => { this._wake = resolve; });
        this._wake = null;
      }
    }
    if (this._stopRequested) throw stopSignal;
  }

  _ctx() {
    return {
      checkpoint: () => this._checkpoint(),
      event: (operation, message, status) => this._event(operation, message, status),
      finding: (severity, message) => this._finding(severity, message),
      progress: (done, total) => { this._state.progress = { done, total }; this._publish(); },
    };
  }

  pause() {
    if (!this._active || !WORKING.has(this._state.status) || this._pauseRequested || this._stopRequested) return false;
    this._pauseRequested = true;
    this._event('pause', 'Pause requested; the current host step will finish before the operation is held.', 'pausing');
    return true;
  }

  resume() {
    if (!this._active || !this._pauseRequested || this._stopRequested) return false;
    this._pauseRequested = false;
    if (this._state.status === 'paused' && this._statusBeforePause) this._state.status = this._statusBeforePause;
    this._event('resume', 'Operation resumed from the safe boundary.', this._state.status);
    this._wake?.();
    return true;
  }

  stop() {
    if (!this._active || this._stopRequested) return false;
    this._stopRequested = true;
    this._pauseRequested = false;
    if (this._confirmReject) { const reject = this._confirmReject; this._confirmReject = this._confirmResolve = null; reject(stopSignal); }
    this._wake?.();
    return true;
  }

  confirm() {
    if (this._state.status !== 'awaiting-confirmation') return false;
    const resolve = this._confirmResolve; this._confirmResolve = this._confirmReject = null; resolve?.();
    return true;
  }

  decline() {
    if (this._state.status !== 'awaiting-confirmation') return false;
    const reject = this._confirmReject; this._confirmResolve = this._confirmReject = null;
    reject?.(new Error('Declined at the confirmation gate. Nothing was staged or committed.'));
    return true;
  }

  async run(input) {
    if (this._active) throw new Error('An operation is already active.');
    this._active = true;
    const host = this._host;
    try {
      this._advance('resolving'); await this._checkpoint();
      const resolved = host.resolve ? await host.resolve(input) : input;
      await this._checkpoint();

      this._advance('planning');
      const plan = await host.plan(resolved);
      // JSON Patch gap: validate the plan before anything is staged.
      if (host.validatePlan) host.validatePlan(plan);
      const stamp = host.readStamp ? host.readStamp() : (this._state.stamp ?? 0);
      this._state.plan = plan; this._state.stamp = stamp; this._state.receipt = digest(plan);
      this._advance('planned');
      this._event('plan', `Plan prepared. Receipt ${this._state.receipt} issued against stamp ${stamp}.`, 'planned');
      await this._checkpoint();

      // Idempotency gap: a completed plan with the same receipt is replayed, not re-run.
      if (this._idempotency && this._idempotency.has(this._state.receipt)) {
        this._state.result = this._idempotency.get(this._state.receipt);
        this._advance('live');
        this._event('idempotent-replay', `Receipt ${this._state.receipt} already completed; the stored result was returned without re-running.`, 'live');
        return this.snapshot;
      }

      const needsGate = host.needsConfirmation ? host.needsConfirmation(plan) : this._destructive;
      if (needsGate) {
        this._advance('awaiting-confirmation');
        this._event('gate', 'Irreversible change: waits for explicit confirmation before anything is staged.', 'awaiting-confirmation');
        await new Promise((resolve, reject) => { this._confirmResolve = resolve; this._confirmReject = reject; });
        await this._checkpoint();
      }

      this._advance('staging');
      this._event('stage', 'Applying the plan to the working set. Live state is still untouched.', 'staging');
      await host.stage?.(plan, this._ctx());
      this._advance('staged');
      await this._checkpoint();

      this._advance('committing');
      // OCC gap: prefer an atomic compare-and-swap when the host offers one.
      if (host.casStamp) {
        const swapped = host.casStamp(stamp, stamp + 1);
        if (!swapped) throw new ConflictError();
      } else {
        const liveStamp = host.readStamp ? host.readStamp() : stamp;
        if (liveStamp !== stamp) throw new ConflictError();
      }
      // 2PC gap: record the commit decision as a recovery anchor before applying.
      this._event('commit-decision', `Decision to commit receipt ${this._state.receipt} at stamp ${stamp} recorded before applying.`, 'committing');
      await this._checkpoint();
      let result;
      try {
        result = await host.commit(plan, stamp, this._ctx());
      } catch (commitError) {
        // Saga gap: a partial commit is undone by compensating actions in reverse.
        if (commitError instanceof PartialCommitError && host.compensate) {
          this._advance('compensating');
          this._event('compensate', `Commit failed partway after applying ${commitError.applied.length} step(s); running compensating actions in reverse.`, 'compensating');
          await host.compensate(commitError.applied, this._ctx());
          this._advance('rolled-back');
          this._event('rolled-back', 'Compensating actions completed. Live state was restored to its pre-commit shape.', 'rolled-back');
          this._finding('warning', 'The commit failed partway and was rolled back by compensating actions. Re-plan and retry.');
          return this.snapshot;
        }
        throw commitError;
      }
      this._state.result = result;
      if (this._idempotency) this._idempotency.set(this._state.receipt, result);
      this._advance('live');
      this._event('commit', `Committed against matching stamp ${stamp}. The change is now live.`, 'live');
    } catch (error) {
      const stopped = error === stopSignal;
      const conflict = error instanceof ConflictError;
      const invalid = error instanceof ValidationError;
      this._state.status = stopped ? 'stopped' : conflict ? 'conflict' : 'failed';
      if (conflict) this._finding('warning', 'The live stamp moved after planning. Discard the working set and re-plan from current state.');
      else if (invalid) this._finding('error', `Plan rejected by validation: ${error.message}`);
      else if (!stopped) this._finding('error', error instanceof Error ? error.message : String(error));
      this._event(stopped ? 'stop' : conflict ? 'conflict' : invalid ? 'validation' : 'limitation', stopped ? 'Stopped at a safe boundary. Working set can be discarded; live state is unchanged.' : conflict ? 'Commit blocked: the live state changed. Re-plan and retry.' : invalid ? 'Plan failed validation and was never staged. Live state is unchanged.' : 'Operation failed. Live state is unchanged.', this._state.status);
    } finally {
      this._active = false; this._pauseRequested = false; this._stopRequested = false;
      this._wake = null; this._confirmResolve = this._confirmReject = null;
    }
    return this.snapshot;
  }
}

