/**
 * RetrievalService — retrieves relevant chunks for a query on Android.
 *
 * Uses keyword overlap scoring (same algorithm as the Python desktop
 * RetrievalService._keyword_retrieve). No embedding model on Android
 * this week per spec.
 *
 * The service interface is identical to the desktop version so the
 * frontend doesn't need to know which strategy is behind it.
 */

class RetrievalService {
  /**
   * @param {import('./storage.js').Storage} storage - The IndexedDB storage instance
   */
  constructor(storage) {
    this.storage = storage
  }

  /**
   * Stop words to filter out during keyword matching.
   * Same set as the Python backend.
   */
  static STOP_WORDS = new Set([
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
    'can', 'could', 'shall', 'should', 'may', 'might', 'to',
    'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as',
    'into', 'through', 'during', 'before', 'after', 'about',
    'between', 'this', 'that', 'these', 'those', 'it', 'its',
  ])

  /**
   * Retrieve the most relevant chunks for a query using keyword overlap.
   * @param {string} query - The user's question
   * @param {number} [topK=5] - Number of chunks to return
   * @param {string} [documentId] - Optional document to scope search to
   * @returns {Promise<Array<{id:string, content:string, score:number, document_id:string, position:number}>>}
   */
  async retrieve(query, topK = 5, documentId) {
    let chunks
    if (documentId) {
      chunks = await this.storage.getChunksForDocument(documentId)
    } else {
      chunks = await this.storage.getAllChunks()
    }

    if (!chunks || chunks.length === 0) {
      return []
    }

    return this._keywordRetrieve(query, chunks, topK)
  }

  /**
   * Score chunks by keyword overlap with the query.
   * Uses TF-like scoring normalized by chunk length.
   *
   * Algorithm identical to Python RetrievalService._keyword_retrieve:
   *   1. Extract words from query, filter stop words
   *   2. For each chunk, compute overlap with query terms
   *   3. Score = overlap / log(chunk_term_count + 1)
   *   4. Return top-k scored chunks
   *
   * @param {string} query
   * @param {Array} chunks
   * @param {number} topK
   * @returns {Array}
   */
  _keywordRetrieve(query, chunks, topK) {
    const queryTerms = this._extractTerms(query)
    // Filter out stop words without mutating the shared STOP_WORDS Set
    const filteredTerms = new Set()
    for (const t of queryTerms) {
      if (!RetrievalService.STOP_WORDS.has(t)) filteredTerms.add(t)
    }

    if (filteredTerms.size === 0) {
      return chunks.slice(0, topK)
    }

    const scored = []
    for (const chunk of chunks) {
      const chunkTerms = this._extractTerms(chunk.content)
      let overlap = 0
      for (const term of filteredTerms) {
        if (chunkTerms.has(term)) overlap++
      }
      if (overlap > 0) {
        const score = overlap / Math.log(chunkTerms.size + 1)
        scored.push({ score: Math.round(score * 10000) / 10000, chunk })
      }
    }

    scored.sort((a, b) => b.score - a.score)
    return scored.slice(0, topK).map(s => ({
      ...s.chunk,
      score: s.score,
    }))
  }

  /**
   * Extract unique word terms from text.
   * @param {string} text
   * @returns {Set<string>}
   */
  _extractTerms(text) {
    const terms = new Set()
    const matches = text.toLowerCase().match(/\w+/g)
    if (matches) {
      for (const m of matches) terms.add(m)
    }
    return terms
  }
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { RetrievalService }
}
