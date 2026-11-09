# 进度

2026-11-03：创建 E:/PythonCode/EasyChat 源码副本；源仓库业务代码未变。复制范围和哈希见 copy-manifest.json。仅准备副本和方案，不启动修改。

复制完成：1796 文件 / 37.79 MiB，全量 SHA-256 一致。Git 新建 main 分支，origin=https://gitee.com/T_Rex_Warrior/easy-chat.git；未提交、未推送。已发送自进化范围问题，用户要求尽量完整并研究 Harness2。开始固定源码对比和记忆图片审查。

完成 docs/superpowers/specs/2026-11-03-easychat-design.md（10节），补充事件记忆、完整技能/脚本进化、进一步删减矩阵和图片机制评估；调研子任务完成 docs/research/2026-11-03-harness2-assessment.md。旧方案仅加历史版本提示。

交付验证：manifest全部文件存在，原项目文件无变化；副本业务代码哈希均与复制时一致，仅旧方案文档加提示。origin/main、10节文档和报告链接检查通过。未安装、未启动服务、未跑业务测试、未提交推送。方案尚未用户确认，不能开始实施。

2026-11-03：用户要求恢复RBAC和Token排行保留；异步澄清后确认邮件/PDF保留按需启用，自进化边界认可。已修订新讨论稿的删减矩阵、前端范围、7.2确认状态、阶段与验收，并增加3.1～3.3详细设计。仅文档修改，不开始实现。

本轮核验通过：10个主章节、RBAC/排行/邮件PDF和进化确认状态均存在，旧冲突删除措辞已消除；复制清单中全部非文档文件SHA-256未变。未运行业务测试，未提交推送。

2026-11-03：用户要求供其他模型执行的细化方案，重点架构和代码质量。完成模块化单体架构规范、17任务/四里程碑实施计划、144条静态路由定位、独立交接入口和需求对照；当前进行文档/契约/范围交叉核验，仅文档变更。

交接核验首次占位符扫描把英文待办工具名识别为占位符，已改用中文“待办”消除歧义，继续检查。

最终核验：17个Task顺序、16项需求对照、144条静态路由、5段Python示例语法、8个本地文档链接全部检查通过；复制清单全部非文档业务文件hash未变。自审补充了MCP实际任务、通用文件工具绕过技能版本的防护、旧测试退役/迁移及旧数据默认不导入说明。本轮无应用启动/业务测试/安装/提交/推送。交接入口EASYCHAT_HANDOFF.md，架构/实施/source-map均已写入。

2026-11-05：微信 A+C 增量二次验收收尾。required 后端 **708 passed in 208.96s**；本次改动文件 ruff、前端 type-check/build 通过。P1-1～P1-5 已闭合：care 只在 delivery 实际 `sent` 的 `on_sent` 回调后写 `last_care_at`/`mood_care_log`，failed dedup 复用不标记，重复回调幂等。P2 已修：周报“下周”从明天 00:00 起算、`别忘` 与 `我以后都` 触发词边界、care 日志按情绪保留期回收。`memory_correct`、每日 10,000 tokens 预算和“模型不可用时显式记住是否回退正则”仍未纳入；真实 iLink/STT/上传/模型/部署未验证。详见 docs/superpowers/specs/2026-11-04-wechat-a-c-design.md §23.5 与 docs/superpowers/plans/2026-11-04-wechat-a-c-acceptance.md §7。

2026-11-05：微信 A+C 增量第三轮验收收尾。只修两个边界：周报“下周”对重复计划的 occurrence 漏项，以及删除/关闭情绪后的在途 care。`SchedulingService.upcoming(start=...)` 对 once/interval/daily/weekly 做纯投影，不改数据库，展开排序后再截断 50 条；`BriefingService` 早/晚/周报分别传 start。新增 delivery `cancelled` 状态，delete/close 取消 pending/retry care delivery 与 `mood.care`/wake job；`delete_mood` 清空 `last_care_at` 并关闭 opt-in；`on_sent` 用 opt-in 与 `updated_at`/`created_at` 拒绝删除后迟到回调。已用真实 SQLite 集成测试覆盖每日/每周/一次性/briefing 自身/边界/interval/截断，以及 pending→delete/close、sent 后删除再回调、正常幂等。`sending` 已开始外部调用的窗口不可撤回，是残余风险；failed care 当天补偿重试、`on_sent` 写库异常补偿、`memory_correct`、每日 token 预算仍未纳入；真实 iLink/STT/上传/模型/部署未验证。详见 design §14.4/§23.5 与 acceptance §7.5。

2026-11-05：微信 A+C 第四轮 care 并发收尾。新增 `0017_care_epoch.sql` 的 `care_epoch_at`，只在删除/关闭/降低主动性时推进；`ProfilesRepository.mark_care_sent` 把 opt-in/代际校验、care 日志插入和 `last_care_at` 更新放进同一个 `BEGIN IMMEDIATE` 事务，消除 callback 与 delete 的 TOCTOU；普通资料更新不再误伤 care，`proactivity=low` 会取消 pending care 并阻止旧回调。新增 4 条回归测试（交错删除、普通资料更新、低主动性、删除后重新开启旧回调）。required **726 passed in 221.98s**，ruff 与前端 type-check/build 通过。`sending` 不可撤回和目标解绑后的旧 target 仍是残余风险；failed care 重试、`on_sent` 写库异常补偿、`memory_correct`、每日 token 预算仍未纳入；真实外联/模型/部署未验证。详见 design §14.4/§23.5 与 acceptance §7.6。

2026-11-05：容器冒烟验证。默认 PyPI 直连构建遇到 wheel hash mismatch；本机临时用可达镜像源构建并启动单容器，修复 `python-multipart` 缺失（已写入 `docker/requirements-core.txt`）。`/healthz`、`/readyz`、SPA、注册/登录、profile 读写、情绪删除、multipart 上传均通过；容器内迁移到 `0017`、`care_epoch_at` 存在；重启后卷数据仍可登录。默认 Dockerfile 的完整直连构建仍需可靠网络复跑；真实 iLink/STT/模型/部署未验证。
