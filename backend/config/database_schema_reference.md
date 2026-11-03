# AgentForge 数据库表结构参考

> 本文档为人工维护的库表参考，供 Text2SQL Schema Card 召回 & 开发者查阅使用。
> 每张表只记录最终状态，字段语义取自 DDL COMMENT。

---

## 一、用户与权限

### users — 用户账号表

数据粒度：一行代表一个用户
时间字段：created_at, updated_at, last_login_at

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | 用户ID |
| username | VARCHAR(64) | NOT NULL，唯一索引 | 登录名 |
| password | VARCHAR(256) | NOT NULL | scrypt 哈希 |
| email | VARCHAR(128) | DEFAULT '' | 邮箱 |
| role | VARCHAR(16) | DEFAULT 'user'，索引 | super_admin / admin / user（过渡字段，后续用 role_id） |
| role_id | BIGINT | 索引 | 角色ID，关联 roles.id |
| avatar | VARCHAR(512) | DEFAULT '' | 头像URL |
| status | TINYINT | DEFAULT 1，索引 | 1=正常 0=禁用 |
| last_login_at | DATETIME | | 最后登录时间 |
| last_login_ip | VARCHAR(64) | DEFAULT '' | 最后登录IP |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### roles — 角色定义表

数据粒度：一行代表一个角色
时间字段：created_at, updated_at

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | 角色ID |
| name | VARCHAR(128) | NOT NULL，唯一索引 | 角色标识 |
| display_name | VARCHAR(128) | DEFAULT '' | 显示名称 |
| description | TEXT | | 描述 |
| is_system | TINYINT | DEFAULT 0 | 1=系统内置，不可删除 |
| hermes_tools | JSON | | 角色可用的 Hermes 工具集（web/memory/file/terminal...） |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### role_permissions — 角色权限关联表

数据粒度：一行代表一个角色-权限关联
唯一约束：(role_id, permission)

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| role_id | BIGINT | NOT NULL，索引 | 角色ID，关联 roles.id |
| permission | VARCHAR(128) | NOT NULL | 权限标识 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### user_permissions — 用户权限覆盖表

数据粒度：一行代表一个用户-权限覆盖
唯一约束：(user_id, permission)

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| user_id | BIGINT | NOT NULL，索引 | 用户ID，关联 users.id |
| permission | VARCHAR(128) | NOT NULL | 权限标识 |
| granted | TINYINT | DEFAULT 1 | 1=授予 0=拒绝 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### permission_defs — 权限定义表

数据粒度：一行代表一个权限定义
时间字段：created_at

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| key | VARCHAR(128) | NOT NULL，唯一索引 | 权限标识键 |
| label | VARCHAR(128) | NOT NULL | 权限标签 |
| description | TEXT | | 权限描述 |
| group_name | VARCHAR(64) | NOT NULL | 权限分组名称 |
| group_label | VARCHAR(128) | NOT NULL | 权限分组标签 |
| sort_order | INT | DEFAULT 0 | 排序顺序 |
| created_at | DATETIME | NOT NULL | 创建时间 |

---

### user_bindings — 用户绑定表（微信/飞书平台账号绑定）

数据粒度：一行代表一个平台绑定
时间字段：created_at
关联线索：user_id → users.id
唯一约束：(platform, open_id)，(user_id, platform)

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| user_id | BIGINT | NOT NULL | 关联 users.id |
| platform | VARCHAR(20) | NOT NULL | 平台：wechat / feishu |
| open_id | VARCHAR(128) | NOT NULL | 微信 id / 飞书 open_id |
| nickname | VARCHAR(128) | DEFAULT '' | 对方昵称 |
| enabled | TINYINT | DEFAULT 1 | 是否启用 |
| created_at | DATETIME | NOT NULL | 创建时间 |

---

## 二、对话管理

### conversations — 对话记录表

数据粒度：一行代表一条对话消息
时间字段：created_at, updated_at
关联线索：user_id → users.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| session_id | VARCHAR(128) | NOT NULL，索引 | 会话ID |
| user_id | BIGINT | NOT NULL，索引 | 用户ID |
| chat_mode | VARCHAR(32) | DEFAULT 'normal' | 对话模式 |
| user_question | TEXT | NOT NULL | 用户问题 |
| agent_answer | LONGTEXT | NOT NULL | AI 回答 |
| status | TINYINT | DEFAULT 1，索引 | 0=删除 1=完成 2=异常 3=中断 4=进行中 |
| session_title | VARCHAR(255) | | 会话标题 |
| source | VARCHAR(20) | DEFAULT 'web' | 消息来源：web / wechat / feishu |
| metadata | JSON | | 扩展字段 |
| created_at | DATETIME | NOT NULL，索引 | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### attachments — 附件表

数据粒度：一行代表一个附件
时间字段：created_at
关联线索：session_id → conversations.session_id，conversation_id → conversations.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| session_id | VARCHAR(128) | 索引 | 会话ID |
| conversation_id | BIGINT | 索引 | 关联对话ID |
| file_type | INT | DEFAULT 0 | 1=Word 2=Excel 3=PDF 4=图片 |
| file_name | VARCHAR(512) | DEFAULT '' | 文件名 |
| file_path | TEXT | | 文件路径 |
| file_size | BIGINT | DEFAULT 0 | 文件大小（字节） |
| created_at | DATETIME | NOT NULL | 创建时间 |

---

## 三、可观测性

### traces — LLM 调用链路表

数据粒度：一行代表一次 LLM API 调用
时间字段：created_at
关联线索：user_id → users.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| session_id | VARCHAR(64) | NOT NULL，索引 | 会话ID |
| user_id | BIGINT | NOT NULL，索引 | 用户ID |
| source | VARCHAR(16) | DEFAULT 'web'，索引 | 来源：web/wechat/feishu |
| api_request_id | VARCHAR(512) | 唯一索引 | Hermes 唯一请求标识 |
| model | VARCHAR(128) | NOT NULL，索引 | 模型名称 |
| provider | VARCHAR(64) | | 提供商 |
| turn_index | INT | DEFAULT 0 | 对话轮次 |
| input_tokens | INT | DEFAULT 0 | 输入 token 数 |
| output_tokens | INT | DEFAULT 0 | 输出 token 数 |
| cache_read_tokens | INT | DEFAULT 0 | 缓存读取 token 数 |
| cache_write_tokens | INT | DEFAULT 0 | 缓存写入 token 数 |
| reasoning_tokens | INT | DEFAULT 0 | 推理 token 数 |
| total_tokens | INT | DEFAULT 0 | 总 token 数 |
| latency_ms | INT | DEFAULT 0 | 延迟（毫秒） |
| estimated_cost_usd | DECIMAL(10,6) | DEFAULT 0 | 估算成本（美元） |
| finish_reason | VARCHAR(32) | | 结束原因 |
| api_call_count | INT | DEFAULT 0 | API 调用次数 |
| status | TINYINT | DEFAULT 2，索引 | 0=失败 1=成功 2=进行中 |
| error_message | TEXT | | 错误信息 |
| prompt_text | LONGTEXT | | 提示词文本（全量采集模式开启时记录） |
| completion_text | LONGTEXT | | 完成文本（全量采集模式开启时记录） |
| created_at | DATETIME | NOT NULL，索引 | 创建时间 |

