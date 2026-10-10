import { LocalPreparation, sourceKind, MAX_SOURCE_BYTES, MAX_TEXT_BYTES, TASKS, taskRejection } from './lib/processing.js';
import { loadWorkspace, saveWorkspace, isWorkspaceConflict } from './lib/storage.js';
import { encodeWorkspace, decodeWorkspace } from './lib/backup.js';
import { normalizeRevisions, saveVersion, resultFreshness, revisionText } from './lib/revisions.js';
import { diffLines } from './lib/diff.js';

const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
const glyphs = {
 chat:'M4 4h16v12H9l-5 4V4Z', layers:'m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5', folder:'M3 6h7l2 2h9v12H3V6Z',
 panel:'M3 4h18v16H3V4Zm8 0v16', sun:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm0-6v2m0 16v2M2 12h2m16 0h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1',
 history:'M3 11a9 9 0 1 1 2 7M3 5v6h6m3-5v6l4 2', diagram:'M9 3h6v5H9V3ZM2 16h6v5H2v-5Zm14 0h6v5h-6v-5ZM12 8v4M5 16v-4h14v4',
 arrow:'M4 12h16m-6-6 6 6-6 6', 'arrow-up':'M12 20V4m-6 6 6-6 6 6', collapse:'M4 4h16v16H4V4Zm5 0v16m7-8-3 3 3 3',
 search:'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14Zm5 12 6 6', upload:'M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6',
 play:'m8 4 12 8-12 8V4Z', plus:'M12 5v14M5 12h14', attachment:'m8 13 7-7a3 3 0 0 1 4 4L9 20a5 5 0 0 1-7-7L13 2',
 document:'M5 3h9l5 5v13H5V3Zm9 0v6h5M9 13h6m-6 4h6', download:'M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4',
 close:'m6 6 12 12M6 18 18 6', expand:'M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5', chevron:'m9 5 7 7-7 7', down:'m5 9 7 7 7-7', check:'m5 12 4 4L19 6'
};
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${glyphs[name] || glyphs.document}"/></svg>`;
function icons() { $$('[data-icon]').forEach(el => { el.innerHTML = icon(el.dataset.icon); }); }
icons();
const fmt = n => new Intl.NumberFormat().format(n || 0);
const short = n => n >= 10000 ? `${(n / 1000).toFixed(1)}k` : fmt(n);
const size = n => n >= 1048576 ? `${(n / 1048576).toFixed(1)} MiB` : n >= 1024 ? `${(n / 1024).toFixed(1)} KiB` : `${n} B`;
const clock = time => new Date(time).toLocaleTimeString([], { hour:'2-digit', minute:'2-digit', second:'2-digit' });
const terminal = status => ['completed','partial','failed','stopped','interrupted'].includes(status);
const emptyWorkspace = () => ({ version:1, sources:[], selected:[], selectedFile:null, results:[], history:[], systemNotes:[], agentNotes:[], agentDraft:'', systemDraft:'', agentAttachment:null, theme:'light', collapsed:[], folders:{}, editorMode:'read', mobileView:'agent', activeRun:null, requestedTask:'inspect', lastNotice:null, referencePack:0, focusWork:false, panelWidths:{} });
let state = emptyWorkspace();
let filter = 'all', search = '', currentRun = null, processor = null, toastTimer, persistTimer, persistVersion = 0, imageURL, imageZoom = 1, activePreparation = false, importBusy = false, workspaceReady = false, restoreFocus = false, snapshotDirty = false;
let sourceCommitBusy = false;
let storageConflict = false, pendingRestore = null, lastAnnouncedRunState = '', commandIndex = -1;
const operationLock = 'oneshot-workspace-operation';
for (const region of ['.topbar', '.viewbar', '#workbench']) $(region).inert = true;
const sourceById = id => [...state.sources, ...state.results].find(file => file.id === id);
const chosenFile = () => sourceById(state.selectedFile);
function toast(message) { $('#toast').textContent = message; $('#toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').hidden = true, 4300); }
function announce(message) { $('#live-status').textContent = message; }
function showStorageConflict(message = 'Another tab saved newer work. This tab has stopped saving so that neither copy is overwritten.') {
  storageConflict = true; clearTimeout(persistTimer); processor?.stop();
  $('#save-status').textContent = 'Save conflict · recovery needed';
  $('#conflict-status').textContent = `${message} Download this tab’s copy before reloading the latest saved workspace. Reload discards this tab’s unsaved changes.`;
  $$('dialog[open]').forEach(dialog=>dialog.close());
  $('#workbench').inert = true; $('#conflict-dialog').showModal(); announce(message);
}
async function runWithOwnership(action) {
  if (storageConflict) { showStorageConflict(); return false; }
  if (!navigator.locks) { toast('This browser cannot safely coordinate workspace operations. Use a browser with Web Locks support.'); return false; }
  return navigator.locks.request(operationLock,{ifAvailable:true},async lock=>{
    if (!lock) { toast('Another tab is processing this workspace. Wait for it to finish, then reload this tab.'); return false; }
    return action();
  });
}
async function persist(immediate = false) {
  clearTimeout(persistTimer);
  if (!workspaceReady || sourceCommitBusy || storageConflict) return false;
  if (!immediate) { $('#save-status').textContent = 'Saving workspace…'; persistTimer = setTimeout(() => persist(true), 350); return; }
  const version = ++persistVersion;
  try { await saveWorkspace(state); if (version === persistVersion) $('#save-status').textContent = 'Workspace saved in this browser'; return true; }
  catch (error) { if(isWorkspaceConflict(error)) showStorageConflict(); else { $('#save-status').textContent = 'Workspace could not be saved'; toast(error.message); } return false; }
}
function rememberEditor() {
  const file = chosenFile(); if (!file) return;
  if ($('#review-view').hidden || !$('#process-view').hidden) return;
  const position = { ...file.position };
  const editor = $('#file-editor'), reader = $('#read-content'), diff = $('#diff-content');
  if (!editor.hidden && editor.getClientRects().length) {
    position.start = editor.selectionStart; position.end = editor.selectionEnd; position.editScroll = editor.scrollTop;
  }
  if (!reader.hidden && reader.getClientRects().length) position.readScroll = reader.scrollTop;
  if (!diff.hidden && diff.getClientRects().length) position.diffScroll = diff.scrollTop;
  file.position = position;
}
const scopeSources = () => state.sources.filter(file => file.inScope !== false);
function visibleSources() { return scopeSources().filter(file => (!search || file.path.toLowerCase().includes(search)) && (filter === 'all' || sourceKind(file) === filter)); }
function togglePanel(name, force) {
  const panel = $(`#${name}-panel`);
  if (state.focusWork && ['agent','system'].includes(name)) { state.focusWork=false; $('#workbench').classList.remove('focus-work'); }
  if (innerWidth <= 960) { state.mobileView = name; $('#workbench').dataset.mobileView = name; panel.classList.remove('is-collapsed'); }
  else if (name === 'system' && innerWidth <= 1300) { panel.classList.toggle('force-open', force ?? !panel.classList.contains('force-open')); panel.classList.remove('is-collapsed'); }
  else { const open = force ?? panel.classList.contains('is-collapsed'); panel.classList.toggle('is-collapsed', !open); state.collapsed = $$('.panel.is-collapsed').map(p => p.id.replace('-panel','')); }
  syncViewControls(); fitPanels();
  persist();
}
function syncViewControls() {
  $$('.view-switcher button').forEach(button => {
    const active = innerWidth <= 960 ? button.dataset.view === state.mobileView : $(`#${button.dataset.view}-panel`).getClientRects().length > 0;
    button.classList.toggle('active',active); button.setAttribute('aria-pressed',String(active));
  });
  $('#focus-toggle').setAttribute('aria-pressed',String(state.focusWork));
}
function renderTree() {
  const focused = $('#source-tree').contains(document.activeElement) ? document.activeElement : null;
  const focusKey = focused && ['select','folderSelect','folder','file'].find(key=>focused.dataset[key]);
  const focusValue = focusKey ? focused.dataset[focusKey] : null;
  const scroll = $('#source-tree').scrollTop;
  const shown = visibleSources(); const root = { files:[], folders:Object.create(null) };
  for (const file of shown) { const parts = file.path.split('/').filter(Boolean); parts.pop(); let node = root; for (const part of parts) node = node.folders[part] ||= { files:[], folders:Object.create(null) }; node.files.push(file); }
  const allIds = node => [...node.files.map(f => f.id), ...Object.values(node.folders).flatMap(allIds)];
  const draw = (node, parent = '') => Object.entries(node.folders).map(([name, sub]) => {
    const path = `${parent}/${name}`, ids = allIds(sub), closed = state.folders[path] === false && !search;
    return `<div class="tree-folder"><div class="folder-heading"><input type="checkbox" data-folder-select="${escape(path)}" aria-label="Select folder ${escape(name)}" ${ids.every(id => state.selected.includes(id)) ? 'checked' : ''} ${activePreparation ? 'disabled' : ''}><button data-folder="${escape(path)}" aria-expanded="${!closed}">${icon(closed ? 'chevron' : 'down')}${icon('folder')}<span>${escape(name)}</span></button><span>${ids.length}</span></div><div class="folder-children" ${closed ? 'hidden' : ''}>${draw(sub,path)}</div></div>`;
  }).join('') + node.files.map(file => {
    const dirty = file.draft !== null && file.draft !== file.saved, kind = sourceKind(file), status = currentRun?.sourceStates?.[file.id] || (file.lastPreparedRevisionId && file.lastPreparedRevisionId!==file.revisionId ? 'changed' : file.lastStatus) || '';
    const statusLabel = dirty ? 'Unsaved edits' : status === 'changed' ? 'Source changed' : status || 'Ready';
    const typeLabel=kind==='reference'?'LINK':file.name.split('.').pop().slice(0,4).toUpperCase();
    return `<div class="tree-row ${state.selectedFile === file.id ? 'active' : ''}"><input type="checkbox" data-select="${file.id}" aria-label="Select ${escape(file.name)}" ${state.selected.includes(file.id) ? 'checked' : ''} ${activePreparation ? 'disabled' : ''}><button class="file-open" data-file="${file.id}" aria-label="Open ${escape(file.name)}" aria-describedby="status-${file.id}" aria-expanded="${state.selectedFile === file.id && !$('#detail-panel').classList.contains('is-collapsed')}"><span class="file-type ${kind === 'image' ? 'visual' : ''}">${escape(typeLabel)}</span><span class="file-name">${escape(file.name)}<small id="status-${file.id}" class="source-status-label">${escape(statusLabel)}</small></span><span class="file-state ${dirty ? 'dirty' : status}" aria-hidden="true"></span><span class="file-chevron">${icon('chevron')}</span></button></div>`;
  }).join('');
  $('#source-tree').innerHTML = shown.length ? draw(root) : '<p class="empty-state">No matching sources. Try another search or add a file.</p>';
  $('#source-tree').scrollTop = scroll;
  if(focusKey) [...$('#source-tree').querySelectorAll('input,button')].find(el=>el.dataset[focusKey]===focusValue)?.focus({preventScroll:true});
  $('#source-count').textContent = scopeSources().length;
  $('#selected-count').textContent = `${state.selected.length} selected`;
  $('#select-all').checked = shown.length > 0 && shown.every(f => state.selected.includes(f.id));
  $('#select-all').indeterminate = shown.some(f => state.selected.includes(f.id)) && !$('#select-all').checked;
  $('#select-all').disabled = activePreparation || !shown.length;
  $$('[data-folder-select]').forEach(input => { const files = shown.filter(f => `/${f.path}`.startsWith(`${input.dataset.folderSelect}/`)); input.indeterminate = files.some(f => state.selected.includes(f.id)) && !files.every(f => state.selected.includes(f.id)); });
  renderScope();
}
function renderScope() {
  const selected = scopeSources().filter(f => state.selected.includes(f.id));
  const chars = selected.reduce((total,file) => total + (typeof file.saved === 'string' ? Array.from(file.saved).length : 0), 0);
  $('#scope-stats').innerHTML = `<div>${selected.length}<small>Selected files</small></div><div>${short(chars)}<small>Known text chars</small></div><div>~${short(Math.ceil(chars / 4))}<small>Est. tokens¹</small></div>`;
  $('#scope-stats').title = 'Known text only. ¹ Token estimate = Unicode characters ÷ 4, rounded up; no model tokenizer. Images and unread text excluded.';
  $('#start-button').disabled = importBusy || activePreparation || !!currentRun || !selected.length;
  $('#start-button').hidden = activePreparation;
  $('#run-controls').hidden = !activePreparation || importBusy;
  $('#add-source').disabled = importBusy || activePreparation;
  $('#remove-sources').disabled = importBusy || activePreparation || !!currentRun || !selected.length;
  $('#requested-task').disabled = importBusy || activePreparation || !!currentRun;
  $('#requested-task').value = state.requestedTask;
  $('#task-description').textContent = TASKS[state.requestedTask]?.description || TASKS[state.requestedTask]?.unavailable || 'Choose a task.';
  $('#task-description').classList.toggle('unavailable',!!TASKS[state.requestedTask]?.unavailable);
  $('.snapshot-note').textContent = selected.some(f => f.draft !== f.saved) ? 'Unsaved edits excluded · save to include' : 'Start uses saved revisions';
}
function renderResults() {
  $('#result-count').textContent = state.results.length;
  $('#prepared-list').innerHTML = state.results.length ? state.results.slice().reverse().map(file => `<button class="result-row" data-result="${file.id}">${icon('document')}<span>${escape(file.name)}</span><small>${escape(file.outcome)}</small></button>`).join('') : '<p class="empty-prepared">Your prepared sources will appear here.</p>';
  const run = state.history.filter(r=>r.responsibility !== 'Source management' && r.status !== 'rejected').at(-1);
  $('#context-status').innerHTML = run ? `<span class="label">${escape(run.taskLabel || 'LATEST PREPARATION')}</span><h3>${run.status === 'completed' ? 'Requested output available' : run.status === 'partial' ? 'Context with known gaps' : run.status === 'failed' ? 'Preparation needs attention' : run.status === 'interrupted' ? 'Run interrupted by reload' : 'Preparation stopped'}</h3><p>${run.processed} of ${run.total} sources inspected. ${run.findings.length} recorded findings.</p><button id="context-open-history">Review activity →</button>` : '<span class="label">PREPARATION SPACE</span><h3>Your context starts here.</h3><p>Select sources and a task, then press Start. Results and coverage gaps stay available for review.</p>';
}
function renderMessages() {
  $$('#agent-messages .draft-card').forEach(el => el.remove());
  for (const note of state.agentNotes) { const div = document.createElement('div'); div.className = 'draft-card'; div.innerHTML = `<small>YOUR SAVED DRAFT · ${escape(clock(note.time))}</small>${escape(note.text)}`; $('#agent-messages').append(div); }
  $('#system-messages').innerHTML = state.systemNotes.map(note => `<div class="system-message"><div class="message-meta"><span>${note.kind === 'event' ? '<i class="system-marker"></i>LOCAL SYSTEM' : 'YOUR CONTEXT NOTE'}</span><time>${escape(clock(note.time))}</time></div><p>${escape(note.text)}</p></div>`).join('');
}
function inline(text) { return escape(text).replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>').replace(/`([^`]+)`/g,'<code>$1</code>'); }
function markdown(text) {
  let code = false, codeLines = [], list = false; const out = [];
  for (const line of text.split(/\r?\n/)) {
    if (/^```/.test(line)) { if (list) { out.push('</ul>'); list = false; } if (code) { out.push(`<pre><code>${escape(codeLines.join('\n'))}</code></pre>`); codeLines = []; } code = !code; continue; }
    if (code) { codeLines.push(line); continue; }
    if (/^\s*[-*] /.test(line)) { if (!list) { out.push('<ul>'); list = true; } out.push(`<li>${inline(line.replace(/^\s*[-*] /,''))}</li>`); continue; }
    if (list) { out.push('</ul>'); list = false; }
    const heading = line.match(/^(#{1,3}) (.*)/); if (heading) out.push(`<h${heading[1].length}>${inline(heading[2])}</h${heading[1].length}>`); else if (line.trim()) out.push(`<p>${inline(line)}</p>`);
  }
  if (list) out.push('</ul>'); if (code) out.push(`<pre><code>${escape(codeLines.join('\n'))}</code></pre>`);
  return out.join('');
}
function renderDiff(file) {
  const a = (file.original ?? '').split('\n'), b = (file.draft ?? '').split('\n'); let begin = 0, endA = a.length, endB = b.length;
  while (begin < endA && begin < endB && a[begin] === b[begin]) begin++;
  while (endA > begin && endB > begin && a[endA - 1] === b[endB - 1]) { endA--; endB--; }
  if (begin === a.length && begin === b.length) { $('#diff-content').innerHTML = '<p class="diff-legend">No changes from the imported original.</p>'; return; }
  const line = (text,type) => `<div class="diff-line ${type}"><span class="sign">${type === 'add' ? '+' : type === 'remove' ? '−' : ' '}</span><span>${escape(text)}</span></div>`;
  const removed = a.slice(begin,endA), added = b.slice(begin,endB), limit = 1000;
  $('#diff-content').innerHTML = `<div class="diff-legend">Imported original → current working revision<br><span>${removed.length} removed lines · ${added.length} added lines</span><br>Changed section shown as a block; unchanged ends collapsed.</div>${a.slice(Math.max(0,begin-3),begin).map(x=>line(x,'same')).join('')}${removed.slice(0,limit).map(x=>line(x,'remove')).join('')}${added.slice(0,limit).map(x=>line(x,'add')).join('')}${removed.length > limit || added.length > limit ? '<p class="diff-legend">Large change: first 1,000 lines of each side shown. Download the full working revision to inspect it.</p>' : ''}${a.slice(endA,endA+3).map(x=>line(x,'same')).join('')}`;
}
function renderEditor() {
  const file = chosenFile();
  renderNotice();
  $('#review-empty').hidden = !!file; $('#editor-shell').hidden = !file; $('#export-file').disabled = !file || !!file.reference;
  if (!file) return;
  const kind = sourceKind(file), editable = typeof file.draft === 'string';
  $('#file-title').textContent = file.name;
  $('#file-breadcrumb').textContent = file.generated ? 'Prepared context / Task output' : `${file.inScope === false ? 'Retained in library / ' : ''}${file.path.split('/').slice(0,-1).join(' / ') || 'Your sources'}`;
  $('#revision-status').textContent = file.draft !== file.saved ? '● Unsaved revision' : file.generated ? 'Generated locally' : 'Saved revision';
  $('#revision-status').classList.toggle('dirty', file.draft !== file.saved);
  const modes = $$('[data-mode]'); modes.forEach(button => { button.disabled = !editable && button.dataset.mode !== 'read'; button.classList.toggle('active', button.dataset.mode === state.editorMode); button.setAttribute('aria-pressed',String(button.dataset.mode === state.editorMode)); });
  $('#save-file').disabled = !editable || file.draft === file.saved;
  $('#file-editor').hidden = state.editorMode !== 'edit' || !editable;
  $('#diff-content').hidden = state.editorMode !== 'diff' || !editable;
  $('#read-content').hidden = state.editorMode !== 'read' && editable;
  $('#image-controls').hidden = kind !== 'image';
  $('#file-editor').value = file.draft ?? '';
  $('#file-metadata').textContent = file.reference ? 'REFERENCE · linked content not copied' : `${file.name.split('.').pop().toUpperCase()} · ${size(file.blob.size)}${editable ? ` · ${fmt(Array.from(file.draft).length)} chars` : ''}`;
  $('#editor-position').textContent = file.draft !== file.saved ? 'Working draft recovered locally' : 'Working copy · saved locally';
  $('#result-banner').hidden = !file.generated;
  $('#result-banner').innerHTML = file.generated ? `Local inspection · ${escape(file.outcome)}. Review the recorded gaps before using this context.<button id="attach-result">Attach to agent draft</button>` : '';
  $('#read-content').classList.toggle('image-preview', kind === 'image');
  if (imageURL) { URL.revokeObjectURL(imageURL); imageURL = null; }
  if (kind === 'reference') {
    $('#read-content').innerHTML = `<div class="reference-preview"><span class="support-pill">Reference only</span><h3>${escape(file.name)}</h3><p>${escape(file.reference)}</p><p>Linked content has not been fetched, copied, or verified. Inventory can record this reference; inspection needs imported content.</p><a class="secondary-button" href="${escape(file.reference)}" target="_blank" rel="noopener noreferrer">Open original website ↗</a></div>`;
  } else if (kind === 'image') {
    imageURL = URL.createObjectURL(file.blob); imageZoom = 1;
    $('#read-content').innerHTML = `<img id="source-image" src="${imageURL}" alt="${escape(file.name)}"><p class="image-caption">${escape(file.name)} · Original source image</p>`;
  } else if (editable) {
    const text = file.draft.length > 180000 ? file.draft.slice(0,180000) : file.draft;
    $('#read-content').innerHTML = /\.(md|markdown)$/i.test(file.name) && !/^\s*(flowchart|graph|digraph|stateDiagram)\b/.test(text) ? markdown(text) : `<pre>${escape(text)}</pre>`;
    if (file.draft.length > 180000) $('#read-content').insertAdjacentHTML('afterbegin','<p class="support-pill">Preview limited to 180,000 characters. Edit or download the full source.</p>');
  } else $('#read-content').innerHTML = `<div class="unsupported-preview"><span class="support-pill">${kind === 'pdf' ? 'PDF document' : 'File source'}</span><h3>Source retained.</h3><p>${escape(file.readError || (kind === 'pdf' ? 'PDF extraction needs a connected processing service. Download the original to open it in your PDF reader.' : 'This format is available for download. Text editing is unavailable.'))}</p><p>${escape(file.name)} · ${size(file.blob.size)}</p></div>`;
  if (state.editorMode === 'diff' && editable) renderDiff(file);
  if (file.position) { $('#file-editor').setSelectionRange(file.position.start || 0,file.position.end || 0); $('#file-editor').scrollTop = file.position.editScroll || 0; $('#read-content').scrollTop = file.position.readScroll || 0; $('#diff-content').scrollTop = file.position.diffScroll || 0; }
}
function openFile(id, toggle = false) {
  if (activePreparation || (currentRun && !terminal(currentRun.status))) { toast('Preparation is active. Pause or finish before opening a source.'); return; }
  if (currentRun && !$('#process-view').hidden) { toast('Review the result and choose Return to review first.'); return; }
  if (toggle && state.selectedFile === id && !$('#detail-panel').classList.contains('is-collapsed') && innerWidth > 960) { togglePanel('detail',false); return; }
  rememberEditor(); const previous = state.selectedFile; state.selectedFile = id; if (previous !== id) state.editorMode = 'read'; togglePanel('detail',true); renderEditor(); renderTree(); persist();
}
async function saveRevision() {
  const file = chosenFile(); if (!file || typeof file.draft !== 'string' || activePreparation) return;
  rememberEditor(); const prior = file.saved; file.saved = file.draft;
  if (!await persist(true)) { file.saved = prior; renderEditor(); return; }
  renderEditor(); renderTree(); toast('Revision saved in this browser.');
}
function download(name, content, type = 'text/plain') { const url = URL.createObjectURL(content instanceof Blob ? content : new Blob([content],{type})); const link = document.createElement('a'); link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url),1000); }
async function makeSource(blob, path, id = crypto.randomUUID()) {
  const file = { id, name:path.split('/').pop(), path, blob, type:blob.type, original:null, saved:null, draft:null, position:null, readError:null, inScope:true };
  if (sourceKind(file) === 'text' && blob.size <= MAX_TEXT_BYTES) { try { const text = new TextDecoder('utf-8',{fatal:true}).decode(await blob.arrayBuffer()); if (text.includes('\0')) throw new Error('Binary content cannot be edited as text.'); file.original = file.saved = file.draft = text; } catch (error) { file.readError = error.message; } }
  else if (sourceKind(file) === 'text') file.readError = 'Text exceeds the 2 MiB local reading limit. The original is available for download.';
  return file;
}
const sourceActions = { INPUT_SOURCE:'Input text', ADD_SOURCE:'Include existing source', IMPORT_SOURCE:'Import sources', REFERENCE_SOURCE:'Link a reference', REMOVE_SOURCE:'Remove from scope' };
function renderNotice() {
  const notice = state.lastNotice;
  $('#review-notice').hidden = !notice;
  if (!notice) return;
  $('#review-notice').dataset.status = notice.status;
  $('#review-notice').innerHTML = `<div><strong>${escape(notice.title)}</strong><p>${escape(notice.message)}</p>${notice.resultId ? `<button data-notice-result="${notice.resultId}">Open task output →</button>` : ''}</div><button id="dismiss-notice" class="icon-button" aria-label="Dismiss review notice">${icon('close')}</button>`;
}
function rejectRequest(label, message, action = 'unresolved', responsibility = 'Source management') {
  if (activePreparation || importBusy || currentRun) { toast('Finish or acknowledge the current operation first.'); return; }
  const time = new Date().toISOString();
  state.lastNotice = { title:`${label} — request rejected`, message, status:'rejected', time };
  state.history.push({ id:crypto.randomUUID(), task:action, taskLabel:label, responsibility, status:'rejected', total:state.selected.length, processed:0, characters:0, events:[{sequence:1,time,operation:'rejection',status:'rejected',message}], findings:[{sourceId:null,severity:'warning',message}], endedAt:time, resultId:null });
  state.systemNotes.push({kind:'event',text:`${label}: ${message}`,time});
  $('#import-dialog').close(); $('#review-view').hidden = false; $('#process-view').hidden = true;
  rememberEditor(); togglePanel('detail',true); renderNotice(); renderMessages(); announce(message); persist(true);
}
function sourceActionPane(name) {
  $$('[data-action-pane]').forEach(p=>p.hidden = p.dataset.actionPane !== name);
  $$('[data-source-action]').forEach(b=>{b.classList.toggle('active',b.dataset.sourceAction === name);b.setAttribute('aria-pressed',String(b.dataset.sourceAction===name));});
  if(name === 'existing') renderLibrary();
}
function openSourceActions(pane='import') {
  if (activePreparation || importBusy || currentRun) { toast('Finish or acknowledge the current operation first.'); return; }
  sourceActionPane(pane); $('#import-dialog').showModal();
}
function renderLibrary() {
  const query = $('#library-search').value.toLowerCase().trim();
  const files = state.sources.filter(f=>f.path.toLowerCase().includes(query));
  $('#library-list').innerHTML = files.length ? files.map(file=>`<div class="library-row"><div><strong>${escape(file.name)}</strong><small>${escape(file.path)}${file.draft !== file.saved ? ' · Draft retained' : ''}</small></div><button class="secondary-button" data-include-source="${file.id}" ${file.inScope !== false ? 'disabled' : ''}>${file.inScope !== false ? 'In scope' : 'Include'}</button></div>`).join('') : '<p class="empty-state">No retained sources match your search.</p>';
}
async function performSourceAction(action, total, build) {
  if (!workspaceReady || activePreparation || importBusy || currentRun) { toast('Finish the current operation before changing sources.'); return false; }
  rememberEditor(); importBusy = activePreparation = sourceCommitBusy = true; clearTimeout(persistTimer);
  $('#import-dialog').close(); $('#save-status').textContent = 'Updating source scope…';
  const run = {id:crypto.randomUUID(),task:action,taskLabel:sourceActions[action],responsibility:'Source management',route:'Source scope operation',status:'running',total,processed:0,characters:0,events:[],findings:[],result:null,sourceStates:{}};
  const emit = (operation,message,status='completed') => {run.events.push({sequence:run.events.length+1,time:new Date().toISOString(),operation,message,status});currentRun=run;renderProcess(run);};
  $('#review-view').hidden=true;$('#process-view').hidden=false;togglePanel('detail',true);renderScope();
  emit('accepted',`${sourceActions[action]} accepted for ${total} source${total===1?'':'s'}.`);
  try {
    state.activeRun=structuredClone(run);
    await saveWorkspace(state);
    const update = await build((message)=>{run.processed++;emit(action,message);});
    emit('storage','Saving the requested source state in this browser.','running');
    const report={...structuredClone(run),status:'completed',endedAt:new Date().toISOString(),resultId:null};
    report.events.push({sequence:report.events.length+1,time:report.endedAt,operation:'commit',message:'Source state committed to local workspace storage.',status:'completed'});
    const notice={title:`${sourceActions[action]} completed`,message:action==='REMOVE_SOURCE'?'Removed from the current scope. Contents and working revisions remain in the library.':action==='ADD_SOURCE'?'The retained source is in scope again with its original identity and working revision.':action==='REFERENCE_SOURCE'?'Reference saved. Linked content was not fetched or copied.':`${total} source${total===1?'':'s'} added to the current scope.`,status:'completed'};
    await saveWorkspace({...state,...update,activeRun:null,lastNotice:notice,history:[...state.history,report]});
    Object.assign(state,update);state.activeRun=null;state.history.push(report);state.lastNotice=notice;
    state.systemNotes.push({kind:'event',text:notice.message,time:report.endedAt});
    activePreparation=importBusy=sourceCommitBusy=false;currentRun=null;
    $('#process-view').hidden=true;$('#review-view').hidden=false;renderTree();renderEditor();renderMessages();renderResults();
    await persist(true);announce(notice.message);return true;
  } catch(error) {
    activePreparation=importBusy=sourceCommitBusy=false;currentRun=null;state.activeRun=null;
    const message=`The requested source change was not committed: ${error.message}`;
    run.status='failed';run.findings.push({sourceId:null,severity:'error',message});run.endedAt=new Date().toISOString();state.history.push(run);
    state.lastNotice={title:`${sourceActions[action]} failed`,message,status:'failed'};
    $('#process-view').hidden=true;$('#review-view').hidden=false;renderTree();renderEditor();announce(message);persist(true);return false;
  }
}
async function importFiles(files, action='IMPORT_SOURCE') {
  if(!files.length)return false;
  const oversized=files.find(blob=>blob.size>MAX_SOURCE_BYTES);
  if(oversized){rejectRequest(sourceActions[action],`${oversized.name} exceeds the 10 MiB limit. No files from this request were imported.`,action);return false;}
  return performSourceAction(action,files.length,async progress=>{
    const sources=state.sources.slice(),selected=state.selected.slice();let first;
    for(const blob of files){
      let path=blob.webkitRelativePath || `${action==='INPUT_SOURCE'?'Inputs':'Imported'}/${blob.name}`,base=path,n=2;
      while(sources.some(f=>f.path===path)){const dot=base.lastIndexOf('.');path=dot>base.lastIndexOf('/')?`${base.slice(0,dot)} (${n++})${base.slice(dot)}`:`${base} (${n++})`;}
      const source=await makeSource(blob,path);source.origin=action;sources.push(source);selected.push(source.id);first ||= source.id;progress(`Staged ${source.name} · ${size(blob.size)} for import.`);
    }
    // A previously open editor stays selected; imports are available in the tree.
    return {sources,selected,...(!state.selectedFile?{selectedFile:first,editorMode:'read'}:{})};
  });
}
async function includeSource(id) {
  const file=sourceById(id);if(!file || file.inScope!==false)return;
  await performSourceAction('ADD_SOURCE',1,async progress=>{progress(`Included ${file.name} using its retained identity.`);return {sources:state.sources.map(f=>f.id===id?{...f,inScope:true}:f),selected:[...new Set([...state.selected,id])]};});
}
async function removeSelected() {
  const ids=scopeSources().filter(f=>state.selected.includes(f.id)).map(f=>f.id);if(!ids.length)return;
  await performSourceAction('REMOVE_SOURCE',ids.length,async progress=>{
    for(const id of ids)progress(`Prepared scope removal for ${sourceById(id).name}; source content retained.`);
    return {sources:state.sources.map(f=>ids.includes(f.id)?{...f,inScope:false}:f),selected:state.selected.filter(id=>!ids.includes(id))};
  });
}
function renderProcess(run) {
  $('#process-view').dataset.status = run.status; $('#process-view').dataset.terminal = terminal(run.status);
  $('#process-state').textContent = run.status;
  $('#process-title').textContent = run.responsibility === 'Source management' ? `${run.taskLabel}…` : ({ running:'Inspecting your sources.', pausing:'Finishing the current read.', paused:'Take your time.', stopping:'Stopping preparation.', partial:'Context, with known gaps.', failed:'Some sources need attention.', stopped:'Preparation stopped.' })[run.status] || 'Requested output available.';
  $('#process-scope').textContent = `${run.taskLabel || 'Local preparation'} · ${run.route || 'Source inspection'} · ${run.total} sources${run.responsibility === 'Source management' ? '' : ` · Saved revisions${snapshotDirty ? ' · Unsaved edits excluded' : ''}`}`;
  $('#coverage-stats').innerHTML = `<div><strong>${run.processed}<span style="font-size:13px;color:var(--muted)"> / ${run.total}</span></strong><small>${run.responsibility==='Source management'?'Sources staged':'Sources inspected'}</small></div><div><strong>${short(run.characters)}</strong><small>Decoded characters</small></div><div><strong>${run.findings.length}</strong><small>Known findings</small></div>`;
  $('.coverage-caption').textContent=run.responsibility==='Source management'?'Sources staged · changes apply after storage commits':'File coverage · counts from completed inspections';
  $('#coverage-bar').style.width = `${run.total ? run.processed / run.total * 100 : 0}%`;
  const events = run.events.slice(-16);
  $('#process-events').innerHTML = events.map(event => `<div class="event-row"><span class="event-dot"></span><div><strong>${escape(event.operation.replace(/[-_]/g,' '))}</strong><p>${escape(event.message)}</p></div><time>${escape(clock(event.time))}</time></div>`).join('');
  $('#process-findings').innerHTML = terminal(run.status) ? run.findings.map(f => `<div class="finding">${escape(f.message)}</div>`).join('') : '';
  if (terminal(run.status)) { $('#process-events').before($('#process-findings'),$('#acknowledge-run')); }
  $('#acknowledge-run').hidden = !terminal(run.status);
  $('#pause-button').textContent = run.status === 'paused' ? 'Resume' : run.status === 'pausing' ? 'Pausing…' : 'Pause';
  $('#pause-button').disabled = !['running','paused'].includes(run.status);
  $('#stop-button').disabled = run.status === 'stopping';
  $('#status-summary').textContent = terminal(run.status) ? `${run.status} · ${run.processed}/${run.total} sources inspected` : `${run.status} · ${run.processed}/${run.total} sources`;
}
async function startPreparation() {
  if (importBusy || activePreparation || currentRun) return;
  const selected = scopeSources().filter(f => state.selected.includes(f.id));
  const task=state.requestedTask;
  const rejection=taskRejection(selected,task);
  if(rejection){rejectRequest(TASKS[task]?.label || 'Unresolved task',rejection,task,TASKS[task]?.responsibility || 'Unresolved');return;}
  state.lastNotice=null;renderNotice();
  rememberEditor(); snapshotDirty = selected.some(f => f.draft !== f.saved); restoreFocus = $('#detail-panel').contains(document.activeElement) || document.activeElement === $('#start-button');
  activePreparation = true; processor = new LocalPreparation(); let finalized = false, accepted = false, checkpointAt = 0;
  processor.addEventListener('update', event => {
    const run = event.detail; currentRun = run; state.activeRun = run;
    if (!accepted) {
      accepted = true; $('#review-view').hidden = true; $('#process-view').hidden = false; togglePanel('detail',true);
      checkpointAt = Date.now(); persist(true);
    } else if (Date.now() - checkpointAt > 1000 || ['paused','pausing','stopping'].includes(run.status)) {
      checkpointAt = Date.now(); persist(true);
    }
    renderProcess(run); renderTree();
    if (terminal(run.status) && !finalized) {
      finalized = true; activePreparation = false;
      const report = { ...structuredClone(run), endedAt:new Date().toISOString(), resultId:null };
      if (run.result) {
        const id = crypto.randomUUID(); const file = { id, name:`context-${state.results.length + 1}.md`, path:`Prepared/context-${state.results.length + 1}.md`, type:'text/markdown', blob:new Blob([run.result.text],{type:'text/markdown'}), original:run.result.text, saved:run.result.text, draft:run.result.text, generated:true, outcome:run.status, runId:run.id };
        state.results.push(file); report.resultId = id;
      }
      state.history.push(report); state.activeRun = null;
      state.lastNotice={title:run.status==='completed'?'Requested output available':run.status==='partial'?'Partial output with known gaps':run.status==='failed'?'No usable task output':'Operation stopped',message:`${run.taskLabel}: ${run.processed}/${run.total} sources inspected. ${run.findings.length} findings. Coverage applies to this requested task.`,status:run.status,resultId:report.resultId};
      for (const file of state.sources) if (run.sourceStates[file.id]) file.lastStatus = run.sourceStates[file.id];
      state.systemNotes.push({ kind:'event', text:`Local preparation ${run.status}: ${run.processed}/${run.total} sources inspected. ${run.findings.length} findings recorded.`, time:new Date().toISOString() });
      renderMessages(); renderResults(); renderScope(); announce(`Preparation ${run.status}. Review findings in the detail panel.`); persist(true);
      if (run.status === 'completed') returnToReview();
    }
  });
  try { await processor.start(selected.map(file => ({ id:file.id, name:file.name, path:file.path, type:file.type, blob:file.blob, reference:file.reference, original:file.saved, draft:file.draft })),task); }
  catch (error) { activePreparation = false; currentRun = null; state.activeRun = null; $('#process-view').hidden = true; $('#review-view').hidden = false; renderScope(); rejectRequest(TASKS[task].label,error.message,task,TASKS[task].responsibility); }
}
function returnToReview() {
  if (activePreparation) return;
  currentRun = null; $('#process-view').hidden = true; $('#review-view').hidden = false; renderEditor(); renderTree();
  if (restoreFocus && ($('#process-view').contains(document.activeElement) || document.activeElement === document.body)) { if (state.editorMode === 'edit') $('#file-editor').focus({preventScroll:true}); else $('#close-review').focus({preventScroll:true}); }
  announce('Editor restored. Prepared context is available in Sources.'); persist();
}
function openHistory() {
  $('#history-content').innerHTML = state.history.length ? state.history.slice().reverse().map(run => `<article class="history-run"><h3><span>${escape(run.taskLabel || 'Local preparation')} · ${escape(run.status)}</span><small>${escape(clock(run.endedAt || run.events.at(-1)?.time || Date.now()))}</small></h3><p>${escape(run.responsibility || 'Source inspection')} · ${run.processed} / ${run.total} sources · ${fmt(run.characters)} decoded characters · ${run.findings.length} findings</p><details><summary>Recorded events and findings</summary>${run.events.map(e => `<p>${escape(clock(e.time))} · ${escape(e.operation)} · ${escape(e.message)}</p>`).join('')}${run.findings.map(f => `<p>${escape(f.message)}</p>`).join('')}</details>${run.resultId ? `<button data-history-result="${run.resultId}">Open task output →</button>` : ''}</article>`).join('') : '<p class="empty-state">No operations yet. Choose a source action or inspection task.</p>';
  $('#export-history').disabled = !state.history.length; $('#history-dialog').showModal();
}
function openCommands() { $('#command-search').value = ''; renderCommands(''); $('#command-dialog').showModal(); $('#command-search').focus(); }
function renderCommands(query) {
  const actions = [{id:'add',name:'Add a source',icon:'plus'}, {id:'history',name:'Activity history',icon:'history'}, {id:'theme',name:'Switch color theme',icon:'sun'}, {id:'help',name:'Workspace capabilities',icon:'layers'}].filter(a => a.name.toLowerCase().includes(query));
  const files = [...scopeSources(),...state.results].filter(f => f.path.toLowerCase().includes(query));
  $('#command-results').innerHTML = actions.map(a=>`<button data-command="${a.id}">${icon(a.icon)}${a.name}<small>Action</small></button>`).join('') + files.map(f=>`<button data-command-file="${f.id}">${icon(sourceKind(f) === 'image' ? 'diagram' : 'document')}<span>${escape(f.name)}</span><small>${escape(f.path.split('/')[0])}</small></button>`).join('');
  if (!actions.length && !files.length) $('#command-results').innerHTML = '<p class="empty-state">No matching sources or actions.</p>';
}
function switchTheme() { state.theme = state.theme === 'light' ? 'dark' : 'light'; document.documentElement.dataset.theme = state.theme; persist(); }

document.addEventListener('click', async event => {
  const button = event.target.closest('button'); if (!button) return;
  if (button.dataset.view) togglePanel(button.dataset.view);
  if (button.dataset.toggle) togglePanel(button.dataset.toggle,false);
  if (button.dataset.file) openFile(button.dataset.file,true);
  if (button.dataset.folder) { state.folders[button.dataset.folder] = state.folders[button.dataset.folder] === false; renderTree(); persist(); }
  if (button.dataset.filter) { filter = button.dataset.filter; $$('.source-filters button').forEach(b=>b.classList.toggle('active',b===button)); renderTree(); }
  if (button.dataset.mode) { rememberEditor(); state.editorMode = button.dataset.mode; renderEditor(); persist(); }
  if (button.dataset.sourceAction) sourceActionPane(button.dataset.sourceAction);
  if (button.dataset.includeSource) await includeSource(button.dataset.includeSource);
  if (button.dataset.noticeResult) openFile(button.dataset.noticeResult);
  if (button.id === 'dismiss-notice') { state.lastNotice=null;renderNotice();persist(); }
  if (button.dataset.result) openFile(button.dataset.result);
  if (button.dataset.historyResult) { $('#history-dialog').close(); if (!activePreparation) returnToReview(); openFile(button.dataset.historyResult); }
  if (button.dataset.commandFile) { $('#command-dialog').close(); openFile(button.dataset.commandFile); }
  if (button.dataset.command) { $('#command-dialog').close(); ({add:()=>openSourceActions(), history:openHistory, theme:switchTheme, help:()=>$('#help-dialog').showModal()})[button.dataset.command](); }
  if (button.dataset.action === 'home') togglePanel('agent',true);
  if (button.dataset.action === 'sources') togglePanel('sources',true);
  if (button.dataset.action === 'history') openHistory();
  if (button.dataset.action === 'references') { const diagram = state.sources.find(f=>f.name === 'workflow-diagram.png'); if (diagram) openFile(diagram.id); }
  if (button.id === 'context-open-history') openHistory();
  if (button.id === 'attach-result') { const file = chosenFile(); state.agentAttachment = file.id; $('#agent-context').hidden = false; $('#agent-context').textContent = `Attached to draft: ${file.name} · ${file.outcome}`; togglePanel('agent',true); persist(); toast('Prepared context attached to your agent draft. No agent was run.'); }
});
$('#source-tree').addEventListener('change', event => {
  if (activePreparation) return;
  const input = event.target; let ids = [];
  if (input.dataset.select) ids = [input.dataset.select];
  if (input.dataset.folderSelect) ids = visibleSources().filter(f=>`/${f.path}`.startsWith(`${input.dataset.folderSelect}/`)).map(f=>f.id);
  state.selected = input.checked ? [...new Set([...state.selected,...ids])] : state.selected.filter(id=>!ids.includes(id)); renderTree(); persist();
});
$('#select-all').onchange = event => { const ids = visibleSources().map(f=>f.id); state.selected = event.target.checked ? [...new Set([...state.selected,...ids])] : state.selected.filter(id=>!ids.includes(id)); renderTree(); persist(); };
$('#source-search').oninput = event => { search = event.target.value.trim().toLowerCase(); renderTree(); };
$('#command-search').oninput = event => renderCommands(event.target.value.trim().toLowerCase());
$('#file-editor').oninput = event => { const file = chosenFile(); if (!file) return; file.draft = event.target.value; $('#revision-status').textContent = file.draft !== file.saved ? '● Unsaved revision' : 'Saved revision'; $('#revision-status').classList.toggle('dirty',file.draft !== file.saved); $('#save-file').disabled = file.draft === file.saved; $('#file-metadata').textContent = `${file.name.split('.').pop().toUpperCase()} · ${fmt(Array.from(file.draft).length)} chars`; rememberEditor(); renderTree(); persist(); };
for (const name of ['click','keyup','scroll']) $('#file-editor').addEventListener(name,()=>{ rememberEditor(); const line = $('#file-editor').value.slice(0,$('#file-editor').selectionStart).split('\n').length; $('#editor-position').textContent = `Line ${line} · Working revision`; });
$('#read-content').onscroll = rememberEditor; $('#diff-content').onscroll = rememberEditor;
$('#save-file').onclick = saveRevision;
$('#close-review').onclick = () => { rememberEditor(); togglePanel('detail',false); if (innerWidth <= 960) togglePanel('sources',true); };
$('#export-file').onclick = () => { const file = chosenFile(); if (file) download(file.name,typeof file.draft === 'string' ? file.draft : file.blob); };
$('#add-source').onclick = () => openSourceActions();
$('#source-library').onclick = () => openSourceActions('existing');
$('#remove-sources').onclick = removeSelected;
$('#library-search').oninput = renderLibrary;
$('#requested-task').onchange = event=>{state.requestedTask=event.target.value;renderScope();persist();};
$('#choose-files').onclick = () => $('#file-input').click(); $('#choose-folder').onclick = () => $('#folder-input').click();
$('#file-input').onchange = async event => { await importFiles([...event.target.files]); event.target.value = ''; };
$('#folder-input').onchange = async event => { await importFiles([...event.target.files]); event.target.value = ''; };
$('#text-source-form').onsubmit = async event => { event.preventDefault(); const content = $('#text-source-content').value; if (!content.trim()) { $('#text-source-content').focus(); toast('Add some text to create a source.'); return; } let name = $('#text-source-name').value.trim().replace(/[\\/]/g,'-') || 'Untitled.md'; if (!name.includes('.')) name += '.md'; if(await importFiles([new File([content],name,{type:'text/plain'})],'INPUT_SOURCE')) { $('#text-source-name').value = ''; $('#text-source-content').value = ''; } };
$('#reference-form').onsubmit = async event=>{
  event.preventDefault();let url;
  try{url=new URL($('#reference-url').value.trim());if(!['https:','http:'].includes(url.protocol)||url.username||url.password)throw new Error('Use an HTTP or HTTPS address without embedded credentials.');}
  catch(error){rejectRequest('Link a reference',error.message,'REFERENCE_SOURCE');return;}
  const existing=state.sources.find(f=>f.reference===url.href);
  if(existing){if(existing.inScope===false)await includeSource(existing.id);else toast('This reference is already in scope.');return;}
  const name=$('#reference-name').value.trim()||url.hostname;
  const done=await performSourceAction('REFERENCE_SOURCE',1,async progress=>{const file={id:crypto.randomUUID(),name,path:`References/${name}`,reference:url.href,origin:'REFERENCE_SOURCE',inScope:true,type:'reference',blob:null,original:null,saved:null,draft:null};progress(`Recorded reference ${name}; content not fetched.`);return {sources:[...state.sources,file],selected:[...state.selected,file.id]};});
  if(done){$('#reference-name').value='';$('#reference-url').value='';}
};
$('#other-source-form').onsubmit=event=>{event.preventDefault();const action=$('#other-source-action').value;rejectRequest(action==='delete'?'Delete underlying content':'Unknown source action',action==='delete'?'Deletion requires separate authority and is unavailable here. Remove from scope retains the source and its drafts in the library.':'The requested source operation is unresolved. Choose Input text, Import, Existing, Reference, or Remove from scope.',action);};
$('#agent-form').onsubmit = async event => { event.preventDefault(); const text = $('#agent-input').value.trim(); if (!text) return; state.agentNotes.push({ text, time:new Date().toISOString() }); state.agentDraft = ''; $('#agent-input').value = ''; renderMessages(); if(await persist(true)) toast('Agent draft saved locally.'); };
$('#system-form').onsubmit = async event => { event.preventDefault(); const text = $('#system-input').value.trim(); if (!text) return; state.systemNotes.push({ kind:'note',text,time:new Date().toISOString() }); state.systemDraft = ''; $('#system-input').value = ''; renderMessages(); if(await persist(true)) toast('Context note saved.'); };
$('#agent-input').oninput = event => { state.agentDraft = event.target.value; persist(); }; $('#system-input').oninput = event => { state.systemDraft = event.target.value; persist(); };
$('#start-button').onclick = startPreparation;
$('#pause-button').onclick = () => currentRun?.status === 'paused' ? processor.resume() : processor.pause();
$('#stop-button').onclick = () => processor?.stop();
$('#acknowledge-run').onclick = returnToReview;
$('#welcome-sources').onclick = $('#empty-browse').onclick = () => togglePanel('sources',true);
$('#command-open').onclick = openCommands; $('#theme-toggle').onclick = switchTheme; $('#help-open').onclick = () => $('#help-dialog').showModal();
$('#history-button').onclick = openHistory;
$('#export-history').onclick = () => download('oneshot-activity.json',JSON.stringify(state.history,null,2),'application/json');
const zoom = value => { const img = $('#source-image'); if (!img) return; imageZoom = Math.max(.5,Math.min(4,value)); img.style.width = imageZoom === 1 ? '' : `${imageZoom * 100}%`; img.style.maxWidth = imageZoom === 1 ? '100%' : 'none'; $('#zoom-reset').textContent = imageZoom === 1 ? 'Fit' : `${Math.round(imageZoom * 100)}%`; };
$('#zoom-in').onclick = () => zoom(imageZoom + .25); $('#zoom-out').onclick = () => zoom(imageZoom - .25); $('#zoom-reset').onclick = () => zoom(1);
$('#image-expand').onclick = () => { if (!imageURL) return; $('#expanded-image').src = imageURL; $('#expanded-image').alt = chosenFile().name; $('#image-dialog').showModal(); };
$('#sources-panel').addEventListener('dragover',event=>{event.preventDefault(); if(!activePreparation) $('#sources-panel').classList.add('drag-over');});
$('#sources-panel').addEventListener('dragleave',event=>{if(!$('#sources-panel').contains(event.relatedTarget)) $('#sources-panel').classList.remove('drag-over');});
$('#sources-panel').addEventListener('drop',event=>{event.preventDefault();$('#sources-panel').classList.remove('drag-over');importFiles([...event.dataTransfer.files]);});
document.addEventListener('dragover',event=>event.preventDefault()); document.addEventListener('drop',event=>event.preventDefault());
document.addEventListener('keydown',event=>{
  if (!workspaceReady) return;
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); if (!$$('dialog[open]').length) openCommands(); }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); saveRevision(); }
  if (event.key === '/' && !['INPUT','TEXTAREA'].includes(document.activeElement.tagName) && !$$('dialog[open]').length) { event.preventDefault(); togglePanel('sources',true); $('#source-search').focus(); }
  if (event.key === 'Enter' && document.activeElement === $('#command-search')) { event.preventDefault(); $('#command-results button')?.click(); }
});
$$('.resize-handle').forEach(handle=>{
  const resize = width => { const min = Number(handle.getAttribute('aria-valuemin')), max = Number(handle.getAttribute('aria-valuemax')); width = Math.max(min,Math.min(max,width)); document.documentElement.style.setProperty(handle.dataset.resize === 'agent' ? '--agent-width' : '--source-width',`${width}px`); if(handle.dataset.resize === 'agent') $('#agent-panel').style.flex = `0 0 ${width}px`; handle.setAttribute('aria-valuenow',Math.round(width)); };
  handle.addEventListener('pointerdown',event=>{ const startX = event.clientX, width = $(`#${handle.dataset.resize}-panel`).getBoundingClientRect().width; handle.setPointerCapture(event.pointerId); const move = e=>resize(width + e.clientX-startX); handle.addEventListener('pointermove',move); handle.addEventListener('pointerup',()=>handle.removeEventListener('pointermove',move),{once:true}); });
  handle.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();resize(Number(handle.getAttribute('aria-valuenow'))+(event.key==='ArrowLeft'?-15:15));}});
});
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden'){rememberEditor();persist(true);}});
window.addEventListener('beforeunload',event=>{if(activePreparation){event.preventDefault();event.returnValue='';}});

