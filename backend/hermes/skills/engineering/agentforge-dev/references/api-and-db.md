# AgentForge 数据库 & API 参考

## MySQL 表结构（agentforge 库，utf8mb4）

### conversations
| 列 | 类型 | 说明 |
|---|---|---|
| id | BIGINT PK | |
| session_id | VARCHAR(128) | 会话ID，格式 `{user_id}_{timestamp}` |
| user_id | BIGINT | |
| chat_mode | VARCHAR(32) DEFAULT 'normal' | 'normal' / 'ide' |
| user_question | TEXT | |
| agent_answer | LONGTEXT | |
| status | TINYINT | 1=正常, 2=异常, 3=用户中断, 4=进行中 |
| session_title | VARCHAR(255) | 用户自定义标题（重命名）；NULL 则用首条 user_question |
| metadata | JSON | |
| created_at / updated_at | DATETIME | |

### users
| 列 | 说明 |
|---|---|
| id, username, password, email | |
| role | super_admin / admin / user |

### user_configs
| 列 | 说明 |
|---|---|
| id, user_id, config_key, config_val | 如 llm_base_url, llm_api_key, llm_model |

### model_configs
| 列 | 说明 |
|---|---|
| id, user_id, config_name, config_type(URL/OLLAMA/LOCAL) | |
| api_url, api_key(加密), model_name | |
| is_current(TINYINT) | 全局唯一=1 为激活 |
| enabled, last_test_status/message/time | |

## API 端点速查

| 方法 | 路径 | 功能 | 文件 |
|---|---|---|---|
| GET/POST | /chat/stream | SSE 流式聊天 | chat_controller.py |
| GET | /api/history | 会话列表 | chat_controller.py |
| GET | /api/history/{chat_id} | 会话消息历史 | chat_controller.py |
| PUT | /api/history/{chat_id} | 重命名会话（session_title） | chat_controller.py |
| DELETE | /api/history/{chat_id} | 软删除会话（status=0） | chat_controller.py |
| GET | /api/data/sessions | 分页会话列表（支持 session_type=ide） | data_controller.py |
| DELETE | /api/data/sessions/{id} | 物理删除会话 | data_controller.py |
| GET/POST | /api/config | 读写 user_configs | config_controller.py |
| GET/POST | /api/model-configs | 模型配置列表/新增 | model_config_controller.py |
| PUT | /api/model-configs/{id} | 编辑配置 | model_config_controller.py |
| PUT | /api/model-configs/{id}/active | 设为当前激活 | model_config_controller.py |
| DELETE | /api/model-configs/{id} | 删除配置 | model_config_controller.py |
| POST | /api/model-configs/{id}/test | 测试连接（Anthropic/OpenAI 兼容） | model_config_controller.py |
| POST/GET | /api/ide/root | 设置/获取 IDE 根目录 | ide_controller.py |
| GET | /api/ide/tree | 目录树 | ide_controller.py |
| GET/PUT | /api/ide/file | 读/写文件 | ide_controller.py |
| POST/GET | /api/auth/login, /register, /me | 认证 | auth_controller.py |

## 前端 API helper 位置
- `src/api/chat.ts` — SSE 流式, getChatMessages, cancelStream
- `src/api/session.ts` — getUserSessions, deleteSession, renameSession
- `src/api/config.ts` — model-configs CRUD + 测试
- `src/api/ide.ts` — 文件树/读写/根目录
- `src/api/request.ts` — axios 实例, 自动注入 Bearer token（从 `localStorage.getItem('authToken')`）