---

### trace_spans — 工具调用 Span 表

数据粒度：一行代表一次工具调用
时间字段：created_at
关联线索：trace_id → traces.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| trace_id | BIGINT | NOT NULL，索引 | 追踪ID |
| span_type | VARCHAR(16) | DEFAULT 'tool_call' | span 类型 |
| tool_name | VARCHAR(128) | NOT NULL | 工具名称 |
| duration_ms | INT | DEFAULT 0 | 耗时（毫秒） |
| status | TINYINT | DEFAULT 1 | 0=失败 1=成功 |
| error_message | TEXT | | 错误信息 |
| created_at | DATETIME | NOT NULL | 创建时间 |

---

### trace_config — Trace 采集配置表（KV 存储）

数据粒度：一行代表一个配置项
时间字段：updated_at

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| key | VARCHAR(64) | 主键 | 配置键 |
| value | TEXT | | 配置值 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### daily_user_stats — 每日用户聚合统计表

数据粒度：一行代表一个用户一天的统计（排行榜数据源）
时间字段：stat_date, updated_at
关联线索：user_id → users.id
主键：(stat_date, user_id)

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| stat_date | DATE | 主键 | 统计日期 |
| user_id | BIGINT | 主键，索引 | 用户ID |
| total_tokens | BIGINT | DEFAULT 0 | 总 token 数 |
| api_calls | INT | DEFAULT 0 | API 调用次数 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

## 四、知识库

### kb_knowledge_base — 知识库表

数据粒度：一行代表一个知识库
时间字段：created_at, updated_at
关联线索：user_id → users.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | 知识库ID |
| kb_name | VARCHAR(255) | NOT NULL | 知识库名称 |
| kb_type | VARCHAR(50) | DEFAULT 'general'，索引 | 知识库类型：general / text2sql / history_correct |
| description | TEXT | | 知识库描述 |
| user_id | BIGINT | NOT NULL，索引 | 创建者用户ID |
| is_enabled | TINYINT | DEFAULT 1，索引 | 1=启用 0=禁用 |
| is_system | TINYINT | DEFAULT 0 | 1=系统内置（不可删除）0=用户创建 |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### kb_documents — 知识库文档表

数据粒度：一行代表一个文档
时间字段：created_at, updated_at
关联线索：kb_id → kb_knowledge_base.id，user_id → users.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | 文档ID |
| kb_id | BIGINT | 索引 | 所属知识库ID，NULL 表示默认知识库 |
| user_id | BIGINT | NOT NULL，索引 | 上传者用户ID |
| original_name | VARCHAR(512) | NOT NULL | 原始文件名 |
| stored_name | VARCHAR(128) | NOT NULL | 存储文件名 |
| ext | VARCHAR(16) | DEFAULT '' | 文件扩展名 |
| size_bytes | BIGINT | DEFAULT 0 | 文件大小（字节） |
| sha256 | CHAR(64) | DEFAULT '' | 文件 SHA256 哈希 |
| page_count | INT | DEFAULT 0 | 页数 |
| char_count | INT | DEFAULT 0 | 字符数 |
| chunk_count | INT | DEFAULT 0 | 分片数 |
| status | VARCHAR(20) | DEFAULT 'parsed'，索引 | parsed / parsing / failed / needs_ocr |
| parser | VARCHAR(32) | DEFAULT 'builtin' | 解析器 |
| chunk_size | INT | DEFAULT 1000 | 分片大小 |
| chunk_overlap | INT | DEFAULT 200 | 分片重叠 |
| chunk_strategy | VARCHAR(16) | NOT NULL，DEFAULT 'fixed' | 分片策略：fixed / parent_child |
| error_message | TEXT | | 错误信息 |
| content_text | LONGTEXT | | 文档全文文本 |
| vectorized | TINYINT | DEFAULT 0，索引 | 是否已向量化 0=否 1=是 |
| graph_extracted | TINYINT | DEFAULT 0 | 是否已提取实体关系到知识图谱 |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### kb_chunks — 知识库分块表

数据粒度：一行代表一个文档分片
时间字段：created_at
关联线索：document_id → kb_documents.id，topic_id → kb_topics.id，parent_chunk_id → kb_chunks.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | 分片ID |
| kb_id | BIGINT | 索引 | 所属知识库ID，NULL 表示默认知识库 |
| document_id | BIGINT | NOT NULL，索引 | 文档ID |
| chunk_index | INT | NOT NULL | 分片索引（文档内序号） |
| content | LONGTEXT | | 分片内容 |
| char_count | INT | DEFAULT 0 | 字符数 |
| page_start | INT | | 起始页码 |
| page_end | INT | | 结束页码 |
| metadata | JSON | | 扩展元数据（含 table_refs、heading_path 等） |
| strategy | VARCHAR(16) | NOT NULL，DEFAULT 'fixed' | 分片策略 |
| kind | VARCHAR(16) | NOT NULL，DEFAULT 'base' | 分片类型：base / parent / child / topic |
| is_manual_edit | TINYINT | DEFAULT 0 | 是否手动修改 |
| manual_edit_reason | VARCHAR(500) | | 修改原因 |
| original_content | TEXT | | 原始内容（用于回滚） |
| manual_edit_at | DATETIME | | 手动修改时间 |
| topic_id | BIGINT | 索引 | 所属主题ID |
| parent_chunk_id | BIGINT | 索引 | 父分片ID（父子分片：子片指向父片） |
| scope_layer_id | BIGINT | DEFAULT NULL，索引 | 数据层级ID（NULL=继承 KB 层级，非 NULL=单独指定） |
| created_at | DATETIME | NOT NULL | 创建时间 |

唯一约束：(document_id, chunk_index)

---

### kb_topics — 知识库主题表

数据粒度：一行代表一个文档主题
时间字段：created_at
关联线索：document_id → kb_documents.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | 主题ID |
| document_id | BIGINT | NOT NULL，索引 | 文档ID |
| title | VARCHAR(255) | DEFAULT '' | 主题标题 |
| source | VARCHAR(16) | DEFAULT 'structure' | 来源：structure / marker / cluster |
| page_start | INT | | 起始页码 |
| page_end | INT | | 结束页码 |
| char_count | INT | DEFAULT 0 | 字符数 |
| created_at | DATETIME | NOT NULL | 创建时间 |

---

### kb_retrieval_logs — RAG 检索日志表

数据粒度：一行代表一次检索操作
时间字段：created_at
关联线索：user_id → users.id，thread_id → conversations.session_id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| user_id | BIGINT | NOT NULL，索引 | 用户ID |
| thread_id | VARCHAR(128) | DEFAULT ''，索引 | 会话线程ID |
| conversation_id | BIGINT | | 对话ID |
| query | TEXT | NOT NULL | 检索问题 |
| top_k | INT | DEFAULT 5 | 返回数量 |
| retriever | VARCHAR(16) | DEFAULT '' | 检索器类型：vector / bm25 / hybrid |
| chunk_ids | JSON | | 命中的分片ID列表 |
| hit_count | INT | DEFAULT 0 | 命中数 |
| elapsed_ms | INT | DEFAULT 0 | 检索耗时（毫秒） |
| created_at | DATETIME | NOT NULL | 创建时间 |

---

### kb_feedback — RAG 用户反馈表

