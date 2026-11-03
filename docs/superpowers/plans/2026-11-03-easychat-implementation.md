# EasyChat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task when available. 无对应技能的执行环境按本文检查框顺序推进即可。用户已指定由其他模型实施，本次编写者不开始执行，也不自动分派实施任务。

**Goal:** 将EasyChat源码副本改造成SQLite部署、保留RBAC/Token排行/微信/邮件PDF的轻量个人助手，并交付可追溯记忆和受控技能/脚本自进化。

**Architecture:** 采用按业务能力组织的模块化单体，显式装配；业务数据归app.db，引擎历史归Hermes state.db。所有渠道进入一个执行Interface，生成、计量、投递、学习分别拥有状态；真实变化处用Adapter隔离。

**Tech Stack:** 沿用并核验Python/FastAPI/Hermes/Vue工程；SQLite使用标准库，MCP优先复用现有客户端。具体依赖版本在任务0与最终镜像验收固定，不凭旧pyproject推定完整运行环境。

---

## 执行总则

- 唯一写入项目：`E:\PythonCode\EasyChat`。不得改`E:\PythonCode\AgentForge`，不得连接旧业务库或复制真实.env。
- 先读[架构规范](../specs/2026-11-03-easychat-architecture.md)、[需求讨论稿](../specs/2026-11-03-easychat-design.md)和[源码定位](2026-11-03-easychat-source-map.md)。架构与已确认需求优先于早期历史草案。
- 按任务推进，每个任务内先固定规则/失败用例，再做最小实现、检查、提交；不用一次“大重构”混合所有模块。
- 下文路径均相对于EasyChat根目录；命令也在该目录执行。新文件为目标路径，原文件按函数名定位，不依赖固定行号。
- 每个任务结束更新 `docs/superpowers/plans/easychat-execution-log.md`：已完成ID、commit、实际命令/结果、未验证项、schema版本和下一项。执行者创建此日志，不能写成功但省略证据。
- 接口不确定先遵循架构契约，在任务内记录具体选择；不能用“之后处理”跳过授权、幂等、数据归属和测试。外部服务不可达不阻塞离线实现，但真实联调保留为明确未验证项。
- 每次只暂存本任务文件。首次基线按任务0清单处理，之后禁止`git add .`混入凭证/数据。用户未要求推送，默认只本地提交。

## 公共测试设施与命令约定

测试用真实临时SQLite与临时产物目录，假LLM/微信/SMTP/MCP只替换外部网络Seam，不模拟自己的SQL逻辑。时间通过注入的UTC clock函数固定；tokenizer可用确定性替身测试预算规则，真实token计数在集成验收核对。

`tests/support/rig.py`在任务1建立、随后随模块扩展，只供测试使用：

- `make_rig(tmp_path, clock=None)`：构造独立配置、数据库和产物目录，返回可async关闭的TestRig。
- `rig.seed_user(role, grants=(), revokes=(), toolsets=()) -> Principal`：通过真实access写入口创建用户和权限，不直接绕过校验。
- `rig.seed_session(principal, source='web') -> str`：真实会话入口创建会话。
- `rig.runtime`：FakeRuntime，记录执行次数和请求，按预置RuntimeEvent序列返回，不触发真实网络。
- `rig.assistant`、`rig.access`、`rig.memory`、`rig.skills`、`rig.usage`：真实模块实例，仅在对应任务完成后加入fixture；调用不允许自动fallback旧实现。
- `rig.outbound`：确定性假投递器，可设success/fail/uncertain；`rig.runner`可设超时/越权/成功。真实Adapter另列可选集成测试。
- `rig.drain_runs()` / `rig.drain_jobs()`：推进受控调度直至空闲或测试上限，超限直接失败；不通过任意sleep等待。

计划示例中的fixture通过`tests/conftest.py`明确提供，采用已安装pytest-asyncio支持的写法并在依赖任务核验。新增marker：integration（真实依赖，默认排除）、resources（目标镜像资源测量）；注册到pyproject，避免未知marker警告。默认`python -m pytest tests -m "not integration and not resources" -q`必须离线。

