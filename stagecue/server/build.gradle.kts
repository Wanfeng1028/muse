plugins {
    kotlin("jvm")
    kotlin("plugin.serialization")
    application
}

kotlin {
    jvmToolchain(21)
}

dependencies {
    implementation(project(":shared"))

    implementation("io.ktor:ktor-server-core:3.1.3")
    implementation("io.ktor:ktor-server-cio:3.1.3")
    implementation("io.ktor:ktor-server-websockets:3.1.3")
    implementation("io.ktor:ktor-server-content-negotiation:3.1.3")
    implementation("io.ktor:ktor-serialization-kotlinx-json:3.1.3")
    implementation("io.ktor:ktor-server-call-logging:3.1.3")
    implementation("io.ktor:ktor-server-cors:3.1.3")

    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.10.2")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.8.1")

    implementation("ch.qos.logback:logback-classic:1.5.18")

    implementation("org.xerial:sqlite-jdbc:3.53.4.0")
    implementation("org.flywaydb:flyway-core:10.21.0")
    implementation("com.google.code.gson:gson:2.13.1")
    implementation("io.micrometer:micrometer-core:1.17.1")
    implementation("io.micrometer:micrometer-registry-prometheus:1.17.1")

    testImplementation(kotlin("test"))
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testImplementation("io.ktor:ktor-server-test-host:3.1.3")
}

application {
    mainClass.set("dev.stagecue.server.MainKt")
}

tasks.test {
    useJUnitPlatform()
}
