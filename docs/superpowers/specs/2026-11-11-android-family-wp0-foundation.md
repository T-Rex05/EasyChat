# WP0 核验记录与实施基线(小暖 Android 家庭客户端)

日期 2026-11-11,基线提交 `2d4311e`,工作目录 `E:\PythonCode\EasyChat`。本文件是 WP0 的交付物:环境核验、依赖矩阵、接口核验结果、DTO 映射、与设计文档的差异清单,以及新增后端契约草稿摘要。所有条目标注(实测/源码核对/推断)。

## 1. 应用标识(冻结)

| 项 | 值 |
| --- | --- |
| 应用包名 applicationId | `com.easychat.family` |
| 代码命名空间 namespace | `com.easychat.family` |
| 展示名 | 小暖(可整体替换,替换点:`app_name` 字符串资源) |
| 工程目录 | `android_client/`(单 app 模块,按 feature 包组织) |
| 版本 | versionCode 1,versionName 0.1.0(debug 构建) |

## 2. 开发环境核验(实测 2026-11-11)

| 项 | 结果 |
| --- | --- |
| JDK | 17.0.9(Oracle,`JAVA_HOME=C:\Program Files\Java\jdk-17`)✓ |
| Android SDK | `D:\Android-studio\sdk`(`ANDROID_HOME` 已设置)✓ |
| platforms | android-34、android-35 已装;36 可由 AGP 自动下载(许可证 hash `24333f8a63b6825ea9c5514f83c2829b004d1fee` 已在 `licenses/`)✓ |
| build-tools | 30.0.3 / 34.0.0 / 35.0.0 / 35.0.1 / 37.0.0 ✓ |
| 模拟器 | `emulator/` 与 `system-images/android-34/google_apis_playstore/x86_64` 已装;**尚无 AVD**,待创建 |
| 真机 | `adb devices` 为空,无连接设备;家人真实机型未核验,遗留 WP5 |
| cmdline-tools / avdmanager | **缺失**,需从 `dl.google.com/repository/commandlinetools-win-*.zip` 下载(GET 实测可达) |
| Gradle | 本地完整发行版 8.12:`D:\Android-studio\GradleHome\wrapper\dists\gradle-8.12-bin\cetblhg4pflnnks72fxwobvgv\gradle-8.12`(实测 `--version` 正常)。`~/.gradle/wrapper/dists` 内 8.11.1/8.13 均为未完成 `.zip.part`,不可用 |
| 网络 | `dl.google.com` 与 `repo.maven.apache.org` GET 可达(HEAD 被拦,不影响构建);`services.gradle.org`、`plugins.gradle.org`、aliyun/huawei 镜像不可达;`mirrors.cloud.tencent.com/gradle/` 可达(206) |

**结论**:wrapper `distributionUrl` 指向腾讯镜像(`https://mirrors.cloud.tencent.com/gradle/gradle-8.12-bin.zip`,实测可达),本机构建可直接使用本地 Gradle 8.12;仓库不提交 `local.properties`。

### 2.1 环境问题与处置记录(实测,WP0 实施过程)

