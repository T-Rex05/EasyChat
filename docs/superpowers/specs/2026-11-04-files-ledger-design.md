# EasyChat 文件存储与微信账单分析增量设计

日期：2026-11-04。供执行模型实施。范围：微信/Web上传XLSX、CSV和图片的持久保存、账单解析、意图路由、确定性统计与报告。本轮只编写方案，用户真实账单不复制到源码、fixture或Git。

## 1. 与现有项目的关系

这是已完成主体改造后的增量功能。先核对`EASYCHAT_PROGRESS.md`和当前源码；不要重做旧Task 0–16，不恢复已删除的controller/service/db/RAG模块。主体交接记录中的测试与资源数值是执行模型记录，本方案未重跑验证。

本轮静态核对的接入位置：

| 当前实现 | 已有Interface | 增量用途 |
|---|---|---|
| `modules/assistant/api.py` | `register_attachment(principal, file_name, file_path, mime, file_size, sha256, session_id)` | 保持attachment_id兼容，新增stored_file_id关联 |
| `modules/assistant/contracts.py` | `RunCommand.attachment_ids` | 工具和路由按引用取文件，不传整块base64 |
| `modules/channels/wechat/media.py` | `MediaFetcher.fetch(ref, dest_dir, max_bytes)` | 保留下载/解密/来源检查，把最终持久保存集中到files |
| `modules/delivery/repository.py` | `create_artifact/get_artifact` | 兼容已有报告artifact_id，逐步映射统一文件元数据 |
| `modules/delivery/reports.py` | `create_pdf_artifact/enqueue_email_report` | 复用PDF和邮件投递，报告失败不重跑账单导入 |
| `platform/jobs.py` | `JobQueue.enqueue`及lease | 复用持久任务，不另建Celery、Redis或无限后台线程 |
| `platform/migrations/` | 检查时已有0001–0010 | 只追加新迁移；执行时先重新检查最新序号，不修改历史checksum |

## 2. 产品流程与首版范围

```text
微信/Web收到附件
  → 受控下载、流式暂存、文件校验、持久保存
  → 返回文件ID和接收结果
  → 识别文件及用户任务
  → 账单解析/图片提取 → 标准化候选 → 校验与去重
  → 根据指令分析候选或提交账本
  → 受控统计 → 解释/图表 → 按需PDF及渠道投递
```

保存原文件、生成导入候选、正式入账是不同操作。上传附件本身就需要可靠保存，但不能仅因扩展名是XLSX就永久记成个人账目。明确“导入账本”或用户已开启自动导入时，校验通过直接提交，不反复确认；“分析这份文件”可分析隔离的候选数据，结果注明尚未入账。不确定金额、账户归属和分类时只请求必要澄清。

首版支持：微信账单XLSX/CSV、通用明确列映射CSV、支付截图JPEG/PNG/WebP；原始其他文件可按通用上传策略保存，但未实现的格式明确标不支持分析。首版不承诺读取微信支付实时数据、小程序内部账本或手机全部通知；不恢复知识库RAG。

## 3. Module与数据归属

- `modules/files/`：唯一文件持久保存/读取/下载/生命周期入口，拥有文件元数据、上传收据和引用；内部先用本地磁盘具体实现，不预建对象存储平台。
- `modules/ledger/`：拥有账本、导入批次、原始行、标准交易、分类、退款关联和查询；不直接拼物理文件路径。
- `assistant`：识别任务、组织调用、管理run；不写交易SQL，不重复实现统计。
- `channels`：负责微信协议、下载解密和身份；不拥有另一套永久上传目录。
- `delivery`：负责投递及重试；报告生成物使用files引用，不成为上传文件的第二个权威。
- `memory`：只在用户允许的范围保存预算偏好/分类习惯；不作为账目来源或金额计算器。

跨模块通过`api.py`/`contracts.py`调用，bootstrap显式注入；files与ledger不能反调assistant私有repository。ledger通过受控模型调用做意图/分类/解释，所有调用计入现有usage并带owner/run/source。

## 4. 本地存储布局与可靠保存

```text
data/
  app.db
  hermes/state.db
  uploads/{owner_id}/{yyyy}/{mm}/{file_id}.{verified_extension}
  derived/{owner_id}/{file_id}/{extraction_version}/...
  reports/{owner_id}/{report_id}/...
  staging/{upload_id}.part
```

