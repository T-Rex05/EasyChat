# EasyChat 架构与工程规范

日期：2026-11-03。用途：提供给实施模型的目标设计；不是对现有代码状态的描述。工作目录固定为 `E:\PythonCode\EasyChat`，`E:\PythonCode\AgentForge` 是只读来源。

阅读顺序：交接入口 → 本文 → 实施计划 → 源码定位。需求以用户已确认范围为准，早期个人助手讨论稿中与本文冲突的建议不再采用。本文中的接口、路径、表名是目标设计；不得因为文件尚不存在就误判为遗漏。

## 1. 确定的目标与不做的事

保留：Hermes、微信 iLink、多端接入、Web/SSE、完整RBAC、用户与角色管理、Token排行榜、个人技能、定时提醒、邮件/PDF按需能力、最小运行证据、事实/事件/经验记忆、自进化。

删除：本地KB/RAG/GraphRAG及评测、向量与图存储、技能社区和上架审核、论文复现、Text-to-SQL及其专用平台能力。部门功能尚未被用户批准删除，首版保留其现有行为和数据字段，不借精简RBAC删除部门。企业数据层中仅服务本地KB的部分随KB移除。

目标部署：单机、单应用worker、SQLite，无MySQL/Redis/Neo4j/Milvus等必需服务。WeKnora通过远程协议访问，可以同机或异机。助手常态RSS低于1GiB是验收目标，PDF/脚本子进程及同机WeKnora另测峰值，不预先宣称达标。

不引入微服务、分布式队列、通用插件平台、双数据库引擎兼容、泛型Repository框架或第二套Agent引擎。不重写Hermes完整内核，不在后台自进化中修改服务源码、权限、迁移和部署配置。

## 2. 架构决策与依赖方向

采用**按业务能力组织的模块化单体**。Module拥有业务行为与数据；Interface是调用者需要知道的完整契约，包括授权、顺序、失败、成本和副作用；Adapter负责跨真实Seam的转换。深模块应隐藏复杂业务，不能只是逐层透传参数。

| 决策 | 选择 | 原因及约束 |
|---|---|---|
| A01 | 一个应用进程、显式装配 | 减少常驻资源，避免多个监听器和调度器重复消费 |
| A02 | 每个业务模块拥有自己的表和写入口 | 改动集中；其他模块不能直接操作它的SQL |
| A03 | `app.db` + Hermes `state.db` | 应用状态与引擎历史职责分离；不假装支持跨库事务 |
| A04 | 在真正变化的位置放小接口 | Runtime有Hermes与测试替身，投递有微信/邮件；SQLite暂不套数据库引擎抽象 |
| A05 | 统一执行入口 | Web、微信、定时任务不各写一套模型调用、记忆和权限 |
| A06 | 一个后台工作调度器 | 记忆整理、进化、报告使用有界任务，不叠加旧Dreaming和多套Curator |
| A07 | 用量记录是统计权威，Trace是排障投影 | 避免多观察器重复累计和清理Trace导致排行丢失 |
| A08 | 版本内容不可变、激活指针可切换 | 技能更新可验证、可比较、可原子回滚 |
| A09 | 首版保留现有HTTP/SSE契约 | 不在存储重构时同时强制前端全面改协议 |
| A10 | 先恢复可用闭环，再删除旧实现 | 任何阶段都能清楚说明哪些入口可用，不能吞异常假装成功 |

依赖规则：

```text
HTTP/微信/定时触发 → 对应模块公开Interface → 领域规则/本模块Repository
                                     → 必要的Runtime/投递/Runner Adapter
bootstrap → 显式构造所有模块并注入依赖
所有模块 → 小型shared值对象与错误定义
业务模块 → platform/sqlite、后台队列的公开实现
Hermes第三方实现 ← 仅runtime/hermes及经说明的兼容桥接访问
```

跨模块只能导入公开 `api.py` / `contracts.py`，不能导入另一个模块的repository、私有函数或路由。数据库外键可以跨表域引用，SQL业务写入权仍归表的拥有模块。确需跨模块原子操作时，由bootstrap装配的窄协调函数持有同一SQLite事务，模块仍提供自己的写操作；不能因此创建通用工作单元大框架。

## 3. 目标目录与职责