## 里程碑一：独立、可运行的轻量聊天底座

### Task 0：源基线、依赖及协议盘点

**Files:** 读取 `.planning/2026-11-03-easychat-design/copy-manifest.json`、`.gitignore`、`requirements.txt`、`pyproject.toml`、前端两个锁文件；创建 `docs/superpowers/plans/easychat-execution-log.md`、`docs/architecture/dependencies.md`、`tests/fixtures/contracts/legacy-api.json`、`tests/fixtures/contracts/legacy-sse.json`。

- [ ] 用copy-manifest核对业务源码未丢失；确认origin与工作目录，不把空Git仓库误当成已提交基线。记录原始dirty源码属于复制内容，不丢弃。
- [ ] 选择性修正.gitignore以跟踪本方案、架构文档、pyproject和必要部署脚本，继续忽略真实.env、数据、缓存、密钥；不强制加入整个被忽略目录。创建源码基线本地提交，包含保留的许可证。
- [ ] 静态核对144条路由定位及前端实际调用，列出保留/移除/兼容迁移；fixture记录路径、方法、必需字段、权限、返回字段、SSE事件与续传参数，不生成空数组充数。旧main.py不能为导出OpenAPI而启动。
- [ ] 确认Hermes实际Python和SDK需求，记录可复现安装入口；前端选定一种锁文件，以原有实际部署脚本和锁信息为依据。此时不为可选功能安装所有环境。
- [ ] 核验基线提交不含秘密与运行数据，记录`git status --short`、`git remote -v`和实际基线hash。

**完成标准：** 没有改产品行为；能说明当前每个保留入口、角色语义与源码来源。依赖盘点中的不一致有明确后续所属任务。

### Task 1：公开契约、显式装配与无副作用工厂

**Create:** `backend/shared/{context,errors,identifiers}.py`、`backend/runtime/contracts.py`、`backend/modules/assistant/contracts.py`、`backend/{app,bootstrap}.py`、`tests/support/rig.py`、`tests/conftest.py`、`tests/architecture/test_imports.py`、`tests/contracts/test_app_factory.py`。

- [ ] 按架构文档建立冻结值对象、Runtime Protocol和统一错误码，暂不复制旧业务逻辑。
- [ ] 写工厂契约测试：在假网络调用器和禁用线程启动条件下import/create_app不连任何网络、不读真实.env、不运行迁移、不启动监听器；lifespan才显式启动临时依赖。
- [ ] 检查旧tests/conftest和自动加载逻辑，默认离线测试只用临时配置，禁止隐式load_dotenv读取真实配置；旧真实联调测试标记integration或随删除业务退役，不能靠整个tests目录跳过来获得绿灯。
- [ ] bootstrap通过构造参数接受模块依赖与配置，保留`main.py`旧入口直到新最小闭环完成；新工厂先提供核心存活/就绪与错误映射。
- [ ] 架构测试用AST检查模块私有跨import、路由SQL和循环依赖。存量违规名单固定为具体路径，新增路径不允许加入无说明的豁免；每迁出一项缩小名单。
- [ ] 运行`python -m pytest tests/architecture tests/contracts/test_app_factory.py -q`，期望通过且无真实网络/后台线程泄漏，再提交。

### Task 2：SQLite平台、版本迁移与首批业务表

**Create:** `backend/platform/{sqlite,settings,jobs}.py`、`backend/platform/migrations/0001_core.sql`、`tests/storage/test_sqlite.py`、`tests/storage/test_migrations.py`、`tests/storage/test_jobs.py`。

