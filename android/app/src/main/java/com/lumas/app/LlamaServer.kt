package com.lumas.app

import android.content.Context
import android.util.Log
import java.io.File
import java.io.FileOutputStream

/**
 * Kotlin wrapper around the llama.cpp native server JNI bridge.
 *
 * Responsibilities:
 *   1. Copy the bundled GGUF model from assets to internal storage
 *   2. Start the native llama.cpp HTTP server on a background thread
 *   3. Provide health-check and shutdown
 */
class LlamaServer(private val context: Context) {

    companion object {
        private const val TAG = "LlamaServer"
        private const val MODEL_FILENAME = "lumas-model.gguf"
        private const val SERVER_PORT = 8080
        private const val MODEL_DIR = "models"
    }

    private var modelPath: String? = null

    /**
     * Extract the GGUF model from app assets to internal storage.
     * Returns the absolute path to the extracted model file.
     */
    private fun extractModel(): String {
        val modelDir = File(context.filesDir, MODEL_DIR)
        modelDir.mkdirs()

        val modelFile = File(modelDir, MODEL_FILENAME)
        if (modelFile.exists() && modelFile.length() > 0) {
            Log.i(TAG, "Model already extracted: ${modelFile.absolutePath}")
            return modelFile.absolutePath
        }

        Log.i(TAG, "Extracting model from assets...")
        try {
            context.assets.open(MODEL_FILENAME).use { input ->
                FileOutputStream(modelFile).use { output ->
                    input.copyTo(output)
                }
            }
            Log.i(TAG, "Model extracted: ${modelFile.absolutePath} (${modelFile.length()} bytes)")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to extract model from assets", e)
            // Model may not be bundled yet — that's OK for development
            // The app will fall back to connected API mode
            throw e
        }

        return modelFile.absolutePath
    }

    /**
     * Start the llama.cpp HTTP server.
     * Extracts the model first, then calls the native JNI function.
     * Returns the port the server is listening on, or -1 on failure.
     */
    fun start(): Int {
        return try {
            val path = extractModel()
            modelPath = path

            val success = nativeStartServer(path)
            if (success) {
                Log.i(TAG, "Server started on port $SERVER_PORT")
                SERVER_PORT
            } else {
                Log.e(TAG, "Failed to start native server")
                -1
            }
        } catch (e: Exception) {
            Log.e(TAG, "Server start failed", e)
            -1
        }
    }

    /**
     * Signal the native server to stop.
     */
    fun stop() {
        Log.i(TAG, "Stopping server...")
        nativeStopServer()
    }

    /**
     * Check if the native server is currently running.
     */
    val isRunning: Boolean
        get() = nativeIsRunning()

    /**
     * Get the port the server is listening on.
     */
    val port: Int
        get() = nativeGetPort()

    /**
     * Health check: ping the HTTP server to confirm it's responding.
     */
    fun healthCheck(): Boolean {
        if (!isRunning) return false
        return try {
            val url = java.net.URL("http://127.0.0.1:$SERVER_PORT/health")
            val conn = url.openConnection() as java.net.HttpURLConnection
            conn.connectTimeout = 3000
            conn.readTimeout = 3000
            val ok = conn.responseCode == 200
            conn.disconnect()
            ok
        } catch (e: Exception) {
            false
        }
    }

    // ── Native JNI methods ───────────────────────────────────

    private external fun nativeStartServer(modelPath: String): Boolean
    private external fun nativeStopServer()
    private external fun nativeIsRunning(): Boolean
    private external fun nativeGetPort(): Int

    init {
        try {
            System.loadLibrary("lumas_server")
            Log.i(TAG, "Native library loaded")
        } catch (e: UnsatisfiedLinkError) {
            Log.w(TAG, "Native library not available. Run setup.ps1 first.", e)
        }
    }
}