下列结构按任务逐步建立，不先批量创建空文件。每个模块有足够行为时才拆子目录；不要求所有模块都有相同层数。

```text
main.py                             # 兼容启动入口，只调用app工厂
backend/
  app.py                            # create_app：构建路由/中间件，导入不启动网络或迁移
  bootstrap.py                      # 配置、依赖构造、lifespan启停顺序
  shared/
    context.py                      # Principal、ExecutionContext；无全局当前用户变量
    errors.py                       # 少量跨模块错误码
    identifiers.py                  # run/session/call等ID构造与校验
  platform/
    sqlite.py                       # 连接、事务、PRAGMA、忙重试，不含业务SQL
    migrations/                     # 版本化SQLite schema及种子
    jobs.py                         # 小型持久任务队列、lease、重试，不含学习算法
    settings.py                     # 强类型配置与能力开关，显式加载
  modules/
    access/                         # 登录、RBAC、角色/用户/部门、资源授权规则
    assistant/                      # 会话、run生命周期、调度、事件、业务对话投影
    channels/                       # iLink协议、扫码、绑定、账号、入站归一化
    memory/                         # 事实/事件/经验、提取、召回、纠正、遗忘
    skills/                         # 个人技能资产、候选版本、激活、pin/归档
    evolution/                      # 证据→候选→验证→采用；不直接写技能文件
    scheduling/                     # 提醒和定时触发；调用assistant与delivery公开入口
    delivery/                       # 目标、产物、分块、微信/SMTP投递与失败恢复
    usage/                          # 调用计量、日汇总、排行榜与最小Trace
    models/                         # 模型配置、主/辅助/备用选择与调用上下文
  runtime/
    contracts.py                    # ExecutionRuntime Interface
    hermes/
      adapter.py                    # 唯一Hermes整合入口
      sessions.py                   # state.db映射与恢复
      tools.py                      # 工具列表/运行时权限/结果回传
      memory_bridge.py              # Hermes MemoryProvider到memory公开接口
      skills_bridge.py              # Hermes技能读写到skills公开接口
      usage_bridge.py               # Hermes真实请求与统一call_id关联
  integrations/
    mcp.py                          # 复用Hermes MCP能力的窄配置/结果适配
    pdf.py                          # 可选渲染器的资源限制与产物输出
    script_runner.py                # 受限执行器，不能被当作领域规则层
  hermes/                           # 现有内嵌依赖，最小必要补丁
  controller/、service/、db/等        # 过渡入口；按任务迁出，最终删除无调用者的旧实现
agent_frontend/src/                 # 保留现有Vue工程，按功能收敛
tests/{architecture,contracts,access,assistant,memory,skills,evolution,usage,delivery,storage}/
```

`shared`只容纳两个以上模块真实共享且稳定的值对象；禁止把业务规则搬入 `utils.py`、`common.py` 或 `manager.py`。不为每个数据类创建文件，不用文件数量证明架构质量。

### 3.1 模块公开Interface与数据归属

| Module | 调用者能做什么 | 拥有的数据 | 可以依赖 |
|---|---|---|---|
| access | 认证、解析可信Principal、授权、用户/角色管理、失效授权缓存 | 用户/角色/权限/部门 | sqlite、配置 |
| channels | 账号绑定、归一化入站消息、iLink生命周期 | 账号/绑定/游标/接收事件 | access公开接口、assistant入口 |
| assistant | submit/events/cancel、会话列表与运行状态 | 会话/run/业务对话/用户附件元信息 | access、models、memory、skills、usage、runtime |
| models | 取聊天或辅助配置、读取凭证引用、报告可用状态 | 模型配置/版本 | access、sqlite；不反调assistant |
| memory | recall/remember/revise/forget、来源验证 | 记忆/标签/修订/反馈/遗忘规则 | access、受控模型调用、来源读取接口 |
| skills | 列表、读取有效版本、提出候选、激活/回滚 | 技能/版本/内容指纹/激活指针 | access、文件产物存储 |
| evolution | 排队学习、评估候选、批准范围内自动采用 | 学习证据/实验/评估/预算 | memory、skills、runtime实验接口、runner、usage |
| scheduling | 建立/修改提醒、恢复时间触发、生成执行请求 | 定时计划/触发实例 | access、assistant、delivery |
| delivery | 准备产物、投递/重试/查询状态 | 产物/投递/分块尝试 | access、渠道发送Adapter、SMTP/PDF |
| usage | 记录真实调用、查用量/排行、写最小Trace | 调用明细/日汇总/Trace | access、sqlite |

