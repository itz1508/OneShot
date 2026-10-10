import test from 'node:test';
import assert from 'node:assert/strict';
import { diffLines } from '../../lib/diff.js';

const lines = text => text === '' ? [] : text.split('\n');

// Independently replay displayed hunks, including omitted unchanged regions.
// This checks coordinates as well as whether the diff recovers the new text.
function replay(original, diff) {
  const old = lines(original), result = [];
  let oldCursor = 0;
  for (const hunk of diff.hunks) {
    result.push(...old.slice(oldCursor, hunk.oldStart - 1));
    oldCursor = hunk.oldStart - 1;
    assert.equal(result.length + 1, hunk.newStart);
    for (const line of hunk.lines) {
      if (line.type !== 'add') {
        assert.equal(line.oldLine, oldCursor + 1);
        assert.equal(line.text, old[oldCursor++]);
      } else assert.equal(line.oldLine, null);
      if (line.type !== 'remove') {
        assert.equal(line.newLine, result.length + 1);
        result.push(line.text);
      } else assert.equal(line.newLine, null);
    }
  }
  result.push(...old.slice(oldCursor));
  return result.join('\n');
}

// Small, unrelated dynamic-programming oracle for minimal line edit distance.
function distance(original, working) {
  const a = lines(original), b = lines(working);
  let previous = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const next = [i];
    for (let j = 1; j <= b.length; j++) next[j] = a[i - 1] === b[j - 1] ? previous[j - 1] : Math.min(previous[j] + 1, next[j - 1] + 1);
    previous = next;
  }
  return previous[b.length];
}

test('identical and empty documents contain no edits', () => {
  for (const value of ['', 'single line', 'a\n\nb\n', 'é 中文 🎨\n']) {
    assert.deepEqual(diffLines(value, value), { hunks: [], added: 0, removed: 0, limited: false });
  }
});

test('empty documents, insertion, deletion, EOF and whitespace have exact coordinates', () => {
  for (const [original, working] of [
    ['', 'a'], ['a', ''], ['', '\n'], ['\n', ''], ['a\nb', 'a\ninserted\nb'],
    ['a\nremoved\nb', 'a\nb'], ['a', 'a\n'], ['a\n', 'a'],
    ['a\r\nb\r\n', 'a\nb\n'], ['a\n b\n', 'a\nb\n']
  ]) {
    const diff = diffLines(original, working);
    assert.equal(diff.limited, false);
    assert.equal(diff.added + diff.removed, distance(original, working));
    assert.equal(replay(original, diff), working);
  }
});

test('distant edits form separate hunks with only three lines of context', () => {
  const original = Array.from({ length: 100 }, (_, i) => `line ${i + 1}`);
  const working = [...original];
  working[10] = 'changed early'; working[90] = 'changed late';
  const diff = diffLines(original.join('\n'), working.join('\n'));
  assert.equal(diff.limited, false);
  assert.equal(diff.hunks.length, 2);
  assert.equal(diff.added, 2); assert.equal(diff.removed, 2);
  assert.deepEqual(diff.hunks.map(hunk => [hunk.oldStart, hunk.newStart]), [[8, 8], [88, 88]]);
  assert.ok(diff.hunks.every(hunk => hunk.lines.filter(line => line.type === 'same').length === 6));
  assert.equal(replay(original.join('\n'), diff), working.join('\n'));
});

test('nearby changes share context instead of duplicating lines', () => {
  const original = Array.from({ length: 20 }, (_, i) => `line ${i}`);
  const working = [...original]; working[5] = 'first'; working[11] = 'second';
  const diff = diffLines(original.join('\n'), working.join('\n'));
  assert.equal(diff.hunks.length, 1);
  assert.equal(replay(original.join('\n'), diff), working.join('\n'));
});

test('repeated lines and adversarial short sequences match a minimal edit oracle', () => {
  let seed = 271828;
  const random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed; };
  const vocabulary = ['a', 'b', 'a', '', 'same', 'same', '中文', '🎨'];
  for (let attempt = 0; attempt < 250; attempt++) {
    const make = () => Array.from({ length: random() % 30 }, () => vocabulary[random() % vocabulary.length]).join('\n');
    const original = make(), working = make(), diff = diffLines(original, working);
    assert.equal(diff.limited, false, `case ${attempt}`);
    assert.equal(diff.added + diff.removed, distance(original, working), `minimal case ${attempt}`);
    assert.equal(replay(original, diff), working, `replay case ${attempt}`);
  }
});

test('a two MiB document with distant edits yields a small exact preview', { timeout: 3000 }, () => {
  const original = Array.from({ length: 32_000 }, (_, i) => `${String(i).padStart(6, '0')} ${'abcdefgh'.repeat(7)}`);
  const working = [...original]; working[20] = 'changed at start'; working[16_000] = 'changed in middle'; working[31_980] = 'changed at end';
  const diff = diffLines(original.join('\n'), working.join('\n'));
  assert.equal(diff.limited, false);
  assert.equal(diff.hunks.length, 3);
  assert.equal(diff.added, 3); assert.equal(diff.removed, 3);
  assert.equal(replay(original.join('\n'), diff), working.join('\n'));
});

test('very many empty lines do not require a document-sized object matrix', { timeout: 3000 }, () => {
  const original = '\n'.repeat(2_097_150), working = `start${original}end`;
  const diff = diffLines(original, working);
  assert.equal(diff.limited, false);
  assert.equal(diff.added, 2); assert.equal(diff.removed, 2);
  assert.equal(diff.hunks.length, 2);
  assert.ok(diff.hunks.flatMap(hunk => hunk.lines).length <= 16);
});

test('a pathological rewrite is explicitly limited and its preview is bounded', { timeout: 3000 }, () => {
  const original = Array.from({ length: 30_000 }, (_, i) => `before ${i}`).join('\n');
  const working = Array.from({ length: 30_000 }, (_, i) => `after ${i}`).join('\n');
  const diff = diffLines(original, working), visible = diff.hunks.flatMap(hunk => hunk.lines);
  assert.equal(diff.limited, true);
  assert.ok(visible.length <= 4000);
  assert.ok(visible.reduce((total, line) => total + line.text.length, 0) <= 180_000);
  assert.ok(diff.added > 0 && diff.removed > 0);
});

test('large insertions and oversized individual lines retain the limited warning', () => {
  for (const [original, working] of [['before', `before\n${'new line\n'.repeat(10_000)}`], ['before', 'x'.repeat(2_097_152)]]) {
    const diff = diffLines(original, working), visible = diff.hunks.flatMap(hunk => hunk.lines);
    assert.equal(diff.limited, true);
    assert.ok(visible.length <= 4000);
    assert.ok(visible.reduce((total, line) => total + line.text.length, 0) <= 180_000);
  }
});
