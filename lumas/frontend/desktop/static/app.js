/* ═══════════════════════════════════════════════════════════
   Lumas Desktop — Main Application
   ═══════════════════════════════════════════════════════════ */

const API = '/api'
let sid = null       // current session ID
let docId = null     // active document ID
let docName = ''     // active document name
let activeChunkId = null // chunk used for quiz generation
let settingsTimer = null

// ── Init ─────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadSessions()
  loadDocuments()
  loadSettings()
  setupNetworkMonitor()
  setupDragDrop()
  setupChatInput()
  setupCopyButtons()
  setupQuizInteractions()
})

// ── Toast Notifications ──────────────────────────────────

function toast(msg, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container')
  const el = document.createElement('div')
  el.className = `toast ${type}`
  const icon = type === 'error' ? '✕' : type === 'success' ? '✓' : 'ℹ'
  el.innerHTML = `<span class="toast-icon">${icon}</span><span>${esc(msg)}</span>`
  container.appendChild(el)
  setTimeout(() => {
    el.classList.add('removing')
    setTimeout(() => el.remove(), 200)
  }, duration)
}

// ── API Helper ───────────────────────────────────────────

async function api(method, path, body) {
  const opts = {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined
  }
  const res = await fetch(API + path, opts)
  if (!res.ok) {
    let msg
    try { const e = await res.json(); msg = e.detail || e.message || res.statusText }
    catch { msg = await res.text().catch(() => res.statusText) }
    throw new Error(msg)
  }
  return res.json()
}

// ── Loading ──────────────────────────────────────────────

function loading(on, text) {
  document.getElementById('loading').hidden = !on
  document.getElementById('loading-text').textContent = text || 'Processing...'
}

function setStatus(text, ok = true) {
  document.getElementById('status-text').textContent = text
  const dot = document.getElementById('status-dot')
  dot.className = 'status-dot'
  if (!ok) dot.classList.add('error')
}

// ── Network Monitor ──────────────────────────────────────

function setupNetworkMonitor() {
  const statusBar = document.getElementById('network-status')
  function update() {
    if (!navigator.onLine) {
      statusBar.classList.add('offline')
    } else {
      statusBar.classList.remove('offline')
    }
  }
  window.addEventListener('online', update)
  window.addEventListener('offline', update)
  update()
}

// ── Escaping ─────────────────────────────────────────────

function esc(s) {
  const d = document.createElement('div')
  d.textContent = s
  return d.innerHTML
}

// ── View Switching ───────────────────────────────────────

function switchView(view) {
  document.querySelectorAll('.view').forEach(el => el.classList.remove('active'))
  document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'))
  document.getElementById('view-' + view)?.classList.add('active')
  document.querySelector(`.nav-btn[data-view="${view}"]`)?.classList.add('active')
  if (view === 'quizzes') loadQuizResults()
  if (view === 'documents') loadDocuments()
}

// ── Sessions ─────────────────────────────────────────────

async function loadSessions() {
  try {
    const sessions = await api('GET', '/sessions')
    const sel = document.getElementById('session-select')
    sel.innerHTML = '<option value="">+ New session</option>'
    sessions.forEach(s => {
      const opt = document.createElement('option')
      opt.value = s.id
      const d = new Date(s.created_at * 1000)
      opt.textContent = `Session ${s.id.slice(0, 6)}… ${d.toLocaleDateString()}`
      sel.appendChild(opt)
    })
  } catch (e) {
    // Server might not be ready yet, that's OK
  }
}

async function newSession() {
  try {
    setStatus('Creating session…')
    const s = await api('POST', '/sessions', {})
    sid = s.id
    document.getElementById('session-select').value = ''
    document.getElementById('messages').innerHTML =
      '<div class="welcome"><div class="welcome-icon">💬</div><h3>New Session</h3><p>Ask a question to get started.</p></div>'
    loadSessions()
    document.getElementById('engine-badge').textContent = s.engine_used
    document.getElementById('btn-delete-session').hidden = false
    setStatus('Ready')
    toast('New session created', 'success', 2000)
  } catch (e) {
    toast('Failed to create session: ' + e.message, 'error')
    setStatus('Error', false)
  }
}

