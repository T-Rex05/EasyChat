# 模型配置控制器：从零建表到前端列表+编辑+测试

## 背景

AgentForge 项目中 `ModelConfigMapperImpl` 虽然提供了完整 CRUD，但依赖两张不存在的表（`model_configs`/`user_info`），且管理员体系与当前登录的 `users` 表不兼容。需要自建一套干净的控制器。


## 完整流程模板

### 1. 建表（三处同步）

- **Powerful ALTER TABLE**：先在 MySQL 里 `CREATE TABLE IF NOT EXISTS model_configs (...)`
- **`backend/db/schema.py`**：在 MySQL 建表语句区追加 `CREATE TABLE IF NOT EXISTS model_configs (...)`
- 表字段建议：`user_id BIGINT, config_name VARCHAR, config_type VARCHAR, api_url VARCHAR, api_key VARCHAR(加密存储), model_name VARCHAR, is_current TINYINT, enabled TINYINT`

### 2. 控制器文件

创建 `backend/controller/model_config_controller.py`：

- `_get_conn()` — 直连 MySQL（从环境变量读参数），返回 `pymysql.connect(..., cursorclass=DictCursor, autocommit=True)`
- `router = APIRouter(prefix="/api/model-configs")`
- 鉴权：`from backend.service.auth_middleware import get_current_user`，关键操作用 `_is_admin(user) or has_permission(...)` 双重判断（admin 优先于 SQLite-based permission query，防止后者在 MySQL 模式下退化）
- API Key 加密：`from backend.utils.crypto_utils import encrypt/decrypt`。写入时 `encrypt(plaintext)`，读取时 `decrypt(ciphertext)`，列表接口返回 `"***已配置***"` 脱敏
- 关键端点：
  - `GET /` — 列表（api_key 脱敏）
  - `POST /` — 新增（加密 api_key，全局 `is_current` 置 0 后插入新行设 is_current=1）
  - `PUT /{id}` — 编辑（api_key 留空则不动密钥）
  - `PUT /{id}/active` — 设当前激活（全局 `is_current` 置 0 后 set 目标行）
  - `DELETE /{id}` — 删除
  - `POST /{id}/test` — 测试连接

### 3. 注册路由

在 `main.py` 中：

```python
from backend.controller.model_config_controller import router as mcfg_router
app.include_router(mcfg_router)
```

### 4. 打通聊天流

在 `backend/controller/agent_controller.py` 的 `get_current_model_config` 最前面插入最高优先级：

```python
try:
    conn = pymysql.connect(...)
    cur = conn.cursor()
    cur.execute("SELECT ... FROM model_configs WHERE is_current=1 AND enabled=1 LIMIT 1")
    row = cur.fetchone()
    if row:
        return {"config_type": ..., "api_url": ..., "api_key": decrypt(...), "model_name": ...}
except: pass  # 表不存在等回退
```

这样"系统配置"页面保存的模型立即成为聊天使用的模型。

### 5. 前端

- 新建 `agent_frontend/src/api/config.ts`（axios `request` 封装各端点）
- 重写 `ConfigView.vue` 的 LLM 卡片为列表 + 编辑态 + 新增表单 + 测试按钮
- 测试结果用 `v-if="testResult"` 展示 ok/fail 横幅

## 测试连接端点的多轮调试

因远端 API 端点协议多变，测试端点经历了四版迭代：

1. **第一版**：只试 `{base}/models` → OpenAI 兼容端点 OK，DeepSeek Anthropic 端点 GET 一律 404
2. **第二版**：试 `{base}/v1/models` + `{base}/models` + 根路径 → Anthropic 根路径也 404（只接受 POST）
3. **第三版**：检测 `/anthropic` 路径时发 POST 最小请求 → Windows 下 `urllib` SSL 证书报错（CA 不全/企业代理）
4. **第四版（最终）**：加 `ssl._create_unverified_context()` 绕过证书校验 + 对 Anthropic 端点发 POST `{"model":"...","max_tokens":1,"messages":[{"role":"user","content":"ping"}]}` 带 `x-api-key` + `Authorization: Bearer` 双鉴权头 + `anthropic-version: 2023-06-01`

关键教训：

- **不要只测 GET**：Anthropic 兼容端点仅接受 POST 消息，GET 任何路径都 404
- **x-api-key + Bearer 双鉴权**：DeepSeek 兼容 `x-api-key`，标准 Anthropic 需要 `x-api-key`，同时保留 `Authorization: Bearer` 兼容更多实现
- **SSL unverified context**：Windows `urllib` 在企业代理环境或 CA 不全时容易 SSL 报错，构造 `ssl._create_unverified_context()` 传给 `urlopen(context=ctx)`
- **URLError vs HTTPError**：`HTTPError` 说明服务器可达但有 HTTP 错误码（至少连通了），`URLError` 说明网络层根本没通（DNS/连接拒绝/SSL 握手失败）
