# 上下文策略对照与消融评测

当前状态：10-28完成过6开发题×3组×1次本地初测，见[历史报告](../report/context_budget/qwen-pilot-01/report.md)。
11-03完善结构化恢复、其它短字段候选和full/delta/off投影入口，只做离线验证，没有新模型结果。
云端中断小批仍只作调试材料；新实验必须从全新目录冻结配置。

## 新增消融矩阵（已准备，未运行）

[config.ablation-local.json](./config.ablation-local.json) 包含6个profile：off、rules_legacy_full、
rules_conservative_full、rules_conservative_delta、rules_conservative_off、context_mode。

- legacy_full对conservative_full：比较其它短字段保留，恢复接口和full投影一致。
- conservative_full/delta/off：隔离投影策略，证据账本始终维护，不把关闭注入混成关闭状态。
- off/context_mode：保留开关与上游系统参考，不作为纯算法因果比较。

同任务、重复和profile组成交叉矩阵，seed=731随机交错；6开发题×6profile×3重复=108 runs。
名称须唯一且不能含路径片段。每run冻结result_policy、task_state_projection和runtime_arm，
覆盖继承环境；结果/报告按profile分组，不把不同投影混进同一个rules汇总。

只准备时不需要凭证或upstream checkout，不导入模型客户端或启动MCP：

~~~powershell
python -X utf8 eval/context_budget/pilot.py --prepare-only --config eval/context_budget/config.ablation-local.json --output E:/AgentForgePrivate/context-eval/ablation-prepared-001 --repeats 3 --parallel 1
~~~

plan.json保存配置、配置/源码/fixture哈希和随机作业表，executed=false、model_calls_executed=0。
这个零只描述准备阶段；执行manifest不继承它，实际请求以逐调用账本计量。
真正运行仍需显式--execute，包含context_mode的配置还必须传--upstream；准备命令不会续跑已准备目录。
全部失败的profile也保留在报告中，缺失Agent耗时标unknown。

这是开发集消融入口，18题holdout和跨run总token/费用硬停止仍未完成，不能称正式benchmark完成。

本次已生成[审查后的108-run冻结计划](../report/context_budget/ablation-plan-2026-11-03-reviewed/plan.json)，
其中executed=false。准备计划不代表108次模型实验已经发生，也不提供性能结论。

## 三组定义

1. off：真实 Hermes，关闭新模块，使用原有输出预算。
2. rules：同一 Hermes 和任务源，启用原文保存、字段保护、恢复；压缩策略为当前规则。
3. context_mode：同一模型和任务源，使用固定 commit 的原版 MCP server。
   读取/分析通过 ctx_execute / ctx_execute_file，保存/回读通过 ctx_index / ctx_search。
   不向此组暴露旁路 fetch_fixture；必须在轨迹中确认上游工具实际调用。

前两组使用相同工具协议，可判断模块开关效果。第三组工具表面不同，是 MCP 工具集的
系统比较，不能把差值全部归因于某个算法，也不能称作包含原版全部宿主 hooks 的比较。
两边均可在完整数据上执行代码分析；不得强迫原版全量输出或禁止其正常聚合。

## 固定条件与任务

先用6道开发题检查：小输出、长JSON关键字段、批量聚合、非保护字段检索、错误回执、
两轮延迟追问。正式集采用此前设计的6类×4题：每类1 dev、3 test，共6 dev/18 test。
按模板和数据来源拆分。现有 pilot.py 只有开发烟测任务，不等于正式测试集。

每个任务各组使用相同 fixture 哈希、问题、后续追问揭示时机、模型版本、采样设置、
上下文窗口、输出上限、调用上限和超时。测试前冻结 manifest；不依据结果调整提示或阈值。
各 task/repeat 内平衡随机运行顺序；正式每题3重复，分析单位为任务。

每run使用新进程、HERMES_HOME、会话、原文库和上游MCP HOME。缓存命中按provider
返回计量，不能声称清空了provider缓存。SDK内部重试也需逐HTTP attempt留账。
答案与验收器不提供给agent；检查MCP调用轨迹是否越过指定fixture读取其他运行结果。
当前本地MCP运行不是强OS沙箱；正式跨用户安全评估需要独立执行环境。

## 本地模型接入

将 config.example.json 复制为本机配置，填写本地模型的精确ID、OpenAI兼容
Chat Completion端点、输出上限和每任务墙钟限制。默认地址是localhost，无内置云端地址。
若服务要求鉴权，在 api_key_env 指定环境变量；配置文件不要写密钥。
本地无鉴权服务仅对 localhost / 127.0.0.1 / ::1 允许占位凭证。

准备完毕后，由用户明确要求运行时再执行：

~~~powershell
python -X utf8 eval/context_budget/pilot.py --execute --config E:/private/local-eval.json --output E:/private/context-eval/run-001 --upstream C:/Users/SWQ/AppData/Local/AgentForge/context-eval/context-mode --repeats 1 --parallel 1
~~~

不传 --execute 不会调用模型，可显式 --prepare-only 保存计划。先单并发开发烟测，检查模型的tool calling、
usage和上下文长度；确认计量及验收后才运行正式集。模型吞吐评测应固定并发，分开报告
模型/工具执行时间和含冷启动的完整墙钟时间。

## 指标与验收

- 任务成功：精确字段、聚合真值、最终产物等程序断言；内容正确与严格JSON格式分别报告。
  当前pilot的严格JSON验收会将“JSON后附解释”判失败；正式运行前必须锁定两种口径。
- token：逐调用记录原始usage、未缓存输入、缓存读/写、输出/思考，并聚合全部尝试。
  output已含reasoning时不再加一次。无usage记unknown，字符估计只能作诊断。
- 成本：本地服务无API账单时，API费用记不适用；需电费/算力费用则按GPU功耗、单价、
  运行时长或租用单价单独测量。Coding Plan token消耗不能冒充实际人民币扣款。
  官方按量单价折算仅作反事实参考，必须与实际成本分列。
- 延迟：每run端到端、agent循环、模型请求时间，报告中位数和全部失败/超时。
- 总费用包括判断/摘要/恢复/修复/失败/重试；离线评分成本另列。失败样本不能删除。
- 恢复次数、保护字段遗漏、工具选择、原版MCP实际调用和原始/呈现大小作为诊断项。

主要比较预注册为rules对off；context_mode为系统对照。先对每题重复求均值，再作任务级
配对分析和区间。小批开发题只说明可运行性与故障，不足以证明泛化收益。

## 正式评测前尚需完成的验收

1. 完整18题holdout与独立验收器落盘并锁定哈希；当前只有6题开发集生成器。
2. 将config中的总token/费用预算实现为全局硬停止；当前只具备每run调用数/墙钟上限。
3. 在真实本地服务验证非流式响应与provider usage；若需流式，要实现SSE usage聚合，
   当前HTTP计量读取JSON，不能直接计量SSE。
4. 中断/超时的在途调用标unknown；上游MCP启动失败也保存终态，不能遗漏整run。
5. 保存Node、依赖锁文件、server bundle及本仓未提交源码的哈希；固定实际模型权重版本。

这些属于后续评测准备验收，不是当前已得到的性能结果。现有prototype入口便于接本地
模型验证，尚未宣称完整正式benchmark runner。
