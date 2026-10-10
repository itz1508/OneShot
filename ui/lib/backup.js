// Portable workspace backups. Binary bytes are encoded independently of JSON;
// decoding and validation have no IndexedDB or application-state side effects.
export const MAX_BACKUP_BYTES = 128 * 1024 * 1024;
const MAX_BLOB_BYTES = 10 * 1024 * 1024;
const MAX_STRING_LENGTH = 16 * 1024 * 1024;
const MAX_ITEMS = 100000;
const FORMAT = 'oneshot-workspace';
const BLOB_KEY = '__oneshot_blob__';
const FORBIDDEN_KEYS = new Set(['__proto__', 'prototype', 'constructor']);
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const PANELS = ['agent', 'system', 'sources', 'detail'];

export class WorkspaceBackupError extends Error {
  constructor(message) { super(`Workspace backup: ${message}`); this.name = 'WorkspaceBackupError'; this.code = 'INVALID_WORKSPACE_BACKUP'; }
}
const fail = message => { throw new WorkspaceBackupError(message); };
const object = (value, path) => {
  if (!value || typeof value !== 'object' || Array.isArray(value) || value instanceof Blob) fail(`${path} must be an object.`);
};
const string = (value, path, nullable = false) => {
  if (nullable && value === null) return;
  if (typeof value !== 'string' || value.length > MAX_STRING_LENGTH) fail(`${path} must be text within the backup size limit.`);
};
const array = (value, path) => { if (!Array.isArray(value) || value.length > MAX_ITEMS) fail(`${path} must be a bounded list.`); };
const number = (value, path) => { if (!Number.isFinite(value) || value < 0) fail(`${path} must be a nonnegative number.`); };
const id = (value, path, nullable = false) => { if (!(nullable && value === null) && (typeof value !== 'string' || !SAFE_ID.test(value))) fail(`${path} is not a valid identifier.`); };
const optional = (record, key, check, path) => { if (record[key] !== undefined) check(record[key], `${path}.${key}`); };
const boolean = (value, path) => { if (typeof value !== 'boolean') fail(`${path} must be true or false.`); };
const enumValue = (value, allowed, path) => { if (!allowed.includes(value)) fail(`${path} has an unsupported value.`); };
const time = (value, path) => { string(value, path); if (!Number.isFinite(Date.parse(value))) fail(`${path} is not a valid date.`); };

function validateFile(file, path) {
  object(file, path); id(file.id, `${path}.id`);
  for (const key of ['name', 'path', 'type']) string(file[key], `${path}.${key}`);
  if (!file.name.trim() || !file.path.trim()) fail(`${path} must have a name and path.`);
  if (file.blob !== null && !(file.blob instanceof Blob)) fail(`${path}.blob must contain file bytes or be null for a reference.`);
  if (file.blob && file.blob.size > MAX_BLOB_BYTES) fail(`${path}.blob exceeds 10 MiB.`);
  for (const key of ['original', 'saved', 'draft']) string(file[key], `${path}.${key}`, true);
  if (file.reference !== undefined) {
    string(file.reference, `${path}.reference`);
    let url;
    try { url = new URL(file.reference); } catch { fail(`${path}.reference must be an HTTP or HTTPS address.`); }
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) fail(`${path}.reference must use HTTP or HTTPS without embedded credentials.`);
  } else if (!file.blob) fail(`${path} is missing its original file bytes.`);
  if (file.type === 'reference' && !file.reference) fail(`${path} is missing its reference address.`);
  optional(file, 'inScope', boolean, path); optional(file, 'generated', boolean, path);
  for (const key of ['origin', 'outcome', 'lastStatus', 'referenceKey']) optional(file, key, string, path);
  for (const key of ['revisionId', 'lastPreparedRevisionId', 'runId']) optional(file, key, id, path);
  if (file.position != null) {
    object(file.position, `${path}.position`);
    for (const [key, value] of Object.entries(file.position)) number(value, `${path}.position.${key}`);
  }
  if (file.readError != null) string(file.readError, `${path}.readError`);
  if (file.revisions !== undefined) {
    array(file.revisions, `${path}.revisions`); const ids = new Set();
    for (const revision of file.revisions) {
      object(revision, `${path}.revisions`); id(revision.id, `${path}.revision.id`);
      if (ids.has(revision.id)) fail(`${path} contains a duplicate revision ID.`); ids.add(revision.id);
      string(revision.text, `${path}.revision.text`); time(revision.time, `${path}.revision.time`);
    }
  }
  if (file.sourceRefs !== undefined) {
    array(file.sourceRefs, `${path}.sourceRefs`);
    for (const ref of file.sourceRefs) {
      object(ref, `${path}.sourceRefs`); id(ref.sourceId, `${path}.sourceRef.sourceId`); id(ref.revisionId, `${path}.sourceRef.revisionId`);
      string(ref.name, `${path}.sourceRef.name`); string(ref.path, `${path}.sourceRef.path`);
    }
  }
}

