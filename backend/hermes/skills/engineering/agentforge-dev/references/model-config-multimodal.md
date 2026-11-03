# 模型配置三层多模态检测

## 架构概览

```
创建/测试模型配置
  ├─ Layer 1: 静态名称规则 (instant, 0 cost)
  ├─ Layer 2: 厂商元数据接口 (未实现, reserved)
  └─ Layer 3: 图片探测预检 (authoritative, 7-day cache)
```

## Layer 1 — 静态名称规则

文件: `backend/utils/multimodal_detect.py`

三类规则,按优先级:

1. **纯文本排除 (最高优先级)** — `\bcoder\b`, `\bcode\b`, `\btext\b`, `instruct[-_]?text`, `gpt-3\.5`, `text-davinci`, `text-embedding`, `whisper`, `dall-e`, `moderation`, `rerank`, `sentence` 等
2. **通用多模态关键词** — `\bvl\b`, `\bvision\b`, `\bomni\b`, `\bmultimodal\b` (跨厂商)
3. **厂商特定模式** — `gpt-4o`, `claude-[3-9]`, `gemini-`, `qwen3`, `glm-4v`, `cogview`, `internvl`, `minicpm.*v`, `llava`, `pixtral`, `paligemma` 等

判定逻辑: 先排除纯文本 → 再匹配通用关键词 → 再匹配厂商模式 → 默认判纯文本。

## Layer 2 — 厂商元数据接口

预留位置。设计思路: 调用服务商模型元信息接口 (如 `/v1/models` 返回 `capabilities.vision: true`),批量缓存模型能力标识。无 token 消耗,只能判断模型本身能力,无法校验账号订阅。

## Layer 3 — 图片探测预检

函数: `probe_image_support(api_url, api_key, model_name, timeout=20)` → `(bool, str)`

**探测方式**: 发送一张 1×1 白色 PNG (base64, 84 bytes) 作为 `image_url` content block,附带 `"What color is this? Answer with one word."` 文本,`max_tokens=5`, `temperature=0`。

**端点判定**:
- URL 含 `/anthropic` → POST 到 `{base}/v1/messages`
- 其他 → POST 到 `{base}/chat/completions`
- 自动补全: 已有 `/v1/messages`/`/chat/completions` 后缀则不重复追加

**响应判定**:
| 响应 | 判定 | 缓存 |
|---|---|---|
| 200 OK | 支持图片,判定 multimodal | ✅ 7天 |
| 400 + "only text" / "does not support image" 等提示 | 纯文本模型 | ✅ 7天 |
| 400 其他原因 (图片格式/尺寸) | 不判定,建议重试 | ❌ 不缓存 |
| 404 / 403 | 模型可能支持但账号无权限 | ✅ 7天 |
| 网络异常 | 请求失败 | ❌ 不缓存 |

**缓存**: 进程内 `_IMAGE_PROBE_CACHE` dict,key = `sha256(model_name|api_url|api_key)`, TTL = 7天。

**集成**: 在 `POST /api/model-configs/{id}/test` 端点中,创建完 `multimodal` 变量后:

```python
# Layer 3 — 图片探测预检
probe_ok = None
probe_msg = ""
try:
    probe_ok, probe_msg = probe_image_support(api_url, api_key, model_name_for_detect, timeout=15)
except Exception:
    pass

multimodal = stored_multimodal or probe_ok or (detected_multimodal if probe_ok is None else False)
```

所有测试连接返回都带 `"probe_multimodal": probe_ok` 和 `"probe_message": probe_msg` 字段。

前端 `api/config.ts` 的 `TestResult` 接口需加:
```typescript
probe_multimodal?: boolean | null
probe_message?: string
```

## 模型配置测试连接 — Anthropic 端点特殊处理

**检测逻辑**: `is_anthropic = "/anthropic" in base or base.endswith("/messages")`

**路径补全**: 裸域名自动补 `/v1/messages`,已有 `/v1/messages`/`/v1`/`/messages` 后缀则不重复。

**Headers**:
- `Authorization: Bearer {api_key}` (同时带)
- `x-api-key: {api_key}` (DeepSeek Anthropic 兼容)
- `anthropic-version: 2023-06-01`

**POST body**: `{"model": "...", "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]}`

**404 处理 — 关键陷阱**: Anthropic 分支 HTTPError 仅 2xx 判 `ok: True`。404/500/503 等必须返回 `ok: False`。DeepSeek 的 `/anthropic` 路径若不存在会返回 404,不能误判为成功。

## 模型配置 URL 提示 (前端)

`ConfigView.vue` 新增/编辑表单的 API Base URL 输入框下提示:
```
⚠️ 只需填根域名,不要手动加 /v1、/v1/models、/v1/messages,系统自动补全。
· OpenAI 兼容 (GPT/Qwen/GLM 等): 填 https://api.openai.com 即可
· Anthropic 兼容 (Claude/DeepSeek 等): 填 https://api.deepseek.com/anthropic 即可
```
