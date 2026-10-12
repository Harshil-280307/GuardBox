plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.google.services)
}

android {
    namespace = "com.veronic.guardbox"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.veronic.guardbox"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables {
            useSupportLibrary = true
        }

        // Customer Build-Time Configurable Properties (Phase 6.1)
        val customDeviceId = (project.findProperty("customDeviceId") as? String)
            ?: "guardbox-shop-f20424b4"
        val customDbUrl = (project.findProperty("customDbUrl") as? String)
            ?: "https://guardbox-jewelleryshop-default-rtdb.firebaseio.com"
        val customLocalUrl = (project.findProperty("customLocalUrl") as? String)
            ?: "http://192.168.31.188:8000/"
        val customRemoteUrl = (project.findProperty("customRemoteUrl") as? String)
            ?: "https://guardbox-tunnel.example.com/"

        buildConfigField("String", "DEFAULT_TARGET_DEVICE_ID", "\"$customDeviceId\"")
        buildConfigField("String", "FIREBASE_DATABASE_URL", "\"$customDbUrl\"")
        buildConfigField("String", "DEFAULT_LOCAL_URL", "\"$customLocalUrl\"")
        buildConfigField("String", "DEFAULT_REMOTE_URL", "\"$customRemoteUrl\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.activity.compose)
    
    // Compose
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    implementation(libs.androidx.material.icons.extended)
    implementation(libs.androidx.navigation.compose)
    
    // Networking
    implementation(libs.retrofit)
    implementation(libs.retrofit.converter.gson)
    implementation(libs.okhttp)
    implementation(libs.okhttp.logging)
    
    // Coroutines
    implementation(libs.kotlinx.coroutines.android)
    
    // Firebase (Auth, RTDB, FCM, Analytics)
    implementation(platform(libs.firebase.bom))
    implementation(libs.firebase.messaging)
    implementation(libs.firebase.auth)
    implementation(libs.firebase.database)
    
    // Images & Data
    implementation(libs.coil.compose)
    implementation(libs.androidx.datastore.preferences)

    debugImplementation(libs.androidx.ui.tooling)
}
