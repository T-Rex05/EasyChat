# EasyChat（原 AgentForge）

> 微信个人助手 + 超级代理：微信收需求 → 后台编码代理 → 自动 Draft PR → 微信回执。

## 当前架构（以此为准）

- 启动入口：`backend/server.py` → `backend/app.py`（工厂）→ `backend/bootstrap.py`（生命周期装配）。本地开发 `python main.py`（端口 8001）；生产入口 `docker/Dockerfile`（依赖 docker/requirements-core.txt + requirements-hermes.txt）。
- 存储：SQLite（`backend/platform/sqlite.py`，迁移在 `backend/platform/migrations/`，追加式、checksum 校验）。
- 后端模块：`backend/modules/`（access/assistant/channels/delivery/scheduling/superagent/files/ledger/memory/inbox/profiles/briefing/skills/evolution/models/usage）。
- 执行引擎：Hermes AIAgent 经 `backend/runtime/hermes/adapter.py` 适配（唯一 Seam 是 `backend/runtime/contracts.py`）。
- 前端：Vue 3 + Vite（`agent_frontend/`，`npm run dev` 端口 3000，`/api` 代理 8001）。
- 能力开关默认全关：`EASYCHAT_WECHAT_ENABLED` / `EASYCHAT_HERMES_ENABLED` / `EASYCHAT_EMAIL_ENABLED` 等，凭证加密依赖 `EASYCHAT_ENCRYPTION_SECRET`。

## 测试与构建

```powershell
python -m pytest tests -q -m "not integration and not resources"   # 全量维护套件
python -m pytest tests/superagent tests/contracts -q               # 定向
cd agent_frontend && npm run type-check && npm run build
```

---

# 以下为历史 AgentForge 文档（旧架构，已退役，仅作参考）

> ⚠️ 下文描述的 MySQL、Redis、Neo4j、GraphRAG、Code Mode、模型网关、KB RAG 等均属旧架构，当前代码库不再包含这些组件。请勿据此理解或恢复旧依赖。



> 基于 Hermes 的 AI Agent 服务框架 — 三层记忆（Episodic/Semantic/Neo4j）+ GraphRAG 知识图谱 + 安全审批 + 可观测性 + Docker 一键部署

---

## 核心特性

| 特性 | 说明 |
|---|---|
| **Hermes 决策引擎** | 进程内嵌入 Hermes AIAgent，单智能体自主循环 |
| **三层记忆系统** | Episodic（30天TTL）/ Semantic（永久晋升）/ Neo4j 图谱 + **写入前去重 + 矛盾检测 + 自动晋升 + TTL 淘汰** |
| **知识库 RAG** | 多格式文档解析（PDF/Markdown/Word）+ 父子切片 + 三种检索（BM25/向量/混合）+ **置信度门控** |
| **GraphRAG 知识图谱** | 文档实体自动提取 + Neo4j 知识图谱可视化 + 图遍历检索 + 三路混合召回 |
| **Code Mode 代码模式** | Agent 写 Python 组合调用工具 + **AST 安全检查 + 错误分类/自动修复/重试机制** + Token 节省 90%+ |
| **模型网关与路由** | **熔断器（CircuitBreaker）+ 降级链 + 场景路由** + 请求级模型选择 + TracedLLMClient 全链路追踪 |
| **Redis 缓存层** | **优雅降级（Redis→LRU）+ 三层一致性（主动失效/Outbox/TTL）+ Pub/Sub 多实例同步** |
| **容错执行引擎** | **go_safe 后台保护 + 状态机 + 重试机制 + Race Group 竞速执行** + 取消令牌 |
| **RAG 测评系统** | 分层评测（检索层 Recall@K/MRR + 生成层 RAGAS LLM 裁判）+ 七态分类 + 优化建议闭环 |
| **四维评测闭环** | 80 题四维评测（会话内/跨会话/混合检索/端到端）+ LLM Judge + 失败根因分析 + 6 项优化落地 |
| **安全审批体系** | 三层 RBAC（25 个权限）+ 主机白名单 + 命令黑名单 + 双人审核（SSE 广播） |
| **内容池审核** | 技能/工具发布需管理员审核（AST 白名单扫描）+ 审核人留痕 |
| **LLM 可观测性** | 三 Tab 面板（概览/排行榜/用户）+ Token 统计 + 调用链路追踪 |
| **Text2SQL** | 知识库自动提取 table_refs，辅助 SQL 生成 |
| **SSE 流式输出** | 实时推送 token，支持工具调用时的流式纠错 |
| **Hook 插件机制** | `ChatHooks` 可插拔钩子，pre_process/post_process/on_complete |
| **技能管理** | REST API + 文件系统，支持 LLM 和用户自主创建技能 |
| **多用户隔离** | 基于 contextvars 的记忆命名空间隔离 |
| **MySQL 业务库** | 连接池直连，启动时自动建表/迁移（31 张表） |
| **Docker 一键部署** | Dockerfile + docker-compose.yml |

---

## GraphRAG 知识图谱

AgentForge 集成了 GraphRAG 能力，支持从知识库文档中自动提取实体关系，构建知识图谱并提供可视化界面。

### 功能特性

- **实体自动提取**：LLM 分析文档内容，提取人物、组织、地点、概念、事件等实体
- **关系自动构建**：识别实体间的关联关系（RELATES_TO、PART_OF、CAUSES 等）
- **图谱可视化**：交互式图谱界面，支持搜索、筛选、聚焦子图
- **图遍历检索**：通过 Neo4j APOC 实现多跳关联检索
- **三路混合召回**：向量检索 + BM25 关键词 + 图遍历，RRF 融合排序

### 图谱可视化界面

访问「知识图谱」页面可：

- **智能加载**：点击「加载图谱」按钮主动加载，避免一次性加载过多节点导致卡顿
- **增量加载**：点击「加载更多节点」追加加载，自动融合到现有图谱
- **按类型筛选**：实体类型（人物/组织/地点/概念/事件等），支持多选
- **按关系筛选**：关系类型（认识/工作于/创立/使用/偏好等）
- **实时统计**：显示当前图谱中的节点数和关系数，筛选后自动更新
- **实体搜索**：搜索实体名称，自动加载相关子图
- **节点详情**：点击节点查看详情、关联实体、关联记忆
- **子图扩展**：双击节点聚焦扩展子图
- **实体列表**：右侧面板分页浏览所有实体，支持搜索和点击聚焦

