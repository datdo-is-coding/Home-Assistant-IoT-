plugins {
    id("com.android.application")
    id("com.google.gms.google-services")

    id("dev.flutter.flutter-gradle-plugin")
}

import java.io.FileInputStream
import java.util.Properties

val keystorePropertiesFile = rootProject.file("key.properties")
val keystoreProperties = Properties()
val hasKeystore = keystorePropertiesFile.exists()
if (hasKeystore) {
    keystoreProperties.load(FileInputStream(keystorePropertiesFile))
}

android {
    namespace = "com.homecompetition.app"
    compileSdk = 36

    compileOptions {
        isCoreLibraryDesugaringEnabled = true
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {

        applicationId = "com.dtv.homeassistant.dtv_home_assistant"

        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (hasKeystore) {
            create("release") {
                keyAlias = keystoreProperties.getProperty("keyAlias") ?: System.getenv("KEY_ALIAS")
                keyPassword = keystoreProperties.getProperty("keyPassword") ?: System.getenv("KEY_PASSWORD")
                storeFile = (keystoreProperties.getProperty("storeFile") ?: System.getenv("STORE_FILE"))?.let { file(it) }
                storePassword = keystoreProperties.getProperty("storePassword") ?: System.getenv("STORE_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            if (hasKeystore && signingConfigs.findByName("release") != null) {
                signingConfig = signingConfigs.getByName("release")
            } else {
                logger.warn("⚠️ WARNING: key.properties not found! Falling back to debug signing configuration for release build.")
                signingConfig = signingConfigs.getByName("debug")
            }
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}

dependencies {
    implementation("com.github.espressif:esp-idf-provisioning-android:lib-2.4.4")
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")
}
