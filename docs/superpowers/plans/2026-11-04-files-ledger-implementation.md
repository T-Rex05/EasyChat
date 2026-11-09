# EasyChat Files and Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task when available；环境无该技能时按检查框执行。本次由用户指定其他模型实施，方案作者仅写文档。

**Goal:** 在现有EasyChat上增量交付可靠文件保存、微信账单导入、图片候选提取、意图路由、准确统计和报告。

**Architecture:** 新增files与ledger两个业务Module；复用现有Assistant、RBAC、JobQueue、usage和delivery。原件存本地持久目录，元数据/账目存app.db，模型理解和解释，受控查询计算金额。

**Tech Stack:** 沿用当前已锁Python/SQLite/FastAPI/Vue工程；表格读取库和OCR/视觉依赖在Task F0核查实际锁定版本与官方用法。优先复用，按需安装，核心保存/CSV统计不依赖OCR服务。

## 入口与范围

先读[详细设计](../specs/2026-11-04-files-ledger-design.md)，然后核对`EASYCHAT_PROGRESS.md`、当前代码和旧实施日志。旧主体Task 0–16已由执行模型完成，不重做。工作目录固定`E:\PythonCode\EasyChat`，不更改AgentForge和个人桌面账单。

开始前运行git status、核对HEAD，保留并尊重新改动。按F0–F11执行，逐任务测试和本地提交；不自动推送。记录到`docs/superpowers/plans/files-ledger-execution-log.md`，不要覆盖旧主体执行日志。每项记录schema、接口变化、实际命令/结果、未验收项、下一项与回退点。

首版不实现手机自动监听、小程序数据接口、云对象存储服务或整套财务ERP；合法上传保存、账单解析、准确统计和授权来源必须完整。用户真实文件不作为测试fixture或仓库提交内容。

## Task F0：当前接口、迁移与合成基线

**Read:** `modules/assistant/api.py:register_attachment`、`channels/wechat/media.py:MediaFetcher.fetch`、`delivery/repository.py:create_artifact/get_artifact`、`delivery/reports.py`、`platform/jobs.py`、`bootstrap.py`及当前模块测试。

**Create:** `tests/fixtures/ledger/README.md`、`tests/support/ledger_fixtures.py`、`docs/superpowers/plans/files-ledger-execution-log.md`。

- [ ] 记录现有附件ID、物理目录、授权、报告artifact外键、清理任务、媒体重试与游标规则，列出桥接点；不靠旧讨论稿推断当前实现。
- [ ] 检查最新迁移编号并记录；本次检查已有0010，实施时若已新增迁移，应从实际下一个号开始，绝不编辑已提交checksum文件。
- [ ] 运行当前核心离线测试命令记录真实基线；用户进度中的303通过不是本轮已运行证据。核对哪些已有用例可复用，不复制一套同名测试设施。
- [ ] 建人工合成微信XLSX/CSV、截图及假OCR结果，使用虚构商户和订单。fixture生成器包含说明行/表头位置变化、超长字符串ID、退款与重叠导出；文件生成不需要读取个人账单。
- [ ] 核查核心读取依赖、可选视觉能力、PDF导出和前端组件版本，记录选用库及受控读取设置，提交F0。

## Task F1：统一文件模型和版本化迁移

**Create:** `backend/modules/files/{contracts,api,repository,local_store}.py`、追加`0011_files.sql`（以F0核对结果调整编号）、`tests/files/test_metadata.py`。

- [ ] 建stored_files/upload_receipts/file_references/file_extractions，状态/唯一键/外键/索引对应设计。可空scope规范为非空，测试Web无渠道账号也能幂等。
- [ ] 定义FileRecord与唯一FileService入口，原件状态、提取状态分开；Repository不返回可被前端拼接的绝对路径。
- [ ] 测试同owner同内容不同上传收据复用内容、不同owner隔离、同名不同内容不覆盖、删除一引用不删共享原件。
- [ ] 迁移测试覆盖重复启动、旧附件表存在/为空、升级失败回滚、数据库checksum一致，不启动真实服务。
- [ ] 运行`python -m pytest tests/files/test_metadata.py tests/storage -q`后提交。

## Task F2：流式保存、崩溃恢复和受限读取

**Modify:** files/local_store与api；**Create:** `backend/modules/files/reconcile.py`、`tests/files/test_persistence.py`、`tests/files/test_recovery.py`。

