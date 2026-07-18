package com.lumas.app;

import android.app.AlertDialog;
import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.os.Bundle;
import android.view.Menu;
import android.view.MenuItem;
import android.view.ViewGroup;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;

import androidx.annotation.NonNull;
import androidx.webkit.WebViewAssetLoader;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/**
 * Native Android shell for the shared Lumas text tutor.
 *
 * The WebView uses the exact same HTML/CSS/JS as the desktop web client.
 * Connected mode points at the FastAPI API. Local mode talks to a llama.cpp
 * OpenAI-compatible HTTP server and keeps the current learner context on the
 * device. The connection can be changed from the Android overflow menu.
 */
public final class MainActivity extends Activity {
    private static final String PREFS = "lumas_android";
    private static final String KEY_MODE = "mode";
    private static final String KEY_API_BASE = "api_base";
    private static final String KEY_LOCAL_URL = "local_url";
    private static final String KEY_HISTORY = "local_history";
    private static final String DEFAULT_API_BASE = "http://10.0.2.2:8765/api";
    private static final String DEFAULT_LOCAL_URL = "http://127.0.0.1:8080/v1/chat/completions";

    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private final List<JSONObject> localHistory = new ArrayList<>();
    private SharedPreferences preferences;
    private WebView webView;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        preferences = getSharedPreferences(PREFS, MODE_PRIVATE);
        loadLocalHistory();

        webView = new WebView(this);
        webView.setBackgroundColor(Color.WHITE);
        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        webView.getSettings().setAllowFileAccess(false);
        webView.getSettings().setAllowContentAccess(false);
        webView.addJavascriptInterface(new AndroidConfig(), "AndroidConfig");

