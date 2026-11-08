# Files & Ledger 增量执行日志（F0–F11）

工作目录：`E:\PythonCode\EasyChat`。原项目 `E:\PythonCode\AgentForge` 未修改、未读取其真实数据。
本日志只记录增量功能（files/ledger），旧主体 Task 0–16 的证据仍在 `easychat-execution-log.md`，本文件不覆盖它。

约定：只记录**实际运行过**的命令与结果；未联调项单独列出，不把替身测试写成真实外联成功。

---

## F0 — 当前接口、迁移与合成基线

### 0.1 起始状态核对（2026-11-04）

- `git status --short`：`.planning/*`、`EASYCHAT_HANDOFF.md`、架构 spec 有修改，`2026-11-04-files-ledger-*` 为未跟踪新增；没有其他模型已完成的 files/ledger 代码（`backend/modules/files|ledger` 不存在，`tests/files|ledger` 不存在）。
- HEAD：`6886531 docs: mark Task 0-16 complete with final verification and unverified external items`。
- 结论：增量功能从 F0 开始，未重做旧 Task 0–16。

### 0.2 桥接点实测（读源码，非按旧讨论稿推断）

| 接入点 | 实际实现 | 增量用法 |
|---|---|---|
| `modules/assistant/api.py:register_attachment` | 写 `attachments`（file_name/file_path/file_size/mime/sha256/session_id），返回 `att_…` | 追加 `stored_file_id` 列并保持旧 ID 可用 |
| `modules/assistant/contracts.py:RunCommand.attachment_ids` | tuple[str,...] 写入 `runs.attachment_ids` JSON | 继续只传引用；files/ledger 按 ID 取内容 |
| `modules/channels/wechat/media.py:MediaFetcher.fetch` | 下载/解密到 `media_dir/<event_id>/`，返回 FetchedMedia | 保留协议/SSRF/解密；最终持久保存委托 files |
| `modules/channels/api.py:_ingest_media` | fetch → `assistant.register_attachment` | 改为 fetch 暂存 → `files.save_stream` → 登记 attachment 引用 |
| `modules/delivery/repository.py:create_artifact/get_artifact` | `artifacts(id, owner_id, run_id, kind, file_path, sha256, file_size, mime, …)` | 追加 `stored_file_id`；旧 artifact_id 仍可发送 |
| `modules/delivery/reports.py` | 渲染后 `create_artifact`，邮件只重试同一 artifact | 报告产物同时登记 files 引用 |
| `platform/jobs.py` | `enqueue/claim (lease)/complete/fail/recover_expired_leases`，`dedup_key` 全局唯一 | ledger 解析/提取/提交/分析复用，不新建队列 |
| `platform/sqlite.py` | 逐语句迁移 + checksum；`executescript` 禁用 | 新增迁移只追加，不改已提交文件 |
| 备份/清理 | 当前没有统一备份注册；`purge_old_events` 只清渠道事件 | F11 新增 `files.reconcile`/lifecycle 与运维文档 |

### 0.3 迁移编号

`backend/platform/migrations/` 实测最新为 `0010_delivery_email.sql`。本次追加：

- `0011_files.sql`（F1）
- `0012_ledger.sql`（F4）

已提交的 0001–0010 checksum 未修改。

### 0.4 依赖核查（实测已安装版本）

| 能力 | 选用 | 版本/结论 |
|---|---|---|
| XLSX 读取 | `openpyxl`（只读、`data_only=True`、不加载 VBA、不计算公式） | 3.1.5 已安装 |
| CSV 读取 | 标准库 `csv` + 自实现编码探测（utf-8-sig/utf-8/gb18030） | 标准库 |
| 图片解码/像素限制 | `Pillow`（仅图像提取用；缺失时明确 capability_unavailable） | 12.3.0 已安装，仍保持可选导入 |
| PNG 夹具 | 标准库 zlib/struct | 不依赖 Pillow |
| PDF | 复用 `integrations/pdf.py`（现有可选渲染器） | 不新增依赖 |
| 测试 | pytest 9.1.1（`asyncio_mode=auto`）、ruff 0.15.12 | — |

### 0.5 测试目录映射

