# EasyChat 微信记忆、星图与多角色改造方案

日期 2026-11-20。审查基线为 `03b41ee` 及本地已有未提交改动，审查范围为从微信或 Web 入口到会话、记忆、角色和 Hermes 的完整功能链。本方案供审阅，产品代码由后续实施任务处理。（Git 核查与交付范围）

基线验证运行了第 7 节第一条命令，结果为 `213 passed in 128.30s`。已用合成数据单独复现 scope 共用与来源引文残留，两个问题都需要新的回归用例才能进入改造验收。（本轮实测）

**目标**　让用户能核对某轮对话召回的记忆，在微信或 Web 修订它，再按需开设具有独立会话和记忆的角色。（拟定设计）

**架构**　EasyChat 继续持有身份、会话、记忆和角色配置。微信负责短文本查询与操作，Web 负责列表、图谱与版本详情，Hermes 接收已筛选的上下文。DeepSeek Harness 保留为可独立评估的执行器选项。（建议）

**实施顺序**　先修遗忘残留并打通微信精确修订，再记录单轮召回和做只读图谱，最后引入独立角色与后台会话。每阶段均能单独验收。（方案）

## 1. 现有代码与发现

| 环节 | 当前实现与证据 | 对改造的影响 |
|---|---|---|
| 微信受理 | 绑定用户及 `chat.use` 先检查，再解析当前 session 和命令。`/记忆` 返回最近 10 条的摘要，`/忘掉` 支持前缀或关键词。见 `backend/modules/channels/api.py:635`、`commands.py:185` | 复用确定性命令和绑定身份，微信查看详情、修订和按轮查询需要新增入口 |
| Web 记忆 | `MemoryView.vue` 已有列表、召回、来源引用、修订与遗忘。`memory/routes.py` 没有单条详情或修订历史读取路由 | 图与列表复用现有编辑和错误处理，增加经过权限检查的详情接口 |
| 版本修订 | `MemoryService.revise()` 校验 `memory.edit` 后写入，repository 在同一事务比较 `expected_version` 并追加修订。当前 service 对 `system.manage` 加 `memory.edit` 有跨 owner 修订例外，`list/recall` 按本人查询。见 `memory/api.py:115`、`repository.py:104` | 新的本人详情与微信命令要显式限制当前 owner；存量管理写入口单独核对策略，新增入口不能继承跨 owner 例外 |
| 流式召回 | dispatcher 对 Web 和微信按本人检索，取最多 3 条、800 个估算 token 并拼入请求。当前路径只拼正文，没有保留所选条目版本用于该轮展示。见 `assistant/dispatcher.py:379`、`:410` | 在构造实际注入文本的同一位置生成回执，之后查询历史回执时无须重新召回 |
| 持久化与引擎 | Hermes Adapter 已用 `persona_context` 与 `context_prefix` 组装当前轮，并传原用户文本作持久化用途。见 `backend/runtime/hermes/adapter.py:341`、`:371` | 新功能主要属于 EasyChat 业务层；真实内核测试继续检查附加上下文和长期会话历史的边界 |
| 隔离 | `memories.scope` 已存在，`candidates()` 按 owner/status 查询，`find_active_content()` 按 owner/kind/content 去重。临时 SQLite 实测不同 `scope` 的相同正文得到同一条记录，默认召回可见 | 当前 `scope` 只是已有数据字段。角色私有记忆需同时覆盖查询、去重、后台写入和管理操作。见 `memory/repository.py:180`、`:205` |
| 遗忘 | `forget_memories()` 清空 `content` 并删除历史版本。临时 SQLite 实测 `source_refs[].quote` 仍留在被遗忘的行内。见 `memory/repository.py:263` | 来源详情和图谱上线前清除墓碑中的来源原文与不应保留的派生元数据，测试从写入到遗忘后的实际持久化结果 |
| 提取 | `remember_explicit()` 当前强制 `scope="user"`。微信直接写偏好和异步 `memory.extract` 均需参与范围决策。见 `memory/api.py:91`、`channels/api.py:711`、`memory/worker.py:193` | 角色阶段需要贯穿全部写入路径，后台 job 用本轮已解析的会话归属 |
| 当前人设 | `assistant_profiles` 以 `owner_id` 为主键，`/人设` 修改当前用户风格，dispatcher 按 owner 渲染。见 `0014_wechat_ac.sql:4`、`profiles/api.py:131`、`channels/commands.py:157` | 默认角色兼容已有偏好，新增会话选角色。时区、静默时段和渠道偏好继续按用户管理 |
| 微信会话与回执 | `channel_session_cursors` 每个渠道账号、外部用户和外部会话存一个当前 session，普通聊天结果和部分确认回执通过 session 反查微信路由。见 `0004_channels.sql:25`、`channels/repository.py:440`、`:490`、`channels/api.py:340`、`:389` | 切换会话时须保留旧会话的来源归属，否则在途 run 的确认或结果可能丢失回执目标（推断，待回归） |
| 重放与幂等 | 命令处理、缓存回复、更新 `processing_state` 分多步执行。见 `channels/api.py` 的 `handle_inbound()`、`replay_due_events()` | 新增修订属于持久写入。需覆盖“修订成功后、事件标记完成前崩溃”的重放窗口（推断，待故障注入） |