- [ ] 先写临时数据库测试：重复迁移不重复播种；迁移失败回滚并不就绪；外键有效；关闭后无连接泄漏；两个工作线程写入有界重试不丢记录。
- [ ] 平台提供显式connect/transaction/migrate，schema先覆盖access/models/assistant/channels/usage所需列，后续模块按版本新增，不能在请求中建表。迁移checksum不一致必须失败。
- [ ] 实现小型jobs认领/lease/幂等键/重试状态，不加入业务handler；测试两个认领者只得到一次任务、lease过期可恢复、不可重试任务不被重新执行。
- [ ] 实测实际SQLite运行时和HermesWAL兼容规则，明确选用journal模式。无MySQL占位符替换层，不保留DBUtils连接池。
- [ ] 运行`python -m pytest tests/storage -q`；记录schema和PRAGMA结果，提交。

**SQL规则示例：** 每个规范化非空幂等scope进入UNIQUE；`INSERT ... ON CONFLICT ...`处理业务幂等，不能用`INSERT OR REPLACE`删除重建带外键的业务记录。

### Task 3：RBAC、用户/角色/部门与会话资源授权

**Create:** `backend/modules/access/{api,contracts,policy,repository,routes}.py`、`tests/access/test_policy.py`、`tests/access/test_cache_invalidation.py`、`tests/contracts/test_auth.py`。迁移来源：`backend/permission/`、`backend/service/auth/`、auth/admin控制器。

- [ ] 固定角色权限、grant、revoke和super_admin规则；测试角色变更/禁用用户/解绑后立即影响下一次操作，管理权限可以按原行为管理他人资源。
- [ ] 用纯函数表达有效权限运算，并用真实repository测试角色CRUD、toolsets JSON、用户授权和部门已有字段。角色与用户缓存有界并按版本失效，去掉Redis。
- [ ] 新公开接口生成可信Principal、执行操作授权和归属检查；HTTP与渠道调用同一实现，外部owner字段不能被信任。保留密码/认证有效性行为，不临时弱化成固定管理员。
- [ ] 只移除KB/图谱/论文专用权限种子；新增记忆/进化操作明确映射角色。迁移种子不能每次启动覆盖用户自定义授权。
- [ ] 运行`python -m pytest tests/access tests/contracts/test_auth.py -q`，确认被拒绝的请求未触发Runtime，再提交。

纯规则测试示例（目标函数在`backend/modules/access/policy.py`定义）：

```python
def test_revoke_wins_over_role_and_grant():
    from backend.modules.access.policy import effective_permissions
    assert effective_permissions(
        role_permissions=frozenset({'chat.use', 'skill.create'}),
        grants=frozenset({'chat.use'}),
        revokes=frozenset({'chat.use'}),
    ) == frozenset({'skill.create'})
```

### Task 4：模型配置与唯一用量计量入口

**Create:** `backend/modules/models/{api,contracts,repository}.py`、`backend/modules/usage/{api,contracts,repository,routes}.py`、`tests/usage/test_calls.py`、`tests/usage/test_ranking.py`。来源：model_router/model_config、trace/write/stats、utils/llm_usage。

- [ ] 建立chat/auxiliary/fallback配置与显式system主体，不带embedding/rerank管理；复用现有密钥保护方式并去掉Redis熔断同步，状态本机有界保存。
- [ ] 定义UsageRecord：call_id、run/owner/source、provider/model、时间、规范化usage、raw_usage、usage_complete/estimated。每真实请求先分配call_id，重复回调沿用它，真实重试生成新call_id。
- [ ] 实现明细/日汇总同事务写入、晚到usage差额更新、缓存字段映射；排行接口按source汇总后兼容原字段，保留trace.view语义。
- [ ] 测试同回调两次只计一次；NULL补全一次正确加量；真实重试两次计两次；系统任务不归给user1；上海日期切换正确；删Trace不删排行；无权限看不到他人明细。
- [ ] 运行`python -m pytest tests/usage -q`；记录每类模型入口的计量负责人，不允许旧observer再次加日汇总，提交。

### Task 5：Hermes Runtime Adapter与SessionDB恢复

**Create:** `backend/runtime/hermes/{adapter,sessions,tools,usage_bridge}.py`、`backend/integrations/mcp.py`、`tests/contracts/test_runtime.py`、`tests/contracts/test_mcp.py`、`tests/assistant/test_engine_history.py`。来源：`backend/hermes_adapter.py`、原SessionDB与工具注册。

