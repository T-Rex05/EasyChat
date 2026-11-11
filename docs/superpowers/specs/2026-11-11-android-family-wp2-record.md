# WP2 记录:登录与聊天主链(真实服务端联调)

日期 2026-11-11,基线 WP1(`023871f`)。本文件是 WP2 的验收记录:交付物、真机联调证据、验收对照与遗留项。

## 1. 交付物(代码)

- `core/network/`:ApiClient(Bearer + 401 单飞刷新重试一次 + 错误体三类兼容解析)、ChatStreamClient(POST /chat/stream SSE,Last-Event-ID 续传,响应消费全部在 IO 线程)、SseFrameParser(纯逻辑:id/data/多行 data/心跳注释/retry 指令)、ChatEventCodec(start/token/thinking_step/stream_reset/chat_complete/error;未知事件忽略)、AuthRepository(连接检查/登录/me/退出 + session epoch)、ChatRepository(会话列表/整段快照/重命名/删除/取消 query 参数 + cancelled 字段/thread_id 兼容格式)、ApiError(HTTP 码 ↔ 稳定错误码 ↔ 家人可读文案)。
- `core/storage/`:XnKeystore(AES-256-GCM,密钥不出 AndroidKeystore,fail-closed)、TokenStore(密文落 DataStore;解密失败按未登录处理)、ConnectionStore(服务器地址 + 账号快照 + session epoch 分区失效)。
- `core/model/Dto.kt`:全部 DTO 按WP0 核验契约(kotlinx.serialization,ignoreUnknownKeys)。
- UI 真实化:ServerConfig(真实 /healthz+/readyz 依次检查 + 「连接成功/正在启动/地址暂时连不上」)、Login(真实 /api/auth/login + /api/auth/me)、ChatList(真实 /api/history + 筛选)、ChatDetail(真实流式状态机:submitting→streaming→completed;recovering 1/2/4/8s 退避上限 4 次;cancel_requested→cancelled;停止按钮切换)、Profile(真实用户名 + 退出登录)。
- debug 构建专用 `app/src/debug/AndroidManifest.xml` 允许明文 HTTP(设计 §5.1 内网联调配置);release 仅 HTTPS。

## 2. 真实联调证据(模拟器 Android 14 ↔ 本机运行中的后端 8001)

联调通道:`adb reverse tcp:8001 tcp:8001`,App 内地址 `http://127.0.0.1:8001`;测试账号 `xiaonuan_test`(经 /api/auth/register 创建)。截图在 `docs/superpowers/specs/assets/android-wp2/`:

| 截图 | 场景 |
| --- | --- |
| wp2_01_connected_login.png | 真实连接检查通过后自动进入登录页 |
| wp2_02_login_error_friendly.png | 错误文案示例(后端可达性问题的家人可读反馈) |
| wp2_03_thinking_stop_button.png | 发送后「正在想一想」+ 输入区切换为停止按钮(状态机 busy) |
| wp2_04_stream_complete.png | 流式完成:真实模型回复「Hi〜今晚有什么想一起处理的吗?😊」,停止按钮恢复为发送 |
| wp2_05_real_sessions.png | 杀进程重启后:token 持久化直达主界面;会话列表来自真实 /api/history(两条 App 会话) |
| wp2_06_history_restore.png | 打开历史会话:整段快照恢复(消息与流式完成时一致;时间格式化修复后显示 HH:mm) |

服务端核对(同一时间窗,与 App 互证):POST /chat/stream 返回 start(conversation_id=run_…)+ seq 递增 thinking_step/token 帧(App 按帧解析渲染)。

## 3. 联调中发现并修复的问题(每条带证据)

1. **NetworkOnMainThreadException**:rawCall 在 IO 执行请求但 `Response.use` 关闭落在主线程 → rawCall 改为在 IO 内消费并关闭、返回 `RawHttpResponse(code, body)`。证据:logcat `XnConn` 全栈。
2. **kotlinx serialization `Serializer for class 'Any'`**:inline reified `post<T>(path, body: Any?)` 丢失 body 类型 → 改双 reified `post<T, B>(path, body: B)`。证据:logcat `XnLogin` 栈顶 `AuthRepository.login`。
3. **历史消息时间戳显示原始 ISO**:渲染未走格式化 → `XnTime.formatIso`。证据:wp2_06。
4. **服务器地址畸形输入无校验**(联调中拼出 `…8001http:` 才暴露)→ 地址格式正则校验 + 友好报错示例。
5. **明文 HTTP 被系统拦截**(Android 9+ 默认)→ debug-only cleartext 覆盖(release 不含),符合设计 §5.1「明确的开发构建配置」。

## 4. 验收对照(设计 §10 WP2)

| 验收目标 | 结果 |
| --- | --- |
| 服务配置、登录、me、凭证保护 | 完成;token 经 AndroidKeystore AES-GCM 加密落盘,解密失败 fail-closed 按未登录处理 |
| 历史读取 | 完成;整段快照替换策略(服务端无消息 ID,WP0 核验边界) |
| 文字聊天 + 流式 | 完成;真实后端联调证据 wp2_03/04 |
| 取消 | 代码完成(query 参数 + cancelled 字段 + UI 停止按钮);长生成实测未做(见 §5) |
| 断线恢复 | 代码完成(Last-Event-ID + 同 client_msg_id 幂等 + 1/2/4/8s 退避);断流实测未做(见 §5) |
| 可安装调试 APK | `app-debug.apk` 0.1.0;`assembleDebug testDebugUnitTest` BUILD SUCCESSFUL(13 项单测) |

## 5. 遗留项(记录,不阻塞 WP3)

1. 取消与断流恢复的真实网络级实测:需长回复会话 + 主动断网(飞行模式)窗口,在 WP3 联调窗口补做并补截图;
2. 图片附件上传(upload-images)UI 未接(设计 §5.3 附件进度态),WP3 收尾;
3. 会话标题为空时显示「未命名对话」:后续在会话打开后按首条消息自动 rename(rename 接口已就绪);
4. 草稿持久化(DataStore 按 server+owner+session 分区)未落,当前草稿仅内存;设计 §8.1 的「退出前提示有草稿」依赖此项,WP3 落地;
5. 401 刷新路径未在联调中触发(token 30 天有效),单元级验证在 WP3 补(mockwebserver)。
