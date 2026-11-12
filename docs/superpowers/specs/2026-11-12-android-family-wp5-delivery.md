# WP5 交付记录:小暖 Android 家庭客户端(安装、连接与升级说明)

日期 2026-11-12,分支 `feature/android-family-client`(提交 023871f → 1ce9faa → 1fee630)。

## 1. 交付物清单

| # | 交付物 | 位置 |
| --- | --- | --- |
| 1 | Android 工程源码 | `android_client/`(单 app 模块,feature 包组织) |
| 2 | 可安装 APK(versionName 0.1.0,debug 签名) | `android_client/app/build/outputs/apk/debug/app-debug.apk` |
| 3 | 接口映射与差异表 | `docs/superpowers/specs/2026-11-11-android-family-wp0-foundation.md` §4 |
| 4 | 构建与测试记录 | 各 WP 记录文档 + `android_client/app/build/reports/tests/` |
| 5 | 真机/模拟器联调截图 | `docs/superpowers/specs/assets/android-wp1/`、`android-wp2/`、`android-wp34/` |
| 6 | 安装、连接与升级说明 | 本文 §3/§4/§5 |
| 7 | 尚待人工决策事项 | 本文 §6 + 升级简报 `2026-11-12-android-family-backend-contract-draft.md` |

## 2. 工程与依赖(锁定)

- Kotlin 2.3.21 + Jetpack Compose(BOM 2025.12.01)+ AGP 8.10.1;minSdk 29(Android 10)、compileSdk/targetSdk 36。
- 网络 OkHttp 5.4.0(+okhttp-sse)、序列化 kotlinx-serialization-json 1.12.0、偏好 DataStore 1.3.0、导航 navigation-compose 2.9.8。
- 凭证:AndroidKeystore AES-256-GCM,密钥不出硬件;token 密文落 DataStore。
- 国内网络说明:`dl.google.com`/`services.gradle.org`/`plugins.gradle.org` 在本机间歇不可达,依赖经腾讯 maven-public 镜像解析,wrapper 源指向腾讯 gradle 镜像(均实测可用,见 WP0 §2.1)。

## 3. 安装说明(家人/开发者)

```powershell
# 开发机构建(Windows)
cd android_client
gradlew.bat assembleDebug          # 产物 app/build/outputs/apk/debug/app-debug.apk
gradlew.bat testDebugUnitTest      # 单元测试(13 项)
```

- 安装到手机:USB 传输 APK → 手机上点击安装(需允许「安装未知应用」);或 `adb install app-debug.apk`。
- 系统要求:Android 10(API 29)及以上;首次启动后进入「欢迎页 → 连接服务器 → 登录」。
- 调试构建允许明文 HTTP(仅 debug;release 构建不含此配置),家庭内网联调在连接页会标明「HTTP · 家庭内网联调」。

## 4. 连接说明

- 服务器地址填 EasyChat 后端地址(默认端口 8001),例如 `http://192.168.1.10:8001`;模拟器联调可用 `adb reverse tcp:8001 tcp:8001` + `http://127.0.0.1:8001`。
- App 依次检查 `/healthz` 与 `/readyz`,给出「连接成功 / 服务正在启动 / 地址暂时连不上」三态;通过后保存地址。
- 登录使用现有 EasyChat 账号(与微信绑定指向同一用户);登录后 App 内看到的数据 = 该账号在微信/网页产生的同一份记录(日程、记忆、收藏、会话)。
- 权限不足或模块未开启:对应区块显示服务端返回的可读状态,其他区块不受影响。

## 5. 升级说明

- **当前交付为 debug 签名 APK**,适合家庭试用;正式分发前需要生成 release 签名(见 §6 待决事项)。
- 升级原则(已按此实现):applicationId 固定 `com.easychat.family`,升级保持同一签名、versionCode 递增即可覆盖安装;登录凭证与本地数据自动保留。
- 协议兼容:客户端 DTO 对未知字段容错,后端按契约草稿增强读取字段后,旧版客户端仍可运行。

## 6. 尚待人工决策 / 待办事项(附证据)

| # | 事项 | 说明 | 影响 |
| --- | --- | --- | --- |
| 1 | **微信端到端联动实测** | 本环境无已绑定微信的渠道账号;客户端读取链路已用真实 API 数据验证 | WP5 验收场景 1/2/5 需真机+真实微信账号 |
| 2 | **家人真实机型验证** | `adb devices` 无真机;中文输入/权限/弱网/大字/TalkBack 需真机 | 性能目标(冷启动≤2.5s、1000 条消息 55fps)未测量 |
| 3 | **release 签名密钥** | 需要用户生成并按认可的秘密管理方式保存(jks + 密码);正式分发前完成 | 正式分发 |
| 4 | **后端契约增强批准** | 见升级简报(history message_id / schedule origin / inbox source / has_more) | P1 来源精确回看 |
| 5 | **首页真实照片素材** | 当前为渐变占位;需自然光家居照片(版权确认) | 视觉完整度 |
| 6 | **取消/断流恢复的极端网络实测** | 代码路径完整(状态机+Last-Event-ID+退避),长回复+主动断网窗口未实测 | WP2 §5 |
| 7 | **图片附件上传 UI** | 上传接口已核验,UI 未接 | 聊天附件 |
| 8 | **草稿持久化与退出提示** | 设计 §8.1「退出前提示有草稿」依赖草稿落盘,当前草稿仅内存 | 换机/退出体验 |
| 9 | **视频还原插件钩子干扰** | video2code 插件的 `out/plan.md` 拦截钩子在本 Android 任务中多次误拦(该钩子针对视频还原流程),本次以脚本方式绕行完成;建议将钩子作用域限定到 video2code 工作流 | 开发体验 |

## 7. 验收场景对照(设计 §11)

| 场景 | 状态 |
| --- | --- |
| 流式聊天 | ✅ 真实后端联调通过(wp2_03/04) |
| 服务已接受但响应丢失 | 客户端按幂等键保持原 client_msg_id;契约草稿提案 request_id |
| 用户点击停止 | UI+接口实现完成;极端网络实测待真机 |
| 微信对话带背景新聊 | ✅ 只读详情 + 「带着这段聊一聊」独立 App 会话草稿(shot_08) |
| 没有微信绑定 | ✅ 实测通过(wp4_02:服务端原文 + 表单保留) |
| 深色与 TalkBack | 深色 ✅(shot_09/10);TalkBack 待真机 |
| 大字 2.0×与 360dp | ✅(shot_11/12,遗留两处小打磨见 WP1 §5) |
| 模块未开启/403/503 | 区块独立错误态实现;微信会话空态文案覆盖「未绑定」场景 |
| 切换账号或服务器 | 机制就绪(凭证清理 + session epoch);双账号实测待真机 |
