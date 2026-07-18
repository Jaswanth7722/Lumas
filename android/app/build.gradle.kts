plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.lumas.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.lumas.app"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"

        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }

        externalNativeBuild {
            cmake {
                arguments("-DLLAMA_METAL=OFF", "-DLLAMA_BLAS=OFF")
                cppFlags("-std=c++17", "-O2")
            }
        }
    }

    buildFeatures {
        buildConfig = true
        prefab = true
    }

    // Assets: merge the Android frontend + the shared JS modules
    // The shared modules are copied to assets/shared/ by copySharedAssets task
    sourceSets["main"].assets.srcDirs(
        file("src/main/assets"),              // index.html
        file("../../lumas/frontend/android"), // style.css, app.js
    )

    externalNativeBuild {
        cmake {
            path = file("CMakeLists.txt")
            version = "3.22.1"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

// ── Copy shared JS modules into assets/shared/ before each build ──
// The index.html references them as shared/storage.js etc.
val copySharedAssets by tasks.registering(Copy::class) {
    from("../../lumas/frontend/shared") {
        include("*.js")
    }
    into("src/main/assets/shared")
}

// Hook into the asset merge task
tasks.whenTaskAdded {
    if (name.contains("merge") && name.contains("Assets")) {
        dependsOn(copySharedAssets)
    }
}

dependencies {
    implementation("androidx.webkit:webkit:1.12.1")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("org.jetbrains.kotlin:kotlin-stdlib:2.0.21")
}
