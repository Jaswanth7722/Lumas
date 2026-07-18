/**
 * Lumas Shared Frontend Modules
 *
 * These modules are the JS equivalent of the Python desktop backend,
 * designed to run inside the Android WebView calling the local llama.cpp
 * HTTP endpoint on the device.
 *
 * Usage (browser - script tags):
 *   <script src="shared/storage.js"></script>
 *   <script src="shared/prompting.js"></script>
 *   <script src="shared/retrieval.js"></script>
 *   <script src="shared/engine.js"></script>
 *   <script src="shared/quiz.js"></script>
 *   <script src="shared/index.js"></script>
 *   <script>
 *     const { storage, engine, ... } = Lumas
 *   </script>
 *
 * Usage (Node.js):
 *   const { Storage, PromptBuilder, ... } = require('./shared/index.js')
 */

// Create the Lumas namespace
const Lumas = {
  Storage: (typeof module !== 'undefined' && module.exports)
    ? require('./storage.js').Storage
    : window.Storage,
  PromptBuilder: (typeof module !== 'undefined' && module.exports)
    ? require('./prompting.js').PromptBuilder
    : window.PromptBuilder,
  RetrievalService: (typeof module !== 'undefined' && module.exports)
    ? require('./retrieval.js').RetrievalService
    : window.RetrievalService,
  LocalEngine: (typeof module !== 'undefined' && module.exports)
    ? require('./engine.js').LocalEngine
    : window.LocalEngine,
  QuizService: (typeof module !== 'undefined' && module.exports)
    ? require('./quiz.js').QuizService
    : window.QuizService,
  ConversationService: (typeof module !== 'undefined' && module.exports)
    ? require('./conversation.js').ConversationService
    : window.ConversationService,
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
  module.exports = Lumas
} else if (typeof window !== 'undefined') {
  window.Lumas = Lumas
}
