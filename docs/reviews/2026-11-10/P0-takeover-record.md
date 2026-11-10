# P0 接管记录(2026-11-10)

接管提示词由用户在会话中下达;本记录对应仓库 `AGENTS.md` §交付约定与执行计划 §10 P0。所有结论同句附证据;无证据处标"推断"。

## 1. 起点

| 项 | 值 | 证据 |
|---|---|---|
| 分支 | `feature/permission-remediation` | `git branch --show-current` |
| HEAD | `d174afa`(AGENTS.md 提交,已推 Gitee origin + GitHub) | `git rev-parse HEAD` |
| 工作区修改(待保留) | `agent_frontend/src/views/admin/RoleEditDialog.vue`(M,3+/4-)、`agent_frontend/tests/role-modes.test.mjs`(未跟踪)、`docs/reviews/`(未跟踪,含 access 草稿包六件)、`docs/superpowers/plans/2026-11-10-superagent-production-execution.md`(未跟踪) | `git status --short` |
| 部署版本 | EasyChat 服务未运行(8001 无监听,`netstat`);内嵌 Hermes `0.19.0`(`backend/hermes/hermes_cli/__init__.py:__version__`);Python 3.12.8;前端测试 `node --test`(package.json) | 实测 |
| 其他运行任务 | DSH 独立工具(superagent-pstack 分层系统)在 WSL 面板 3082 监听——**其他会话产物,保留不动** | `netstat -ano` PID 34528 |
| 活跃编码任务 | 无 running/queued;历史 2 cancelled + 1 failed(`data/app.db` mode=ro 查询) | 只读 SQL |

## 2. 受保护路径许可范围(会话内人工授权)

- 用户接管指令明确列出执行顺序含 "P2 权限草稿修复",构成 `AGENTS.md` 要求的续作许可:**获准在隔离分支应用 `docs/reviews/2026-11-10/access-fixes.draft.patch` 四项修复并纳入 tests/access 回归**。
- 授权边界:①委派上限(delegation matrix)为产品决策,保持"设计待决",不实施;②memory capability 语义(写是否隐含读)保持草稿现策略(不扩大授权),如需变更另确认;③执行引擎切换/P10 Harness 试验单独排期,不在本轮。
- 真实微信外发与真实 GitHub PR 的测试目标未授权/未提供:`tests/security`、`tests/delivery` 的 integration/resources 用例继续默认排除;GitHub 实单验收需用户指定测试仓库(候选 `T-Rex05/EasyChat` 本体,待确认)。

## 3. 基线(P1 第一步,本轮实测)

| 套件 | 结果 | 退出码 |
|---|---|---|
| `tests/access tests/security`(未打补丁源码) | **52 passed** | 0 |
| `tests/superagent tests/contracts` | **1 failed / 197 passed**(`test_tool_context.py::test_async_handler_resolves_context_before_leaving_current_thread`,ModuleNotFoundError) | 1 |
| `tests` 全量 | **1130 passed, 2 skipped** | 0 |
| 前端 `npm test` / `type-check` / `build` | 22 passed / 通过 / ✓ built 21.97s | 0 / 0 / 0 |

说明:access 现有套件全绿与简报"基线红灯"不矛盾——红灯证据来自草稿新增回归 `test_access_draft.py`(在 docs/reviews/2026-11-10/,未入 tests/access);四项缺陷仅被新回归暴露。

### 基线缺陷 #1(本轮新发现,已修复)

