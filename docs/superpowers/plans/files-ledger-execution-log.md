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
- 失败路径：超限、上游流中断、写盘 ENOSPC、移动失败、hash 不一致、提交事务失败都标 `failed` 且不留半成品，不返回“已保存”。
- `reconcile`：按收据预期 key/hash 补提交或标 failed；`finalizing` 文件 hash 一致补 ready；ready 但物理缺失标 `missing`；孤立文件只报告不删除。
- 校验：路径穿越/绝对路径/符号链接逃逸拒绝；类型伪装按内容签名判定；XLSX/ZIP 条目数与展开总量上限、越界条目拒绝；图片像素上限。
- 说明：`store.finalize` 在 Windows 跳过父目录 fsync（`_fsync_dir` 仅 POSIX），已在此记录，运维文档 F11 复述。

```powershell
python -m pytest tests/files/test_metadata.py tests/files/test_persistence.py -q
# 30 passed
```

提交：`feat(files): unify file model with streaming save and crash recovery (F1/F2)`
（F1 与 F2 共用同一条保存代码路径，合并为一次提交；两套测试分别覆盖元数据与持久化/恢复边界。）

下一步：F3 旧附件/报告桥接与微信/Web 接入。

---

## F3 — 旧附件/报告桥接、微信与 Web 接入

- 旧 `attachments`/`artifacts` 追加 `stored_file_id`；`AssistantService.register_attachment` 增加可选 `stored_file_id`，旧调用（只传 file_path）行为不变；新增 `get_attachment`（按 owner）。
- 微信媒体：`ChannelService._ingest_media` 下载/解密（保留原 SSRF 白名单与 AES 解密）后委托 `FileService.ingest_local_path`，再登记 attachment 并 `files.link(attachment)`；幂等作用域用**平台事件 ID + 媒体序号**（不是内部事件行 ID，事件行被清理后仍可幂等）。未装配 files 时保留旧路径。
- Web：`backend/modules/files/routes.py` 显式路由 `POST/GET /api/files`、`GET /api/files/{id}`、`GET /api/files/{id}/content`、`DELETE /api/files/{id}?scope=`；下载鉴权 + RFC 5987 文件名 + `nosniff`/`no-store`，不暴露 storage_key。
- `bootstrap` 构造 `FileService`（`settings.files_root = app.db 所在目录`）并注入 ChannelService；`app.py` 注册 files 路由。
- 报告：本轮只保证 `artifact.stored_file_id` 可写、旧 `artifact_id` 发送路径不变；报告产物真正改由 files 保存放在 F10（此处明确未完成）。

```powershell
python -m pytest tests/files tests/contracts/test_wechat.py -q          # 63 passed
python -m pytest tests/contracts/test_file_upload.py -q                  # 8 passed
python -m pytest tests/contracts tests/delivery tests/assistant tests/architecture -q  # 158 passed
```

下一步：F4 账本 schema 与纯解析器。



---

## F4 — 账本 schema、纯解析器与账本服务骨架

- 迁移 `0012_ledger.sql`（新增 10 表：`ledger_accounts`/`ledger_imports`/`ledger_source_rows`/`ledger_categories`/`ledger_transactions`/`ledger_transaction_sources`/`ledger_refund_links`/`ledger_category_rules`/`ledger_changes`/`ledger_analyses`；0011 之前 checksum 未改）。
- 纯解析器 `backend/modules/ledger/parsers/`：表头按内容识别（说明行数量可变）、UTF-8/GB18030/TSV/引号内换行、控制总额与起止时间提取、坏行保留 `errors` 不丢弃、`max_rows` 截断、微信与通用 CSV 分流（通用必须显式列映射，不猜列）。
- 归一化：金额整数分（`1,234.5`/`¥12.34`/负数）、时间（含 Excel 序列号）、状态 key、事件角色（**只看类型/商品/方向，不看状态文本**，避免“已全额退款”把原支付翻成退款导致身份漂移）、长单号按字符串保留并标记可靠性。
- 身份：`external_id:<acct>|<role>|<id>`（含事件角色，同一单号的原单与退款不互相覆盖），无可靠单号时退化指纹；控制总额闸门（不一致必须显式 `confirm_mismatch`）。
- 服务骨架 `LedgerService`：导入状态机（saved→parsing→validated/needs_review→committed/failed）、JobQueue `ledger.parse` + 单 worker、提交（事务内去重/状态更新/来源关联/退款匹配）、三口径 SQL 编译（`QueryPlan` 白名单校验 + 全参数化，不接受模型 SQL）、图片候选（FakeVision 接口）。

