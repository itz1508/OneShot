// Local preparation follows Architecture.md's intake and coverage branches.
// It reads actual saved source bytes. No model or remote operation is simulated.
export const MAX_SOURCE_BYTES = 10 * 1024 * 1024;
export const MAX_TEXT_BYTES = 2 * 1024 * 1024;
const CHUNK_BYTES = 64 * 1024;
const EXCERPT_CHARACTERS = 4000;
const TEXT_EXTENSIONS = new Set(['txt', 'md', 'markdown', 'json', 'jsonl', 'csv', 'tsv', 'xml', 'html', 'htm', 'css', 'scss', 'js', 'mjs', 'cjs', 'jsx', 'ts', 'tsx', 'py', 'yaml', 'yml', 'toml', 'ini', 'conf', 'log', 'sql', 'sh', 'ps1', 'bat', 'rs', 'go', 'java', 'c', 'cpp', 'h', 'hpp', 'rb', 'php', 'swift', 'kt', 'dot', 'mmd', 'mermaid', 'svg']);
const TEXT_MIME = new Set(['application/json', 'application/ld+json', 'application/xml', 'application/javascript', 'application/x-javascript', 'application/sql', 'application/yaml', 'image/svg+xml']);
const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'avif', 'bmp']);
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
const stopSignal = Symbol('stopped');
export const TASKS = Object.freeze({
  inspect: { label:'Inspect local contents', responsibility:'Source inspection', description:'Read text excerpts and image dimensions. Coverage applies to local inspection.' },
  inventory: { label:'Inventory sources', responsibility:'Source inspection', description:'List source types, saved sizes, folder paths, and references. Content is not read.' },
  extract: { label:'Extract text', responsibility:'Source inspection', description:'Read UTF-8 text and prepare excerpts, up to 4,000 characters per source.' },
  summary: { label:'Understand and summarize', responsibility:'Source inspection', unavailable:'Semantic understanding and summarization need a connected processing service. Choose local inspection or inventory.' },
  research: { label:'Research with evidence', responsibility:'Research', unavailable:'Browser research is not connected. A saved reference does not fetch or verify its target.' }
});
export function taskRejection(sources, task) {
  if (!TASKS[task]) return 'The requested task is unresolved. Choose a supported inspection task.';
  if (TASKS[task].unavailable) return TASKS[task].unavailable;
  if (!Array.isArray(sources) || !sources.length) return 'Select at least one source in the current scope.';
  return null;
}

export function sourceKind(source) {
  if (source.reference) return 'reference';
  const extension = String(source.name || source.path || '').split('.').pop().toLowerCase();
  const mime = String(source.blob?.type || source.type || '').toLowerCase().split(';')[0];
  if (mime === 'application/pdf' || extension === 'pdf') return 'pdf';
  if (TEXT_EXTENSIONS.has(extension) || mime.startsWith('text/') || TEXT_MIME.has(mime)) return 'text';
  if (IMAGE_EXTENSIONS.has(extension) || mime.startsWith('image/')) return 'image';
  return 'unsupported';
}

function freezeSnapshot(value) {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    for (const item of Object.values(value)) freezeSnapshot(item);
    Object.freeze(value);
  }
  return value;
}

export class LocalPreparation extends EventTarget {
  constructor() {
    super();
    this.snapshot = null;
    this._active = false;
    this._pauseRequested = false;
    this._stopRequested = false;
    this._wake = null;
  }

  _publish() {
    this.snapshot = freezeSnapshot(structuredClone(this._state));
    this.dispatchEvent(new CustomEvent('update', { detail: this.snapshot }));
    return this.snapshot;
  }

  _event(operation, message, status = 'completed', sourceId = null) {
    this._state.events.push({ sequence: this._state.events.length + 1, time: new Date().toISOString(), sourceId, operation, message, status });
    this._publish();
  }

  _finding(sourceId, severity, message) {
    this._state.findings.push({ sourceId, severity, message });
  }

