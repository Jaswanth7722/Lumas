/**
 * QuizService — generates quizzes from document chunks and tracks student answers.
 *
 * JS port of the Python QuizService in lumas/backend/services/quiz.py.
 * Quizzes are generated content distinct from conversational turns.
 * Results are stored keyed to chunk and question so progress is visible across sessions.
 */

class QuizService {
  /**
   * @param {import('./storage.js').Storage} storage - IndexedDB storage instance
   * @param {import('./engine.js').LocalEngine} engine - llama.cpp engine interface
   * @param {import('./prompting.js').PromptBuilder} [promptBuilder]
   */
  constructor(storage, engine, promptBuilder) {
    this.storage = storage
    this.engine = engine
    // Accept an injected PromptBuilder or look it up from the global/window scope
    if (promptBuilder) {
      this.promptBuilder = promptBuilder
    } else if (typeof window !== 'undefined' && window.PromptBuilder) {
      this.promptBuilder = new window.PromptBuilder()
    } else if (typeof PromptBuilder !== 'undefined') {
      this.promptBuilder = new PromptBuilder()
    } else {
      // Fallback: create a minimal inline builder
      this.promptBuilder = {
        buildQuizPrompt: (content, n) =>
          `You are Lumas, a quiz generator. Based on the following content from a study document, generate ${n} multiple-choice questions to test understanding of the key concepts.\n\nContent:\n${content}\n\nRespond with ONLY valid JSON.`
      }
    }
  }

  /**
   * Generate a quiz from a document chunk.
   * @param {string} sessionId - Current session ID
   * @param {string} chunkId - Source document chunk ID
   * @param {number} [numQuestions=5] - Number of questions to generate
   * @returns {Promise<Object|null>} Quiz object with id, questions, or null on failure
   */
  async generateQuiz(sessionId, chunkId, numQuestions = 5) {
    const chunk = await this.storage.getChunk(chunkId)
    if (!chunk) {
      console.warn(`Chunk ${chunkId} not found`)
      return null
    }

    const prompt = this.promptBuilder.buildQuizPrompt(chunk.content, numQuestions)

    // Attempt generation with one retry
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        let raw
        if (attempt === 1) {
          const retryPrompt = prompt + '\n\nIMPORTANT: Return ONLY valid JSON. No other text.'
          raw = await this.engine.generateText(retryPrompt, { maxTokens: 2048 })
        } else {
          raw = await this.engine.generateText(prompt, { maxTokens: 2048 })
        }

        const questions = QuizService._parseQuizJson(raw)
        if (questions) {
          const quiz = await this.storage.createQuiz(sessionId, chunkId, questions)
          console.log(`Quiz ${quiz.id} generated (${questions.length} questions from chunk ${chunkId})`)
          return quiz
        }
      } catch (e) {
        console.warn(`Quiz generation attempt ${attempt + 1} failed:`, e)
      }
    }

    console.error(`Quiz generation failed after 2 attempts for chunk ${chunkId}`)
    return null
  }

  /**
   * Record a student's answer to a quiz question.
   * @param {string} quizId
   * @param {number} questionIndex
   * @param {string} studentAnswer - The student's chosen answer (index as string like "0", "1", etc.)
   * @param {number} correctIndex - The correct answer index
   * @returns {Promise<Object>} Answer record with feedback
   */
  async answerQuestion(quizId, questionIndex, studentAnswer, correctIndex) {
    const isCorrect = String(studentAnswer).trim() === String(correctIndex).trim()
    const answer = await this.storage.addQuizAnswer(quizId, questionIndex, isCorrect, studentAnswer)

    // Fetch the quiz to provide feedback
    const quiz = await this.storage.getQuiz(quizId)
    let correctAnswer = null
    if (quiz && questionIndex < quiz.questions.length) {
      const q = quiz.questions[questionIndex]
      correctAnswer = q.options[q.correct_index]
    }

    return {
      id: answer.id,
      quiz_id: quizId,
      question_index: questionIndex,
      is_correct: isCorrect,
      student_answer: studentAnswer,
      correct_answer: correctAnswer,
    }
  }

  /**
   * Get all quiz results for a session with answer details.
   * @param {string} sessionId
   * @returns {Promise<Array>}
   */
  async getQuizResults(sessionId) {
    const quizzes = await this.storage.getQuizzesForSession(sessionId)
    const results = []
    for (const quiz of quizzes) {
      const answers = await this.storage.getAnswersForQuiz(quiz.id)
      const correctCount = answers.filter(a => a.is_correct).length
      results.push({
        quiz_id: quiz.id,
        chunk_id: quiz.chunk_id,
        questions: quiz.questions,
        answers,
        score: `${correctCount}/${quiz.questions.length}`,
        created_at: quiz.created_at,
      })
    }
    return results
  }

  /**
   * Parse JSON from model output, handling common wrapping.
   * Same algorithm as Python QuizService._parse_quiz_json.
   * @param {string} raw - Raw model output
   * @returns {Array|null} Parsed questions or null on failure
   */
  static _parseQuizJson(raw) {
    raw = raw.trim()

    // Remove code fences if present
    if (raw.startsWith('```')) {
      const firstNewline = raw.indexOf('\n')
      if (firstNewline > 0) {
        raw = raw.slice(firstNewline + 1)
      }
      const lastFence = raw.lastIndexOf('```')
      if (lastFence >= 0) {
        raw = raw.slice(0, lastFence)
      }
    }

    // Find JSON object boundaries
    const start = raw.indexOf('{')
    const end = raw.lastIndexOf('}') + 1
    if (start >= 0 && end > start) {
      raw = raw.slice(start, end)
    }

    try {
      const data = JSON.parse(raw)
      const questions = data.questions || []
      // Validate structure
      for (const q of questions) {
        if (!q.question || !q.options || q.correct_index === undefined) {
          console.warn('Missing required keys in question:', q)
          return null
        }
        if (q.options.length !== 4) {
          console.warn(`Question must have 4 options, got ${q.options.length}`)
          return null
        }
        if (q.correct_index < 0 || q.correct_index > 3) {
          console.warn(`correct_index must be 0-3, got ${q.correct_index}`)
          return null
        }
      }
      return questions
    } catch (e) {
      console.warn('Failed to parse quiz JSON:', e.message)
      return null
    }
  }
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { QuizService }
}