### 性能优化

| 优化项 | 说明 |
|--------|------|
| **延迟加载** | 默认不自动加载，用户主动点击后加载 50 个节点 |
| **增量追加** | 支持追加加载更多节点，自动融合到现有图谱 |
| **物理引擎** | 高阻尼配置，节点快速稳定，减少漂移 |
| **初始分布** | 螺旋分布初始位置，避免节点从中心涌现 |
| **颜色分组** | 按实体类型自动着色，直观区分不同类型 |

### 实体类型与颜色

| 类型 | 说明 | 颜色 | 示例 |
|------|------|------|------|
| Person | 人物 | 🟢 绿色 | 张三、李经理 |
| Organization | 组织 | 🔵 蓝色 | 阿里云、技术部 |
| Location | 地点 | 🟠 橙色 | 北京、数据中心 |
| Concept | 概念 | 🟣 紫色 | 微服务、CI/CD |
| Event | 事件 | 🔴 红色 | 系统上线、故障恢复 |
| Project | 项目 | 🔷 靛蓝 | AgentForge、守护之眼 |
| Tool | 工具 | ⚫ 灰色 | Docker、Kubernetes |
| Skill | 技能 | 🔹 青色 | Python 开发、系统运维 |
| Fact | 事实 | 🟤 棕色 | 系统版本 2.0 |
| Preference | 偏好 | 💗 粉色 | 偏好 VS Code |

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/graph/stats` | 图谱统计（实体数/关系数） |
| `GET` | `/api/graph/user-graph` | 获取用户图谱数据（支持 limit 参数） |
| `GET` | `/api/graph/entities/{id}` | 获取实体详情 + 关联实体 + 关联记忆 |
| `GET` | `/api/graph/entities/search` | 搜索实体 |
| `GET` | `/api/graph/subgraph/{id}` | 获取实体子图 |
| `POST` | `/api/graph/documents/{id}/extract` | 提取文档实体 |
| `POST` | `/api/graph/documents/{id}/refresh` | 刷新文档实体（删除旧数据 + 重新提取） |
| `DELETE` | `/api/graph/documents/{id}/entities` | 清除文档实体 |

---

## 三层记忆系统

AgentForge 实现了基于 **Episodic（情景）/ Semantic（语义）/ Neo4j（图谱）** 的三层记忆架构，配合 **写入前去重、矛盾检测、自动晋升、TTL 淘汰** 等自动化机制，形成完整的记忆生命周期管理。

### 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                    AgentForgeMemoryProvider                      │
│  prefetch() / sync_turn() / system_prompt_block()              │
│  ├─ 意图分类 + 混合检索 + Reranker + 图扩展                     │
│  └─ 矛盾检测（发现矛盾偏好时提示 LLM 以最新为准）              │
└──────────────────────────┬──────────────────────────────────────┘
                           │
       ┌───────────────────┼───────────────────┐
       ▼                   ▼                   ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ Episodic    │    │ Semantic    │    │ Neo4j 图谱   │
│ (情景记忆)  │    │ (语义记忆)  │    │ (图增强)    │
│             │    │             │    │             │
│ • 30天TTL   │ →  │ • 永久存储   │    │ • FOLLOWS   │
│ • 写入前去重│    │ • 晋升而来   │    │ • SIMILAR_TO│
│ • 自动晋升  │    │ • 语义知识   │    │ • 跨层边     │
│ • TTL 淘汰  │    │             │    │             │
└─────────────┘    └─────────────┘    └─────────────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│              OutboxWorker（异步维护）                             │
│  ├─ 向量/图同步（MySQL → Milvus/Neo4j，幂等 upsert）           │
│  ├─ 自动晋升：importance ≥ 0.85 或 access_count ≥ 10 → 晋升    │
│  └─ TTL 淘汰：importance < 0.3 + 过期 + 未置顶 → 软删除         │
└─────────────────────────────────────────────────────────────────┘
```

### 记忆类型

| 类型 | 说明 | 示例 |
|------|------|------|
| **preference** | 用户偏好 | 喜欢用 Python 开发、偏好 VS Code 编辑器 |
| **fact** | 确认事实 | 用户是后端工程师、有 5 年经验 |
| **event** | 重要事件 | 2024 年 1 月参与微服务迁移项目 |
| **skill** | 学到的技能 | 掌握 Docker 和 Kubernetes 部署 |

### 记忆生命周期

```
用户对话 → sync_turn() 检查轮次
              ↓ 达到阈值
        LLM 提取记忆 (preference/fact/event/skill)
              ↓
        写入前去重（hybrid_search min_score=0.92）
        ├─ 存在相似 → 递增 access_count + 更新 importance，不新建
        └─ 不存在 → 新建 Episodic 记忆 + Outbox 事件
              ↓
        OutboxWorker 异步同步到 Milvus + Neo4j
              ↓
        定期维护（每 10 分钟）：
        ├─ 自动晋升：importance ≥ 0.85 → Semantic
        ├─ 自动晋升：access_count ≥ 10 AND importance ≥ 0.5 → Semantic
        └─ TTL 淘汰：importance < 0.3 + 过期 + 未置顶 → 软删除
              ↓
        Prefetch 时矛盾检测：
        ├─ 发现矛盾偏好 → 提示 LLM 以最新为准
        └─ 无矛盾 → 正常注入记忆到上下文
```

### 前端管理

访问「记忆管理」页面可：
- 按类型筛选记忆（偏好/事实/事件/技能）
- 语义搜索相关记忆
- 手动创建/编辑/删除记忆
- 查看图谱关联（Neo4j）
- 手动触发记忆合并
- 按重要度/时间排序筛选

### 自动记忆提取

Hermes 会在对话中自动提取值得记住的信息：

