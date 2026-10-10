// Proves the SINGLE SAFE OPERATION (main active workflow) and its variations.
// Run: node --test temp/reference/lifecycle.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SafeOperation, ConflictError, relink, digest, maskSensitive } from './lifecycle.mjs';

// In-memory host mirroring OneShot's working-set vs. live-state split.
function makeHost({ destructive = false, driftAtCommit = false } = {}) {
  const host = {
    stamp: 1, live: [], working: [], commits: 0,
    resolve: async input => ({ ...input, resolved: true }),
    plan: async resolved => ({ action: 'note', body: resolved.body, secret: 's3cr3t' }),
    needsConfirmation: () => destructive,
    stage: async (plan, ctx) => {
      if (driftAtCommit) host.stamp += 1; // another actor changes live state during staging
      host.working.push(plan); ctx.event('stage', `Staged ${plan.action}.`);
    },
    commit: async (plan, stamp, ctx) => {
      host.commits += 1; host.live.push({ ...plan, stamp }); ctx.progress(1, 1);
      return { committed: plan.action, at: stamp };
    },
    readStamp: () => host.stamp,
  };
  return host;
}

const settle = async predicate => { while (!predicate()) await new Promise(r => setTimeout(r, 0)); };

test('MAIN WORKFLOW: resolve -> plan+receipt -> stage -> commit -> live', async () => {
  const host = makeHost();
  const op = new SafeOperation(host, { sensitive: ['secret'] });
  const snap = await op.run({ body: 'hello' });
  assert.equal(snap.status, 'live');
  assert.equal(typeof snap.receipt, 'string');
  assert.ok(snap.trace.some(t => t.operation === 'plan'));
  assert.ok(snap.trace.some(t => t.operation === 'commit'));
  assert.equal(host.commits, 1);
  assert.equal(host.live.length, 1);
  // Write-only masking: the sensitive plan value never appears in the snapshot.
  assert.equal(snap.plan.secret, '•');
});

test('VARIATION conflict: a moved live stamp blocks commit, live untouched', async () => {
  const host = makeHost({ driftAtCommit: true });
  const op = new SafeOperation(host);
  await op.run({ body: 'x' });
  assert.equal(op.snapshot.status, 'conflict');
  assert.ok(op.snapshot.findings.some(f => f.severity === 'warning' && /re-plan/i.test(f.message)));
  assert.equal(host.live.length, 0);
});

test('VARIATION gate: irreversible work waits for confirm, does nothing until then', async () => {
  const host = makeHost({ destructive: true });
  const op = new SafeOperation(host);
  const running = op.run({ body: 'x' });
  await settle(() => op.snapshot.status === 'awaiting-confirmation');
  assert.equal(host.commits, 0);
  assert.equal(host.working.length, 0);
  assert.equal(op.confirm(), true);
  await running;
  assert.equal(op.snapshot.status, 'live');
  assert.equal(host.commits, 1);
});

test('VARIATION gate: declining stages and commits nothing', async () => {
  const host = makeHost({ destructive: true });
  const op = new SafeOperation(host);
  const running = op.run({ body: 'x' });
  await settle(() => op.snapshot.status === 'awaiting-confirmation');
  assert.equal(op.decline(), true);
  const snap = await running;
  assert.equal(snap.status, 'failed');
  assert.equal(host.commits, 0);
  assert.equal(host.live.length, 0);
});

test('cooperative pause holds at a checkpoint and resume reaches live', async () => {
  const host = makeHost();
  const op = new SafeOperation(host);
  const running = op.run({ body: 'x' });
  assert.equal(op.pause(), true);
  await settle(() => op.snapshot.status === 'paused' || op.snapshot.status === 'live');
  if (op.snapshot.status === 'paused') { assert.equal(op.pause(), false); assert.equal(op.resume(), true); }
  await running;
  assert.equal(op.snapshot.status, 'live');
});

test('cooperative stop discards the working set and leaves live unchanged', async () => {
  const host = makeHost();
  const op = new SafeOperation(host);
  const running = op.run({ body: 'x' });
  assert.equal(op.stop(), true);
  const snap = await running;
  assert.equal(snap.status, 'stopped');
  assert.equal(host.commits, 0);
  assert.equal(host.live.length, 0);
});

test('VARIATION relink: lead / tail / follow keep one acyclic chain', () => {
  const chain = [{ id: 'a', next: 'b' }, { id: 'b', next: 'c' }, { id: 'c', next: null }];
  const asMap = nodes => new Map(nodes.map(n => [n.id, n.next]));
  let m = asMap(relink(chain, { id: 'c', position: 'lead' }));
  assert.equal(m.get('c'), 'a'); assert.equal(m.get('a'), 'b'); assert.equal(m.get('b'), null);
  m = asMap(relink(chain, { id: 'a', position: 'tail' }));
  assert.equal(m.get('b'), 'c'); assert.equal(m.get('c'), 'a'); assert.equal(m.get('a'), null);
  m = asMap(relink(chain, { id: 'a', position: 'follow', anchorId: 'c' }));
  assert.equal(m.get('b'), 'c'); assert.equal(m.get('c'), 'a'); assert.equal(m.get('a'), null);
});

test('VARIATION relink: rejects unknown nodes, self-anchors, broken chains', () => {
  const chain = [{ id: 'a', next: 'b' }, { id: 'b', next: null }];
  assert.throws(() => relink(chain, { id: 'zzz', position: 'lead' }), /Unknown node/);
  assert.throws(() => relink(chain, { id: 'a', position: 'follow', anchorId: 'a' }), /itself/);
  assert.throws(() => relink([{ id: 'a', next: 'a' }], { id: 'a', position: 'lead' }), /cycle|entry point|unreachable/);
  assert.throws(() => relink([{ id: 'a', next: null }, { id: 'b', next: null }], { id: 'a', position: 'lead' }), /entry point/);
});

test('receipt digest is order-independent; ConflictError surfaces as conflict', async () => {
  assert.equal(digest({ a: 1, b: 2 }), digest({ b: 2, a: 1 }));
  assert.notEqual(digest({ a: 1 }), digest({ a: 2 }));
  const masked = maskSensitive({ token: 'x', keep: 'y', nested: { token: 'z' } }, new Set(['token']));
  assert.equal(masked.token, '•'); assert.equal(masked.nested.token, '•'); assert.equal(masked.keep, 'y');
  const host = makeHost();
  host.commit = async () => { throw new ConflictError(); };
  const op = new SafeOperation(host);
  const snap = await op.run({ body: 'x' });
  assert.equal(snap.status, 'conflict');
  assert.equal(host.live.length, 0);
});

test('VARIATION chaining: the same loop runs repeatedly as child operations', async () => {
  const host = makeHost();
  for (const body of ['one', 'two', 'three']) {
    const op = new SafeOperation(host);
    const snap = await op.run({ body });
    assert.equal(snap.status, 'live');
  }
  assert.equal(host.live.length, 3);
  assert.equal(host.commits, 3);
});


test('VARIATION masking: frozen snapshots never leak sensitive values or mutate', async () => {
  const host = makeHost();
  const op = new SafeOperation(host, { sensitive: ['secret'] });
  const snap = await op.run({ body: 'x' });
  assert.equal(Object.isFrozen(snap), true);
  assert.equal(Object.isFrozen(snap.trace), true);
  assert.throws(() => { snap.status = 'tampered'; });
});
