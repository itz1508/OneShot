/* OneShot video capture demo. Completely synthetic; never calls /api or external MCP. */
(() => {
  'use strict'
  const stageNames = ['Input', 'Research', 'Audit Discovery', 'Planning', 'Scanner', 'Fixture Validation', 'Build Admission', 'Build', 'Verification']
  const event = (stage, actor, title, detail, status = 'running', artifact = null, todo = null) => ({ stage, actor, title, detail, status, artifact, todo: todo || title })
  const e = event
  const scenarios = [
    {
      id: 'happy', label: '01 · Complete workflow', title: 'Feature delivery — validated build',
      intent: 'Add a read-only project summary dashboard, verify the design, implement only admitted changes, and run end-to-end checks.',
      description: 'A fully successful multi-stage workflow, with separate Planner and host receipts.',
      scenes: [
        e('Input', 'Host', 'Intent accepted', 'Created a synthetic task, run binding, and input revision.', 'done', '_input.json'),
        e('Research', 'Researcher', 'Evidence search started', 'Reviewing repository requirements and authoritative package documentation.'),
        e('Research', 'Researcher', 'Research findings recorded', 'Source provenance, limitations, and acceptance criteria captured.', 'done', '_research.json'),
        e('Audit Discovery', 'Audit Agent', 'Repository inventory', 'Inspecting routes, service boundaries, UI components, and tests.'),
        e('Audit Discovery', 'Audit Agent', 'CodeIntent handoff', 'Mapped existing functionality and required touchpoints without selecting implementation.', 'done', '_audit_discovery.json'),
        e('Planning', 'Planner', 'Compiling build specification', 'Identifying authorized files, dependencies, constraints, and verification checks.'),
        e('Planning', 'Planner', 'Plan candidate submitted', 'Candidate specification references exact input and research revisions.', 'done', '_planning.json'),
        e('Scanner', 'Scanner', 'Structural gap scan', 'Checking paths, reference closure, tool identity, and side-effect boundaries.', 'done', '_gap_analysis.json'),
        e('Fixture Validation', 'Fixture Validator', 'Fixture checks running', 'Validating expected contracts and independent test fixtures.'),
        e('Fixture Validation', 'Fixture Validator', 'Fixture readiness issued', 'All synthetic fixture checks satisfied.', 'done', '_fixture_validation.json'),
        e('Build Admission', 'Host', 'Freezing accepted plan', 'Binding exact revisions, tool registry, authorized paths, and expected outputs.'),
        e('Build Admission', 'Host', 'Build admitted', 'Host authorization receipt issued for the frozen plan.', 'done', '_build_admission.json'),
        e('Build', 'Builder', 'Sandbox provisioned', 'Isolated execution environment prepared from pinned inputs.'),
        e('Build', 'Builder', 'Implementing admitted changes', 'Writing scoped UI modules and running unit tests.'),
        e('Build', 'Builder', 'Build receipt persisted', 'Changed files, commands, outputs, and effects recorded.', 'done', '_build.json'),
        e('Verification', 'Build Verifier', 'Browser verification', 'Checking navigable UI, task status, and artifact inspection.'),
        e('Verification', 'Build Verifier', 'End-to-end checks passed', 'Independent final verification receipt issued.', 'done', '_build_validation.json'),
      ],
    },
    {
      id: 'gap', label: '02 · Gap and correction', title: 'Scanner finds a planning gap',
      intent: 'Implement a project search feature while preserving existing authorization and dependency contracts.',
      description: 'The scanner rejects the candidate; the Planner revises it before admission.',
      scenes: [
        e('Input', 'Host', 'Request persisted', 'Initial request and task identifiers captured.', 'done', '_input.json'),
        e('Research', 'Researcher', 'Requirements located', 'Public API usage and repository search behavior documented.', 'done', '_research.json'),
        e('Audit Discovery', 'Audit Agent', 'Existing search adapters mapped', 'Located read-only entry points and their test fixtures.', 'done', '_audit_discovery.json'),
        e('Planning', 'Planner', 'Candidate plan submitted', 'First revision omits an explicit tool authorization constraint.', 'done', '_planning_r1.json'),
        e('Scanner', 'Scanner', 'Gap detected', 'ToolRegistrySnapshot binding is missing; admission blocked.', 'blocked', '_gap_analysis_r1.json'),
        e('Planning', 'Planner', 'Plan revision started', 'Adding exact tool registry and prohibit-action constraints.'),
        e('Planning', 'Planner', 'Revised plan submitted', 'Revision 2 incorporates all scanner findings.', 'done', '_planning_r2.json'),
        e('Scanner', 'Scanner', 'Gap scan passed', 'No unresolved structural blockers for revision 2.', 'done', '_gap_analysis_r2.json'),
        e('Fixture Validation', 'Fixture Validator', 'Fixture validation passed', 'Independent synthetic fixtures match revision 2.', 'done', '_fixture_validation.json'),
        e('Build Admission', 'Host', 'Revision 2 admitted', 'Frozen bytes and receipts bound to the synthetic run.', 'done', '_build_admission.json'),
        e('Build', 'Builder', 'Applying admitted changes', 'Executing only revision 2 authorized actions.', 'done', '_build.json'),
        e('Verification', 'Build Verifier', 'E2E passed after correction', 'All requested checks reported complete.', 'done', '_build_validation.json'),
      ],
    },
    {
      id: 'blocked', label: '03 · Unsupported claim', title: 'Unverified evidence blocks the build',
      intent: 'Build a provider integration using a claimed API endpoint with no verified reference.',
      description: 'Unsupported evidence remains unresolved; no fake build authorization is issued.',
      scenes: [
        e('Input', 'Host', 'Input received', 'Saved the synthetic integration request.', 'done', '_input.json'),
        e('Research', 'Researcher', 'Checking provider documentation', 'Searching for an official API contract.'),
        e('Research', 'Researcher', 'Claim unsupported', 'Endpoint and authentication scheme cannot be verified.', 'blocked', '_research.json'),
        e('Audit Discovery', 'Audit Agent', 'Local adapter inspected', 'Found a compatible integration boundary but no authority for the claimed endpoint.', 'done', '_audit_discovery.json'),
        e('Planning', 'Planner', 'VALIDATE_FIRST selected', 'Plan explicitly prohibits implementation dependent on the unsupported claim.', 'blocked', '_planning.json'),
        e('Scanner', 'Scanner', 'Unresolved blocker preserved', 'No host Build Admission receipt can be issued.', 'blocked', '_gap_analysis.json'),
        e('Verification', 'Host', 'Awaiting verified information', 'Run intentionally stops without a Build or completion receipt.', 'blocked'),
      ],
    },
    {
      id: 'recovery', label: '04 · Interrupted build recovery', title: 'Checkpoint, reconcile, resume',
      intent: 'Upgrade a workflow adapter, preserving state across a simulated sandbox interruption.',
      description: 'Shows interrupted execution and safe checkpoint reconciliation before retry.',
      scenes: [
        e('Input', 'Host', 'Task bound', 'Synthetic immutable input snapshot stored.', 'done', '_input.json'),
        e('Research', 'Researcher', 'Relevant API references verified', 'Source hashes and limitations recorded.', 'done', '_research.json'),
        e('Audit Discovery', 'Audit Agent', 'Implementation paths discovered', 'Mapped adapter, tests, and existing checkpoint logic.', 'done', '_audit_discovery.json'),
        e('Planning', 'Planner', 'Build plan created', 'Specifies effect boundaries and interruption recovery.', 'done', '_planning.json'),
        e('Scanner', 'Scanner', 'No structural gaps', 'Authorized tool checks complete.', 'done'),
        e('Fixture Validation', 'Fixture Validator', 'Recovery fixtures passed', 'Interruption and idempotency examples validated.', 'done'),
        e('Build Admission', 'Host', 'Build admission accepted', 'Frozen task and sandbox profile authorized.', 'done', '_build_admission.json'),
        e('Build', 'Builder', 'Executing first attempt', 'Adapter changes are being applied in the isolated environment.'),
        e('Build', 'Sandbox', 'Execution interrupted', 'Process terminated after the pre-effect checkpoint was persisted.', 'blocked', '_checkpoint.json'),
        e('Build', 'Host', 'Reconciling checkpoint', 'Checking which effects occurred before interruption.'),
        e('Build', 'Host', 'Retry classified safe', 'No duplicate side effects; resume authorized.', 'done', '_recovery.json'),
        e('Build', 'Builder', 'Resuming from checkpoint', 'Remaining admitted actions complete.', 'done', '_build.json'),
        e('Verification', 'Build Verifier', 'Recovery E2E passed', 'Restored state and effect ledger agree.', 'done', '_build_validation.json'),
      ],
    },
    {
      id: 'mcp', label: '05 · MCP and API configuration', title: 'Connector settings and discovery',
      intent: 'Configure a public MCP endpoint and a browser API URL, discover tools, and show their responses.',
      description: 'Visual connection simulation only; no server URL, secret, or tool is contacted.',
      scenes: [
        e('Input', 'Host', 'Connection request shown', 'Synthetic request for frontend connection configuration.', 'done', '_input.json'),
        e('Research', 'Researcher', 'Transport requirements checked', 'Reviewing streamable HTTP and discovery semantics.', 'done', '_research.json'),
        e('Audit Discovery', 'Audit Agent', 'Settings UI inspected', 'Identified API base URL and MCP URL fields.', 'done', '_audit_discovery.json'),
        e('Planning', 'Planner', 'Connection flow planned', 'Defines local URL validation and isolated demo behavior.', 'done', '_planning.json'),
        e('Scanner', 'Scanner', 'Configuration boundary checked', 'No secrets or private credentials in demonstration output.', 'done'),
        e('Fixture Validation', 'Fixture Validator', 'Connector fixture ready', 'Synthetic tools/list response accepted.', 'done'),
        e('Build Admission', 'Host', 'Demo fixture admitted', 'Simulated only; no host effect granted.', 'done'),
        e('Build', 'Demo connector', 'Checking API endpoint', 'Example API URL: https://api.example.test', 'running'),
        e('Build', 'Demo connector', 'MCP handshake', 'Example MCP URL: https://mcp.example.test/mcp', 'running'),
        e('Build', 'Demo connector', 'Tools discovered', 'Available examples: project_search, file_summary, status_check.', 'done', '_tools_list.json'),
        e('Verification', 'Build Verifier', 'Demo response displayed', 'Simulated tool response and artifact preview generated.', 'done', '_build_validation.json'),
      ],
    },
    {
      id: 'audit', label: '06 · Repository audit', title: 'Audit findings and validation',
      intent: 'Inspect a repository for contract drift, duplicate owners, missing tests, and security gaps.',
      description: 'Displays a read-only audit with multiple discovery actions and an evidence artifact.',
      scenes: [
        e('Input', 'Host', 'Audit request created', 'Synthetic audit capability selected.', 'done', '_input.json'),
        e('Research', 'Researcher', 'Audit rules collected', 'Validation criteria and project boundaries identified.', 'done', '_research.json'),
        e('Audit Discovery', 'Audit Agent', 'Source tree traversal', 'Enumerating modules, configs, tests, and adapters.'),
        e('Audit Discovery', 'Audit Agent', 'Dependency trace', 'Following import graph and production entry points.'),
        e('Audit Discovery', 'Audit Agent', 'Contract ownership scan', 'Checking overlapping responsibility and duplicate schemas.'),
        e('Audit Discovery', 'Audit Agent', 'Security and path review', 'Looking for unchecked effects and improper credential handling.'),
        e('Audit Discovery', 'Audit Agent', 'Findings captured', 'One stale reference and two missing regression assertions identified.', 'done', '_audit_discovery.json'),
        e('Planning', 'Planner', 'Read-only remediation plan drafted', 'Corrective actions proposed, not applied.', 'done', '_planning.json'),
        e('Scanner', 'Scanner', 'Gap report complete', 'Findings classified by severity and evidence quality.', 'done', '_gap_analysis.json'),
        e('Verification', 'Host', 'Audit review ready', 'Results shown without pretending source code was modified.', 'done', '_audit.json'),
      ],
    },
  ]

  const $ = (id) => document.getElementById(id)
  const scenarioSelect = $('scenario')
  const params = new URLSearchParams(location.search)
  const originalId = params.get('scenario')
  scenarios.forEach((scenario) => scenarioSelect.add(new Option(scenario.label, scenario.id)))
  scenarioSelect.add(new Option('07 · All scenarios (playlist)', 'all'))
  scenarioSelect.value = scenarios.some((s) => s.id === originalId) || originalId === 'all' ? originalId : 'happy'
  if (['0.5', '1', '2', '4'].includes(params.get('speed'))) $('speed').value = params.get('speed')
  let sceneIndex = -1
  let timer = null
  let playing = false
  let actionNumber = 0
  let currentScenarioId = ''
  let events = []
  let actionLog = []
  let artifacts = new Map()
  let startMs = performance.now()
  let currentTodo = ''
  const stageColors = { blocked: 'blocked', done: 'done', running: 'active' }
  const playlist = () => scenarioSelect.value === 'all' ? scenarios.flatMap((s) => s.scenes.map((step) => ({ ...step, scenarioId: s.id }))) : scenarios.find((s) => s.id === scenarioSelect.value).scenes.map((step) => ({ ...step, scenarioId: scenarioSelect.value }))
  const scenarioById = (id) => scenarios.find((s) => s.id === id)
  const record = (action, payload = {}) => {
    const row = { sequence: ++actionNumber, type: action, scenario_id: currentScenarioId || scenarioSelect.value, scene_index: sceneIndex, elapsed_ms: Math.round(performance.now() - startMs), synthetic: true, ...payload }
    actionLog.push(row)
    return row
  }
  const putText = (node, text) => { node.textContent = String(text) }
  const clear = (node) => { node.replaceChildren() }
  const el = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node }
  const createSample = (name, step, scenarioId) => ({
    _demo: true, synthetic: true, file: name,
    scenario: scenarioId,
    stage: step.stage,
    actor: step.actor,
    status: step.status,
    action: step.title,
    detail: step.detail,
    source: 'oneshot-video-demo/1.0',
    binding: { task_id: 'demo-' + scenarioId, run_id: 'demo-run-' + scenarioId, revision: sceneIndex + 1 },
    verification: 'SIMULATED — NOT AN ACTUAL RECEIPT',
  })
  const stageList = () => {
    const current = scenarioById(currentScenarioId || (scenarioSelect.value === 'all' ? scenarios[0].id : scenarioSelect.value))
    const present = [...new Set(current.scenes.map((step) => step.stage))]
    return stageNames.filter((s) => present.includes(s))
  }
  function renderStages() {
    const node = $('stages'); clear(node)
    const current = scenarioById(currentScenarioId || (scenarioSelect.value === 'all' ? scenarios[0].id : scenarioSelect.value))
    const relevant = events.filter((entry) => entry.scenarioId === current.id)
    const knownStages = stageList()
    knownStages.forEach((stage) => {
      const matching = relevant.filter((entry) => entry.stage === stage)
      const last = matching.at(-1)
      const currentEvent = relevant.at(-1)
      const status = !last ? 'queued' : last === currentEvent ? last.status : last.status === 'blocked' ? 'blocked' : 'done'
      const row = el('div', 'stage-row ' + (stageColors[status] || ''))
      row.dataset.stage = stage
      row.append(el('span', 'stage-icon', status === 'blocked' ? '!' : status === 'done' ? '✓' : status === 'running' ? '●' : '·'), el('span', 'stage-label', stage), el('small', status))
      node.append(row)
    })
    putText($('stageCount'), `${knownStages.length} stages`)
  }
  function renderTodos() {
    const node = $('todos'); clear(node)
    const relevant = events.filter((entry) => entry.scenarioId === currentScenarioId).slice(-4)
    if (!relevant.length) node.append(el('div', 'empty-note', 'TODO entries appear when a scene advances.'))
    relevant.forEach((item, i) => {
      const row = el('div', 'todo-row ' + (i === relevant.length - 1 ? stageColors[item.status] || 'active' : 'done'))
      row.append(el('span', 'stage-icon', item.status === 'blocked' ? '!' : i === relevant.length - 1 && item.status === 'running' ? '●' : '✓'), el('span', '', item.todo))
      node.append(row)
    })
    putText($('todoCount'), `${events.filter((entry) => entry.scenarioId === currentScenarioId).length} tasks`)
  }
  function renderFiles() {
    const node = $('files'); clear(node)
    const list = [...artifacts.entries()].reverse().slice(0, 5)
    if (!list.length) node.append(el('div', 'empty-note', 'Synthetic artifact snapshots appear after steps run.'))
    list.forEach(([name]) => {
      const button = el('button', 'artifact-row'); button.type = 'button'; button.setAttribute('aria-label', `Open ${name}`)
      button.append(el('span', '', '▧'))
      const body = el('span');body.append(el('strong', '', name), el('small', '', 'Read-only · simulated sample'))
      button.append(body, el('span', '', '›'));button.addEventListener('click', () => openArtifact(name))
      node.append(button)
    })
    putText($('artifactTotal'), `${artifacts.size} files`)
    putText($('artifactCount'), `${artifacts.size} artifacts`)
  }
  function renderEvidence() {
    const node = $('evidence'); clear(node)
    events.slice(-6).reverse().forEach((item) => {
      const row = el('div', 'event-row');row.append(el('small', '', '#' + item.sequence))
      const body = el('div');body.append(el('strong', '', item.title), el('p', '', item.detail));row.append(body);node.append(row)
    })
    if (!events.length) node.append(el('div', 'empty-note', 'Synthetic stage events appear here.'))
    putText($('evidenceCount'), `${events.length} events`)
    putText($('eventCount'), `${events.length} events`)
  }
  function addMessage(step) {
    const row = el('article', 'message left ' + (step.status === 'blocked' ? 'warn' : 'host'))
    const actor = step.actor === 'Host' ? 'H' : step.actor.charAt(0)
    row.append(el('div', 'avatar', actor))
    const body = el('div', 'bubble-wrap')
    const meta = el('div', 'bubble-meta');meta.append(el('strong', '', step.actor), el('span', '', step.stage), el('small', '', `${currentScenarioId} · #${sceneIndex + 1}`))
    const bubble = el('div', 'bubble');bubble.append(el('strong', '', step.title), el('p', '', step.detail))
    body.append(meta, bubble);row.append(body)
    $('transcript').append(row)
    $('transcript').scrollTop = $('transcript').scrollHeight
  }
  function addRequest(scenario) {
    const row = el('article', 'message right')
    row.append(el('div', 'avatar', 'Y'))
    const body = el('div', 'bubble-wrap')
    const meta = el('div', 'bubble-meta');meta.append(el('strong', '', 'Sample request'), el('span', '', scenario.label))
    body.append(meta, el('div', 'bubble', scenario.intent));row.append(body)
    $('transcript').append(row)
  }
  function updateSummary(step) {
    const scenario = scenarioById(currentScenarioId)
    putText($('taskTitle'), scenario.title)
    putText($('taskDescription'), scenario.description)
    putText($('intent'), scenario.intent)
    putText($('headline'), step ? step.title : 'One workflow, visualized')
    putText($('currentStage'), step?.stage || 'Idle')
    putText($('execution'), step ? `${step.status === 'blocked' ? 'blocked' : step.status === 'done' ? 'completed' : 'processing'} (demo)` : 'idle (demo)')
    putText($('worker'), step?.actor || 'Unassigned')
    putText($('captureNote'), step?.status === 'blocked' ? 'This red state is simulated. No actual task was blocked.' : 'Every event, action, and artifact is synthetic and can be exported for storyboarding.')
  }
  function renderProgress() {
    const count = playlist().length
    const percentage = count ? Math.round(((sceneIndex + 1) / count) * 100) : 0
    $('progress').style.width = percentage + '%'
    putText($('percent'), `${percentage}%`)
    putText($('scenarioCounter'), `Scene ${sceneIndex + 1} / ${count}`)
    putText($('play'), playing ? 'Pause' : sceneIndex + 1 >= count ? 'Replay' : 'Play')
    $('next').disabled = sceneIndex + 1 >= count
  }
  function stop() { if (timer !== null) clearTimeout(timer); timer = null; playing = false; renderProgress() }
  function reset() {
    stop(); sceneIndex = -1; actionNumber = 0; startMs = performance.now();currentScenarioId = '';events = [];artifacts = new Map();actionLog = [];currentTodo = ''
    clear($('transcript'))
    const greeting = el('article', 'message left host');greeting.append(el('div', 'avatar', 'O'))
    const body = el('div', 'bubble-wrap');body.append(el('div', 'bubble-meta', 'OneShot · simulated workflow'), el('div', 'bubble', 'Choose a scenario and press Play. No backend actions are performed.'))
    greeting.append(body);$('transcript').append(greeting)
    currentScenarioId = scenarioSelect.value === 'all' ? scenarios[0].id : scenarioSelect.value
    updateSummary(null);renderStages();renderTodos();renderFiles();renderEvidence();renderProgress()
    record('reset', { total_scenes: playlist().length })
  }
  function advance() {
    const scenes = playlist()
    if (sceneIndex + 1 >= scenes.length) { stop(); return false }
    sceneIndex += 1
    const step = scenes[sceneIndex]
    if (currentScenarioId !== step.scenarioId || !events.length) {
      currentScenarioId = step.scenarioId
      if (events.length) { $('transcript').append(el('div', 'eyebrow', 'NEW DEMONSTRATION SCENARIO')) }
      addRequest(scenarioById(currentScenarioId))
      record('scenario_started', { title: scenarioById(currentScenarioId).title })
    }
    const line = { ...step, sequence: events.length + 1, scene_index: sceneIndex }
    events.push(line)
    currentTodo = step.todo
    if (step.artifact) artifacts.set(step.artifact, createSample(step.artifact, step, currentScenarioId))
    addMessage(step);updateSummary(step);renderStages();renderTodos();renderFiles();renderEvidence();renderProgress()
    record('scene_entered', { stage: step.stage, actor: step.actor, status: step.status, title: step.title, artifact: step.artifact || null })
    document.dispatchEvent(new CustomEvent('oneshot-demo-scene', { detail: { scene_index: sceneIndex, scenario_id: currentScenarioId, stage: step.stage } }))
    if (sceneIndex + 1 >= scenes.length) { playing = false;renderProgress();record('playlist_finished') }
    return true
  }
  function schedule() {
    if (!playing) return
    timer = setTimeout(() => { timer = null; if (!advance()) { stop();return } schedule() }, Math.max(110, 1000 / Number($('speed').value)))
  }
  function play() {
    if (playing) { stop(); record('paused');return }
    if (sceneIndex + 1 >= playlist().length) reset()
    playing = true;record('played');advance();renderProgress();schedule()
  }
  function exportLog() {
    record('exported_actions', { count: actionLog.length })
    const output = [JSON.stringify({ kind: 'manifest', synthetic: true, source: 'OneShot demo', scenarios: scenarioSelect.value, scene_count: playlist().length, version: 1 }), ...actionLog.map((row) => JSON.stringify(row))].join('\n') + '\n'
    const blob = new Blob([output], { type: 'application/x-ndjson' })
    const url = URL.createObjectURL(blob);const anchor = document.createElement('a');anchor.href = url;anchor.download = `oneshot-demo-actions-${scenarioSelect.value}.jsonl`;anchor.click();setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  function openArtifact(name) {
    if (!artifacts.has(name)) return
    putText($('modalTitle'), name);putText($('fileEditor'), JSON.stringify(artifacts.get(name), null, 2));$('modal').hidden = false
    record('artifact_opened', { artifact: name })
  }
  function closeArtifact() { $('modal').hidden = true;record('artifact_closed') }
  scenarioSelect.addEventListener('change', () => { const p = new URLSearchParams(location.search);p.set('scenario', scenarioSelect.value);p.delete('autoplay');history.replaceState(null, '', '?' + p);reset() })
  $('speed').addEventListener('change', () => { record('speed_changed', { speed: $('speed').value });if (playing) { if (timer !== null) clearTimeout(timer); schedule() } })
  $('play').addEventListener('click', play)
  $('next').addEventListener('click', () => { if (playing) stop();advance() })
  $('restart').addEventListener('click', reset)
  $('export').addEventListener('click', exportLog)
  $('modalClose').addEventListener('click', closeArtifact)
  $('modalDone').addEventListener('click', closeArtifact)
  $('modal').addEventListener('click', (evt) => { if (evt.target === $('modal')) closeArtifact() })
  document.addEventListener('keydown', (evt) => { if (evt.key === 'Escape' && !$('modal').hidden) closeArtifact(); else if (evt.code === 'Space' && evt.target === document.body) { evt.preventDefault();play() } })
  window.__oneshotDemo = Object.freeze({
    scenarios: scenarios.map((s) => ({ id: s.id, title: s.title, scenes: s.scenes.length })),
    next: advance, reset, play, pause: stop,
    getState: () => ({ sceneIndex, currentScenarioId, playing, events: events.map((x) => ({ ...x })), actionLog: actionLog.map((x) => ({ ...x })), artifacts: Object.fromEntries(artifacts), synthetic: true }),
  })
  reset()
  if (params.get('step') !== null) {
    const index = Math.max(-1, Math.min(playlist().length - 1, Number(params.get('step')) || 0))
    for (let i = 0; i <= index; i++) advance()
  }
  if (params.get('autoplay') === '1') play()
})()