1. **轮次计数**：每 N 轮对话触发一次提取
2. **LLM 分析**：自动识别用户偏好、确认事实、重要事件、学到的技能
3. **向量化存储**：支持语义相似度检索
4. **图谱增强**：自动建立记忆间的关联关系

### 记忆一致性架构

AgentForge 实现了基于 **Outbox 模式 + 版本号 + 增量对账** 的记忆一致性架构，确保 MySQL（真相源）、Milvus（向量库）、Neo4j（图谱）三库数据的最终一致性。

#### 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                    MySQL 事务（原子性保证）                       │
│  ┌────────────────────┐    ┌──────────────────────────────┐    │
│  │ INSERT memory_items│ +  │ INSERT memory_outbox         │    │
│  │ (业务数据)         │    │ (向量/图同步事件)            │    │
│  └────────────────────┘    └──────────────────────────────┘    │
│                           要么都成功，要么都回滚                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                    Outbox Worker 异步消费
                              ↓
              ┌───────────────┼───────────────┐
              ↓               ↓               ↓
           Milvus          Neo4j         其他派生库
        (幂等 upsert)    (幂等 MERGE)
```

#### 核心组件

| 组件 | 文件 | 职责 |
|------|------|------|
| **Outbox Types** | `outbox_types.py` | 事件类型定义、内容哈希计算 |
| **Outbox Writer** | `outbox_writer.py` | 事务内写入事件 |
| **Outbox Worker** | `outbox_worker.py` | 异步消费事件，幂等处理 |
| **Reconciler** | `reconciler.py` | 增量对账，发现并修复差异 |

#### 一致性保证

| 层级 | 机制 | 说明 |
|------|------|------|
| **写入一致性** | Outbox 模式 | 业务数据 + 同步事件在同一事务提交 |
| **并发控制** | 版本号 + 乐观锁 | 每条记忆维护 `version`，更新时校验 |
| **幂等处理** | 版本校验 + MERGE | 派生库写入时检查版本，拒绝旧操作 |
| **故障恢复** | 重试 + 死信队列 | 失败事件指数退避重试，超限进死信 |
| **最终收敛** | 增量对账 | 每小时检查最近变化，发现差异生成修复事件 |

#### 对账策略

| 策略 | 频率 | 成本 | 说明 |
|------|------|------|------|
| **心跳检查** | 5 分钟 | 极低 | 对比 MySQL 和 Milvus 的记录数量 |
| **增量对账** | 1 小时 | 中等 | 检查最近 24 小时有变化的记忆 |
| **全量对账** | 每月 | 高 | 完整扫描所有记忆 + KG 去重（安全兜底） |

> **KG 去重说明**：实体提取使用 MERGE + hash-based ID 生成，同一 name+type 产生相同 ID，设计层面已防止重复。去重检测仅在全量对账中执行，作为安全兜底。

#### 数据库字段

```sql
-- memory_episodic 新增字段
version BIGINT NOT NULL DEFAULT 1,        -- 版本号
content_hash VARCHAR(64) NOT NULL,        -- 内容哈希（对账用）
deleted_at DATETIME DEFAULT NULL,         -- 软删除时间
promoted_to_semantic TINYINT DEFAULT 0,   -- 是否已晋升到 Semantic
is_user_pinned TINYINT DEFAULT 0          -- 用户置顶（豁免淘汰）

-- memory_outbox 表（同步事件队列）
event_id VARCHAR(36) NOT NULL UNIQUE,     -- 事件唯一 ID
memory_id BIGINT NOT NULL,                -- 关联记忆 ID
memory_version BIGINT NOT NULL,           -- 事件版本
event_type VARCHAR(32) NOT NULL,          -- upsert_vector/delete_vector/...
target VARCHAR(16) NOT NULL,              -- milvus/neo4j
status VARCHAR(16) NOT NULL DEFAULT 'pending',  -- 状态
attempts INT NOT NULL DEFAULT 0           -- 重试次数
```

---

## 记忆自动化维护（基于评测反馈优化）

经过 80 题四维评测（A/B/C/D，通过率 78%）定位短板后，新增了 6 项自动化维护机制：

### 写入前去重

```
create_episodic() 入口
    ↓
hybrid_search(user_id, content, top_k=3, min_score=0.92)
    ├─ 存在高相似度 → 递增 access_count + 更新 importance → 返回 existing_id
    └─ 不存在 → 正常创建
```

> 修复了评测 B2-01（重复写入「喜欢喝咖啡」导致记忆膨胀）问题。

### 矛盾检测（Prefetch 阶段）

```python
# 预取 Top 8 条记忆中，检测是否存在矛盾对
_CONTRADICTORY_PAIRS = [
    ("喜欢", "不喜欢"), ("偏好", "不偏好"), ("表格", "列表"), ...
]

def _is_potentially_contradictory(text_a: str, text_b: str) -> bool:
    """基于反义关键词 + token 重叠判断是否可能矛盾"""
```

发现矛盾后，prefetch 输出末尾追加：
```
⚠️ 注意：以上记忆中存在可能矛盾的信息，请以最近更新的为准。
```

> 修复了评测 B1-02（偏好冲突时 Agent 无法判断哪条最新）问题。

### 自动晋升（OutboxWorker 定期维护）

每 10 分钟执行一次，两种晋升条件（OR 关系）：

| 条件 | 阈值 | 理由 |
|------|------|------|
| 高重要性 | `importance_score >= 0.85` | 明确的高价值知识 |
| 高频访问 + 中等重要性 | `access_count >= 10 AND importance_score >= 0.5` | 经过验证的常用知识 |

晋升流程：复制内容到 Semantic 表 → Outbox 同步向量/图 → Episodic 标记 `promoted_to_semantic=1`

> 修复了评测 B3-01/03（高重要性/高频访问记忆未晋升）问题。

### TTL 淘汰（OutboxWorker 定期维护）

淘汰条件（全部满足才淘汰）：
- `importance_score < 0.3`（低价值）
- `expires_at < NOW()`（已过期）
- `is_user_pinned = 0`（非置顶）

淘汰执行：三层清理（向量 → KGStore → GraphMemory）→ MySQL 软删除

> 修复了评测 B4-02（低重要性过期记忆未淘汰）问题。

### 系统提示词反幻觉规则

在 `backend/agents/prompts.py` 新增 4 个规则段：

| 规则段 | 解决的问题 |
|--------|-----------|
| **记忆使用规则** | 禁止编造记忆、禁止编造评分、完整引用细节、代词消解、矛盾偏好处理 |
| **任务状态判断规则** | 「当前任务」≠「Todo 列表」；空 Todo 不等于无任务；区分执行进度 vs 系统建设进度 |
| **数据范围规则** | 区域数据需先确认范围；全局数据不能当区域数据；项目进度以记忆为准而非 Todo |

> 修复了评测 B3-01/02/03 + B4-02/03（Agent 幻觉）、A4-01/02（任务状态混淆）、D2-01（区域数据错误）等问题。

### Graph 检索降级

```
GraphRetriever.retrieve(query)
    ├─ Neo4j 正常返回 → 返回结果
    ├─ Neo4j 返回 0 条 → 降级到 HybridRetriever
    └─ Neo4j 异常 → 降级到 HybridRetriever