数据粒度：一行代表一条用户反馈
时间字段：created_at, updated_at
关联线索：user_id → users.id，thread_id → conversations.session_id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| user_id | BIGINT | NOT NULL，索引 | 用户ID |
| conversation_id | BIGINT | 索引 | 对话ID |
| thread_id | VARCHAR(128) | DEFAULT '' | 会话线程ID |
| rating | TINYINT | NOT NULL，DEFAULT 0 | 评分（1=赞 0=踩） |
| comment | VARCHAR(512) | DEFAULT '' | 评论内容 |
| retrieved_chunk_ids | JSON | | 关联的检索分片ID |
| status | VARCHAR(16) | NOT NULL，DEFAULT 'open'，索引 | 状态：open / processed |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### data_layers — 数据层级（部门）定义表

数据粒度：一行代表一个数据层级（部门）
时间字段：created_at, updated_at

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | 层级ID |
| name | VARCHAR(64) | NOT NULL，唯一索引 | 层级名称 |
| description | VARCHAR(255) | DEFAULT '' | 层级说明 |
| sort_order | INT | DEFAULT 0 | 排序（前端展示顺序） |
| is_system | TINYINT | DEFAULT 0 | 1=系统内置（不可删除） |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

内置 id=0 为「全员」层级，所有用户默认可见。

---

### user_data_layers — 用户-数据层级关联表

数据粒度：一行代表一个用户所属的数据层级
时间字段：created_at
关联线索：user_id → users.id，layer_id → data_layers.id
主键：(user_id, layer_id)

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| user_id | BIGINT | NOT NULL，主键 | 用户ID |
| layer_id | BIGINT | NOT NULL，主键，索引 | 数据层级ID |
| created_at | DATETIME | NOT NULL | 创建时间 |

---

### kb_data_layers — 知识库-数据层级关联表

数据粒度：一行代表一个知识库所属的数据层级
时间字段：created_at
关联线索：kb_id → kb_knowledge_base.id，layer_id → data_layers.id
主键：(kb_id, layer_id)

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| kb_id | BIGINT | NOT NULL，主键 | 知识库ID |
| layer_id | BIGINT | NOT NULL，主键，索引 | 数据层级ID |
| created_at | DATETIME | NOT NULL | 创建时间 |

用户只能检索自己所属数据层级对应的知识库。

---

## 五、RAG 测评

### kb_eval_sets — RAG 测评集表

数据粒度：一行代表一个测评集
时间字段：created_at, updated_at
关联线索：user_id → users.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| user_id | BIGINT | NOT NULL，索引 | 创建者用户ID |
| name | VARCHAR(255) | NOT NULL | 测评集名称 |
| description | VARCHAR(512) | DEFAULT '' | 描述 |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### kb_eval_items — RAG 测评题目表

数据粒度：一行代表一道测评题
时间字段：created_at
关联线索：eval_set_id → kb_eval_sets.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| eval_set_id | BIGINT | NOT NULL，索引 | 测评集ID |
| question | TEXT | NOT NULL | 问题 |
| ground_truth_chunk_ids | JSON | | 标准答案分片ID |
| ground_truth_chunk_content | JSON | | 标准答案分片内容 |
| ground_truth_answer | TEXT | | 标准答案 |
| sort_order | INT | DEFAULT 0 | 排序 |
| created_at | DATETIME | NOT NULL | 创建时间 |

---

### kb_eval_runs — RAG 测评运行表

数据粒度：一行代表一次测评运行
时间字段：created_at, started_at, finished_at
关联线索：eval_set_id → kb_eval_sets.id，user_id → users.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| eval_set_id | BIGINT | NOT NULL，索引 | 测评集ID |
| user_id | BIGINT | NOT NULL | 执行用户ID |
| config | JSON | | 运行配置 |
| status | VARCHAR(16) | DEFAULT 'running' | 状态：running / done / failed |
| progress | JSON | | 进度 |
| metrics | JSON | | 聚合指标 |
| error | TEXT | | 错误信息 |
| started_at | DATETIME | | 开始时间 |
| finished_at | DATETIME | | 结束时间 |
| created_at | DATETIME | NOT NULL | 创建时间 |

---

### kb_eval_results — RAG 测评结果表

数据粒度：一行代表一道题的测评结果
时间字段：created_at
关联线索：run_id → kb_eval_runs.id，item_id → kb_eval_items.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| run_id | BIGINT | NOT NULL，索引 | 运行ID |
| item_id | BIGINT | NOT NULL | 题目ID |
| question | TEXT | | 问题 |
| retrieved_chunks | JSON | | 检索到的分片 |
| metrics | JSON | | 检索指标 |
| answer | TEXT | | 生成答案 |
| judge_metrics | JSON | | 裁判指标（RAGAS LLM 评估） |
| classification | VARCHAR(32) | DEFAULT '' | RAG 评测六态分类 |
| created_at | DATETIME | NOT NULL | 创建时间 |

---

### kb_eval_suggestions — RAG 优化建议表

数据粒度：一行代表一条优化建议
时间字段：created_at, updated_at, resolved_at
关联线索：user_id → users.id，eval_set_id → kb_eval_sets.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| user_id | BIGINT | NOT NULL，索引 | 用户ID |
| eval_set_id | BIGINT | 索引 | 测评集ID |
| source | VARCHAR(16) | NOT NULL，DEFAULT 'eval' | 来源：eval / feedback / manual |
| kind | VARCHAR(32) | NOT NULL，DEFAULT 'manual' | 建议类型：rechunk_suggest / manual |
| summary | TEXT | | 建议摘要 |
| evidence | JSON | | 证据 |
| status | VARCHAR(16) | NOT NULL，DEFAULT 'pending'，索引 | 状态：pending / verifying / verified / failed / dismissed |
| before_metrics | JSON | | 验证前指标 |
| after_metrics | JSON | | 验证后指标 |
| linked_run_ids | JSON | | 关联运行ID |
| attempts | INT | DEFAULT 0 | 尝试次数 |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |
| resolved_at | DATETIME | | 解决时间 |
| suggestion_type | VARCHAR(32) | DEFAULT 'general' | 建议类型：general / sql_example / chunk_modify / mixed |
| sql_example_content | TEXT | | SQL 示例内容（Markdown 格式） |
| sql_example_approved | TINYINT | DEFAULT 0 | SQL 示例是否已审批通过 |
| sql_example_document_id | BIGINT | | SQL 示例入库后的文档ID |
| chunk_modify_suggestions | JSON | | 对 chunks 的修改建议列表 |
| target_kb_id | BIGINT | | 目标知识库ID（历史正确案例） |
| verification_query | VARCHAR(512) | DEFAULT '' | 验证用的原始问题 |
| verification_result | JSON | | 验证结果 |

---

## 六、记忆系统

> ~~`memory_items` 表已废弃~~，记忆系统已迁移为两层架构：
> - **Episodic（近期记忆）** — 30 天 TTL，有向量，无图节点
> - **Semantic（永久知识）** — 无 TTL，有向量 + 图节点

### memory_outbox — 记忆同步事件队列表（Outbox 模式）

