# ═══════════════════════════════════════════════════════════
# Lumas Android - llama.cpp NDK Build
# ═══════════════════════════════════════════════════════════
#
# Builds the llama.cpp server as a shared library (.so) linked
# via JNI so the Kotlin app can start/stop it programmatically.
#
# Prerequisites:
#   1. Run setup.ps1 to download llama.cpp source to ../../llamacpp/
#   2. The GGUF model file is bundled as an app asset
#
# Requirements:
#   - Android NDK 26+
#   - CMake 3.22+
#
# Supported ABIs:
#   - arm64-v8a  (most modern Android devices)
#   - x86_64     (emulator)
# ═══════════════════════════════════════════════════════════

cmake_minimum_required(VERSION 3.22)
project(lumas_llama LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ── llama.cpp source path ─────────────────────────────────
# The setup.ps1 script clones llama.cpp into ../../llamacpp/
# Relative to app/CMakeLists.txt, that's:
set(LLAMACPP_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../llamacpp")

# ── Build llama.cpp as a static library ───────────────────
# Only build the core library + server, skip examples/tests
if(EXISTS "${LLAMACPP_DIR}/ggml.c")
    add_subdirectory(${LLAMACPP_DIR} llamacpp_build EXCLUDE_FROM_ALL)

    # Only build common and server targets
    set_target_properties(llama PROPERTIES EXCLUDE_FROM_ALL ON)
else()
    message(WARNING "llama.cpp source not found at ${LLAMACPP_DIR}. "
                    "Run setup.ps1 first or build will fail.")
endif()

# ── JNI Bridge shared library ─────────────────────────────
add_library(lumas_server SHARED
    src/main/jni/llamaserver.cpp
)

target_include_directories(lumas_server PRIVATE
    ${LLAMACPP_DIR}
    ${LLAMACPP_DIR}/common
    ${LLAMACPP_DIR}/ggml/include
)

if(EXISTS "${LLAMACPP_DIR}/ggml.c")
    target_link_libraries(lumas_server PRIVATE
        llama
        common
        ggml
        log
        jnigraphics
        android
    )
endif()

# ── Compiler flags ────────────────────────────────────────
target_compile_options(lumas_server PRIVATE
    -O2
    -fPIC
    -flto
)

# ── Output ────────────────────────────────────────────────
# The library is named liblumas_server.so and will be placed
# in jniLibs/<abi>/ by the Android Gradle plugin.