```

> 修复了评测 C 系列（Graph 模式全部返回 0）的可用性问题。

---

## Code Mode 代码模式

AgentForge 实现了类似 Claude Code / Cursor 的 Code Mode，让 Agent 写 Python 代码组合调用工具，大幅提升效率并降低 Token 消耗。

### 核心特性

| 特性 | 说明 |
|------|------|
| **批量操作** | search_files/read_file 支持列表参数，一次调用搜索/读取多个目标 |
| **AST 安全检查** | 禁止 import/eval/exec/open 等危险操作，含属性访问检测 |
| **错误分类** | 区分语法错误/运行时错误/超时，针对性处理 |
| **自动修复** | 语法错误自动重试（最多 2 次），修复常见拼写/参数问题 |
| **多用户隔离** | 通过 `copy_context()` 传递 contextvars，保证用户数据隔离 |
| **Token 节省** | 理想场景节省 90%+ Token（12 次调用 300K → 2 次调用 24K） |

### 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                    run_python 工具                                │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐ │
│  │ AST 静态检查 │  │ 受限 globals │  │ safe_print 输出截断     │ │
│  │ (禁止危险   │  │ (SAFE_BUILTINS│  │ (单次 16K + 总计 32K)   │ │
│  │  操作)      │  │  + 工具白名单)│  │                         │ │
│  └─────────────┘  └──────────────┘  └─────────────────────────┘ │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    _ToolWrapper 监控层                            │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐ │
│  │ 调用次数统计 │  │ 大输出告警   │  │ 执行耗时监控            │ │
│  └─────────────┘  └──────────────┘  └─────────────────────────┘ │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    工具函数（白名单）                              │
│  search_files / read_file / knowledge_search / sql_query / ...   │
│  （只读工具 + 业务写入工具，不暴露 terminal/文件写入等危险工具）   │
└─────────────────────────────────────────────────────────────────┘
```

### 使用示例

```python
# 第 1 次 run_python：批量搜索
patterns = ["milvus", "vector", "schema"]
print(search_files(patterns))  # 一次搜索多个模式

# 第 2 次 run_python：批量读取
files = ["file1.py", "file2.py", "file3.py"]
print(read_file(files))        # 一次读取多个文件
```

---

## 模型网关与路由

AgentForge 实现了企业级 LLM 模型网关，支持熔断器、降级链、场景路由，确保 LLM 服务的高可用性。

### 核心组件

| 组件 | 说明 |
|------|------|
| **CircuitBreaker** | 每模型独立熔断器，三态状态机（closed/open/half_open） |
| **ModelGateway** | 配置选择器，按 is_current 排序，跳过熔断中的配置 |
| **ModelRouter** | 路由器，支持用户指定/场景路由/默认/降级链/fail-open |
| **TracedLLMClient** | 全链路追踪客户端，集成 TraceObserver 钩子 |

### 熔断器状态机

```
closed ──连续失败≥阈值──→ open ──冷却超时──→ half_open
                                               │
                                    ┌──成功──→ closed
                                    └──失败──→ open (重新计时)
```

### 路由优先级

1. 用户手动指定 model_id → 直接返回
2. 场景路由 scene → 查 model_route_settings
3. 默认 is_current → 经 ModelGateway 熔断器检查
4. 降级链 → 按配置顺序逐个尝试
5. fail-open → 全部熔断时强制返回 is_current

---

## Redis 缓存层

AgentForge 实现了统一的 Redis 缓存抽象层，支持优雅降级、三层一致性保障、Key 规范。

### 设计原则

| 原则 | 说明 |
|------|------|
| **优雅降级** | Redis 不可用时自动 fallback 到 FallbackCache（进程内 LRU + TTL） |
| **统一抽象** | 业务代码通过 `RedisClient` 访问缓存，不直接调用 redis-py |
| **Key 规范** | `agentforge:{module}:{entity}:{id}` 命名空间，避免 key 冲突 |
| **非强依赖** | Redis 初始化失败不阻止应用启动，降级为本地缓存 |

### 三层一致性保障

| 层级 | 机制 | 说明 |
|------|------|------|
| **主动失效** | 写入时删除相关缓存 | 保证写后立即读的一致性 |
| **Outbox 同步** | 业务数据 + 缓存事件同一事务 | 异步更新缓存，最终一致性 |
| **TTL 兜底** | 每条缓存独立 TTL | 防止脏数据长期存在 |

### 优雅降级机制

```
RedisClient.is_available
    │
    ├─ True  → 读写 Redis（redis-py）
    │          同时写入 FallbackCache（热备份）
    │
    └─ False → 读写 FallbackCache（进程内 LRU）
               自动尝试重连（30s 间隔）
```

---

## 容错执行引擎

AgentForge 实现了企业级容错执行机制，包括后台线程保护、状态机、重试机制、竞速执行。

### 容错设计原则