所有路径从一个已配置DATA_ROOT派生，数据库只保存相对storage_key。原文件名是展示元数据，不能参与路径定位。随机file_id避免同名覆盖；SHA-256用于完整性及同owner内容去重，不作为跨用户公开地址。下载走有鉴权的接口，不映射到公开static目录。

保存顺序：登记receiving上传收据 → 向staging限流写入并计算hash → 完成校验与flush/fsync → 同文件系统原子移动到最终位置 → SQLite短事务提交ready元数据/引用/后续job → 回复已保存。平台允许时同步父目录；执行环境不具备相同持久性语义时在运维文档注明。

文件系统与SQLite没有共享事务：receiving/finalizing记录保留预期storage_key和hash；恢复任务可核对完成移动但未提交的文件。只有ready文件可读取，孤立文件不立即删除，需确认无引用且超过宽限期。磁盘写满/下载不全不能返回已保存；解析失败不删除原文件。

微信游标在持久保存与可恢复任务入队后才推进，不等完整OCR/分析结束。重投同平台事件返回原上传收据；解析消息入队失败可由收据恢复，不重新下载并重复入账。沿用现有CDN来源/解密校验，不允许任意消息URL变成下载地址。

## 5. 文件schema与公开契约

字段至少覆盖下表；实际DDL在新增迁移中确定，外键和唯一索引必须有测试。

| 表 | 字段与约束 |
|---|---|
| stored_files | id、owner_id、storage_key唯一、original_name、declared_mime、verified_mime、size_bytes、sha256、kind、status、created_at、retention_policy、deleted_at；完整性状态与分析状态分开 |
| upload_receipts | id、owner、channel/account/external_event/media_index、request_id、state、expected_key、error、received_at；规范化非空scope组合唯一 |
| file_references | file_id、owner、ref_kind、ref_id、created_at；组合唯一；session/attachment/import/report/delivery各自显式关联 |
| file_extractions | id、file_id、extractor/version、input_hash、state、derived_file_id、quality_summary、error；一次提取版本幂等 |

同owner相同内容可以复用一个stored_file，但每次上传保留独立收据/展示名和引用；删除一条附件不误删另一处使用的内容。不进行跨owner去重，避免权限和删除相互牵连。

files公开方法：

| 方法 | 行为 |
|---|---|
| `save_stream(principal, chunks, metadata, request_id)` async | 消费有界字节流；返回FileRecord；重复请求返回原记录；外部metadata不能指定owner和storage_key |
| `get(principal, file_id)` | 返回有权查看的元数据；不返回绝对路径/解密凭证 |
| `open_read(principal, file_id)` | 返回受控可关闭读取句柄/流，拒绝非ready/缺失/已删文件 |
| `link(principal, file_id, ref_kind, ref_id)` | 校验资源归属后建立引用 |
| `request_delete(principal, file_id, scope)` | 显示影响范围，按明确删除范围撤销引用/启动删除流程；不能静默级联删账 |
| `reconcile()` | 后台限量核对中断收据、缺失文件及孤立文件 |

FileRecord固定包含file_id、original_name、verified_mime、size_bytes、sha256、status、created_at。内部管理员诊断才可获得受限物理定位；LLM只取得授权ID和必要提取信息。

对现有attachments/artifacts采用追加stored_file_id或显式ID映射，保持旧ID可用。backfill只处理应用受管目录中的真实文件，缺失标missing，绝不伪造ready；保留旧path读兼容直到迁移核验完成，不能直接删除当前表/覆盖技能版本目录。

## 6. 限额、权限、保留与备份

初始可配置上限：单文件50MiB，单次10附件，XLSX解压总量200MiB/条目2000/单表10万行，图片解码2000万像素，解析进程256MiB/60秒，OCR并发1/单张60秒/输出上限。达到限制时原文件若已合法保存则保留，分析标受限；超上传限额在接收时拒绝并清理不完整.part。无需为满足大小限制把原图悄悄覆盖成缩略图。

校验扩展名、内容签名与MIME；XLSX是压缩容器，检查路径穿越/展开量；不执行宏、不访问公式外链、不计算不可信公式。CSV导出防公式注入。文件内容是数据，图中文字和单元格中的指令不得控制工具或凭证。