数据粒度：一行代表一个同步事件
时间字段：created_at, available_at, locked_at, processed_at
关联线索：memory_id → memory_episodic.id / memory_semantic.id（由 memory_layer 区分）

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| event_id | VARCHAR(36) | NOT NULL，唯一索引 | 事件唯一ID（UUID） |
| memory_id | BIGINT | NOT NULL，索引 | 关联的记忆ID |
| memory_version | BIGINT | NOT NULL，索引 | 事件产生时的记忆版本 |
| event_type | VARCHAR(32) | NOT NULL | 事件类型：upsert_vector / delete_vector / upsert_graph_node / delete_graph_node |
| target | VARCHAR(16) | NOT NULL | 目标库：milvus / neo4j |
| payload | JSON | | 事件载荷 |
| status | VARCHAR(16) | NOT NULL，DEFAULT 'pending'，索引 | 状态：pending / processing / processed / dead |
| attempts | INT | NOT NULL，DEFAULT 0 | 重试次数 |
| available_at | DATETIME | NOT NULL | 可用于消费的时间 |
| locked_at | DATETIME | 索引 | 被领取的时间 |
| locked_by | VARCHAR(64) | | 领取者标识 |
| processed_at | DATETIME | | 处理完成时间 |
| last_error | TEXT | | 最后一次错误信息 |
| memory_layer | VARCHAR(16) | NOT NULL，DEFAULT 'legacy' | 记忆层级：legacy / episodic / semantic |
| created_at | DATETIME | NOT NULL | 创建时间 |

---

### memory_rounds — 记忆轮次表（滑动窗口）

数据粒度：一行代表一个会话的记忆轮次
时间字段：created_at, updated_at
关联线索：user_id → users.id，thread_id → conversations.session_id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| thread_id | VARCHAR(128) | NOT NULL，唯一索引 | 会话ID |
| user_id | BIGINT | NOT NULL，索引 | 用户ID |
| round_count | INT | DEFAULT 0 | 当前轮次计数 |
| last_message_hash | VARCHAR(64) | DEFAULT '' | 最后消息哈希（防重） |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### memory_consolidation_logs — 记忆合并日志表

数据粒度：一行代表一次合并操作
时间字段：created_at
关联线索：user_id → users.id，target_id → memory_episodic.id / memory_semantic.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| user_id | BIGINT | NOT NULL，索引 | 用户ID |
| source_ids | TEXT | NOT NULL | 源记忆ID列表（JSON 数组） |
| target_id | BIGINT | NOT NULL | 目标记忆ID |
| similarity_score | FLOAT | NOT NULL | 相似度分数 |
| consolidation_type | VARCHAR(32) | DEFAULT 'merge' | 合并类型：merge / dedup |
| created_at | DATETIME | NOT NULL | 创建时间 |

---

### memory_episodic — 近期记忆表（30 天 TTL，带向量）

数据粒度：一行代表一条近期记忆
时间字段：created_at, updated_at, last_accessed_at, expires_at
关联线索：user_id → users.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | 记忆ID |
| user_id | BIGINT | NOT NULL，索引 | 用户ID |
| memory_type | VARCHAR(32) | NOT NULL，索引 | 记忆类型：preference / fact / event / skill |
| content | TEXT | NOT NULL | 记忆内容 |
| embedding_id | VARCHAR(128) | DEFAULT '' | 向量库ID |
| vector_id | VARCHAR(128) | DEFAULT '' | 向量ID |
| importance_score | FLOAT | DEFAULT 0.5，索引 | 重要性分数 0-1 |
| access_count | INT | DEFAULT 0 | 访问次数 |
| last_accessed_at | DATETIME | | 最后访问时间 |
| decay_rate | FLOAT | DEFAULT 0.95 | 衰减率 |
| ttl_days | INT | DEFAULT 30 | 存活天数 |
| expires_at | DATETIME | 索引 | 过期时间 |
| source_thread_id | VARCHAR(128) | DEFAULT '' | 来源会话ID |
| source_round | INT | DEFAULT 0 | 来源轮次 |
| is_user_edited | TINYINT | DEFAULT 0 | 用户是否手动编辑 |
| version | BIGINT | NOT NULL，DEFAULT 1 | 版本号 |
| content_hash | VARCHAR(64) | NOT NULL，DEFAULT '' | 内容哈希 |
| deleted_at | DATETIME | | 软删除时间 |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### memory_semantic — 永久知识表（无 TTL，带向量+图）

数据粒度：一行代表一条永久知识
时间字段：created_at, updated_at，last_accessed_at
关联线索：user_id → users.id，source_episodic_id → memory_episodic.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | 记忆ID |
| user_id | BIGINT | NOT NULL，索引 | 用户ID |
| memory_type | VARCHAR(32) | NOT NULL，索引 | 记忆类型：preference / fact / event / skill |
| content | TEXT | NOT NULL | 记忆内容 |
| embedding_id | VARCHAR(128) | DEFAULT '' | 向量库ID |
| vector_id | VARCHAR(128) | DEFAULT '' | 向量ID |
| graph_node_id | VARCHAR(128) | DEFAULT '' | Neo4j 节点ID |
| importance_score | FLOAT | DEFAULT 0.5，索引 | 重要性分数 0-1 |
| access_count | INT | DEFAULT 0 | 访问次数 |
| last_accessed_at | DATETIME | | 最后访问时间 |
| source_thread_id | VARCHAR(128) | DEFAULT '' | 来源会话ID |
| source_round | INT | DEFAULT 0 | 来源轮次 |
| source_episodic_id | BIGINT | | 来源 episodic 记忆ID |
| is_user_edited | TINYINT | DEFAULT 0 | 用户是否手动编辑 |
| version | BIGINT | NOT NULL，DEFAULT 1 | 版本号 |
| content_hash | VARCHAR(64) | NOT NULL，DEFAULT '' | 内容哈希 |
| deleted_at | DATETIME | | 软删除时间 |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### memory_versions — 记忆版本历史表

数据粒度：一行代表一条记忆的一个历史版本
时间字段：created_at
关联线索：memory_id → memory_episodic.id / memory_semantic.id（由实际所在层决定）

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| memory_id | BIGINT | NOT NULL，索引 | 关联的记忆ID |
| version | INT | NOT NULL，DEFAULT 1 | 版本号 |
| content | TEXT | NOT NULL | 历史内容 |
| importance_score | FLOAT | NOT NULL，DEFAULT 0.5 | 历史重要性 |
| memory_type | VARCHAR(32) | | 历史类型 |
| change_reason | VARCHAR(64) | NOT NULL，DEFAULT 'consolidation' | 变更原因：consolidation / conflict_resolution / user_edit / llm_merge |
| source_memory_id | BIGINT | | 合并来源的另一条记忆ID（合并场景） |
| created_at | DATETIME | NOT NULL | 创建时间 |

---

### memory_operation_logs — 记忆操作审计日志表

数据粒度：一行代表一次记忆操作
时间字段：created_at
关联线索：user_id → users.id，memory_id → memory_episodic.id / memory_semantic.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| user_id | BIGINT | 索引 | 用户ID |
| username | VARCHAR(64) | DEFAULT '' | 用户名 |
| action | VARCHAR(32) | NOT NULL，索引 | 操作类型：create / read / update / delete / search / promote / restore / consolidate |
| memory_id | BIGINT | 索引 | 操作对象记忆ID（search 时可为空） |
| memory_layer | VARCHAR(16) | DEFAULT '' | 记忆层级：legacy / episodic / semantic |
| detail | VARCHAR(1024) | DEFAULT '' | 操作详情摘要 |
| ip_address | VARCHAR(64) | DEFAULT '' | IP 地址 |
| status | TINYINT | DEFAULT 1 | 0=失败 1=成功 |
| created_at | DATETIME | NOT NULL | 创建时间 |