| 问题 | 处置 | 证据 |
| --- | --- | --- |
| `~/.gradle/wrapper/dists` 内 gradle-8.11.1/8.13 均为未完成 `.zip.part`(`services.gradle.org` 不可达) | 使用 `D:\Android-studio\GradleHome\wrapper\dists\gradle-8.12-bin\...\gradle-8.12` 完整发行版;wrapper 源指向腾讯镜像 | `gradle --version` 输出 Gradle 8.12/JDK 17 |
| `plugins.gradle.org` 不可达,Kotlin android/serialization 插件 marker 不在 google/central | 根 `build.gradle.kts` buildscript classpath 提供 AGP 8.10.1 + Kotlin 2.3.21 + compose-compiler + serialization;`plugins {}` 块不带版本经 classpath 描述符解析 | 首次 `gradle help` 2m35s 成功 |
| `dl.google.com` 间歇不可达(TLS 握手失败;`mavenCentral`/腾讯镜像正常;本机代理 Fake-IP 198.18.0.2) | `settings.gradle.kts`/根 buildscript 以腾讯 `nexus/repository/maven-public` 为首仓库,google/central 兜底 | androidx 经腾讯镜像解析成功 |
| sdkmanager 的 Java 网络栈拉取清单失败 | curl 走腾讯 SDK 镜像手动安装 `platform-36`(`AndroidSDK/platform-36_r02.zip`,65,878,410 字节) | `platforms/android-36/source.properties` ApiLevel=36 |
| 最新 2026 线 androidx(compose 1.12/lifecycle 2.11/navigation 2.10/core 1.19/okhttp 5.5)要求 **compileSdk 37 + AGP 9.1**(JDK 17 不满足 AGP 9) | 版本回退一代:compose-bom 2025.12.01、navigation 2.9.8、lifecycle 2.10.0、core-ktx 1.17.0、activity-compose 1.12.4、okhttp 5.4.0(要求 compileSdk 36,兼容 AGP 8.10) | `checkDebugAarMetadata` 33 项问题→回退后通过 |
| 模拟器启动报「too many emulator instances」(WHPX 与 TCG 均触发) | 清理 `%TEMP%\AndroidEmulator`(crash-db)后以显式端口 `-ports 15554,15555` 启动成功 | `adb devices` 出现 emulator-15554,Android 14 启动约 30s |
| `avdmanager` 缺失 | 下载 `commandlinetools-win-13114758_latest.zip`(dl.google.com,143,040,480 字节)→ `sdk/cmdline-tools/latest`;创建 AVD `xn_test`(pixel_6 + android-34 google_apis_playstore x86_64) | `emulator -list-avds` 输出 xn_test |

## 3. 依赖矩阵(锁定,2026-11-11 构建实测后修订)

AGP 与 Gradle 配对依据 Google 兼容矩阵(AGP 8.10 最低 Gradle 8.11.1,实测用本地 8.12);Kotlin 2.3.x 与 Compose 编译器插件同版本;全部为发布时 Maven 元数据中的最新稳定版(实测查询 2026-11-11)。**修订**:2026 线 androidx 需要 compileSdk 37 + AGP 9.1(JDK 17 环境不满足),按 §2.1 回退一代,以下为实测通过组合。

| 依赖 | 版本 | 用途 |
| --- | --- | --- |
| Android Gradle Plugin | 8.10.1 | 构建 |
| Gradle | 8.12(本地缓存)/ wrapper 同版(腾讯镜像源) | 构建 |
| Kotlin | 2.3.21 | 语言 + compose/serialization 插件 |
| compose-bom | 2025.12.01 | ui/material3/foundation |
| activity-compose | 1.12.4 | Compose 宿主 |
| navigation-compose | 2.9.8 | 导航 |
| lifecycle-viewmodel-compose / runtime-compose | 2.10.0 | 状态 |
| core-ktx | 1.17.0 | 基础 |
| kotlinx-coroutines | 1.11.0(core/android/test) | 异步 |
| okhttp / okhttp-sse / logging-interceptor | 5.4.0 | 网络 + SSE(WP2) |
| kotlinx-serialization-json | 1.12.0 | DTO(WP2) |
| datastore-preferences | 1.3.0 | 偏好(WP2) |
| room(runtime/ktx/compiler)+ KSP | 引入时按 KSP 兼容矩阵定 | 本地缓存(WP2/WP3) |
| junit | 4.13.2 | 测试 |

SDK 目标:`minSdk 29`(Android 10,设计默认)、`compileSdk 36`、`targetSdk 36`。WP1 不引入 Room/KSP,按 sequence-verifiable-units 渐进。

## 4. 接口核验结果(源码核对,与设计文档 §7 对照)

以下均已再次逐文件核验;与设计文档差异以**本表为准**(代码为准):

