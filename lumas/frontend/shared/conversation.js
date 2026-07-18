/**
 * ConversationService — orchestrates the chat flow on Android.
 *
 * Flow:
 *   1. Store the user message in IndexedDB
 *   2. Retrieve relevant context chunks
 *   3. Build the prompt with context + conversation history
 *   4. Generate response via the local llama.cpp endpoint
 *   5. Store the assistant response
 *   6. Return the response text
 *
 * JS port of the Python ConversationService in lumas/backend/services/conversation.py
 */

class ConversationService {
  /**
   * @param {import('./storage.js').Storage} storage
   * @param {import('./engine.js').LocalEngine} engine
   * @param {import('./retrieval.js').RetrievalService} retrieval
   * @param {import('./prompting.js').PromptBuilder} [promptBuilder]
   */
  constructor(storage, engine, retrieval, promptBuilder) {
    this.storage = storage
    this.engine = engine
    this.retrieval = retrieval
    this.promptBuilder = promptBuilder || this._defaultPromptBuilder()
  }

  _defaultPromptBuilder() {
    if (typeof window !== 'undefined' && window.PromptBuilder) {
      return new window.PromptBuilder()
    }
    // Minimal fallback with the same system prompt
    return {
      buildConversationPrompt: (query, contextChunks, history) => {
        const messages = [{ role: 'system', content: 'You are Lumas, a helpful tutor.' }]
        if (contextChunks && contextChunks.length > 0) {
          messages.push({ role: 'system', content: 'Context:\n' + contextChunks.join('\n\n---\n') })
        }
        if (history) {
          for (const msg of history.slice(-20)) {
            messages.push({ role: msg.role || 'user', content: msg.content || '' })
          }
        }
        messages.push({ role: 'user', content: query })
        return messages
      }
    }
  }

  /**
   * Process a user query and return the assistant's response.
   * @param {string} sessionId
   * @param {string} query
   * @param {string} [documentId] - Optional document to scope context to
   * @param {number} [temperature] - Override default temperature
   * @param {AbortSignal} [signal] - Optional AbortSignal for cancellation
   * @returns {Promise<string>} The assistant's response text
   */
  async ask(sessionId, query, documentId, temperature, signal) {
    // 1. Store user message
    await this.storage.addMessage(sessionId, 'user', query)

    // 2. Retrieve relevant context
    const chunks = await this.retrieval.retrieve(query, 5, documentId)
    const contextChunks = chunks.map(c => c.content)

    // 3. Get conversation history (excluding the just-stored query)
    const history = await this.storage.getRecentMessages(sessionId, 20)
    const historyWithoutLast = history.slice(0, -1)

    // 4. Build prompt
    const messages = this.promptBuilder.buildConversationPrompt(
      query,
      contextChunks,
      historyWithoutLast,
    )

    // 5. Generate response
    const response = await this.engine.generate(messages, { temperature, signal })

    // 6. Store assistant response
    await this.storage.addMessage(sessionId, 'assistant', response)

    console.log(
      `Session ${sessionId.slice(0, 8)}: answered query (${query.length} chars, chunks=${contextChunks.length})`
    )
    return response
  }

  /**
   * Generate a response without storing it (for previews or suggestions).
   * @param {string} sessionId
   * @param {string} query
   * @param {string} [documentId]
   * @returns {Promise<string>}
   */
  async preview(sessionId, query, documentId) {
    const chunks = await this.retrieval.retrieve(query, 3, documentId)
    const contextChunks = chunks.map(c => c.content)
    const history = await this.storage.getRecentMessages(sessionId, 10)

    const messages = this.promptBuilder.buildConversationPrompt(
      query,
      contextChunks,
      history,
    )
    return this.engine.generate(messages, { maxTokens: 256 })
  }

  /**
   * Get the full message history for a session.
   * @param {string} sessionId
   * @returns {Promise<Array<{role:string, content:string}>>}
   */
  async getHistory(sessionId) {
    return this.storage.getMessages(sessionId)
  }

  /**
   * Create a new session and return it.
   * @param {string} [engineType='local']
   * @returns {Promise<Object>}
   */
  async createSession(engineType = 'local') {
    return this.storage.createSession(engineType)
  }

  /**
   * List all sessions.
   * @returns {Promise<Array>}
   */
  async listSessions() {
    return this.storage.listSessions()
  }

  /**
   * Delete a session and all its messages.
   * @param {string} sessionId
   */
  async deleteSession(sessionId) {
    await this.storage.deleteSession(sessionId)
  }
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { ConversationService }
} else if (typeof window !== 'undefined') {
  window.ConversationService = ConversationService
}
