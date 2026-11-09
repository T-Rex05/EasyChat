# P0.5 微信 A+C 外部探针记录

日期：2026-11-04。环境：Windows / PowerShell，工作区 `E:\PythonCode\EasyChat`。

## 1. 结论先行

本轮执行环境**没有可用的真实 iLink 账号凭证、绑定设备或真实微信账单导出文件**。因此：

- 未执行真实语音下载/格式识别/云端 STT 调用；
- 未执行真实主动推送（`context_token` 缺失/过期/有效）实验；
- 不伪造“已验证”结论，P3 与主动推送能力按**未验证 Adapter + feature flag**交付。

阻塞证据（只读核对）：

```text
settings 默认 wechat_enabled=False；没有 EASYCHAT_WECHAT_ENABLED / EASYCHAT_ENCRYPTION_SECRET 注入
没有真实 channel_accounts 凭证可供发送；测试全部使用 Fake transport/fetcher
```

## 2. 语音媒体格式探针（未验证）

待有真实账号时执行：

1. 向机器人发送 3 条普通话语音（短/中/长各一）。
2. 记录 `item_list[].voice_item` 的 `url`/`encrypt_query_param`/`aes_key`/`len`，下载解密后看首 16 字节。
3. 判定容器：
   - `#!SILK_V3` → SILK v3；
   - `#!AMR` → AMR；
   - `ID3`/`0xFFFB` → MP3；
   - `RIFF....WAVE` → WAV；
   - `OggS` → OGG/Opus。
4. 分别尝试：
   - 原始容器直接 POST `{base_url}/audio/transcriptions`；
   - `ffmpeg -i input -ar 16000 -ac 1 output.wav` 后再 POST。
5. 记录状态码、错误体、转写文本与耗时。

未验证时的实现承诺：

- 白名单接受 `.mp3/.m4a/.wav/.ogg/.opus/.amr/.silk/.aac/.webm`；
- SILK magic 且无解码器时明确失败，不把二进制送模型；
- STT 总开关默认关闭；
- 只选择 OpenAI 兼容配置，不把音频发往 Anthropic。

## 3. 主动推送窗口探针（未验证）

待有真实账号时对同一绑定用户执行：

| 场景 | 请求 | 记录 |
|---|---|---|
| token 有效 | 带上最近入站 `context_token` | HTTP/业务码、是否到达 |
| token 缺失 | 不传 `context_token` | 是否拒绝、错误码/errmsg |
| token 过期 | 使用 24h 前 token | 是否拒绝、错误码/errmsg |
| 用户再次说话后 | 刷新 token 重试 | 是否恢复 |

未验证时的实现承诺：

- `ChannelService.send_wechat_text` 在 token 为空时补 `latest_context_token()`；
- 发送错误分类：鉴权/参数/窗口明确拒绝 → `failed`（不重试）；超时/连接中断 → `uncertain`；未知保守 `uncertain`；
- 简报/提醒不承诺准点送达，只承诺进入投递账本并记录失败。

## 4. 后续动作

- 有凭证后把本文件“未验证”替换为真实输出，再关闭 feature flag 的“未验证”标记。
- 不把真实语音、账单、聊天记录提交到仓库或日志。