- [ ] 先用FakeRuntime验证架构中的execute/cancel/aclose契约，再接Hermes，不在业务模块导入run_agent等内部模块。
- [ ] 拆出模型参数、用户会话、线程与事件转换、工具策略、缓存失效；先提供空的可注入memory/skills上下文，不挂旧AgentForgeMemoryProvider、不运行旧Dreaming。会话压缩和原始工具结果证据继续保留。
- [ ] 移除get_project_tools对KB/KG/SQL/论文包的提前导入；保留时间、待办、提醒及可用安全工具。禁用工具在实际dispatcher也不可调用。
- [ ] 复用Hermes远程MCP实现，配置服务地址/凭证引用/允许工具/超时/结果上限；按实际握手发现WeKnora能力。测试空结果、401、超时、断线重连、完整目录刷新、跨用户凭证隔离与能力健康检查，普通聊天不强制检索。测试用假MCP，不安装WeKnora服务。
- [ ] 缓存隔离测试覆盖同session不同owner、模型版本、权限版本、技能版本；ContextVar跨工作线程且最终reset；active Agent不被LRU关闭。
- [ ] 用临时state.db运行恢复测试，确认不拼接重复UI历史；真实LLM/MCP仅在可选integration中使用。运行`python -m pytest tests/contracts/test_runtime.py tests/contracts/test_mcp.py tests/assistant/test_engine_history.py -q`后提交。

### Task 6：统一Assistant、run状态与Web兼容

**Create:** `backend/modules/assistant/{api,repository,dispatcher,events,routes}.py`、`tests/assistant/test_runs.py`、`tests/contracts/test_web_chat.py`、`tests/contracts/test_sse.py`。来源：chat/stream、chat/persistence、run_registry、stream_runner。

- [ ] submit在app.db事务中校验/创建run，唯一键包含非空channel_scope；事件订阅和取消遵守架构Interface。controller不再选模型、写SQL或创建Agent。
- [ ] 测试同client_message_id返回同run、执行次数1；不同用户不能猜ID订阅；同会话两条输入顺序稳定；队列满明确busy；Web原busy语义通过薄HTTP适配保留。
- [ ] 把原SSE事件名/字段、from_seq/心跳、stream_reset、断线续传和cancel映射到新内部事件。未缓存的旧帧返回resync+最终状态，不能重新执行。
- [ ] 注入checkpoint/业务投影写入失败，确认interrupted可对账但不重跑有副作用工具；完成状态与投递/学习job同库事务提交。
- [ ] 运行`python -m pytest tests/assistant tests/contracts/test_web_chat.py tests/contracts/test_sse.py -q`；新入口达到离线Web聊天闭环后，切换main.py到新app工厂，提交。

接口行为测试示例（TestRig先按公共设施定义实现）：

```python
async def test_duplicate_web_submit_runs_once(rig):
    from backend.modules.assistant.contracts import RunCommand
    user = rig.seed_user(role='user', grants=('chat.use',))
    session = rig.seed_session(user)
    command = RunCommand(user, session, 'web', 'msg-1', '你好')
    first = await rig.assistant.submit(command)
    second = await rig.assistant.submit(command)
    await rig.drain_runs()
    assert first.run_id == second.run_id
    assert second.duplicate is True
    assert rig.runtime.execute_count == 1
```

### Task 7：微信与多端归一化、身份绑定和持久去重

**Create:** `backend/modules/channels/{api,contracts,repository,routes}.py`、`backend/modules/channels/wechat/{listener,parser,account}.py`、`tests/contracts/test_wechat.py`、`tests/assistant/test_channel_identity.py`。来源：platform_gateway、platform_config/user_binding控制器、wechat/与backend/wechat/。

