/* ═══════════════════════════════════════════════════════════
   Lumas Android — Main Application
   ═══════════════════════════════════════════════════════════
   Runs entirely on-device. Uses IndexedDB (via shared/Storage)
   and calls the local llama.cpp HTTP endpoint (via shared/LocalEngine).
   No external API server required.
   ═══════════════════════════════════════════════════════════ */

// ── State ─────────────────────────────────────────────────
let sid = null          // current session ID
let docId = null        // active document chunk ID for context
let docName = ''        // active document name
let settingsTimer = null
let isGenerating = false

// ── Shared Module Instances ───────────────────────────────
let storage, promptBuilder, retrieval, engine, quizService, conversationService

// ── Init ──────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  try {
    storage = new Storage()
    promptBuilder = new PromptBuilder()
    retrieval = new RetrievalService(storage)
    engine = new LocalEngine('http://localhost:8080', 0.7, 1024)
    quizService = new QuizService(storage, engine, promptBuilder)
    conversationService = new ConversationService(storage, engine, retrieval, promptBuilder)

    // Create or load the default session
    const sessions = await storage.listSessions()
    if (sessions.length > 0) {
      sid = sessions[0].id
      const msgs = await storage.getMessages(sid)
      if (msgs.length > 0) renderMessages(msgs)
    }

    // Load saved settings
    await loadSettings()

    // Check engine health
    checkEngineHealth()

    setupEventDelegation()
    setupChatInput()
    toast('Lumas is ready', 'success', 2000)
    setStatus(true)
  } catch (e) {
    console.error('Init error:', e)
    toast('Initialization failed: ' + e.message, 'error')
  }
})

// ── Event Delegation ─────────────────────────────────────
function setupEventDelegation() {
  // Tab bar switching
  document.getElementById('tab-bar').addEventListener('click', e => {
    const tab = e.target.closest('.tab-btn')
    if (!tab) return
    switchView(tab.dataset.view)
  })

  // Document selection
  document.getElementById('documents-list').addEventListener('click', e => {
    const card = e.target.closest('.doc-card')
    if (!card) return
    selectDocumentChunk(card.dataset.chunkId, card.dataset.docTitle)
  })

  // Settings - temperature range
  document.getElementById('temp-range').addEventListener('input', function() {
    document.getElementById('temp-val').textContent = this.value
    saveSettingDelayed('temperature', this.value)
  })

  // Settings - server URL change
  document.getElementById('server-url').addEventListener('change', function() {
    const url = this.value.trim().replace(/\/+$/, '')
    engine.baseUrl = url
    saveSetting('server_url', url)
  })

  // Settings - context size
  document.getElementById('ctx-size').addEventListener('change', function() {
    saveSetting('context_size', this.value)
  })

  // Settings - max tokens
  document.getElementById('max-tokens').addEventListener('change', function() {
    saveSetting('max_tokens', this.value)
  })
}

// ── Toast Notifications ──────────────────────────────────
function toast(msg, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container')
  const el = document.createElement('div')
  el.className = 'toast ' + type
  const icon = type === 'error' ? '✕' : type === 'success' ? '✓' : 'ℹ'
  el.innerHTML = '<span class="toast-icon">' + icon + '</span><span>' + esc(msg) + '</span>'
  container.appendChild(el)
  setTimeout(() => {
    el.classList.add('removing')
    setTimeout(() => el.remove(), 250)
  }, duration)
}

// ── Escaping ─────────────────────────────────────────────
function esc(s) {
  const d = document.createElement('div')
  d.textContent = s
  return d.innerHTML
}

// ── Loading ──────────────────────────────────────────────
function loading(on, text) {
  document.getElementById('loading').hidden = !on
  document.getElementById('loading-text').textContent = text || 'Processing...'
}

function setStatus(ok = true) {
  const dot = document.getElementById('status-dot')
  dot.className = 'status-dot'
  if (!ok) dot.classList.add('error')
}

