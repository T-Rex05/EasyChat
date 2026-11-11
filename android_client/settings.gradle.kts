// 小暖(EasyChat 家庭客户端)设置:依赖优先走腾讯 maven-public 代理
// (dl.google.com 在当前网络间歇不可达,WP0 实测);google/central 兜底。
// plugins.gradle.org 与 services.gradle.org 不可达,Kotlin/AGP 插件经
// buildscript classpath 解析,见根目录 build.gradle.kts。
pluginManagement {
    repositories {
        maven("https://mirrors.cloud.tencent.com/nexus/repository/maven-public/")
        google()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        maven("https://mirrors.cloud.tencent.com/nexus/repository/maven-public/")
        google()
        mavenCentral()
    }
}

rootProject.name = "XiaoNuan"
include(":app")