| 原则 | 说明 | 实现方式 |
|------|------|----------|
| **隔离性** | 后台任务异常不影响主流程 | `go_safe` 包装器捕获所有异常 |
| **幂等性** | 同一请求可重复处理 | `client_msg_id` 去重 + 断线续传 |
| **可观测性** | 任务状态可追踪 | 状态机 + 日志记录 |
| **优雅降级** | 核心依赖不可用时降级 | Milvus → ChromaDB fallback |
| **资源保护** | 防止资源泄漏/堆积 | TTL 超时 + LRU 淘汰 |

### 核心组件

| 组件 | 说明 |
|------|------|
| **go_safe** | 后台线程保护，捕获所有异常防止进程崩溃 |
| **NodeStatus** | 六态状态机（pending/running/success/failed/cancelled/timeout） |
| **CancelToken** | 取消令牌，支持优雅取消正在执行的任务 |
| **Race Group** | 竞速执行，多个候选中取最快成功的 |
| **重试机制** | 可配置重试次数和延迟，支持指数退避 |

### 防御层次

```
┌─────────────────────────────────────────────────────────────────┐
│                     请求入口层                                    │
│  幂等去重 (msg_id) │ 并发控制 (ThreadBusy) │ 参数校验 (Pydantic)  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     执行层                                        │
│  重试机制 (max_retries) │ 超时控制 (timeout) │ 取消检测 (CancelToken)│
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     后台任务层                                    │
│  go_safe (panic recover) │ 异常捕获 (try-except) │ 日志追踪       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 评测结果（2026-09-07）

### 四维评测概览

| 维度 | 题目数 | 通过数 | 通过率 | 平均分 |
|------|--------|--------|--------|--------|
| A. 会话内记忆 | 14 | 10 | 71% | 3.6/5.0 |
| B. 跨会话记忆 | 19 | 10 | 53% | 3.5/5.0 |
| C. 混合检索 | 30 | 27（API可用） | 90% | - |
| D. 端到端综合 | 17 | 15 | 88% | 3.8/5.0 |
| **合计** | **80** | **62** | **78%** | - |

### 失败根因分布

| 根因类型 | 影响题数 | 状态 |
|----------|---------|------|
| Agent 幻觉（编造记忆/评分） | 7 | ✅ 已优化（prompt 反幻觉规则） |
| 任务状态 vs Todo 混淆 | 3 | ✅ 已优化（任务状态判断规则） |
| Prefetch 记忆选择偏差 | 4 | 🟡 部分优化（矛盾检测） |
| 系统功能缺失（晋升/遗忘/去重） | 5 | ✅ 已补齐 |
| 代词消解推理不足 | 1 | ✅ 已优化（代词消解规则） |

> 详细评测报告：[eval/report/eval_report.md](eval/report/eval_report.md)
> 失败分析与优化方案：[eval/report/failure_analysis.md](eval/report/failure_analysis.md)

---

## 架构总览

```
┌───────────────────────────────────────────────────────────────┐
│                        浏览器 / 客户端                          │
│               agent_frontend/ (Vue 3 + Vite 前端)              │
└──────────────────────────┬────────────────────────────────────┘
                           │ SSE (EventSource)
                           ▼
┌───────────────────────────────────────────────────────────────┐
│                      FastAPI 应用 (main.py)                    │
│                                                               │
│  ┌─────────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │  静态文件服务    │  │ /health      │  │ /chat/stream     │ │
│  │  / (前端页面)   │  │ 健康检查      │  │ SSE 流式聊天     │ │
│  └─────────────────┘  └──────────────┘  └───────┬──────────┘ │
│                                                  │            │
│  ┌───────────────────────────────────────────────┴──────────┐ │
│  │              chat_controller.py (核心控制器)              │ │
│  │  ┌───────────────┐  ┌──────────────┐  ┌──────────────┐  │ │
│  │  │ Hook 预处理   │  │ Hermes 调用  │  │ Hook 后处理  │  │ │
│  │  │ pre_process   │  │ runtime.run  │  │ post_process │  │ │
│  │  └───────┬───────┘  └──────┬───────┘  └──────┬───────┘  │ │
│  │          │                 │                  │          │ │
│  │  ┌───────┴─────────────────┴──────────────────┴───────┐  │ │
│  │  │           stream_runner.py (SSE 解耦层)            │  │ │
│  │  │     RunRegistry: 幂等去重 / 断线续传 / 串行控制    │  │ │
│  │  └────────────────────────────────────────────────────┘  │ │
│  └──────────────────────────────────────────────────────────┘ │
│                           │                                    │
│  ┌────────────────────────┴──────────────────────────────────┐ │
│  │              hermes_adapter.py (Hermes 适配层)            │ │
│  │  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐ │ │
│  │  │ 用户缓存    │  │ 会话恢复     │  │ 记忆隔离         │ │ │
│  │  │ (user_id,   │  │ (state.db)   │  │ (contextvars)    │ │ │
│  │  │  thread_id) │  │              │  │                  │ │ │
│  │  └─────────────┘  └──────────────┘  └──────────────────┘ │ │
│  │  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐ │ │
│  │  │ 工具注册    │  │ 技能播种     │  │ 流式纠错         │ │ │
│  │  │ ToolRegistry│  │ seed_skills  │  │ stream_reset     │ │ │
│  │  └─────────────┘  └──────────────┘  └──────────────────┘ │ │
│  └──────────────────────────────────────────────────────────┘ │
│                           │                                    │
│  ┌────────────────────────┴──────────────────────────────────┐ │
│  │              Hermes AIAgent (backend/hermes/)             │ │
│  │  ┌─────────┐  ┌────────┐  ┌────────┐  ┌──────────────┐  │ │
│  │  │ LLM 调用│  │ 工具   │  │ 记忆   │  │ 技能系统     │  │ │
│  │  │ (OpenAI/ │  │ 执行   │  │ MEMORY │  │ skills/      │  │ │
│  │  │  Anthro- │  │ (终端/ │  │ .md    │  │ SKILL.md     │  │ │
│  │  │  pic)    │  │  文件) │  │        │  │              │  │ │
│  │  └─────────┘  └────────┘  └────────┘  └──────────────┘  │ │
│  └──────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

## 请求流程

