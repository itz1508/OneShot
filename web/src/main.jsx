import React, { useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
 ArrowUp,
 Check,
 ChevronRight,
 CircleAlert,
 FileCode2,
 FileJson2,
 FolderClosed,
 LoaderCircle,
 RefreshCw,
 Settings2,
 Sparkles,
 X,
} from 'lucide-react'
import './styles.css'

const json = async (response) => {
 let payload = {}
 try {
 payload = await response.json()
 } catch {
 payload = {}
 }

 if (!response.ok) {
 const detail =
 typeof payload.detail === 'string'
 ? payload.detail
 : typeof payload.error === 'string'
 ? payload.error
 : response.statusText || 'Request failed'
 const error = new Error(detail)
 error.status = response.status
 error.payload = payload
 throw error
 }

 return payload
}

const mergeEvents = (existing, incoming) => {
 const merged = new Map()
 for (const entry of existing) merged.set(Number(entry.sequence), entry)
 for (const entry of incoming) merged.set(Number(entry.sequence), entry)
 return Array.from(merged.values()).sort((a, b) => Number(a.sequence) - Number(b.sequence))
}

const lastSequence = (events) => events.reduce((max, event) => Math.max(max, Number(event.sequence) || 0), 0)
const titleize = (value) => String(value || '').replaceAll('_', ' ').replace(/\b\w/g, (match) => match.toUpperCase())
const formatTime = (value) => {
 if (!value) return ''
 const stamp = String(value)
 return stamp.includes('T') ? stamp.replace('T', ' ').replace('Z', ' UTC') : stamp
}
const eventSide = (type) => {
 const normalized = String(type || '').toLowerCase()
 if (normalized.includes('input')) return 'right'
 if (normalized.includes('error') || normalized.includes('blocked') || normalized.includes('conflict')) return 'left warn'
 if (normalized.includes('audit') || normalized.includes('research') || normalized.includes('stream')) return 'left host'
 return 'left'
}