async function boot() {
  const saved = await loadWorkspace();
  if (saved?.version === 1) {
    state = { ...state,...saved };
    if (state.activeRun) { const run = structuredClone(state.activeRun); run.status = 'interrupted'; run.endedAt = new Date().toISOString(); run.findings.push({severity:'warning',sourceId:null,message:'The page closed before a terminal result was recorded. This run cannot resume; start a new preparation.'}); state.history.push(run); state.activeRun = null; toast('An interrupted preparation was recovered in Activity history.'); }
  } else {
    const references = [
      ['Architecture.md','Design/Architecture.md'],['workflow-diagram.png','Design/Diagrams/workflow-diagram.png'],['state-driven-transition.png','Design/Diagrams/state-driven-transition.png'],['UI-layout.txt','Design/Reviews/UI-layout.txt'],['UI-gap-review.txt','Design/Reviews/UI-gap-review.txt'],['Historical-rebuild-plan.txt','Historical references/Historical-rebuild-plan.txt'],['Historical-market-gap.txt','Historical references/Historical-market-gap.txt']
    ];
    for (const [name,path] of references) { const response = await fetch(`references/${name}`); if (!response.ok) throw new Error(`Reference unavailable: ${name}`); state.sources.push(await makeSource(await response.blob(),path)); }
    state.selected = state.sources.slice(0,3).map(f=>f.id); state.selectedFile = state.sources[1].id; state.folders['/Historical references'] = false; state.folders['/Design/Reviews'] = false;
  }
  if(state.referencePack < 2){
    for(const name of ['mermaid-diagram (2).png','mermaid-diagram (3).png']){
      const path=`Design/Diagrams/${name}`;
      if(!state.sources.some(file=>file.referenceKey===name || file.path===path)){
        const response=await fetch(`references/${encodeURIComponent(name)}`);
        if(!response.ok)throw new Error(`Reference unavailable: ${name}`);
        const file=await makeSource(await response.blob(),path);file.referenceKey=name;state.sources.push(file);
      }
    }
    state.referencePack=2;
  }
  state.selected=state.selected.filter(id=>scopeSources().some(file=>file.id===id));
  document.documentElement.dataset.theme = state.theme; $('#workbench').dataset.mobileView = state.mobileView; syncViewControls();
  state.collapsed.forEach(name=>$(`#${name}-panel`)?.classList.add('is-collapsed'));
  $('#agent-input').value = state.agentDraft; $('#system-input').value = state.systemDraft;
  if (state.agentAttachment) { const file = sourceById(state.agentAttachment); if(file){$('#agent-context').hidden=false;$('#agent-context').textContent=`Attached to draft: ${file.name} · ${file.outcome}`;} }
  renderTree(); renderResults(); renderMessages(); renderEditor();
  workspaceReady = true;
  for (const region of ['.topbar', '.viewbar', '#workbench']) $(region).inert = false;
  await persist(true);
}
boot().catch(error=>{
  toast(`Workspace could not open: ${error.message}`);
  $('#save-status').textContent = 'Workspace loading failed. ';
  const retry = document.createElement('button'); retry.textContent = 'Retry loading';
  retry.onclick = () => location.reload(); $('#save-status').append(retry);
});