function validateRun(run, path) {
  object(run, path); id(run.id, `${path}.id`); string(run.status, `${path}.status`);
  for (const key of ['task', 'taskLabel', 'responsibility', 'route']) optional(run, key, string, path);
  for (const key of ['total', 'processed', 'characters']) number(run[key], `${path}.${key}`);
  optional(run, 'estimatedTokens', number, path);
  array(run.events, `${path}.events`); array(run.findings, `${path}.findings`);
  for (const event of run.events) {
    object(event, `${path}.events`); time(event.time, `${path}.event.time`);
    for (const key of ['operation', 'message', 'status']) string(event[key], `${path}.event.${key}`);
    optional(event, 'sequence', number, path);
    if (event.sourceId != null) id(event.sourceId, `${path}.event.sourceId`);
  }
  for (const finding of run.findings) {
    object(finding, `${path}.findings`); string(finding.message, `${path}.finding.message`); string(finding.severity, `${path}.finding.severity`);
    if (finding.sourceId != null) id(finding.sourceId, `${path}.finding.sourceId`);
  }
  if (run.sourceStates !== undefined) {
    object(run.sourceStates, `${path}.sourceStates`);
    for (const [key, value] of Object.entries(run.sourceStates)) { id(key, `${path}.sourceStates key`); string(value, `${path}.sourceStates value`); }
  }
  if (run.result != null) { object(run.result, `${path}.result`); string(run.result.name, `${path}.result.name`); string(run.result.text, `${path}.result.text`); }
  if (run.resultId != null) id(run.resultId, `${path}.resultId`);
  optional(run, 'endedAt', time, path);
}

function validateWorkspace(workspace) {
  object(workspace, 'workspace');
  if (workspace.version !== 1) fail('this application supports workspace version 1.');
  for (const key of ['sources', 'results', 'history', 'systemNotes', 'agentNotes', 'selected', 'collapsed']) array(workspace[key], `workspace.${key}`);
  const sourceIds = new Set(), allIds = new Set();
  for (const key of ['sources', 'results']) {
    for (const [index, file] of workspace[key].entries()) {
      validateFile(file, `${key}[${index}]`);
      if (allIds.has(file.id)) fail('source and result identifiers must be unique.'); allIds.add(file.id);
      if (key === 'sources') sourceIds.add(file.id);
    }
  }
  const resultIds = new Set(workspace.results.map(file => file.id));
  const requireLink = (value, ids, path) => { id(value, path); if (!ids.has(value)) fail(`${path} points to content missing from this backup.`); };
  const selectedIds = new Set();
  for (const selected of workspace.selected) {
    requireLink(selected, sourceIds, 'workspace.selected');
    if (selectedIds.has(selected)) fail('selected source identifiers must be unique.'); selectedIds.add(selected);
  }
  if (workspace.selectedFile !== null) requireLink(workspace.selectedFile, allIds, 'workspace.selectedFile');
  for (const file of workspace.results) for (const ref of file.sourceRefs || []) requireLink(ref.sourceId, sourceIds, 'result.sourceRefs.sourceId');
  for (const [index, run] of workspace.history.entries()) { validateRun(run, `history[${index}]`); if (run.resultId != null) requireLink(run.resultId, resultIds, 'history.resultId'); }
  if (workspace.activeRun != null) validateRun(workspace.activeRun, 'activeRun');
  for (const key of ['systemNotes', 'agentNotes']) {
    for (const note of workspace[key]) {
      object(note, key); string(note.text, `${key}.text`); time(note.time, `${key}.time`);
      optional(note, 'kind', string, key); optional(note, 'id', id, key);
      if (note.attachments !== undefined) {
        array(note.attachments, `${key}.attachments`);
        for (const attachment of note.attachments) {
          object(attachment, `${key}.attachment`); requireLink(attachment.resultId, resultIds, `${key}.attachment.resultId`);
          id(attachment.revisionId, `${key}.attachment.revisionId`); string(attachment.name, `${key}.attachment.name`); string(attachment.outcome, `${key}.attachment.outcome`);
        }
      }
    }
  }
  for (const key of ['agentDraft', 'systemDraft']) string(workspace[key], `workspace.${key}`);
  if (workspace.agentAttachment != null) requireLink(workspace.agentAttachment, resultIds, 'workspace.agentAttachment');
  enumValue(workspace.theme, ['light', 'dark'], 'workspace.theme');
  enumValue(workspace.editorMode, ['read', 'edit', 'diff'], 'workspace.editorMode');
  enumValue(workspace.mobileView, PANELS, 'workspace.mobileView');
  for (const panel of workspace.collapsed) enumValue(panel, PANELS, 'workspace.collapsed');
  object(workspace.folders, 'workspace.folders');
  for (const value of Object.values(workspace.folders)) boolean(value, 'workspace.folders value');
  optional(workspace, 'requestedTask', string, 'workspace'); optional(workspace, 'referencePack', number, 'workspace');
  optional(workspace, 'focusWork', boolean, 'workspace'); optional(workspace, 'sourceDetailsOpen', boolean, 'workspace');
  if (workspace.panelWidths !== undefined) {
    object(workspace.panelWidths, 'workspace.panelWidths');
    for (const [key, value] of Object.entries(workspace.panelWidths)) { enumValue(key, ['agent', 'sources'], 'workspace.panelWidths key'); number(value, `workspace.panelWidths.${key}`); }
  }
  if (workspace.lastNotice != null) {
    object(workspace.lastNotice, 'workspace.lastNotice');
    for (const key of ['title', 'message', 'status']) string(workspace.lastNotice[key], `workspace.lastNotice.${key}`);
    if (workspace.lastNotice.resultId != null) requireLink(workspace.lastNotice.resultId, resultIds, 'workspace.lastNotice.resultId');
  }
  return workspace;
}

