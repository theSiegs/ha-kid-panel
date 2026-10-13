import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// Per-install settings stay out of the repo: local.properties (or ~/.gradle/gradle.properties) supplies
//   kidpanel.server=https://your-home-assistant.example   (the address the watch reaches Home Assistant at)
//   kidpanel.keystore=/path/to/upload.jks, kidpanel.keystorePassword=..., kidpanel.keyAlias=..., kidpanel.keyPassword=...
val local = Properties().apply {
    val file = rootProject.file("local.properties")
    if (file.exists()) file.inputStream().use { load(it) }
}
fun setting(name: String): String? = (providers.gradleProperty(name).orNull ?: local.getProperty(name))?.trim()

val server = setting("kidpanel.server")?.trimEnd('/') ?: ""

android {
    namespace = "io.github.thesiegs.kidpanel"
    compileSdk = 35

    defaultConfig {
        applicationId = "io.github.thesiegs.kidpanel"
        minSdk = 30
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String", "SERVER", "\"$server\"")
    }

    signingConfigs {
        val keystore = setting("kidpanel.keystore")
        if (keystore != null) {
            create("upload") {
                storeFile = file(keystore)
                storePassword = setting("kidpanel.keystorePassword")
                keyAlias = setting("kidpanel.keyAlias")
                keyPassword = setting("kidpanel.keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.findByName("upload")
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
    kotlinOptions {
        jvmTarget = "17"
    }
}

tasks.register("checkServer") {
    doLast {
        require(server.startsWith("https://")) {
            "Set kidpanel.server=https://... in wear/local.properties: the address the watch reaches Home Assistant at"
        }
    }
}
tasks.matching { it.name.startsWith("bundleRelease") || it.name.startsWith("assembleRelease") }
    .configureEach { dependsOn("checkServer") }

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2025.04.01")
    implementation(composeBom)
    implementation("androidx.core:core-ktx:1.16.0")
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.9.0")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.wear.compose:compose-material:1.4.1")
    implementation("androidx.wear.compose:compose-foundation:1.4.1")
    implementation("androidx.wear:wear-input:1.2.0")
    implementation("androidx.wear.tiles:tiles:1.5.0")
    implementation("androidx.wear.protolayout:protolayout:1.3.0")
    implementation("androidx.wear.protolayout:protolayout-material:1.3.0")
    implementation("androidx.concurrent:concurrent-futures-ktx:1.2.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
