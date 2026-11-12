# WP5/WP6/WP7 记录与最终汇总(2026-11-11)

## WP5 主管汇总（最小交付，已实施）

- `GET /api/superagent/tasks/{id}/brief`：只读聚合账本事实——任务状态/phase、PR、
  attempt 数与最新 checkpoint、未消费输入数、最新验收轮次、阻塞原因、**状态→下一步映射**
  （queued/running/waiting_input/blocked/failed/interrupted/succeeded/awaiting_review 十态）。
  归属校验复用 `_task_for`（跨用户拒绝有回归）。
- 微信聚合通知出口：**已有机制沿用**（communication 段"统一出口、进度不打扰、完成/阻塞才发"
  ——P6/WP2 记录），主管汇总以 brief 数据源回信，不新增第二条出口。
- 复杂需求拆解（父子任务/依赖/负责人/预算）：**设计待决**——按方案"按需求增量引入"。
  已固化设计要点：父传需求/约束/工件引用、子任务独立 attempt、服务端校验依赖环与
  授权继承（受限授权+总预算）、同仓并发先定义工作区/分支/集成顺序；触发条件：单任务
  反复打回≥2 轮或需求含多个独立可验收目标时由主管提议拆解，人工确认后创建。

## WP6 事件策略与远程执行（核查+设计，未新增代码）

- 事件策略现状核查（对照方案要求逐项）：确定性命令(channels/commands)、绑定与重复事件
  (UNIQUE 三元组+envelope)、机器人回声(协议层无入站回声，推断+阶段 F 观察)、webhook 规则
  (验签/去重/allowlist/bot 跳过/旧 head 忽略/P7 自动修复预算)——**全部已有实现与回归**。
  语义判断接收（自然语言受理）= 模型工具调用路径（P9 修复后工具已可见），超时/预算口径：
  attempt 墙钟 4h + 轮数预算（自动修复）；纯语义分类器（独立小模型判断层）未引入——
  记录为可选增强（判定不稳定时才需要），当前不上。
- 远程执行：**设计待决**。依据 P4 探测（编码会话同 OS 用户全文件可见），独立执行环境
  三候选（docker env_type/独立 OS 账号/WSL 发行版）与远程 Runner 设计要点（设备身份、
  任务凭据范围、租约、心跳、输入幂等、取消确认、工件上传、晚到结果拒绝、控制端持密）
  已写入 P4 记录 §2；触发条件：出现多设备/无人值守长任务需求，或越权风险实际发生时优先级提升。

## WP7 升级治理、全差异评审与回滚演练

### 版本与组合记录（本轮增量）

| 项 | 版本/来源 |
|---|---|
| EasyChat 分支/HEAD | feature/permission-remediation @ 64181f9（WP4 前端摘回后链） |
| 迁移链 | 0001–0025（0024 自动修复、0025 验收账本为本轮新增，均追加式） |
| 内嵌 Hermes | 0.19.0，**产品补丁 0**（P3 provenance 实测），5 文件复制期差异可重放 |
| 微信协议参考 | Tencent/openclaw-weixin @ 0ad1ae91347a（2026-11-11 固定） |
| Acceptance | lobehub/acceptance skill v0.10.0 @ f720feb862bd（Apache-2.0）；lh CLI 0.0.78 |
| 前端 | Vue/Vite，npm test 23、type-check 0、build ✓（退出码 0） |

### 全差异自评审（baseline 4d1c206 → 64181f9，8 提交逐 diff）

已当场修复的问题：①`__always_available__` 暴露缺口（P9 根因，架构级）；②webhook 通知
同秒 dedup 碰撞丢通知；③modal 窄屏滚动不可达；④Esc 无绑定；⑤**delivery 私引 channels
实现文件**（架构违规，tests 当时漏跑 architecture——教训已固化为 AST 回归）。
自评仍存风险（如实）：
- `acceptance_evidence_path` 的 resolve 校验依赖 `verification_ref` 目录存在；空验证任务
  （未配置验证命令）无工件根，证据预览返回 Forbidden——**已知限制**，前端将以错误提示呈现。
- `routes.list_acceptance` 在路由内做 JSON 解析（表现层组装）——可下沉 repository，非缺陷。
- `test_toolset_exposure` 对内核 `_HERMES_CORE_TOOLS` 私有变量的注入依赖内核未变签名；
  升级 Hermes 需同步（已在 P3 升级演练清单）。

### 回滚演练（步骤化，本轮完成书面演练；实际恢复已具 P1 DRILL_OK 能力）

1. 停止新任务派发：面板 Settings → enabled=false（或 API PUT）；
2. 在途对账：`scripts`/worker 无在途则跳过；有 running → 启动恢复语义标 interrupted；
3. 外部副作用对账：GitHub 分支/PR 用 gh-agent 按任务分支名核对（先查后建记录在 events）；
4. 代码回滚：revert 对应提交；0024/0025 为追加式新表/列，旧代码 `dict.get` 读列
   自动忽略——**无需数据回退**（单库升降级兼容已由 get 模式保证）；
5. 数据恢复：backup.py 一致性快照（P1 演练 DRILL_OK）+ 恢复前旧行改名保留；
6. 渠道默认关闭重启，人工核验后重新启用。

### 真实闭环现状（截至本轮）

- ✅ 微信受理（`/开发`）→ 工作区（git 代理生效，clone 成功）→ 编码执行 → 结果判定
  （no_changes 如实拦截模型的临时脚本假完成）→ 回执送达微信（delivery `sent`）；
- ✅ 验收打回 → 幂等输入 → 回队返工（真库联调，test_acceptance + 页面）；
- ⏳ "真实变更 → push → Draft PR"一步：模型质量为本轮观测到的剩余变量
  （no_changes 假完成 1 例），链路各环节已就绪（仓库已切 T-Rex05/EasyChat、
  push 凭据+代理就绪），续作条件：换用更强模型重发实单，或人工在面板重试并观察。

## 未验证项汇总（含续作条件）

1. 真实键盘 Esc/焦点圈（c6/c8 blocked）——真机浏览器一次按键；
2. 真实 GitHub Draft PR——环境就绪，待强模型实单；
3. 真实微信扫码全链（绑定已通；收发短消息/长任务结果/解绑分段演练）——需授权账号在线时段；
4. 远程执行/父子任务——设计待决，触发条件见 WP5/WP6 节；
5. Acceptance 云端发布——需 LobeHub 账号（本地模式零上传已验证）。