function App() {
 const [prompt, setPrompt] = useState('')
 const [purpose, setPurpose] = useState('research')
 const [task, setTask] = useState(null)
 const [events, setEvents] = useState([])
 const [files, setFiles] = useState([])
 const [activeFile, setActiveFile] = useState(null)
 const [editText, setEditText] = useState('')
 const [loading, setLoading] = useState(false)
 const [error, setError] = useState('')
 const [hostHealthy, setHostHealthy] = useState(false)
 const [mcpConfigured, setMcpConfigured] = useState(false)
 const [streamState, setStreamState] = useState('idle')
 const [pinnedToBottom, setPinnedToBottom] = useState(true)
 const [focusMode, setFocusMode] = useState(false)
 const streamRef = useRef(null)
 const transcriptRef = useRef(null)
 const endRef = useRef(null)
 const pinnedRef = useRef(true)
 const streamCursor = useRef(0)
 const taskId = task?.task_id

 async function fetchDetails(id) {
 const [record, artifacts, timeline] = await Promise.all([
 fetch('/api/tasks/' + id).then(json),
 fetch('/api/tasks/' + id + '/artifacts').then(json),
 fetch('/api/tasks/' + id + '/events').then(json),
 ])

 const orderedEvents = mergeEvents([], timeline)
 setTask(record)
 setFiles(artifacts)
 setEvents(orderedEvents)
 streamCursor.current = lastSequence(orderedEvents)
 setPinnedToBottom(true)
 pinnedRef.current = true
 return record
 }

 useEffect(() => {
 fetch('/api/health')
 .then(json)
 .then((health) => {
 setHostHealthy(health.status === 'ok')
 setMcpConfigured(health.mcp_transport_configured === true)
 })
 .catch(() => setHostHealthy(false))
 }, [])

 useEffect(() => {
 let cancelled = false

 const restore = async () => {
 const id = new URLSearchParams(window.location.search).get('task')
 if (!id) {
 if (!cancelled) {
 setTask(null)
 setEvents([])
 setFiles([])
 setActiveFile(null)
 setError('')
 setStreamState('idle')
 streamCursor.current = 0
 }
 return
 }

 try {
 if (!cancelled) setStreamState('connecting')
 await fetchDetails(id)
 if (!cancelled) setError('')
 } catch (exc) {
 if (!cancelled) {
 setTask(null)
 setEvents([])
 setFiles([])
 setActiveFile(null)
 setError(exc.message)
 setStreamState('error')
 streamCursor.current = 0
 }
 }
 }

 restore()
 window.addEventListener('popstate', restore)
 return () => {
 cancelled = true
 window.removeEventListener('popstate', restore)
 }
 }, [])

 useEffect(() => {
 streamRef.current?.close()
 if (!taskId) {
 setStreamState('idle')
 return undefined
 }

 const source = new EventSource('/api/tasks/' + taskId + '/stream?after=' + streamCursor.current)
 streamRef.current = source
 setStreamState('connecting')

 source.onopen = () => {
 setStreamState('connected')
 setError('')
 }

 source.addEventListener('activity', (message) => {
 const entry = JSON.parse(message.data)
 setEvents((current) => mergeEvents(current, [entry]))
 streamCursor.current = Math.max(streamCursor.current, Number(entry.sequence) || 0)
 })

 source.addEventListener('stream_error', (message) => {
 let payload = {}
 try {
 payload = JSON.parse(message.data)
 } catch {
 payload = {}
 }
 setStreamState('reconnecting')
 setError(payload.code === 'EVENT_READ_FAILED' ? 'Live event history could not be read. The browser will retry automatically.' : 'Live stream interrupted. Reconnecting automatically.')
 })

 source.onerror = () => {
 setStreamState('reconnecting')
 setError('Live stream interrupted. Reconnecting automatically.')
 }

 return () => source.close()
 }, [taskId])

 useEffect(() => {
 if (pinnedRef.current) {
 endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
 }
 }, [taskId, events.length, files.length, streamState])

 const canRun = task && task.current_stage === 'research' && ['audit_pending', 'awaiting_mcp', 'audit_recovery_required'].includes(task.execution_status) && (task.purpose === 'audit' || mcpConfigured)
 const currentStage = task?.current_stage || 'Idle'
 const streamStatusLabel =
 streamState === 'connected'
 ? 'Live stream connected'
 : streamState === 'connecting'
 ? 'Connecting live stream'
 : streamState === 'reconnecting'
 ? 'Reconnecting live stream'
 : streamState === 'error'
 ? 'Live stream error'
 : 'Live stream idle'
 const nextActionLabel = task
 ? canRun
 ? `Run ${task.purpose === 'audit' ? 'Audit' : 'Research'} on the host`
 : task.purpose !== 'audit' && !mcpConfigured && task.execution_status === 'awaiting_mcp'
 ? 'Configure an MCP Research server in the host environment, then restart the API.'
 : task.execution_status === 'audit_completed'
 ? 'Review the audit artifact or wait for the host to advance.'
 : 'The host controls completion, approvals, and receipts.'
 : 'Create a task to begin a live workflow.'

 const messages = useMemo(() => {
 const items = []
 if (!task) {
 items.push({
 id: 'empty-state',
 side: 'left host',
 sender: 'OneShot',
 label: 'System Chat',
 text: 'Submit a task to open a real host-backed workflow. The transcript below is driven by live state and SSE events, not a fake replay.',
 meta: 'Waiting for a task',
 })
 return items
 }

 items.push({
 id: 'request',
 side: 'right user',
 sender: 'You',
 label: `Task request · ${task.purpose || 'research'}`,
 text: task.input_text,
 meta: `Task ${task.task_id.slice(0, 8)} · ${currentStage}`,
 })

 items.push({
 id: 'status',
 side: 'left host',
 sender: 'Host state',
 label: 'Current execution',
 text: `Stage: ${task.current_stage}\nStatus: ${task.execution_status}\nCapability: ${titleize(task.purpose)}`,
 meta: `${files.length} artifacts · ${events.length} events`,
 })

 if (streamState !== 'connected') {
 items.push({
 id: 'stream-state',
 side: 'left host',
 sender: 'Live stream',
 label: streamStatusLabel,
 text: streamState === 'error' ? 'The browser will retry automatically and replay from the current cursor when the stream returns.' : 'Subscribing to the server event stream…',
 meta: task.task_id.slice(0, 8),
 })
 }

 for (const event of events) {
 items.push({
 id: `event-${event.sequence}`,
 side: eventSide(event.type),
 sender: titleize(event.type),
 label: `Event ${event.sequence}`,
 text: event.message,
 meta: formatTime(event.created_at),
 })
 }

 if (files.length) {
 items.push({
 id: 'artifacts',
 side: 'left host',
 sender: 'Artifacts',
 label: 'Latest snapshot',
 text: files.map((file) => `${file.name} · rev ${file.revision}`).join('\n'),
 meta: 'Open a file to inspect or edit supported artifacts.',
 })
 }

 return items
 }, [task, events, files, streamState, streamStatusLabel, currentStage])

 function handleTranscriptScroll() {
 const shell = transcriptRef.current
 if (!shell) return
 const threshold = 56
 const atBottom = shell.scrollHeight - shell.scrollTop - shell.clientHeight < threshold
 pinnedRef.current = atBottom
 setPinnedToBottom(atBottom)
 }

 async function submit(event) {
 event.preventDefault()
 if (!prompt.trim() || loading) return
 setLoading(true)
 setError('')
 try {
 const record = await fetch('/api/tasks', {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify({ prompt, purpose }),
 }).then(json)
 window.history.replaceState(null, '', '?task=' + record.task_id)
 setPrompt('')
 await fetchDetails(record.task_id)
 } catch (exc) {
 setError(exc.message)
 } finally {
 setLoading(false)
 }
 }

 async function runTask() {
 if (!task || loading || !canRun) return
 setLoading(true)
 setError('')
 try {
 const selected = task.purpose === 'audit' ? 'audit' : 'research'
 await fetch('/api/tasks/' + task.task_id + '/' + selected, { method: 'POST' }).then(json)
 await fetchDetails(task.task_id)
 } catch (exc) {
 await fetchDetails(task.task_id).catch(() => {})
 setError(exc.message)
 } finally {
 setLoading(false)
 }
 }

 function openFile(file) {
 setActiveFile(file)
 setEditText(file.kind === 'input' ? task?.input_text || '' : file.content || '')
 }

 async function saveInput() {
 if (!task || !activeFile || activeFile.kind !== 'input') return
 setLoading(true)
 try {
 const updated = await fetch('/api/tasks/' + task.task_id + '/input', {
 method: 'PATCH',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify({ text: editText, expected_revision: task.input_revision }),
 }).then(json)
 await fetchDetails(updated.task_id)
 setActiveFile(null)
 setError('')
 } catch (exc) {
 if (String(exc.message).includes('conflict')) {
 await fetchDetails(task.task_id).catch(() => {})
 }
 setError(exc.message)
 } finally {
 setLoading(false)
 }
 }

 const fileListPreview = files.slice().reverse().slice(0, 4)

 return (
 <div className={'app ' + (focusMode ? 'focus' : '')}>
 <aside className="rail" aria-label="Primary navigation">
 <div className="brand">
 <span className="brand-orbit" />
 </div>
 <nav className="rail-nav">
 <button className="rail-button active" type="button" aria-label="System chat">
 <Sparkles size={18} />
 <span>Chat</span>
 </button>
 <button className="rail-button" type="button" aria-label="Task summary" onClick={() => document.getElementById('summary')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>
 <FolderClosed size={18} />
 <span>Task</span>
 </button>
 <button className="rail-button" type="button" aria-label="Artifacts" onClick={() => document.getElementById('artifactPanel')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>
 <FileJson2 size={18} />
 <span>Files</span>
 </button>
 </nav>
 <button className="rail-button rail-settings" type="button" aria-label="Settings" onClick={() => setFocusMode((value) => !value)}>
 <Settings2 size={18} />
 <span>{focusMode ? 'Exit' : 'Focus'}</span>
 </button>
 </aside>

 <main className="workspace">
 <header className="topbar">
 <div className="topbar-title">
 <div className="wordmark">OneShot</div>
 <div className="title-copy">
 <strong>{task ? 'Live workflow chat' : 'System Chat'}</strong>
 <span>{task ? `Task ${task.task_id.slice(0, 8)}` : 'Real-time transcript backed by host state'}</span>
 </div>
 </div>
 <div className="topbar-meta">
 <span className={hostHealthy ? 'chip live' : 'chip muted'}>
 <span className="dot" />
 {hostHealthy ? 'Host connected' : 'Host unavailable'}
 </span>
 <span className={streamState === 'connected' ? 'chip live' : 'chip muted'}>
 <span className="dot" />
 {streamStatusLabel}
 </span>
 <button className="icon-button" type="button" onClick={() => task && fetchDetails(task.task_id).catch((exc) => setError(exc.message))} aria-label="Refresh task">
 <RefreshCw size={16} />
 </button>
 </div>
 </header>

 <section className="main-grid">
 <div className="chat-panel panel">
 <div className="panel-head">
 <div>
 <div className="eyebrow">SYSTEM CHAT</div>
 <h1>One workflow, live transcript</h1>
 </div>
 <div className="panel-status">
 <span>{events.length} events</span>
 <span>{files.length} artifacts</span>
 </div>
 </div>

 <div className="transcript" ref={transcriptRef} onScroll={handleTranscriptScroll} aria-label="Live chat transcript" role="log" aria-live="polite">
 {messages.map((message) => (
 <article key={message.id} className={`message ${message.side}`}>
 <div className="avatar">{message.sender.slice(0, 1).toUpperCase()}</div>
 <div className="bubble-wrap">
 <div className="bubble-meta">
 <strong>{message.sender}</strong>
 <span>{message.label}</span>
 {message.meta ? <small>{message.meta}</small> : null}
 </div>
 <div className="bubble">
 {String(message.text || '')
 .split('\n')
 .map((line, index) => (
 <p key={`${message.id}-${index}`}>{line || '\u00a0'}</p>
 ))}
 </div>
 </div>
 </article>
 ))}
 <div ref={endRef} />
 </div>

 <div className="composer-area">
 {error ? (
 <div className="alert" role="alert">
 <CircleAlert size={16} />
 <span>{error}</span>
 <button type="button" aria-label="Dismiss error" onClick={() => setError('')}>
 <X size={14} />
 </button>
 </div>
 ) : null}

 <form className="composer" onSubmit={submit}>
 <textarea
 aria-label="Task request"
 placeholder="Message OneShot… create a live host-backed task"
 rows={2}
 value={prompt}
 onChange={(e) => setPrompt(e.target.value)}
 onKeyDown={(e) => {
 if (e.key === 'Enter' && !e.shiftKey) {
 e.preventDefault()
 e.currentTarget.form.requestSubmit()
 }
 }}
 />
 <div className="composer-row">
 <label className="purpose-picker">
 <span>Capability</span>
 <select aria-label="Task capability" value={purpose} onChange={(e) => setPurpose(e.target.value)} disabled={loading}>
 <option value="research">Research</option>
 <option value="audit">Audit</option>
 </select>
 </label>
 <div className="composer-hint">Enter to send · Shift+Enter for new line</div>
 <button className="send-button" type="submit" disabled={!prompt.trim() || loading} aria-label="Submit task">
 {loading ? <LoaderCircle size={17} className="spin" /> : <ArrowUp size={17} />}
 </button>
 </div>
 </form>
 </div>
 </div>

 <aside className="summary-panel panel" id="summary">
 <div className="summary-block">
 <div className="eyebrow">TASK SUMMARY</div>
 <h2>{task ? 'Host-backed workflow' : 'No task loaded'}</h2>
 <p>{nextActionLabel}</p>
 </div>

 <div className="summary-stat">
 <span>Current stage</span>
 <strong>{currentStage}</strong>
 </div>
 <div className="summary-stat">
 <span>Execution</span>
 <strong>{task?.execution_status || 'idle'}</strong>
 </div>
 <div className="summary-stat">
 <span>Capability</span>
 <strong>{task ? titleize(task.purpose) : purpose}</strong>
 </div>

 <div className="summary-actions">
 <button className="primary-button" type="button" onClick={runTask} disabled={!canRun || loading}>
 {loading ? 'Running…' : task ? `Run ${task.purpose === 'audit' ? 'Audit' : 'Research'}` : 'Create a task first'}
 </button>
 <div className="action-help">
 {canRun ? 'This calls the real supported API action.' : task ? 'The host determines when this action is available.' : 'No task to execute yet.'}
 </div>
 </div>

 <div className="artifact-block" id="artifactPanel">
 <div className="artifact-head">
 <div className="eyebrow">ARTIFACTS</div>
 <span>{files.length} files</span>
 </div>
 <div className="artifact-list">
 {fileListPreview.length ? (
 fileListPreview.map((file) => (
 <button key={file.name} type="button" className="artifact-row" onClick={() => openFile(file)}>
 <FileCode2 size={15} />
 <span>
 <strong>{file.name}</strong>
 <small>{file.kind === 'input' ? 'Editable input' : 'Read-only artifact'} · rev {file.revision}</small>
 </span>
 <ChevronRight size={14} />
 </button>
 ))
 ) : (
 <div className="empty-note">Artifact snapshots appear here after the host persists them.</div>
 )}
 </div>
 </div>

 <div className="artifact-block">
 <div className="artifact-head">
 <div className="eyebrow">EVIDENCE STREAM</div>
 <span>{events.length} events</span>
 </div>
 <div className="event-list">
 {events.slice(-8).reverse().map((event) => (
 <div key={event.sequence} className="event-row">
 <span className="event-seq">#{event.sequence}</span>
 <div>
 <strong>{titleize(event.type)}</strong>
 <p>{event.message}</p>
 </div>
 </div>
 ))}
 {!events.length ? <div className="empty-note">Live host events will appear here.</div> : null}
 </div>
 </div>

 <div className="artifact-block hint-block">
 <div className="eyebrow">LIVE STATUS</div>
 <p>{pinnedToBottom ? 'Auto-scroll is following the live transcript.' : 'Auto-scroll paused because you scrolled away.'}</p>
 </div>
 </aside>
 </section>
 </main>

 {activeFile ? (
 <div className="modal-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) setActiveFile(null) }}>
 <div className="review-modal" role="dialog" aria-modal="true" aria-label="Review artifact">
 <header>
 <span>
 <FileCode2 size={18} />
 {activeFile.name}
 <small>rev {activeFile.revision}</small>
 </span>
 <button className="icon-button" aria-label="Close artifact" onClick={() => setActiveFile(null)}>
 <X size={18} />
 </button>
 </header>
 <div className="modal-meta">
 {activeFile.kind === 'input' ? 'Editable input with revision checks' : 'Read-only artifact'}
 </div>
 <label htmlFor="file-editor">Artifact content</label>
 <textarea id="file-editor" spellCheck="false" value={editText} readOnly={activeFile.kind !== 'input'} onChange={(e) => setEditText(e.target.value)} />
 <footer>
 <span>{activeFile.kind === 'input' ? 'Saving uses the current expected revision.' : 'This artifact cannot be edited.'}</span>
 <button className="secondary-button" onClick={() => setActiveFile(null)}>Close</button>
 {activeFile.kind === 'input' ? (
 <button className="primary-button" disabled={loading || !editText.trim()} onClick={saveInput}>
 {loading ? 'Saving…' : 'Save revision'}
 </button>
 ) : null}
 </footer>
 </div>
 </div>
 ) : null}

 <div className="sr-only" aria-live="polite" aria-atomic="true">
 {error || streamStatusLabel}
 </div>
 </div>
 )
}

createRoot(document.getElementById('root')).render(<App />)
