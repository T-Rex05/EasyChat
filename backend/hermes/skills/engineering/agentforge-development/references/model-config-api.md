# 模型配置 API — 完整模式参考

## 表结构 (`model_configs`)

```sql
CREATE TABLE IF NOT EXISTS model_configs (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id       BIGINT DEFAULT 1,
    config_name   VARCHAR(128) NOT NULL DEFAULT '',
    config_type   VARCHAR(32)  NOT NULL DEFAULT 'URL',
    api_url       VARCHAR(512) DEFAULT '',
    api_key       VARCHAR(512) DEFAULT '',         -- AES-256-GCM 加密
    model_name    VARCHAR(128) DEFAULT '',
    is_current    TINYINT DEFAULT 0,               -- 全局唯一=1
    enabled       TINYINT DEFAULT 1,
    last_test_status   VARCHAR(64),
    last_test_message  VARCHAR(512),
    last_test_time     DATETIME,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_current (user_id, is_current)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

## 控制器端点 (Prefix: `/api/model-configs`)

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/` | 登录即可 | api_key 脱敏为 `***已配置***`；返回 `{configs, env_configured}` |
| POST | `/` | config.manage 或 admin/super_admin | 加密 api_key，全局 is_current 置 0 后插入新=1 |
| PUT | `/{id}` | config.manage 或 admin | 编辑配置；api_key **留空则保持原密钥不变** |
| PUT | `/{id}/active` | config.manage 或 admin | 全局 is_current 置 0 → 目标置 1 |
| DELETE | `/{id}` | config.manage 或 admin | — |
| POST | `/{id}/test` | 登录即可 | 多级回退探测（见下） |

## 已知 Bug 修复：Anthropic 404 误判 ok=True

**症状**：测试 DeepSeek Anthropic 端点（`https://api.deepseek.com/anthropic`）显示 "服务器响应 HTTP 404，连接正常 ✓" 绿色对勾，但实际端点路径不正确。

**根因**：Anthropic 分支的 `except urllib.error.HTTPError` 只过滤了 401/403，其余所有 HTTP 错误码（包括 404）都走 `return {"ok": True, ...}`。

**修复** (`model_config_controller.py`，Anthropic 分支 `except HTTPError as e` 块内)：
```python
# 401/403 → API Key 被拒绝
if e.code in (401, 403):
    return {"ok": False, "message": "服务器可达，但 API Key 被拒绝..."}

# 2xx → 真正成功
if 200 <= e.code < 300:
    return {"ok": True, "message": "连接正常..."}

# 其他（404/500/503...）→ 服务器可达但端点路径不对
return {"ok": False, "message": f"服务器可达（HTTP {e.code}），但端点路径不正确。请确认 Base URL"}

# 然后才是 URLError（网络不通/DNS 失败）
```

**关键原则**：仅 2xx 算成功，HTTP 错误码说明服务器可达但路径/权限有问题，不是"连通 OK"。

- 列表：`configs` ref + `getModelConfigs()`，每条显示名称/模型/BaseURL/当前激活
- inline 编辑：点击「编辑」→ `startEdit(cfg)` 填入编辑表单 → 保存 `updateModelConfig(id, {...editForm})` → api_key 留空则保持原密钥
- 测试：「测试连接」按钮 → `testModelConfig(id)` → `testResult` ref 展示结果（成功/失败双色条）
- 新增：底部表单，保存即设为当前激活

## 测试连接端点的多级回退策略

测试端点 (`POST /{id}/test`) 必须覆盖三类 API：

1. **Anthropic 兼容端点** (`/anthropic`): 不支持 GET，只能 POST。发送 `{model, max_tokens:1, messages:[{role:"user",content:"ping"}]}` + `x-api-key` + `Bearer` header + `anthropic-version: 2023-06-01`。**路径自动补全**: 如果 Base URL 不以 `/v1/messages` 或 `/v1` 结尾，自动拼接 `/v1/messages`（如 `https://api.deepseek.com/anthropic` → `https://api.deepseek.com/anthropic/v1/messages`）。
2. **OpenAI 兼容端点**: GET `/v1/models` → `/models` → 根路径 GET。
3. **SSL 问题**: Windows 下 `urllib` 需要 `ssl._create_unverified_context()`。

**关键**: 不能假设所有端点都有 `/models` 接口。Anthropic 类端点只接受 POST，GET 一律 404。必须在分支里判断 URL 特征后走不同的探测路径。

## 测试结果中的多模态检测

测试连接返回所有字段均包含 `"is_multimodal": True/False`，由 `backend/utils/multimodal_detect.py` 根据模型名称自动判断：
- 前端展示测试结果时，若 `testResult.is_multimodal` 为真，在消息旁显示 🖼️ 多模态 badge
- 创建/保存模型配置时，后端 `is_multimodal_model(model)` 自动写入 `is_multimodal` 字段，用户无需手动标记
- 多模态模式涵盖：GPT-4o、Claude 3+、Gemini、Qwen-VL、Qwen3 系列、GLM-4V 等；`qwen3.7-plus` 等 qwen3 系列现已被识别
- 数据库 `is_multimodal` 字段若被人工设为 1，以数据库为准（覆盖自动检测）

## 前端 URL 输入提示

ConfigView.vue 的新增/编辑表单中 API Base URL 输入框下方有提示：
```
⚠️ 只需填根域名，不要手动加 /v1、/v1/models、/v1/messages，系统自动补全。
· OpenAI 兼容（GPT/Qwen/GLM 等）：填 https://api.openai.com 即可
· Anthropic 兼容（Claude/DeepSeek 等）：填 https://api.deepseek.com/anthropic 即可
```

## 聊天流接入

`backend/controller/agent_controller.py` 的 `get_current_model_config()` 读取顺序：
1. `model_configs` 表 `WHERE is_current=1 AND enabled=1`（最高优先级，新增的）
2. 旧的 `ModelConfigMapperImpl.get_active_model_config()`（依赖不存在的 `user_info` 表→回退）
3. `user_configs` 表 `llm_base_url/llm_api_key/llm_model`（`/api/config` 写入）
4. 环境变量 `LLM_BASE_URL/LLM_API_KEY/LLM_MODEL`

## 加密存储

```python
from backend.utils.crypto_utils import encrypt, decrypt

# 存储时加密（创建/更新）
encrypted_key = encrypt(api_key) if api_key else ""

# 读取时解密
api_key = decrypt(encrypted_key)

# 列表查询时脱敏
row["api_key"] = "***已配置***" if row.get("api_key") else ""
```
