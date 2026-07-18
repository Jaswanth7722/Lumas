/**
 * Tests for the shared frontend JS modules.
 * Run with: node lumas/tests/test_shared_js.js
 */

// Simulate browser globals for self-registering modules
if (typeof global.window === 'undefined') global.window = {}

const path = require('path')
const projectRoot = path.resolve(__dirname, '..', '..')

const Storage = require(path.join(projectRoot, 'lumas/frontend/shared/storage.js')).Storage
const PromptBuilder = require(path.join(projectRoot, 'lumas/frontend/shared/prompting.js')).PromptBuilder
const RetrievalService = require(path.join(projectRoot, 'lumas/frontend/shared/retrieval.js')).RetrievalService
const LocalEngine = require(path.join(projectRoot, 'lumas/frontend/shared/engine.js')).LocalEngine
const QuizService = require(path.join(projectRoot, 'lumas/frontend/shared/quiz.js')).QuizService
const ConversationService = require(path.join(projectRoot, 'lumas/frontend/shared/conversation.js')).ConversationService
const Lumas = require(path.join(projectRoot, 'lumas/frontend/shared/index.js'))

let pass = 0, fail = 0
function check(ok, msg) {
  if (ok) { pass++; console.log('  \u2713', msg) }
  else { fail++; console.log('  \u2717', msg) }
}

console.log('=== Lumas Shared JS Module Tests ===\n')

// ── 1. Module Loading ──
console.log('1. Module Loading')
check(typeof Storage === 'function', 'Storage loaded')
check(typeof PromptBuilder === 'function', 'PromptBuilder loaded')
check(typeof RetrievalService === 'function', 'RetrievalService loaded')
check(typeof LocalEngine === 'function', 'LocalEngine loaded')
check(typeof QuizService === 'function', 'QuizService loaded')
check(typeof ConversationService === 'function', 'ConversationService loaded')
check(typeof Lumas === 'object', 'Lumas namespace loaded')

// ── 2. PromptBuilder ──
console.log('\n2. PromptBuilder')
const pb = new PromptBuilder()
const msgs = pb.buildConversationPrompt('What is quantum?', ['Quantum physics is...'], [])
check(msgs.length >= 2, 'buildConversationPrompt returns ' + msgs.length + ' messages')
check(msgs.some(m => m.role === 'system'), 'System prompt present')
check(msgs.some(m => m.role === 'user' && m.content === 'What is quantum?'), 'User query present')

const quizPrompt = pb.buildQuizPrompt('Biology', 3)
check(quizPrompt.includes('3 questions'), 'Quiz prompt includes num_questions=' + quizPrompt.match(/\d+ questions/)?.[0])
check(quizPrompt.includes('correct_index'), 'Quiz prompt includes correct_index')

const stripped = PromptBuilder.stripSpecialTokens('<s>Hello <|im_end|> world')
check(stripped === 'Hello  world', 'stripSpecialTokens: "' + stripped + '"')

// Continuation prompt
const cMsgs = pb.buildContinuationPrompt(['context'], [{role:'user', content:'hi'}])
check(cMsgs.length === 3, 'buildContinuationPrompt returns ' + cMsgs.length + ' messages')

// Quiz messages
const qMsgs = pb.buildQuizMessages('content', 2)
check(qMsgs.length === 2, 'buildQuizMessages returns ' + qMsgs.length + ' messages')

// ── 3. RetrievalService ──
console.log('\n3. RetrievalService')
const mockStorage = { getAllChunks: () => Promise.resolve([]) }
const rs = new RetrievalService(mockStorage)
check(typeof rs.retrieve === 'function', 'retrieve() exists')
check(typeof rs._keywordRetrieve === 'function', '_keywordRetrieve() exists')

const chunks = [
  { id: '1', content: 'The mitochondrion is the powerhouse of the cell. It produces ATP through oxidative phosphorylation.' },
  { id: '2', content: 'Photosynthesis converts sunlight into chemical energy. Plants use chlorophyll for this process.' },
  { id: '3', content: 'Mitochondria and chloroplasts have their own DNA. They are semi-autonomous organelles.' },
]
// Note: only chunk 1 contains all query terms ('mitochondrion', 'powerhouse', 'cell')
// Chunks 2 and 3 don't match all terms, so top-k=2 returns 1 result
const scored = rs._keywordRetrieve('mitochondrion powerhouse cell', chunks, 2)
check(scored.length === 1, 'Only chunk 1 matches all query terms (got ' + scored.length + ')')
check(scored[0].id === '1', 'Most relevant chunk first (id=' + scored[0].id + ')')
check(typeof scored[0].score === 'number', 'Score is a number: ' + scored[0].score)

