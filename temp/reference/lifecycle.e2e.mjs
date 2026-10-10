// End-to-end fixture tests for the gap fixes in lifecycle.mjs.
// Covers: validation gate, idempotency replay, atomic CAS (OCC), saga
// compensation, and full happy-path / terminal lifecycle scenarios.
// Run: node --test reference/lifecycle.e2e.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SafeOperation, PartialCommitError, ValidationError, ConflictError, digest } from './lifecycle.mjs';

const settle = async predicate => { while (!predicate()) await new Promise(r => setTimeout(r, 0)); };
const ops = snap => snap.trace.map(t => t.operation);

// A fixture host backed by a simple key/value "live" store with a stamp.
function makeStoreHost(overrides = {}) {
  const host = {
    stamp: 1,
    live: new Map(),
    applied: [],
    compensated: [],
    commits: 0,
    resolve: async input => ({ ...input }),
    plan: async resolved => ({ action: 'set', key: resolved.key, value: resolved.value }),
    stage: async (plan, ctx) => { ctx.event('stage', `Staged ${plan.action} ${plan.key}.`); },
    commit: async (plan, stamp, ctx) => {
      host.commits += 1;
      host.live.set(plan.key, plan.value);
      host.applied.push(plan.key);
      return { key: plan.key, value: plan.value, stamp };
    },
    readStamp: () => host.stamp,
    ...overrides,
  };
  return host;
}

test('E2E happy path: a set operation lands in live and is traceable end to end', async () => {
  const host = makeStoreHost();
  const op = new SafeOperation(host);
  const snap = await op.run({ key: 'greeting', value: 'hello' });
  assert.equal(snap.status, 'live');
  assert.equal(host.live.get('greeting'), 'hello');
  assert.equal(host.commits, 1);
  // The full spine is present in order.
  const trace = ops(snap);
  assert.ok(trace.includes('plan'));
  assert.ok(trace.includes('stage'));
  assert.ok(trace.includes('commit'));
  assert.ok(trace.indexOf('plan') < trace.indexOf('stage'));
  assert.ok(trace.indexOf('stage') < trace.indexOf('commit'));
});

test('GAP validation: an invalid plan is rejected before staging; live untouched', async () => {
  const host = makeStoreHost({
    validatePlan: plan => { if (!plan.key) throw new ValidationError('A plan must name a key.'); },
  });
  const op = new SafeOperation(host);
  const snap = await op.run({ key: '', value: 'x' });
  assert.equal(snap.status, 'failed');
  assert.equal(host.commits, 0);
  assert.equal(host.live.size, 0);
  assert.ok(snap.trace.some(t => t.operation === 'validation'));
  assert.ok(snap.findings.some(f => /validation/i.test(f.message)));
  // Stage must never have run.
  assert.ok(!ops(snap).includes('stage'));
});

test('GAP idempotency: a replayed receipt returns the stored result without re-running', async () => {
  const store = new Map();
  const host = makeStoreHost();
  const first = new SafeOperation(host, { idempotency: store });
  const snap1 = await first.run({ key: 'k', value: 'v1' });
  assert.equal(snap1.status, 'live');
  assert.equal(host.commits, 1);

  // Same plan (same receipt) again: should replay, not re-commit.
  const second = new SafeOperation(host, { idempotency: store });
  const snap2 = await second.run({ key: 'k', value: 'v1' });
  assert.equal(snap2.status, 'live');
  assert.equal(host.commits, 1, 'commit must not run again for a replayed receipt');
  assert.ok(snap2.trace.some(t => t.operation === 'idempotent-replay'));
  assert.deepEqual(snap2.result, snap1.result);

  // A different plan has a different receipt, so it commits normally.
  const third = new SafeOperation(host, { idempotency: store });
  const snap3 = await third.run({ key: 'k2', value: 'v2' });
  assert.equal(snap3.status, 'live');
  assert.equal(host.commits, 2);
});

test('GAP OCC atomic: casStamp failure surfaces as conflict and applies nothing', async () => {
  const host = makeStoreHost({
    // Simulate a concurrent writer: the CAS always fails.
    casStamp: (expected, next) => false,
  });
  const op = new SafeOperation(host);
  const snap = await op.run({ key: 'k', value: 'v' });
  assert.equal(snap.status, 'conflict');
  assert.equal(host.commits, 0, 'commit must not run when CAS fails');
  assert.equal(host.live.size, 0);
  assert.ok(snap.findings.some(f => f.severity === 'warning' && /re-plan/i.test(f.message)));
});

