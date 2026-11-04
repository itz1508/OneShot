import React, { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { ArrowUp, Check, ChevronRight, CircleAlert, FileCode2, FileJson2, FolderClosed, LoaderCircle, PanelLeftClose, RefreshCw, Settings2, X } from 'lucide-react'
import './styles.css'

const json = async (response) => {
  let payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || 'Request failed')
  return payload
}

function App() {
  const [prompt, setPrompt] = useState('')
  const [task, setTask] = useState(null)
  const [events, setEvents] = useState([])
  const [files, setFiles] = useState([])
  const [activeFile, setActiveFile] = useState(null)
  const [editText, setEditText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [narrow, setNarrow] = useState(false)
  const streamRef = useRef(null)
  const bottom = useRef(null)
  const taskId = task?.task_id

  async function fetchDetails(id) {
    const [record, artifacts, timeline] = await Promise.all([
      fetch('/api/tasks/' + id).then(json),
      fetch('/api/tasks/' + id + '/artifacts').then(json),
      fetch('/api/tasks/' + id + '/events').then(json),
    ])
    setTask(record)
    setFiles(artifacts)
    setEvents(timeline)
    return record
  }

  useEffect(() => {
    const id = new URLSearchParams(location.search).get('task')
    if (!id) return
    fetchDetails(id).catch((exc) => setError(exc.message))
  }, [])

  useEffect(() => {
    streamRef.current?.close()
    if (!taskId) return
    const source = new EventSource('/api/tasks/' + taskId + '/stream')
    streamRef.current = source
    source.addEventListener('activity', (message) => {
      const entry = JSON.parse(message.data)
      setEvents((old) => old.some((it) => it.sequence === entry.sequence) ? old : [...old, entry])
    })
    source.onerror = () => setError('Live stream interrupted. Reconnecting automatically.')
    source.onopen = () => setError('')
    return () => source.close()
  }, [taskId])

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }) }, [events])

  async function submit(event) {
    event.preventDefault()
    if (!prompt.trim() || loading) return
    setLoading(true)
    setError('')
    try {
      const record = await fetch('/api/tasks', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt }),
      }).then(json)
      history.replaceState(null, '', '?task=' + record.task_id)
      setPrompt('')
      await fetchDetails(record.task_id)
    } catch (exc) {
      setError(exc.message)
    } finally { setLoading(false) }
  }

  function openFile(file) {
    setActiveFile(file)
    setEditText(task?.input_text || '')
  }

  async function saveInput() {
    if (!task || !activeFile) return
    setLoading(true)
    try {
      const updated = await fetch('/api/tasks/' + task.task_id + '/input', {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: editText, expected_revision: task.input_revision }),
      }).then(json)
      await fetchDetails(updated.task_id)
      setActiveFile(null)
      setError('')
    } catch (exc) { setError(exc.message) }
    finally { setLoading(false) }
  }

  return (
    <div className="app">
      <aside className={'sidebar ' + (narrow ? 'collapsed' : '')}>
        <div className="brand">
          <span className="brand-icon">O</span>
          {!narrow && <><strong>OneShot</strong><small>WORKBENCH</small></>}
          <button className="icon-button collapse-button" aria-label="Toggle sidebar" onClick={() => setNarrow(!narrow)}><PanelLeftClose size={17}/></button>
        </div>
        {!narrow && <div className="side-content">
          <div className="section-title"><span>WORKSPACE</span><span className="item-count">{files.length}</span></div>
          <div className="file-tree">
            <div className="folder"><FolderClosed size={15}/> Current task</div>
            {files.map((file) => <button key={file.name} className="file-item" onClick={() => openFile(file)}>
              <FileJson2 size={15}/><span>{file.name}</span><ChevronRight size={14} className="f-chevron"/>
            </button>)}
            {!files.length && <div className="muted-note">Submit a task to generate an input artifact.</div>}
          </div>
          <div className="repo-info">
            <div className="section-title">REPOSITORY SUMMARY</div>
            <div className="info-line"><span>Source</span><strong>OneShot</strong></div>
            <div className="info-line"><span>Stage</span><strong>{task?.current_stage || 'Idle'}</strong></div>
            <div className="info-line"><span>Artifacts</span><strong>{files.length}</strong></div>
            <div className="info-line"><span>Events</span><strong>{events.length}</strong></div>
          </div>
        </div>}
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div className="crumb">Workspace <ChevronRight size={15}/> <strong>{task ? 'Task ' + task.task_id.slice(0, 8) : 'New task'}</strong></div>
          <div className="header-actions">
            <div className="status-dot"><span/> Host available</div>
            <button className="icon-button" title="Refresh task" onClick={() => task && fetchDetails(task.task_id).catch((e) => setError(e.message))}><RefreshCw size={17}/></button>
            <button className="icon-button" title="Settings" onClick={() => setError('Settings are managed by the host configuration.') }><Settings2 size={17}/></button>
          </div>
        </header>
        <div className="conversation">
          <div className="content-shell">
            {!task && <div className="empty-state">
              <div className="hero-shape"><div className="hero-inner">O</div></div>
              <p className="eyebrow">ONE WORKSPACE. ONE WORKFLOW.</p>
              <h1>What will you build today?</h1>
              <p className="subtitle">Describe a task to create a persistent OneShot workflow record. Agent execution is available after MCP integration.</p>
            </div>}
            {task && <>
              <div className="task-heading"><span className="eyebrow">TASK SESSION</span><h1>Workflow activity</h1><p className="subtitle">Host-owned task state and recorded events, streamed as they occur.</p></div>
              <div className="user-message"><div className="message-label">REQUEST</div><p>{task.input_text}</p></div>
              <div className="timeline-heading"><span>LIVE ACTIVITY</span><span>{events.length} EVENTS</span></div>
              <div className="timeline">
                {events.map((event) => <div key={event.sequence} className="activity">
                  <div className="activity-indicator"><Check size={13}/></div>
                  <div><div className="activity-title">{event.type.replaceAll('_', ' ')}</div><div className="activity-description">{event.message}</div><div className="activity-time">{event.created_at}</div></div>
                </div>)}
                <div ref={bottom}/>
              </div>
              <div className="integration-warning"><CircleAlert size={17}/><div><strong>MCP integration pending</strong><p>The task and input are persisted. Research, Audit, Planning, and Build have not been executed.</p></div></div>
            </>}
          </div>
        </div>
        <div className="composer-wrap">
          {error && <div role="alert" className="error"><CircleAlert size={15}/>{error}<button aria-label="Dismiss" onClick={() => setError('')}><X size={14}/></button></div>}
          <form className="composer" onSubmit={submit}>
            <textarea aria-label="Task description" placeholder="Describe what you want OneShot to work on..." rows={2} value={prompt} onChange={(e) => setPrompt(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); e.currentTarget.form.requestSubmit() } }} />
            <div className="composer-bottom"><span>Enter to submit · Shift+Enter for a new line</span><button className="send" disabled={!prompt.trim() || loading} aria-label="Submit task">{loading ? <LoaderCircle size={17} className="spin"/> : <ArrowUp size={18}/>}</button></div>
          </form>
          <div className="footnote">MVP · Persistent host state · No simulated agent results</div>
        </div>
      </main>

      {activeFile && <div className="modal-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) setActiveFile(null) }}>
        <div className="review-modal" role="dialog" aria-modal="true" aria-label="Review input artifact">
          <header><span><FileCode2 size={18}/> {activeFile.name} <small>rev {task?.input_revision}</small></span><button className="icon-button" aria-label="Close" onClick={() => setActiveFile(null)}><X size={18}/></button></header>
          <div className="modal-meta">Immutable input artifact · revisioned editing with conflict protection</div>
          <label htmlFor="file-editor">Task description</label>
          <textarea id="file-editor" spellCheck="false" value={editText} onChange={(e) => setEditText(e.target.value)}/>
          <footer><span>Original content preserved as earlier artifact revisions</span><button className="secondary" onClick={() => setActiveFile(null)}>Cancel</button><button className="primary" disabled={loading || !editText.trim()} onClick={saveInput}>{loading ? 'Saving...' : 'Save revision'}</button></footer>
        </div>
      </div>}
    </div>
  )
}
createRoot(document.getElementById('root')).render(<App/>)
