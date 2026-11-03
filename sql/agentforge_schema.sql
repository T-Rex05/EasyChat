-- ============================================================
-- AgentForge 完整数据库建表脚本 (MySQL)
-- 唯一 DDL 数据源 — backend/db/schema.py 的 init_db() 直接执行本文件
-- 共 65 张表，分 9 大区域；所有 CREATE TABLE 均使用 IF NOT EXISTS
-- 用法: mysql -u root -p < sql/agentforge_schema.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS agentforge CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE agentforge;

-- ════════════════════════════════════════════════════════════
-- 一、基础表
-- ════════════════════════════════════════════════════════════

-- 1. 用户表
CREATE TABLE IF NOT EXISTS users (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    username        VARCHAR(64) NOT NULL UNIQUE COMMENT '登录名',
    password        VARCHAR(256) NOT NULL COMMENT 'scrypt 哈希',
    email           VARCHAR(128) DEFAULT '' COMMENT '邮箱',
    role            VARCHAR(16) DEFAULT 'user' COMMENT 'super_admin / admin / user（过渡字段，后续用 role_id）',
    role_id         BIGINT DEFAULT NULL COMMENT '角色ID，关联 roles.id',
    avatar          VARCHAR(512) DEFAULT '' COMMENT '头像URL',
    status          TINYINT DEFAULT 1 COMMENT '1=正常 0=禁用',
    last_login_at   DATETIME DEFAULT NULL COMMENT '最后登录时间',
    last_login_ip   VARCHAR(64) DEFAULT '' COMMENT '最后登录IP',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status (status),
    INDEX idx_role (role),
    INDEX idx_role_id (role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

-- 2. 角色表（hermes_tools 由代码迁移，首次初始化时也会播种默认角色）
CREATE TABLE IF NOT EXISTS roles (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(128) NOT NULL UNIQUE COMMENT '角色标识',
    display_name VARCHAR(128) DEFAULT '' COMMENT '显示名称',
    description TEXT COMMENT '描述',
    is_system   TINYINT DEFAULT 0 COMMENT '1=系统内置，不可删除',
    hermes_tools JSON COMMENT '角色可用的 Hermes 工具集（web/memory/file/terminal...）',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='角色表';

-- 3. 角色权限关联表
CREATE TABLE IF NOT EXISTS role_permissions (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    role_id     BIGINT NOT NULL COMMENT '角色ID',
    permission  VARCHAR(128) NOT NULL COMMENT '权限标识',
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_role_perm (role_id, permission),
    INDEX idx_role (role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='角色权限表';

-- 4. 用户权限覆盖表
CREATE TABLE IF NOT EXISTS user_permissions (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id     BIGINT NOT NULL COMMENT '用户ID',
    permission  VARCHAR(128) NOT NULL COMMENT '权限标识',
    granted     TINYINT DEFAULT 1 COMMENT '1=授予 0=拒绝',
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_perm (user_id, permission),
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户权限表';

-- 5. 权限定义表（代码启动时由 permission_defs 播种）
CREATE TABLE IF NOT EXISTS permission_defs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    `key` VARCHAR(128) NOT NULL UNIQUE,
    label VARCHAR(128) NOT NULL,
    description TEXT,
    group_name VARCHAR(64) NOT NULL,
    group_label VARCHAR(128) NOT NULL,
    sort_order INT DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='权限定义表';

-- 6. 技能分类表
CREATE TABLE IF NOT EXISTS categories (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(128) NOT NULL UNIQUE COMMENT '分类名称',
    slug        VARCHAR(128) NOT NULL UNIQUE COMMENT '分类标识',
    description TEXT COMMENT '描述',
    sort_order  INT DEFAULT 0 COMMENT '排序',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='技能分类表';

-- 7. 组件状态表（技能/智能体启用禁用）
CREATE TABLE IF NOT EXISTS item_status (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    item_type   VARCHAR(16) NOT NULL DEFAULT 'skill' COMMENT 'skill / agent',
    item_name   VARCHAR(128) NOT NULL COMMENT '技能或智能体名称',
    enabled     TINYINT DEFAULT 1 COMMENT '1=启用 0=禁用',
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_item (item_type, item_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='组件状态表';

-- 注：pending_index 表已废弃删除，功能由 content_pool 表替代

-- 8. 对话记录表（user_id 统一为 BIGINT，与 users.id 一致）
CREATE TABLE IF NOT EXISTS conversations (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id      VARCHAR(128) NOT NULL COMMENT '会话ID',
    user_id         BIGINT NOT NULL COMMENT '用户ID',
    chat_mode       VARCHAR(32) DEFAULT 'normal' COMMENT '对话模式',
    user_question   TEXT NOT NULL COMMENT '用户问题',
    agent_answer    LONGTEXT NOT NULL COMMENT 'AI回答',
    status          TINYINT DEFAULT 1 COMMENT '0删除 1完成 2异常 3中断 4进行中',
    session_title   VARCHAR(255) COMMENT '会话标题',
    source          VARCHAR(20) DEFAULT 'web' COMMENT '消息来源: web/wechat/feishu',
    metadata        JSON COMMENT '扩展字段',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_session (session_id),
    INDEX idx_user (user_id),
    INDEX idx_created_at (created_at),
    INDEX idx_user_created (user_id, created_at),
    INDEX idx_user_status_created (user_id, status, created_at DESC)  -- 用户会话列表查询优化
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='对话记录表';

-- 9. 附件表
CREATE TABLE IF NOT EXISTS attachments (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id      VARCHAR(128) COMMENT '会话ID',
    conversation_id BIGINT COMMENT '关联对话ID',
    file_type       INT DEFAULT 0 COMMENT '1=Word 2=Excel 3=PDF 4=图片',
    file_name       VARCHAR(512) DEFAULT '' COMMENT '文件名',
    file_path       TEXT COMMENT '文件路径',
    file_size       BIGINT DEFAULT 0 COMMENT '文件大小',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session (session_id),
    INDEX idx_conv (conversation_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='附件表';

-- 10. 用户配置表（KV存储）
CREATE TABLE IF NOT EXISTS user_configs (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id     BIGINT NOT NULL COMMENT '用户ID',
    config_key  VARCHAR(128) NOT NULL COMMENT '配置键',
    config_val  TEXT COMMENT '配置值',
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_key (user_id, config_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户配置表';

-- 11. 个人邮箱表
CREATE TABLE IF NOT EXISTS personal_emails (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    email VARCHAR(256) NOT NULL DEFAULT '',
    is_current TINYINT DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_pem_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='个人邮箱表';

-- 12. 技能元信息表
CREATE TABLE IF NOT EXISTS skill_meta (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    owner_id BIGINT NOT NULL,
    category VARCHAR(50) DEFAULT '',
    status VARCHAR(20) DEFAULT 'approved',
    locked TINYINT DEFAULT 0,
    reviewed_by BIGINT DEFAULT NULL,
    reviewed_at DATETIME DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_owner (owner_id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='技能元信息表';

-- 13. 内容池（技能/智能体上架审核）
CREATE TABLE IF NOT EXISTS content_pool (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    content_type VARCHAR(16) NOT NULL,
    content_name VARCHAR(256) NOT NULL,
    owner_id BIGINT NOT NULL,
    submitted_by BIGINT NOT NULL,
    status VARCHAR(16) DEFAULT 'pending',
    reviewed_by BIGINT DEFAULT NULL,
    reviewed_at DATETIME DEFAULT NULL,
    reject_reason TEXT,
    metadata JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_type_name (content_type, content_name),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='内容池表';

-- 14. 内容安装记录
CREATE TABLE IF NOT EXISTS content_installs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    content_type VARCHAR(16) NOT NULL,
    content_name VARCHAR(256) NOT NULL,
    user_id BIGINT NOT NULL,
    installed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_install (content_type, content_name, user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='内容安装记录表';

-- 14b. 用户绑定表（微信/飞书等平台账号绑定）
CREATE TABLE IF NOT EXISTS user_bindings (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL COMMENT '关联 users.id',
    platform VARCHAR(20) NOT NULL COMMENT 'wechat/feishu',
    open_id VARCHAR(128) NOT NULL COMMENT '微信id/飞书open_id',
    nickname VARCHAR(128) DEFAULT '' COMMENT '对方昵称',
    enabled TINYINT DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_platform_openid (platform, open_id),
    UNIQUE KEY uk_user_platform (user_id, platform)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户绑定表';

-- ════════════════════════════════════════════════════════════
-- 二、定时任务
-- ════════════════════════════════════════════════════════════

-- 15. 定时任务表
CREATE TABLE IF NOT EXISTS cron_jobs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    name VARCHAR(255) NOT NULL DEFAULT '',
    prompt TEXT NOT NULL,
    schedule_type VARCHAR(20) NOT NULL DEFAULT 'cron',
    schedule_value VARCHAR(128) NOT NULL DEFAULT '',
    deliver_to VARCHAR(20) NOT NULL DEFAULT 'wechat',
    report_format VARCHAR(20) NOT NULL DEFAULT 'pdf',
    email_sender_id BIGINT DEFAULT NULL,
    email_receiver_id BIGINT DEFAULT NULL,
    receiver_email VARCHAR(256) DEFAULT '',
    enabled TINYINT DEFAULT 1,
    last_run_at DATETIME DEFAULT NULL,
    next_run_at DATETIME DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_cron_user (user_id),
    INDEX idx_cron_next (next_run_at, enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='定时任务表';

-- 16. 定时任务执行记录
CREATE TABLE IF NOT EXISTS cron_executions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id BIGINT NOT NULL,
    session_id VARCHAR(128) DEFAULT '',
    status TINYINT DEFAULT 0,
    result_text LONGTEXT,
    error_message TEXT,
    deliver_status VARCHAR(128) DEFAULT '',
    quality_issues VARCHAR(1024) DEFAULT '' COMMENT '质量问题标记',
    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at DATETIME DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_cexec_job (job_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='定时任务执行记录表';

-- ════════════════════════════════════════════════════════════
-- 三、LLM 链路可观测性
-- ════════════════════════════════════════════════════════════

-- 17. LLM 调用链路表
CREATE TABLE IF NOT EXISTS traces (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id      VARCHAR(64) NOT NULL,
    user_id         BIGINT NOT NULL,
    source          VARCHAR(16) DEFAULT 'web' COMMENT '来源: web/wechat/feishu',
    api_request_id  VARCHAR(512) UNIQUE COMMENT 'Hermes 唯一请求标识',
    model           VARCHAR(128) NOT NULL,
    provider        VARCHAR(64),
    turn_index      INT DEFAULT 0,
    input_tokens       INT DEFAULT 0,
    output_tokens      INT DEFAULT 0,
    cache_read_tokens  INT DEFAULT 0,
    cache_write_tokens INT DEFAULT 0,
    reasoning_tokens   INT DEFAULT 0,
    total_tokens       INT DEFAULT 0,
    latency_ms      INT DEFAULT 0,
    estimated_cost_usd DECIMAL(10,6) DEFAULT 0,
    finish_reason   VARCHAR(32),
    api_call_count  INT DEFAULT 0,
    status          TINYINT DEFAULT 2 COMMENT '0=失败 1=成功 2=进行中',
    error_message   TEXT,
    prompt_text     LONGTEXT,
    completion_text LONGTEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session (session_id),
    INDEX idx_user_time (user_id, created_at),
    INDEX idx_model (model),
    INDEX idx_source (source),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at),
    INDEX idx_user_created_status (user_id, created_at, status)  -- 时间范围查询优化
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='LLM调用链路表';

-- 18. 工具调用 span 表
CREATE TABLE IF NOT EXISTS trace_spans (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    trace_id    BIGINT NOT NULL,
    span_type   VARCHAR(16) DEFAULT 'tool_call',
    tool_name   VARCHAR(128) NOT NULL,
    duration_ms INT DEFAULT 0,
    status      TINYINT DEFAULT 1 COMMENT '0=失败 1=成功',
    error_message TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_trace (trace_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='工具调用Span表';

-- 19. 采集配置表（KV）
CREATE TABLE IF NOT EXISTS trace_config (
    `key`     VARCHAR(64) PRIMARY KEY,
    value       TEXT,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='trace采集配置表';

-- 20. 每日每用户聚合表（排行榜数据源，user_id 统一为 BIGINT）
CREATE TABLE IF NOT EXISTS daily_user_stats (
    stat_date      DATE NOT NULL,
    user_id        BIGINT NOT NULL,
    total_tokens   BIGINT DEFAULT 0,
    api_calls      INT DEFAULT 0,
    updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (stat_date, user_id),
    INDEX idx_date (stat_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='每日用户聚合统计表';

-- ════════════════════════════════════════════════════════════
-- 四、知识库（KB/RAG）
-- ════════════════════════════════════════════════════════════

-- 21. 知识库表
CREATE TABLE IF NOT EXISTS kb_knowledge_base (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    kb_name VARCHAR(255) NOT NULL COMMENT '知识库名称',
    kb_type VARCHAR(50) DEFAULT 'general' COMMENT '知识库类型：general/text2sql/history_correct',
    description TEXT COMMENT '知识库描述',
    user_id BIGINT NOT NULL COMMENT '创建者用户ID',
    is_enabled TINYINT DEFAULT 1 COMMENT '是否启用：1=启用 0=禁用',
    is_system TINYINT DEFAULT 0 COMMENT '系统内置知识库：1=系统内置（不可删除） 0=用户创建',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user (user_id),
    INDEX idx_enabled (is_enabled),
    INDEX idx_type (kb_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识库表';

-- 22. 知识库文档表
CREATE TABLE IF NOT EXISTS kb_documents (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    kb_id BIGINT DEFAULT NULL COMMENT '所属知识库ID，NULL表示默认知识库',
    user_id BIGINT NOT NULL,
    original_name VARCHAR(512) NOT NULL,
    stored_name VARCHAR(128) NOT NULL,
    ext VARCHAR(16) DEFAULT '',
    size_bytes BIGINT DEFAULT 0,
    sha256 CHAR(64) DEFAULT '',
    page_count INT DEFAULT 0,
    char_count INT DEFAULT 0,
    chunk_count INT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'parsed',
    parser VARCHAR(32) DEFAULT 'builtin',
    chunk_size INT DEFAULT 1000,
    chunk_overlap INT DEFAULT 200,
    chunk_strategy VARCHAR(16) NOT NULL DEFAULT 'fixed',
    error_message TEXT,
    content_text LONGTEXT,
    vectorized TINYINT DEFAULT 0,
    graph_extracted TINYINT DEFAULT 0 COMMENT '是否已提取实体关系到知识图谱',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_kb (kb_id),
    INDEX idx_kb_user (user_id, created_at),
    INDEX idx_status (status),
    INDEX idx_vectorized (vectorized)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识库文档表';

-- 23. 知识库分块表
CREATE TABLE IF NOT EXISTS kb_chunks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    kb_id BIGINT DEFAULT NULL COMMENT '所属知识库ID，NULL表示默认知识库',
    document_id BIGINT NOT NULL,
    chunk_index INT NOT NULL,
    content LONGTEXT,
    char_count INT DEFAULT 0,
    page_start INT DEFAULT NULL,
    page_end INT DEFAULT NULL,
    metadata JSON,
    strategy VARCHAR(16) NOT NULL DEFAULT 'fixed',
    kind VARCHAR(16) NOT NULL DEFAULT 'base',
    is_manual_edit TINYINT DEFAULT 0 COMMENT '是否手动修改',
    manual_edit_reason VARCHAR(500) DEFAULT NULL COMMENT '修改原因',
    original_content TEXT COMMENT '原始内容（用于回滚）',
    manual_edit_at DATETIME DEFAULT NULL COMMENT '手动修改时间',
    topic_id BIGINT DEFAULT NULL,
    parent_chunk_id BIGINT DEFAULT NULL COMMENT '父子分片：子片指向父片的 ID',
    scope_layer_id BIGINT DEFAULT NULL COMMENT '数据层级ID（NULL=继承KB层级，非NULL=单独指定）',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_doc_chunk (document_id, chunk_index),
    INDEX idx_kb (kb_id),
    INDEX idx_doc (document_id),
    INDEX idx_topic_id (topic_id),
    INDEX idx_parent (parent_chunk_id),
    INDEX idx_scope_layer (scope_layer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识库分块表';

-- 24. 知识库主题表
CREATE TABLE IF NOT EXISTS kb_topics (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    document_id BIGINT NOT NULL,
    title VARCHAR(255) DEFAULT '',
    source VARCHAR(16) DEFAULT 'structure',
    page_start INT DEFAULT NULL,
    page_end INT DEFAULT NULL,
    char_count INT DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_topic_doc (document_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识库主题表';

-- 25. RAG 测评集
CREATE TABLE IF NOT EXISTS kb_eval_sets (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    name VARCHAR(255) NOT NULL DEFAULT '',
    description VARCHAR(512) DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_eval_user (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RAG测评集表';

-- 26. RAG 测评题目
CREATE TABLE IF NOT EXISTS kb_eval_items (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    eval_set_id BIGINT NOT NULL,
    question TEXT NOT NULL,
    ground_truth_chunk_ids JSON,
    ground_truth_chunk_content JSON,
    ground_truth_answer TEXT,
    sort_order INT DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_eval_set (eval_set_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RAG测评题目表';

-- 27. RAG 测评运行
CREATE TABLE IF NOT EXISTS kb_eval_runs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    eval_set_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    config JSON,
    status VARCHAR(16) DEFAULT 'running',
    progress JSON,
    metrics JSON,
    error TEXT,
    started_at DATETIME,
    finished_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_eval_runs (eval_set_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RAG测评运行表';

-- 28. RAG 测评结果
CREATE TABLE IF NOT EXISTS kb_eval_results (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id BIGINT NOT NULL,
    item_id BIGINT NOT NULL,
    question TEXT,
    retrieved_chunks JSON,
    metrics JSON,
    answer TEXT,
    judge_metrics JSON,
    classification VARCHAR(32) DEFAULT '' COMMENT 'RAG评测六态分类',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_eval_result (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RAG测评结果表';

-- 29. RAG 检索日志（评测闭环）
CREATE TABLE IF NOT EXISTS kb_retrieval_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    thread_id VARCHAR(128) DEFAULT '',
    conversation_id BIGINT DEFAULT NULL,
    query TEXT NOT NULL,
    top_k INT DEFAULT 5,
    retriever VARCHAR(16) DEFAULT '',
    chunk_ids JSON,
    hit_count INT DEFAULT 0,
    elapsed_ms INT DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_retrieval_user (user_id, created_at),
    INDEX idx_retrieval_thread (thread_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RAG检索日志表';

-- 30. RAG 用户反馈（评测闭环）
CREATE TABLE IF NOT EXISTS kb_feedback (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    conversation_id BIGINT DEFAULT NULL,
    thread_id VARCHAR(128) DEFAULT '',
    rating TINYINT NOT NULL DEFAULT 0,
    comment VARCHAR(512) DEFAULT '',
    retrieved_chunk_ids JSON,
    status VARCHAR(16) NOT NULL DEFAULT 'open',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_feedback_user (user_id, created_at),
    INDEX idx_feedback_conv (conversation_id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RAG用户反馈表';

-- 31. RAG 优化建议（评测闭环）
CREATE TABLE IF NOT EXISTS kb_eval_suggestions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    eval_set_id BIGINT DEFAULT NULL,
    source VARCHAR(16) NOT NULL DEFAULT 'eval',
    kind VARCHAR(32) NOT NULL DEFAULT 'manual',
    summary TEXT,
    evidence JSON,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    before_metrics JSON,
    after_metrics JSON,
    linked_run_ids JSON,
    attempts INT DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    resolved_at DATETIME DEFAULT NULL,
    suggestion_type VARCHAR(32) DEFAULT 'general' COMMENT 'general/sql_example/chunk_modify/mixed',
    sql_example_content TEXT COMMENT 'SQL示例内容（Markdown格式）',
    sql_example_approved TINYINT DEFAULT 0 COMMENT 'SQL示例是否已审批通过',
    sql_example_document_id BIGINT DEFAULT NULL COMMENT 'SQL示例入库后的文档ID',
    chunk_modify_suggestions JSON COMMENT '对chunks的修改建议列表',
    target_kb_id BIGINT DEFAULT NULL COMMENT '目标知识库ID（历史正确案例）',
    verification_query VARCHAR(512) DEFAULT '' COMMENT '验证用的原始问题',
    verification_result JSON COMMENT '验证结果',
    INDEX idx_suggestion_user (user_id, status, created_at),
    INDEX idx_suggestion_set (eval_set_id),
    INDEX idx_status_created (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RAG优化建议表';

-- 31b. 知识图谱归档表（P2 优化：冷热分离）
CREATE TABLE IF NOT EXISTS kg_archived_entities (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    entity_id VARCHAR(64) NOT NULL COMMENT '实体ID（Neo4j 中的 id）',
    name VARCHAR(255) NOT NULL COMMENT '实体名称',
    entity_type VARCHAR(32) NOT NULL COMMENT '实体类型',
    user_id BIGINT DEFAULT NULL COMMENT '用户ID（多租户隔离）',
    data JSON NOT NULL COMMENT '完整的实体数据（JSON 格式）',
    archived_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '归档时间',
    UNIQUE KEY uk_entity_id (entity_id),
    INDEX idx_archived_at (archived_at),
    INDEX idx_entity_type (entity_type),
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识图谱归档表（冷热分离）';

-- 31c. 知识图谱审核候选表（提取→审核→更正 闭环）
CREATE TABLE IF NOT EXISTS kg_alignment_candidates (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL COMMENT '所属用户',
    candidate_type VARCHAR(16) NOT NULL COMMENT 'duplicate/name_collision/low_confidence/relation_direction',
    entity_a_id VARCHAR(64) NOT NULL COMMENT '实体A（Neo4j id）',
    entity_a_name VARCHAR(255) DEFAULT '' COMMENT '实体A名称',
    entity_b_id VARCHAR(64) DEFAULT NULL COMMENT '实体B/关系ID',
    entity_b_name VARCHAR(255) DEFAULT '' COMMENT '实体B名称',
    score DECIMAL(4,3) DEFAULT NULL COMMENT '置信度/相似度',
    reason TEXT COMMENT '标记原因',
    status VARCHAR(16) DEFAULT 'pending' COMMENT 'pending/merged/confirmed/ignored/edited',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at DATETIME DEFAULT NULL,
    INDEX idx_user_status (user_id, status),
    INDEX idx_candidate_type (candidate_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识图谱审核候选表';

-- 31d. RAG Embedding 模型配置
CREATE TABLE IF NOT EXISTS rag_embedding_configs (
    id INT NOT NULL AUTO_INCREMENT,
    user_id INT DEFAULT 1,
    config_name VARCHAR(128) DEFAULT 'Default',
    provider_type VARCHAR(32) DEFAULT 'OPENAI_COMPATIBLE',
    base_url VARCHAR(512) DEFAULT '',
    api_key VARCHAR(512) DEFAULT '',
    model_name VARCHAR(128) DEFAULT 'text-embedding-3-small',
    dimension INT DEFAULT 1024,
    batch_size INT DEFAULT 8,
    timeout_seconds INT DEFAULT 180,
    send_dimensions TINYINT DEFAULT 0,
    is_current TINYINT DEFAULT 1,
    enabled TINYINT DEFAULT 1,
    last_test_status VARCHAR(32) DEFAULT NULL,
    last_test_message TEXT,
    last_test_time DATETIME DEFAULT NULL,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RAG Embedding 模型配置表';

-- 31e. 知识图谱变更日志
CREATE TABLE IF NOT EXISTS graph_change_log (
    id BIGINT NOT NULL AUTO_INCREMENT,
    user_id BIGINT NOT NULL COMMENT '操作用户ID',
    event_type VARCHAR(32) NOT NULL COMMENT 'entity_created/entity_updated/entity_deleted/relation_created/relation_deleted/relation_updated/relation_flipped',
    entity_id VARCHAR(64) DEFAULT NULL COMMENT '实体/关系 Neo4j ID',
    entity_name VARCHAR(255) DEFAULT '' COMMENT '实体/关系名称',
    entity_type VARCHAR(32) DEFAULT '' COMMENT '实体类型（person/location/...）',
    before_json JSON DEFAULT NULL COMMENT '修改前快照',
    after_json JSON DEFAULT NULL COMMENT '修改后快照',
    ip_address VARCHAR(64) DEFAULT '' COMMENT '操作IP',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_log_user (user_id, created_at),
    KEY idx_log_entity (entity_id),
    KEY idx_log_event (event_type),
    KEY idx_log_time (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识图谱变更日志表';

-- 31f. 知识图谱社区表
CREATE TABLE IF NOT EXISTS kg_communities (
    id VARCHAR(64) NOT NULL COMMENT '社区ID (community_xxx)',
    user_id BIGINT NOT NULL COMMENT '所属用户',
    level INT NOT NULL DEFAULT 0 COMMENT '层级 (0=最细, 数字越大越粗)',
    parent_id VARCHAR(64) DEFAULT NULL COMMENT '父社区ID',
    entity_count INT DEFAULT 0 COMMENT '包含实体数',
    entity_ids JSON DEFAULT NULL COMMENT '包含的实体ID列表',
    relationship_count INT DEFAULT 0 COMMENT '内部关系数',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_community_user (user_id),
    KEY idx_community_level (level),
    KEY idx_community_parent (parent_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识图谱社区表';

-- 31g. 知识图谱社区报告表
CREATE TABLE IF NOT EXISTS kg_community_reports (
    id BIGINT NOT NULL AUTO_INCREMENT,
    community_id VARCHAR(64) NOT NULL COMMENT '社区ID',
    title VARCHAR(255) DEFAULT '' COMMENT '社区标题',
    summary TEXT COMMENT '摘要 (50-100字)',
    full_content TEXT COMMENT '完整报告',
    summary_embedding JSON DEFAULT NULL COMMENT '摘要向量 (用于相似度匹配)',
    rating INT DEFAULT 5 COMMENT '重要性评分 (1-10)',
    findings JSON DEFAULT NULL COMMENT '关键发现列表',
    top_entities JSON DEFAULT NULL COMMENT '核心实体列表',
    status VARCHAR(16) DEFAULT 'pending' COMMENT 'pending/generating/completed/failed',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_community (community_id),
    KEY idx_report_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识图谱社区报告表';

-- 31h. 知识图谱 Claim 表（事实陈述）
-- Claim 是从文本中提取的事实陈述，不同于实体和关系：
-- - Entity: 人/物/概念
-- - Relation: 实体间关系
-- - Claim: 事实陈述（如"关羽在公元 219 年败走麦城"）
CREATE TABLE IF NOT EXISTS kg_claims (
    id BIGINT NOT NULL AUTO_INCREMENT,
    claim_id VARCHAR(64) NOT NULL COMMENT 'Claim ID（Neo4j id）',
    claim_type VARCHAR(16) NOT NULL DEFAULT 'fact' COMMENT 'fact/opinion/inference',
    claim_text TEXT NOT NULL COMMENT 'Claim 文本',
    subject VARCHAR(255) NOT NULL COMMENT '主体实体名称',
    object VARCHAR(255) DEFAULT '' COMMENT '客体实体名称',
    claim_value VARCHAR(255) DEFAULT '' COMMENT 'Claim 值（如"败走"）',
    time VARCHAR(64) DEFAULT '' COMMENT '时间属性',
    confidence DECIMAL(3,2) DEFAULT 1.00 COMMENT '置信度 (0-1)',
    status VARCHAR(16) DEFAULT 'active' COMMENT 'active/refuted/superseded',
    source_entity_id VARCHAR(64) DEFAULT '' COMMENT '来源实体 ID',
    source_chunk_id BIGINT DEFAULT NULL COMMENT '来源文本块 ID',
    source_document_id BIGINT DEFAULT NULL COMMENT '来源文档 ID',
    user_id BIGINT DEFAULT NULL COMMENT '用户 ID（记忆场景）',
    properties JSON DEFAULT NULL COMMENT '额外属性',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_claim_id (claim_id),
    KEY idx_subject (subject),
    KEY idx_object (object),
    KEY idx_source_document (source_document_id),
    KEY idx_source_chunk (source_chunk_id),
    KEY idx_user (user_id),
    KEY idx_confidence (confidence DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识图谱 Claim 表（事实陈述）';

-- ════════════════════════════════════════════════════════════
-- 五、模型配置
-- ════════════════════════════════════════════════════════════

-- 32. 模型配置表（宽表兼容 chat/embedding；api_key 为 AES-256-GCM 加密存储）
CREATE TABLE IF NOT EXISTS model_configs (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id       BIGINT DEFAULT 1,
    config_name   VARCHAR(128) NOT NULL DEFAULT '',
    config_type   VARCHAR(32)  NOT NULL DEFAULT 'URL',
    api_url       VARCHAR(512) DEFAULT '',
    api_key       VARCHAR(512) DEFAULT '',
    model_name    VARCHAR(128) DEFAULT '',
    provider      VARCHAR(64)  DEFAULT '',
    category      VARCHAR(32)  NOT NULL DEFAULT 'chat',
    is_multimodal TINYINT DEFAULT 0,
    dimension     INT DEFAULT 0,
    send_dimensions TINYINT DEFAULT 0,
    reasoning_effort VARCHAR(16) DEFAULT '',
    is_current    TINYINT DEFAULT 0,
    enabled       TINYINT DEFAULT 1,
    priority      INT DEFAULT 0 COMMENT '降级优先级，数字越小优先级越高',
    cost_per_1k_input  DECIMAL(10,6) DEFAULT 0 COMMENT '每1000输入token成本(USD)',
    cost_per_1k_output DECIMAL(10,6) DEFAULT 0 COMMENT '每1000输出token成本(USD)',
    context_length INT DEFAULT 0 COMMENT '模型上下文窗口大小',
    capabilities JSON COMMENT '模型能力标签 {"code":true,"vision":true,"json_mode":true}',
    description TEXT COMMENT '模型描述/备注',
    last_test_status   VARCHAR(64),
    last_test_message  VARCHAR(512),
    last_test_time     DATETIME,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_current (user_id, is_current),
    INDEX idx_category (category),
    INDEX idx_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='模型配置表';

-- 32a. 模型路由配置表（降级链 + 场景路由，KV JSON 存储）
CREATE TABLE IF NOT EXISTS model_route_settings (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    setting_key  VARCHAR(64) NOT NULL UNIQUE COMMENT '配置键: fallback_chain / scene_routing',
    setting_value JSON NOT NULL COMMENT '配置值（JSON）',
    description  VARCHAR(256) DEFAULT '',
    updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='模型路由配置表';

-- 预置路由配置
INSERT IGNORE INTO model_route_settings (setting_key, setting_value, description) VALUES
('fallback_chain', '{"model_ids": []}', '降级链：按顺序排列的 model_config ID 列表'),
('scene_routing', '{}', '场景路由：{scene_name: model_config_id}');

-- 32b. 邮件服务器配置表
CREATE TABLE IF NOT EXISTS email_configs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT DEFAULT 1,
    config_name VARCHAR(128) NOT NULL DEFAULT '',
    host VARCHAR(256) NOT NULL DEFAULT '',
    port VARCHAR(8) NOT NULL DEFAULT '587',
    sender_email VARCHAR(256) NOT NULL DEFAULT '',
    sender_name VARCHAR(128) DEFAULT 'AgentForge',
    password VARCHAR(512) DEFAULT '',
    is_current TINYINT DEFAULT 0,
    enabled TINYINT DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_email_current (user_id, is_current)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='邮件服务器配置表';

-- 32c. 平台配置表（KV存储）
CREATE TABLE IF NOT EXISTS platform_config (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    platform VARCHAR(20) NOT NULL COMMENT 'wechat/feishu/email',
    config_json JSON NOT NULL COMMENT '平台配置JSON',
    enabled TINYINT DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_platform (platform)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='平台配置表';

-- ════════════════════════════════════════════════════════════
-- 六、安全控制
-- ════════════════════════════════════════════════════════════

-- 33. 主机白名单
CREATE TABLE IF NOT EXISTS host_whitelist (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    host_identifier VARCHAR(128) NOT NULL,
    access_user VARCHAR(64) DEFAULT '',
    access_port INT DEFAULT 22,
    allowed_actions VARCHAR(256) DEFAULT '',
    auth_method VARCHAR(16) DEFAULT 'password' COMMENT 'password/ssh_key',
    auth_secret TEXT COMMENT '加密存储的认证凭据',
    remark VARCHAR(256) DEFAULT '',
    status TINYINT DEFAULT 1,
    expires_at DATETIME DEFAULT NULL,
    created_by BIGINT DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_host (host_identifier)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='主机白名单表';

-- 34. 执行审批日志
CREATE TABLE IF NOT EXISTS exec_approval_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    thread_id VARCHAR(128) NOT NULL,
    user_id BIGINT DEFAULT NULL,
    command TEXT,
    decision VARCHAR(32) DEFAULT '',
    allow_permanent TINYINT DEFAULT 0,
    confirmed_by_name VARCHAR(64) DEFAULT '',
    confirmed_by_user_id BIGINT DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_approval_thread (thread_id, created_at),
    INDEX idx_decision (decision)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='执行审批日志表';

-- 35. 命令黑名单
CREATE TABLE IF NOT EXISTS command_blacklist (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    pattern VARCHAR(512) NOT NULL COMMENT '正则表达式',
    description VARCHAR(256) DEFAULT '' COMMENT '规则描述',
    enabled TINYINT DEFAULT 1 COMMENT '0=禁用 1=启用',
    created_by BIGINT DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='命令黑名单表';

-- 36. AI 操作审计日志
CREATE TABLE IF NOT EXISTS agent_operation_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    thread_id VARCHAR(128) NOT NULL,
    user_id BIGINT DEFAULT NULL,
    username VARCHAR(64) DEFAULT '',
    tool_name VARCHAR(128) NOT NULL,
    operation_type VARCHAR(32) DEFAULT 'tool_call' COMMENT 'tool_call / ssh_remote / blocked',
    command TEXT,
    args_summary VARCHAR(1024) DEFAULT '' COMMENT '参数摘要（截断）',
    result_summary VARCHAR(1024) DEFAULT '' COMMENT '结果摘要（截断）',
    target_host VARCHAR(128) DEFAULT '' COMMENT '远程目标主机（ssh/scp 场景）',
    status TINYINT DEFAULT 1 COMMENT '0=拦截/失败 1=成功 2=已审批执行',
    error_message TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_op_thread (thread_id, created_at),
    INDEX idx_op_user (user_id, created_at),
    INDEX idx_op_host (target_host),
    INDEX idx_operation_type (operation_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI操作审计日志表';

-- 37. SQL 操作审计日志
CREATE TABLE IF NOT EXISTS sql_operation_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    thread_id VARCHAR(128) NOT NULL,
    user_id BIGINT DEFAULT NULL,
    username VARCHAR(64) DEFAULT '',
    query TEXT,
    status TINYINT DEFAULT 1 COMMENT '0=失败 1=成功',
    error_message TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_sql_thread (thread_id, created_at),
    INDEX idx_sql_user (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='SQL操作审计日志表';

-- 记忆操作审计日志
CREATE TABLE IF NOT EXISTS memory_operation_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT DEFAULT NULL,
    username VARCHAR(64) DEFAULT '',
    action VARCHAR(32) NOT NULL COMMENT 'create / read / update / delete / search / promote / restore / consolidate',
    memory_id BIGINT DEFAULT NULL COMMENT '操作对象记忆ID（search 时可为空）',
    memory_layer VARCHAR(16) DEFAULT '' COMMENT 'legacy / episodic / semantic',
    detail VARCHAR(1024) DEFAULT '' COMMENT '操作详情摘要',
    ip_address VARCHAR(64) DEFAULT '',
    status TINYINT DEFAULT 1 COMMENT '0=失败 1=成功',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_mem_op_user (user_id, created_at),
    INDEX idx_mem_op_action (action),
    INDEX idx_mem_op_memory (memory_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='记忆操作审计日志表';

-- ════════════════════════════════════════════════════════════
-- 七、默认数据
-- ════════════════════════════════════════════════════════════

-- 默认角色（代码首次启动会同步权限到这些角色）
INSERT IGNORE INTO roles (name, display_name, description, is_system) VALUES
('super_admin', '超级管理员', '拥有系统全部权限', 1),
('admin', '管理员', '审核和配置权限', 1),
('user', '普通用户', '基础权限', 1);

-- 角色权限（仅当角色不存在时插入）
-- 注意：super_admin 的权限由代码 seed_to_db() 自动同步所有权限
-- 当前权限 key 列表（15 个，与 backend/permission/builtin.py DEFAULT_ROLE_PERMISSIONS 一致）：
--   chat.use, skill.create, skill.pool.review, skill.manage,
--   memory.view, memory.edit, terminal.audit, cron.create,
--   system.manage, system.config, trace.view, trace.manage,
--   kb.manage, kb.eval, graph.manage
INSERT IGNORE INTO role_permissions (role_id, permission)
SELECT r.id, p.permission FROM roles r
JOIN (
    -- admin: 全部 15 个权限
    SELECT 'admin' as role, 'chat.use' as permission UNION ALL
    SELECT 'admin', 'skill.create' UNION ALL SELECT 'admin', 'skill.pool.review' UNION ALL SELECT 'admin', 'skill.manage' UNION ALL
    SELECT 'admin', 'memory.view' UNION ALL SELECT 'admin', 'memory.edit' UNION ALL
    SELECT 'admin', 'terminal.audit' UNION ALL
    SELECT 'admin', 'cron.create' UNION ALL
    SELECT 'admin', 'system.manage' UNION ALL SELECT 'admin', 'system.config' UNION ALL
    SELECT 'admin', 'trace.view' UNION ALL SELECT 'admin', 'trace.manage' UNION ALL
    SELECT 'admin', 'kb.manage' UNION ALL SELECT 'admin', 'kb.eval' UNION ALL SELECT 'admin', 'graph.manage' UNION ALL
    -- user: 基础可用集合（6 个）
    SELECT 'user', 'chat.use' UNION ALL
    SELECT 'user', 'skill.create' UNION ALL
    SELECT 'user', 'memory.view' UNION ALL SELECT 'user', 'memory.edit' UNION ALL
    SELECT 'user', 'cron.create' UNION ALL
    SELECT 'user', 'trace.view'
) p ON p.role = r.name
WHERE NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id);

-- 默认分类
INSERT IGNORE INTO categories (name, slug, description) VALUES
('工程', 'engineering', '软件工程、开发工具相关技能'),
('运维', 'devops', '系统运维、安全加固相关技能'),
('研究', 'research', '调研、分析、学术相关技能');

-- 默认用户（代码启动时若 admin 不存在会自动创建 admin/admin123，此处预留占位）
INSERT IGNORE INTO users (username, password, role, status)
VALUES ('admin', 'REPLACE_WITH_HASH', 'super_admin', 1);

-- trace_config 预置项
INSERT IGNORE INTO trace_config (`key`, value) VALUES
('trace_detail_enabled', 'false'),
('trace_max_text_chars', '10000'),
('trace_retention_days', '30');

-- ════════════════════════════════════════════════════════════
-- 八、记忆系统（三层架构：Legacy / Episodic / Semantic）
-- ════════════════════════════════════════════════════════════

-- 38. 记忆项（Legacy 层）
CREATE TABLE IF NOT EXISTS memory_items (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL COMMENT '用户ID',
    memory_type VARCHAR(32) NOT NULL COMMENT 'preference/fact/event/skill',
    content TEXT NOT NULL COMMENT '记忆内容',
    embedding_id VARCHAR(128) DEFAULT '' COMMENT '向量库ID（Milvus/ChromaDB）',
    importance_score FLOAT DEFAULT 0.5 COMMENT '重要性分数 0-1',
    access_count INT DEFAULT 0 COMMENT '访问次数',
    last_accessed_at DATETIME DEFAULT NULL COMMENT '最后访问时间',
    decay_rate FLOAT DEFAULT 0.95 COMMENT '衰减率',
    ttl_days INT DEFAULT 60 COMMENT '存活天数',
    expires_at DATETIME DEFAULT NULL COMMENT '过期时间',
    source_thread_id VARCHAR(128) DEFAULT '' COMMENT '来源会话ID',
    source_round INT DEFAULT 0 COMMENT '来源轮次',
    merged_from TEXT COMMENT '合并来源ID列表（JSON数组）',
    graph_node_id VARCHAR(128) DEFAULT '' COMMENT 'Neo4j节点ID',
    is_user_edited TINYINT DEFAULT 0 COMMENT '用户是否手动编辑',
    version BIGINT NOT NULL DEFAULT 1 COMMENT '版本号',
    content_hash VARCHAR(64) NOT NULL DEFAULT '' COMMENT '内容哈希',
    deleted_at DATETIME DEFAULT NULL COMMENT '软删除时间',
    vector_id VARCHAR(128) DEFAULT NULL COMMENT 'Milvus向量ID',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_memory_user (user_id, memory_type),
    INDEX idx_memory_type (memory_type),
    INDEX idx_memory_expires (expires_at),
    INDEX idx_memory_importance (importance_score),
    INDEX idx_memory_version (id, version),
    INDEX idx_memory_deleted (deleted_at),
    FULLTEXT KEY ft_memory_content (content)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='记忆项表（Legacy 层）';

-- 39. 记忆同步事件队列（Outbox 模式核心表）
CREATE TABLE IF NOT EXISTS memory_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(36) NOT NULL UNIQUE COMMENT '事件唯一ID（UUID）',
    memory_id BIGINT NOT NULL COMMENT '关联的记忆ID',
    memory_version BIGINT NOT NULL COMMENT '事件产生时的记忆版本',
    event_type VARCHAR(32) NOT NULL COMMENT '事件类型：upsert_vector/delete_vector/upsert_graph_node/delete_graph_node',
    target VARCHAR(16) NOT NULL COMMENT '目标库：milvus/neo4j',
    payload JSON COMMENT '事件载荷',
    status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT 'pending/processing/processed/dead',
    attempts INT NOT NULL DEFAULT 0 COMMENT '重试次数',
    available_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '可用于消费的时间',
    locked_at DATETIME DEFAULT NULL COMMENT '被领取的时间',
    locked_by VARCHAR(64) DEFAULT NULL COMMENT '领取者标识',
    processed_at DATETIME DEFAULT NULL COMMENT '处理完成时间',
    last_error TEXT COMMENT '最后一次错误信息',
    memory_layer VARCHAR(16) NOT NULL DEFAULT 'legacy' COMMENT '记忆层级：legacy/episodic/semantic',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_outbox_ready (status, available_at),
    INDEX idx_outbox_memory (memory_id, memory_version),
    INDEX idx_outbox_stale_lock (status, locked_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='记忆同步事件队列（Outbox 模式）';

-- 40. 记忆版本历史
CREATE TABLE IF NOT EXISTS memory_versions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    memory_id BIGINT NOT NULL COMMENT '关联的记忆ID',
    version INT NOT NULL DEFAULT 1 COMMENT '版本号',
    content TEXT NOT NULL COMMENT '历史内容',
    importance_score FLOAT NOT NULL DEFAULT 0.5 COMMENT '历史重要性',
    memory_type VARCHAR(32) DEFAULT NULL COMMENT '历史类型',
    change_reason VARCHAR(64) NOT NULL DEFAULT 'consolidation' COMMENT '变更原因：consolidation/conflict_resolution/user_edit/llm_merge',
    source_memory_id BIGINT DEFAULT NULL COMMENT '合并来源的另一条记忆ID（合并场景）',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_versions_memory (memory_id),
    INDEX idx_versions_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='记忆版本历史';

-- 41. 近期记忆（Episodic 层，30天TTL，带向量）
CREATE TABLE IF NOT EXISTS memory_episodic (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL COMMENT '用户ID',
    memory_type VARCHAR(32) NOT NULL COMMENT 'preference/fact/event/skill',
    content TEXT NOT NULL COMMENT '记忆内容',
    embedding_id VARCHAR(128) DEFAULT '' COMMENT '向量库ID',
    vector_id VARCHAR(128) DEFAULT '' COMMENT '向量ID',
    importance_score FLOAT DEFAULT 0.5 COMMENT '重要性分数 0-1',
    access_count INT DEFAULT 0 COMMENT '访问次数',
    last_accessed_at DATETIME DEFAULT NULL COMMENT '最后访问时间',
    decay_rate FLOAT DEFAULT 0.95 COMMENT '衰减率',
    ttl_days INT DEFAULT 30 COMMENT '存活天数（默认30天）',
    expires_at DATETIME DEFAULT NULL COMMENT '过期时间',
    source_thread_id VARCHAR(128) DEFAULT '' COMMENT '来源会话ID',
    source_round INT DEFAULT 0 COMMENT '来源轮次',
    is_user_edited TINYINT DEFAULT 0 COMMENT '用户是否手动编辑',
    version BIGINT NOT NULL DEFAULT 1 COMMENT '版本号',
    content_hash VARCHAR(64) NOT NULL DEFAULT '' COMMENT '内容哈希',
    promoted_to_semantic TINYINT DEFAULT 0 COMMENT '是否已晋升到 Semantic 层',
    is_user_pinned TINYINT DEFAULT 0 COMMENT '用户置顶（豁免 TTL 淘汰）',
    deleted_at DATETIME DEFAULT NULL COMMENT '软删除时间',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_episodic_user (user_id, memory_type),
    INDEX idx_episodic_expires (expires_at),
    INDEX idx_episodic_importance (importance_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='近期记忆（Episodic 层，30天TTL）';

-- 42. 永久知识（Semantic 层，无TTL，带向量+图）
CREATE TABLE IF NOT EXISTS memory_semantic (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL COMMENT '用户ID',
    memory_type VARCHAR(32) NOT NULL COMMENT 'preference/fact/event/skill',
    content TEXT NOT NULL COMMENT '记忆内容',
    embedding_id VARCHAR(128) DEFAULT '' COMMENT '向量库ID',
    vector_id VARCHAR(128) DEFAULT '' COMMENT '向量ID',
    graph_node_id VARCHAR(128) DEFAULT '' COMMENT 'Neo4j节点ID',
    importance_score FLOAT DEFAULT 0.5 COMMENT '重要性分数 0-1',
    access_count INT DEFAULT 0 COMMENT '访问次数',
    last_accessed_at DATETIME DEFAULT NULL COMMENT '最后访问时间',
    source_thread_id VARCHAR(128) DEFAULT '' COMMENT '来源会话ID',
    source_round INT DEFAULT 0 COMMENT '来源轮次',
    source_episodic_id BIGINT DEFAULT NULL COMMENT '来源episodic记忆ID',
    is_user_edited TINYINT DEFAULT 0 COMMENT '用户是否手动编辑',
    version BIGINT NOT NULL DEFAULT 1 COMMENT '版本号',
    content_hash VARCHAR(64) NOT NULL DEFAULT '' COMMENT '内容哈希',
    deleted_at DATETIME DEFAULT NULL COMMENT '软删除时间',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_semantic_user (user_id, memory_type),
    INDEX idx_semantic_importance (importance_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='永久知识（Semantic 层，无TTL）';

-- 43. 记忆轮次追踪
CREATE TABLE IF NOT EXISTS memory_rounds (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    thread_id VARCHAR(128) NOT NULL COMMENT '会话ID',
    user_id BIGINT NOT NULL COMMENT '用户ID',
    round_count INT DEFAULT 0 COMMENT '当前轮次计数',
    last_message_hash VARCHAR(64) DEFAULT '' COMMENT '最后消息哈希（防重）',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_thread (thread_id),
    KEY idx_round_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='记忆轮次追踪表';

-- 44. 记忆整合日志
CREATE TABLE IF NOT EXISTS memory_consolidation_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL COMMENT '用户ID',
    source_ids TEXT NOT NULL COMMENT '源记忆ID列表（JSON）',
    target_id BIGINT NOT NULL COMMENT '目标记忆ID',
    similarity_score FLOAT NOT NULL COMMENT '相似度分数',
    consolidation_type VARCHAR(32) DEFAULT 'merge' COMMENT 'merge/dedup',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_consolidation_user (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='记忆整合日志表';

-- 45. 记忆评估集
CREATE TABLE IF NOT EXISTS memory_eval_sets (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(128) NOT NULL COMMENT '评估集名称',
    description TEXT COMMENT '描述',
    user_id BIGINT DEFAULT NULL COMMENT '创建者ID',
    is_active TINYINT DEFAULT 1 COMMENT '是否启用',
    item_count INT DEFAULT 0 COMMENT '评估项数量',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_eval_set_user (user_id),
    KEY idx_eval_set_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='记忆评估集表';

-- 46. 记忆评估项
CREATE TABLE IF NOT EXISTS memory_eval_items (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    eval_set_id BIGINT NOT NULL COMMENT '评估集ID',
    query TEXT NOT NULL COMMENT '查询/问题',
    expected_answer TEXT COMMENT '期望答案',
    expected_memory_ids TEXT COMMENT '期望关联的记忆ID（JSON数组）',
    tags VARCHAR(255) DEFAULT '' COMMENT '标签（逗号分隔）',
    difficulty VARCHAR(32) DEFAULT 'medium' COMMENT '难度：easy/medium/hard',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_eval_item_set (eval_set_id),
    FULLTEXT KEY ft_eval_query (query)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='记忆评估项表';

-- 47. 记忆评估运行
CREATE TABLE IF NOT EXISTS memory_eval_runs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    eval_set_id BIGINT NOT NULL COMMENT '评估集ID',
    user_id BIGINT NOT NULL COMMENT '执行用户ID',
    run_type VARCHAR(32) DEFAULT 'manual' COMMENT 'manual/scheduled',
    status VARCHAR(32) DEFAULT 'pending' COMMENT 'pending/running/completed/failed',
    total_items INT DEFAULT 0 COMMENT '总评估项数',
    passed_items INT DEFAULT 0 COMMENT '通过项数',
    precision_score FLOAT DEFAULT 0 COMMENT '精确率',
    recall_score FLOAT DEFAULT 0 COMMENT '召回率',
    f1_score FLOAT DEFAULT 0 COMMENT 'F1分数',
    latency_ms INT DEFAULT 0 COMMENT '平均延迟（毫秒）',
    error_message TEXT COMMENT '错误信息',
    config_json TEXT COMMENT '评估配置（JSON）',
    started_at DATETIME DEFAULT NULL COMMENT '开始时间',
    completed_at DATETIME DEFAULT NULL COMMENT '完成时间',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_eval_run_set (eval_set_id),
    KEY idx_eval_run_user (user_id),
    KEY idx_eval_run_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='记忆评估运行表';

-- 48. 记忆评估结果
CREATE TABLE IF NOT EXISTS memory_eval_results (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id BIGINT NOT NULL COMMENT '评估运行ID',
    item_id BIGINT NOT NULL COMMENT '评估项ID',
    retrieved_memory_ids TEXT COMMENT '检索到的记忆ID（JSON数组）',
    retrieved_contents TEXT COMMENT '检索到的内容（JSON数组）',
    llm_judgment TEXT COMMENT 'LLM判断结果（JSON）',
    is_correct TINYINT DEFAULT 0 COMMENT '是否正确',
    relevance_score FLOAT DEFAULT 0 COMMENT '相关性分数',
    latency_ms INT DEFAULT 0 COMMENT '延迟（毫秒）',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_eval_result_run (run_id),
    KEY idx_eval_result_item (item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='记忆评估结果表';

-- 49. 记忆 A/B 实验
CREATE TABLE IF NOT EXISTS memory_ab_experiments (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(128) NOT NULL COMMENT '实验名称',
    description TEXT COMMENT '实验描述',
    variant_a VARCHAR(64) NOT NULL COMMENT '变体A配置',
    variant_b VARCHAR(64) NOT NULL COMMENT '变体B配置',
    traffic_split FLOAT DEFAULT 0.5 COMMENT '流量分配（A的比例）',
    status VARCHAR(32) DEFAULT 'draft' COMMENT 'draft/running/paused/completed',
    metrics_json TEXT COMMENT '指标配置（JSON）',
    results_json TEXT COMMENT '实验结果（JSON）',
    started_at DATETIME DEFAULT NULL COMMENT '开始时间',
    ended_at DATETIME DEFAULT NULL COMMENT '结束时间',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_ab_exp_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='记忆 A/B 实验表';

-- 50. 记忆 A/B 实验事件
CREATE TABLE IF NOT EXISTS memory_ab_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    experiment_name VARCHAR(128) NOT NULL,
    variant_name VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    thread_id VARCHAR(64) DEFAULT '',
    event_type VARCHAR(32) NOT NULL,
    metrics_json TEXT,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_ab_event_exp (experiment_name),
    KEY idx_ab_event_variant (experiment_name, variant_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='记忆 A/B 实验事件表';

-- 51. 数据层级定义表
CREATE TABLE IF NOT EXISTS data_layers (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL UNIQUE COMMENT '层级名称',
    description VARCHAR(255) DEFAULT '' COMMENT '层级说明',
    sort_order INT DEFAULT 0 COMMENT '排序（前端展示顺序）',
    is_system TINYINT DEFAULT 0 COMMENT '1=系统内置（不可删除）',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_sort (sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据层级定义表';

-- 内置"全员"层级（NO_AUTO_VALUE_ON_ZERO 确保 id=0 不被 AUTO_INCREMENT 覆盖）
SET @old_sql_mode = @@sql_mode;
SET sql_mode = 'NO_AUTO_VALUE_ON_ZERO';
INSERT IGNORE INTO data_layers (id, name, description, sort_order, is_system)
VALUES (0, '全员', '所有用户可见（默认）', 0, 1);
SET sql_mode = @old_sql_mode;

-- 52. 用户-数据层级关联表（多对多）
CREATE TABLE IF NOT EXISTS user_data_layers (
    user_id BIGINT NOT NULL COMMENT '用户ID',
    layer_id BIGINT NOT NULL COMMENT '数据层级ID',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, layer_id),
    INDEX idx_layer (layer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户-数据层级关联表';

-- 53. 知识库-数据层级关联表（多对多）
CREATE TABLE IF NOT EXISTS kb_data_layers (
    kb_id BIGINT NOT NULL COMMENT '知识库ID',
    layer_id BIGINT NOT NULL COMMENT '数据层级ID',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (kb_id, layer_id),
    INDEX idx_layer (layer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识库-数据层级关联表';

-- ════════════════════════════════════════════════════════════
-- 九、多 Agent 委派
-- ════════════════════════════════════════════════════════════

-- 54. 多 Agent 委派留痕表（每个子 Agent 任务一行）
-- 写入点：① 子 Agent 生命周期事件（running/tool_count/completed）② 后台委派结果回流时按
-- Hermes 的 completion 事件做权威校准（delegation_id/summary/tokens/api_calls）。
-- 目的：委派不再"无声"——失败、丢失、重复、未回流都可在库里查到。
-- 读写入口：backend/service/delegation/store.py（fail-soft + DB 熔断，不阻塞 Agent 主循环）
CREATE TABLE IF NOT EXISTS delegation_tasks (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    delegation_id    VARCHAR(64) DEFAULT NULL COMMENT 'Hermes 批次ID（同一批 fan-out 共享，回流时回填）',
    subagent_id      VARCHAR(64) DEFAULT NULL COMMENT '子 Agent 唯一ID（Hermes 生成 sa-<idx>-<hex>）',
    task_index       INT DEFAULT NULL COMMENT '批内序号（从 subagent_id 解析）',
    child_session_id VARCHAR(64) DEFAULT NULL COMMENT '子 Agent 会话ID',
    parent_session_id VARCHAR(64) DEFAULT NULL COMMENT '父 Agent Hermes 会话ID（归属判定用）',
    thread_id        VARCHAR(64) DEFAULT NULL COMMENT 'AgentForge 会话（前端 chat_id）',
    user_id          BIGINT DEFAULT 0 COMMENT '发起委派的用户',
    goal             TEXT COMMENT '子任务目标',
    model            VARCHAR(128) DEFAULT NULL,
    depth            INT DEFAULT 0 COMMENT '委派深度（0=一级子 Agent）',
    status           VARCHAR(24) DEFAULT 'running' COMMENT 'running/completed/error/interrupted/runtime_lost/rejected_sync',
    tool_count       INT DEFAULT 0 COMMENT '子 Agent 工具调用次数',
    api_calls        INT DEFAULT 0 COMMENT '子 Agent LLM 调用次数',
    input_tokens     INT DEFAULT 0,
    output_tokens    INT DEFAULT 0,
    duration_seconds DECIMAL(10,2) DEFAULT 0,
    summary          LONGTEXT COMMENT '子 Agent 最终产出（回流通道的权威来源）',
    error_message    TEXT,
    live_transcript  VARCHAR(512) DEFAULT NULL COMMENT 'Hermes 实时转录日志路径',
    delivered        TINYINT DEFAULT 0 COMMENT '1=结果已回流进父对话',
    duplicate_hint   TINYINT DEFAULT 0 COMMENT '预留字段：同批任务语义疑似重叠标记（当前无代码写入，重叠检测仅告警）',
    started_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at     DATETIME DEFAULT NULL,
    UNIQUE KEY uk_subagent (subagent_id),
    INDEX idx_delegation (delegation_id),
    INDEX idx_parent_session (parent_session_id, started_at),
    INDEX idx_thread (thread_id, started_at),
    INDEX idx_user_time (user_id, started_at),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='多Agent委派留痕表';