// ── View Switching ───────────────────────────────────────
function switchView(view) {
  document.querySelectorAll('.view').forEach(el => el.classList.remove('active'))
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'))

  const target = document.getElementById('view-' + view)
  if (target) target.classList.add('active')

  const tab = document.querySelector('.tab-btn[data-view="' + view + '"]')
  if (tab) tab.classList.add('active')

  if (view === 'quizzes') loadQuizResults()
  if (view === 'documents') loadDocuments()
}

// ── Chat ─────────────────────────────────────────────────
function setupChatInput() {
  const input = document.getElementById('chat-input')
  const sendBtn = document.getElementById('send-btn')

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  })

  input.addEventListener('input', function() {
    this.style.height = 'auto'
    this.style.height = Math.min(this.scrollHeight, 100) + 'px'
    sendBtn.disabled = !this.value.trim()
  })

  sendBtn.addEventListener('click', send)
}

async function send() {
  const el = document.getElementById('chat-input')
  const query = el.value.trim()
  if (!query || isGenerating) return

  isGenerating = true

  // Auto-create session if needed
  if (!sid) {
    try {
      const session = await storage.createSession('local')
      sid = session.id
    } catch (e) {
      toast('Failed to create session: ' + e.message, 'error')
      isGenerating = false
      return
    }
  }

  appendMessage('user', query)
  el.value = ''
  el.style.height = 'auto'
  document.getElementById('send-btn').disabled = true

  // Show typing indicator
  showTypingIndicator()

  try {
    const response = await conversationService.ask(sid, query, docId)

    hideTypingIndicator()
    appendMessage('assistant', response)
    setStatus(true)
  } catch (e) {
    hideTypingIndicator()
    const errMsg = e.message.includes('Failed to fetch') || e.message.includes('NetworkError')
      ? 'Cannot reach the local model. Is llama.cpp running on port 8080? Tap Settings to check.'
      : e.message
    appendMessage('assistant', '⚠️ ' + errMsg)
    setStatus(false)
  } finally {
    isGenerating = false
  }
}

function showTypingIndicator() {
  const container = document.getElementById('messages')
  const existing = document.getElementById('typing-indicator')
  if (existing) return

  const el = document.createElement('div')
  el.className = 'typing-indicator'
  el.id = 'typing-indicator'
  el.innerHTML = '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>'
  container.appendChild(el)
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
  div.innerHTML = formatMessage(text)
  container.appendChild(div)
  container.scrollTop = container.scrollHeight
}