- [ ] save_stream登记收据，按块写.part并计算hash，类型/大小校验后flush/fsync、原子移动，再提交ready和引用。不要全文件read到内存。
- [ ] 注入下载中断、磁盘满、hash不符、移动失败、移动后DB失败，确认只有真实ready可读取，中断可恢复、不出现已保存假成功。
- [ ] 认领有界reconcile任务，核对收据/最终路径/hash，修复已完成但未登记的记录；孤立文件先标记，宽限期后且无引用才清理。
- [ ] 测试路径穿越、符号链接绕出、原始文件名注入、类型伪装、压缩展开和图片像素限制；重处理不会修改原件hash。
- [ ] 运行`python -m pytest tests/files/test_persistence.py tests/files/test_recovery.py -q`，提交。

## Task F3：现有附件/报告桥接、微信和Web接入

**Modify:** `assistant/api.py`、`channels/wechat/media.py`及现有媒体协调入口、`delivery/reports.py`；**Create:** `modules/files/routes.py`、`tests/files/test_legacy_bridge.py`、`tests/contracts/test_file_upload.py`。

- [ ] 旧attachment_id/artifact_id关联stored_file_id，保持原调用返回兼容。旧路径仅对受管目录backfill；缺失文件标missing，不伪造ready；不迁移技能不可变目录。
- [ ] 微信下载解密走原协议/SSRF校验，保存委托files；游标在可恢复保存/任务登记后推进。媒体重投用receipt去重，不重复创建账目。
- [ ] Web上传、元数据和鉴权下载接入显式路由；后台下载复核当前用户状态与owner/manage。下载文件名安全编码，不暴露storage_key。
- [ ] 测试Web/微信上传同文件、用户禁用/解绑、跨owner猜ID、文件保存成功但Assistant提交失败后可恢复，以及报告仍能通过旧artifact_id发送。
- [ ] 运行`python -m pytest tests/contracts/test_file_upload.py tests/files/test_legacy_bridge.py tests/contracts/test_wechat.py tests/delivery -q`；若当前测试路径不同按F0实际名称执行并记录，提交。

**阶段A完成：** 无OCR/LLM时也能从微信/Web可靠保存、查状态、下载原件，现有报告/技能功能不退化。

## Task F4：账本schema与纯解析器

**Create:** `backend/modules/ledger/{contracts,repository,api}.py`、`backend/modules/ledger/parsers/{base,wechat_xlsx,wechat_csv,generic_csv}.py`、`backend/modules/ledger/normalization.py`、新增账本迁移、`tests/ledger/test_parsers.py`、`tests/ledger/test_normalization.py`。

- [ ] 建设计中的accounts/imports/source_rows/transactions/sources/refund_links/categories/rules/changes/analyses，正式事实和候选隔离；公开入口先支持preview。
- [ ] parser定位必需列，不固定行18；提取声明区间、账户线索、时区、控制总额和原始行定位，支持多sheet但不重复合并同一表。
- [ ] CSV覆盖BOM/GB18030、逗号/制表符、带引号字段/嵌入换行；XLSX不执行宏/公式/外链，缺必需原值行明确失败/待审，不默默跳过。
- [ ] 金额函数`money_to_minor(text: str) -> int`只接受可验证小数/币种规则，用Decimal转分；订单ID全程字符串；时间支持Excel纪元与明确时区。
- [ ] 合成样本控制汇总与原始行总额独立对账。运行`python -m pytest tests/ledger/test_parsers.py tests/ledger/test_normalization.py -q`后提交。

测试示例：

```python
def test_money_keeps_decimal_cents():
    from backend.modules.ledger.normalization import money_to_minor
    assert money_to_minor('0.10') + money_to_minor('0.20') == 30
    assert money_to_minor('1000000.01') == 100000001
```

## Task F5：导入状态机、去重、状态更新与提交

**Create:** `backend/modules/ledger/{imports,identity,jobs}.py`、`tests/ledger/test_imports.py`、`tests/ledger/test_transaction_identity.py`。

- [ ] preview登记版本化批次，经JobQueue流转saved/probing/parsing/validated/needs_review/failed；原件保存成功不等于导入成功。
- [ ] 实现文件、批次、提交请求和交易身份四层幂等；重叠导出合并来源，已存在ID的新状态更新交易版本。原单和退款即使同ID也按event_role区分。
- [ ] 无可靠ID的截图/退款仅生成候选匹配，不能合并两笔同时间同金额付款；可靠交易身份重复来源可复用并审计。
- [ ] commit要求expected_revision/request_id，事务原子提交批次事实和来源；查询不包含未提交/半成品。超大批次先拒绝分析，不引入未设计的分片半提交。
- [ ] 注入提交中断/并发重复commit/取消/删除原件，重启后只重试可恢复阶段。运行`python -m pytest tests/ledger/test_imports.py tests/ledger/test_transaction_identity.py -q`后提交。