RBAC新增`file.upload/read/delete`和`ledger.view/import/edit/export/manage`，注册并迁移到明确角色；super_admin按现有规则拥有全集，已有普通用户的默认权限按产品角色种子明确配置，不自动赋予全员跨用户读取。管理员跨owner操作遵守manage授权并审计；后台任务使用原owner重新校验，队列payload不能升级身份。

原始合法上传默认长期保留，不受30天Trace/临时产物清理规则影响。derived无活跃引用时默认7天可清理；报告沿用现有保留规则，但被用户固定、未完成投递或审计引用时保留。账本事实默认长期保留，用户明确删除/账户销毁优先。

删除分三种：移除某次附件引用；删原件但保留已导入账目（来源标不可下载）；删除原件及其独占导入数据。多来源交易只删除指定来源，是否删除仍有其他来源的交易必须显式确定。记录最小墓碑阻止异步任务重新生成已删除内容，报告/摘要/提取副本按范围撤销。

备份覆盖app.db、state.db、uploads/reports及文件索引，使用一致性SQLite备份与共同backup_id。协调窗口需暂停相关后台写入、前台文件终态提交和物理删除，再截取元数据快照；按快照列出的不可变文件建立备份固定引用，直到文件复制与hash校验完成才释放，避免复制期间被清理。不能只停后台认领却放任前台删除，也不能复制活动.db后声称完整。每日增量文件备份到独立磁盘/远程位置，数据库快照配套保留；备份记录不含明文密钥，恢复配置密钥需独立受保护流程。恢复演练验证文件hash、引用、账目和未完成任务。同机另一文件夹不承担整盘故障备份。

## 7. 解析：保留来源，再标准化

Parser Interface：`probe(file_metadata, sample) -> FormatMatch`；`parse(read_handle, options) -> ParsedStatement`。FormatMatch含格式/version/必需列/是否需要列映射；ParsedStatement含声明区间/账户线索/币种/原始行/控制汇总/警告。解析器不直接写账本或调用Agent。

微信XLSX依据列名组合寻找表头，不能固定第18行。识别交易时间、类型、对方、商品、收支、金额、支付方式、状态、交易单号、商户单号和备注；元数据/说明行不是交易。校验文件是否声明全部账单、区间及控制总笔数/收支额。支持Excel日期类型与1900/1904纪元；保留原值和转换方式。

CSV检测UTF-8/BOM/GB18030、分隔符、引号、换行和人民币符号；无法可靠识别时列出原因/请求映射，不默默跳过行。交易ID按字符串处理，禁止经float或Excel科学计数法不可逆截断；已损坏ID标无可靠标识。

金额用Decimal解析后转整数分，禁止浮点累计；先验证小数位/币种，不把未知币种当人民币。时间保留原时区并规范化UTC，查询展示按账本时区。收支为expense/income/neutral/unknown；业务类型和状态各自保存，不靠金额正负猜所有语义。

图片先保留原图，建立仅用于识别的派生图；OCR/视觉Adapter返回候选字段、置信度、文字框和原图定位。缺日期不能自动用上传时间替代消费时间，缺币种/金额/交易方向不能直接入账。无法确定的候选进入review；用户批量确认后才提交，不逐字段反复打断。未配置识别模型时保留原图并说明识别不可用，不返回假账目。

## 8. 账本模型、幂等和导入事务

| 表 | 主要字段/约束 |
|---|---|
| ledger_accounts | id、owner、provider、account_alias、currency、timezone；昵称不等于可靠账号ID |
| ledger_imports | id、owner/account、file_id、parser_version、state、declared_from/to、coverage_kind、control_totals、row_counts、error、commit_request_id唯一 |
| ledger_source_rows | id、import_id、sheet/row或image_region、raw_fields受限JSON、raw_hash、parse_state/errors；source_locator在批次内唯一 |
| ledger_transactions | id、owner/account、provider、external_id、event_role、amount_minor、currency、direction、type、merchant/product、occurred_at、status、category_id、verification、revision、deleted_at |
| ledger_transaction_sources | transaction_id、source_row_id、observed_at、status_observed；一笔交易保留多次导出来源 |
| ledger_refund_links | refund_id、original_id、amount_minor、match_method、confirmation、revision；退款可多笔；累计已确认退款不能超原单金额 |
| ledger_categories/category_rules | owner、规范分类、匹配字段/条件、优先级、scope、origin、enabled、version |
| ledger_changes | actor/run/request、entity/revision、变更差异、原因、时间；不可被模型随意改写 |
| ledger_analyses | owner、query_plan、plan_version、snapshot_revision、data_cutoff、coverage、result/产物引用、state |