另有两个应在新增入口时处理的边界。`MemoryService.revise()` 当前只检查内容非空，创建记忆有 2000 字上限，建议新旧修订入口统一验证长度并保留真实来源。`MemoryView.vue` 目前直接渲染新增、修订、遗忘按钮，建议依据实际 `memory.view`、`memory.edit` 及 capabilities 分别展示读写动作。（源码核查与方案）

## 2. 用户交互

| 界面 | 操作 | 预期结果 |
|---|---|---|
| 微信 | `/记忆` | 查看最近摘要，带短 ID 与版本。支持既有帮助和该渠道的输出上限 |
| 微信 | `/记忆 <短ID>` | 查询本人可见条目，返回正文摘要、版本和经过裁剪的来源类型及日期 |
| 微信 | `/纠正 <短ID>@<版本> <新内容>` | 明确目标和版本后执行修订。仅给 ID 时先回显当前版本及完整指令，歧义时提示输入更长 ID。可以粘贴含空格和换行的新内容 |
| 微信 | `/本轮记忆` | 展示当前会话上一条已完成回答的召回记录，返回选择时版本。支持进一步指定本会话的短 run ID，服务端验证归属 |
| 微信 | `/星图` | 返回已有可信 Web 基址上的登录链接。基址未配置时给出 Web 菜单路径。链接只含定位参数 |
| 微信 | `/角色`、`/角色 <名称>` | 列出可用角色，选择后恢复该角色在此会话来源下的后台会话，同时显示角色与默认记忆范围 |
| Web | 记忆列表/图谱、回答详情、角色选择 | 共用详情、版本、读写权限与错误语义。无写权限时提供浏览，登录后可以按链接定位记忆 |

自然语言纠正可以后续转成候选与确认步骤。首版使用带版本的确定性命令，便于明确修订哪条记录，避免把普通讨论解释成写操作。（产品建议）

## 3. 阶段一 — 遗忘与微信修订

**修改位置**　`backend/modules/memory/api.py`、`repository.py`、`routes.py`，`backend/modules/channels/commands.py`、`api.py`，测试复用 `tests/memory/test_forgetting.py`、`test_revision.py`、`tests/channels/test_durable_intake.py`、`tests/contracts/test_wechat.py`。（方案）

- [ ] 在临时 SQLite 补回归。对带 `source_refs[].quote`、标签、修订和反馈的记忆执行遗忘，检查正文、版本和来源内容清理，并验证原消息重放不会复活记录。（可复验条件）
- [ ] 在同一短事务收集用于阻止重提取的来源/正文哈希，清空墓碑中的来源原文，删除关联版本及能复现内容的派生信息。写入新记忆时在持久化事务内重新检查遗忘规则，验证提取和遗忘并发时不会重新落入已遗忘的内容。以追加迁移或现有清理入口处理历史墓碑，先验证旧数据库副本。原始聊天记录及备份遵循其各自生命周期，产品文案明确说明遗忘范围。（方案）
- [ ] 增加 owner 限定的 service 查询，按规范 ID 前缀查询数据库，再判定 0、1、多条结果。已有 `/忘掉` 的最多 200 条扫描不适合作为新入口的统一定位策略。`GET /api/memory/{id}` 返回可访问的现行记录，修订历史按相同权限另行分页读取。已遗忘、权限撤销或角色范围变更时返回不可读。（方案，`channels/commands.py:202`）
- [ ] 新命令走 `MemoryService` 的实际读写检查。修订原因、微信事件来源、目标版本和成功结果由服务端记录。来源显示优先使用可验证的摘要，用户在 Web 手填的来源标为手动，原始消息跳转再次验证会话权限。（方案）
- [ ] 新增持久化修订操作去重，键以 `(owner_id, channel_event_id, action)` 为准。将修订 CAS 和操作回执写入同一事务。重放读取原操作结果，按当前可见性生成最小回执。成功后崩溃再处理时版本只增加一次，两个独立事件同时修订时旧版本冲突且保留输入。（方案）
- [ ] 检查 Web 记忆路线与动作的 `memory.view/edit`，保持原有路由兼容。增加明确的版本冲突、被遗忘、找不到和无权结果，并验证下次召回使用最新正文。（验收要求）