  async _checkpoint() {
    if (this._stopRequested) throw stopSignal;
    if (this._pauseRequested) {
      this._state.status = 'paused';
      this._event('pause', 'Paused at a source or chunk boundary. No further reading will begin until resumed.', 'paused');
      while (this._pauseRequested && !this._stopRequested) {
        await new Promise(resolve => { this._wake = resolve; });
        this._wake = null;
      }
    }
    if (this._stopRequested) throw stopSignal;
  }

  pause() {
    if (!this._active || this._state.status !== 'running') return false;
    this._pauseRequested = true;
    this._state.status = 'pausing';
    this._event('pause', 'Pause requested; the current read or image decode may finish before acknowledgment.', 'pausing');
    return true;
  }

  resume() {
    if (!this._active || !this._pauseRequested || this._stopRequested) return false;
    this._pauseRequested = false;
    this._state.status = 'running';
    this._event('resume', 'Local preparation resumed.', 'running');
    this._wake?.();
    return true;
  }

  stop() {
    if (!this._active || this._stopRequested) return false;
    this._stopRequested = true;
    this._pauseRequested = false;
    this._state.status = 'stopping';
    this._event('stop', 'Stop requested; waiting for the current read or image decode to return.', 'stopping');
    this._wake?.();
    return true;
  }

  async _readText(source, blob) {
    if (blob.size > MAX_TEXT_BYTES) throw new Error('Text exceeds the 2 MiB decoding limit. Its content was not read.');
    const decoder = new TextDecoder('utf-8', { fatal: true });
    const pieces = [];
    let sourceCharacters = 0;
    for (let offset = 0; offset < blob.size; offset += CHUNK_BYTES) {
      await this._checkpoint();
      const bytes = await blob.slice(offset, Math.min(offset + CHUNK_BYTES, blob.size)).arrayBuffer();
      await this._checkpoint();
      const text = decoder.decode(bytes, { stream: offset + CHUNK_BYTES < blob.size });
      // Reject text-labelled binary data rather than presenting it as readable text.
      if (text.includes('\0')) throw new Error('The source contains null bytes and cannot be treated as UTF-8 text.');
      pieces.push(text);
      const added = Array.from(text).length;
      sourceCharacters += added;
      this._state.characters += added;
      this._state.estimatedTokens = Math.ceil(this._state.characters / 4);
      this._event('read', `Read ${Math.min(offset + CHUNK_BYTES, blob.size).toLocaleString()} / ${blob.size.toLocaleString()} bytes of ${source.name}.`, 'running', source.id);
      // Yield after actual chunk work so controls can act on the next checkpoint.
      await tick();
    }
    await this._checkpoint();
    const text = pieces.join('');
    if (!text.trim()) throw new Error('The source contains no usable text.');
    return { characters: sourceCharacters, lines: text.split(/\r\n|\r|\n/).length, excerpt: Array.from(text).slice(0, EXCERPT_CHARACTERS).join(''), truncated: sourceCharacters > EXCERPT_CHARACTERS };
  }

  async _inspectImage(blob) {
    if (typeof createImageBitmap !== 'function') throw new Error('Image decoding is unavailable in this browser.');
    const bitmap = await createImageBitmap(blob);
    try {
      await this._checkpoint();
      return { width: bitmap.width, height: bitmap.height };
    } finally {
      bitmap.close();
    }
  }