function guardTree(value, { allowBlobs = false, allowMarkers = false } = {}) {
  let nodes = 0, textUnits = 0, blobBytes = 0;
  const walk = (item, depth) => {
    if (++nodes > 300000 || depth > 32) fail('workspace nesting or object count exceeds the supported limit.');
    if (item === null || typeof item === 'boolean') return;
    if (typeof item === 'string') { textUnits += item.length; if (item.length > MAX_STRING_LENGTH || textUnits > MAX_BACKUP_BYTES) fail('text exceeds the supported size limit.'); return; }
    if (typeof item === 'number') { if (!Number.isFinite(item)) fail('numbers must be finite.'); return; }
    if (allowBlobs && item instanceof Blob) { blobBytes += item.size; if (item.size > MAX_BLOB_BYTES || blobBytes > MAX_BACKUP_BYTES) fail('binary content exceeds the supported size limit.'); return; }
    if (Array.isArray(item)) { array(item, 'array'); for (const child of item) walk(child, depth + 1); return; }
    if (!item || typeof item !== 'object' || ![Object.prototype, null].includes(Object.getPrototypeOf(item))) fail('only plain objects, text, numbers, lists and file bytes can be backed up.');
    for (const key of Object.keys(item)) {
      if (FORBIDDEN_KEYS.has(key) || (!allowMarkers && key === BLOB_KEY)) fail(`reserved object key "${key}" is not allowed.`);
      if (key.length > 1024) fail('an object key exceeds the supported length.');
      walk(item[key], depth + 1);
    }
  };
  walk(value, 0);
}

function bytesToBase64(bytes) {
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += 32768) binary += String.fromCharCode(...bytes.subarray(offset, offset + 32768));
  return btoa(binary);
}

