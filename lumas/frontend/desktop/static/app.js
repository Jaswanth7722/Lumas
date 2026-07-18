/* ═══════════════════════════════════════════════════════════
   Lumas Desktop — Main Application
   ═══════════════════════════════════════════════════════════ */

const API = '/api'
let sid = null       // current session ID
let docId = null     // active document ID
let docName = ''     // active document name
let settingsTimer = null

// ── Init ─────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadSessions()
  loadDocuments()
  loadSettings()
  setupDragDrop()
  setupChatInput()
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
    return
  }
  sid = id
  try {
    const msgs = await api('GET', '/sessions/' + sid + '/messages')
    renderMessages(msgs)
    const s = await api('GET', '/sessions/' + sid)
    document.getElementById('engine-badge').textContent = s.engine_used
  } catch (e) {
    toast('Failed to load session: ' + e.message, 'error')
  }
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
  if (!query) return

  if (!sid) {
    try {
      const s = await api('POST', '/sessions', {})
      sid = s.id
      loadSessions()
    } catch (e) {
      toast('Create a session first', 'error')
      return
    }
  }

  appendMessage('user', query)
  el.value = ''
  onChatInput(el)

  // Show typing indicator
  const typingEl = document.createElement('div')
  typingEl.className = 'typing-indicator'
  typingEl.id = 'typing-indicator'
  typingEl.innerHTML = '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>'
  document.getElementById('messages').appendChild(typingEl)
  document.getElementById('messages').scrollTop = document.getElementById('messages').scrollHeight

  setStatus('Thinking…', true)
  try {
    const r = await api('POST', '/chat', {
      session_id: sid,
      query: query,
      document_id: docId || undefined
    })
    document.getElementById('typing-indicator')?.remove()
    appendMessage('assistant', r.response)
    setStatus('Ready')
  } catch (e) {
    document.getElementById('typing-indicator')?.remove()
    appendMessage('assistant', '⚠️ ' + e.message)
    setStatus('Error', false)
  }
}

function appendMessage(role, text) {
  const container = document.getElementById('messages')
  // Remove welcome if present
  const welcome = container.querySelector('.welcome')
  if (welcome) welcome.remove()

  const div = document.createElement('div')
  div.className = 'msg ' + role
  div.innerHTML = formatMessage(text)
  container.appendChild(div)
  container.scrollTop = container.scrollHeight
}

function formatMessage(text) {
  let h = esc(text)
    .replace(/&amp;#xFE0F;/g, '')
  // Code blocks first
  h = h.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
  // Inline code
  h = h.replace(/`([^`]+)`/g, '<code>$1</code>')
  // Bold
  h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  // Paragraphs
  h = h.replace(/\n\n/g, '</p><p>')
  h = h.replace(/\n/g, '<br>')
  return '<p>' + h + '</p>'
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

function setDoc(id, title) {
  docId = id
  docName = title
  const ind = document.getElementById('doc-indicator')
  ind.hidden = false
  document.getElementById('doc-name').textContent = title
}

function clearDoc() {
  docId = null
  docName = ''
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
      const err = await res.text().catch(() => res.statusText)
      throw new Error(err)
    }
    const doc = await res.json()
    addDocumentCard(doc)
    setDoc(doc.id, doc.title)
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
  card.innerHTML = `
    <div class="doc-card-info">
      <span class="doc-card-icon">📄</span>
      <div>
        <div class="doc-card-title">${esc(doc.title)}</div>
        <div class="doc-card-meta">${doc.chunks.length} chunks · ${esc(doc.source_filename)}</div>
      </div>
    </div>
    <div class="doc-card-actions">
      <button onclick="useDoc('${doc.id}', '${esc(doc.title)}')">Use</button>
      <button class="btn-danger" onclick="deleteDoc('${doc.id}')">Delete</button>
    </div>`
  list.appendChild(card)
}

function useDoc(id, title) {
  setDoc(id, title)
  toast(`Using "${title}"`, 'info', 2000)
  switchView('chat')
}

async function deleteDoc(id) {
  try {
    await api('DELETE', '/documents/' + id)
    loadDocuments()
    if (docId === id) clearDoc()
    toast('Document deleted', 'info', 2000)
  } catch (e) {
    toast('Delete failed: ' + e.message, 'error')
  }
}

// ── Quizzes ─────────────────────────────────────────────

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
              return `<div class="${cls}">${icon}${esc(opt)}</div>`
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
  } catch (e) {
    // Settings endpoint might not be available
  }
}

async function saveSetting(key, value) {
  try {
    await api('PUT', '/settings/' + key, { value: String(value) })
    if (key === 'engine') {
      document.getElementById('engine-badge').textContent = value
      toast('Engine: ' + value, 'info', 2000)
    }
  } catch (e) {
    toast('Failed to save setting: ' + e.message, 'error')
  }
}

function saveSettingDelayed(key, value) {
  clearTimeout(settingsTimer)
  settingsTimer = setTimeout(() => saveSetting(key, value), 500)
}
