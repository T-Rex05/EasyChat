# WP3+WP4 记录:生活页真实聚合与提醒管理(真实服务端联调)

日期 2026-11-12,基线 WP2(`1ce9faa`)。WP3(微信记录与生活页)与 WP4 客户端部分(提醒管理)合并记录;WP4 的后端增强按仓库规则单独成草稿文档等待人工决策,未改后端代码。

## 1. 交付物

- `core/network/LifeRepository`:schedules/memory/inbox/wechat 会话过滤(source=wechat)/bindings 聚合读取。
- `core/network/SchedulesRepository`:创建(at=ISO 本地时间文本 + timezone,WP0 核验 `_parse_at` 契约)、PATCH enabled、DELETE、occurrences 查看。
- `feature/today/TodayViewModel` + `feature/life/LifeViewModel`:各区块独立 BlockState(Loading/Ready/Error 含 403/503 标记),单区块失败保留其他区块并可重试(设计 §5.2)。
- `feature/today/TodayScreen` 真实化:称呼问候(真实用户名+时段)、「更新于 HH:mm」真实时间、今日安排(next_run_at 秒级 epoch → 用户时区「今天 23:41/周三 09:30」)、最近记下的事、微信对话入口(直达只读详情)。
- `feature/life/LifeScreen` 真实化:三分区(日程/记下的事/收藏)真实列表;记忆显示偏好/重要的事/生活信息分类与「你确认过的记录/小暖整理的」状态;收藏显示标题/域名/时间;厨房预留入口。
- WP4 提醒管理:新建表单对话框(标题/说明/日期/时间 + 自然语言复述「记好后,会在 明天 09:30 通过微信提醒你」)、详情对话框(下次提醒「预计提醒」文案、投递渠道、最近触发实例 with pending/queued/missed 状态)、暂停/恢复(PATCH enabled)、删除(二次确认)。
- `core/storage` 优化:token 与 baseUrl 进内存缓存,请求路径零阻塞(不再 runBlocking DataStore/Keystore;冷启动由 XiaoNuanApp 预热一次)。

## 2. 真实联调证据(`docs/superpowers/specs/assets/android-wp34/`)

测试数据经真实 API 为 `xiaonuan_test` 创建:once 日程「取快递」(email 目标)、preference 记忆「晚饭喜欢清淡一些」(user_confirmed)、收藏「腌笃鲜的做法」。

| 截图 | 场景 |
| --- | --- |
| wp3_01_today_real.png | 今天页:真实用户名/更新时间/今日安排(epoch 转换「今天 23:41」)/真实记忆 |
| wp3_02_memories_real.png | 记下的事:真实记忆 + 分类标签 + 确认状态文案 |
| wp3_03_schedules_real.png | 日程:真实计划「周三 23:41 取快递 · 一次 · 已暂停/已启用」(once 过期后服务端停用如实呈现) |
| wp3_04_bookmarks_real.png | 收藏:真实 inbox「腌笃鲜的做法 · xiachufang.com · 22:39」 |
| wp4_01_new_reminder_form.png | 新建表单:字段 + 自然语言复述 + 「记好」禁用态 |
| wp4_02_no_binding_error.png | 验收场景「没有微信绑定」:服务端原文错误「没有可用的微信绑定,请先绑定渠道或提供邮箱目标」+ 表单草稿保留 + 其他区块不受影响 |

构建:`assembleDebug testDebugUnitTest` BUILD SUCCESSFUL(13 项单测,新增 SchedulesRepository 后全绿)。

## 3. 联调中发现并修复的问题(每条带证据)

1. **`at` 字段契约**:误发 epoch 秒,服务端 422「at 不是合法 ISO 时间」(`scheduling/api.py::_parse_at`)→ 改为 ISO 本地时间文本 `yyyy-MM-ddTHH:mm:ss` + `timezone` 字段。设计文档 §7 表格仅写「按 ScheduleCreateBody 发送字段」,实施时补齐了精确格式。
2. **并发区块竞态(关键修复)**:三区块并发加载时 `_state.value = _state.value.copy(...)` 的 receiver 在 suspend 挂起**前**捕获,恢复后用旧快照赋值,互相回滚——表现为「请求全部成功(日志 200/231ms)但 UI 永远 Loading」。修复:suspend 调用移出 copy 参数,统一 `MutableStateFlow.update {}` 原子更新。证据:logcat `XnHttp call done GET /api/memory 201ms` 与 UI 状态矛盾 → 修复后三分区稳定显示(wp3_02/03/04)。
3. **请求路径 runBlocking 阻塞**:buildRequest 每次 `runBlocking{ DataStore+Keystore }` 造成主线程 jank 与偶发悬挂 → token/baseUrl 内存缓存化,请求路径零阻塞。

## 4. 验收对照(设计 §10 WP3/WP4)

| 验收目标 | 结果 |
| --- | --- |
| 聚合微信会话/schedule/memory/inbox,完成今天与生活页 | 完成(wp3_01~04);微信会话经 source 过滤,直达只读详情 |
| 微信产生记录后 App 主动刷新可见 | 刷新按钮 + 下行链路就绪;微信端产生记录的端到端见 §5 遗留 |
| 退出换账号隔离 | session epoch 机制就绪;双账号实测见 §5 遗留 |
| 列表分页 | history offset 分页已接;schedules/memory 默认上限 50 条按服务端契约,超出部分 WP5 契约草稿 |
| 明确表单创建、暂停恢复、删除、occurrence 查看 | 完成(表单+详情对话框);无绑定错误路径实测通过 |
| 响应丢失确认流程 | WS 阶段:创建成功以「重新读取列表」为准(已实现 loadSchedules);幂等契约缺失(无 request_id)按设计 §8.1 先查询核实,WP4 契约草稿一并提案 |

## 5. 遗留项(记录,不阻塞交付评审)

1. **微信端到端联动实测**需要已绑定微信的家用账号(本环境无微信渠道账号),WP5 真机阶段执行;客户端读取链路已用 API 直建数据验证。
2. **双账号隔离实测**:机制就绪(epoch 自增 + 退出清凭证),实测步骤与截图在 WP5 真机阶段补。
3. **删除同步/暂停后 Today 页即时刷新**:Today 页与 Life 页各自独立刷新,跨页即时同步留待缓存层(Room)统一。
4. 模拟器时间跳跃(宿主睡眠)曾造成 once 日程过期——服务端行为符合预期,无客户端问题。
