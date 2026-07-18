# Lumas Android

Native Android shell that starts a llama.cpp HTTP server via NDK and loads
the mobile-optimized frontend in a WebView. Everything runs on-device.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  MainActivity.kt                │
│  ┌──────────────┐         ┌─────────────────┐  │
│  │ LlamaServer  │  JNI →  │  llamaserver.cpp │  │
│  │   (Kotlin)   │         │   (Native/C++)   │  │
│  └──────┬───────┘         └────────┬─────────┘  │
│         │                          │             │
│         ▼                          ▼             │
│  ┌───────────────────────────────────────────┐   │
│  │            WebView                        │   │
│  │  ┌─────────────────────────────────────┐  │   │
│  │  │  index.html + style.css + app.js    │  │   │
│  │  │  shared/storage.js                  │  │   │
│  │  │  shared/prompting.js                │  │   │
│  │  │  shared/retrieval.js                │  │   │
│  │  │  shared/engine.js  → localhost:8080──┼──┼──→ llama.cpp
│  │  │  shared/quiz.js                     │  │   │
│  │  │  shared/conversation.js             │  │   │
│  │  └─────────────────────────────────────┘  │   │
│  └───────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

- **LlamaServer.kt** — Kotlin JNI wrapper. Extracts the GGUF model from app
  assets to internal storage, then calls the native library to start the
  HTTP server on a background thread.
- **llamaserver.cpp** — JNI C++ code. Loads the model via llama.cpp, starts
  the built-in HTTP server on port 8080. Runs in a detached pthread.
- **index.html** — Mobile-optimized frontend with bottom tab navigation.
- **shared/*.js** — Copied from `lumas/frontend/shared/` during build.
  These modules handle all orchestration: storage (IndexedDB), retrieval
  (keyword), prompting, engine calling, quiz generation.

## Prerequisites

- Android Studio Hedgehog (2023.1.1) or later
- Android SDK 35, NDK 26+
- Kotlin plugin 2.0.21
- Windows: PowerShel 7+ for the setup script

## Setup

```powershell
# 1. Run the setup script (downloads llama.cpp source + model)
cd android
.\setup.ps1 -ModelUrl <optional-url-to-gguf-model>

# 2. Open the android/ directory in Android Studio
# 3. Let Gradle sync (File > Sync Project with Gradle Files)
# 4. Select an arm64-v8a emulator or device
# 5. Run the 'app' configuration
```

The first NDK build takes several minutes because it compiles llama.cpp
from source. Subsequent builds are incremental.

## Bundling a GGUF Model

Place your fine-tuned GGUF model (e.g., Gemma 3 270M int4 quant) at:

```
android/app/src/main/assets/lumas-model.gguf
```

Or use the setup script:
```powershell
.\setup.ps1 -ModelUrl https://huggingface.co/your-org/your-model/resolve/main/model.gguf
```

Without a bundled model, the app attempts to start the local server but
will gracefully fail. The frontend shows a "Server offline" status and
can still function in a read-only / demo mode.

## Development

### Frontend changes

The mobile frontend lives in `lumas/frontend/android/`. Edit the HTML/CSS/JS
there and reload the app to see changes (the Gradle `copySharedAssets` task
copies the JS modules automatically).

### Native C++ changes

Edit `app/src/main/jni/llamaserver.cpp`. The NDK build recompiles
automatically on the next run.

### Without a model (fallback behavior)

If no GGUF model is bundled, the `LumasNative.getServerUrl()` JavaScript
interface returns `http://127.0.0.1:8080` but `isServerHealthy()` returns
`false`. The frontend's Settings screen shows "Offline ✗" and the chat
input is disabled with a message to check the server.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `UnsatisfiedLinkError` | llama.cpp source not cloned. Run `setup.ps1` |
| WebView shows blank page | Asset path issue. Check `assets/` in APK |
| Model fails to load | GGUF not found or wrong architecture |
| Slow first build | NDK compiling llama.cpp — this is expected |