## 4. 阶段二 — 单轮召回记录与 2D 图谱

**修改位置**　`backend/modules/assistant/dispatcher.py`、`repository.py`、`api.py` 与 `routes.py`，`backend/modules/memory/repository.py`、`api.py`、`routes.py`，`agent_frontend/src/views/MemoryView.vue`、`ChatView.vue` 与现有消息组件。迁移使用实施时下一个可用编号，当前最高为 `0026`。（方案与磁盘核查）

- [ ] 新增按 run 保存的引用表，包含 `run_id`、`owner_id`、`memory_id`、`memory_version`、`position`、`created_at`。引用按 run 与条目去重，按顺序展示。索引覆盖 owner/run 查询及 memory_id 清理。正文、来源摘录、模型原始提示和微信凭据均由现有渠道与记忆域持有。（拟定数据契约）
- [ ] 把记忆段和引用从同一组已选条目生成，记录于真正交给 `ExecutionRuntime.execute()` 的请求边界。查询以 `已加入本轮请求` 为语义。若记录写入失败，聊天按现有降级策略继续，查询标记无法核实。旧 run 返回无记录，实际记录过的空集与旧 run 用明确标记区分，例如在 run 上存 `memory_context_recorded_at`。（方案）
- [ ] 返回本轮选中的版本，并按当前权限获取可展示的最新摘要。在记录已修订时标注旧版本，历史详情经授权后按需读取。已遗忘时移除对应引用或显示统一的不可用状态，测试身份撤销、迁移、旧版本及 SSE 重连。（方案）
- [ ] 通过已登录的 run 接口和微信 `/本轮记忆` 读取同一结果。微信基于绑定与会话选最近完成 run，Web 用明确 run ID。用户并发发送、会话切换、有失败或取消 run 时都只能看到正确关联。（验收要求）
- [ ] 从现有记忆管理页增加 2D 视图，使用本人可见记录和已存的类型、标签、记忆归属及明确存在的修订/替代关系。图按稳定顺序布局，默认仅加载当前筛选的一页节点，沿用列表选择与详情。为移动端、键盘和低性能环境提供同等列表操作。（方案）
- [ ] 前端验收覆盖从聊天召回记录点击定位、搜到同一条、修订后图更新、遗忘后节点与边消失、登录后返回定位、窄屏和键盘。UI 改动保存相同场景 Before/After。（验收与仓库要求）

图谱首版表示已知数据之间的关系，标签分组属于展示关系，来源与修订边属于可查证关系。若后续需要实体多跳召回，另行评估实体归并、边来源、时态与撤销传播。（设计选择）

## 5. 阶段三 — 会话角色与私有记忆

**修改位置**　`backend/modules/profiles/`、`assistant/`、`channels/`、`memory/`，相应追加迁移与 Web 角色入口。运行时沿用 `RuntimeRequest.persona_context`。相关受保护路径与公共契约依 `AGENTS.md` 准备草稿和升级简报。（方案与仓库规则）

### 5.1 数据与权限

| 数据 | 拟定约束 |
|---|---|
| 用户角色 | 独立角色表保存 `owner_id`、角色 ID、名称、版本、风格设定、状态。默认角色仍读取现有 profile 的风格；用户显式选择其他角色时使用角色快照。角色与授权角色的命名在 API 和界面上区分 |
| 会话绑定 | 会话持久记录 `persona_id`，已有会话的空值解析为默认角色。切换后创建或恢复另一会话，角色不同的 Hermes 历史持续独立。运行时按 run 或其固定会话解析角色归属，角色切换不会迁移在途请求 |
| 记忆范围 | 建议引入明确的 `namespace_kind` 与 `persona_id` 字段，并在 service/repository 执行，避免把既有自由文本 `scope` 当权限。范围为旧默认角色、账号共享、角色私有。若引入项目记忆，另行绑定真实仓库快照及授权 |
| 微信选中角色 | 保留当前游标用于表示活动会话，另保存微信来源到各角色/会话的映射，由服务端校验 owner、渠道账号、发送方与会话来源。回信从原 run/session 的来源查询解析，发送时重新核对绑定和有效投递上下文 |

**默认建议**　历史记忆继续由默认角色使用。新增角色默认只看本角色记录与用户明确标为共享的条目。由用户逐条或批量确认共享旧记录，迁移过程保留原 ID、原时间和版本。（待审阅的产品选择，可避免旧记录自动扩散）

