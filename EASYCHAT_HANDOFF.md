# EasyChat 实施交接入口

最后更新：2026-11-03。给负责后续实现的模型/开发者使用。此文件是文档，不是运行脚本。

## 从哪里开始

工作目录：`E:\PythonCode\EasyChat`。原项目`E:\PythonCode\AgentForge`保持只读，不能在那里实施、清理或回退。

按顺序阅读：

1. [架构与工程规范](docs/superpowers/specs/2026-11-03-easychat-architecture.md)：模块职责、依赖、Interface、数据与状态、质量要求。
2. [逐任务实施计划](docs/superpowers/plans/2026-11-03-easychat-implementation.md)：从Task 0开始，四个里程碑与17项任务。
3. [源码定位与兼容基线](docs/superpowers/plans/2026-11-03-easychat-source-map.md)：关键文件/函数与144条静态路由装饰器；不是已核验的全部运行端点。
4. [已确认需求与调研背景](docs/superpowers/specs/2026-11-03-easychat-design.md)：功能取舍、用户图片记忆方案及自进化范围。
5. [Harness²评估](docs/research/2026-11-03-harness2-assessment.md)：固定上游源码调研，首版借鉴流程，不整包接入在线链路。

优先级：用户最新明确要求 → 本文件确认范围 → 架构规范 → 实施任务 → 讨论背景 → 旧AgentForge文档。遇到实现细节不一致，先保持已确认能力和核心契约，记录差异，不以历史草案覆盖用户要求。

## 已经完成与尚未完成

已完成：Task 0–14；Task 15 的后端显式装配与 API 兼容守卫已完成（新 app 挂载 access/usage/assistant/channels/memory/skills/evolution）。新架构测试当前 **299 passed**；逐任务证据、commit 与未验证项见 `docs/superpowers/plans/easychat-execution-log.md`，当前进度与交接要点见 `EASYCHAT_PROGRESS.md`。

未完成：Task 15 剩余（前端页面/API 收敛、旧模块删除、main.py 切换、144 路由逐条核对）与 Task 16（干净镜像/资源/恢复/最终交付）；真实 LLM/微信/MCP/SMTP/PDF 未联调；真实 Runner 隔离未验收，自动执行保持关闭；新仓库未推送。

没有复制：旧.git、真实.env/密钥、数据库/数据卷、上传、缓存、日志、已安装依赖。不要以为缺少这些文件就是拷贝失败，也不要自动从原项目取生产凭证。复制清单与hash位于`.planning/2026-11-03-easychat-design/copy-manifest.json`。

原.gitignore会忽略docs、scripts、pyproject等部分重要文件；Task 0需选择性修正以便提交方案与必要源码，同时继续排除秘密和运行产物。不要先执行git clean、reset或批量删除“未跟踪文件”，当前源码本来就尚未提交。

## 确认范围与任务对照

| ID | 必须交付的结果 | 主要任务 |
|---|---|---|
| R01 | EasyChat独立项目，不更改AgentForge，不擅自push | 0、16 |
| R02 | SQLite业务库、保留Hermes原始历史；无MySQL/Redis/图向量必需服务 | 2、5、15、16 |
| R03 | 移除本地知识库/RAG/GraphRAG、评测与专用数据层 | 5、15 |
| R04 | WeKnora等MCP按需调用，允许同机或异机，失败不影响普通聊天 | 5、7、16 |
| R05 | 保留微信iLink、Web、多端扩展、附件和会话恢复 | 5、6、7 |
| R06 | 保留完整RBAC、角色、用户单独授权、工具集控制；部门未批准删除 | 3、7、15 |
| R07 | 保留Token用户排行榜和统计，包含记忆/进化成本，不重复累计 | 4、5、11 |
| R08 | 保留个人技能库、版本、固定保护、归档与恢复 | 10、12 |
| R09 | 保留微信提醒、可靠投递和最小执行证据 | 6、8、14 |
| R10 | 邮件发送、SMTP/收件人和PDF报告保留、按需启用 | 8、14、16 |
| R11 | 用户事实/偏好、事件、经验记忆，来源、纠正、中文检索与遗忘 | 9 |
| R12 | 自进化从反馈到经验/技能/脚本、验证、启用与回滚 | 10、11、12、13 |
| R13 | 自进化不得直接修改生产服务源码、鉴权、权限、迁移和部署 | 3、11、12、13 |
| R14 | 删除技能社区、论文复现、Text-to-SQL等冗余平台业务 | 10、15 |
| R15 | 模块化单体、显式装配、小Interface、无路由SQL/循环依赖 | 1～16，架构测试持续检查 |
| R16 | 单worker、有界缓存/任务、常态主进程RSS<1GiB目标、真实资源验证 | 5、6、11、13、14、16 |

“保留邮件/PDF”不是把菜单留着却删掉实现；“保留RBAC”不是用单管理员替代；“保留Token排行”不是只留日志；“精简记忆”不是只保留摘要；“完整自进化”不是生成几条反思文字。

## 关键工程约束

- 一个Assistant执行入口，Web/微信/定时任务共用权限、模型、记忆、run与落库规则；渠道只处理协议和显示/投递。
- Module拥有自己的数据写入口；只通过公开Interface跨模块协作。SQLite先用具体Repository，不为不存在的第二种数据库创建兼容平台。
- app.db是应用业务权威，state.db是引擎历史权威，技能/附件大内容是不可变文件产物。没有跨库原子事务，不自动重跑有副作用工具“修复”投影。
- 唯一用量计量入口、唯一进化调度器、唯一技能激活入口；复用Hermes时防止原生后台路径绕过这些入口。
- 先做必要行为测试，真实临时SQLite，不mock自己所有SQL；网络和外发用替身。真实SMTP/微信发送、部署、远程push仍需用户实际明确指令。
- 所有默认预算/留存/容量是架构给出的可配置起始值，不是已测量结论。缺少真实Runner隔离验收时不能启用任意脚本自动执行。
- 每项任务完成要记录真实命令/结果、schema和commit；不得把计划中的命令写成已经运行。保持阶段可回退、旧桥接随迁移完成删除。

## 可以直接交给执行模型的指令

```text
请在 E:\PythonCode\EasyChat 按 EASYCHAT_PROGRESS.md 的当前进度继续实施。
先读 EASYCHAT_PROGRESS.md、架构规范、实施计划和 easychat-execution-log.md，
从未完成任务的下一项开始（当前为 Task 8），每阶段完成必要测试和本地提交，
更新 easychat-execution-log.md 与 EASYCHAT_PROGRESS.md。
不要修改 E:\PythonCode\AgentForge，不使用旧生产凭证，不自动推送。
严格保留RBAC、Token排行榜、个人技能库、微信提醒和执行记录，
邮件/PDF按需能力也要保留。架构采用模块化单体和单一执行/计量/进化入口，
不要通过一个万能Manager、全局mapper或多套后台循环实现功能。
离线测试可自主完成；涉及真实外发、部署或凭证缺失时单独说明。
不要在前几个任务就宣称全部完成；按四个里程碑交付并明确未验证项。
```

本文件最初由方案作者编写（当时未开始任何 Task 的业务实现）。当前 Task 0–7 已由执行模型完成；接手者先按 `EASYCHAT_PROGRESS.md` 核对工作区与最新提交，继续现有进度，不覆盖后续改动。