```
1. 用户发送消息 → GET /chat/stream?message=xxx&thread_id=xxx

2. chat_controller 处理:
   ├─ 解析 thread_id → user_id
   ├─ 创建 Hook 上下文 (ChatHookContext)
   ├─ 执行 pre_process 钩子（业务域守卫/RAG增强等）
   ├─ 入口即落库（status=4 进行中）
   └─ 调用 HermesRuntime.run()

3. HermesRuntime.run():
   ├─ 恢复会话历史 (_recover_session_history from state.db)
   ├─ 在线程池执行 run_conversation()
   │   └─ Hermes 核心循环:
   │       ├─ LLM 调用 → 检查 tool_calls
   │       ├─ 执行工具 → 返回结果
   │       └─ 继续 LLM 调用...
   └─ 通过 stream_callback 实时推送 token 到 thread_queue

4. stream_runner 消费 thread_queue → 推送 SSE 事件:
   ├─ start: 会话开始（含 conversation_id）
   ├─ token: 文本增量
   ├─ stream_reset: 清空已渲染内容（工具调用纠错）
   ├─ chat_complete: 对话结束（含完整响应）
   └─ retry: 86400000 (压制浏览器自动重连)
```

---

## 核心组件

| 文件 | 职责 |
|---|---|
| `hermes_adapter.py` | Hermes AIAgent 运行时封装，用户缓存/记忆隔离/工具注册/流式纠错 |
| `controller/chat_controller.py` | SSE 流式聊天端点，Hook 集成，对话持久化 |
| `controller/stream_runner.py` | SSE 解耦层（RunRegistry），幂等去重/断线续传/串行控制 |
| `hooks/__init__.py` | ChatHooks 插件机制，pre_process/post_process/on_complete/on_error |
| `db/` | 数据层（MySQL 连接池 + 自动建表，完整建表脚本见 `sql/agentforge_schema.sql`） |
| `service/skill_service.py` | 技能管理 CRUD（直接操作 HERMES_HOME/skills/ 文件系统） |
| `service/run_registry.py` | SSE run 生命周期管理（ThreadBusyError 串行控制） |
| `tools/tools_decorator.py` | 项目自定义工具定义（`@tool` + `get_project_tools()`） |
| `agents/prompts.py` | 系统提示词管理（`get_decision_system_prompt()`） |

---

## 快速开始

### 本地开发

```bash
# 1. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY 和 MySQL 连接信息（MYSQL_HOST/PORT/DATABASE/USER/PASSWORD）

# 4. 初始化数据库（首次：建库建表 + 默认数据）
mysql -u root -p < sql/agentforge_schema.sql

# 5. 启动（启动时也会自动建表/迁移，幂等安全）
python main.py
# 访问 http://localhost:8001/
```

> 💡 业务数据使用 **MySQL**（连接池直连）；Hermes 自身的会话/记忆存于 SQLite（`backend/hermes/.home/state.db`），无需手动初始化。

### Docker 部署

```bash
cp docker/.env.example .env
# 编辑 .env，填入 LLM_API_KEY

cd docker && docker compose up -d
# 访问 http://localhost:8001/
# 健康检查: curl http://localhost:8001/health
```

---

## 添加自定义工具

编辑 `backend/tools/tools_decorator.py`：

```python
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class WeatherInput(BaseModel):
    city: str = Field(description="城市名称")

@tool(args_schema=WeatherInput)
def get_weather(city: str) -> str:
    """获取天气信息。当用户询问天气时调用。"""
    return f"{city}：晴，25°C"

# 注册到工具列表
def get_project_tools() -> list:
    return [get_current_time, todo_add, todo_update, todo_get, get_weather]
```

重启服务后，Hermes LLM 即可自动调用 `get_weather`。

---

## 添加业务逻辑（Hook 插件）

```python
# my_hooks.py
from backend.hooks import ChatHooks, ChatHookContext

def my_pre_process(ctx: ChatHookContext) -> ChatHookContext:
    # 消息预处理（业务域守卫、RAG 增强等）
    return ctx

def my_post_process(ctx: ChatHookContext, response: str) -> str:
    # 响应后处理（格式化、注入额外信息）
    return response

my_hooks = ChatHooks(
    pre_process=my_pre_process,
    post_process=my_post_process,
)
```

在 `main.py` 的 `create_app()` 中注册：
```python
from my_hooks import my_hooks
from backend.hooks import register_hooks
register_hooks(my_hooks)
```

---

## API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/chat/stream` | SSE 流式聊天（参数: `message`, `thread_id`, `client_msg_id`） |
| `GET/POST` | `/chat/cancel` | 取消正在进行的对话 |
| `GET` | `/api/auth` | 登录 / 当前用户信息 |
| `GET` | `/api/skills` | 列出所有技能 |
| `GET` | `/api/skills/{name}` | 获取技能详情 |
| `POST` | `/api/skills` | 创建技能 |
| `PUT` | `/api/skills/{name}` | 更新技能 |
| `DELETE` | `/api/skills/{name}` | 删除技能 |
| `GET` | `/api/categories` | 技能分类 |
| `GET` | `/api/memories` | 记忆列表（支持类型过滤、用户筛选） |
| `GET` | `/api/memories/stats` | 记忆统计 |
| `POST` | `/api/memories` | 创建记忆（自动向量化） |
| `PUT` | `/api/memories/{id}` | 更新记忆 |
| `DELETE` | `/api/memories/{id}` | 删除记忆 |
| `POST` | `/api/memories/search` | 语义搜索记忆 |
| `GET` | `/api/memories/{id}/graph` | 获取记忆的图谱关联 |
| `POST` | `/api/memories/consolidate` | 手动触发记忆合并 |
| `GET` | `/api/memories/users` | 获取有记忆的用户列表（管理员） |
| `GET` | `/api/history` | 聊天会话列表 |
| `GET` | `/api/history/{chat_id}` | 特定对话的消息历史 |
| `GET` | `/api/todos` | 当前会话任务清单 |
| `GET/PUT` | `/api/traces/config` | 观测采集配置 |
| `GET` | `/api/traces/dashboard` | 可观测性概览统计 |
| `GET` | `/api/traces` | 当前用户 trace 列表 |
| `GET` | `/api/traces/all` | 全部用户 trace（trace.manage） |
| `GET` | `/api/traces/ranking` | Token 消耗排行榜（trace.ranking） |
| `GET` | `/api/traces/users/search` | 搜索用户（trace.manage） |
| `GET` | `/api/traces/{id}` | trace 详情 + spans |
| `GET/POST` | `/api/kb` | 知识库文档列表 / 上传解析 |
| `DELETE` | `/api/kb/{id}` | 删除知识库文档 |
| `GET/POST` | `/api/kb/eval-sets` | RAG 测评集 CRUD |
| `GET/POST` | `/api/kb/eval-runs` | 发起/查看 RAG 测评运行 |
| `GET/POST/PUT/DELETE` | `/api/model-configs` | 模型配置 CRUD + 测试连接 |
| `GET` | `/api/tools` | 工具列表 / 启停 |
| `GET/POST/PUT/DELETE` | `/api/cron-jobs` | 定时任务 CRUD + 执行记录（用户隔离，只能看到自己的任务） |
| `GET` | `/api/admin` | 用户/角色/权限管理 |
| `GET/PUT` | `/api/platform-config` | 平台配置 |
| `GET/POST` | `/api/email-configs` | 邮件服务配置 |
| `GET/POST` | `/api/personal-emails` | 个人邮箱绑定 |
| `GET/POST` | `/api/user-bindings` | 微信等渠道绑定 |
| `GET` | `/health` | 健康检查（Docker 用） |
| `GET` | `/docs` | OpenAPI 自动文档（Swagger UI） |