```powershell
python -m pytest tests/ledger -q     # 138 passed（identity 35 / query 40 / extraction 23 / parsers 21 / import_flow 19）
python -m ruff check backend/modules/ledger tests/ledger   # All checks passed
python .tmp_check_ledger_migration.py                       # 12 个迁移全部应用；fk: []；10 张 ledger 表
python -m pytest tests/ledger tests/files tests/contracts tests/architecture -q   # 285 passed
```

- 迁移验证脚本是一次性临时文件，运行后已删除；正式断言在 `tests/ledger/test_import_flow.py::test_migration_0012_creates_ledger_tables`。

## F5 — 导入提交、去重、状态更新与退款匹配（端到端）

- 同一 `(owner, file, parser, version)` 复用同一批次；重复登记已提交批次不会重解析。
- 提交在单事务内完成：`find → insert/merge → link_source`（`LedgerRepository._tx` 可复用调用方连接，避免自锁），`request_id` 幂等返回 `duplicate=True`。
- 重叠导出只新增未见过的交易；后一份导出把同一交易状态改为退款时只更新状态不产生重复行。
- 退款匹配：同单号/备注引用 → `confirmed` 建 `ledger_refund_links`；容量校验按原支付金额（已确认合计不得超出）。
- 三口径已用真实 SQLite 验证：`statement_flow`（退款不冲减支出）/`consumption_net`（扣本期关联退款）/`period_cash_outflow`（跨期退款抵本期流出），并用“9 月消费、10 月退款”用例证明三者数值确实不同。
- 删除批次：未提交可删（同时解除 import 引用、保留原件），已提交拒绝并提示逐笔删除。

下一步：F6 图片识别候选与人工校对的 HTTP 层、F7 指标/分类、F8 分析接口、F9 意图路由。

---

## F6–F8 — HTTP 层、分类规则、分析查询与后台 worker（2026-11-04）

- 路由 `backend/modules/ledger/routes.py`（`/api/ledger/*`）：导入登记/解析/预览/提交/删除、来源行分页、交易列表/详情/修正/删除、分类与规则 CRUD、退款候选/关联/确认/解除、`/analyze`、`/reports`、`/analyses`、`/images/{file_id}/candidates`、`/candidates/{id}/confirm`。路由只做参数与权限转发，无业务 SQL。
- 服务层：`LedgerService` 补齐 `import_summary`、`list_source_rows`、分类/规则、交易修正（写 `ledger_changes` 审计、`revision` 递增）、`suggest_refunds`、`save_image_candidate`/`confirm_image_candidate`（低置信字段必须显式纠正；未配置视觉服务返回 422 而非伪造结果）。
- 提交路径保持单事务：`find_transaction/insert_transaction/update_transaction/link_source` 均可复用外层连接；重叠导出先查身份键再决定 insert/merge，避免唯一约束冲突。
- worker：`ledger.parse` 任务成功/失败/重试语义；存储不可用（`StorageUnavailableError`/`OSError`）回到 `saved` 并 `retry_wait`，确定性的格式错误才标 `failed`，防止把临时 IO 故障当坏文件。
- 迁移修正：`0012` 发布后发现 `note` 字段遗漏，**未改已发布迁移**，追加 `0013_ledger_note.sql`（`ALTER TABLE ledger_transactions ADD COLUMN note ...`）；`test_migration_0013_upgrades_existing_0012_database` 真实模拟“已应用 0012 的旧库 → 删除 0013 记录 → 再迁移”，同时证明 0001–0012 checksum 未被改写。

```powershell
python -m pytest tests/ledger -q                                   # 168 passed
python -m pytest tests/contracts/test_ledger_api.py -q             # 12 passed
python -m pytest tests/ledger tests/contracts -q                   # 265 passed
python -m ruff check backend/modules/ledger tests/ledger           # All checks passed
```

## F9 — 意图路由与工具面

