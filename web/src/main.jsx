import React, { useEffect, useRef, useState } from 'react'
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
  PanelLeftClose,
  RefreshCw,
  Settings2,
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
  for (const entry of existing) merged.set(entry.sequence, entry)
  for (const entry of incoming) merged.set(entry.sequence, entry)
  return Array.from(merged.values()).sort((a, b) => Number(a.sequence) - Number(b.sequence))
}

const lastSequence = (events) => events.reduce((max, event) => Math.max(max, Number(event.sequence) || 0), 0)
const capabilityLabel = (purpose) => (purpose === 'audit' ? 'Audit' : 'Research')
const shortDigest = (digest) => (digest ? `${digest.slice(0, 8)}…${digest.slice(-6)}` : '—')

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
  const [narrow, setNarrow] = useState(false)
  const [focusMode, setFocusMode] = useState(false)
  const [hostHealthy, setHostHealthy] = useState(false)
  const [streamState, setStreamState] = useState('idle')
  const [pinnedToBottom, setPinnedToBottom] = useState(true)
  const streamRef = useRef(null)
  const bottom = useRef(null)
  const conversation = useRef(null)
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
      .then((health) => setHostHealthy(health.status === 'ok'))
      .catch(() => setHostHealthy(false))
  }, [])

  useEffect(() => {
    let cancelled = false

    const restoreFromLocation = async () => {
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

    restoreFromLocation()
    window.addEventListener('popstate', restoreFromLocation)
    return () => {
      cancelled = true
      window.removeEventListener('popstate', restoreFromLocation)
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
      setEvents((old) => mergeEvents(old, [entry]))
      streamCursor.current = Math.max(streamCursor.current, Number(entry.sequence) || 0)
    })

    source.addEventListener('stream_error', (message) => {
      let payload = {}
      try {
        payload = JSON.parse(message.data)
      } catch {
        payload = {}
      }
      setStreamState('error')
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
      bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [taskId, events.length])

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

      history.replaceState(null, '', '?task=' + record.task_id)
      setPrompt('')
      await fetchDetails(record.task_id)
    } catch (exc) {
      setError(exc.message)
    } finally {
      setLoading(false)
    }
  }

  async function runTask() {
    if (!task || loading) return
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

  function handleConversationScroll() {
    const shell = conversation.current
    if (!shell) return
    const threshold = 56
    const atBottom = shell.scrollHeight - shell.scrollTop - shell.clientHeight < threshold
    pinnedRef.current = atBottom
    setPinnedToBottom(atBottom)
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

  const currentStage = task?.current_stage || 'Idle'
  const currentStatus = task?.execution_status || 'not_started'
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
  const nextAction = task
    ? task.purpose === 'audit'
      ? 'Use Audit only when the host allows it.'
      : 'Run Research when the host marks the task ready.'
    : 'Create a task to begin.'

  return (
    <div className={'app ' + (focusMode ? 'app--focus' : '')}>
      <aside className={'sidebar ' + (narrow || focusMode ? 'collapsed' : '')}>
        <div className="brand">
          <span className="brand-icon">O</span>
          {!narrow && !focusMode && (
            <>
              <strong>OneShot</strong>
              <small>WORKBENCH</small>
            </>
          )}
          <button className="icon-button collapse-button" aria-label="Toggle sidebar" onClick={() => setNarrow(!narrow)}>
            <PanelLeftClose size={17} />
          </button>
        </div>
        {!narrow && !focusMode && (
          <div className="side-content">
            <div className="section-title">
              <span>WORKSPACE</span>
              <span className="item-count">{files.length}</span>
            </div>
            <div className="file-tree">
              <div className="folder">
                <FolderClosed size={15} /> Current task
              </div>
              {files.map((file) => (
                <button key={file.name} className="file-item" onClick={() => openFile(file)}>
                  <FileJson2 size={15} />
                  <span>{file.name}</span>
                  <ChevronRight size={14} className="f-chevron" />
                </button>
              ))}
              {!files.length && <div className="muted-note">Submit a task to generate an input artifact.</div>}
            </div>
            <div className="repo-info">
              <div className="section-title">REPOSITORY SUMMARY</div>
              <div className="info-line">
                <span>Source</span>
                <strong>OneShot</strong>
              </div>
              <div className="info-line">
                <span>Stage</span>
                <strong>{currentStage}</strong>
              </div>
              <div className="info-line">
                <span>Capability</span>
                <strong>{task?.purpose || purpose}</strong>
              </div>
              <div className="info-line">
                <span>Artifacts</span>
                <strong>{files.length}</strong>
              </div>
              <div className="info-line">
                <span>Events</span>
                <strong>{events.length}</strong>
              </div>
            </div>
          </div>
        )}
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div className="crumb">
            Workspace <ChevronRight size={15} /> <strong>{task ? 'Task ' + task.task_id.slice(0, 8) : 'New task'}</strong>
          </div>
          <div className="header-actions">
            <div className="status-dot">
              <span style={{ background: hostHealthy ? '#38bd9a' : '#a77562' }} />
              {hostHealthy ? 'Host connected' : 'Host unavailable'}
            </div>
            <button
              className="icon-button"
              title={focusMode ? 'Exit focus mode' : 'Focus work layer'}
              onClick={() => setFocusMode((value) => !value)}
            >
              {focusMode ? 'Exit' : 'Focus'}
            </button>
            <button className="icon-button" title="Refresh task" onClick={() => task && fetchDetails(task.task_id).catch((e) => setError(e.message))}>
              <RefreshCw size={17} />
            </button>
            <button className="icon-button" title="Settings" onClick={() => setError('Settings are managed by the host configuration.') }>
              <Settings2 size={17} />
            </button>
          </div>
        </header>
        <div className="conversation" ref={conversation} onScroll={handleConversationScroll}>
          <div className="content-shell">
            {!task && (
              <div className="empty-state">
                <div className="hero-shape">
                  <div className="hero-inner">O</div>
                </div>
                <p className="eyebrow">ONE WORKSPACE. ONE WORKFLOW.</p>
                <h1>What will you build today?</h1>
                <p className="subtitle">Describe a task to create a persistent OneShot workflow record. Agent execution is available after MCP integration.</p>
              </div>
            )}
            {task && (
              <>
                <div className="task-heading">
                  <span className="eyebrow">TASK SESSION</span>
                  <h1>Workflow activity</h1>
                  <p className="subtitle">Host-owned task state and recorded events, streamed as they occur.</p>
                </div>

                <div className="status-grid">
                  <article className="status-card">
                    <span>Current stage</span>
                    <strong>{currentStage}</strong>
                  </article>
                  <article className="status-card">
                    <span>Status</span>
                    <strong>{currentStatus}</strong>
                  </article>
                  <article className="status-card">
                    <span>Live stream</span>
                    <strong>{streamStatusLabel}</strong>
                  </article>
                </div>

                <div className="user-message">
                  <div className="message-label">REQUEST · {task.purpose || 'research'}</div>
                  <p>{task.input_text}</p>
                </div>

                <div className="execution-control">
                  <span role="status" aria-label="Execution status">
                    {task.execution_status}
                  </span>
                  {task.current_stage === 'research' && ['audit_pending', 'awaiting_mcp', 'audit_recovery_required'].includes(task.execution_status) && (
                    <button className="primary" type="button" onClick={runTask} disabled={loading}>
                      {loading ? 'Running...' : task.execution_status === 'audit_recovery_required' ? 'Resume Audit' : 'Run ' + capabilityLabel(task.purpose)}
                    </button>
                  )}
                </div>

                <div className="workspace-hint">
                  <div>
                    <strong>Next authorized action</strong>
                    <p>{nextAction}</p>
                  </div>
                  <div className="artifact-summary">
                    <span>{files.length} artifacts</span>
                    <span>{events.length} events</span>
                  </div>
                </div>

                <div className="timeline-heading">
                  <span>LIVE ACTIVITY</span>
                  <span>{events.length} EVENTS</span>
                </div>
                <div className="timeline">
                  {events.map((event) => (
                    <div key={event.sequence} className="activity">
                      <div className="activity-indicator">
                        <Check size={13} />
                      </div>
                      <div>
                        <div className="activity-title">{String(event.type || '').replaceAll('_', ' ')}</div>
                        <div className="activity-description">{event.message}</div>
                        <div className="activity-time">{event.created_at}</div>
                      </div>
                    </div>
                  ))}
                  <div ref={bottom} />
                </div>

                {task.execution_status === 'awaiting_mcp' && (
                  <div className="integration-warning">
                    <CircleAlert size={17} />
                    <div>
                      <strong>Research transport required</strong>
                      <p>Research requires a configured MCP provider; no agent output is simulated.</p>
                    </div>
                  </div>
                )}
                {task.purpose === 'audit' && task.execution_status === 'audit_completed' && (
                  <div className="integration-warning">
                    <Check size={17} />
                    <div>
                      <strong>Audit findings persisted</strong>
                      <p>Static scanning completed. The Research stage remains open until a valid ResearchRecord is accepted.</p>
                    </div>
                  </div>
                )}
                {task.execution_status === 'audit_blocked' && (
                  <div className="integration-warning">
                    <CircleAlert size={17} />
                    <div>
                      <strong>Audit blocked</strong>
                      <p>Review the stored findings and limitations; no stage advancement occurred.</p>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        <div className="composer-wrap">
          {error && (
            <div role="alert" className="error">
              <CircleAlert size={15} />
              {error}
              <button aria-label="Dismiss" onClick={() => setError('')}>
                <X size={14} />
              </button>
            </div>
          )}
          <form className="composer" onSubmit={submit}>
            <textarea
              aria-label="Task description"
              placeholder="Describe what you want OneShot to work on..."
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
            <div className="composer-bottom">
              <label className="mode-picker">
                Capability
                <select aria-label="Task capability" value={purpose} onChange={(e) => setPurpose(e.target.value)} disabled={loading}>
                  <option value="research">Research</option>
                  <option value="audit">Audit</option>
                </select>
              </label>
              <span>Enter to submit · Shift+Enter for a new line</span>
              <button className="send" disabled={!prompt.trim() || loading} aria-label="Submit task">
                {loading ? <LoaderCircle size={17} className="spin" /> : <ArrowUp size={18} />}
              </button>
            </div>
          </form>
          <div className="footnote">MVP · Persistent host state · No simulated agent results</div>
        </div>
      </main>

      {activeFile && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) setActiveFile(null) }}>
          <div className="review-modal" role="dialog" aria-modal="true" aria-label="Review artifact">
            <header>
              <span>
                <FileCode2 size={18} /> {activeFile.name} <small>rev {activeFile.revision}</small>
              </span>
              <button className="icon-button" aria-label="Close" onClick={() => setActiveFile(null)}>
                <X size={18} />
              </button>
            </header>
            <div className="modal-meta">
              Digest {shortDigest(activeFile.digest)} · {activeFile.kind === 'input' ? 'Revisioned input editing with conflict protection' : 'Verified, read-only artifact'}
            </div>
            <label htmlFor="file-editor">{activeFile.kind === 'input' ? 'Task description' : 'Artifact content'}</label>
            <textarea id="file-editor" spellCheck="false" value={editText} readOnly={activeFile.kind !== 'input'} onChange={(e) => setEditText(e.target.value)} />
            <footer>
              <span>{activeFile.kind === 'input' ? 'Original content preserved in earlier revisions' : 'Read-only source of evidence'}</span>
              <button className="secondary" onClick={() => setActiveFile(null)}>Close</button>
              {activeFile.kind === 'input' && (
                <button className="primary" disabled={loading || !editText.trim()} onClick={saveInput}>
                  {loading ? 'Saving...' : 'Save revision'}
                </button>
              )}
            </footer>
          </div>
        </div>
      )}

      <div className="sr-status" aria-live="polite" aria-atomic="true">
        {error || streamStatusLabel}
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')).render(<App />)
