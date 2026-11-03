# AgentForge API 接口文档

本文档描述所有 REST API 端点的请求参数、响应格式和权限要求。

## 聊天接口-SSE流式输出

聊天通过 Server-Sent Events 实现实时流式输出。

**端点**: `GET /chat/stream`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| message | string | 是 | 用户消息内容 |
| thread_id | string | 否 | 会话 ID，不传则创建新会话 |

**权限**: 所有已登录用户

**响应事件类型**:
- `start`: 对话开始，携带 thread_id
- `token`: 流式 token，携带增量文本
- `stream_reset`: 工具调用时清空旁白
- `chat_complete`: 对话完成
- `error`: 错误信息

**取消对话**: `GET /chat/cancel?thread_id=xxx`

**注意事项**:
- SSE 连接每 8 秒发送心跳保持连接
- 单个 thread 同时只能有一个活跃对话（ThreadBusyError）
- 断线后可用相同 thread_id 重连续传

## 知识库管理接口

知识库 CRUD 操作接口。

**创建知识库**: `POST /api/knowledge-bases`
```json
{"kb_name": "新知识库", "kb_type": "general", "description": "描述"}
```

**获取知识库列表**: `GET /api/knowledge-bases`
返回所有知识库及其文档数、chunk 数统计。

**上传文档**: `POST /api/knowledge-bases/{kb_id}/documents`
- Content-Type: multipart/form-data
- 支持格式：md、txt、pdf、docx
- 参数：file（文件）、chunk_strategy（fixed/parent_child）、chunk_size、chunk_overlap

**删除文档**: `DELETE /api/knowledge-bases/{kb_id}/documents/{doc_id}`

**重新处理文档**: `POST /api/knowledge-bases/{kb_id}/documents/{doc_id}/reprocess`
- 可切换切分策略（fixed ↔ parent_child）
- 重新切分后需要重新向量化

**权限**: kb.manage（知识库全部操作，含创建/文档管理）

## 技能管理接口

技能的 CRUD 操作，支持通过 API 和 LLM 两种方式管理。

**列出所有技能**: `GET /api/skills`
返回技能列表，每个技能包含 name、description、created_at。

**获取技能详情**: `GET /api/skills/{name}`
返回技能的完整内容（Markdown 格式）。

**创建技能**: `POST /api/skills`
```json
{
  "name": "my-skill",
  "content": "# 技能指令\n\n## 步骤\n1. ...\n2. ...",
  "description": "技能描述"
}
```

**更新技能**: `PUT /api/skills/{name}`
请求体同创建，完整替换内容。

**删除技能**: `DELETE /api/skills/{name}`

**权限**: 所有已登录用户可管理自己的技能

## 可观测性接口

LLM 调用链路追踪和统计分析。

**Dashboard 统计**: `GET /api/traces/dashboard`
返回：总调用次数、今日 token 消耗、模型分布、来源分布、错误率。

**Trace 列表**: `GET /api/traces`
返回当前用户的 trace 记录，支持分页和时间范围过滤。

**全部用户 Trace**: `GET /api/traces/all`
**权限**: trace.manage

**排行榜**: `GET /api/traces/ranking`
基于 `daily_user_stats` 预聚合表，返回 token 消耗排名。
**权限**: trace.ranking

**Trace 详情**: `GET /api/traces/{id}`
返回单次 LLM 调用的详细信息，包括 prompt_tokens、completion_tokens、latency_ms、关联的 tool spans。

**采集配置**: `GET/PUT /api/traces/config`
控制是否启用全量采集模式（保存用户提问和 AI 回复）。

## RAG测评接口

知识库检索质量评测的完整流程接口。

**创建测评集**: `POST /api/kb-eval/sets`
```json
{"name": "产品手册测评", "description": "验证父子切片的检索效果"}
```

**添加评测题目**: `POST /api/kb-eval/sets/{set_id}/items`
```json
{
  "question": "用户表有哪些字段？",
  "ground_truth_chunk_ids": [123, 124],
  "ground_truth_answer": "users 表包含 id, username, email, role, status 等字段"
}
```

**运行评测**: `POST /api/kb-eval/sets/{set_id}/run`
```json
{
  "top_k": 5,
  "generate_answer": true,
  "judge_enabled": true,
  "retriever_mode": "bm25",
  "chunk_kind": "child"
}
```

**对比多次运行**: `GET /api/kb-eval/runs/compare?ids=1,2,3`

**自动生成题目**: `POST /api/kb-eval/generate`
使用 LLM 从文档自动生成 Q&A 对，导入指定测评集。

**权限**: kb.eval

## 历史会话接口

对话历史查询和管理。

**会话列表**: `GET /api/history`
返回当前用户的所有会话，按最后活跃时间排序。

**消息历史**: `GET /api/history/{chat_id}`
返回指定会话的完整消息列表（用户消息 + AI 回复 + 工具调用记录）。

**删除会话**: `DELETE /api/history/{chat_id}`

**权限**: 所有已登录用户（只能访问自己的会话）