导入状态：saved → probing → parsing → validated / needs_review / failed → committing → committed；允许取消，失败重试保留来源。提交前的候选不是正式交易，分析候选时标注scope=import_preview。

幂等分四层：平台消息/媒体收据；owner内文件内容；导入批次/提交request；标准交易身份。相同文件重复导入复用已提交批次；不同文件区间重叠通过交易身份合并来源。相同交易ID的新状态更新版本，不简单跳过，否则已退款订单仍停留支付成功。

不能假设退款与原单使用不同交易ID：身份至少区分provider/account/transaction_id/event_role；具有独立退款ID时纳入。标识缺失的退款用稳定来源指纹形成候选，弱匹配只提出关联，不按“金额相同+日期相近”自动吞并。图片与账单重复也先匹配可靠订单号，无可靠标识时人工确认；两次同金额付款可以是不同交易。

先把整个批次解析/验证到staging，再在短事务提交本批正式交易、来源和统计修订。首版超过10万行明确拒绝分析，避免为了“支持大文件”引入复杂分片提交；若后续分片，必须以active batch/snapshot防止半批数据被查询。重跑相同提交不新增交易；原始控制总额和标准化结果分别展示。

## 9. 统计口径与退款

必须提供显式basis，用户未指定时先给“原始收支概览”，并清楚标注不是家庭总收入/全部生活消费。不能把微信单渠道收入叫工资，也不能把支出减收入称为全部储蓄率。

| basis | 定义 |
|---|---|
| statement_flow | 按发生时间统计文件/账本原始收入、支出与中性交易；不因当前退款状态改写当期原始支付额 |
| consumption_net | 查询期间发生的已确认消费原单金额，减截至data_cutoff已确认关联的退款；转账/红包默认独立展示，未分类待说明；支持跨期退款并标注发生时间 |
| period_cash_outflow | 当期原始支出减当期确认的退款入账；明确它是当期净流出视图，不重复再排除已退款原支付 |

原订单“已全额退款”状态和单独退款收入是同一经济事件的不同证据，不能先删掉该订单金额又减退款一次。退款对账不足时提供待核实数量与可确定金额，不能把未知差额当零。跨区间退款找不到原单时列为未关联退款，不编造原单。

统计能力：按日/周/月趋势、商户排行、交易类型/类别、金额分布、大额/高频交易、支付方式、退款概览、同长度区间变化。8月/11月这类部分月明确覆盖区间，比较默认相同日期跨度，或明确显示完整月/部分月差异。

平台名不等于消费类别；如骑行订单不能因平台相同全部归外卖。分类按用户修正 > 用户规则 > 已验证映射 > 模型建议 > 未分类，匹配优先级版本化。user规则只影响本人及指定范围；自进化不能修改金额、订单号和统计公式来使报告更好看。

## 10. 意图路由和受控查询

路由结合用户动作、当前附件/会话和已授权账本：`file.save`、`ledger.preview`、`ledger.import`、`ledger.analyze`、`ledger.correct`、`ledger.report`、`schedule.create`。普通报错截图的“分析一下”不能误入账本。只传文件不含动作先完成保存与轻量识别，返回可用动作，不自动记账或外发。

账本模块公开方法：`preview(principal, file_ids, account_id=None)`、`commit(principal, import_id, expected_revision, request_id)`、`analyze(principal, query)`、`correct(principal, transaction_id, expected_revision, change)`、`export_report(principal, analysis_id, format)`。所有者由可信Principal决定。

QueryPlan固定字段示例（示例日期和数字用于规则说明，不含用户明细）：

```json
{
  "version": 1,
  "scope": "ledger",
  "account_ids": ["account-demo"],
  "period": {"start": "2026-10-01", "end_exclusive": "2026-11-01", "timezone": "Asia/Shanghai"},
  "basis": "statement_flow",
  "metrics": ["expense_sum", "expense_count"],
  "group_by": ["merchant"],
  "filters": {"directions": ["expense"]},
  "top_n": 10,
  "output": "chat"
}
```

