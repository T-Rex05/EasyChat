# 文件存储与账单账本：运维手册

> 适用版本：迁移 `0011_files`、`0012_ledger`、`0013_ledger_note`。本文只描述可验证行为；
> 未经真实微信账单/真实视觉服务联调的部分在文末“已知限制”中明确标注。

## 1. 数据布局

| 数据 | 位置 | 说明 |
| --- | --- | --- |
| 业务元数据 | `data/app.db`（SQLite） | `stored_files`、`upload_receipts`、`file_references`、`file_extractions`、`ledger_*` |
| 原始上传 | `data/uploads/<owner_id>/<前缀>/…` | 相对 `storage_key` 存库，不存绝对路径 |
| 派生内容 | `data/derived/…` | 7 天保留策略（`derived_7d`），仅无引用时清理 |
| 报告 | `data/reports/…` | 报告文件同时登记为 `stored_files` 并引用 `analysis` |
| 暂存 | `data/staging/…` | 上传中的 `.part`，不备份，重启由 `reconcile` 处理 |

数据库与文件系统没有共享事务：保存顺序是“收据 receiving → 写 `.part` + 计算 hash → fsync →
原子改名 → 短事务写 ready+收据+引用”。任何一步中断都只会留下可对账的中间态。

## 2. 状态与对账

- 只有 `status='ready'` 的文件可读；`receiving/deleted/failed` 一律 404/不可下载。
- 启动与定时调用 `FileService.reconcile()`：
  - 收据超时未完成 → 标记失败并清理 `.part`；
  - 数据库有 ready 但文件缺失 → 标记 `failed` 并记录 `error`（不会静默当作可读）；
  - 文件存在但无 ready 行 → 计入孤儿报告，人工确认后再删。
- 账本导入：`saved → parsing → validated → committed`，失败为 `failed`。
  `validated` 前不写交易；控制总额不一致时提交需要显式 `confirm_mismatch`。
- 解析任务走 `JobQueue`（kind `ledger.parse`），租约过期会重试；
  存储不可用属于可重试错误，任务回到 `retry_wait`，导入回到 `saved`，不会误标失败。

## 3. 留存、删除与容量

| 对象 | 策略 |
| --- | --- |
| 原始上传（图片/表格/文档） | `permanent`，默认长期保留，清理任务永不触碰 |
| 派生内容 | `derived_7d`；`FileLifecycle.sweep_derived()` 先标记 deleted 再删 blob |
| 报告 | 随分析保留；删除报告只是删文件引用，不重算账 |

删除范围（`FileService.request_delete`）：

1. `preview`：只返回引用计数与影响，不删；
2. `unlink`：仅解除指定 `(ref_kind, ref_id)` 引用；
3. `purge`：无任何引用时才删除记录与 blob；有引用直接拒绝，不级联删账。

容量：`FileLifecycle.assert_writable(owner_id, incoming)` 在配额或用磁盘水位不足时抛
`InvalidInputError`，**只拒绝新保存，不删除旧原件**。部署方需把该检查接到上传入口
（`FileService` 已支持 `min_free_bytes` 注入，配额可按用户扩展）。

## 4. 备份

备份必须同时覆盖 `app.db` 与受管文件；只拷 `app.db` 会得到“有记录无原件”的坏备份。

```powershell
# 默认输出到 data/backups/backup-<UTC 时间戳>
python scripts/files_ledger_backup.py backup

# 指定目录（目录必须不存在或为空）
python scripts/files_ledger_backup.py backup --dest D:\easy chat backups\2026-11-04

# 校验（数据库 integrity_check + 每个文件 sha256 + manifest 覆盖检查）
python scripts/files_ledger_backup.py verify --backup D:\easy chat backups\2026-11-04
```

备份过程：

1. SQLite 官方 backup API 生成一致性快照（不复制正在写入的库文件）；
2. 读取快照中 `status='ready'` 的 `storage_key`，逐份复制并比对 sha256；
3. 写 `manifest.json`（DB hash、文件列表、大小、创建时间）；
4. 先写 `<dest>.partial`，全部成功后才原子改名为最终目录；失败自动清理半成品。

校验失败会返回非零退出码并列出问题（缺失文件、hash 不一致、manifest 漏项、DB 损坏）。

## 5. 恢复

**恢复前停止服务**，确认没有上传/解析/投递任务在写库。

```powershell
# 默认 dry-run：只校验并打印将写入的位置
python scripts/files_ledger_backup.py restore --backup D:\backups\2026-11-04

# 真正恢复
python scripts/files_ledger_backup.py restore --backup D:\backups\2026-11-04 --apply
```

行为：

- 先 `verify_backup`，不通过直接拒绝；
- 现有 `app.db` 改名为 `app.db.pre-restore-<时间戳>` 保留，不覆盖；
- 清掉 `-wal/-shm` 旁文件，写入快照并复制文件；
- 恢复后删除规则继续有效（引用/留存策略都在快照里）；
- 未完成的 job 会随库恢复为待处理状态，需确认不会自动外发（投递表状态决定，worker 启动后再消费）。

## 6. 已知限制与验收缺口

- 真实微信账单导出文件（不同版本列名/合并单元格）未纳入自动化测试；解析器测试使用合成账单。
- 图片识别依赖部署方注入的视觉服务；未配置时接口返回 422 并明确提示，不会造假数据。
- PDF 导出复用现有 `PdfRenderer`；未安装 `weasyprint` 或关闭 `pdf_enabled` 时明确报错。
- 备份不含 `staging/` 与 `artifacts/` 下的历史报告产物；报告在 files 中另有登记。
- 前端账单页覆盖上传/核验/统计/修正/退款确认/截图候选，但未做移动端专项验收与真实微信端到端联调。
- 单机 SQLite 部署假设；多实例共享同一目录不在本期支持范围。