        WebViewAssetLoader assetLoader = new WebViewAssetLoader.Builder()
                .addPathHandler("/assets/", new WebViewAssetLoader.AssetsPathHandler(this))
                .build();
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                return assetLoader.shouldInterceptRequest(request.getUrl());
            }

            @SuppressWarnings("deprecation")
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, String url) {
                return assetLoader.shouldInterceptRequest(android.net.Uri.parse(url));
            }
        });

        setContentView(webView, new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));
        webView.loadUrl("https://appassets.androidplatform.net/assets/index.html");
    }

    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        menu.add("Connection settings").setShowAsAction(MenuItem.SHOW_AS_ACTION_NEVER);
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(@NonNull MenuItem item) {
        if ("Connection settings".contentEquals(item.getTitle())) {
            showConnectionSettings();
            return true;
        }
        return super.onOptionsItemSelected(item);
    }

    private void showConnectionSettings() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        int padding = (int) (24 * getResources().getDisplayMetrics().density);
        layout.setPadding(padding, 0, padding, 0);

        RadioGroup modes = new RadioGroup(this);
        RadioButton apiMode = new RadioButton(this);
        apiMode.setText("Connected Lumas API");
        apiMode.setId(1);
        RadioButton localMode = new RadioButton(this);
        localMode.setText("Offline llama.cpp server");
        localMode.setId(2);
        modes.addView(apiMode);
        modes.addView(localMode);
        modes.check(isLocalMode() ? 2 : 1);
        layout.addView(modes);

        EditText api = new EditText(this);
        api.setHint("Lumas API base URL");
        api.setSingleLine(true);
        api.setText(apiBase());
        layout.addView(api);

        EditText local = new EditText(this);
        local.setHint("llama.cpp /v1/chat/completions URL");
        local.setSingleLine(true);
        local.setText(localEngineUrl());
        layout.addView(local);

        new AlertDialog.Builder(this)
                .setTitle("Lumas connection")
                .setView(layout)
                .setPositiveButton("Save", (dialog, which) -> {
                    preferences.edit()
                            .putString(KEY_MODE, modes.getCheckedRadioButtonId() == 2 ? "local" : "api")
                            .putString(KEY_API_BASE, api.getText().toString().trim())
                            .putString(KEY_LOCAL_URL, local.getText().toString().trim())
                            .apply();
                    localHistory.clear();
                    saveLocalHistory();
                    webView.reload();
                })
                .setNegativeButton("Cancel", null)
                .show();
    }

    private boolean isLocalMode() {
        return "local".equals(preferences.getString(KEY_MODE, "api"));
    }

    private String apiBase() {
        return preferences.getString(KEY_API_BASE, DEFAULT_API_BASE);
    }

    private String localEngineUrl() {
        return preferences.getString(KEY_LOCAL_URL, DEFAULT_LOCAL_URL);
    }

    private void loadLocalHistory() {
        String encoded = preferences.getString(KEY_HISTORY, "[]");
        try {
            JSONArray values = new JSONArray(encoded);
            for (int i = 0; i < values.length(); i++) {
                localHistory.add(values.getJSONObject(i));
            }
        } catch (JSONException ignored) {
            localHistory.clear();
        }
    }

    private void saveLocalHistory() {
        JSONArray values = new JSONArray();
        for (JSONObject message : localHistory) values.put(message);
        preferences.edit().putString(KEY_HISTORY, values.toString()).apply();
    }

    private String requestLocalChat(String prompt) throws Exception {
        JSONObject user = new JSONObject().put("role", "user").put("content", prompt);
        localHistory.add(user);

        JSONObject body = new JSONObject();
        body.put("model", "local");
        JSONArray messages = new JSONArray();
        messages.put(new JSONObject()
                .put("role", "system")
                .put("content", "You are Lumas, a patient offline study tutor. Explain clearly and encourage reasoning."));
        for (JSONObject message : localHistory) messages.put(message);
        body.put("messages", messages);
        body.put("temperature", 0.7);
        body.put("stream", false);

        HttpURLConnection connection = (HttpURLConnection) new URL(localEngineUrl()).openConnection();
        connection.setRequestMethod("POST");
        connection.setConnectTimeout(5000);
        connection.setReadTimeout(120000);
        connection.setRequestProperty("Content-Type", "application/json");
        connection.setDoOutput(true);
        try (OutputStream output = connection.getOutputStream()) {
            output.write(body.toString().getBytes(StandardCharsets.UTF_8));
        }

        int status = connection.getResponseCode();
        InputStream stream = status >= 200 && status < 300
                ? connection.getInputStream() : connection.getErrorStream();
        String response = read(stream);
        if (status < 200 || status >= 300) {
            localHistory.remove(localHistory.size() - 1);
            throw new IOException("llama.cpp returned HTTP " + status + ": " + response);
        }

        JSONObject json = new JSONObject(response);
        JSONArray choices = json.optJSONArray("choices");
        JSONObject message = choices == null || choices.length() == 0
                ? null : choices.getJSONObject(0).optJSONObject("message");
        String text = message == null ? "" : message.optString("content", "");
        if (text.isEmpty()) {
            localHistory.remove(localHistory.size() - 1);
            throw new IOException("llama.cpp returned no message");
        }
        localHistory.add(new JSONObject().put("role", "assistant").put("content", text));
        saveLocalHistory();
        return new JSONObject().put("ok", true).put("response", text).toString();
    }

    private static String read(InputStream input) throws IOException {
        if (input == null) return "";
        StringBuilder result = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(input, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) result.append(line);
        }
        return result.toString();
    }

    @Override
    protected void onDestroy() {
        if (webView != null) webView.destroy();
        network.shutdownNow();
        super.onDestroy();
    }

    public final class AndroidConfig {
        @JavascriptInterface
        public boolean isLocalMode() {
            return MainActivity.this.isLocalMode();
        }

        @JavascriptInterface
        public String apiBase() {
            return MainActivity.this.apiBase();
        }

        @JavascriptInterface
        public String chat(String prompt) {
            try {
                return network.submit(() -> requestLocalChat(prompt)).get(130, TimeUnit.SECONDS);
            } catch (Exception error) {
                String message = error.getMessage() == null ? "Local tutor request failed" : error.getMessage();
                try {
                    return new JSONObject().put("ok", false).put("error", message).toString();
                } catch (JSONException ignored) {
                    return "{\"ok\":false,\"error\":\"Local tutor request failed\"}";
                }
            }
        }
    }
}