async function switchSession(id) {
  if (!id) {
    sid = null
    document.getElementById('messages').innerHTML =
      '<div class="welcome"><div class="welcome-icon">📚</div><h3>Welcome to Lumas</h3><p>Upload a PDF and start asking questions.</p></div>'
    document.getElementById('btn-delete-session').hidden = true
    return
  }
  sid = id
  document.getElementById('btn-delete-session').hidden = false
  try {
    setStatus('Loading session…')
    const [msgs, s] = await Promise.all([
      api('GET', '/sessions/' + sid + '/messages'),
      api('GET', '/sessions/' + sid)
    ])
    renderMessages(msgs)
    document.getElementById('engine-badge').textContent = s.engine_used
    setStatus('Ready')
  } catch (e) {
    toast('Failed to load session: ' + e.message, 'error')
    setStatus('Error', false)
  }
}

// ── Confirm Dialog ───────────────────────────────────────-

let _confirmCallback = null

function confirm(title, message, onYes, yesLabel) {
  document.getElementById('confirm-title').textContent = title
  document.getElementById('confirm-message').textContent = message
  document.getElementById('confirm-yes').textContent = yesLabel || 'Delete'
  document.getElementById('confirm-modal').hidden = false
  _confirmCallback = onYes
}

function closeConfirm() {
  document.getElementById('confirm-modal').hidden = true
  _confirmCallback = null
}

function confirmAction() {
  document.getElementById('confirm-modal').hidden = true
  if (_confirmCallback) _confirmCallback()
  _confirmCallback = null
}

// Close modal on overlay click
document.getElementById('confirm-modal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeConfirm()
})

async function deleteSession() {
  if (!sid) return
  confirm(
    'Delete Session',
    'This will permanently delete this session and all its messages and quizzes.',
    async () => {
      try {
        await api('DELETE', '/sessions/' + sid)
        sid = null
        document.getElementById('messages').innerHTML =
          '<div class="welcome"><div class="welcome-icon">📚</div><h3>Session deleted</h3><p>Start a new session to begin.</p></div>'
        document.getElementById('btn-delete-session').hidden = true
        loadSessions()
        toast('Session deleted', 'info', 2000)
      } catch (e) {
        toast('Failed to delete session: ' + e.message, 'error')
      }
    },
    'Delete'
  )
}

// ── Chat ─────────────────────────────────────────────────

function setupChatInput() {
  document.getElementById('chat-input').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  })
}

function onChatInput(el) {
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 120) + 'px'
  document.getElementById('send-btn').disabled = !el.value.trim()
}

async function send() {
  const el = document.getElementById('chat-input')
  const query = el.value.trim()
  const sendBtn = document.getElementById('send-btn')
  if (!query || sendBtn.disabled) return

  // Disable input while generating
  sendBtn.disabled = true
  el.disabled = true

  if (!sid) {
    try {
      const s = await api('POST', '/sessions', {})
      sid = s.id
      document.getElementById('btn-delete-session').hidden = false
      loadSessions()
    } catch (e) {
      toast('Create a session first', 'error')
      sendBtn.disabled = false
      el.disabled = false
      el.focus()
      return
    }
  }

  appendMessage('user', query)
  el.value = ''
  onChatInput(el)

  // Show typing indicator
  showTypingIndicator()

  setStatus('Thinking…', true)
  try {
    const r = await api('POST', '/chat', {
      session_id: sid,
      query: query,
      document_id: docId || undefined
    })
    hideTypingIndicator()
    appendMessage('assistant', r.response)
    setStatus('Ready')
  } catch (e) {
    hideTypingIndicator()
    const msg = e.message
    let errMsg
    if (msg.includes('Failed to fetch') || msg.includes('NetworkError')) {
      errMsg = 'Connection lost — the request took too long. Please try again.'
    } else if (msg.includes('timeout') || msg.includes('timed out')) {
      errMsg = 'Request timed out. The model is generating — try a simpler question.'
    } else {
      errMsg = msg
    }
    appendMessage('assistant', '⚠️ ' + errMsg)
    setStatus('Error', false)
  } finally {
    sendBtn.disabled = false
    el.disabled = false
    el.focus()
  }
}

