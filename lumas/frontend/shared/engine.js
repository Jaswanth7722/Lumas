/**
 * LocalEngine — calls the local llama.cpp HTTP endpoint on Android.
 *
 * The llama.cpp server runs on-device (started by the native shell) and
 * exposes a completion endpoint at http://localhost:8080/completion.
 *
 * This module provides the same interface as the Python LocalEngine
 * (generate, generateText, healthCheck) so the frontend JS can use it
 * identically regardless of platform.
 */

class LocalEngine {
  /**
   * @param {string} [baseUrl='http://localhost:8080'] - llama.cpp server URL
   * @param {number} [temperature=0.7] - Default generation temperature
   * @param {number} [maxTokens=1024] - Default max tokens
   */
  constructor(baseUrl = 'http://localhost:8080', temperature = 0.7, maxTokens = 1024) {
    this.baseUrl = baseUrl.replace(/\/+$/, '')
    this.temperature = temperature
    this.maxTokens = maxTokens
    this.name = 'local (Android)'
    this.isOnline = false
  }

  /**
   * Convert chat messages into the prompt format expected by llama.cpp.
   * Uses the same <|im_start|>/<|im_end|> format as the Python LocalEngine.
   * @param {Array<{role:string, content:string}>} messages
   * @returns {string}
   */
  _messagesToPrompt(messages) {
    const parts = []
    for (const msg of messages) {
      const role = msg.role || 'user'
      const content = msg.content || ''
      parts.push(`<|im_start|>${role}\n${content}<|im_end|>`)
    }
    parts.push('<|im_start|>assistant\n')
    return parts.join('\n')
  }

  /**
   * Call the llama.cpp completion endpoint.
   * @param {string} prompt - The prompt string
   * @param {number} [temperature] - Override default temperature
   * @param {number} [maxTokens] - Override default max tokens
   * @param {AbortSignal} [signal] - Optional AbortSignal for fetch cancellation
   * @returns {Promise<string>} - The generated text
   */
  async _callHttp(prompt, temperature, maxTokens, signal) {
    const temp = temperature !== undefined ? temperature : this.temperature
    const tokens = maxTokens !== undefined ? maxTokens : this.maxTokens

    const response = await fetch(`${this.baseUrl}/completion`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt,
        temperature: temp,
        n_predict: tokens,
        stop: ['</s>', '<|im_end|>'],
      }),
      signal,
    })

    if (!response.ok) {
      const text = await response.text().catch(() => response.statusText)
      throw new Error(`llama.cpp error (${response.status}): ${text}`)
    }

    const result = await response.json()
    return result.content || ''
  }

  /**
   * Generate a response from chat messages.
   * @param {Array<{role:string, content:string}>} messages
   * @param {Object} [options]
   * @param {number} [options.temperature]
   * @param {number} [options.maxTokens]
   * @param {AbortSignal} [options.signal]
   * @returns {Promise<string>}
   */
  async generate(messages, options = {}) {
    const prompt = this._messagesToPrompt(messages)
    return this._callHttp(prompt, options.temperature, options.maxTokens, options.signal)
  }

  /**
   * Generate a text completion from a raw string prompt.
   * Used for quiz generation.
   * @param {string} prompt
   * @param {Object} [options]
   * @param {number} [options.temperature]
   * @param {number} [options.maxTokens]
   * @param {AbortSignal} [options.signal]
   * @returns {Promise<string>}
   */
  async generateText(prompt, options = {}) {
    return this._callHttp(prompt, options.temperature, options.maxTokens, options.signal)
  }

  /**
   * Check if the llama.cpp server is running and healthy.
   * @returns {Promise<boolean>}
   */
  async healthCheck() {
    try {
      const response = await fetch(`${this.baseUrl}/health`, {
        method: 'GET',
        signal: AbortSignal.timeout(5000),
      })
      return response.ok
    } catch {
      return false
    }
  }

  /**
   * Stream a response from the chat endpoint using server-sent events.
   * llama.cpp's /completion endpoint supports streaming.
   *
   * @param {Array<{role:string, content:string}>} messages
   * @param {Object} [options]
   * @param {function(string): void} options.onToken - Called with each token
   * @param {function(string): void} [options.onComplete] - Called with full text when done
   * @param {function(Error): void} [options.onError] - Called on error
   * @param {AbortSignal} [options.signal]
   */
  async generateStream(messages, options = {}) {
    const prompt = this._messagesToPrompt(messages)
    const temp = options.temperature !== undefined ? options.temperature : this.temperature
    const tokens = options.maxTokens !== undefined ? options.maxTokens : this.maxTokens

    try {
      const response = await fetch(`${this.baseUrl}/completion`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt,
          temperature: temp,
          n_predict: tokens,
          stop: ['</s>', '<|im_end|>'],
          stream: true,
        }),
        signal: options.signal,
      })

      if (!response.ok) {
        throw new Error(`llama.cpp error (${response.status})`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let fullText = ''
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6).trim()
            if (!data || data === '[DONE]') continue
            try {
              const parsed = JSON.parse(data)
              const token = parsed.content || parsed.token || ''
              if (token) {
                fullText += token
                if (options.onToken) options.onToken(token)
              }
            } catch {
              // Skip malformed lines
            }
          }
        }
      }

      if (options.onComplete) options.onComplete(fullText)
    } catch (e) {
      if (e.name === 'AbortError') return
      if (options.onError) options.onError(e)
      else throw e
    }
  }
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { LocalEngine }
}