test('GAP OCC atomic: casStamp success commits and bumps the stamp', async () => {
  const host = makeStoreHost({
    // A working CAS: succeeds when the expected stamp matches, then advances it.
    casStamp: (expected, next) => { if (host.stamp !== expected) return false; host.stamp = next; return true; },
  });
  const op = new SafeOperation(host);
  const snap = await op.run({ key: 'k', value: 'v' });
  assert.equal(snap.status, 'live');
  assert.equal(host.stamp, 2, 'CAS should have advanced the stamp');
  assert.equal(host.live.get('k'), 'v');
});

test('GAP saga: a partial commit is compensated in reverse and ends rolled-back', async () => {
  const host = makeStoreHost({
    // Apply two steps, then fail on the third -> PartialCommitError.
    commit: async (plan, stamp, ctx) => {
      host.commits += 1;
      host.live.set('step1', 'a');
      host.applied.push('step1');
      host.live.set('step2', 'b');
      host.applied.push('step2');
      throw new PartialCommitError(['step1', 'step2'], 'Failed while applying step3.');
    },
    compensate: async (applied, ctx) => {
      // Undo in reverse order, as a saga requires.
      for (const key of [...applied].reverse()) {
        host.live.delete(key);
        host.compensated.push(key);
      }
      ctx.event('compensate', `Compensated ${applied.length} step(s) in reverse.`);
    },
  });
  const op = new SafeOperation(host);
  const snap = await op.run({ key: 'ignored', value: 'x' });
  assert.equal(snap.status, 'rolled-back');
  // Compensation ran in reverse: step2 undone before step1.
  assert.deepEqual(host.compensated, ['step2', 'step1']);
  // Live store is back to empty (pre-commit shape).
  assert.equal(host.live.size, 0);
  const trace = ops(snap);
  assert.ok(trace.includes('compensate'));
  assert.ok(trace.includes('rolled-back'));
  assert.ok(snap.findings.some(f => f.severity === 'warning' && /rolled back/i.test(f.message)));
});

test('GAP saga: a partial commit with no compensate hook surfaces as failed (honest)', async () => {
  const host = makeStoreHost({
    commit: async () => { throw new PartialCommitError(['step1'], 'Boom.'); },
    // No compensate hook provided.
  });
  const op = new SafeOperation(host);
  const snap = await op.run({ key: 'k', value: 'v' });
  assert.equal(snap.status, 'failed');
  assert.ok(snap.findings.some(f => f.severity === 'error'));
});

test('E2E gate + commit: destructive op waits, then commits only after confirm', async () => {
  const host = makeStoreHost();
  const op = new SafeOperation(host, { destructive: true });
  const running = op.run({ key: 'k', value: 'v' });
  await settle(() => op.snapshot.status === 'awaiting-confirmation');
  assert.equal(host.commits, 0);
  assert.equal(op.confirm(), true);
  const snap = await running;
  assert.equal(snap.status, 'live');
  assert.equal(host.live.get('k'), 'v');
  assert.ok(ops(snap).includes('gate'));
});

test('E2E terminal matrix: stopped / declined / conflict / failed are all inspectable', async () => {
  // stopped
  const h1 = makeStoreHost();
  const o1 = new SafeOperation(h1);
  const r1 = o1.run({ key: 'k', value: 'v' });
  o1.stop();
  assert.equal((await r1).status, 'stopped');

  // declined at gate
  const h2 = makeStoreHost();
  const o2 = new SafeOperation(h2, { destructive: true });
  const r2 = o2.run({ key: 'k', value: 'v' });
  await settle(() => o2.snapshot.status === 'awaiting-confirmation');
  o2.decline();
  assert.equal((await r2).status, 'failed');

  // conflict via CAS
  const h3 = makeStoreHost({ casStamp: () => false });
  const o3 = new SafeOperation(h3);
  assert.equal((await o3.run({ key: 'k', value: 'v' })).status, 'conflict');

  // failed via host error
  const h4 = makeStoreHost({ commit: async () => { throw new Error('disk full'); } });
  const o4 = new SafeOperation(h4);
  const s4 = await o4.run({ key: 'k', value: 'v' });
  assert.equal(s4.status, 'failed');
  assert.ok(s4.findings.some(f => /disk full/.test(f.message)));
});

test('E2E chaining with idempotency store shared across a batch', async () => {
  const store = new Map();
  const host = makeStoreHost();
  for (const [k, v] of [['a', '1'], ['b', '2'], ['c', '3']]) {
    const op = new SafeOperation(host, { idempotency: store });
    const snap = await op.run({ key: k, value: v });
    assert.equal(snap.status, 'live');
  }
  assert.equal(host.commits, 3);
  assert.equal(store.size, 3, 'each distinct plan stored its own receipt');
  assert.equal(host.live.get('a'), '1');
  assert.equal(host.live.get('c'), '3');
});