- **现象**:`tests/superagent tests/contracts` 序列下 `test_async_handler_resolves_context_before_leaving_current_thread` 报 `ModuleNotFoundError: No module named 'tools.registry'`;单独跑与全量跑均通过(两次复现 + 单独复现通过)。
- **根因(实测实锤)**:本机全局 Python 3.12 site-packages 存在 `D:\Python\Python312\Lib\site-packages\_editable_impl_austin_sparkflow.pth`(对 `E:\JavaCode\Austin\austin-sparkflow` 的 editable 安装残留),把该目录常驻注入 sys.path。`sys.modules['tools']` 若在此路径上抢先绑定(其 `tools` 无 registry 子模块),内核 `from tools.registry import registry` 即失败。诊断插件(临时,已删)证实 contracts 序列中 `tools.__path__=['E:\\JavaCode\\Austin\\austin-sparkflow\\tools']`。
- **最小修复**:`tests/conftest.py` 在根目录插入后,将 `backend/hermes` 置于 sys.path 最前并 `sys.modules.pop("tools", None)`,使内核绑定确定性抢先。
- **修复回归(实测)**:原失败序列 `tests/superagent tests/contracts` **198 passed**;`tests/contracts` 单独 **136 passed**;全量 **1130 passed, 2 skipped**(无回归)。
- **回滚**:还原 conftest.py 该段即可。
- **遗留建议(环境侧,需主人决定)**:全局 Python 中的 austin-sparkflow editable 安装建议卸载或迁移到该项目自有 venv,否则任何本机 Python 工具链都可能受同类污染。

## 4. 工作包状态标注(P0–P10)

| 包 | 状态 | 依据 |
|---|---|---|
| P0 接管盘点 | **本次完成** | 本文件 |
| P1 基线/备份/CI/规则 | **agent 侧完成**(3de6a9c+演练脚本):基线✓、备份/恢复演练 DRILL_OK✓、CI 入库+npm test✓(注意 .github 此前被 gitignore,工作流从未在 GitHub 运行,本轮实锤入库)、rulesets 重新实测 protected:false/空→owner 清单(P1-owner-ruleset-checklist.md) | §3 与计划 §10 P1 |
| P2 权限草稿+权限界面 | **核心完成**(8082ff0/9abc28a):四项修复应用并验证(重放62/定向71/全量1140);入口矩阵 24 键全有 service 检查、三缺口补回归;RoleEditDialog 修复+role-modes 已入库(47952bd);委派上限=设计待决 | P2-entry-matrix.md、P2-access-applied.md |
| P3 Hermes 来源与升级治理 | **核查完成**：来源三层实锤(产品补丁 0、复制期差异恰 5 文件、上游未确认如实记录);集成点 9 项清单;遗留导入定位(skill_manager 死路径候选,待复现后删);架构约束测试已有且双向防漂移(P3-4);候选升级演练=设计阻塞 | P3-hermes-governance.md、hermes-provenance.json |
| P4 隔离/取消/预算 | 已有待验证为主(T1–T4 已实现 worker 侧取消/限时/回收),越界探测=确认缺口 | HANDOFF T1–T4、计划 §4 |
| P5 恢复/验证/发布 | 已有待验证(完成门禁+双比较+checkpoint 已实现),故障注入回归=确认缺口 | HANDOFF T1、计划 §5 |
| P6 微信受理/追问/回执 | 已有待验证(/开发 /任务 /补充 /取消 /重试 命令族+持久 inbox 已实现),真实渠道=环境阻塞 | HANDOFF T5、计划 §5 阶段 D |
| P7 webhook 反馈 | 已有待验证(T7 已实现),真实投递=环境阻塞 | HANDOFF T7 |
| P8 前端验收 | 确认缺口为主(此前 UI 修复已有部分),真实浏览器操作未做 | 计划 §10 P8 |
| P9 全量评审/实单/回滚 | 未开始(依赖 P1–P8) | 计划 §7 |
| P10 Harness 对照试验 | 单独排期,本轮不动 | 接管指令 |

## 5. P0 交付清单

- 本记录:`docs/reviews/2026-11-10/P0-takeover-record.md`
- 修改:`tests/conftest.py`(基线缺陷 #1 修复,见 §3)
- 待保留修改未触碰;无提交、无推送(小步提交将在 P1 完成后按 conventional 风格进行)
