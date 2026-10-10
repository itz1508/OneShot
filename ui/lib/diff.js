// Bounded Myers line matching. The frontier records edit distance, not a
// document-sized matrix. See https://github.com/kpdecker/jsdiff for the
// underlying Myers reference and the rationale for bounded diff operations.
// No dependency or implementation code is copied from that project.
const CONTEXT = 3;
const MAX_DISTANCE = 1024;
const MAX_SEARCH_WORK = 12_000_000;
const MAX_PREVIEW_LINES = 4000;
const MAX_PREVIEW_CHARACTERS = 180_000;
const MAX_LINE_PREVIEW = 16_000;

// Store offsets instead of allocating a string/object for every line. Even a
// 2 MiB file containing only newlines needs at most ~8 MiB of line offsets.
// A trailing newline has its own empty line, so changing EOF is visible.
class Lines {
  constructor(text) {
    this.text = text;
    let count = text.length ? 1 : 0;
    for (let i = 0; i < text.length; i++) if (text.charCodeAt(i) === 10) count++;
    this.length = count;
    this.starts = new Uint32Array(count + 1);
    let line = 1;
    for (let i = 0; i < text.length; i++) if (text.charCodeAt(i) === 10) this.starts[line++] = i + 1;
    this.starts[count] = text.length;
  }
  size(index) {
    return this.starts[index + 1] - this.starts[index] - (index + 1 < this.length ? 1 : 0);
  }
  get(index) {
    return this.text.slice(this.starts[index], this.starts[index] + this.size(index));
  }
}

function equal(a, ai, b, bi, budget) {
  const size = a.size(ai);
  if (budget) {
    budget.remaining -= size === b.size(bi) ? Math.max(1, size) : 1;
    if (budget.remaining < 0) return false;
  }
  return size === b.size(bi) && a.get(ai) === b.get(bi);
}

function frontierAt(frontier, diagonal) {
  const index = diagonal + ((frontier.length - 1) >> 1);
  return index < 0 || index >= frontier.length ? -1 : frontier[index];
}

// Returns compact runs; unchanged documents never create per-line objects.
function matchMiddle(a, b, start, oldEnd, newEnd) {
  const n = oldEnd - start, m = newEnd - start;
  if (!n) return m ? [{ type: 'add', old: start, new: start, length: m }] : [];
  if (!m) return [{ type: 'remove', old: start, new: start, length: n }];
  const budget = { remaining: MAX_SEARCH_WORK };
  const trace = [];
  for (let distance = 0; distance <= Math.min(MAX_DISTANCE, n + m); distance++) {
    const next = new Int32Array(2 * distance + 1).fill(-1);
    const previous = trace[distance - 1];
    for (let diagonal = -distance; diagonal <= distance; diagonal += 2) {
      if (--budget.remaining < 0) return null;
      let x;
      if (!distance) x = 0;
      else if (diagonal === -distance || (diagonal !== distance && frontierAt(previous, diagonal - 1) < frontierAt(previous, diagonal + 1))) x = frontierAt(previous, diagonal + 1);
      else x = frontierAt(previous, diagonal - 1) + 1;
      let y = x - diagonal;
      if (x < 0 || y < 0 || x > n || y > m) continue;
      while (x < n && y < m && equal(a, start + x, b, start + y, budget)) { x++; y++; }
      if (budget.remaining < 0) return null;
      next[diagonal + distance] = x;
      if (x === n && y === m) {
        const backwards = [];
        for (let d = distance; d > 0; d--) {
          const prior = trace[d - 1], k = x - y;
          const added = k === -d || (k !== d && frontierAt(prior, k - 1) < frontierAt(prior, k + 1));
          const priorK = k + (added ? 1 : -1);
          const priorX = frontierAt(prior, priorK), priorY = priorX - priorK;
          const unchanged = added ? x - priorX : y - priorY;
          if (unchanged) backwards.push({ type: 'same', old: start + x - unchanged, new: start + y - unchanged, length: unchanged });
          backwards.push({ type: added ? 'add' : 'remove', old: start + priorX, new: start + priorY, length: 1 });
          x = priorX; y = priorY;
        }
        if (x) backwards.push({ type: 'same', old: start, new: start, length: x });
        return backwards.reverse();
      }
    }
    trace.push(next);
  }
  return null;
}