// Empty query returns top-k
const empty = rs._keywordRetrieve('', chunks, 2)
check(empty.length === 2, 'Empty query returns top-k=2')

// ── 4. STOP_WORDS not mutated ──
console.log('\n4. STOP_WORDS integrity')
const origSize = RetrievalService.STOP_WORDS.size
rs._keywordRetrieve('the a an is', chunks, 1)
check(RetrievalService.STOP_WORDS.size === origSize, 'STOP_WORDS size unchanged: ' + RetrievalService.STOP_WORDS.size + ' (was ' + origSize + ')')
check(RetrievalService.STOP_WORDS.has('the'), '"the" still in set')
check(RetrievalService.STOP_WORDS.has('a'), '"a" still in set')
check(RetrievalService.STOP_WORDS.has('is'), '"is" still in set')

// ── 5. LocalEngine ──
console.log('\n5. LocalEngine')
const eng = new LocalEngine()
check(typeof eng.generate === 'function', 'generate()')
check(typeof eng.generateText === 'function', 'generateText()')
check(typeof eng.healthCheck === 'function', 'healthCheck()')
check(typeof eng.generateStream === 'function', 'generateStream()')
check(eng.name === 'local (Android)', 'name: ' + eng.name)
check(eng.isOnline === false, 'isOnline: ' + eng.isOnline)

const testMsgs = [
  { role: 'system', content: 'You are Lumas.' },
  { role: 'user', content: 'Hello' },
]
const prompt = eng._messagesToPrompt(testMsgs)
check(prompt.includes('<|im_start|>'), 'Uses im_start/im_end tokens')
check(prompt.includes('assistant'), 'Ends with assistant header')
check(!prompt.includes('undefined'), 'No undefined in prompt')

// ── 6. QuizService ──
console.log('\n6. QuizService')
const qs = new QuizService({}, eng, pb)
check(typeof qs.generateQuiz === 'function', 'generateQuiz()')
check(typeof qs.answerQuestion === 'function', 'answerQuestion()')
check(typeof qs.getQuizResults === 'function', 'getQuizResults()')

// JSON parsing
const validJson = JSON.stringify({
  questions: [
    { question: 'What is ATP?', options: ['Energy', 'Protein', 'Sugar', 'Lipid'], correct_index: 0 }
  ]
})
const parsed = QuizService._parseQuizJson(validJson)
check(parsed !== null, 'Valid JSON parses')
check(parsed.length === 1, '1 question parsed')

const fenced = '```json\n' + validJson + '\n```'
const parsed2 = QuizService._parseQuizJson(fenced)
check(parsed2 !== null && parsed2.length === 1, 'Fenced JSON strips ```')

const extra = 'Some text before\n' + validJson + '\nSome text after'
const parsed3 = QuizService._parseQuizJson(extra)
check(parsed3 !== null && parsed3.length === 1, 'Extra text around JSON is handled')

const invalid = QuizService._parseQuizJson('not json at all')
check(invalid === null, 'Invalid JSON returns null')

// ── 7. ConversationService ──
console.log('\n7. ConversationService')
const cs = new ConversationService({}, eng, rs, pb)
check(typeof cs.ask === 'function', 'ask()')
check(typeof cs.preview === 'function', 'preview()')
check(typeof cs.createSession === 'function', 'createSession()')
check(typeof cs.getHistory === 'function', 'getHistory()')
check(typeof cs.listSessions === 'function', 'listSessions()')
check(typeof cs.deleteSession === 'function', 'deleteSession()')

// ── 8. Lumas namespace ──
console.log('\n8. Lumas namespace exports')
check(typeof Lumas.Storage === 'function', 'Storage')
check(typeof Lumas.PromptBuilder === 'function', 'PromptBuilder')
check(typeof Lumas.RetrievalService === 'function', 'RetrievalService')
check(typeof Lumas.LocalEngine === 'function', 'LocalEngine')
check(typeof Lumas.QuizService === 'function', 'QuizService')
check(typeof Lumas.ConversationService === 'function', 'ConversationService')

// ── Summary ──
console.log('\n=== SUMMARY: ' + pass + ' passed, ' + fail + ' failed ===')
process.exit(fail > 0 ? 1 : 0)