  _result(records, terminal) {
    const state = this._state;
    const lines = [
      `# ${TASKS[state.task].label}`, '',
      `Responsibility: ${TASKS[state.task].responsibility}`,
      `Coverage target: ${TASKS[state.task].description}`,
      `Run: ${state.id}`, `Created: ${new Date().toISOString()}`, `Outcome: ${terminal}`,
      `Inspected sources: ${state.processed} / ${state.total}`,
      `Decoded characters: ${state.characters} Unicode code points`,
      `Estimated tokens: ${state.estimatedTokens} (characters / 4, rounded up; no model tokenizer)`, '',
      '## Coverage and limitations', '',
      'Coverage is assessed against the requested local task. No semantic understanding, image interpretation, or research is claimed.',
      'Preparation uses the saved source revision at Start. Unsaved editor drafts are excluded.',
      'Limits: 10 MiB per source; 2 MiB per text source; UTF-8 text only; excerpts limited to 4,000 Unicode code points per source.', '',
      '## Source inventory', ''
    ];
    for (const record of records) {
      lines.push(`### ${record.path}`, '', `Kind: ${record.kind}`, `Saved source bytes: ${record.bytes}`, `Outcome: ${record.status}`);
      if (record.text) lines.push(`Decoded characters: ${record.text.characters}`, `Lines: ${record.text.lines}`, '', record.text.truncated ? 'Text excerpt (truncated):' : 'Text excerpt:', '', ...record.text.excerpt.split('\n').map(line => `> ${line}`));
      if (record.image) lines.push(`Image dimensions: ${record.image.width} × ${record.image.height} pixels`, 'Image content was not interpreted.');
      if (record.error) lines.push(`Limitation: ${record.error}`);
      if (record.reference) lines.push(`Reference: ${record.reference}`, 'Linked content was not fetched, copied, or verified.');
      lines.push('');
    }
    if (state.findings.length) {
      lines.push('## Findings', '');
      for (const finding of state.findings) lines.push(`- ${finding.severity}: ${finding.message}`);
    }
    return { name: `prepared-context-${state.id}.md`, text: lines.join('\n') };
  }

