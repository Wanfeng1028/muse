pluginManagement {
    repositories {
        mavenCentral()
        google()
        gradlePluginPortal()
    }
    plugins {
        kotlin("multiplatform") version "2.2.10"
        kotlin("jvm") version "2.2.10"
        kotlin("plugin.serialization") version "2.2.10"
        id("org.jetbrains.compose") version "1.8.2"
        id("org.jetbrains.kotlin.plugin.compose") version "2.2.10"
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.PREFER_SETTINGS)
    repositories {
        mavenCentral()
        google()
    }
}

rootProject.name = "stagecue"

include(":shared")
include(":server")
include(":desktopApp")