---

### memory_eval_sets — 记忆评测集表

数据粒度：一行代表一个评测集
时间字段：created_at, updated_at
关联线索：user_id → users.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| name | VARCHAR(128) | NOT NULL | 评估集名称 |
| description | TEXT | | 描述 |
| user_id | BIGINT | 索引 | 创建者ID |
| is_active | TINYINT | DEFAULT 1，索引 | 是否启用 |
| item_count | INT | DEFAULT 0 | 评估项数量 |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### memory_eval_items — 记忆评测题目表

数据粒度：一行代表一道评测题
时间字段：created_at
关联线索：eval_set_id → memory_eval_sets.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| eval_set_id | BIGINT | NOT NULL，索引 | 评估集ID |
| query | TEXT | NOT NULL，全文索引 | 查询/问题 |
| expected_answer | TEXT | | 期望答案 |
| expected_memory_ids | TEXT | | 期望关联的记忆ID（JSON 数组） |
| tags | VARCHAR(255) | DEFAULT '' | 标签（逗号分隔） |
| difficulty | VARCHAR(32) | DEFAULT 'medium' | 难度：easy / medium / hard |
| created_at | DATETIME | NOT NULL | 创建时间 |

---

### memory_eval_runs — 记忆评测运行表

数据粒度：一行代表一次评测运行
时间字段：created_at, started_at, finished_at
关联线索：eval_set_id → memory_eval_sets.id，user_id → users.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| eval_set_id | BIGINT | NOT NULL，索引 | 评估集ID |
| user_id | BIGINT | NOT NULL，索引 | 执行用户ID |
| run_type | VARCHAR(32) | DEFAULT 'manual' | 运行类型：manual / scheduled |
| status | VARCHAR(32) | DEFAULT 'pending'，索引 | 状态：pending / running / completed / failed |
| total_items | INT | DEFAULT 0 | 总评估项数 |
| passed_items | INT | DEFAULT 0 | 通过项数 |
| precision_score | FLOAT | DEFAULT 0 | 精确率 |
| recall_score | FLOAT | DEFAULT 0 | 召回率 |
| f1_score | FLOAT | DEFAULT 0 | F1 分数 |
| started_at | DATETIME | | 开始时间 |
| finished_at | DATETIME | | 结束时间 |
| created_at | DATETIME | NOT NULL | 创建时间 |

---

### memory_eval_results — 记忆评测结果表

数据粒度：一行代表一道题的评测结果
时间字段：created_at
关联线索：run_id → memory_eval_runs.id，item_id → memory_eval_items.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| run_id | BIGINT | NOT NULL，索引 | 评估运行ID |
| item_id | BIGINT | NOT NULL，索引 | 评估项ID |
| retrieved_memory_ids | TEXT | | 检索到的记忆ID（JSON 数组） |
| retrieved_contents | TEXT | | 检索到的内容（JSON 数组） |
| llm_judgment | TEXT | | LLM 判断结果（JSON） |
| is_correct | TINYINT | DEFAULT 0 | 是否正确 |
| relevance_score | FLOAT | DEFAULT 0 | 相关性分数 |
| latency_ms | INT | DEFAULT 0 | 延迟（毫秒） |
| created_at | DATETIME | NOT NULL | 创建时间 |

---

### memory_ab_experiments — 记忆 AB 实验表

数据粒度：一行代表一个 AB 实验
时间字段：created_at, updated_at, started_at, ended_at

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| name | VARCHAR(128) | NOT NULL | 实验名称 |
| description | TEXT | | 实验描述 |
| variant_a | VARCHAR(64) | NOT NULL | 变体 A 配置 |
| variant_b | VARCHAR(64) | NOT NULL | 变体 B 配置 |
| traffic_split | FLOAT | DEFAULT 0.5 | 流量分配（A 的比例） |
| status | VARCHAR(32) | DEFAULT 'draft'，索引 | 状态：draft / running / paused / completed |
| metrics_json | TEXT | | 指标配置（JSON） |
| results_json | TEXT | | 实验结果（JSON） |
| started_at | DATETIME | | 开始时间 |
| ended_at | DATETIME | | 结束时间 |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### memory_ab_events — 记忆 AB 实验事件表

数据粒度：一行代表一个实验事件
时间字段：created_at
关联线索：user_id → users.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| experiment_name | VARCHAR(128) | NOT NULL，索引 | 实验名称 |
| variant_name | VARCHAR(64) | NOT NULL，索引 | 变体名称 |
| user_id | BIGINT | NOT NULL，索引 | 用户ID |
| thread_id | VARCHAR(64) | DEFAULT '' | 会话ID |
| event_type | VARCHAR(32) | NOT NULL | 事件类型：exposure / conversion / metric |
| metrics_json | TEXT | | 指标数据（JSON） |
| created_at | DATETIME | NOT NULL | 创建时间 |

---

## 七、知识图谱

### kg_archived_entities — 知识图谱归档表（冷热分离）

数据粒度：一行代表一个归档实体
时间字段：archived_at
关联线索：user_id → users.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| entity_id | VARCHAR(64) | NOT NULL，唯一索引 | 实体ID（Neo4j 中的 id） |
| name | VARCHAR(255) | NOT NULL | 实体名称 |
| entity_type | VARCHAR(32) | NOT NULL，索引 | 实体类型 |
| user_id | BIGINT | 索引 | 用户ID（多租户隔离） |
| data | JSON | NOT NULL | 完整的实体数据（JSON 格式） |
| archived_at | DATETIME | NOT NULL，索引 | 归档时间 |

---

### kg_alignment_candidates — 知识图谱审核候选表

数据粒度：一行代表一个审核候选（实体去重/冲突检测）
时间字段：created_at, reviewed_at
关联线索：user_id → users.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| user_id | BIGINT | NOT NULL，索引 | 所属用户 |
| candidate_type | VARCHAR(16) | NOT NULL，索引 | 候选类型：duplicate / name_collision / low_confidence / relation_direction |
| entity_a_id | VARCHAR(64) | NOT NULL | 实体 A（Neo4j id） |
| entity_a_name | VARCHAR(255) | DEFAULT '' | 实体 A 名称 |
| entity_b_id | VARCHAR(64) | | 实体 B / 关系ID |
| entity_b_name | VARCHAR(255) | DEFAULT '' | 实体 B 名称 |
| score | DECIMAL(4,3) | | 置信度/相似度 |
| reason | TEXT | | 标记原因 |
| status | VARCHAR(16) | DEFAULT 'pending' | 状态：pending / merged / confirmed / ignored / edited |
| created_at | DATETIME | NOT NULL | 创建时间 |
| reviewed_at | DATETIME | | 审核时间 |

---

### graph_change_log — 知识图谱变更日志表