---

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LLM_BASE_URL` | `https://api.openai.com/v1` | LLM API 地址（支持任何 OpenAI 兼容接口） |
| `LLM_API_KEY` | (必填) | LLM API Key |
| `LLM_MODEL` | `gpt-4` | 模型名称 |
| `MYSQL_HOST` | `localhost` | MySQL 主机（业务数据库，必需） |
| `MYSQL_PORT` | `3306` | MySQL 端口 |
| `MYSQL_DATABASE` | `agentforge` | MySQL 数据库名 |
| `MYSQL_USER` | `root` | MySQL 用户名 |
| `MYSQL_PASSWORD` | (空) | MySQL 密码 |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j 连接地址（图增强，可选） |
| `NEO4J_USERNAME` | `neo4j` | Neo4j 用户名 |
| `NEO4J_PASSWORD` | (空) | Neo4j 密码 |
| `MILVUS_HOST` | `localhost` | Milvus 向量库地址（可选） |
| `MILVUS_PORT` | `19530` | Milvus 端口 |
| `MEMORY_DELAY_ROUNDS` | `10` | 记忆提取轮次阈值 |
| `MEMORY_TTL_DAYS` | `60` | 记忆默认存活天数 |
| `MEMORY_AUTO_PROMOTE_THRESHOLD` | `0.85` | 自动晋升 importance 阈值 |
| `CONTEXT_STRATEGY` | `default` | 上下文压缩策略（default/fact_anchor/none） |
| `AGENT_SYSTEM_PROMPT` | (内置) | 自定义系统提示词（覆盖默认） |
| `AGENTFORGE_DATA_DIR` | (自动) | 数据目录（Hermes state/skills） |
| `AGENTFORGE_LOG_DIR` | `./logs` | 日志目录 |
| `PORT` | `8001` | 服务端口 |
| `ALLOWED_ORIGINS` | `*` | CORS 允许的来源（逗号分隔） |

---

## 项目结构