function mergeRuns(runs) {
  const merged = [];
  for (const run of runs) {
    if (!run.length) continue;
    const prior = merged.at(-1);
    if (prior?.type === run.type &&
        prior.old + (prior.type === 'add' ? 0 : prior.length) === run.old &&
        prior.new + (prior.type === 'remove' ? 0 : prior.length) === run.new) prior.length += run.length;
    else merged.push({ ...run });
  }
  return merged;
}

function preview(runs, a, b, limited) {
  const hunks = [];
  let added = 0, removed = 0, lineCount = 0, characterCount = 0;
  for (const run of runs) {
    if (run.type === 'add') added += run.length;
    if (run.type === 'remove') removed += run.length;
  }
  function append(hunk, run, offset, length) {
    for (let i = offset; i < offset + length; i++) {
      if (lineCount >= MAX_PREVIEW_LINES || characterCount >= MAX_PREVIEW_CHARACTERS) { limited = true; return false; }
      const old = run.old + (run.type === 'add' ? 0 : i);
      const current = run.new + (run.type === 'remove' ? 0 : i);
      let text = run.type === 'add' ? b.get(current) : a.get(old);
      const available = Math.min(MAX_LINE_PREVIEW, MAX_PREVIEW_CHARACTERS - characterCount);
      if (text.length > available) { text = text.slice(0, Math.max(0, available - 1)) + '…'; limited = true; }
      hunk.lines.push({ type: run.type, oldLine: run.type === 'add' ? null : old + 1, newLine: run.type === 'remove' ? null : current + 1, text });
      lineCount++; characterCount += text.length;
    }
    return true;
  }
  for (let first = 0; first < runs.length;) {
    if (runs[first].type === 'same') { first++; continue; }
    let last = first;
    while (last + 1 < runs.length) {
      const following = runs[last + 1];
      if (following.type !== 'same') { last++; continue; }
      if (following.length <= CONTEXT * 2 && last + 2 < runs.length) { last += 2; continue; }
      break;
    }
    const before = runs[first - 1], after = runs[last + 1];
    const contextBefore = before?.type === 'same' ? Math.min(CONTEXT, before.length) : 0;
    const hunk = { oldStart: runs[first].old - contextBefore + 1, newStart: runs[first].new - contextBefore + 1, lines: [] };
    hunks.push(hunk);
    if (contextBefore && !append(hunk, before, before.length - contextBefore, contextBefore)) break;
    let complete = true;
    for (let i = first; i <= last; i++) if (!append(hunk, runs[i], 0, runs[i].length)) { complete = false; break; }
    if (!complete) break;
    if (after?.type === 'same' && !append(hunk, after, 0, Math.min(CONTEXT, after.length))) break;
    first = last + 1;
  }
  return { hunks: hunks.filter(hunk => hunk.lines.length), added, removed, limited };
}

/**
 * Compare text as lines, retaining whitespace, CR characters and EOF changes.
 * Line numbers and hunk starts are one-based; missing sides use null.
 *
 * limited=true means the comparison or its rendering was bounded. Counts may
 * describe a coarse replacement and must not be presented as exact changes.
 * Offer both complete revisions for download when this flag is set.
 */
export function diffLines(original, working) {
  if (typeof original !== 'string' || typeof working !== 'string') throw new TypeError('Line comparison requires two strings.');
  if (original === working) return { hunks: [], added: 0, removed: 0, limited: false };
  const a = new Lines(original), b = new Lines(working);
  let start = 0, oldEnd = a.length, newEnd = b.length;
  while (start < oldEnd && start < newEnd && equal(a, start, b, start)) start++;
  while (oldEnd > start && newEnd > start && equal(a, oldEnd - 1, b, newEnd - 1)) { oldEnd--; newEnd--; }
  const matched = matchMiddle(a, b, start, oldEnd, newEnd);
  const middle = matched || [
    { type: 'remove', old: start, new: start, length: oldEnd - start },
    { type: 'add', old: oldEnd, new: start, length: newEnd - start }
  ];
  const runs = mergeRuns([
    { type: 'same', old: 0, new: 0, length: start },
    ...middle,
    { type: 'same', old: oldEnd, new: newEnd, length: a.length - oldEnd }
  ]);
  return preview(runs, a, b, matched === null);
}