数据粒度：一行代表一次图谱变更事件
时间字段：created_at
关联线索：user_id → users.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| user_id | BIGINT | NOT NULL，索引 | 所属用户ID |
| event_type | VARCHAR(32) | NOT NULL，索引 | 事件类型：entity_created / entity_updated / entity_deleted / relation_created / relation_deleted / relation_updated / relation_flipped |
| entity_id | VARCHAR(64) | 索引 | 实体/关系 Neo4j ID |
| entity_name | VARCHAR(255) | DEFAULT '' | 实体/关系名称（便于展示） |
| entity_type | VARCHAR(32) | DEFAULT '' | 实体类型（person/location/...） |
| before_json | JSON | | 修改前数据 |
| after_json | JSON | | 修改后数据 |
| ip_address | VARCHAR(64) | DEFAULT '' | 操作 IP |
| created_at | DATETIME | NOT NULL，索引 | 创建时间 |

---

### kg_communities — 知识图谱社区检测表

数据粒度：一行代表一个社区
时间字段：created_at, updated_at
关联线索：user_id → users.id，parent_id → kg_communities.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | VARCHAR(64) | 主键 | 社区 ID（community_xxx） |
| user_id | BIGINT | NOT NULL，索引 | 所属用户 |
| level | INT | NOT NULL，DEFAULT 0，索引 | 层级（0=最细，越大越粗） |
| parent_id | VARCHAR(64) | 索引 | 父社区 ID |
| entity_count | INT | DEFAULT 0 | 包含实体数量 |
| entity_ids | JSON | | 包含实体 ID 列表 |
| relationship_count | INT | DEFAULT 0 | 内部关系数量 |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### kg_community_reports — 知识图谱社区报告表

数据粒度：一行代表一个社区的报告
时间字段：created_at, updated_at
关联线索：community_id → kg_communities.id
唯一约束：community_id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| community_id | VARCHAR(64) | NOT NULL，唯一索引 | 社区 ID |
| title | VARCHAR(255) | DEFAULT '' | 报告标题 |
| summary | TEXT | | 摘要（50-100 字） |
| full_content | TEXT | | 完整报告内容 |
| summary_embedding | JSON | | 摘要向量（用于语义相似度匹配） |
| rating | INT | DEFAULT 5 | 重要度评分（1-10） |
| findings | JSON | | 关键发现列表 |
| top_entities | JSON | | 核心实体列表 |
| status | VARCHAR(16) | DEFAULT 'pending'，索引 | 状态：pending / generating / completed / failed |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

## 八、技能管理

### skill_meta — 技能元信息表

数据粒度：一行代表一个技能
时间字段：created_at, updated_at
关联线索：owner_id → users.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| name | VARCHAR(100) | NOT NULL，唯一索引 | 技能名称 |
| owner_id | BIGINT | NOT NULL，索引 | 所有者ID |
| category | VARCHAR(50) | DEFAULT '' | 分类 |
| status | VARCHAR(20) | DEFAULT 'approved'，索引 | 状态：approved / pending / rejected |
| locked | TINYINT | DEFAULT 0 | 是否锁定 |
| reviewed_by | BIGINT | | 审核人ID |
| reviewed_at | DATETIME | | 审核时间 |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### content_pool — 内容池表（技能/智能体上架审核）

数据粒度：一行代表一个待审核内容
时间字段：created_at, updated_at
关联线索：owner_id → users.id，submitted_by → users.id
唯一约束：(content_type, content_name)

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| content_type | VARCHAR(16) | NOT NULL | 内容类型：skill / tool |
| content_name | VARCHAR(256) | NOT NULL | 内容名称 |
| owner_id | BIGINT | NOT NULL | 所有者ID |
| submitted_by | BIGINT | NOT NULL | 提交者ID |
| status | VARCHAR(16) | DEFAULT 'pending'，索引 | 状态：pending / active / rejected |
| reviewed_by | BIGINT | | 审核人ID |
| reviewed_at | DATETIME | | 审核时间 |
| reject_reason | TEXT | | 拒绝原因 |
| metadata | JSON | | 元数据 |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### content_installs — 内容安装记录表

数据粒度：一行代表一次安装
时间字段：installed_at
关联线索：user_id → users.id
唯一约束：(content_type, content_name, user_id)

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| content_type | VARCHAR(16) | NOT NULL | 内容类型 |
| content_name | VARCHAR(256) | NOT NULL | 内容名称 |
| user_id | BIGINT | NOT NULL | 用户ID |
| installed_at | DATETIME | NOT NULL | 安装时间 |

---

### categories — 技能分类表

数据粒度：一行代表一个分类
时间字段：created_at

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| name | VARCHAR(128) | NOT NULL，唯一索引 | 分类名称 |
| slug | VARCHAR(128) | NOT NULL，唯一索引 | 分类标识 |
| description | TEXT | | 描述 |
| sort_order | INT | DEFAULT 0 | 排序 |
| created_at | DATETIME | NOT NULL | 创建时间 |

---

### item_status — 组件状态表（技能/智能体启用禁用）

数据粒度：一行代表一个组件的状态
时间字段：updated_at
唯一约束：(item_type, item_name)

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| item_type | VARCHAR(16) | NOT NULL，DEFAULT 'skill' | 类型：skill / agent |
| item_name | VARCHAR(128) | NOT NULL | 名称 |
| enabled | TINYINT | DEFAULT 1 | 1=启用 0=禁用 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

## 九、定时任务

### cron_jobs — 定时任务表

数据粒度：一行代表一个定时任务
时间字段：created_at, updated_at, last_run_at, next_run_at
关联线索：user_id → users.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| user_id | BIGINT | NOT NULL，索引 | 用户ID |
| name | VARCHAR(255) | NOT NULL | 任务名称 |
| prompt | TEXT | NOT NULL | 任务提示词 |
| schedule_type | VARCHAR(20) | NOT NULL，DEFAULT 'cron' | 调度类型：cron / interval / daily / once |
| schedule_value | VARCHAR(128) | NOT NULL | 调度值 |
| deliver_to | VARCHAR(20) | NOT NULL，DEFAULT 'wechat' | 投递目标：wechat / email |
| report_format | VARCHAR(20) | NOT NULL，DEFAULT 'pdf' | 报告格式 |
| email_sender_id | BIGINT | | 邮件发送者ID |
| email_receiver_id | BIGINT | | 邮件接收者ID |
| receiver_email | VARCHAR(256) | DEFAULT '' | 接收者邮箱 |
| enabled | TINYINT | DEFAULT 1 | 是否启用 |
| last_run_at | DATETIME | | 最后运行时间 |
| next_run_at | DATETIME | 索引 | 下次运行时间 |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### cron_executions — 定时任务执行记录表

数据粒度：一行代表一次任务执行
时间字段：created_at, started_at, finished_at
关联线索：job_id → cron_jobs.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| job_id | BIGINT | NOT NULL，索引 | 任务ID |
| session_id | VARCHAR(128) | DEFAULT '' | 会话ID |
| status | TINYINT | DEFAULT 0 | 状态：-1=待执行 0=执行中 1=成功 2=失败 3=成功但有质量问题 |
| result_text | LONGTEXT | | 结果文本 |
| error_message | TEXT | | 错误信息 |
| deliver_status | VARCHAR(128) | DEFAULT '' | 投递状态 |
| quality_issues | VARCHAR(1024) | DEFAULT '' | 质量问题标记 |
| started_at | DATETIME | NOT NULL | 开始时间 |
| finished_at | DATETIME | | 结束时间 |
| created_at | DATETIME | NOT NULL，索引 | 创建时间 |