- [ ] 搬迁现有iLink扫码/凭证/长轮询/重连，生命周期可观测实际状态；不保留假running标志掩盖监听失败。
- [ ] 定义platform/account/external_user/chat/message等规范化字段；身份查绑定，线程映射由可信owner决定，不使用昵称或单一openid跨账号串联。
- [ ] 微信调用与Web相同Assistant；消息去重落channel_events，重复接收不执行两次。没有稳定消息ID时记录近似指纹模式和短窗口，不永久吞掉相同文本。
- [ ] 测试未绑定/禁用/解绑拒绝、两个机器人账号同message_id不冲突、图片文件引用不进入无限内存、会话切换及多模态转换。跨端共享owner记忆但会话独立。
- [ ] 运行`python -m pytest tests/contracts/test_wechat.py tests/assistant/test_channel_identity.py -q`；不进行真实扫码或发送，真实iLink联调单列integration，提交。

**里程碑一验收：** 干净临时目录+假LLM可通过Web/微信同链路对话、RBAC、SQLite恢复和Token统计；默认安装和启动不导入本地RAG或连接旧基础设施。真实微信未联调时必须如实说明。

## 里程碑二：可靠提醒、投递和可追溯记忆

### Task 8：投递账本、文本提醒与持久调度

**Create:** `backend/modules/delivery/{api,contracts,repository,worker}.py`、`backend/modules/scheduling/{api,repository,scheduler,routes}.py`、`tests/delivery/test_delivery.py`、`tests/delivery/test_schedule.py`。

- [ ] 先实现目标、不可变产物引用、delivery/parts状态和微信文本Adapter；应用最终结果保存后再投递，失败只重试同结果。
- [ ] 到期计划写唯一occurrence，重启不重复生成；新任务默认微信/文本，保留已有任务的渠道/格式。错过时间默认只处理最新未完成实例，明确记录错过，不自动补发无限历史。
- [ ] 测试发送成功、有限失败、确认丢失uncertain、分块失败恢复、解绑后不继续发、投递失败时Runtime执行次数不增加；验证job lease不等于外部exactly-once。
- [ ] 把原cron调用迁到统一Assistant/Delivery，调度器只有一个生命周期入口，删重叠后台任务启动；提醒与投递各自拥有状态。
- [ ] 运行`python -m pytest tests/delivery -q`，提交。

### Task 9：事实/事件/经验记忆、纠正与遗忘

**Create:** `backend/modules/memory/{api,contracts,repository,extractor,retrieval,forgetting,routes}.py`、`backend/runtime/hermes/memory_bridge.py`、`tests/memory/test_{retrieval,revision,forgetting}.py`、`tests/fixtures/memory/cases.json`。

- [ ] 以真实来源消息建立20条脱敏用例，覆盖“上次直播担心什么”、别名/时间、相似事件、短期指令、长期偏好、archived冷记忆、权限隔离、缺失来源。固定其中一部分只作回归，不拿去生成候选。
- [ ] 建单SQLite记忆模型与revisions/feedback/forget_rules，写入和修改要求expected_version；同时保留用户确认与模型推断，不只留一段总结。
- [ ] 实现有限候选检索、相关性排序、2000 token预算、top5与来源；中文短词与同义扩展有可测回退。候选0条时说明无结果，不调用模型编造用户往事。
- [ ] 接入明确记住/忘记、纠正和阶段完成信号的幂等jobs；forget阻止旧消息重提取，并处理衍生摘要/经验。分别测试source删除和显式遗忘，不把墓碑保存成敏感原文副本。
- [ ] Runtime MemoryProvider桥接只用公开memory接口，后台旧provider/Dreaming失效；运行`python -m pytest tests/memory -q`与聊天回归后提交。

### Task 10：个人技能、不可变版本与Hermes写入桥接

**Create:** `backend/modules/skills/{api,contracts,repository,versions,routes}.py`、`backend/runtime/hermes/skills_bridge.py`、`tests/skills/test_versions.py`、`tests/skills/test_hermes_bridge.py`。