```
AgentForge/
├── main.py                         # FastAPI 入口 + 路由注册
├── requirements.txt                # Python 依赖
├── sql/                            # 数据库脚本
│   └── agentforge_schema.sql       #   完整 MySQL 建表脚本（31 张表 + 默认数据）
│
├── docker/                         # Docker 部署（统一管理）
│   ├── Dockerfile                  #   多阶段构建（前端 + 后端）
│   ├── docker-compose.yml          #   完整编排（agentforge + MySQL + Neo4j + Milvus）
│   ├── .env.example                #   环境变量模板
│   └── README.md                   #   部署说明
│
├── backend/
│   ├── hermes_adapter.py           # ★ Hermes 适配层（核心）
│   ├── agent.py                    # 分析工作流模板
│   ├── config.py                   # 配置管理
│   │
│   ├── memory/                     # ★ 三层记忆系统
│   │   ├── agentforge_provider.py  #   Hermes MemoryProvider 实现
│   │   │                           #   （含 prefetch 矛盾检测 + task_state 注入）
│   │   ├── graph_memory.py         #   Neo4j 图增强层（GraphMemory）
│   │   ├── consolidator.py         #   三阶段合并器
│   │   └── types.py                #   记忆类型定义
│   │
│   ├── context/                    # ★ 会话内上下文压缩策略
│   │   ├── factory.py              #   策略工厂（STRATEGIES 注册表）
│   │   ├── task_state.py           #   会话级任务状态维护（TaskStateMaintainer）
│   │   └── strategies/             #   压缩策略实现
│   │       ├── default.py          #   透传 Hermes 默认
│   │       └── fact_anchor.py      #   事实锚定（压缩前提取关键事实）
│   │
│   ├── controller/                 # API 控制器
│   │   ├── chat_controller.py      #   ★ SSE 流式聊天 + Hook 集成
│   │   ├── stream_runner.py        #   SSE 解耦层（RunRegistry）
│   │   ├── agent_controller.py     #   模型配置读取
│   │   ├── skill_controller.py     #   技能管理 REST API
│   │   ├── memory_items_controller.py  # ★ 三层记忆管理 API
│   │   ├── conversation_controller.py  # 会话历史管理
│   │   ├── file_controller.py      #   附件处理
│   │   └── utils_controller.py     #   通用工具函数
│   │
│   ├── hooks/                      # ★ 插件钩子系统
│   │   └── __init__.py             #   ChatHooks / ChatHookContext
│   │
│   ├── db/                         # 数据层（MySQL 连接池）
│   │   ├── __init__.py             #   工厂函数 + 抽象接口
│   │   ├── connection_pool.py      #   统一连接池（DBUtils.PooledDB）
│   │   ├── conversation_store.py   #   对话持久化
│   │   ├── memory_mapper.py        #   ★ 记忆数据访问层
│   │   ├── schema.py               #   自动建表 + 增量迁移
│   │   └── mysql_impl.py           #   MySQL mapper
│   │
│   ├── service/                    # 服务层
│   │   ├── skill_service.py        #   技能 CRUD
│   │   ├── memory/                 #   ★ 记忆服务（完整）
│   │   │   ├── memory_service.py   #   记忆 CRUD + 写入前去重 + 混合检索
│   │   │   ├── memory_consolidator.py  # 记忆合并（矛盾检测+LLM融合+降级）
│   │   │   ├── memory_evaluator.py     # 记忆评估服务
│   │   │   ├── outbox_types.py     #   Outbox 事件类型定义
│   │   │   ├── outbox_writer.py    #   事务内写入 Outbox 事件
│   │   │   ├── outbox_worker.py    #   ★ 异步消费 + 自动晋升 + TTL 淘汰
│   │   │   └── reconciler.py       #   增量对账（MySQL→Milvus/Neo4j）
│   │   ├── kb/                     #   知识库服务（13 文件）
│   │   └── run_registry.py         #   SSE 会话管理
│   │
│   ├── tools/                      # 工具定义
│   │   ├── tools_decorator.py      #   ★ 自定义工具（在此添加）
│   │   ├── code_executor.py        #   Code Mode（Python 沙箱执行）
│   │   ├── text_to_sql.py          #   Text2SQL（自然语言转 SQL）
│   │   └── data_visualization.py   #   数据可视化（图表生成，未注册）
│   │
│   ├── agents/                     # Agent 配置
│   │   └── prompts.py              #   ★ 系统提示词（含反幻觉/任务状态/数据范围规则）
│   │
│   ├── impl/                       # 数据映射层
│   │   ├── conversation_mapper_impl.py
│   │   └── model_config_mapper_impl.py
│   │
│   ├── prompts/                    # 提示词模板
│   │   └── agent_core_prompt.py    #   Agent 能力说明
│   │
│   ├── utils/                      # 工具类
│   │   ├── log_utils.py            #   日志（loguru）
│   │   ├── model_manager.py        #   LLM 实例构建
│   │   ├── port_killer.py          #   端口清理
│   │   ├── time_utils.py           #   时间工具
│   │   ├── todo_parser.py          #   任务解析
│   │   └── token_counter.py        #   Token 计数
│   │
│   └── hermes/                     # Hermes 框架（第三方，不修改）
│       ├── run_agent.py            #   AIAgent 主类
│       ├── agent/                  #   Agent 核心逻辑
│       ├── tools/                  #   内建工具（89 个）
│       ├── skills/                 #   默认技能
│       └── plugins/                #   插件存根
│
├── eval/                           # ★ 四维评测系统
│   ├── dataset/                    #   评测数据集（A/B/C/D 四维度）
│   ├── eval_runner.py              #   评测执行器（SSE 调用 + LLM Judge）
│   ├── generate_report.py          #   报告生成器
│   └── report/                     #   评测报告输出
│       ├── eval_report.md          #   完整评测报告
│       ├── failure_analysis.md     #   失败案例根因分析
│       └── pred_*.jsonl            #   各维度预测结果
│
├── agent_frontend/                 # 前端（Vue 3 + Vite，唯一前端实现）
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.ts / App.vue       #   入口
│       ├── router/                 #   路由
│       ├── api/                    #   API 客户端
│       │   └── memoryItems.ts      #   ★ 记忆管理 API 客户端
│       ├── components/             #   Vue 组件
│       ├── views/                  #   页面视图
│       │   └── MemoryItemsView.vue #   ★ 记忆管理页面
│       └── styles/                 #   设计系统（Arco Design 风格）
│
└── static/                         # 静态资源
    └── charts/                     #   生成的图表（运行时产物）
```

---

## 技术栈

| 组件 | 技术 |
|---|---|
| Web 框架 | FastAPI + uvicorn |
| Agent 引擎 | Hermes AIAgent（进程内嵌入） |
| LLM 接口 | OpenAI 兼容 API（langchain-openai）+ **TracedLLMClient 全链路追踪** |
| **模型网关** | **CircuitBreaker 熔断器 + 降级链 + 场景路由** |
| **Redis 缓存** | **redis-py + FallbackCache（LRU）+ Pub/Sub 多实例同步** |
| **Code Mode** | **AST 安全检查 + 错误分类/自动修复/重试 + contextvars 隔离** |
| **容错引擎** | **go_safe + NodeStatus 状态机 + CancelToken + Race Group** |
| 流式通信 | SSE (EventSource) + RunRegistry 断线续传 |
| 工具定义 | LangChain `@tool` + Pydantic Schema |
| 记忆隔离 | `contextvars` + Hermes MemoryStore |
| 会话持久化 | 业务数据 MySQL（连接池）；Hermes 会话/记忆 `state.db` (SQLite) |
| 向量检索 | Milvus / ChromaDB（双路召回之一） |
| 图数据库 | Neo4j（GraphRAG + 图增强 + 社区检测） |
| 记忆架构 | Episodic（30天TTL）+ Semantic（永久晋升）+ Neo4j 图谱 |
| 记忆维护 | OutboxWorker 异步消费 + 自动晋升 + TTL 淘汰 |
| 上下文压缩 | 策略可插拔（default / fact_anchor / none） |
| 技能管理 | 文件系统 CRUD + Hermes Skills |
| 评测系统 | LLM Judge + 四维评测（会话内/跨会话/混合检索/端到端） |
| 日志 | loguru（三路分级：console / warning / audit） |
| 前端 | Vue 3 + Vite（`agent_frontend/`） |
| 部署 | Docker + docker-compose |

---

## 常用命令

```bash
python main.py                    # 启动开发服务器
cd docker && docker compose up -d # Docker 部署
cd docker && docker compose logs  # 查看容器日志
cd docker && docker compose down  # 停止服务
```

---

## License

MIT
