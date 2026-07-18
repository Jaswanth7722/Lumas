/**
 * Storage — IndexedDB wrapper for Android WebView.
 *
 * Mirrors the desktop SQLite schema (minus embeddings).
 * Stores: documents, chunks, sessions, messages, quizzes, quiz_answers, settings
 *
 * All methods return Promises.
 * Read operations use proper IndexedDB request.onsuccess patterns.
 * Write operations use a transaction helper.
 */

class Storage {
  constructor(dbName = 'lumas_db', version = 1) {
    this.dbName = dbName
    this.version = version
    this._db = null
  }

  _open() {
    if (this._db) return Promise.resolve(this._db)
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(this.dbName, this.version)

      req.onupgradeneeded = (e) => {
        const db = e.target.result

        if (!db.objectStoreNames.contains('documents')) {
          const store = db.createObjectStore('documents', { keyPath: 'id' })
          store.createIndex('created_at', 'created_at', { unique: false })
        }
        if (!db.objectStoreNames.contains('chunks')) {
          const store = db.createObjectStore('chunks', { keyPath: 'id' })
          store.createIndex('document_id', 'document_id', { unique: false })
          store.createIndex('position', 'position', { unique: false })
        }
        if (!db.objectStoreNames.contains('sessions')) {
          const store = db.createObjectStore('sessions', { keyPath: 'id' })
          store.createIndex('last_activity_at', 'last_activity_at', { unique: false })
        }
        if (!db.objectStoreNames.contains('messages')) {
          const store = db.createObjectStore('messages', { keyPath: 'id' })
          store.createIndex('session_id', 'session_id', { unique: false })
          store.createIndex('sequence_number', 'sequence_number', { unique: false })
        }
        if (!db.objectStoreNames.contains('quizzes')) {
          const store = db.createObjectStore('quizzes', { keyPath: 'id' })
          store.createIndex('session_id', 'session_id', { unique: false })
          store.createIndex('chunk_id', 'chunk_id', { unique: false })
        }
        if (!db.objectStoreNames.contains('quiz_answers')) {
          const store = db.createObjectStore('quiz_answers', { keyPath: 'id' })
          store.createIndex('quiz_id', 'quiz_id', { unique: false })
        }
        if (!db.objectStoreNames.contains('settings')) {
          db.createObjectStore('settings', { keyPath: 'key' })
        }
      }

      req.onsuccess = (e) => {
        this._db = e.target.result
        resolve(this._db)
      }
      req.onerror = (e) => reject(new Error(`IndexedDB open failed: ${e.target.error}`))
    })
  }

  // ── Write helper (for add/put/delete where we don't need the stored value back) ──

  _write(storeName, fn) {
    return this._open().then(db => new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, 'readwrite')
      try {
        fn(tx.objectStore(storeName))
      } catch (e) {
        reject(e)
        return
      }
      tx.oncomplete = () => resolve()
      tx.onerror = (e) => reject(new Error(`Write error: ${e.target.error}`))
    }))
  }

  // ── Read helper (for get operations that return a single value) ──

  _get(storeName, key) {
    return this._open().then(db => new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, 'readonly')
      const req = tx.objectStore(storeName).get(key)
      req.onsuccess = () => resolve(req.result || null)
      req.onerror = (e) => reject(new Error(`Read error: ${e.target.error}`))
    }))
  }

  // ── Cursor helper (for collecting all results from an index or store) ──

  _cursor(storeName, indexName, direction = 'next') {
    return this._open().then(db => new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, 'readonly')
      const store = tx.objectStore(storeName)
      const source = indexName ? store.index(indexName) : store
      const results = []
      const req = source.openCursor(null, direction)
      req.onsuccess = (e) => {
        const cursor = e.target.result
        if (cursor) {
          results.push(cursor.value)
          cursor.continue()
        } else {
          resolve(results)
        }
      }
      req.onerror = (e) => reject(new Error(`Cursor error: ${e.target.error}`))
    }))
  }

  // ── Indexed cursor (for filtering by an index key) ──

  _indexCursor(storeName, indexName, indexValue) {
    return this._open().then(db => new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, 'readonly')
      const index = tx.objectStore(storeName).index(indexName)
      const results = []
      const req = index.openCursor(indexValue)
      req.onsuccess = (e) => {
        const cursor = e.target.result
        if (cursor) {
          results.push(cursor.value)
          cursor.continue()
        } else {
          resolve(results)
        }
      }
      req.onerror = (e) => reject(new Error(`Index cursor error: ${e.target.error}`))
    }))
  }

  _uuid() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
      const r = Math.random() * 16 | 0
      return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16)
    })
  }

  _now() {
    return Date.now() / 1000
  }

  // ── Documents ──────────────────────────────────────────────

  addDocument(title, sourceFilename) {
    const doc = {
      id: this._uuid(),
      title,
      source_filename: sourceFilename,
      created_at: this._now(),
    }
    return this._write('documents', store => store.add(doc)).then(() => doc)
  }

  getDocument(docId) {
    return this._get('documents', docId)
  }

  listDocuments() {
    return this._cursor('documents', 'created_at', 'prev')
  }

  deleteDocument(docId) {
    return this._open().then(db => new Promise((resolve, reject) => {
      const tx = db.transaction(['documents', 'chunks'], 'readwrite')
      tx.objectStore('documents').delete(docId)

      const chunkIndex = tx.objectStore('chunks').index('document_id')
      chunkIndex.openCursor(docId).onsuccess = (e) => {
        const cursor = e.target.result
        if (cursor) {
          tx.objectStore('chunks').delete(cursor.value.id)
          cursor.continue()
        }
      }
      tx.oncomplete = () => resolve()
      tx.onerror = (e) => reject(new Error(`Delete error: ${e.target.error}`))
    }))
  }

  // ── Chunks ─────────────────────────────────────────────────

  addChunks(chunks) {
    return this._write('chunks', store => {
      chunks.forEach(c => store.put(c))
    })
  }

  getChunk(chunkId) {
    return this._get('chunks', chunkId)
  }

  getChunksForDocument(documentId) {
    return this._indexCursor('chunks', 'document_id', documentId)
      .then(results => results.sort((a, b) => a.position - b.position))
  }

  getAllChunks() {
    return this._cursor('chunks')
  }

  // ── Sessions ───────────────────────────────────────────────

  createSession(engineUsed = 'local') {
    const now = this._now()
    const session = {
      id: this._uuid(),
      engine_used: engineUsed,
      created_at: now,
      last_activity_at: now,
    }
    return this._write('sessions', store => store.add(session)).then(() => session)
  }

  getSession(sessionId) {
    return this._get('sessions', sessionId)
  }

  listSessions() {
    return this._cursor('sessions', 'last_activity_at', 'prev')
  }

  updateSessionActivity(sessionId) {
    return this._get('sessions', sessionId).then(session => {
      if (!session) return
      session.last_activity_at = this._now()
      return this._write('sessions', store => store.put(session))
    })
  }

  deleteSession(sessionId) {
    return this._open().then(db => new Promise((resolve, reject) => {
      const tx = db.transaction(['sessions', 'messages', 'quizzes', 'quiz_answers'], 'readwrite')

      tx.objectStore('sessions').delete(sessionId)

      const msgIndex = tx.objectStore('messages').index('session_id')
      msgIndex.openCursor(sessionId).onsuccess = (e) => {
        const cursor = e.target.result
        if (cursor) {
          tx.objectStore('messages').delete(cursor.value.id)
          cursor.continue()
        }
      }

      const quizIndex = tx.objectStore('quizzes').index('session_id')
      quizIndex.openCursor(sessionId).onsuccess = (e) => {
        const cursor = e.target.result
        if (cursor) {
          const ansIndex = tx.objectStore('quiz_answers').index('quiz_id')
          ansIndex.openCursor(cursor.value.id).onsuccess = (e2) => {
            const ansCursor = e2.target.result
            if (ansCursor) {
              tx.objectStore('quiz_answers').delete(ansCursor.value.id)
              ansCursor.continue()
            }
          }
          tx.objectStore('quizzes').delete(cursor.value.id)
          cursor.continue()
        }
      }

      tx.oncomplete = () => resolve()
      tx.onerror = (e) => reject(new Error(`Delete session error: ${e.target.error}`))
    }))
  }

  // ── Messages ───────────────────────────────────────────────

  addMessage(sessionId, role, content) {
    return this._open().then(db => new Promise((resolve, reject) => {
      const tx = db.transaction(['messages', 'sessions'], 'readwrite')

      // Get next sequence number
      const msgIndex = tx.objectStore('messages').index('session_id')
      const seqReq = msgIndex.openCursor(sessionId, 'prev')
      seqReq.onsuccess = () => {
        let lastSeq = 0
        if (seqReq.result) lastSeq = seqReq.result.value.sequence_number || 0

        const msg = {
          id: this._uuid(),
          session_id: sessionId,
          sequence_number: lastSeq + 1,
          role,
          content,
          timestamp: this._now(),
        }
        tx.objectStore('messages').add(msg)

        // Update session activity
        const sessionReq = tx.objectStore('sessions').get(sessionId)
        sessionReq.onsuccess = () => {
          const session = sessionReq.result
          if (session) {
            session.last_activity_at = this._now()
            tx.objectStore('sessions').put(session)
          }
        }

        tx.oncomplete = () => resolve(msg)
      }
      seqReq.onerror = (e) => reject(new Error(`Seq error: ${e.target.error}`))
      tx.onerror = (e) => reject(new Error(`Add message error: ${e.target.error}`))
    }))
  }

  getMessages(sessionId) {
    return this._indexCursor('messages', 'session_id', sessionId)
      .then(results => results.sort((a, b) => a.sequence_number - b.sequence_number))
  }

  getRecentMessages(sessionId, limit = 50) {
    return this.getMessages(sessionId).then(msgs => msgs.slice(-limit))
  }

  // ── Quizzes ────────────────────────────────────────────────

  createQuiz(sessionId, chunkId, questions) {
    const quiz = {
      id: this._uuid(),
      session_id: sessionId,
      chunk_id: chunkId,
      questions_json: JSON.stringify(questions),
      created_at: this._now(),
    }
    return this._write('quizzes', store => store.add(quiz)).then(() => {
      quiz.questions = questions
      return quiz
    })
  }

  getQuiz(quizId) {
    return this._get('quizzes', quizId).then(quiz => {
      if (!quiz) return null
      quiz.questions = JSON.parse(quiz.questions_json || '[]')
      return quiz
    })
  }

  getQuizzesForSession(sessionId) {
    return this._indexCursor('quizzes', 'session_id', sessionId).then(results => {
      results.forEach(q => { q.questions = JSON.parse(q.questions_json || '[]') })
      return results
    })
  }

  getQuizzesForChunk(chunkId) {
    return this._indexCursor('quizzes', 'chunk_id', chunkId).then(results => {
      results.forEach(q => { q.questions = JSON.parse(q.questions_json || '[]') })
      return results
    })
  }

  // ── Quiz Answers ───────────────────────────────────────────

  addQuizAnswer(quizId, questionIndex, isCorrect, studentAnswer) {
    const answer = {
      id: this._uuid(),
      quiz_id: quizId,
      question_index: questionIndex,
      is_correct: isCorrect ? 1 : 0,
      student_answer: String(studentAnswer),
      created_at: this._now(),
    }
    return this._write('quiz_answers', store => store.add(answer)).then(() => answer)
  }

  getAnswersForQuiz(quizId) {
    return this._indexCursor('quiz_answers', 'quiz_id', quizId)
      .then(results => {
        results.sort((a, b) => a.question_index - b.question_index)
        results.forEach(a => { a.is_correct = Boolean(a.is_correct) })
        return results
      })
  }

  // ── Settings ────────────────────────────────────────────────

  getSetting(key, defaultValue = null) {
    return this._get('settings', key).then(result => {
      if (!result) return defaultValue
      try { return JSON.parse(result.value) } catch { return result.value }
    })
  }

  setSetting(key, value) {
    const entry = { key, value: JSON.stringify(value) }
    return this._write('settings', store => store.put(entry))
  }

  // ── Clear All Data ───────────────────────────────────────────

  clearAll() {
    return this._open().then(db => new Promise((resolve, reject) => {
      const stores = ['documents', 'chunks', 'sessions', 'messages', 'quizzes', 'quiz_answers', 'settings']
      const tx = db.transaction(stores, 'readwrite')
      for (const name of stores) {
        tx.objectStore(name).clear()
      }
      tx.oncomplete = () => resolve()
      tx.onerror = (e) => reject(new Error(`Clear error: ${e.target.error}`))
    }))
  }
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { Storage }
}
