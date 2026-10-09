plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val captureEnabled = (project.findProperty("dac.captureEnabled") as String?)?.toBoolean() ?: false

android {
    namespace = "ai.detectaclip.lab"
    compileSdk = 37

    defaultConfig {
        applicationId = "ai.detectaclip.lab"
        minSdk = 34          // app-window sharing research starts at Android 14 (S02)
        targetSdk = 37
        versionCode = 1
        versionName = "0.1.0-lab"
        buildConfigField("boolean", "CAPTURE_ENABLED", captureEnabled.toString())
        buildConfigField("String", "BUILD_PURPOSE", "\"LAB\"")
    }
    buildFeatures { buildConfig = true }
    buildTypes {
        release { isMinifyEnabled = false }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    testOptions { unitTests.isReturnDefaultValues = true }
}

// No analytics, crash, logging or networking dependency (CTRL-G00 step 1).
dependencies {
    testImplementation("junit:junit:4.13.2")
}
