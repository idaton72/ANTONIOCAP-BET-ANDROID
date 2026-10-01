plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "it.antoniocap.bet"
    compileSdk = 35

    defaultConfig {
        applicationId = "it.antoniocap.bet"
        minSdk = 26
        targetSdk = 35
        versionCode = 7
        versionName = "0.7"
    }
}