- [ ] 抽取现有个人技能文件读取/编辑，删社区与内容池依赖；有效技能列表仍按权限和owner筛选，不按owner_id=1猜公共归属。
- [ ] 新候选写不可变内容路径+hash，元数据记录父版本/来源；activate用expected_active_version比较交换。文件和DB中断时保留旧active，孤立文件延迟清理。
- [ ] 覆盖Web编辑、skill_manage及后台review三个写入口，统一走skills API；不能绕过版本直接编辑当前激活目录。运行时读取固定版本快照，更新只影响下一轮。
- [ ] 对File/Terminal/CodeMode/Runner设置受保护路径规则，运行时不可直接改技能不可变内容或active指针；需要编辑时转换成受版本管理的提案。后台进化的origin策略不能被所有者较大的终端权限覆盖。
- [ ] 测试pin/用户手写保护、并发候选激活失败不覆盖、版本回退、恶意路径/符号链接越界、内容指纹不符拒绝和重启恢复。
- [ ] 运行`python -m pytest tests/skills -q`，记录既有skill_usage侧写数据的迁移/只读兼容方式，明确唯一权威，提交。

**里程碑二验收：** 记忆可查来源、可纠正、可遗忘；技能可恢复旧版；提醒与投递失败不会重复执行任务。普通文本流程不需要PDF或SMTP可用。

## 里程碑三：经验到技能与受控脚本进化

### Task 11：唯一学习调度、证据与预算

**Create:** `backend/modules/evolution/{api,contracts,repository,evidence,budget,worker}.py`、`tests/evolution/test_signals.py`、`tests/evolution/test_budget.py`。

- [ ] 完成run的显式回调入队，按source_event_id去重；学习任务不能触发另一个“学习自身”任务。后台只一个并发，前台在阶段切换时优先。
- [ ] 将任务反馈变成带run/source、适用条件、反例和确认程度的经验，不把模型自评当用户事实。旧Dreaming、background_review、Curator不能各自再产生重复写入。
- [ ] 按架构默认预算实现预留/核销/超限停止，持久化跨重启；未知usage保留未结算预留，明确失败策略，不在未知时立即返还全部预算。
- [ ] 测试重复反馈学习一次、禁用用户/权限变更阻止执行、暂停后不认领、重启lease恢复、超预算前不发下个LLM调用、system主体归属正确。
- [ ] 运行`python -m pytest tests/evolution/test_signals.py tests/evolution/test_budget.py -q`，提交。

### Task 12：候选生成、回放比较、激活与回滚

**Create:** `backend/modules/evolution/{proposal,validation,adoption,routes}.py`、`tests/evolution/test_validation.py`、`tests/evolution/test_adoption.py`、`tests/fixtures/evolution/regression.json`。

- [ ] 复用Hermes已有review提示策略/来源保护，输出结构化候选；候选只调用skills.propose，不直接写文件或修改验证器。
- [ ] 验证顺序固定：schema/能力范围/必需样例 → baseline与candidate同环境回放 → 保留回归用例 → 指标和证据记录。规则型指标优先，必要模型判断独立记录不充作硬证据。
- [ ] 自动采用要求必需用例全部通过、无确定性回归、至少一项预先定义目标改善；无法比较、只有格式变长或依赖不可用均不采用。确需纯修复候选时，目标是原失败用例转通过且其他用例不退步。
- [ ] 测试原版更好时仍保留原版、父版本已变时stale、用户手写/pin不被动、回放不会真实投递、对照数据不污染用户会话；激活后观测失败可回退到已知有效版本。
- [ ] 运行`python -m pytest tests/evolution/test_validation.py tests/evolution/test_adoption.py tests/skills -q`，提交。Harness²本阶段只借鉴流程，不额外安装其执行器链。

### Task 13：脚本Runner与权限范围

**Create:** `backend/integrations/script_runner.py`、`backend/modules/evolution/runner_contracts.py`、`tests/evolution/test_runner_contract.py`、`tests/integration/test_linux_runner.py`。