assistant完成run后，通过注入的回调向evolution入队，避免assistant与evolution循环导入。memory的来源读取同样注入小型函数，不能反导assistant的repository。公共返回值是类型化值对象，不返回数据库cursor、连接或Hermes Agent实例。

## 4. 执行契约：一个入口，多种渠道

以下代码用于固定目标Interface，不是要求复制空壳后即算完成。类型定义在文中指定路径，所有调用者遵守同一命名。

`backend/shared/context.py`：

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Principal:
    user_id: int
    role: str
    permission_revision: int

@dataclass(frozen=True, slots=True)
class ExecutionContext:
    run_id: str
    session_id: str
    principal: Principal
    source: str  # web / wechat / schedule / memory / evolution
    channel_account_id: str | None
    model_profile_id: str
    policy_revision: int
```

Principal由Web登录或渠道绑定产生，外部请求和工具参数不能指定任意owner。快照不等于永久授权：排队后开始执行、重要工具调用、后台任务重试时重新校验有效用户、授权版本及资源归属。权限被撤销时，取消后续有副作用步骤，不能撤销已完成的外部操作。

`backend/modules/assistant/contracts.py`：

```python
from dataclasses import dataclass
from typing import Mapping
from backend.shared.context import Principal

@dataclass(frozen=True, slots=True)
class RunCommand:
    principal: Principal
    session_id: str
    source: str
    client_message_id: str
    text: str
    attachment_ids: tuple[str, ...] = ()
    channel_account_id: str | None = None

@dataclass(frozen=True, slots=True)
class RunReceipt:
    run_id: str
    session_id: str
    state: str
    duplicate: bool

@dataclass(frozen=True, slots=True)
class RunEvent:
    run_id: str
    seq: int
    kind: str
    payload: Mapping[str, object]
```

`Assistant.submit(command) -> RunReceipt` 为async：校验身份和会话、持久化接收/去重/入队后返回，不等模型完成。重复请求返回相同run，不重跑工具。

`Assistant.events(principal, run_id, after_seq=0) -> AsyncIterator[RunEvent]`：验证owner/管理权限后订阅；断开订阅不取消run。`Assistant.cancel(principal, run_id) -> bool` 为async且幂等：请求取消，响应表示已接受请求，不宣称在执行的同步工具已被强行终止。SSE环形缓存失效时发明确的resync信号并提供持久最终状态，不从头重新执行。

稳定内部事件至少包含 accepted、queued、started、token、tool_started、tool_finished、stream_reset、completed、failed、cancel_requested、cancelled；seq在单run内单调递增。公开Web事件名/字段按原SSE契约适配；内部新增事件不自动暴露敏感工具内容。token可合并发送，不逐token写SQLite。

会话必须先由可信用户创建或解析；run中记录输入摘要与附件引用。同一会话不同输入排队执行；Web若原契约对busy返回冲突，可以在HTTP适配层保留该响应，微信使用有界队列。全局run容量与忙响应明确配置。

### 4.1 Runtime Seam

`backend/runtime/contracts.py`：

```python
from dataclasses import dataclass
from typing import AsyncIterator, Mapping, Protocol
from backend.shared.context import ExecutionContext

@dataclass(frozen=True, slots=True)
class RuntimeRequest:
    context: ExecutionContext
    text: str
    attachment_ids: tuple[str, ...]
    system_context: str
    allowed_tools: frozenset[str]
    skill_versions: tuple[tuple[str, str], ...]

@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    kind: str
    payload: Mapping[str, object]

class ExecutionRuntime(Protocol):
    def execute(self, request: RuntimeRequest) -> AsyncIterator[RuntimeEvent]: ...
    async def cancel(self, run_id: str) -> None: ...
    async def aclose(self) -> None: ...
