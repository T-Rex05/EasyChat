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