/** Return JSON text suitable for downloading with application/json. */
export async function encodeWorkspace(workspace) {
  // Clone synchronously before awaiting Blob reads so a running UI cannot mix
  // source bytes from one moment with notes or selection from a later moment.
  const snapshot = structuredClone(workspace);
  delete snapshot._storageRevision; // A portable backup has no ownership of a live database revision.
  guardTree(snapshot, { allowBlobs: true }); validateWorkspace(snapshot);
  const blobs = [];
  const encode = async value => {
    if (value instanceof Blob) {
      const index = blobs.length; blobs.push(null);
      blobs[index] = { type: value.type, size: value.size, base64: bytesToBase64(new Uint8Array(await value.arrayBuffer())) };
      return { [BLOB_KEY]: index };
    }
    if (Array.isArray(value)) { const encoded = []; for (const item of value) encoded.push(await encode(item)); return encoded; }
    if (value && typeof value === 'object') { const encoded = {}; for (const [key, item] of Object.entries(value)) encoded[key] = await encode(item); return encoded; }
    return value;
  };
  const encoded = await encode(snapshot);
  const text = JSON.stringify({ format: FORMAT, backupVersion: 1, createdAt: new Date().toISOString(), workspace: encoded, blobs });
  if (new Blob([text]).size > MAX_BACKUP_BYTES) fail('the encoded archive exceeds 128 MiB. No backup was produced.');
  return text;
}

/** Validate an entire JSON string/File/Blob before returning a detached workspace. */
export async function decodeWorkspace(input) {
  if (input instanceof Blob) { if (input.size > MAX_BACKUP_BYTES) fail('archive exceeds 128 MiB.'); input = await input.text(); }
  if (typeof input !== 'string') fail('choose a JSON workspace backup.');
  if (input.length > MAX_BACKUP_BYTES || new Blob([input]).size > MAX_BACKUP_BYTES) fail('archive exceeds 128 MiB.');
  let archive;
  try { archive = JSON.parse(input); } catch { fail('file is not valid JSON.'); }
  object(archive, 'archive');
  if (archive.format !== FORMAT || archive.backupVersion !== 1) fail('unrecognized format or backup version.');
  time(archive.createdAt, 'archive.createdAt'); array(archive.blobs, 'archive.blobs');
  // Check binary records separately: their base64 strings can exceed the normal
  // per-text-field bound, but the complete file is already bounded above.
  let totalBytes = 0;
  const blobs = archive.blobs.map((record, index) => {
    object(record, `blobs[${index}]`);
    if (Object.keys(record).some(key => !['type', 'size', 'base64'].includes(key))) fail(`blobs[${index}] has unsupported fields.`);
    if (typeof record.type !== 'string' || record.type.length > 255 || /[^\x20-\x7e]/.test(record.type)) fail(`blobs[${index}] has an invalid MIME type.`);
    if (!Number.isSafeInteger(record.size) || record.size < 0 || record.size > MAX_BLOB_BYTES) fail(`blobs[${index}] exceeds 10 MiB or has an invalid byte count.`);
    totalBytes += record.size; if (totalBytes > MAX_BACKUP_BYTES) fail('decoded binary content exceeds 128 MiB.');
    if (typeof record.base64 !== 'string' || record.base64.length !== Math.ceil(record.size / 3) * 4 || !/^[A-Za-z0-9+/]*={0,2}$/.test(record.base64)) fail(`blobs[${index}] has malformed binary encoding.`);
    const binary = atob(record.base64);
    if (binary.length !== record.size || btoa(binary) !== record.base64) fail(`blobs[${index}] byte count or binary encoding is inconsistent.`);
    return new Blob([Uint8Array.from(binary, character => character.charCodeAt(0))], { type: record.type });
  });
  // Reject dangerous keys in the complete envelope, then validate all workspace
  // fields the UI dereferences. No state changes happen during this operation.
  for (const key of Object.keys(archive)) if (!['format', 'backupVersion', 'createdAt', 'workspace', 'blobs'].includes(key)) fail(`unsupported archive field "${key}".`);
  guardTree(archive.workspace, { allowMarkers: true });
  const used = new Set();
  const decode = value => {
    if (Array.isArray(value)) return value.map(decode);
    if (value && typeof value === 'object') {
      if (Object.hasOwn(value, BLOB_KEY)) {
        const index = value[BLOB_KEY];
        if (Object.keys(value).length !== 1 || !Number.isSafeInteger(index) || index < 0 || index >= blobs.length) fail('a binary content reference is invalid.');
        used.add(index); return blobs[index];
      }
      const decoded = {}; for (const [key, item] of Object.entries(value)) decoded[key] = decode(item); return decoded;
    }
    return value;
  };
  const workspace = decode(archive.workspace);
  if (used.size !== blobs.length) fail('archive includes unreferenced binary content.');
  object(workspace, 'workspace');
  delete workspace._storageRevision;
  return validateWorkspace(workspace);
}