```

这是合法Protocol声明，不是待填的实现。Hermes Adapter负责线程/回调转换、会话历史、内部工具格式和错误映射；业务层不知道Hermes模块导入路径。工具实际分发仍须经过当前能力策略，不能只在schema列表里隐藏。

Runtime缓存键至少包含owner/session、模型配置版本、权限/策略版本、技能有效版本摘要。缓存大小与闲置时间受限，不能复用另一个用户或旧权限下的Agent。活跃实例不被LRU回收；失效后下一轮重建，已发生的调用不重放。桥接临时ContextVar用token/reset且传播到工作线程，显式ExecutionContext仍是权威。

## 5. 持久状态、事务与恢复

### 5.1 单一数据权威

- `app.db`：身份授权、业务会话、运行、渠道、投递、记忆、技能元数据/版本、后台队列、用量和提醒。
- `state.db`：Hermes完整消息和工具历史、引擎压缩状态。通过 `(owner_id, app_session_id, hermes_session_id)` 显式映射，不能根据可猜测的外部昵称直接复用会话。
- 文件：附件、报告、技能不可变版本内容；数据库存artifact引用、指纹、归属和生命周期，不复制大块base64。
- `conversations`是UI投影，不再作为第二套模型历史，不能先从UI记录恢复后又加载state.db造成重复上下文。

默认从新的app.db起步，不自动导入旧MySQL、复杂记忆或知识库数据。本文“历史任务兼容”指保留既有任务字段/格式语义，并用脱敏fixture验证；若用户另外要求导入真实历史数据，作为明确的一次性离线导入任务单独验收，不在启动时读取旧服务。

### 5.2 表域与关键约束

表名能复用现有业务语义时保留，迁移文件固定目标列和约束，不能散落在各请求路径临时建表。

| 表域 | 最少字段/约束 |
|---|---|
| users/roles/role_permissions/user_permissions/permission_defs | 保留用户名、状态、角色与toolsets、grant/revoke；用户名/角色名唯一，授权组合唯一；现有部门字段/表保留 |
| channel_accounts/channel_bindings/channel_events | account与platform；binding唯一(platform, account_id, external_user_id)；事件唯一(platform, account_id, external_event_id) |
| sessions | owner_id、source、channel_account_id、external_chat_id、hermes_session_id、active状态、时间；不可修改owner绕过隔离 |
| runs | owner/session、source、client_message_id、status、input/artifact_refs、started/finished_at、error、runtime_checkpoint；唯一(owner_id, session_id, source, channel_account_scope, client_message_id) |
| conversations/attachments | run关联唯一或明确每轮顺序；附件路径/大小/MIME/hash/owner；列表分页索引 |
| memories/memory_revisions/memory_tags/memory_feedback/forget_rules | kind、content、source_refs、event_at/recorded_at、scope、version、status、pinned、supersedes；反馈按source_event+memory幂等 |
| skills/skill_versions | owner、name、origin、pinned、active_version；版本不可变，version_id/hash/parent/evidence/validation，唯一(skill_id, version_id) |
| evolution_runs/evolution_evaluations | owner、证据run、候选/基线版本、预算、结果和采用原因；同一信号去重；不能把“缺少验证”存为passed |
| jobs | kind、dedup_key、owner、payload_version、payload、state、available_at、lease_until、attempts、last_error；dedup_key按业务唯一 |
| scheduled_jobs/scheduled_occurrences | 计划、时区、目标、格式、owner；每计划的scheduled_at唯一，用于重启去重 |
| artifacts/deliveries/delivery_parts | artifact内容地址/hash/owner；delivery引用run/目标/产物/发送状态；分块序号唯一 |
| llm_calls/daily_user_stats | call_id主键、owner/source/run、provider/model、原始usage+规范化字段、quality、时间；汇总唯一(stat_date, user_id, source) |
| model_configs/app_settings/schema_migrations | 模型和密钥引用、配置版本；migration版本和checksum唯一；不保存明文密钥到可公开字段 |

SQLite的唯一键中可空列不能直接承担幂等：`channel_account_scope`使用明确的非空规范值（例如Web用空串），其他可选键同样规范化或采用恰当的部分唯一索引；测试必须覆盖无渠道账号的Web重复提交。

时间统一以UTC存储，UI和日统计按显式项目时区转换，初始 `Asia/Shanghai`。时区是统计规则的一部分，改变规则必须重算对应日汇总，不能混合不同规则的数据。JSON写入先序列化验证，不能把Python对象repr当JSON。

### 5.3 事务与状态机

`runs`：queued → running → completed / failed / cancelled / interrupted；running可先进入cancel_requested。只有运行模块可推进状态，更新以旧状态为条件，不允许cancelled再覆盖成completed。

`jobs`：pending → leased → succeeded / retry_wait / failed / cancelled。SQLite短事务认领任务并写lease；执行期间不持连接/写锁。重启后仅重新认领lease过期且可重试的任务。进程内写串行化只覆盖本进程，SQLite busy timeout及短事务仍必需。

`deliveries`：pending → sending → sent / retry_wait / uncertain / failed。生成结果与投递请求先持久化，再尝试发送。发送确认丢失且平台不支持幂等时进入uncertain，不能假装发送必达或盲目无限重发。

`skill_versions`：draft → validating → validated / rejected；通过基线门槛后，用条件更新切换skills.active_version。验证结束后若父版本或权限已变，不覆盖新版本，重新比较或标记stale。文件先写不可变路径并校验hash，再提交元数据；中断留下的未引用文件由延迟清理，不覆盖有效文件。

双库之间不做伪事务：创建run先落app.db，再运行引擎；完成后写结果投影与投递/学习job。同库完成状态和这些job可原子提交。若引擎结束但应用投影失败，保留可查checkpoint，重启标interrupted并对账；禁止自动再次执行可能有副作用的工具。任何“自动恢复”都需说明恢复的是投影、投递还是任务本身。

### 5.4 SQLite实现要求

使用标准库sqlite3，参数化SQL；每个操作在工作线程内创建/关闭连接，不跨线程无锁共享。平台模块统一配置foreign_keys、busy_timeout及受支持的journal模式，检查实际SQLite运行时和Hermes已有WAL兼容检查；版本选择和PRAGMA需在锁依赖任务中核实。

写事务短小，不跨await，不含LLM/SMTP/MCP/PDF/脚本。不能通过 `check_same_thread=False` 掩盖并发所有权；不能用捕获所有SQL异常后返回空列表伪装数据库可用。迁移在启动就绪之前执行，失败明确终止启动；备份用一致性备份接口，恢复演练包含两库和产物。

## 6. 权限、模型调用与工具策略

RBAC精确保留：super_admin取得已注册有效权限全集；其他用户有效权限为 `(角色权限 ∪ 用户grant) − 用户revoke`。角色toolsets仍源自角色配置，不能因为重构将全部用户升级成管理员。缺失/损坏toolset配置不授予工具。

授权决策分为身份有效性、操作权限、资源归属及渠道能力。原实现对具有manage权限的管理者允许跨owner操作，这一能力保留，不将所有管理请求强行限制为本人。缓存有界且按user/角色版本失效，角色变更须失效其全部用户；禁用用户和解绑立即影响后续操作。

保持现有 `trace.view` 查看排行语义，不能悄悄改权限键或公开全部Trace。新增进化管理操作映射到明确注册的权限，迁移种子只给预期角色，不自动给所有既有用户。工具按具体操作声明权限；生成技能不能授权自己调用新工具。

models模块提供chat、auxiliary及可选fallback配置；配额、凭证引用及provider调用参数留在适配层。普通聊天、记忆提取、评估、回放全部带ExecutionContext；系统任务使用显式system主体，不猜测user_id=1。

MCP客户端复用Hermes，连接与工具目录有超时、上限、允许列表及凭证作用域。跨用户不共享权限更大的令牌。刷新失败保留上一次完整目录或明确不可用，不能使用半份schema。WeKnora故障是能力故障，不能使核心服务健康检查失效。

## 7. 统一计量与Token排行榜

每个真实出站LLM请求分配本地唯一call_id，重试请求是新的call_id，同一请求的observer回调重复不产生新计量。供应商request_id仅作为外部关联，不足以跨供应商做唯一键。run_id不是call_id，一轮可能有多次调用。

`usage.record_call(record)`是唯一计量写入口。Hermes和traced_llm各入口可产生通知，但必须汇入同一个call_id；迁移期间旧Trace observer不得再次直接累加daily_user_stats。未知usage可先记录，后续补全时同事务计算新旧差额更新汇总，不能先写NULL以后永久忽略，也不能每次UPDATE重复加总。

usage字段保留未知与估算标志，缓存/推理Token按provider规范统一映射，不能将其与已包含总量重复相加。供应商原始usage保存为受限JSON便于核对。用户排行以可解释的total_tokens汇总，来源显示chat/memory/evolution/schedule；后台改进成本归属发起用户。

日汇总和调用明细在app.db一个事务中提交。清理排障Trace不清理日汇总；若需要重建，明细保留范围必须覆盖重建区间，超出范围不能声称完整重建。缓存只是加速，不是唯一统计来源。

## 8. 记忆模块的行为规范

事实/偏好、事件、经验统一写单一SQLite模型，保留来源、适用范围、事件/记录时间、版本与用户确认程度；不做episodic/semantic跨库存储晋升。原始历史仍由state.db负责。

公开操作：`recall(context, query, budget)`、`remember(context, candidate)`、`revise(context, memory_id, expected_version, change)`、`forget(context, selector)`。每项均校验owner或管理权限，返回类型化结果、来源与裁剪原因；来源缺失不得补造经历。

召回先用owner、标签/别名、时间、状态索引获得有限候选，相关性优先，近期性与重要性辅助。首版初始candidate_limit=80、注入top_k=5、最多2000 tokens，可配置；明确询问旧事时包含archived冷记忆。关键词同义扩展和原始消息回查有独立预算，不承诺纯关键词能覆盖所有语义。

中文索引先用可测的关键词/别名/分词词项方案，FTS5存在时作为索引加速；默认tokenizer不等于中文语义检索，短词需要回退。不得将聊天原文/整库无上限发送给模型。

写入信号：明确记住/忘记、用户纠正、重要事件、阶段完成、任务反馈。普通聊天产生候选，不每条消息永久保存；假设场景/引用别人话不写成用户事实。提取任务去重，模型推断和用户确认分别记录；新指令按scope/time生效，不覆盖无关长期偏好。

忘记包括撤销可用记录、衍生摘要/经验处理和禁止重新提取规则。默认墓碑阻止旧消息重生；墓碑不保留用户要求删除的原文。原始历史与备份物理删除另按用户配置执行，界面明确遗忘层级，不宣称删除一行即清空一切。

首版不把检索曝光当奖励，不自动物理删除低分记忆，不建设共现图。后续强度维护只根据真实used/confirmed/rejected信号，并以last_decay_at增量衰减。画像和重要事实可以pin；不以情绪推断形成永久人格标签。

## 9. 技能、自进化与脚本

skills是技能内容与激活的唯一写入口；Hermes技能工具改为调用skills公开接口，而非旁路直接修改已激活文件。兼容期用明确桥接拦截写路径，验收覆盖前台skill_manage、后台review和文件编辑三条路径，不能只给Web编辑器加版本。

文件/终端/CodeMode/脚本等通用工具同样不能直接写不可变版本内容、active指针或生产受保护目录；编辑意图必须进入版本化提案。后台origin策略是额外能力约束，不因发起用户拥有terminal权限就绕过；受限Runner从操作系统/执行环境落实对应文件可见性与写权限，不能只靠提示词承诺。

evolution不直接写技能文件/授权表；流程为收集证据 → 形成经验 → propose版本 → 验证 → 比较基线 → activate或保留候选 → 观察/回退。用户手写/pinned资产只读，用户可显式转交管理；无法判断改进时不启用。

默认学习范围包括记忆、经验、技能、提示词片段和受限脚本。执行能力必须在预配工具/文件/网络范围内；服务源码、鉴权、权限策略、数据库迁移、部署配置仅产生建议。模型不能修改验证器、通过降低门槛实现“验证成功”。

验证要求：版本结构和schema检查、能力范围检查、与当前版本同任务比较、固定未参与生成的回归样例、指标与失败证据记录。输出更长/模型自评通过不代表效果更好。提示词候选同样不能绕开权限或隐藏用户已确认需求。

普通任务回放使用快照、替身或无副作用资源。投递/提醒创建/外部写MCP必须替换，不能多次真实发送。隔离runner有资源和能力策略；单独Python进程加AST过滤不构成完整隔离。在Linux启用受限runner或配置远程runner并通过负面测试之前，脚本仅能生成候选和静态检查，不标为执行验证成功。

初始自动学习预算：每用户每日20,000模型tokens、单次5,000 tokens/120秒、全局后台活跃任务1；这是可调整产品默认值，不是实测最优。不得透支前台run预算。请求发送前预留最坏允许输出预算，响应后按实际核销；超预算不发起下一步。主模型调用完成后才触发整理，不递归触发“学习自己的学习”。

Hermes background_review/Curator可复用整理策略，但写入统一走本模块；关闭重复自动触发，保留隔离用户会话、来源追踪、保护用户技能和归档恢复。Harness²首版不安装整套在线框架，离线适配是后续独立改进，不改变当前质量门槛。

## 10. 后台任务、提醒、邮件/PDF与资源预算

jobs只承担持久任务调度，payload带版本与ID引用，不存连接、模型实例、凭证或大附件。任务类型的handler由bootstrap显式注册，不依赖扫描全包。claim、lease、重试和关闭共享实现，业务重试条件留在各模块。

新提醒默认微信/文本，可选择邮件/PDF；历史任务保留原格式。schedule到期记录唯一occurrence，再调用assistant执行或投递预先确定内容；不会因重启补发同一计划多次。失败补跑策略与错过时间的处理写进设置，不默认重放无限历史。

报告生成与投递分开：PDF成功后产生不可变artifact，邮件失败只重试投递；不能重跑Agent生成另一份内容。SMTP按需读取受保护凭证，PDF按需加载已安装的可选依赖；能力被启用但依赖缺失时阻止相关任务并报告原因，普通聊天继续运行。

起始容量：foreground active=1、会话串行、等待run最多32、Runtime cache最多8且idle 15分钟、进程内事件缓存每run最多256帧/256KiB并取较小限制；短时token合并降低帧开销，完成run缓存5分钟。后台任务并发1，PDF/脚本重任务互斥，避免同时叠加多个渲染器/解释器。

前台优先是调度规则，不承诺抢断已经运行的同步线程/网络请求。后台每阶段边界让出，所有外部调用有超时；需要硬终止的PDF/脚本用可回收进程而非仅取消Future。反复超时进入失败/冷却，不无限生成僵尸线程。

启动：读取配置 → 版本化迁移/能力检查 → 构造模块与显式路由 → 恢复过期lease与interrupted状态 → 启动唯一调度器/微信监听 → 就绪。关闭：停止接收 → 停止认领后台任务 → 取消/限时等待run → 关闭Runtime/MCP/HTTP/进程 → 最终刷计量/状态 → 释放连接。整个流程幂等，异常仅在边界统一记录一次。

## 11. 错误、日志与兼容

跨模块错误保持小集合：unauthenticated、forbidden、not_found、conflict、invalid_input、busy、capability_unavailable、dependency_timeout、storage_unavailable、interrupted。业务层返回/抛出有明确语义的错误，HTTP边界映射401/403/404/409/422/429/503等；不能把所有异常转200空结果。

明确区分MCP无结果/连接失败/认证失败，邮件未发送/发送不确定，记忆未找到/来源不可读取。日志包含run_id/session_id/call_id/job_id等可关联ID，不写密钥、整段私密聊天或未经裁剪工具结果。支持调试内容采样并继承访问控制。

Web迁移使用已记录的144条静态路由装饰器作为定位清单，再与真实前端请求和新OpenAPI比较。只删除已确认移除模块的入口；兼容薄控制器不包含业务SQL、不导入旧全局mapper，迁移完成就清理，不无限叠包装层。

Vue按feature收敛API/状态与组件，保留TypeScript类型检查。不要在组件里做RBAC真实判定或直接拼接内部MCP凭证；菜单隐藏只是展示，服务器始终授权。删除图谱/论文视图前检查依赖图，再删除对应graphology/sigma/vue-flow等确实无调用者的包，保留技能编辑/PDF必要依赖。

## 12. 代码质量与持续演进要求

1. **显式依赖注入**：模块构造时接受依赖，业务函数里不随手创建网络客户端、读.env、扫描文件或创建线程；小型纯函数优先。
2. **导入无副作用**：import和create_app装配不自动连数据库/启动监听/播种技能；网络与迁移在显式lifespan阶段，工厂测试可注入临时存储与替身。
3. **类型化Interface**：公开函数有输入/输出/异常语义。未知外部JSON在Adapter边界验证并归一化，领域不传播无约束dict[str, Any]。
4. **模块拥有数据**：路由不得执行SQL；模块不得写其他模块表；去掉全局conversation_mapper、按线程名猜用户等隐式依赖。
5. **异步/线程边界清楚**：同步阻塞工作在受控线程/进程运行；ContextVar传播与reset有测试，取消不伪装成已停止。
6. **不靠monkey patch架构**：已有Hermes补丁逐条登记；先放Adapter/注入hook，确无扩展点才最小内核改动并补契约测试。不得继续把所有逻辑塞回hermes_adapter.py。
7. **控制变化范围**：不同时改格式、命名、存储与产品行为；每阶段提交一个可解释闭环，删除没有调用者的旧桥接。不凭文件行数拆成大量透传层。
8. **测试真实规则**：RBAC覆盖优先级和缓存失效，存储用真实临时SQLite，跨渠道用假网络/真业务；不只mock自己的repository来证明函数被调用。
9. **可复现依赖**：先核对Hermes支持的Python版本，再统一包元数据与锁定安装入口；保留一个实际使用的前端包管理锁文件，不能同时更新npm/pnpm两套结果。
10. **架构可机器验证**：tests/architecture用AST检查禁用import和循环依赖；路由不得导入pymysql/redis，业务不得越过runtime直接引用hermes内部。

文件超过约400～600行且包含多项责任时应检查拆分，行数不是自动失败阈值；新增超长模块必须解释原因。禁止新建一个统一Manager接受十几个万能依赖，也禁止每个表都建一套无行为Interface/DTO/Mapper/Service四层。

## 13. 验证、回退与交付门槛

测试分层：纯规则单元测试；临时SQLite集成；公开Interface契约；Web/微信/提醒到同一执行链的离线端到端；可选真实MCP/SMTP/PDF联调；Linux目标镜像资源与恢复验收。默认测试不读取真实.env、不连接真实服务、不发送消息。

必须覆盖：RBAC撤销和即时失效、未绑定微信、会话归属、重复提交含NULL账号情况、SSE续传、发送失败不重跑工具、两库中断、后台授权变更、用量晚到补全且不重复统计、中文旧事召回、遗忘不重生、技能激活并发与回滚、脚本越界/超时、邮件/PDF能力关闭与历史任务兼容。

默认留存建议：最终业务对话和日用量汇总不自动删除；详细Trace/工具产物30天、报告30天、失败实验产物7天，用户可改。显式用户删除优先；清理不得破坏pinned技能、active版本、未完成投递、记忆来源所需证据及正在运行任务。参考计数/保留原因可查询，不能盲目按文件mtime删除。

每阶段交付：具体改动、公开Interface变化、schema版本、删除范围、测试命令与实际结果、未验证项、回退步骤和下一阶段入口。没有真实连接时明确标注离线验收，不能把替身测试写成真实微信/邮件可用。

恢复：保留新仓库的阶段提交与备份；数据库升级前备份两库/配置引用/产物索引，不运行未经验证的反向DDL。失败时回到上一代码版本并恢复对应数据快照，不覆盖AgentForge旧数据，不双写旧MySQL。涉及真实秘密的配置不进入Git基线。

后续增加渠道只增加入站/投递Adapter；更换模型只改models/runtime适配；增强记忆召回只改memory内部；更换runner只跨runner Seam。若新增能力必须同时修改所有控制器或十几个跨模块SQL，说明本次Interface设计尚未达到目标。

| 后续迭代 | 预期主要改动位置 | 应保持不变的契约 |
|---|---|---|
| 增加飞书渠道 | channels新Adapter、delivery新发送Adapter、显式注册 | RunCommand、Assistant、记忆和用量规则 |
| 切换WeKnora版本/另一个MCP | integrations/mcp、凭证/工具配置及契约测试 | 核心run、RBAC、来源表示与失败语义 |
| 给记忆增加远程语义召回 | memory内部候选检索及来源/预算测试 | recall Interface、记忆数据权威和遗忘规则 |
| 换PDF渲染器 | integrations/pdf及产物/资源测试 | Delivery状态与邮件重试规则 |
| 增加进化评估指标 | evolution验证规则、固定回归数据 | 技能候选/版本/激活权限及回滚 |
| 采用远程Runner | runner Adapter与隔离契约验证 | 演化工作流、预算、受保护路径和结果状态 |

每次改变这些约定时在架构文档追加决策、原因、迁移影响和测试证据；不能为了“以后可能用”预先实现所有Adapter。