字段使用枚举/类型/长度上限，schema拒绝未知字段。查询编译器从允许的metrics/group_by/filters选择参数化SQL，模型不提交任意SQL、文件路径或Python代码。scope、账户归属、日期覆盖、币种和basis由服务器再校验，不能依赖意图识别自觉。

“上个月”以当前用户时区解析成明确区间；数据只更新到旧日期时展示data_cutoff和缺口，不能用“最新文件月份”替代用户的上个月。“为什么上涨”输出差额贡献，不把统计相关性写成未经证实的生活原因。混合请求拆成分析、提醒、邮件等动作，按各自权限和授权范围执行。

分析结果包含query_plan、数据修订/快照、覆盖区间、币种、指标、明细证据ID、分类质量、未关联退款和警告。SQL/整数计算给出数字，LLM只接收必要聚合和少量授权证据进行解释；报表结果可重算，不把整份账单常驻模型上下文。

## 11. API、交互、报告与任务恢复

拟新增接口（执行前检查现有路由命名，保留兼容别名）：

| 路由 | 行为 |
|---|---|
| POST /api/files | 流式上传，返回file_id/status |
| GET /api/files、GET /api/files/{id} | 本人可见文件/状态，分页 |
| GET /api/files/{id}/content | 鉴权下载，安全文件名/Content-Disposition；不可猜storage_key |
| DELETE /api/files/{id} | 显式scope，返回依赖影响/删除任务 |
| POST /api/ledger/imports | 对file_ids建立候选，返回import_id/job_id |
| GET /api/ledger/imports/{id} | 进度、校验、待审字段、重复/更新/新增计数 |
| POST /api/ledger/imports/{id}/commit | expected_revision+request_id，幂等提交 |
| GET /api/ledger/transactions | 授权筛选/分页/来源引用 |
| PATCH /api/ledger/transactions/{id} | 乐观锁修正分类/必要字段，审计 |
| POST /api/ledger/analyses | 经验证QueryPlan统计，返回analysis_id |
| POST /api/ledger/analyses/{id}/reports | 导出图表/XLSX/CSV/PDF中已实现格式，返回file_id |

长任务返回202及可查状态，继续沿用Assistant run事件推送；文件保存/导入/报告状态各自可查，不能用一个成功布尔值盖住部分失败。微信简短反馈“已保存、正在解析、候选待核对、已入账、已完成”，不把迁移/SQL等内部细节发给用户。

后台handler：files.reconcile、ledger.parse、ledger.extract_image、ledger.commit、ledger.analyze、ledger.report；小型统计可同步快速完成，但统一留下分析记录。去重键含业务ID/version，重试需新attempt；新parser重算是新版本任务，不被旧dedup_key永久挡住。

每个handler认领后重新授权；外部模型调用有timeout/计量，stage落库后才进入下一阶段。进程退出后只恢复可幂等阶段，不重新发送成功邮件/微信。导出或发送失败复用已生成分析/产物，用户修改分类后旧报告标旧snapshot而不静默覆盖。

## 12. 测试、资源与交付

测试全部使用人工合成账单/图片和假OCR；个人文件仅可在用户本机以显式integration配置验收，不进入Git/日志/模型训练。

必须覆盖：表头移动、说明/空行、多sheet、日期纪元、ID超长、编码/BOM/引号/换行、精度、缺字段、控制总额不符、重复文件、重叠文件、状态更新、相同金额独立交易、原支付/退款同ID、多笔/部分/跨期退款、重复扣减、截图识别不确定、已删文件异步重生、同名文件、磁盘满、移动后DB失败、重启、权限撤销、跨owner下载、查询注入与表格导出公式注入。

性能验收按2核2G目标测试50MiB保存、10万行上限及并发图片场景；流式保存不全文件read进内存，图片和解析重任务并发1，保留前台聊天容量。压缩展开/图片解码/PDF进程各有独立预算，不把主进程低RSS当成整机安全。

功能完成需同时证明：原件可下载且hash一致；重试不重复记账；分类/退款口径可解释；按授权数据分析；数字能回查程序结果；PDF/投递复用当前模块；备份恢复后文件引用和账目仍一致。真实外联未验证时明确列出，不能用假OCR宣称实际图片识别已验收。
