import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
    id("io.github.takahirom.roborazzi")
}

// ---------------------------------------------------------------------------
// Build-time configuration. Nothing of this is editable in the app UI.
//   FONAR_BACKEND_URL    https://your-server   (baked into BuildConfig.BACKEND_URL)
//   FONAR_KEYSTORE_PATH / FONAR_KEYSTORE_PASSWORD / FONAR_KEY_ALIAS / FONAR_KEY_PASSWORD
//   FONAR_VERSION_CODE / FONAR_VERSION_NAME
// They can also be given as -P gradle properties or in android/keystore.properties
// (git-ignored). The signing key itself must live outside the repository.
// ---------------------------------------------------------------------------
val localProps = Properties().apply {
    val f = rootProject.file("keystore.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}

fun cfg(name: String): String? =
    (project.findProperty(name) as String?)?.takeIf { it.isNotBlank() }
        ?: System.getenv(name)?.takeIf { it.isNotBlank() }
        ?: localProps.getProperty(name)?.takeIf { it.isNotBlank() }

val backendUrl = (cfg("FONAR_BACKEND_URL") ?: "http://10.0.2.2:8000").trimEnd('/')
val keystorePath = cfg("FONAR_KEYSTORE_PATH")

val robolectricRuntime: Configuration by configurations.creating
val robolectricDir = layout.buildDirectory.dir("robolectric-jars")
val robolectricJars = tasks.register<Copy>("robolectricJars") {
    onlyIf { robolectricDir.get().asFile.listFiles().isNullOrEmpty() }
    from(robolectricRuntime)
    into(robolectricDir)
}

android {
    namespace = "app.fonar"
    compileSdk = 36

    defaultConfig {
        applicationId = "app.fonar"
        minSdk = 26
        targetSdk = 36
        versionCode = (cfg("FONAR_VERSION_CODE") ?: "1").toInt()
        versionName = cfg("FONAR_VERSION_NAME") ?: "1.0.0"
        buildConfigField("String", "BACKEND_URL", "\"$backendUrl\"")
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    signingConfigs {
        if (keystorePath != null) {
            create("release") {
                storeFile = file(keystorePath)
                storePassword = cfg("FONAR_KEYSTORE_PASSWORD")
                keyAlias = cfg("FONAR_KEY_ALIAS") ?: "fonar"
                keyPassword = cfg("FONAR_KEY_PASSWORD") ?: cfg("FONAR_KEYSTORE_PASSWORD")
                enableV1Signing = true
                enableV2Signing = true
                enableV3Signing = true
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            if (keystorePath != null) signingConfig = signingConfigs.getByName("release")
        }
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
        // Minified like release (R8), but may talk to a test backend on the emulator host.
        // Used only by the emulator end-to-end workflow.
        create("e2e") {
            initWith(getByName("release"))
            applicationIdSuffix = ".e2e"
            versionNameSuffix = "-e2e"
            signingConfig = signingConfigs.getByName("debug")
            matchingFallbacks += listOf("release")
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        unitTests {
            isIncludeAndroidResources = true
            all { test ->
                test.systemProperty("fonar.backend", System.getenv("FONAR_TEST_BACKEND") ?: "")
                test.maxHeapSize = "3g"
                // Robolectric's own downloader ignores proxies; let Gradle fetch the Android jar instead.
                test.dependsOn(robolectricJars)
                test.systemProperty("robolectric.offline", "true")
                test.systemProperty("robolectric.logging", "stdout")
                test.systemProperty("robolectric.dependency.dir", robolectricDir.get().asFile.absolutePath)
            }
        }
    }

    packaging {
        resources.excludes += setOf("/META-INF/{AL2.0,LGPL2.1}", "/META-INF/*.kotlin_module", "DebugProbesKt.bin")
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

// A release build must point at a real HTTPS backend.
gradle.taskGraph.whenReady {
    if (allTasks.any { it.name.contains("Release") && (it.name.startsWith("assemble") || it.name.startsWith("bundle")) }) {
        require(backendUrl.startsWith("https://")) {
            "Release build needs FONAR_BACKEND_URL=https://... (got $backendUrl)"
        }
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2025.10.01")
    implementation(composeBom)
    implementation("androidx.core:core-ktx:1.17.0")
    implementation("androidx.activity:activity-compose:1.11.0")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.navigation:navigation-compose:2.9.5")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.9.4")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.9.4")
    implementation("androidx.lifecycle:lifecycle-process:2.9.4")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.9.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("androidx.exifinterface:exifinterface:1.4.1")
    implementation("io.coil-kt.coil3:coil-compose:3.3.0")
    implementation("io.coil-kt.coil3:coil-network-okhttp:3.3.0")
    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")

    robolectricRuntime("org.robolectric:android-all-instrumented:15-robolectric-13954326-i7") { isTransitive = false }
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.robolectric:robolectric:4.16")
    testImplementation("androidx.test:core:1.7.0")
    testImplementation("androidx.test.ext:junit:1.3.0")
    testImplementation(composeBom)
    testImplementation("androidx.compose.ui:ui-test-junit4")
    testImplementation("io.github.takahirom.roborazzi:roborazzi:1.50.0")
    testImplementation("io.github.takahirom.roborazzi:roborazzi-compose:1.50.0")
    testImplementation("io.github.takahirom.roborazzi:roborazzi-junit-rule:1.50.0")
}