| 接口 | 实际行为 | 证据 |
| --- | --- | --- |
| `POST /chat/stream` | Bearer + JSON `{message, thread_id, client_msg_id, attachment_ids[]}`(另有 mode/scene/model_id 字段但 `_make_command` 不消费,首版不发送);响应 `text/event-stream` | `backend/modules/assistant/routes.py::stream_post` |
| thread_id 合法格式 | `sess_*`(归属校验)、`^\d+_\d+$`(解析/创建 web 会话)、`wx_*` 明确拒绝 | `routes.py::_resolve_session` |
| SSE start | `{"type":"start","thread_id":<客户端原值>,"conversation_id":<run_id>}` | `routes.py::_stream_events` |
| SSE token/thinking_step | `token{content}`、`thinking_step{content}`;`tool_started` 不下发 | 同上 |
| SSE chat_complete | `{"final_content":…}`;之后发 `retry: 86400000` | 同上 |
| SSE error | **`{"type":"error","message":…}`**(message 字段) | 同上 |
| stream_reset | 环形缓存失效→`stream_reset`+从持久状态补终态帧,不重执行 | `routes.py::_final_frame_for` |
| Last-Event-ID | 服务端 `seq+1`,客户端传最后已消费序号 | `routes.py::_resume_from` |
| 取消 | `GET/POST /chat/cancel` 读 **query**(`run_id` 优先,回退 `thread_id+client_msg_id`);返回 `{"ok":true,"cancelled":bool,"run_id":…}` | `routes.py::cancel_chat` |
| 会话列表 | `GET /api/history?offset&limit(≤200)`→`{sessions:[{session_id,title,source,created_at,updated_at}]}`(过滤 active) | `routes.py::history_list` |
| 会话消息 | `GET /api/history/{session_id}`→messages 仅 `{role,content,created_at}`,**无 message_id/run_id/附件** | `routes.py::history_messages` |
| 重命名/删除 | `PUT /api/history/{id}` body `{title}`;`DELETE /api/history/{id}` | 同上 |
| 图片/文件上传 | `POST /api/chat/upload-images|upload-files`,multipart 字段 `files`(1–10 个);图片回 `data_url`,文件回 `url=/api/files/{file_id}/content` | `backend/modules/assistant/compat.py` |
| 登录/me/refresh | `POST /api/auth/login`(username/password,回 `token`+`permissions`+`hermes_tools`)、`GET /api/auth/me`(id/username/role/permissions/capabilities)、`POST /api/auth/refresh` | `backend/modules/access/routes.py`(login 返回体含 `access.login` 展开的 `token`,WP2 联调再实测字段名) |
| SSE ticket | `POST /api/chat/sse-ticket`→`{ticket, expires_in}`(EventSource 备用;Android 用 OkHttp 原生 header,不必走 ticket) | 同上 |
| capabilities | `{modules:{chat/memory/scheduling/inbox/profiles…:{label,enabled,read,use,manage}},tools,super_admin,permissions}` | `backend/modules/access/api.py::capabilities` |
| 日程 | `GET/POST /api/schedules`;`PATCH /{id}` body `{enabled}`;`DELETE /{id}`;`GET /{id}/occurrences`;创建 body 字段 title/text/at/every_seconds/daily_at/weekly_at/weekday/timezone/content_kind/briefing_kind/target_kind/target_ref | `backend/modules/scheduling/routes.py` |
| 日程目标 | 不传 target 时默认取微信绑定;无绑定 422「没有可用的微信绑定…」 | `routes.py::_target` |
| next_run_at | **秒级 epoch float**;`last_run_at`/`scheduled_at` 为 ISO 文本 | `scheduling/contracts.py::ScheduleView` |
| 记忆 | `GET /api/memory`(默认 50 条上限);创建 `POST /api/memory/remember`;修改 **`PUT /api/memory/{id}`**(设计文档写 PATCH,实为 PUT,携带 expected_version);`POST /api/memory/forget`;`DELETE /api/memory/{id}?reason=` | `backend/modules/memory/routes.py` |
| 记忆记录 | memory_id/kind(fact|preference|event|experience)/content/source_refs/scope/event_at/recorded_at/version/status/pinned/confidence/source_type(user_confirmed|model_inferred)/tags | `memory/routes.py::_record` |
| 收藏 | `GET /api/inbox?status&limit(默认20,≤100)`、`GET /api/inbox/search?q`、`POST /api/inbox`(url/file_id/note/title/tags)、`POST /{id}/archive`、`POST /{id}/read`、`DELETE /{id}` | `backend/modules/inbox/routes.py` |
| 个人偏好 | `GET/PATCH /api/profile`;字段 persona_preset/address_form/max_chars/emoji_level/proactivity/quiet_start/quiet_end/timezone/custom_instruction/mood_opt_in/mood_retention_days | `backend/modules/profiles/routes.py` |
| 微信绑定 | `GET /api/channels/bindings`→本人绑定(admin 看全部);`PATCH /bindings/{id}`/`DELETE` 本人可解绑自己 | `backend/modules/channels/routes.py`、`api.py::list_bindings/set_binding_status` |
| 微信会话归属 | 入站按 `platform+account+external_user` 查 binding→owner;会话 `source="wechat"`,`external_chat_id="{account_id}:{外部chat}"` | `channels/api.py::_process_event/_resolve_session` |
| App 会话来源 | `_make_command` 硬编码 `source="web"`;带背景新聊走独立 App 会话即独立 `sess_*` 线程 | `assistant/routes.py` |
| 幂等键 | runs 按 `owner+session+source+channel_account_scope+client_message_id` 去重,重复提交返回原 run | `assistant/repository.py::create_run` |
| 错误结构 | AppError→`{error:<code>,message,details?}`;busy 在 chat 路由特化为 `{"error":str}`(无 message);HTTP 映射 401/403/404/409/422/429/503/504 | `backend/shared/errors.py`、`routes.py::stream_post` |
| 模块未就绪 | 503 `capability_unavailable`(`_LazyModule`) | `backend/app.py` |

