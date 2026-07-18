/**
 * PromptBuilder — assembles system prompts for the local engine (Android).
 *
 * This is the JS twin of the Python PromptBuilder in lumas/backend/prompting/builder.py.
 * Keeping both in sync prevents prompt drift between desktop and Android.
 *
 * Templates are identical to the Python version so the model sees the same
 * instructions regardless of platform.
 */

class PromptBuilder {
  constructor(systemPrompt) {
    this.SYSTEM_TEMPLATE = systemPrompt || (
      'You are Lumas, a helpful tutor guiding a student through their learning material. '
      + 'You have access to the following context from their document to answer accurately.\n\n'
      + 'Rules:\n'
      + '- Answer based on the provided context. If the context doesn\'t contain enough information, say so.\n'
      + '- Be concise but thorough — explain concepts clearly.\n'
      + '- Use examples when helpful.\n'
      + '- Do not make up facts or cite sources not present in the context.\n'
      + '- When the student answers a quiz question incorrectly, explain the correct answer patiently.'
    )
    this.systemPrompt = this.SYSTEM_TEMPLATE
  }

  /**
   * Build a message list for chat-style model calls.
   * @param {string} query - The user's current question
   * @param {string[]} contextChunks - Retrieved document chunks
   * @param {Array<{role:string, content:string}>} [conversationHistory] - Previous messages
   * @returns {Array<{role:string, content:string}>}
   */
  buildConversationPrompt(query, contextChunks, conversationHistory) {
    const messages = [{ role: 'system', content: this.systemPrompt }]

    // Inject retrieved context
    if (contextChunks && contextChunks.length > 0) {
      const contextBlock = contextChunks.join('\n\n---\n')
      messages.push({
        role: 'system',
        content: 'Relevant document context:\n' + contextBlock,
      })
    }

    // Add conversation history (last 20)
    if (conversationHistory && conversationHistory.length > 0) {
      const recent = conversationHistory.slice(-20)
      for (const msg of recent) {
        messages.push({
          role: msg.role || 'user',
          content: msg.content || '',
        })
      }
    }

    // Add the current query
    messages.push({ role: 'user', content: query })
    return messages
  }

  /**
   * Build a prompt for the model to continue without a new query.
   * @param {string[]} contextChunks
   * @param {Array<{role:string, content:string}>} conversationHistory
   * @returns {Array<{role:string, content:string}>}
   */
  buildContinuationPrompt(contextChunks, conversationHistory) {
    const messages = [{ role: 'system', content: this.systemPrompt }]

    if (contextChunks && contextChunks.length > 0) {
      const contextBlock = contextChunks.join('\n\n---\n')
      messages.push({
        role: 'system',
        content: 'Relevant document context:\n' + contextBlock,
      })
    }

    if (conversationHistory) {
      for (const msg of conversationHistory) {
        messages.push({
          role: msg.role || 'user',
          content: msg.content || '',
        })
      }
    }

    return messages
  }

  /**
   * Build a text prompt for quiz generation.
   * @param {string} content - The document chunk content
   * @param {number} [numQuestions=5] - Number of questions to generate
   * @returns {string} - A single prompt string for text-completion models
   */
  buildQuizPrompt(content, numQuestions = 5) {
    return (
      'You are Lumas, a quiz generator. Based on the following content from a study document, '
      + `generate ${numQuestions} multiple-choice questions to test understanding of the key concepts.\n\n`
      + `Content:\n${content}\n\n`
      + 'Respond with ONLY valid JSON in the following format — no other text:\n'
      + '{\n'
      + '  "questions": [\n'
      + '    {\n'
      + '      "question": "What is ...?",\n'
      + '      "options": ["A) ...", "B) ...", "C) ...", "D) ..."],\n'
      + '      "correct_index": 0\n'
      + '    }\n'
      + '  ]\n'
      + '}\n\n'
      + `Generate exactly ${numQuestions} questions. Each must have exactly 4 options. `
      + 'correct_index must be 0-3 indicating the correct option.'
    )
  }

  /**
   * Build a message list for quiz generation (chat API).
   * @param {string} content - The document chunk content
   * @param {number} [numQuestions=5] - Number of questions to generate
   * @returns {Array<{role:string, content:string}>}
   */
  buildQuizMessages(content, numQuestions = 5) {
    return [
      {
        role: 'system',
        content: `You are Lumas, a quiz generator. Based on the following content, generate ${numQuestions} multiple-choice questions to test understanding.\n\nContent:\n${content}`,
      },
      {
        role: 'user',
        content: `Generate ${numQuestions} questions based on the above content. Return ONLY valid JSON.`,
      },
    ]
  }

  /**
   * Remove special/control tokens that might leak from the model.
   * @param {string} text
   * @returns {string}
   */
  static stripSpecialTokens(text) {
    return text
      .replace(/<\|.*?\|>/g, '')
      .replace(/\[INST\].*?\[\/INST\]/gs, '')
      .replace(/<s>|<\/s>/g, '')
      .trim()
  }
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { PromptBuilder }
}