增量测试落在 `tests/files/`、`tests/ledger/`、`tests/contracts/test_file_upload.py`、`tests/contracts/test_ledger_api.py`；
`tests/files|ledger` 当前不存在，`tests/storage`、`tests/contracts`、`tests/delivery`、`tests/access` 为既有目录，命令按实际名称执行。

### 0.6 基线（本轮实际运行）

```powershell
python -m pytest tests/architecture tests/contracts tests/access tests/assistant tests/models tests/storage tests/usage tests/delivery tests/memory tests/skills tests/evolution -q
```

结果：`303 passed in 105.83s`（与进度文档一致；本轮为实际重跑证据）。

### 0.7 新增产物

- `tests/fixtures/ledger/README.md`：合成夹具说明与禁止事项。
- `tests/support/ledger_fixtures.py`：合成微信 XLSX/CSV、通用 CSV、多行引号 CSV、PNG、假视觉结果、对账场景。
- 本文件。

### 0.8 未验证项（F0 时点）

- 真实微信支付导出的 XLSX 列名/说明行变体未用真实账单验证（只按公开格式与合成样本设计，解析器对未知列明确失败/待审）。
- 真实 OCR/视觉服务未联调（F6 用 FakeVision）。

下一步：F1 统一文件模型与 `0011_files.sql`。

---

## F1 — 统一文件模型与 0011 迁移

- 迁移：`0011_files.sql`（新增 `stored_files`、`upload_receipts`、`file_references`、`file_extractions`；旧 `attachments`/`artifacts` 追加 `stored_file_id`）。已提交的 0001–0010 checksum 未改。
- 代码：`backend/modules/files/{contracts,repository,local_store,api}.py`；权限新增 `file.upload/read/delete`（admin+user 默认授予，跨 owner 仍需 `system.manage`）。
- 关键规则：owner 由 Principal 决定；外部 metadata 不能指定 owner/storage_key；同 owner 同 sha256 复用文件但每次上传独立收据；跨 owner 不去重；删除一条引用不删共享原件；FileRecord 不含绝对路径。
- 测试命令与结果：

```powershell
python -m pytest tests/files -q        # F1+F2 合并后 30 passed
python -m pytest tests/storage tests/architecture tests/access -q   # 61 passed
```

## F2 — 流式保存、崩溃恢复与受限读取