- `backend/modules/ledger/intent.py`：规则分类（导入/查询/修正/报告/退款核对/未知）＋确定性时间解析（本月/上月/今年/去年/最近 N 天/`YYYY年M月`），查询默认口径 `consumption_net`，提到“流水/现金”切换口径。
- 模型端口 `PlannerPort` 只允许返回 QueryPlan；模型返回未知字段（如 `sql`）时由 `analyze` 的白名单校验拒绝，**不执行任何模型生成的 SQL**。
- `backend/modules/ledger/tools.py`：5 个受控工具（导入预览/统计/修正/报告/退款候选），参数 schema 无 SQL/code 字段；**提交账单不暴露为工具**，必须人工确认。`handle_message` 把“用户原话 + 文件/交易上下文”落到服务调用。
- 金额、去重、退款净额全部由服务端受控代码计算；工具只转发。

```powershell
python -m pytest tests/ledger/test_intent.py -q     # 11 passed
python -m ruff check backend/modules/ledger tests/ledger   # All checks passed
```

## F10 — 报告、导出与前端账单页

- `backend/modules/ledger/reports.py`：Markdown/CSV 排版 + PDF 用 HTML；数字全部来自 `AnalysisResult`，报告文件经 `FileService.save_report` 落库并 `link(analysis)`，`ledger_analyses.report_file_id` 留痕。
- PDF 复用 `PdfRenderer`（未启用/未安装渲染依赖时明确报 `InvalidInputError`，不返回空文件）。
- 前端：`agent_frontend/src/views/LedgerView.vue` + `src/api/ledger.ts` + 路由 `/ledger`（权限 `ledger.view`）；覆盖上传→核验（控制总额/新增/更新/未变）→提交→按口径统计→报告下载→交易分类修正→退款候选确认→截图候选人工确认。

```powershell
python -m pytest tests/ledger/test_reports.py -q    # 5 passed
cd agent_frontend; npm run type-check               # 通过（无输出）
cd agent_frontend; npm run build                    # ✓ built in 12.71s（LedgerView 13.63 kB）
```

## F11 — 留存清理、容量水位、备份恢复与运维文档

- `backend/modules/files/lifecycle.py`：`derived_7d` 到期且**无引用**才清理（先标记 deleted 再删 blob）；原件 `permanent` 永不清理；配额或用磁盘水位不足时拒绝新保存，不删旧原件。
- `backend/platform/backup.py` + `scripts/files_ledger_backup.py`：SQLite backup API 一致性快照 + ready 文件逐一 sha256 校验 + manifest；先写 `.partial` 再原子改名；`verify` 检查 DB integrity、文件 hash、manifest 覆盖；`restore` 默认 dry-run，`--apply` 前把现有库改名保留。
- `docs/architecture/files-ledger-operations.md`：数据布局、状态机/对账、留存与删除范围、配额、备份/恢复命令与已知限制。

```powershell
python -m pytest tests/files/test_lifecycle.py -q   # 5 passed
python -m pytest tests/storage/test_backup.py -q    # 6 passed
python -m pytest tests/ledger tests/files tests/storage tests/contracts -q   # 360 passed
python -m ruff check backend/modules/ledger backend/modules/files tests/ledger tests/files/test_lifecycle.py tests/storage/test_backup.py   # All checks passed
```

下一步：全量回归（`python -m pytest -q`）与最终验收报告；前端移动端与真实微信/视觉服务联调仍未做。

## 最终回归（2026-11-04）

```powershell
python -m pytest tests/access tests/architecture tests/assistant tests/contracts tests/delivery tests/evolution tests/files tests/fixtures tests/ledger tests/memory tests/models tests/resources tests/skills tests/storage tests/usage -q
# 543 passed in 217.73s（追加迁移升级测试后重跑：544 passed in 168.09s）
python -m ruff check backend/modules/ledger backend/modules/files backend/platform/backup.py backend/bootstrap.py tests/ledger tests/files/test_lifecycle.py tests/storage/test_backup.py tests/contracts/test_ledger_api.py scripts/files_ledger_backup.py
# All checks passed!
cd agent_frontend; npm run type-check   # 通过
cd agent_frontend; npm run build        # ✓ built in 12.71s
```

- 直接运行 `python -m pytest -q` 会在 `tests/test_*.py` 的 17 个历史文件上收集失败
  （`ModuleNotFoundError: backend.service` 等，Task 15 删除旧模块后遗留），属**既有**问题，
  本次改动未触碰；模块化测试目录全绿。
- 未做：真实微信账单导出文件解析、真实视觉服务、真实 SMTP/微信投递、移动端专项验收、多实例部署。