function showTypingIndicator() {
  const container = document.getElementById('messages')
  if (document.getElementById('typing-indicator')) return
  const typingEl = document.createElement('div')
  typingEl.className = 'typing-indicator'
  typingEl.id = 'typing-indicator'
  typingEl.innerHTML = '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>'
  container.appendChild(typingEl)
  container.scrollTop = container.scrollHeight
}

function hideTypingIndicator() {
  const el = document.getElementById('typing-indicator')
  if (el) el.remove()
}

function appendMessage(role, text) {
  const container = document.getElementById('messages')
  // Remove welcome if present
  const welcome = container.querySelector('.welcome')
  if (welcome) welcome.remove()

  const div = document.createElement('div')
  div.className = 'msg ' + role
  div.innerHTML = formatMessage(text) + '<div class="msg-timestamp">' + formatTimestamp(Date.now()) + '</div>'
  container.appendChild(div)
  container.scrollTop = container.scrollHeight
  return div
}

function formatMessage(text) {
  // Process code blocks BEFORE HTML escaping to avoid double-escape
  // Extract code blocks, replace with placeholders, escape text, then restore blocks
  const codeBlocks = []
  let h = text.replace(/```(\w*)\n([\s\S]*?)```/g, (match, lang, code) => {
    const idx = codeBlocks.length
    codeBlocks.push('<pre><code>' + esc(code) + '</code><button class="copy-btn" onclick="copyCode(this)">📋 Copy</button></pre>')
    return '%%CODEBLOCK_' + idx + '%%'
  })
  // Now escape the rest
  h = esc(h)
  // Restore code block placeholders (which are already safely escaped)
  h = h.replace(/%%CODEBLOCK_(\d+)%%/g, (match, idx) => codeBlocks[parseInt(idx)])
  // Inline code
  h = h.replace(/`([^`]+)`/g, '<code>$1</code>')
  // Bold
  h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  // Paragraphs
  h = h.replace(/\n\n/g, '</p><p>')
  h = h.replace(/\n/g, '<br>')
  return '<p>' + h + '</p>'
}

function formatTimestamp(ts) {
  const d = new Date(ts)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function copyCode(btn) {
  const code = btn.parentElement.querySelector('code')
  if (!code) return
  const text = code.textContent
  navigator.clipboard.writeText(text).then(() => {
    btn.textContent = '✓ Copied!'
    setTimeout(() => { btn.textContent = '📋 Copy' }, 2000)
  }).catch(() => {
    btn.textContent = 'Failed'
  })
}

function setupCopyButtons() {
  // Delegate copy button clicks for dynamically loaded messages
  document.getElementById('messages').addEventListener('click', e => {
    const btn = e.target.closest('.copy-btn')
    if (btn) copyCode(btn)
  })
}

function renderMessages(msgs) {
  const container = document.getElementById('messages')
  container.innerHTML = ''
  if (!msgs.length) {
    container.innerHTML =
      '<div class="welcome"><div class="welcome-icon">💬</div><h3>Session Started</h3><p>Ask a question to begin.</p></div>'
    return
  }
  msgs.forEach(m => appendMessage(m.role, m.content))
}

// ── Document Context ────────────────────────────────────

function setDoc(id, title, chunkId = null) {
  docId = id
  docName = title
  activeChunkId = chunkId
  const ind = document.getElementById('doc-indicator')
  ind.hidden = false
  document.getElementById('doc-name').textContent = title
}

function clearDoc() {
  docId = null
  docName = ''
  activeChunkId = null
  document.getElementById('doc-indicator').hidden = true
}

// ── Documents ───────────────────────────────────────────

function setupDragDrop() {
  const zone = document.getElementById('drop-zone')
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover') })
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'))
  zone.addEventListener('drop', e => {
    e.preventDefault()
    zone.classList.remove('dragover')
    const file = e.dataTransfer.files[0]
    if (file) uploadFile(file)
  })
}

async function uploadFile(file) {
  if (!file || !file.name.toLowerCase().endsWith('.pdf')) {
    toast('Please upload a PDF file.', 'error')
    return
  }

  loading(true, 'Uploading and processing…')
  const fd = new FormData()
  fd.append('file', file)

  try {
    const res = await fetch(API + '/documents/upload', { method: 'POST', body: fd })
    if (!res.ok) {
      const raw = await res.text().catch(() => res.statusText)
      let detail = raw
      try { detail = JSON.parse(raw).detail || raw } catch { /* plain-text error */ }
      throw new Error(detail)
    }
    const doc = await res.json()
    addDocumentCard(doc)
    setDoc(doc.id, doc.title, doc.chunks?.[0]?.id || null)
    toast(`"${doc.title}" uploaded (${doc.chunks.length} chunks)`, 'success', 3000)
    switchView('chat')
  } catch (e) {
    toast('Upload failed: ' + e.message, 'error')
  } finally {
    loading(false)
  }
}

async function loadDocuments() {
  try {
    const docs = await api('GET', '/documents')
    const list = document.getElementById('documents-list')
    list.innerHTML = ''
    docs.forEach(d => addDocumentCard(d))
  } catch (e) {
    // Server may not be ready
  }
}

function addDocumentCard(doc) {
  const list = document.getElementById('documents-list')
  // Remove empty state if present
  const empty = list.querySelector('.empty-state')
  if (empty) empty.remove()

  const card = document.createElement('div')
  card.className = 'doc-card'
  card.dataset.docId = doc.id
  card.dataset.docTitle = doc.title
  card.dataset.docChunkId = doc.chunks?.[0]?.id || ''
  card.innerHTML = `
    <div class="doc-card-info">
      <span class="doc-card-icon">📄</span>
      <div>
        <div class="doc-card-title">${esc(doc.title)}</div>
        <div class="doc-card-meta">${doc.chunks.length} chunks · ${esc(doc.source_filename)}</div>
      </div>
    </div>
    <div class="doc-card-actions">
      <button class="btn-use">Use</button>
      <button class="btn-danger btn-delete">Delete</button>
    </div>`
  list.appendChild(card)
}

// Event delegation for document card actions
// Uses data attributes instead of inline onclick to avoid XSS vectors
document.getElementById('documents-list').addEventListener('click', e => {
  const card = e.target.closest('.doc-card')
  if (!card) return
  const id = card.dataset.docId
  const title = card.dataset.docTitle
  const chunkId = card.dataset.docChunkId || null
  if (e.target.classList.contains('btn-use')) {
    useDoc(id, title, chunkId)
  } else if (e.target.classList.contains('btn-delete')) {
    deleteDoc(id)
  }
})

function useDoc(id, title, chunkId) {
  setDoc(id, title, chunkId)
  toast(`Using "${title}"`, 'info', 2000)
  switchView('chat')
}

async function deleteDoc(id) {
  confirm(
    'Delete Document',
    'This will permanently delete this document and all its chunks. This cannot be undone.',
    async () => {
      try {
        await api('DELETE', '/documents/' + id)
        loadDocuments()
        if (docId === id) clearDoc()
        toast('Document deleted', 'info', 2000)
      } catch (e) {
        toast('Delete failed: ' + e.message, 'error')
      }
    },
    'Delete'
  )
}

// ── Quizzes ─────────────────────────────────────────────

async function generateQuiz() {
  if (!docId) {
    toast('Select a document first (Documents view → Use)', 'warning')
    return
  }
  if (!activeChunkId) {
    toast('This document has no usable text chunk', 'warning')
    return
  }
  if (!sid) {
    try {
      const session = await api('POST', '/sessions', {})
      sid = session.id
      document.getElementById('btn-delete-session').hidden = false
      loadSessions()
    } catch (e) {
      toast('Create a session first: ' + e.message, 'error')
      return
    }
  }

  loading(true, 'Generating quiz…')
  const button = document.getElementById('btn-gen-quiz')
  button.disabled = true
  try {
    const r = await api('POST', '/quizzes/generate', {
      session_id: sid,
      chunk_id: activeChunkId,
      num_questions: 3
    })
    toast('Quiz generated! Check the Quizzes view.', 'success', 3000)
    switchView('quizzes')
  } catch (e) {
    toast('Failed to generate quiz: ' + e.message, 'error')
  } finally {
    loading(false)
    button.disabled = false
  }
}

function setupQuizInteractions() {
  document.getElementById('quiz-content').addEventListener('click', e => {
    const option = e.target.closest('.quiz-option[data-quiz-id]')
    if (option) answerQuizOption(option)
  })
  document.getElementById('quiz-content').addEventListener('keydown', e => {
    if (e.key !== 'Enter' && e.key !== ' ') return
    const option = e.target.closest('.quiz-option[data-quiz-id]')
    if (!option) return
    e.preventDefault()
    answerQuizOption(option)
  })
}

async function answerQuizOption(option) {
  if (option.dataset.answered === 'true') return
  option.dataset.answered = 'true'
  try {
    await api('POST', '/quizzes/answer', {
      quiz_id: option.dataset.quizId,
      question_index: Number(option.dataset.questionIndex),
      student_answer: option.dataset.optionIndex,
      // Kept for API compatibility; the server validates against stored quiz data.
      correct_index: 0
    })
    toast('Answer saved', 'success', 1500)
    await loadQuizResults()
  } catch (e) {
    delete option.dataset.answered
    toast('Could not save answer: ' + e.message, 'error')
  }
}

async function loadQuizResults() {
  if (!sid) {
    document.getElementById('quiz-content').innerHTML =
      '<div class="empty-state"><div class="empty-icon">💬</div><h3>No session active</h3><p>Start a chat session first, then generate quizzes from your document chunks.</p></div>'
    return
  }

  try {
    const results = await api('GET', `/sessions/${sid}/quiz-results`)
    const container = document.getElementById('quiz-content')

    if (!results.length) {
      container.innerHTML =
        '<div class="empty-state"><div class="empty-icon">📝</div><h3>No quizzes yet</h3><p>Ask Lumas to generate a quiz from your document in the chat.</p></div>'
      return
    }

    container.innerHTML = ''
    results.forEach((r, idx) => {
      const card = document.createElement('div')
      card.className = 'quiz-card'

      const date = new Date(r.created_at * 1000).toLocaleString()
      card.innerHTML = `
        <div class="quiz-header">
          <h4>Quiz ${idx + 1}</h4>
          <span class="quiz-score">${r.score} · ${date}</span>
        </div>
        ${r.questions.map((q, qi) => {
          const answer = r.answers.find(a => a.question_index === qi)
          return `<div class="quiz-question">
            <div class="q-text">${esc(q.question)}</div>
            ${q.options.map((opt, oi) => {
              let cls = 'quiz-option'
              let icon = ''
              if (answer) {
                if (oi === q.correct_index) { cls += ' correct'; icon = '✓ ' }
                else if (oi === parseInt(answer.student_answer) && !answer.is_correct) { cls += ' wrong'; icon = '✗ ' }
              }
              const answerAttrs = answer ? 'data-answered="true"' : `data-quiz-id="${esc(r.quiz_id)}" data-question-index="${qi}" data-option-index="${oi}" role="button" tabindex="0"`
              return `<div class="${cls}" ${answerAttrs}>${icon}${esc(opt)}</div>`
            }).join('')}
          </div>`
        }).join('')}`
      container.appendChild(card)
    })
  } catch (e) {
    document.getElementById('quiz-content').innerHTML =
      '<div class="empty-state"><div class="empty-icon">⚠️</div><h3>Could not load quizzes</h3><p>' + esc(e.message) + '</p></div>'
  }
}

// ── Settings ─────────────────────────────────────────────

async function loadSettings() {
  try {
    const s = v => document.getElementById(v)
    for (const [key, elId, fallback] of [
      ['engine', 'engine-select', 'local'],
      ['temperature', 'temp-range', '0.7'],
      ['context_size', 'ctx-size', '2048'],
      ['model_path', 'model-path', '']
    ]) {
      try {
        const r = await api('GET', '/settings/' + key)
        s(elId).value = r.value
      } catch {
        s(elId).value = fallback
      }
    }
    document.getElementById('temp-val').textContent = s('temp-range').value
    document.getElementById('engine-badge').textContent = s('engine-select').value
    loadModelStatus()
  } catch (e) {
    // Settings endpoint might not be available
  }
}

let modelPollTimer = null

function formatModelBytes(value) {
  if (!value) return '0 MB'
  return (value / (1024 * 1024)).toFixed(0) + ' MB'
}

async function loadModelStatus() {
  const button = document.getElementById('model-download-btn')
  const status = document.getElementById('model-download-status')
  if (!button || !status) return
  try {
    const result = await api('GET', '/models/status')
    if (result.state === 'ready' && result.available) {
      button.textContent = 'Model installed'
      button.disabled = true
      status.textContent = result.filename + ' is ready for offline use'
    } else if (result.state === 'downloading') {
      button.textContent = 'Installing...'
      button.disabled = true
      status.textContent = result.total_bytes
        ? `${result.progress}% (${formatModelBytes(result.downloaded_bytes)} / ${formatModelBytes(result.total_bytes)})`
        : `Downloading (${formatModelBytes(result.downloaded_bytes)})`
      if (!modelPollTimer) modelPollTimer = setInterval(loadModelStatus, 1000)
    } else if (result.state === 'error') {
      button.textContent = 'Retry install'
      button.disabled = false
      status.textContent = result.error || 'Model installation failed'
      if (modelPollTimer) { clearInterval(modelPollTimer); modelPollTimer = null }
    } else {
      button.textContent = 'Install model'
      button.disabled = false
      status.textContent = 'Gemma 3 1B is not installed yet'
    }
  } catch (e) {
    status.textContent = 'Model installer unavailable'
  }
}

async function downloadModel() {
  const button = document.getElementById('model-download-btn')
  if (!button) return
  button.disabled = true
  try {
    await api('POST', '/models/download', {})
    await loadModelStatus()
    toast('Model installation started', 'info', 2500)
  } catch (e) {
    button.disabled = false
    toast(e.message, 'error')
  }
}

const saveCache = {}
async function saveSetting(key, value) {
  // Debounce rapid saves from range input
  const now = Date.now()
  if (saveCache[key] && now - saveCache[key] < 100) return
  saveCache[key] = now

  try {
    await api('PUT', '/settings/' + key, { value: String(value) })
    if (key === 'engine') {
      document.getElementById('engine-badge').textContent = value
      toast('Engine: ' + value, 'info', 2000)
    }
    if (key === 'temperature') {
      toast('Temperature: ' + value, 'info', 1500)
    }
  } catch (e) {
    toast('Failed to save setting: ' + e.message, 'error')
  }
}

function saveSettingDelayed(key, value) {
  clearTimeout(settingsTimer)
  settingsTimer = setTimeout(() => saveSetting(key, value), 500)
}