function formatMessage(text) {
  let h = esc(text)
  // Code blocks
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
      '<div class="welcome"><div class="welcome-icon">💬</div><h3>Lumas</h3><p>Ask a question to get started.</p></div>'
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

function selectDocumentChunk(chunkId, docTitle) {
  setDoc(chunkId, docTitle)
  toast('Using chunk from "' + docTitle + '"', 'info', 2000)
  switchView('chat')
}

// ── Documents ───────────────────────────────────────────
async function loadDocuments() {
  try {
    const chunks = await storage.getAllChunks()
    const list = document.getElementById('documents-list')
    const empty = document.getElementById('docs-empty')

    if (chunks.length === 0) {
      empty.hidden = false
      list.innerHTML = ''
      return
    }

    empty.hidden = true
    list.innerHTML = ''

    // Group chunks by document
    const byDoc = {}
    for (const c of chunks) {
      const key = c.document_id || 'unknown'
      if (!byDoc[key]) {
        const doc = c.document_id ? await storage.getDocument(c.document_id) : null
        byDoc[key] = {
          title: doc ? doc.title : 'Unknown Document',
          chunks: []
        }
      }
      byDoc[key].chunks.push(c)
    }

    for (const [docId, group] of Object.entries(byDoc)) {
      // Document header
      const header = document.createElement('div')
      header.style.cssText = 'font-size:13px;font-weight:600;color:var(--text-secondary);padding:12px 4px 4px;'
      header.textContent = group.title
      list.appendChild(header)

      for (const chunk of group.chunks.slice(0, 10)) {  // Max 10 per doc
        const card = document.createElement('div')
        card.className = 'doc-card'
        card.dataset.chunkId = chunk.id
        card.dataset.docTitle = group.title
        card.innerHTML = `
          <div class="doc-card-header">
            <span class="doc-card-icon">📄</span>
            <span class="doc-card-title">${esc(group.title)}</span>
          </div>
          <div class="doc-card-preview">${esc(chunk.content.slice(0, 200))}</div>
          <div class="doc-card-meta">Position ${chunk.position} · ${chunk.content.length} chars</div>`
        list.appendChild(card)
      }
    }
  } catch (e) {
    console.error('Load documents error:', e)
  }
}

// ── Quizzes ─────────────────────────────────────────────
async function loadQuizResults() {
  if (!sid) {
    document.getElementById('quiz-content').innerHTML =
      '<div class="empty-state"><div class="empty-icon">💬</div><h3>No session active</h3><p>Start a chat session first.</p></div>'
    return
  }

  try {
    const results = await quizService.getQuizResults(sid)
    const container = document.getElementById('quiz-content')

    if (!results.length) {
      container.innerHTML =
        '<div class="empty-state"><div class="empty-icon">📝</div><h3>No quizzes yet</h3><p>Select a document chunk and ask Lumas to generate a quiz.</p></div>'
      return
    }

    container.innerHTML = ''
    results.forEach((r, idx) => {
      const card = document.createElement('div')
      card.className = 'quiz-card'

      const date = new Date(r.created_at * 1000).toLocaleDateString()
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
      '<div class="empty-state"><div class="empty-icon">⚠️</div><h3>Error</h3><p>' + esc(e.message) + '</p></div>'
  }
}

// ── Settings ─────────────────────────────────────────────
async function checkEngineHealth() {
  const statusEl = document.getElementById('engine-status')
  statusEl.className = 'engine-status checking'
  statusEl.textContent = 'Checking…'

  try {
    const ok = await engine.healthCheck()
    if (ok) {
      statusEl.className = 'engine-status online'
      statusEl.textContent = 'Online ✓'
      setStatus(true)
    } else {
      statusEl.className = 'engine-status offline'
      statusEl.textContent = 'Offline ✗'
      setStatus(false)
    }
  } catch (e) {
    statusEl.className = 'engine-status offline'
    statusEl.textContent = 'Error ✗'
    setStatus(false)
  }
}

async function loadSettings() {
  try {
    engine.baseUrl = (await storage.getSetting('server_url', 'http://localhost:8080'))
    document.getElementById('server-url').value = engine.baseUrl

    const temp = await storage.getSetting('temperature', '0.7')
    document.getElementById('temp-range').value = temp
    document.getElementById('temp-val').textContent = temp

    document.getElementById('ctx-size').value = await storage.getSetting('context_size', '2048')
    document.getElementById('max-tokens').value = await storage.getSetting('max_tokens', '1024')
  } catch (e) {
    // Defaults used
  }
}

async function saveSetting(key, value) {
  try {
    await storage.setSetting(key, value)
  } catch (e) {
    console.warn('Failed to save setting:', e)
  }
}

function saveSettingDelayed(key, value) {
  clearTimeout(settingsTimer)
  settingsTimer = setTimeout(() => saveSetting(key, value), 500)
}

async function clearAllData() {
  if (!confirm('Clear all local data? This will delete all sessions, documents, and settings.')) return

  loading(true, 'Clearing data…')
  try {
    await storage.clearAll()

    sid = null
    docId = null
    docName = ''

    // Reset UI
    document.getElementById('messages').innerHTML =
      '<div class="welcome"><div class="welcome-icon">📚</div><h3>Welcome to Lumas</h3><p>All data cleared.</p></div>'

    toast('All data cleared', 'info', 2000)
  } catch (e) {
    toast('Error clearing data: ' + e.message, 'error')
  } finally {
    loading(false)
  }
}
