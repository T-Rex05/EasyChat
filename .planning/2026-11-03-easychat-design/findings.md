# 调研发现

- 原仓库有未提交和未跟踪源码，已按工作区内容复制并逐文件 SHA-256 校验。
- 既有 .gitignore 忽略 docs、scripts、pyproject.toml 等源码/设计文件，复制时补入必要文件；不复制旧 .git。
- 现有 skill_service 包含内容池、上架审核、分类、安装等平台逻辑；技能文件 CRUD 与加载能力可独立保留。
- AgentForge 的 provider 已有 _run_dreaming（每10轮分析合并/删除）和结构化偏好/事实/事件/技能抽取；不能简单声称缺少自动记忆，但它们耦合多存储与旧服务，不应原样复制。
- get_project_tools 在权限过滤前导入论文复现和 Text2SQL；关闭菜单/toolset 不足以切断导入依赖。
- Hermes skill_manager_tool 支持创建/修改/删除技能和附属文件；已有加载和扫描可复用，但需要版本、验证、提升与回滚闭环。
- 原 cron 默认 report_format=pdf，投递耦合邮件/PDF；微信提醒应走纯文本渠道投递，不必保留重型报告栈。
- 图片中 top-k 命中与真正使用/反馈应分开；夜间衰减时间基点必须明确，否则重复累计衰减。数值权重未经过 EasyChat 场景评估。
- Hermes 已存在 background_review、curator、skill_provenance、skill_usage：应复用并统一调度，而非叠加多套自进化任务。后台审查 fork 对外部记忆提供器有隔离，需适配新 SQLite 记忆路径。
- Harness2 固定提交 6868817518876de8fd170c6a8354daca273b6191：现有 Codex/OpenCode executor，Hermes 需适配；基础Python dependencies为空。k=1正常路径4次任务执行、3改进阶段，不等于固定API次数；最终候选池不含baseline，EasyChat需另加不改差门槛。
- 用户修订：保留完整RBAC、Token排行、个人技能库、微信提醒、最小执行记录；邮件与PDF保留按需启用；已认可自进化范围。部门组织与数据层不能与RBAC混为一谈，暂不将部门列为已批准删除。
- 源码核实 get_ranking 汇总 daily_user_stats.total_tokens/api_calls，/api/traces/ranking 使用trace.view；write.py在调用完成时更新日汇总。迁移需要SQLite UPSERT、幂等计量及明确后台任务归属，不依赖Redis。
- cron/delivery.py 的邮件和微信投递均支持report_format并默认pdf；按需启用需保留真实能力和既有任务格式，不能仅隐藏入口或删除依赖后声称保留。
- 交接细化：静态提取144条保留控制器路由装饰器并保存source-map，记录关键文件/函数；未运行旧main.py导出OpenAPI，避免连接旧基础设施。
- 核心架构风险：controller自动扫描、权限跨层直SQL、llm_gateway Redis状态、两套用量观测和双SQLite一致性。采用模块化单体、显式组装、少量真实可替换Interface，不引入泛型Repository/插件平台。
- 精确权限公式已核对：(role ∪ user grants) − user revokes，super_admin使用已定义全集；management权限可跨owner管理，不能误改为仅本人。
- 交接新增architecture规范、17任务implementation、静态source-map及根目录HANDOFF。特别覆盖SQLite可空唯一键失效、用量晚到差额、技能激活CAS、两库恢复与任务副作用，避免执行者用假原子性/回放掩盖失败。