---

## 十、系统配置

### model_configs — 模型配置表

数据粒度：一行代表一个模型配置
时间字段：created_at, updated_at
关联线索：user_id → users.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| user_id | BIGINT | DEFAULT 1，索引 | 用户ID |
| config_name | VARCHAR(128) | NOT NULL | 配置名称 |
| config_type | VARCHAR(32) | NOT NULL，DEFAULT 'URL' | 配置类型：URL / OLLAMA / LOCAL |
| api_url | VARCHAR(512) | DEFAULT '' | API URL |
| api_key | VARCHAR(512) | DEFAULT '' | API Key（AES-256-GCM 加密存储） |
| model_name | VARCHAR(128) | DEFAULT '' | 模型名称 |
| provider | VARCHAR(64) | DEFAULT '' | 提供商 |
| category | VARCHAR(32) | NOT NULL，DEFAULT 'chat'，索引 | 分类：chat / embedding |
| is_multimodal | TINYINT | DEFAULT 0 | 是否多模态 |
| dimension | INT | DEFAULT 0 | 向量维度（Embedding 模型） |
| send_dimensions | TINYINT | DEFAULT 0 | 是否发送维度参数 |
| reasoning_effort | VARCHAR(16) | DEFAULT '' | 推理强度 |
| is_current | TINYINT | DEFAULT 0，索引 | 是否当前激活 |
| enabled | TINYINT | DEFAULT 1，索引 | 是否启用 |
| priority | INT | DEFAULT 0 | 降级优先级，数字越小优先级越高 |
| cost_per_1k_input | DECIMAL(10,6) | DEFAULT 0 | 每 1000 输入 token 成本（USD） |
| cost_per_1k_output | DECIMAL(10,6) | DEFAULT 0 | 每 1000 输出 token 成本（USD） |
| context_length | INT | DEFAULT 0 | 模型上下文窗口大小 |
| capabilities | JSON | | 模型能力标签 {"code":true,"vision":true,"json_mode":true} |
| description | TEXT | | 模型描述/备注 |
| last_test_status | VARCHAR(64) | | 最后测试状态 |
| last_test_message | VARCHAR(512) | | 最后测试消息 |
| last_test_time | DATETIME | | 最后测试时间 |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### user_configs — 用户配置表（KV 存储）

数据粒度：一行代表一个用户配置项
时间字段：updated_at
关联线索：user_id → users.id
唯一约束：(user_id, config_key)

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| user_id | BIGINT | NOT NULL | 用户ID |
| config_key | VARCHAR(128) | NOT NULL | 配置键 |
| config_val | TEXT | | 配置值 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### personal_emails — 个人邮箱表

数据粒度：一行代表一个邮箱
时间字段：created_at, updated_at
关联线索：user_id → users.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| user_id | BIGINT | NOT NULL，索引 | 用户ID |
| email | VARCHAR(256) | NOT NULL | 邮箱地址 |
| is_current | TINYINT | DEFAULT 0 | 是否当前使用 |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### email_configs — 邮件发送配置表

数据粒度：一行代表一个邮件发送配置
时间字段：created_at, updated_at
关联线索：user_id → users.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| user_id | BIGINT | DEFAULT 1，索引 | 用户ID |
| config_name | VARCHAR(128) | NOT NULL | 配置名称 |
| host | VARCHAR(256) | NOT NULL | SMTP 主机 |
| port | VARCHAR(8) | NOT NULL，DEFAULT '587' | SMTP 端口 |
| sender_email | VARCHAR(256) | NOT NULL | 发件人邮箱 |
| sender_name | VARCHAR(128) | DEFAULT 'AgentForge' | 发件人名称 |
| password | VARCHAR(512) | | 密码（加密存储） |
| is_current | TINYINT | DEFAULT 0 | 是否当前激活 |
| enabled | TINYINT | DEFAULT 1 | 是否启用 |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### platform_config — 平台配置表（KV 存储）

数据粒度：一行代表一个平台的配置
时间字段：created_at, updated_at
唯一约束：platform

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| platform | VARCHAR(20) | NOT NULL，唯一索引 | 平台：wechat / feishu / email |
| config_json | JSON | NOT NULL | 平台配置 JSON |
| enabled | TINYINT | DEFAULT 0 | 是否启用 |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### rag_embedding_configs — RAG Embedding 模型配置表

数据粒度：一行代表一个 Embedding 模型配置
时间字段：created_at, updated_at

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | INT | 主键，自增 | |
| user_id | INT | DEFAULT 1 | 用户ID |
| config_name | VARCHAR(128) | DEFAULT 'Default' | 配置名称 |
| provider_type | VARCHAR(32) | DEFAULT 'OPENAI_COMPATIBLE' | 提供商类型 |
| base_url | VARCHAR(512) | DEFAULT '' | API 基础 URL |
| api_key | VARCHAR(512) | | API Key（加密存储） |
| model_name | VARCHAR(128) | DEFAULT 'text-embedding-3-small' | 模型名称 |
| dimension | INT | DEFAULT 1024 | 向量维度 |
| batch_size | INT | DEFAULT 8 | 批量大小 |
| timeout_seconds | INT | DEFAULT 180 | 超时时间（秒） |
| send_dimensions | TINYINT | DEFAULT 0 | 是否发送维度参数 |
| is_current | TINYINT | DEFAULT 1 | 是否当前激活 |
| enabled | TINYINT | DEFAULT 1 | 是否启用 |
| last_test_status | VARCHAR(32) | | 最后测试状态 |
| last_test_message | TEXT | | 最后测试消息 |
| last_test_time | DATETIME | | 最后测试时间 |
| created_at | DATETIME | | 创建时间 |
| updated_at | DATETIME | | 更新时间 |

---

## 十一、安全审计

### host_whitelist — 主机白名单表

数据粒度：一行代表一个白名单主机
时间字段：created_at, updated_at
关联线索：created_by → users.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| host_identifier | VARCHAR(128) | NOT NULL，索引 | 主机标识（IP / 主机名） |
| access_user | VARCHAR(64) | DEFAULT '' | 访问用户 |
| access_port | INT | DEFAULT 22 | 访问端口 |
| allowed_actions | VARCHAR(256) | DEFAULT '' | 允许的操作 |
| auth_method | VARCHAR(16) | DEFAULT 'password' | 认证方式：password / ssh_key |
| auth_secret | TEXT | | 加密存储的认证凭据 |
| remark | VARCHAR(256) | DEFAULT '' | 备注 |
| status | TINYINT | DEFAULT 1 | 1=启用 0=禁用 |
| expires_at | DATETIME | | 过期时间 |
| created_by | BIGINT | | 创建人 |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### exec_approval_logs — 命令执行审批日志表

数据粒度：一行代表一次命令审批
时间字段：created_at
关联线索：thread_id → conversations.session_id，user_id → users.id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| thread_id | VARCHAR(128) | NOT NULL，索引 | 会话线程ID |
| user_id | BIGINT | | 用户ID |
| command | TEXT | | 执行的命令 |
| decision | VARCHAR(32) | DEFAULT ''，索引 | 审批决策：allow-once / allow-session / deny |
| allow_permanent | TINYINT | DEFAULT 0 | 是否永久允许 |
| confirmed_by_name | VARCHAR(64) | DEFAULT '' | 确认人姓名 |
| confirmed_by_user_id | BIGINT | | 确认人用户ID |
| created_at | DATETIME | NOT NULL | 创建时间 |