### 5.2 落地步骤

- [ ] 以新表或追加列实现归属关系，使用 owner 和角色的组合约束。先验证旧数据迁移、所有旧记录的默认可见性，以及读取旧备份后的恢复。（步骤）
- [ ] 查询、候选数量限制、去重、替代、修订、遗忘、反馈、详情、图谱和 run 回执都使用同一范围口径。SQL 在 `LIMIT` 前过滤可见范围，防止不可见记录挤掉召回候选。针对相同文字跨角色写入、跨范围原样重放、跨范围替代、标签和来源链接分别回归。（步骤）
- [ ] 将角色范围贯穿 Web 明确记住、微信快速保存、后台 `memory.extract`、显式信号与后续管理接口。后台读取服务端的 run 归属，尊重当前用户权限与角色状态，模型只能提供候选正文。遗忘阻止重提取的规则至少维持现有 owner 级保护，若后续按角色拆分应作为独立语义变更。（步骤）
- [ ] 为微信切换增加来源历史映射，保证 `/新对话`、`/切换`、旧会话回看及编码任务回执兼容。活动游标和角色选择有一致的更新规则。用户 A 的旧微信来源重新绑定给用户 B 后，A 的在途回执必须 fail-closed。（具体回归）
- [ ] 入队时记录角色 ID 和角色配置版本，通过不可变版本或 run 内快照还原当时设定。会话绑定决定角色历史，已入队运行及其后台记忆提取按已保存的身份处理。归档后停止新运行，旧记录是否可管理按同一 owner 规则展示，保留明确的用户操作入口。（方案）
- [ ] 用两个角色分别写入互斥偏好，测微信 A→B→A 的历史恢复、角色私有记忆隔离、共享记忆可读、旧 run 经重启后仍写入正确范围、权限撤销后查询和投递被拒绝。（验收要求）

## 6. DeepSeek Harness 选型

本阶段推荐继续使用 Hermes。当前 Web 和微信由 dispatcher 调用 EasyChat 记忆服务，既有 runtime 请求已有独立人格与上下文字段，需求的主要变化发生在产品侧。（源码推断）

若要评估 DSH 原生插件或编码能力，可以固定同一模型、仓库版本和任务，用独立 `CodingRunner` 候选比较。检查产物质量、工具授权、取消、会话恢复、凭据隔离、用量、依赖升级与回滚。表明收益且能通过现有契约后，再提出小范围切换设计。普通聊天的引擎替换还需另外验证旧会话可读与流式事件兼容。（方案）

参考项目分别提供图谱、单轮读写记录，以及独立记忆库。其设计可以分别采用。（设计依据）[RestRegular/dsh-memory](https://github.com/RestRegular/dsh-memory) · [dsh-mnemon](https://github.com/omdsh-dev/dsh-mnemon) · [Hindsight](https://github.com/vectorize-io/hindsight) · [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)

## 7. 验收与发布

```powershell
python -m pytest tests/memory tests/profiles tests/channels tests/contracts/test_wechat.py tests/contracts/test_web_chat.py tests/contracts/test_runtime.py tests/contracts/test_sse.py -q
python -m pytest tests/superagent tests/contracts -q
python -m pytest tests -q -m "not integration and not resources"
Push-Location agent_frontend
npm test
npm run type-check
npm run build
Pop-Location
```

- [ ] 每阶段先做定向回归，验证正确及拒绝路径。旧 SQLite 副本做追加迁移和故障恢复，保护路径按仓库规则处理，写事务内保持无外呼。（仓库要求）
- [ ] 使用模拟微信入站验证持久化、同事件重放、幂等和版本竞争。真实微信验收记录账号范围、来源会话、修订确认、成果及重复消息行为。（验收要求）
- [ ] 使用真实 Hermes 验证本轮请求中的记忆及角色提示，不因切换、重连或压缩把其他角色的上下文带进当前会话。Web 记录同场景 Before/After。（验收要求）
- [ ] 加法迁移分阶段发布，功能开关按仓库规则默认关闭。回滚先停止新增命令和角色创建，排空在途任务，核对数据后恢复匹配应用版本。角色私有数据上线后，旧版本若仍按 owner 全量召回，则回滚需恢复匹配快照或暂停记忆读写，直到范围隔离重新有效。（回滚要求，依据现有 owner 级查询）

建议首批交付范围是阶段一与阶段二的单轮回执。2D 图谱可独立上线，会话角色与历史记忆共享默认值在本设计确认后实施。（建议）