  async start(sources, task = 'inspect') {
    if (this._active) throw new Error('A preparation run is already active.');
    const rejection = taskRejection(sources, task);
    if (rejection) throw new Error(rejection);
    const ids = new Set();
    const selected = sources.map(source => {
      if (!source.id || ids.has(source.id)) throw new Error('Each selected source must have a unique ID.');
      ids.add(source.id);
      return { id: source.id, name: String(source.name || 'Untitled'), path: String(source.path || source.name || 'Untitled'), type: source.type, blob: source.blob, reference:source.reference || null, original: typeof source.original === 'string' ? source.original : null };
    });
    this._active = true;
    this._pauseRequested = false;
    this._stopRequested = false;
    const kinds = new Set(selected.map(sourceKind));
    const route = kinds.size > 1 ? 'Mixed-source inspection' : kinds.has('image') ? 'Visual inspection · dimensions' : kinds.has('text') ? 'Text inspection' : 'Files and folders inspection';
    this._state = { id: crypto.randomUUID(), task, taskLabel:TASKS[task].label, responsibility:TASKS[task].responsibility, route:task === 'inventory' ? 'Files, folders, and reference inventory' : route, status: 'running', events: [], total: selected.length, processed: 0, characters: 0, estimatedTokens: 0, findings: [], result: null, sourceStates: Object.fromEntries(selected.map(source => [source.id, 'queued'])) };
    const records = [];
    let usable = 0;
    try {
      this._event('intake', `Accepted ${selected.length} saved source revision${selected.length === 1 ? '' : 's'} for local preparation.`, 'completed');
      this._event('route', `${TASKS[task].label} · ${this._state.route}`, 'completed');
      for (const source of selected) {
        await this._checkpoint();
        const kind = sourceKind(source);
        const blob = kind === 'text' && source.original !== null ? new Blob([source.original], { type: 'text/plain;charset=utf-8' }) : source.blob;
        const record = { sourceId: source.id, path: source.path, kind, bytes: blob?.size || 0, reference:source.reference, status: 'inspecting' };
        records.push(record);
        this._state.sourceStates[source.id] = 'reading';
        this._event('inventory', `${source.path} · ${kind} · ${record.bytes.toLocaleString()} bytes`, 'completed', source.id);
        try {
          await this._checkpoint();
          if (kind === 'reference' && task !== 'inventory') throw new Error('Linked content was not copied or fetched. Import the content to inspect it; research requires a connected service.');
          if (kind !== 'reference' && !(blob instanceof Blob)) throw new Error('The saved source bytes are unavailable. Import this source again.');
          if (task === 'inventory') {
            this._event('metadata', kind === 'reference' ? `Recorded reference ${source.reference}; target not fetched.` : `Recorded saved metadata for ${source.name}. Content was not inspected.`, 'completed', source.id);
            record.status = 'completed';
          } else {
          if (blob.size > MAX_SOURCE_BYTES) throw new Error('Source exceeds the 10 MiB local preparation limit.');
          if (kind === 'pdf') throw new Error('PDF extraction is unavailable. Import a UTF-8 text export to prepare its content.');
          if (kind === 'unsupported') throw new Error('This file format has no local reader. Its content was not decoded.');
          if (task === 'extract' && kind !== 'text') throw new Error('This source is not supported by the local text reader. Image OCR and PDF extraction are unavailable.');
          if (kind === 'text') {
            record.text = await this._readText(source, blob);
            this._event('extract', `Read ${record.text.characters.toLocaleString()} characters from ${source.name}.`, 'completed', source.id);
            if (record.text.truncated) this._finding(source.id,'warning',`${source.name}: the report includes the first 4,000 characters; remaining content is omitted.`);
          } else {
            record.image = await this._inspectImage(blob);
            this._event('inspect', `Decoded ${source.name}: ${record.image.width} × ${record.image.height} pixels. Visual inspection is limited to dimensions.`, 'completed', source.id);
          }
          record.status = record.text?.truncated ? 'partial' : 'completed';
          }
          await this._checkpoint();
          usable += 1;
          this._state.sourceStates[source.id] = record.status;
        } catch (error) {
          if (error === stopSignal) throw error;
          record.status = 'failed';
          record.error = error instanceof Error ? error.message : String(error);
          this._state.sourceStates[source.id] = 'failed';
          this._finding(source.id, 'error', `${source.name}: ${record.error}`);
          this._event('limitation', `${source.name}: ${record.error}`, 'failed', source.id);
        }
        this._state.processed += 1;
        this._event('coverage', `${this._state.processed} / ${this._state.total} sources inspected.`, 'completed', source.id);
        await tick();
      }
      await this._checkpoint();
      const terminal = !usable ? 'failed' : this._state.findings.length ? 'partial' : 'completed';
      this._state.result = this._result(records, terminal);
      this._event('coverage', terminal === 'completed' ? `Requested task completed for all ${selected.length} sources. Coverage is sufficient for ${TASKS[task].label.toLowerCase()}.` : usable ? 'Partial task output is available with known gaps.' : 'The requested task produced no usable output. Review the limitations.', terminal);
      // A listener can request Pause on the last coverage event. Honor it too.
      await this._checkpoint();
      this._state.status = terminal;
      this._publish();
    } catch (error) {
      const stopped = error === stopSignal;
      this._state.status = stopped ? 'stopped' : 'failed';
      for (const [id, state] of Object.entries(this._state.sourceStates)) {
        if (state === 'queued' || state === 'reading') this._state.sourceStates[id] = stopped ? 'stopped' : 'failed';
      }
      for (const record of records) if (record.status === 'inspecting') record.status = stopped ? 'stopped' : 'failed';
      if (!stopped) this._finding(null, 'error', error instanceof Error ? error.message : String(error));
      this._state.result = this._result(records, this._state.status);
      this._event(stopped ? 'stop' : 'limitation', stopped ? 'Preparation stopped. Inspected sources and findings remain available.' : 'Preparation failed. Review the report for available evidence.', this._state.status);
    } finally {
      this._active = false;
      this._pauseRequested = false;
      this._stopRequested = false;
      this._wake = null;
    }
    return this.snapshot;
  }
}