- `save_stream`/`ingest_local_path`/`save_bytes`/`save_derived`/`save_report` 分块写 `.part` + sha256，flush/fsync 后同文件系统原子 rename，再短事务提交 ready+收据+引用；移动后复核 hash。
原件本地长期保存，SQLite记录元数据和账目；所有分析可追溯来源、幂等且授权。
模型只识别意图/分类/解释，金额和退款统计由受控程序执行。
用合成账单和假视觉做默认测试，不把桌面真实账单、秘密和运行数据加入Git。
每任务记录真实测试证据与本地提交，不自动推送；真实外发另按用户授权执行。
```

## 微信 A+C 增量交接（2026-11-05 第四轮 care 收尾）

范围：微信「事务外脑 + 人格情绪层」A+C，含 A5 账单对话、`/账单确认`、weekly 周报、微信聊天窗口文件上传。

状态：代码已落地，第四轮 care 并发收尾完成。P1-1～P1-5 保持闭合：care 只在 delivery 实际 `sent` 回调后写 `last_care_at`/`mood_care_log`，入队和 failed 复用不标记，重复回调幂等。第三轮修复两个 P2 边界：

- 周报“下周”不再只按 `next_run_at` 过滤：`SchedulingService.upcoming(start=...)` 会把 once/interval/daily/weekly 重复计划纯投影到明天 00:00 后的下一次 occurrence，不修改数据库；50 条上限在展开排序后截断。真实 SQLite 集成测试覆盖每日、每周、一次性、briefing 自身、边界、interval 和截断。
- 删除/关闭情绪会取消尚未发送的 `source=care` delivery（`cancelled`）和 pending/retry `mood.care` job；`delete_mood` 同时清空 `last_care_at`、关闭 opt-in。第四轮新增 `0017_care_epoch`：`care_epoch_at` 只在删除/关闭/降低主动性时推进；`mark_care_sent` 在同一个 `BEGIN IMMEDIATE` 事务内校验 opt-in/代际后写入，回调与删除不再有“检查后插入”的 TOCTOU；`proactivity=low` 也会取消 pending care。`sending` 已开始外部调用的窗口不可撤回；目标解绑后旧 target 的 pending delivery 仍可能发出，见设计 §14.4/§23.5。

仍未达到生产可交付：真实 iLink 推送、真实语音格式/STT、真实微信上传、真实模型效果、部署长稳未验证；`memory_correct`、每日 10,000 tokens 预算、failed care 当天补偿重试、`on_sent` 写库异常补偿仍不在范围。不能把 required 套件全绿当成这些外部项的验收通过。

容器冒烟（2026-11-05）：本机临时用可达 PyPI 镜像构建单容器（默认 PyPI 直连遇到 wheel hash mismatch），启动后 `/healthz`、`/readyz`、SPA、注册/登录、profile 读写、情绪删除、multipart 上传均 200；迁移到 `0017`，`care_epoch_at` 存在，重启后卷数据仍可登录。首次启动暴露 `python-multipart` 缺失，已加入 `docker/requirements-core.txt`。默认 Dockerfile 的完整直连构建仍需在可靠网络/镜像源下复跑；真实 iLink/STT/模型/部署长稳仍未验证。

- 设计：[2026-11-04-wechat-a-c-design.md](docs/superpowers/specs/2026-11-04-wechat-a-c-design.md)（§14.4/§14.5 删除与在途 care、§23.5 第三/四轮收尾、0014+0015+0016+0017）
- 验收报告与修复提示词：[2026-11-04-wechat-a-c-acceptance.md](docs/superpowers/plans/2026-11-04-wechat-a-c-acceptance.md)（§7.5、§7.6 验收）

接手模型不要重做已完成的 A+C 实现；后续优先是真实外联验证与产品确认“模型不可用时显式记住是否回退正则”“failed care 是否当天重试”“on_sent 写库异常是否补偿”，不要在未确认时改语义。真实外联没有凭证时单列为未验证，不伪造结果。变更后更新设计 §23 与验收 §7，并按报告中的 required 命令复跑。

## 超级代理增量交接（2026-11-08 feature/superagent 分支）

范围：参考 deepseek-ai/dsh-superagent-prototype 的领域模型（Source → Ticket → Executor → PR → Reply），在 EasyChat 上落地「微信收需求 → 后台编码代理 → 自动提 PR → 微信回信」。

- 模块：`backend/modules/superagent/`（contracts/repository/api/routes/worker/github），路由 `/api/superagent/*`，迁移 `0019_superagent.sql`（settings 单行 + tasks 队列 + events 时间线）。
- 任务表自身即队列（queued→running→终态），不走共享 jobs 表：编码任务执行可达数十分钟，超过 JobQueue lease 语义；启动恢复沿用 assistant 语义（遗留 running 标 failed，可手动重试）。
- 执行链：`SuperagentWorker.tick()` 认领 → git 工作区（`data/artifacts/superagent/<owner>__<repo>`，token 只出现在一次性 fetch/push URL，不落 .git/config）→ 复用 Hermes 运行时（独立 session_id，新接缝 `HermesRuntimeAdapter.prepare_session_workspace/release_session_workspace` 按 session 注入 CWD 覆盖）→ terminal/file/web 工具集 → git commit/push → GitHub/Gitee REST 创建 PR → delivery 队列回信微信（无绑定时仅面板可见）。
- 入口：微信对话经 `superagent_submit_task` 工具（`backend/tools/business/superagent_tools.py`，`__always_available__`，身份来自 ToolContext）；Web 面板 `SuperagentView.vue`（配置仓库/token + 建任务 + 轨迹时间线，轮询 5s）。
- 权限：`superagent.view/create/manage` 三键；admin 默认全量、user 默认 view+create；token 经既有 AES-GCM（EASYCHAT_ENCRYPTION_SECRET）加密存储，面板只出掩码。
- 测试：`python -m pytest tests/superagent tests/contracts/test_superagent_api.py tests/storage tests/architecture -q`（69 passed）；git/PR/运行时全部可注入假件，离线可重复。
- 已知边界：真实 GitHub push/PR、真实模型长任务、并发 >1 的终端容器共享语义未实测；服务端审批回调沿用 fail-closed（tirith 标记的命令拒绝执行）。

## 超级代理可靠化交接（2026-11-09 feature/superagent-reliability 分支，T0–T8）

依据 `docs/superpowers/plans/2026-11-09-project-review-and-wechat-superagent.md` 完成 T0–T8。基线 3b3d6c5 + 工作区微信 A+C 增量，提交链 c72eb4f → ad01bce（7 个提交）。

- **T1–T4 可靠化**（f8a37ff）：0020 迁移（任务快照/attempts/inputs/reports/version）；CAS 状态机（迟到 attempt 拒绝写终态）；严格 HTTPS parser + 无凭证 remote + credential helper（token 只进 git 子进程环境，不进 URL/config/argv，错误统一脱敏）；host/repo_hash/task_id 独立工作区；git/agent/验证分别限时 + 进程树回收；CodingRunner 窄接缝；cancel 改 await 协作取消；completed 门禁 + base...HEAD 双比较（覆盖代理自行 commit）；验证门禁（verify_profile JSON + allow_unverified_draft 策略）；checkpoint 推进；PR 先查后建（Draft 复用）；终态+报告+回执同事务，dedup 按 attempt/report/target；取消/发布竞态记 cancelled_after_publication；capabilities 端点。
- **T5 持久 inbox**（fc6c89d）：0021 迁移；入站 envelope 先落库（全文/媒体/来源），内部失败 failed+退避本地重放（不再 delete_event），毒消息 dead；/开发 /任务 /补充 /取消 /重试 命令族（短号解析限定本人，幂等键=平台事件 ID）；ToolContext 增加 source_ref/source_chat_id（dispatcher 晚绑定 source_for_session 服务端查询）；工具服务端操作键幂等。
- **T6 前端工作台**（4edbd48）：capabilities 驱动受理入口（修复失败也 ready 的缺陷）、新状态徽标+phase、游标分页、增量事件（after_id）、防竞态（单在途/切详情弃旧响应）、补充输入表单。
- **T7 webhook**（a496db9）：0022 迁移；HMAC 验签（缺配置 403）、delivery_id 去重、allowlist、持久 job；PR closed（merged/closed_unmerged 回流 outcome）、评审/评论转任务输入（waiting/blocked/failed 自动回队）、CI 失败报告；Bot 跳过、旧 head 不触发。配置 EASYCHAT_GITHUB_WEBHOOK_SECRET。
- **T8**（ad01bce）：auth 受保护解析 + chatUserId 去 '1' 兜底 + ready 状态；运维指标 GET /api/superagent/ops/metrics + 面板；bundle 记录（入口 JS 1,020 kB / gzip 332 kB，Element Plus 全量引入为主因，按需引入列为预算评审项）。

状态机：queued/running/succeeded/failed/cancelled + waiting_input/blocked/awaiting_review/interrupted/cancel_requested；phase 单独（preparing/coding/verifying/publishing）；PR 状态单独（draft/open/merged/closed）+ outcome（merged/closed_unmerged）。

默认决策（用户未逐条确认，复核点）：①第一版仅 GitHub HTTPS（Gitee/SSH 拒绝并提示）；②缺验证命令默认允许发 Draft PR（PR 记录缺失证据），开关可强制门禁；③webhook 自动修复规则暂缓；④真实并发固定 1（max_concurrent 仅历史语义）；⑤旧任务无快照禁止重试（提示重新提交）；⑥start-local.bat 不入库（含密钥）。

测试：`python -m pytest tests -q -m "not integration and not resources"`（全量）；定向 `python -m pytest tests/superagent tests/channels tests/tools tests/contracts/test_superagent_api.py tests/contracts/test_wechat.py tests/architecture tests/storage -q`。迁移测试硬编码版本列表（test_migration_0014.py），新增迁移需同步。真实 GitHub push/PR、真实微信、webhook 真实投递未联调（需凭证/测试仓库）。