## Task F6：图片提取与可核对候选

**Create:** `backend/modules/ledger/image_extraction.py`、`backend/integrations/bill_vision.py`、`tests/ledger/test_image_extraction.py`。

- [ ] 定义视觉Seam：输入受限文件引用/派生图，输出字段、置信度、原文及位置。使用既有辅助模型与usage计量，先以FakeVision完成业务测试。
- [ ] 原图不可变，解码/压缩只生成派生物；设置像素/时间/输出预算，单图识别并发1，模型失败保存原图和失败状态。
- [ ] 测试缺金额/方向/日期/币种、多个付款截图拼图、低置信度与恶意图片文字；上传时间不能充当未知交易时间，识别文本指令不执行。
- [ ] 提供批量确认/修正候选再commit的Interface；明确图片候选与已有账单匹配规则，缺ID的疑似重复必须可审阅。
- [ ] 运行`python -m pytest tests/ledger/test_image_extraction.py -q`；真实视觉服务另列integration，未验证不声称实际图片识别可用，提交。

## Task F7：分类与退款口径

**Create:** `backend/modules/ledger/{classification,refunds,metrics}.py`、`tests/ledger/test_classification.py`、`tests/ledger/test_refunds.py`。

- [ ] 分类优先级落实用户修正/用户规则/验证映射/模型建议/未分类；规则有scope/version，平台名不直接等于商品用途。
- [ ] 原单/退款来源关联，支持部分、多笔和跨期，弱关联待确认；退款累计不能超原单金额，状态证据不等于另一笔退款入账。
- [ ] 三种basis独立实现：statement_flow、consumption_net、period_cash_outflow。测试退款状态和退款收入同时出现不会减两次，未知关联保留待核实。
- [ ] 合成用例：原消费100、部分退款30、转账50、充值200；原始支出150/退款入账30/中性200，当期净流出120，已确认消费净额70。另一用例消费100全退100，消费净额0，不能为-100。
- [ ] 运行`python -m pytest tests/ledger/test_classification.py tests/ledger/test_refunds.py -q`，提交。

## Task F8：QueryPlan、查询编译器和确定性统计

**Create:** `backend/modules/ledger/{queries,query_schema,analytics}.py`、`tests/ledger/test_queries.py`、`tests/ledger/test_coverage.py`。

- [ ] 将设计QueryPlan落实强类型schema，枚举metric/group/basis，验证日期、top_n/行数、账户归属和币种；外部owner_id和未知字段拒绝。
- [ ] 编译白名单参数化SQL，支持趋势、商户、类型、分类、金额档位、退款和对比；查询只读正式事实或显式preview scope，不执行模型SQL/Python。
- [ ] 返回data_cutoff、coverage、snapshot_revision、币种、来源ID和quality警告。用户要的区间无覆盖时不返回“花费为零”；部分月份比较明确口径。
- [ ] 测试注入/越权、多账户不同币种、不完整月、旧账单询问上月、0条真实交易和无数据的区别、分类修正后旧报告snapshot不变。
- [ ] 运行`python -m pytest tests/ledger/test_queries.py tests/ledger/test_coverage.py -q`，提交。

## Task F9：意图路由、API与微信连续对话

**Create:** `backend/modules/ledger/{routing,routes,tools}.py`、`tests/contracts/test_ledger_api.py`、`tests/ledger/test_intent_routing.py`；**Modify:** 当前Assistant工具装配、bootstrap与RBAC种子。

- [ ] 实现file.save/ledger.preview/import/analyze/correct/report和schedule组合动作。看用户意图、附件probe和会话上下文，不按“分析”关键词单独路由。
- [ ] 上传无动作只保存并提供动作；明确导入直接幂等提交校验通过记录，明确分析可使用候选scope；只对不确定部分澄清，不反复请求已给授权。
- [ ] 新增设计中的files/ledger API与明确RBAC，工具实际dispatcher再授权；新增权限配置到预期角色，不能更改现有super_admin/grant/revoke规则。
- [ ] 端到端测试“文件上传→分析→追问商户→分类纠正→重算”、报错截图不入账、无文件但已授权账本查询、用户要求未有数据的日期、模型输出未知QueryPlan字段被拒。
- [ ] 运行`python -m pytest tests/contracts/test_ledger_api.py tests/ledger/test_intent_routing.py tests/access -q`，提交。

