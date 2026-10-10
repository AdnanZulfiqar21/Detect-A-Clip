plugins {
    id("com.android.application")   // AGP 9 compiles Kotlin sources itself (built-in Kotlin)
}

val captureEnabled = (project.findProperty("dac.captureEnabled") as String?)?.toBoolean() ?: false
// CAP-A03: "user_choice" (API 34 picker) or "app_only" (API 37+: display source disabled).
val sourceMode = (project.findProperty("dac.sourceMode") as String?) ?: "user_choice"
require(sourceMode == "user_choice" || sourceMode == "app_only") { "dac.sourceMode must be user_choice or app_only" }

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
        buildConfigField("String", "SOURCE_MODE", "\"$sourceMode\"")
    }
    buildFeatures { buildConfig = true }
    buildTypes {
        release { isMinifyEnabled = false }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    testOptions { unitTests.isReturnDefaultValues = true }
}

// No analytics, crash, logging or networking dependency (CTRL-G00 step 1).
dependencies {
    testImplementation("junit:junit:4.13.2")
}
