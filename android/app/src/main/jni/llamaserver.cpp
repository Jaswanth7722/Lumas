/**
 * llamaserver.cpp — JNI bridge to start/stop the llama.cpp HTTP server.
 *
 * This native library is loaded by LlamaServer.kt at app startup.
 * It starts the llama.cpp built-in HTTP server on a background thread,
 * listening on http://127.0.0.1:8080 with the bundled GGUF model.
 *
 * Compile target: arm64-v8a / x86_64 via NDK + CMake.
 */

#include <jni.h>
#include <android/log.h>
#include <pthread.h>
#include <atomic>
#include <cstring>
#include <string>

#define LOG_TAG "LumasLlama"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

// ── Forward declarations of llama.cpp server functions ──
// These are linked from the llama.cpp static library.
// The full llama.cpp server is header-heavy; we expose only
// what the JNI bridge needs.

extern "C" {
    // Initialize the llama context from a model path.
    // Returns a pointer handle (opaque).
    void* llama_init_from_file(const char* model_path, int n_ctx);

    // Free the model context.
    void llama_free(void* ctx);

    // Start the HTTP server on the given port with the loaded model.
    // Returns 0 on success, non-zero on failure.
    // This function blocks until the server stops.
    int server_start(void* ctx, int port);
}

// ── Global state ─────────────────────────────────────────
static pthread_t g_server_thread = 0;
static std::atomic<bool> g_server_running{false};
static std::atomic<bool> g_server_should_stop{false};

/**
 * Server thread function.
 * Loads the model, starts the HTTP server, blocks until shutdown.
 */
static void* server_thread_func(void* arg) {
    const char* model_path = static_cast<const char*>(arg);
    if (!model_path) {
        LOGE("No model path provided to server thread");
        g_server_running = false;
        return nullptr;
    }

    LOGI("Loading model from: %s", model_path);

    // Initialize the llama model
    void* ctx = llama_init_from_file(model_path, 2048);
    if (!ctx) {
        LOGE("Failed to load model: %s", model_path);
        g_server_running = false;
        return nullptr;
    }

    LOGI("Model loaded successfully. Starting HTTP server on port 8080...");

    // Start the HTTP server (blocks until stopped)
    g_server_running = true;
    int result = server_start(ctx, 8080);

    if (result != 0) {
        LOGE("Server exited with code %d", result);
    }

    // Cleanup
    llama_free(ctx);
    g_server_running = false;
    g_server_should_stop = false;

    LOGI("Server stopped");
    return nullptr;
}

// ── JNI Functions ────────────────────────────────────────

extern "C" JNIEXPORT jboolean JNICALL
Java_com_lumas_app_LlamaServer_nativeStartServer(
    JNIEnv* env,
    jobject /*thiz*/,
    jstring model_path_jstr)
{
    if (g_server_running.load()) {
        LOGI("Server already running");
        return JNI_TRUE;
    }

    const char* model_path = env->GetStringUTFChars(model_path_jstr, nullptr);
    if (!model_path) {
        LOGE("Failed to get model path string");
        return JNI_FALSE;
    }

    // Copy the path since the JNI string handle is temporary
    char* model_path_copy = strdup(model_path);
    env->ReleaseStringUTFChars(model_path_jstr, model_path);

    g_server_should_stop = false;

    if (pthread_create(&g_server_thread, nullptr, server_thread_func, model_path_copy) != 0) {
        LOGE("Failed to create server thread");
        free(model_path_copy);
        return JNI_FALSE;
    }

    // Detach thread so it cleans up automatically
    pthread_detach(g_server_thread);

    LOGI("Server thread started");
    return JNI_TRUE;
}

extern "C" JNIEXPORT void JNICALL
Java_com_lumas_app_LlamaServer_nativeStopServer(
    JNIEnv* /*env*/,
    jobject /*thiz*/)
{
    if (!g_server_running.load()) {
        LOGI("Server not running, nothing to stop");
        return;
    }

    LOGI("Signaling server to stop...");
    g_server_should_stop = true;
    g_server_running = false;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_lumas_app_LlamaServer_nativeIsRunning(
    JNIEnv* /*env*/,
    jobject /*thiz*/)
{
    return g_server_running.load() ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jint JNICALL
Java_com_lumas_app_LlamaServer_nativeGetPort(
    JNIEnv* /*env*/,
    jobject /*thiz*/)
{
    return 8080;
}