## Task F10：分析报告、导出与提醒复用

**Create:** `backend/modules/ledger/reports.py`、`tests/ledger/test_reports.py`；**Modify:** 现有前端文件/账本页和API、report/delivery/scheduling公开接入。

- [ ] 报告展示统计basis、日期/覆盖、币种、快照、分类质量和来源；图表与文字用同一结果，模型不得自行改数字。首版交付聊天+CSV+PDF，XLSX导出若启用须单独验收公式/格式，不能留只返回文件名的空实现。
- [ ] 报告原件进入files并关联analysis；PDF/邮件沿用当前能力，投递失败复用相同产物，不重做导入。CSV文本字段防公式注入。
- [ ] “每周报告”复用现有计划/投递，报告注明数据更新截止；有新文件不代表有实时微信支付数据，不发送虚构当日汇总。
- [ ] 前端支持文件状态/来源下载、导入核验、重复/更新计数、待审图片、交易纠正和口径切换；手机微信返回简洁进度与可用动作。
- [ ] 运行`python -m pytest tests/ledger/test_reports.py tests/delivery -q`，前端执行当前锁定包管理器的type-check/build，提交。

## Task F11：留存删除、备份恢复与最终回归

**Create:** `backend/modules/files/lifecycle.py`、`tests/files/test_lifecycle.py`、`tests/files/test_backup_restore.py`、`docs/architecture/files-ledger-operations.md`；**Modify:** 现有清理/备份注册和增量进度记录。

- [ ] 原件默认长期保留，derived临时内容7天；清理先看引用和任务状态，旧Trace/报告TTL不得波及原始上传。设置用户配额/磁盘低水位，临界时明确拒绝新保存，不删除旧原件腾空间。
- [ ] 实现三种删除scope、异步墓碑、来源/交易多来源保护，测试删除过程中OCR/导入job晚到不会重生；备份恢复后的删除规则继续有效。
- [ ] app.db/state.db和uploads/reports协调备份，记录backup_id/文件hash；恢复到隔离目录验证原件可读、账目数额/来源/分类/报告一致，未完成job可恢复且不外发。
- [ ] 2核2G目标测50MiB保存、压缩展开限制、最大支持批次、图片识别进程、PDF和前台聊天资源，记录主进程和子进程RSS/时延/磁盘/线程；未实测必须列出。
- [ ] 执行下列最终命令与现有核心回归，提交增量完成记录；不改主体旧任务的已完成证据，也不自动push。

```powershell
python -m pytest tests/files tests/ledger tests/contracts tests/access tests/storage tests/delivery -m "not integration and not resources" -q
python -m ruff check backend/modules/files backend/modules/ledger tests/files tests/ledger
python -m compileall -q backend/modules/files backend/modules/ledger
```

目录或marker与当前工程不一致时在F0记录实际映射后统一使用；不得通过跳过全部测试或追加全局ignore消除错误。真实视觉/微信/SMTP依赖按现有integration机制验收，不发起未经明确授权的真实外发。

## 完成门槛与回退

- [ ] 合法原件可持久保存/重启下载/hash一致；失败状态可解释。
- [ ] 新旧附件/报告ID兼容，没有第二套永久文件权威。
- [ ] XLSX/CSV确定性解析，图片输出可核对且可提交的候选。
- [ ] 四层去重、交易状态更新、跨文件来源和退款口径通过合成对账。
- [ ] 意图路由结合上下文，查询白名单且授权，模型不负责金额计算。
- [ ] 重试不重复入账/外发，删除不重生，备份恢复正确。
- [ ] 普通聊天、RBAC、Token排行、技能和已有提醒回归通过。
- [ ] 实际命令/结果、真实联调限制、资源数据、迁移版本、接口和本地commit记录齐全。

每阶段变更前备份匹配代码/数据库/产物索引。失败时回退对应代码并恢复协调快照，不执行未经验证的反向DDL，不覆盖原项目或桌面文件。旧迁移不可变，追加迁移引入唯一文件权威后保留必要兼容读取，测试通过再移除已无调用者的旧路径。
