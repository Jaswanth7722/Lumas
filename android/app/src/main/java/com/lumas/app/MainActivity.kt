package com.lumas.app

import android.annotation.SuppressLint
import android.os.Bundle
import android.view.ViewGroup
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import androidx.webkit.WebViewAssetLoader
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * Lumas Android Shell — starts the llama.cpp server and loads the
 * mobile frontend in a WebView.
 *
 * Architecture:
 *   1. On create, extract the GGUF model from assets to internal storage
 *   2. Start the llama.cpp HTTP server via the native JNI bridge
 *   3. Load the mobile frontend (index.html, style.css, app.js + shared JS)
 *      from app assets into a fullscreen WebView
 *   4. Expose server status + model info to the frontend via JavaScriptInterface
 *
 * The frontend handles all orchestration (sessions, chat, retrieval, quizzes)
 * using IndexedDB and calls the local llama.cpp endpoint at http://127.0.0.1:8080.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var llamaServer: LlamaServer
    private val executor = Executors.newSingleThreadExecutor()

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Initialize the llama.cpp server wrapper
        llamaServer = LlamaServer(applicationContext)

        // Start the native server in the background
        startServerAsync()

        // Set up the WebView
        webView = WebView(this)
        webView.setBackgroundColor(0xFF1B1E24.toInt())
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = false
        }

        // Expose server status to JavaScript
        webView.addJavascriptInterface(ServerBridge(), "LumasNative")

        // Serve assets from the APK via localhost-like URLs
        val assetLoader = WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()

        webView.webViewClient = object : WebViewClient() {
            override fun shouldInterceptRequest(
                view: WebView,
                request: WebResourceRequest
            ) = assetLoader.shouldInterceptRequest(request.url)

            @Suppress("DEPRECATION")
            override fun shouldInterceptRequest(view: WebView, url: String) =
                assetLoader.shouldInterceptRequest(android.net.Uri.parse(url))
        }

        setContentView(webView, ViewGroup.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT
        ))

        webView.loadUrl("https://appassets.androidplatform.net/assets/index.html")
    }

    /**
     * Start the llama.cpp server in a background thread.
     * The frontend JS will detect the server via health check.
     */
    private fun startServerAsync() {
        executor.submit {
            try {
                val port = llamaServer.start()
                if (port > 0) {
                    android.util.Log.i(TAG, "llama.cpp server started on port $port")
                    // Notify the frontend that the server is ready
                    runOnUiThread {
                        webView.evaluateJavascript(
                            "window.dispatchEvent(new CustomEvent('llamaReady', {detail: {port: $port}}))",
                            null
                        )
                    }
                } else {
                    android.util.Log.w(TAG, "llama.cpp server failed to start (model may not be bundled)")
                }
            } catch (e: Exception) {
                android.util.Log.e(TAG, "Failed to start llama.cpp server", e)
            }
        }
    }

    override fun onDestroy() {
        llamaServer.stop()
        webView.destroy()
        executor.shutdownNow()
        super.onDestroy()
    }

    /**
     * JavaScript interface exposed to the frontend as `LumasNative`.
     *
     * Provides:
     *   - serverPort: the port the llama.cpp server is on
     *   - isServerRunning(): whether the server process is alive
     *   - getConfig(): JSON config object with model info
     *   - extractFile(path): expose a file from assets (for future use)
     */
    inner class ServerBridge {
        @JavascriptInterface
        fun serverPort(): Int = llamaServer.port

        @JavascriptInterface
        fun isServerRunning(): Boolean = llamaServer.isRunning

        @JavascriptInterface
        fun isServerHealthy(): Boolean = llamaServer.healthCheck()

        @JavascriptInterface
        fun getConfig(): String {
            return JSONObject().apply {
                put("platform", "android")
                put("serverUrl", "http://127.0.0.1:${llamaServer.port}")
                put("modelPath", "lumas-model.gguf")
                put("ndkVersion", android.os.Build.VERSION.SDK_INT)
            }.toString()
        }

        @JavascriptInterface
        fun getServerUrl(): String {
            return "http://127.0.0.1:${llamaServer.port}"
        }

        @JavascriptInterface
        fun triggerHealthCheck(): Boolean {
            return llamaServer.healthCheck()
        }
    }

    companion object {
        private const val TAG = "LumasActivity"
    }
}
