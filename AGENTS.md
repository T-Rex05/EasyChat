# AGENTS.md — 编码代理仓库须知

本文件是给所有编码代理(super agent worker、poteto-mode 会话、任何 AI 协作者)的仓库级说明。人类开发者同样适用。以磁盘代码与 `CLAUDE.md` 为准;两者冲突时先停下来问人。

## 仓库速览

- 后端:`python main.py`(uvicorn,8001)→ `backend/server.py` → `backend/app.py` → `backend/bootstrap.py`
- 前端:`agent_frontend/`(Vite,3000,`/api` 代理 8001)
- 模块:`backend/modules/<domain>/` 四件套 contracts/api/repository/routes;路由注册在 `app.py::_register_explicit_routers`,装配在 `bootstrap.py::run_startup`
- 存储 SQLite + 追加式迁移 `backend/platform/migrations/NNNN_*.sql`
- 执行引擎唯一 Seam:`backend/runtime/contracts.py`;业务层禁止 import `backend/hermes` 内部
- 工具身份唯一来源:`backend/shared/tool_context.py`(ContextVar);工具绝不接受模型传入的 user_id

## 硬约束(违反即事故,没有例外)

1. **SQLite WAL 守卫**:3.45.0–3.51.2 是损坏区间,守卫逻辑回退 DELETE journal;不要无条件启用 WAL。
2. **迁移只追加**:已发布迁移不可修改;迁移 SQL 禁 `executescript`;时间文本统一 UTC ISO-8601。
3. **事务体内禁外呼**:`db.transaction()` 体内禁止网络/LLM/SMTP 等外部调用。
4. **能力开关默认关闭**:渠道凭证/模型密钥 AES-GCM 加密,密钥来自 `EASYCHAT_ENCRYPTION_SECRET`。
5. **无人值守 fail-closed**:审批不过就是不过;不要为"让流程走通"放宽守卫。

## 风险清单(protected paths)

触碰以下区域的工作是高风险,自主会话必须停在草稿 + 升级简报,不要自行推到底:

| 区域 | 路径 | 原因 |
| --- | --- | --- |
| 认证与权限 | `backend/modules/access/**` | owner 边界与 capabilities,回归即数据越权 |
| 存储与迁移 | `backend/platform/**` | 迁移 checksum 锁定;WAL 守卫区间 |
| 外发通道 | `backend/modules/delivery/**` | 真实发邮件/微信给人,收件人验证 fail-closed |
| 调度 | `backend/modules/scheduling/**` | 无人值守自动化,错即静默触发 |
| 代理运行时 | `backend/runtime/**`、`backend/modules/superagent/**` | 执行引擎 Seam 与无人值守编码链路 |
| 部署与供应链 | `docker/**`、`requirements*.txt`、`pyproject.toml` 依赖 | 能力默认关闭;新依赖即供应链变更 |
| 公共契约 | 任何模块的 `contracts.py` | 跨模块依赖签名,变更=协同重设计 |

## 例行安全区(可自动做到 ready-for-review)

文档/注释/日志文案;针对已定义行为的测试补齐;由类型检查器/linter/测试断言客观定义正确态的修复;`backend/modules/ledger/parsers/**` 的确定性改动;`agent_frontend` 有既定目标并带 Before/After 证据的局部打磨。

## 工作纪律(源自 pstack 原则,按 EasyChat 落地)

- **prove-it-works**:验证真实产物——跑真实的 pytest 子集、真实的构建;"能编译"不是证据。
- **test-behavior-not-implementation**:测行为与契约,不测内部实现细节。
- **fix-root-causes**:修因不修标;守卫只有在状态本身合法时才算修复。
- **laziness-protocol**:最小改动,优先删除;不引入"过渡兼容态"。
- **sequence-verifiable-units**:小步提交,每步以一项检查收尾,让评审者可以逐段验证。
- **encode-lessons-in-structure**:教训固化到 lint/迁移校验/运行时检查,不是写更多散文。
- **每句话带证据**:回复中每个论断同一句内给出证据或标注(实测/推断/猜测)。

## 验证命令

```bash
python -m pytest tests -q -m "not integration and not resources"
python -m pytest tests/superagent tests/contracts -q
cd agent_frontend && npm run type-check && npm run build
```

## 提交与 PR 约范

- 中文 commit message,conventional 风格(如 `feat(wechat): …`、`fix(access): …`);小步提交。
- PR 标题与描述用中文;代码标识符、命令、路径保持英文。
- UI 改动必须附 Before/After 同场景对比;只有 After 视为不完整交付。
- 无人值守会话遇高风险/设计决策:停不完整草稿 PR + 按 `escalation-brief` 结构写清停因/证据/剩余/续作,报告 blocked,等人在工单线程答复;自动 CI/bot 反馈不能解除人工暂停。
- 禁止 force-push 共享分支;禁止代评审人 approve/merge。

## 本地深度接管

人工接管优先级:面板回答 > Executor 会话直接对话 > 本地 poteto-mode 会话(配合 pstack 的 session-pickup 玩法,在同一工单分支/工作树上继续)。
