# P7 记录:GitHub 反馈校验与有限自动修复(2026-11-10)

## 1. 验证层:已有且验证通过(实测 10 项 webhook 回归全绿)

| 要求 | 实现证据(webhooks.py) |
|---|---|
| HMAC 验签,缺配置拒绝 | `verify_signature` 常量时间比较;secret 或 header 缺失→False→403(routes 层)(test_signature_verification) |
| delivery_id 去重 | UNIQUE 索引 + `ON CONFLICT` 语义 + job dedup_key=`webhook:{delivery_id}`(test_ingest_dedups_and_allowlists) |
| 仓库 allowlist | `_repo_allowed` 对 settings.repo_url_snapshot 全名匹配(不相关仓库 no_task/拒绝) |
| PR/head 关联 | `_find_task`:PR body `EasyChat-Superagent-Task` 标记优先,repo+pr_number 反查兜底;`_head_belongs_to_task` 乱序防护(test_bot_and_stale_head_are_ignored) |
| bot 跳过 | `sender_is_bot`(App 类型或 [bot] 后缀)→bot_skipped |
| 反馈→原任务输入 | 评审/评论 `_append_input`(状态白名单 waiting_input/blocked/failed 回队;succeeded/awaiting_review 仅存输入)——与本轮 auto_fix_requeue 状态集**互斥不相交**(实测源码),无双重入队 |
| 旧 SHA 反馈不覆盖 | stale_head_ignored;PR closed 双 outcome(merged/closed_unmerged)各有回归 |

## 2. 确认缺口与实施:有限自动修复(接管指令 P7 明列;此前"规则暂缓")

**开关与预算(全部默认关闭/最保守)**：
- 迁移 `0024_superagent_auto_fix`(追加式,三条 ADD COLUMN):settings.auto_fix_enabled **默认 0**、auto_fix_max_rounds **默认 1**(部署级硬上限 MAX_AUTO_FIX_ROUNDS=5)、tasks.auto_fix_rounds 默认 0。
- 触发条件全满足才入队:开关开 **且** 非 legacy(无仓库快照) **且** 任务 ∈ {succeeded, awaiting_review} **且** 轮次 < 预算;预算耗尽 CAS →blocked + 通知;任何不满足保持原"报告+人工"行为(默认态行为与旧版逐字节一致,既有 CI 回归不动)。
- **人工暂停保护**:cancel_requested/cancelled 不在状态白名单——自动修复不能复活人类按停的任务(bot 反馈同理不能解除,继承通信规则)。
- 修复输入:`[自动修复] CI 失败(head,check):最小修复使检查通过,不扩大范围`(复用原任务/分支,attempt+1)。
- 墙钟:继承 attempt 级 run_timeout(4h,P4 口径);**token 无硬上限如实声明**(内核无 per-request 回调,口径=轮数×墙钟;P4 记录 §1)。

**修复的一个既有缺陷**:webhook `_notify` 用 `utc_now_iso()` 秒级时间戳做 dedup_key——同一事件内两条通知(❌CI 失败+🔁自动入队)同秒必碰撞(delivery `enqueue_in_transaction` 对同键返回既有行、不新建)。新增 `key_hint` 参数(af-q{轮次}-{head12} / af-b{轮次}-{head12}),其余调用保持原行为(时间戳键现状不变,登记:跨秒才独立,理论碰撞面仍存在于旧路径)。新回归断言**双通知各自成行**。

## 3. 新增回归(tests/superagent/test_webhooks.py,3+1)

1. enabled→终态任务 requeue:queued+rounds=1+修复输入+**两条 deliveries 行**;
2. 预算耗尽→blocked+仅一次迁移(CAS)+不新建轮;
3. cancel_requested→不触活(auto_fix_rounds 保持 0,行为=ci_failure_reported);
4. (强化)默认关闭:既有 test_check_run_failure_on_known_head_reports 原样通过(默认零行为变化)。
迁移清单同步 test_migration_0014(+0024 checksum 断言)。实测:webhook 套件全过、superagent+contracts 75 passed、全量见本包末尾记录。

## 4. 待办与未验证

- **设置 UI**:SuperagentView 配置面板尚无自动修复开关字段——归 P8(浏览器验收+Before/After 纪律);API 已就绪(GET/PUT /settings 含两字段,契约 test_superagent_api 扩展留 P8 一并做)。
- 真实 GitHub webhook 投递(签名+断连重投):环境阻塞,阶段 F 用已授权测试仓库演练(P9)。
- 自动修复的修复质量本身(模型改动能否让 CI 转绿)不在本轮验收——本轮验收=边界与预算。

## 5. 回滚

revert 实施提交即可;0024 迁移为追加式,旧代码 `get_settings` 用 `d.get` 读列——回滚后 0024 列被忽略,无破坏(rollback 演练列 P9)。
