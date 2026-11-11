// 根构建:插件经 buildscript classpath 解析(绕开不可达的 plugins.gradle.org,WP0 实测)。
// 版本对应关系见 docs/superpowers/specs/2026-11-11-android-family-wp0-foundation.md。
buildscript {
    repositories {
        maven("https://mirrors.cloud.tencent.com/nexus/repository/maven-public/")
        google()
        mavenCentral()
    }
    dependencies {
        classpath("com.android.tools.build:gradle:8.10.1")
        classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:2.3.21")
        classpath("org.jetbrains.kotlin:compose-compiler-gradle-plugin:2.3.21")
        classpath("org.jetbrains.kotlin:kotlin-serialization:2.3.21")
    }
}