---

### command_blacklist — 命令黑名单表

数据粒度：一行代表一条黑名单规则
时间字段：created_at, updated_at

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| pattern | VARCHAR(512) | NOT NULL | 正则表达式 |
| description | VARCHAR(256) | DEFAULT '' | 规则描述 |
| enabled | TINYINT | DEFAULT 1，索引 | 0=禁用 1=启用 |
| created_by | BIGINT | | 创建人 |
| created_at | DATETIME | NOT NULL | 创建时间 |
| updated_at | DATETIME | NOT NULL | 更新时间 |

---

### agent_operation_logs — AI 操作审计日志表

数据粒度：一行代表一次 AI 操作
时间字段：created_at
关联线索：user_id → users.id，thread_id → conversations.session_id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| thread_id | VARCHAR(128) | NOT NULL，索引 | 会话线程ID |
| user_id | BIGINT | 索引 | 用户ID |
| username | VARCHAR(64) | DEFAULT '' | 用户名 |
| tool_name | VARCHAR(128) | NOT NULL | 工具名称 |
| operation_type | VARCHAR(32) | DEFAULT 'tool_call'，索引 | 操作类型：tool_call / ssh_remote / blocked |
| command | TEXT | | 执行的命令 |
| args_summary | VARCHAR(1024) | DEFAULT '' | 参数摘要（截断） |
| result_summary | VARCHAR(1024) | DEFAULT '' | 结果摘要（截断） |
| target_host | VARCHAR(128) | DEFAULT ''，索引 | 远程目标主机（ssh/scp 场景） |
| status | TINYINT | DEFAULT 1 | 0=拦截/失败 1=成功 2=已审批执行 |
| error_message | TEXT | | 错误信息 |
| created_at | DATETIME | NOT NULL | 创建时间 |

---

### sql_operation_logs — SQL 操作审计日志表

数据粒度：一行代表一次 SQL 查询
时间字段：created_at
关联线索：user_id → users.id，thread_id → conversations.session_id

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| thread_id | VARCHAR(128) | NOT NULL，索引 | 会话线程ID |
| user_id | BIGINT | 索引 | 用户ID |
| username | VARCHAR(64) | DEFAULT '' | 用户名 |
| query | TEXT | | SQL 语句（完整记录，长文本截断） |
| status | TINYINT | DEFAULT 1 | 0=失败 1=成功 |
| error_message | TEXT | | 错误信息 |
| created_at | DATETIME | NOT NULL | 创建时间 |

---

## 十二、多 Agent 委派

### delegation_tasks — 多 Agent 委派留痕表

数据粒度：一行代表一个子 Agent 任务（同一次 delegate_task 扇出的 N 个子任务 = N 行，共享同一个 delegation_id）
时间字段：started_at, completed_at
关联线索：user_id → users.id；thread_id → conversations.session_id；delegation_id → 同一批 fan-out 共享的批次 ID；child_session_id → 子 Agent 在 Hermes 的会话 ID（可与 traces.session_id 关联）

| 字段 | 类型 | 约束 | 语义 |
|------|------|------|------|
| id | BIGINT | 主键，自增 | |
| delegation_id | VARCHAR(64) | 索引 | Hermes 批次 ID（同一批 fan-out 共享；结果回流时回填） |
| subagent_id | VARCHAR(64) | 唯一索引 | 子 Agent 唯一 ID（Hermes 生成，格式 sa-<批内序号>-<hex8>） |
| task_index | INT | | 批内序号（从 subagent_id 解析，0 起） |
| child_session_id | VARCHAR(64) | | 子 Agent 在 Hermes 的会话 ID（供 on_delegation 回填产出） |
| parent_session_id | VARCHAR(64) | 索引（联合 started_at） | 父 Agent 的 Hermes 会话 ID（结果回流的归属判定依据） |
| thread_id | VARCHAR(64) | 索引（联合 started_at） | AgentForge 会话 ID（即前端 chat_id，用于历史回填） |
| user_id | BIGINT | 索引（联合 started_at） | 发起委派的用户 ID，关联 users.id |
| goal | TEXT | | 子任务目标（Supervisor 派发时填写的 goal） |
| model | VARCHAR(128) | | 子 Agent 实际使用的模型（未指定时继承父 Agent 模型） |
| depth | INT | DEFAULT 0 | 委派深度，0=一级子 Agent（默认 max_spawn_depth=1，不嵌套） |
| status | VARCHAR(24) | 索引，DEFAULT 'running' | running / completed / error / interrupted / runtime_lost / rejected_sync |
| tool_count | INT | DEFAULT 0 | 子 Agent 工具调用次数（每 10 次落一次库，完成时按事件校准） |
| api_calls | INT | DEFAULT 0 | 子 Agent LLM 调用次数 |
| input_tokens | INT | DEFAULT 0 | 子 Agent 输入 token（来自 completion 事件） |
| output_tokens | INT | DEFAULT 0 | 子 Agent 输出 token（来自 completion 事件） |
| duration_seconds | DECIMAL(10,2) | DEFAULT 0 | 子 Agent 执行耗时（秒） |
| summary | LONGTEXT | | 子 Agent 最终产出（结果回流通道的权威来源） |
| error_message | TEXT | | 失败原因（status=error/interrupted 时有值） |
| live_transcript | VARCHAR(512) | | Hermes 写的实时转录日志路径（可 tail 观察子 Agent 全过程） |
| delivered | TINYINT | DEFAULT 0 | 1=结果已回流进父对话（父 Agent 已拿到子任务产出） |
| duplicate_hint | TINYINT | DEFAULT 0 | 预留字段：同批任务语义疑似重叠标记（当前无代码写入，重叠检测仅告警） |
| started_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | 子 Agent 开始执行时间 |
| completed_at | DATETIME | | 子 Agent 结束时间 |

status 取值语义：
- running：子 Agent 正在执行
- completed：正常完成，summary 有值
- error：执行报错（含子 Agent 内部 LLM 调用失败）
- interrupted：被取消（用户停止会经 interrupt_subagent 传导到子 Agent）
- runtime_lost：进程重启导致委派丢失，由 Hermes 的 async_delegations WAL 恢复时标记
- rejected_sync：后台并发池满，Hermes 降级为同步执行（父轮被阻塞，非失败）

查询要点：
- 查「某会话派了哪些子任务、结果回来没有」→ `WHERE thread_id = ? ORDER BY started_at DESC`，delivered=1 表示已回流
- 查「某次扇出批次」→ `WHERE delegation_id = ?`（一批 N 行）
- 查「委派异常」→ `WHERE status IN ('error','interrupted','runtime_lost')`
- 查「委派消耗」→ `SUM(input_tokens + output_tokens)` 按 user_id / thread_id 分组
- **重要**：本表是宿主侧留痕；子 Agent 的 LLM 明细在 `traces`（source='subagent'），两表按 child_session_id = traces.session_id 关联
- **常见错误**：用 subagent_id 当批次 ID 分组（应为 delegation_id）；把 delivered=0 当成失败（它只表示结果尚未回流到父对话）