- [ ] 定义Runner输入：版本artifact、工作目录引用、输入artifact、deadline、memory/output限制、显式文件/网络/工具能力；返回exit/timeout/denied、产物与受限日志，不接收整包业务凭证。
- [ ] 通过假Runner先验收候选流程；Linux实现选择受限本地runner或配置远程runner并固定文档，默认无可用隔离能力时不启用自动执行。现有Code Mode只作受控工具组合，不宣称AST过滤能安全执行任意Python。
- [ ] 真Runner必须验证文件越界、网络越界、环境凭证不可见、超时硬终止、内存/输出限制、子进程回收；额外验证绕过技能工具直接改生产源码、权限文件、技能active内容被拒绝。在无外发测试环境执行，不在用户真实目录试攻击样例。
- [ ] 连接版本验证和受限自动使用，不赋予修改EasyChat源码、鉴权、迁移、部署的权限。生成/静态检查/执行验证三种状态在UI和记录中明确区分。
- [ ] 运行`python -m pytest tests/evolution/test_runner_contract.py -q`；目标Linux环境另运行`python -m pytest tests/integration/test_linux_runner.py -m integration -q`。未通过真实隔离测试时标注功能未验收并保持关闭，提交。

**里程碑三验收：** 至少一个可重放任务从失败经验形成技能改进，通过回归后激活并可回退；真实副作用不会在验证中发生。脚本自动执行必须满足真实Runner验收，不能以假测试冒充完整交付。

## 里程碑四：保留能力闭环、删减与交付

### Task 14：邮件/PDF按需启用与历史任务兼容

**Create/Modify:** `backend/integrations/pdf.py`、`backend/modules/delivery/{smtp,reports}.py`、邮件配置/收件人路由迁移、`tests/delivery/test_reports.py`、`tests/delivery/test_email.py`、可选真实集成测试。

- [ ] 保留SMTP配置、联系人、渠道选择与报告格式，迁到本模块和SQLite；能力开关及凭证保护保留RBAC，不让配置响应泄露密码。
- [ ] PDF生成独立受控进程/队列，先落不可变artifact；邮件失败只重发该文件。未启用时不import渲染栈，不启动SMTP连接。
- [ ] 测试新提醒默认文本、老PDF任务格式不变、渲染缺依赖明确不可用、渲染超时回收进程、临时文件清理不误删被投递引用产物、发送不确定状态正确记录。
- [ ] 假SMTP/真业务测试先过；真实渲染和SMTP在用户提供测试端点后单列integration，未授权不发真实邮件/微信。
- [ ] 运行`python -m pytest tests/delivery -q`，记录可选依赖安装组和能力检查，提交。

### Task 15：前端、API契约与旧模块删除

**Modify:** `agent_frontend/src/{router,api,stores,views}`、`backend/controller/__init__.py`、`main.py`、旧controller/service/db、安装元数据和锁。**Test:** `tests/architecture/test_removed_dependencies.py`、`tests/contracts/test_api_compatibility.py`。

- [ ] 保留聊天/历史、RBAC用户角色部门、Token榜、邮件/PDF、技能、提醒、记忆、运行与进化页面；迁移到模块公开接口，组件内不拼接凭证/执行授权。
- [ ] 删除KB/图谱/评测/论文/社区/SQL专用路由与菜单，再检查前端网络请求不触达已删接口。skill_controller中混合的个人CRUD与社区端点按清单拆分，不能整文件误删。
- [ ] 将路由自动扫描改为bootstrap显式注册；删除旧全局mapper、旧provider与图向量基础设施启动、MySQL驱动/迁移/连接池。模块迁移完成后删除对应兼容桥，不留两套业务权威。
- [ ] 随移除业务删除只验证KB/图谱/论文的旧测试与样本；跨模块鉴权、用量、上下文证据、文件处理测试迁到新Interface继续验证。核对testpaths、markers和conftest，默认全量测试不能残留已删模块import。
- [ ] 全量检索禁用依赖和旧表：backend/rag、graphrag、service/kb、pymysql、DBUtils、redis、neo4j、pymilvus等；只允许历史文档/测试禁止列表提及。内嵌Hermes的可选适配器不要求无字面引用，但默认import闭包不得加载这些依赖。
- [ ] 合并pyproject与运行安装入口、core/pdf/dev依赖组；确定无引用后删前端图谱/论文依赖。执行`npm run type-check`、`npm run build`（若任务0选择pnpm则统一用pnpm，不混用），及`python -m pytest tests/architecture tests/contracts -q`，提交。

