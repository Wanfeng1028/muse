// 根构建脚本：只做通用配置，不重复声明插件版本（版本在 settings.gradle.kts 的 pluginManagement 中管理）

allprojects {
    group = "dev.stagecue"
    version = "0.2.0"
}

subprojects {
    tasks.withType<Test>().configureEach {
        useJUnitPlatform()
    }
}
