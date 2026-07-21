# Future Android architecture

Android will reuse the Lumas text-first experience through a WebView. The
future runtime boundary is:

```text
WebView
  ↓
Local Runtime
  ↓
llama.cpp
  ↓
Gemma 3 1B
```

## Planned responsibilities

- **WebView:** host the shared tutor interface and render text responses.
- **Local Runtime:** own Android lifecycle, local learner state, model
  configuration, and the bridge between the WebView and native inference.
- **llama.cpp:** provide the device-local inference process or library.
- **Gemma 3 1B:** the first supported on-device teaching model.

## Future package placeholder

The `placeholder/com/lumas/` directories reserve the Android package
boundaries without shipping source code. Future work may add a native shell,
runtime adapter, and model packaging only after the desktop MVP is stable.

## Explicit non-goals for this submission

- No Gradle or Android Studio project
- No NDK, JNI, C/C++, Kotlin, or Java implementation
- No APK or Android CI
- No Android-specific product behavior