### Task 16：干净镜像、资源、恢复与最终交付

**Modify/Create:** `docker/Dockerfile`、`docker/docker-compose.yml`、`.env.example`、`README.md`、`docs/architecture/{operations,hermes-patches}.md`、`tests/resources/`及资源采样工具、执行日志。

- [ ] compose只要求EasyChat与持久卷，单worker；MCP地址、SMTP/PDF、Runner由配置启用，不自动部署WeKnora。文档说明主进程和可选子进程资源分别测量。
- [ ] 在无MySQL/Redis/Neo4j/Milvus服务的干净环境安装core依赖并启动；关闭邮件/PDF/Runner时普通聊天正常。单独安装PDF组并验证按需能力，不把缺依赖错误吞掉。
- [ ] 运行完整离线测试、前端类型/构建检查、真实临时数据库迁移。记录真实集成状态；未取得测试凭证的功能保留未验证标签，不声称真实外发成功。
- [ ] 目标Linux 2核2G环境采样冷启、空闲、100轮连续对话、20会话切换、MCP大结果/超时、受限媒体、PDF峰值与Runner峰值；采样主进程及子进程/cgroup，记录p50/p95延迟、RSS趋势、队列/线程数和退出状态。常态主进程RSS目标<1GiB，异常增长需定位后交付，不能只贴某一时刻数字。
- [ ] 两库+产物备份/恢复演练，恢复用户角色、聊天、记忆、技能active版本、排行和未完成投递；注入升级失败验证回到匹配代码/数据版本。完成执行日志与以下交付清单，再提交，不自动push。

## 最终执行命令与预期

```powershell
python -m pytest tests -m "not integration and not resources" -q
python -m ruff check backend tests main.py
python -m compileall -q backend main.py
```

目标：离线规则/集成/契约/架构测试全部通过，新改代码lint无错误；compileall只是语法检查，不代替行为验证。既有Hermes第三方lint问题单独固定范围，不能批量格式化内核制造噪音；不能靠新增全局ignore屏蔽本次错误。

前端在`agent_frontend`执行已选包管理器的type-check/build。测试命令、版本和实际输出摘要必须记录；上述是未来实施命令，本次方案编写没有运行这些业务测试。

## 最终交付清单

- [ ] 已确认功能均可用或清晰列出真实联调限制，没有用“后续补”冒充完成。
- [ ] 模块公开Interface、数据归属、状态转换和错误规则与架构一致。
- [ ] 无新增循环import、无路由SQL、无重复权限/模型/记忆业务实现。
- [ ] SQLite幂等/事务/索引/迁移及两库恢复已测；后台任务恢复不重复外部副作用。
- [ ] RBAC优先级和管理授权不退化，用户状态与权限变更影响后台执行。
- [ ] Token排行保留且无observer重复计量，未知usage和后补usage可解释。
- [ ] 微信/Web/提醒统一执行；邮件/PDF按需能力保留，投递失败不重跑任务。
- [ ] 事件记忆有来源，遗忘不重生，自动技能版本有证据和回滚。
- [ ] 脚本执行真实隔离验收通过才启用；未通过不得写“完整自进化已完成”。
- [ ] 目标镜像资源数据、运行手册、配置模板、补丁清单和阶段提交齐全。

阶段回退统一使用本地阶段commit+匹配备份；不写一套未经验证的down迁移，不回滚到AgentForge目录上覆盖用户旧项目。发现需求冲突先保留用户明确要求的能力，说明冲突并更新文档，不擅自扩大或删减范围。