**既定能力边界**(实施遵守):

- 历史消息无稳定 ID:客户端以整段会话快照替换本地投影,草稿独立存储(设计 §6.5)。
- schedule 无 origin_session_id/origin_message_id:「微信里记下的」标签 P0 阶段不得虚构;仅当来源可证(如 briefing_kind/content_kind 组合不可证,统一不显示来源标签)。WP4 提契约草稿等人工决策。
- inbox 响应无 source 字段:App 无法区分微信收藏与 Web 收藏,P0 收藏列表不显示来源标签。
- 提醒无编辑接口:改时间=删除+新建,UI 明示。
- 无推送通道:提醒投递依赖既有微信/邮箱链路,App 只展示计划与 occurrence。

## 5. 新增后端契约草稿(供人工评审,未实施)

按 AGENTS.md,以下涉及公共契约与存储,只写草稿不写码:`docs/superpowers/specs/2026-11-11-android-family-backend-contract-draft.md`(与 WP4 同步细化)。摘要:

1. `GET /api/history/{session_id}` 消息补 `message_id`、`run_id`、`attachment_ids`、`status`(只读扩展,不改写路径)。
2. `schedules` 读取响应补 `origin_session_id`/`origin_message_id`(写入时由工具层落列,需迁移)。
3. inbox item 响应补 `source`(wechat/web)。
4. history 列表补 `has_more`/`next_cursor`,解决过滤短页。

## 6. WP 实施清单与验收对照

| WP | 范围 | 收尾物 |
| --- | --- | --- |
| WP0(本文) | 环境/接口/权限核验、包名与依赖冻结 | 本文档 + 工程脚手架可构建 |
| WP1 | 主题 Token、四导航、今天/聊天/生活/我的 + 登录布局,模拟数据带「示例」标记 | `assembleDebug` 通过 + 单测(对比度/排版) + 模拟器截图(360/412dp、浅/深、正常/大字) |
| WP2 | 服务器配置、登录、me、Keystore 凭证、历史、文字图片聊天、SSE、取消、断线恢复 | 联调记录 + 状态截图 + 调试 APK |
| WP3 | 今天/生活聚合(schedules/memory/inbox/微信会话)、刷新分页删除、账号隔离 | 联调记录 + 截图 |
| WP4 | 提醒创建/暂停/恢复/删除/occurrence;后端契约草稿呈报 | 联调记录 + 升级简报(如触保护) |
| WP5 | 真机验证、签名 APK、安装升级说明 | 交付记录 |

**阻塞/遗留**:家人真实机型与网络地址未提供(不影响 WP1–WP4 本机验证);AVD 待创建;Web Before 基线截图在 WP2 联调时与 Android After 同场景补齐。
