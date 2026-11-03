# EasyChat 执行日志

执行者按 `EASYCHAT_HANDOFF.md` 与 `docs/superpowers/plans/2026-11-03-easychat-implementation.md` 推进，每任务记录：已完成ID、commit、实际命令/结果、未验证项、schema版本、下一项。

---

---

## Task 0：源基线、依赖及协议盘点 — 2026-11-03 完成（commit `1d41c2a`）

**状态：** 已完成（离线静态盘点，无产品行为改动）。

### 完成项与证据

1. **copy-manifest 核对**：`python` 脚本逐一校验 1,796 个文件的存在与 sha256。
   结果：`ok=1795 missing=0 hash_mismatch=1`。唯一不一致：`docs/superpowers/specs/2026-11-03-personal-assistant-design.md`——交接文档已说明旧方案文档补了历史版本提示后修改，属预期差异。源基线 `source_head=23fdb99f60b6382018e5e8960352129024c6965c`（含工作区修改的快照）。
   manifest 中登记的杂物（`=1.2.2`、`=2.13.4`、`=2.24.0`、`coverage.xml`、`rubric_result.json`、`test_paper_full.py`、`test_paper_parse.py`）确认在盘，磁盘保留、git 基线排除杂物与生成物。
2. **工作区确认**：`git status` 全部未跟踪、`main` 无任何提交（不是已提交基线）；`git remote -v` → origin `https://gitee.com/T_Rex_Warrior/easy-chat.git`。未执行任何 clean/reset/批量删除。
3. **.gitignore 选择性修正**：移除对 `docs/`、`pyproject.toml` 的忽略（方案与元数据需入库）；保留对 `CLAUDE.md`、`scripts/`、`*.bat` 的忽略；新增杂物排除（`=*`、`out/`、`.v2c/`、`rubric_result.json`、`coverage.xml`）与 Hermes optional-skills 图片资源例外（`!backend/hermes/optional-skills/**/*.png|jpg`）。被图片规则排除的仅 `backend/hermes/gateway/assets/telegram-botfather-threads-settings.jpg`（上游文档截图）。
4. **秘密扫描**：仓库树无 `sk-`/`AKIA`/`ghp_` 模式命中；`backend/hermes/.envrc`（direnv nix 配置）、两个 `.env.example`（占位符）确认无真实凭证；无 `.db`/`.env` 真实文件被复制。
5. **路由静态核对**：AST 扫描 `backend/controller` 全部路由装饰器 → **284 条**（`out/task0_route_scan.json`）。源码定位文档保留清单表格实际 **138 行**（文档口径称 144，含 `cancel_chat` GET/POST 双方法等计数差异），138 条全部在代码中核实存在（`out/task0_verify_routes.py`）。
   分类结果（`tests/fixtures/contracts/legacy-api.json`，284 条全量）：**keep 130**（迁移到模块公开接口，HTTP 契约不变）、**remove 130**（graphrag 43、kb_eval 36、kb 15、memory_eval 12、data_layer 10、host_whitelist 域外的 community/pool 8、tool 2、category 3、notification 1 等）、**keep-migrate 24**（host_whitelist 11 + command_blacklist 6 + data 7：服务被保留的执行治理/审计能力或会话列表重复入口，宿主模块 Task 15 定）。
   前端字面调用扫描（`out/task0_frontend_calls.json`）174 个路径交叉核对：`/api/data-layers*`、`/api/kb/*`、`/api/graph/*`、`/api/tools/*` 前端仍调用但属确认移除模块（Task 15 删前端页面）；`agent_frontend/src/api/memory.ts` 的 8 个 `/api/memory*`（单数）路径**后端无承载路由，是死代码**。
6. **SSE 契约 fixture**：`tests/fixtures/contracts/legacy-sse.json` 记录 GET/POST `/chat/stream` 参数、409 busy 语义、`id: {seq}`+`data:` 帧格式、`Last-Event-ID`→`from_seq=N+1` 续传、环形缓存 1000/截断 500、run TTL 300s/MAX 200、8 种公开帧类型与字段、Task 6 适配要求。
7. **依赖盘点**：`docs/architecture/dependencies.md`。Python 3.12.8（pyproject 声明 >=3.10）；关键包实测版本 vs requirements.txt 固定值差异表（openai 3.29.0 与 `<3.0.0` 约束冲突、fastapi 0.143 vs 0.121 等，以实测为准）；croniter/weasyprint/markdown 未安装及其影响；前端锁定 **npm + package-lock.json**（部署脚本实证），pnpm 锁文件 Task 15 删。
8. **基线提交**：本日志与全部产物入库；基线 commit hash 见下方记录（由后续提交回填）。

### 产物清单

- `tests/fixtures/contracts/legacy-api.json`（284 条路由分类清单）
- `tests/fixtures/contracts/legacy-sse.json`（SSE 契约）
- `docs/architecture/dependencies.md`（依赖盘点）
- `docs/superpowers/plans/easychat-execution-log.md`（本文件）
- `out/task0_*.py|json`（盘点脚本与中间产物，git 排除）

### 未验证项

- OpenAPI 全量核对：旧 `main.py` 会初始化 MySQL 等基础设施，不能为导出 OpenAPI 启动；待 Task 1 无副作用工厂完成后由新 app 导出比对。
- 前端调用与后端参数级别的字段核对仅在关键入口（chat/stream、cancel、history）完成；其余入口在对应任务迁移时按 fixture 逐条核对。
- 真实 SQLite 运行时与 Hermes WAL 兼容在 Task 2 实测。

### schema 版本

无（Task 2 建立 `0001_core` 迁移）。

### 基线提交

- baseline commit：`1d41c2a`（含 1,555 个文件；提交后 `git log` 核验）
- `git remote -v`：origin → `https://gitee.com/T_Rex_Warrior/easy-chat.git`（未推送，遵交接约束）

### 下一项

Task 1：公开契约、显式装配与无副作用工厂（`backend/shared/*`、`runtime/contracts.py`、`app.py`/`bootstrap.py`、测试设施 rig、架构 AST 测试、工厂契约测试）。

---

---

## Task 1：公开契约、显式装配与无副作用工厂 — 2026-11-03 完成（commit `6f418e5`）

**状态：** 已完成（离线测试全绿）。

### 新建文件

- `backend/shared/context.py`：`Principal` / `ExecutionContext` 冻结值对象（含 slots，不可变测试覆盖）。
- `backend/shared/errors.py`：10 个 `ErrorCode` + `AppError` 体系 + 类型化子类；`http_status` 映射 401/403/404/409/422/429/503/504/500。
- `backend/shared/identifiers.py`：run/sess/call/job/dlv/art ID 构造与格式校验（`{kind}_{32hex}`，前缀参与校验）。
- `backend/runtime/contracts.py`：`RuntimeRequest` / `RuntimeEvent` / `ExecutionRuntime` Protocol（合法 Protocol 声明，无实现）。
- `backend/modules/assistant/contracts.py`：`RunCommand` / `RunReceipt` / `RunEvent`。
- `backend/bootstrap.py`：`AppSettings`（强类型、能力开关默认关闭）、`default_settings()`（相对路径常量，无文件系统访问）、`settings_from_environment()`（仅 lifespan 显式调用）、`ModuleRegistry`（显式装配容器，模块字段随任务推进）、`run_startup`/`run_shutdown`（Task 1 仅产物目录；迁移与模块后续按序加入）。
- `backend/app.py`：`create_app` 工厂 + `/healthz`、`/readyz`(lifespan前503) + `AppError` 统一异常处理器；`error_to_response` 单一映射点。
- `tests/support/rig.py`：`FakeRuntime`（记录请求/回放事件序列/计数）+ `make_rig`/`TestRig`（临时目录+独立配置）；随任务扩展。
- `tests/conftest.py`：**重写**——删除隐式 `load_dotenv(.env)`（旧配置会读真实凭证，违反离线约束），保留 sys.path 注入，新增 `rig` fixture。
- `tests/architecture/test_imports.py`：AST 架构检查——严格目录（shared/platform/modules/runtime/integrations + app/bootstrap）禁止 pymysql/redis/dbutils/neo4j/pymilvus/chromadb/backend.rag；`backend.hermes` 仅 `runtime/hermes` 可导入；modules 跨模块只允许 `api.py`/`contracts.py`；routes.py 无 SQL import；全部路由文件（含旧 controller）不得直接 import pymysql/redis；严格目录 import 图无环；**存量豁免名单与实际违规双向一致**（未登记的新违规失败、名单过期也失败，防只加不删）。名单现况：20 个禁用依赖文件 + 23 个 Hermes 直接引用文件，全部旧目录并附原因。
- `tests/contracts/test_app_factory.py`：子进程禁网+断言 dotenv 未加载的 import 纯净性测试；`socket.create_connection`/`asyncio.open_connection` 拦截下的工厂+ lifespan 运行测试；create_app 无文件/线程/迁移副作用测试；readyz 503→200 流转；错误映射全表；冻结不可变性；lifespan 幂等。
- `pyproject.toml`：注册 `integration`/`resources` markers。

### 实际命令与结果

```
python -m pytest tests/architecture tests/contracts/test_app_factory.py -q
→ 21 passed in 4.15s
python -m ruff check <新代码路径> → All checks passed!
python -m compileall -q backend/shared backend/runtime backend/modules backend/app.py backend/bootstrap.py tests/support → OK
```

### 关键决策记录

- 旧 `tests/conftest.py` 的隐式 `.env` 加载已移除；旧真实联调测试不再自动获得凭证，属预期（它们随旧业务在 Task 15 退役或标 integration）。默认全量套件绿灯推迟到 Task 15/16 旧测试清理后，不以跳过换绿灯。
- 离线拦截只替换出站原语（`socket.create_connection`、`asyncio.open_connection`），不替换 `socket.socket`——事件循环内部自建 socket 是合法的。
- 架构测试中带 BOM 的存量文件用 `utf-8-sig` 解析。
- `backend/`、`tests/`、`tests/support` 等补齐 `__init__.py`（原为 PEP 420 命名空间包，显式化）。
- AppSettings 拒绝空路径（强类型）；工厂缺省走 `default_settings()` 相对路径。

### 未验证项

- pytest-asyncio `asyncio_mode="auto"` 与 `rig` fixture 的实际配合在 Task 2/3 首个使用处验证（Task 1 尚无 async fixture 使用者——已由 conftest 语法与收集通过）。
- 新 app 工厂导出 OpenAPI 与旧 144 路由清单比对：等 Task 6 路由就绪后进行。

### schema 版本

无（Task 2 建立）。

### 提交

`6f418e5` feat(backend): public contracts, explicit bootstrap, side-effect-free app factory (Task 1)

### 下一项

Task 3：RBAC、用户/角色/部门与会话资源授权（已完成，见下）。

---

---

## Task 2：SQLite平台、版本迁移与首批业务表 — 2026-11-03 完成（commit `ee8f903`）

**状态：** 已完成（离线测试全绿，真实临时SQLite）。

### 新建文件

- `backend/platform/sqlite.py`：`Database`（每操作新建连接、`foreign_keys=ON`、`busy_timeout=5000`、WAL + 文件系统回退DELETE）；`transaction()`（BEGIN IMMEDIATE 短事务，退出提交/回滚并关连接）；`run_migrations`（版本化迁移，**禁用 executescript**——它会隐式提交挂起事务破坏原子性，改用 `sqlite3.complete_statement` 拆语句逐条执行）；`MigrationError`（checksum 不一致失败）；`foreign_key_check`。
- `backend/platform/settings.py`：`AppSettings` 自 bootstrap 迁入（新增 state_db_path 非空校验）、`default_settings()`、`settings_from_environment()`；bootstrap 保留再导出。
- `backend/platform/jobs.py`：`JobQueue`——幂等入队（dedup_key 全局唯一，任意状态同键复用同一任务，同业务信号永不重跑）、短事务认领（两认领者不重复）、条件更新 complete/fail/cancel（过期 lease 失效保护）、`recover_expired_leases`（attempts 保留不重置）；状态机 pending→leased→succeeded/retry_wait/failed/cancelled。
- `backend/platform/migrations/0001_core.sql`：首批表——access(users/roles/role_permissions/user_permissions/permission_defs，列语义沿用旧MySQL schema)、channels(channel_accounts/channel_bindings/channel_events，UNIQUE(platform,account_id,external_event_id))、assistant(sessions/runs/conversations/attachments；runs 唯一键含非空 `channel_account_scope`)、usage(llm_calls/daily_user_stats，UNIQUE(stat_date,user_id,source))、models(model_configs)、平台(app_settings/jobs)。时间 UTC ISO 文本，jobs 调度字段 REAL epoch。种子仅 timezone 系统默认值（幂等 ON CONFLICT DO NOTHING）。
- `tests/storage/test_sqlite.py|test_migrations.py|test_jobs.py`：29 项行为测试。

### 实际命令与结果

```
python -m pytest tests/storage tests/architecture tests/contracts/test_app_factory.py -q
→ 50 passed in 5.43s
python -m ruff check backend/platform tests/storage backend/bootstrap.py → All checks passed!
PRAGMA 实测（Python 3.12.8 / sqlite3 3.45.3, Windows NTFS）：
  journal_mode=wal, foreign_keys=1, busy_timeout=5000, 迁移后表数=19（含schema_migrations）
```

### 关键决策记录

- **journal 模式选 WAL**：与内嵌 Hermes state.db 策略一致（`hermes_state.py` 注释明确 WAL+回退）；两库是不同文件，WAL 为库级设置互不影响。文件系统不支持时自动回退 DELETE 并记录实际模式。
- **迁移原子性**：`executescript` 会先 COMMIT 挂起事务（实测 `cannot commit - no transaction is active`），迁移执行改为逐条 `execute`；失败 ROLLBACK 撤销整个迁移，`schema_migrations` 无记录，`Database.ready` 保持 False。
- **jobs 幂等语义**：dedup_key 任意状态同键返回同一任务 ID（succeeded 后重复入队不产生新任务）；新业务信号必须携带新事件 ID 构造 dedup_key。
- 部门现状核实：旧 MySQL schema（67 张表）**无 departments 表**，仅 `admin.departments` 权限键登记于旧 permission registry；按"保留现状"处理（不新增不删除），Task 3 迁移权限种子时沿用此口径。
- 修复：工厂离线测试原用 `default_settings()` 跑 lifespan 会在仓库根创建 data/ 目录——改用 tmp 路径并清理污染。

### 未验证项

- Linux 目标环境的 WAL 行为与 Hermes 兼容在 Task 16 干净镜像验证。
- jobs 在多进程部署下的行为未验证（架构明确单worker进程内串行只覆盖本进程）。

### schema 版本

`0001_core`（checksum 记录于 app.db `schema_migrations`；迁移清单见 `backend/platform/migrations/`）。

### 下一项

Task 3：RBAC、用户/角色/部门与会话资源授权。

---

---

## Task 3：RBAC、用户/角色/部门与会话资源授权 — 2026-11-03 完成（commit `ba8964e`）

**状态：** 已完成（离线测试全绿）。

### 新建文件

- `backend/modules/access/contracts.py`：权限/工具集注册数据 + `UserSnapshot`/`RoleInfo`/`PermissionOverride`。权限口径：保留 12 键（chat.use、skill.create、skill.manage、memory.view、memory.edit、terminal.audit、cron.create、system.manage、system.config、trace.view、trace.manage），移除 skill.pool.review/kb.manage/kb.eval/graph.manage/paper.use（R03/R14），新增 evolution.view/evolution.manage（R12）。工具集移除 paper_repro，历史废弃键过滤沿用旧 checker 清单。部门现状：旧库无 departments 表，仅历史权限键，不新增不删除。
- `backend/modules/access/policy.py`：纯函数——`effective_permissions`（revoke > grant > 角色；super_admin 取已注册全集）、`effective_toolsets`（fail-closed 过滤）、`can_manage_resource`（super_admin/manage权限/owner，沿用旧 check_ownership 语义）。
- `backend/modules/access/repository.py`：users/roles/role_permissions/user_permissions/permission_defs 全部 SQLite 访问 + scrypt 密码哈希（格式沿用旧 auth_service，存量 SHA256+salt 验证并升级）+ 种子（默认授权仅在角色零授权时播种）。
- `backend/modules/access/api.py`：`AccessService`——register/login（弱密钥拒绝沿用旧规则）、token 生命周期（HS256 格式沿用旧实现，旧 token 可验证；滑动续期+宽限刷新）、`authenticate_token`（每次对 DB 重查禁用状态与角色，token 内角色不信任——按架构 §6 比旧中间件更严格）、`validate_principal`（排队执行/后台重试前重校验）、有界缓存（revision 全局递增，任何授权变更整体失效，替代 Redis）、资源归属授权、用户/角色管理。
- `backend/modules/access/routes.py`：`build_access_router(access)` 注入式工厂；/api/auth（register/login/me/refresh/users）+ /api/admin（users、role/status/perms、permissions、toolsets、roles CRUD）。响应结构沿用旧契约；移除社区审核端点。
- `tests/support/rig.py` 扩展：`db`/`access` 字段、`seed_user(role, grants, revokes)`（真实注册入口+repository 种子路径）、`FakeClock`、`make_rig(seed_access=True)`。

### 实际命令与结果

```
python -m pytest tests/access tests/storage tests/architecture tests/contracts/test_app_factory.py tests/contracts/test_auth.py -q
→ 85 passed in 19.64s
python -m ruff check backend/modules/access tests/access tests/contracts/test_auth.py tests/support → All checks passed!
python -m compileall -q backend/modules/access → OK
```

### 关键决策记录

- super_admin 有效权限=运行时注册全集，不在库中重复授权（与旧 seed_to_db 行为一致）；revoke 对 super_admin 无效。
- 未注册权限键在服务层入口拒绝（set_user_permission/create_role/update_role），防止已删业务权限（kb.manage 等）重新进入授权。
- 缓存失效策略从 Redis+LRU 改为单进程有界 OrderedDict + revision；角色/用户/授权任何变更 invalidate_all（个人助手单机规模，简单正确优先）。
- 禁用用户即时生效靠 authenticate/snapshot 重查 DB（旧行为仅登录时检查，架构 §6 要求请求级重查）。
- rig.seed_user 经 repository 写入角色/覆盖，等价旧 SQL 播种路径；有效权限仍由服务层计算，测试不手工拼集合。

### 未验证项

- HTTP 端点与旧前端的字段级兼容（分页、字段命名差异）在 Task 15 前端迁移时按 fixture 逐项核对。
- 微信解绑（channel binding）即时失效属 channels 模块（Task 7 验证）。

### schema 版本

`0001_core`（无新增迁移；access 复用首批表）。

### 下一项

Task 4：模型配置与唯一用量计量入口。

---

---

## Task 4：模型配置与唯一用量计量入口 — 2026-11-03 完成（commit `09fe0db`）

**状态：** 已完成（离线测试全绿）。

### 新建文件

- `backend/modules/usage/contracts.py`：`NormalizedUsage`（provider 无关规范化；input=未含缓存输入；prompt=input+cache_read+cache_write；未知字段 None + usage_complete 标志）、`UsageRecord`、`SYSTEM_OWNER_ID=0`、`VALID_SOURCES={chat,memory,evolution,schedule}`。
- `backend/modules/usage/repository.py`：llm_calls 明细 + daily_user_stats **同事务**写入；`stat_date_for` 按 Asia/Shanghai（zoneinfo，tzdata 已装）转换；日汇总一律走差额 UPSERT（`ON CONFLICT DO UPDATE ... + excluded`）；`cleanup_calls_before` 只删明细不动汇总。
- `backend/modules/usage/api.py`：`UsageService`——`begin_call`（请求前分配唯一 call_id；真实重试=新 call_id）、`complete_call`（条件更新 `completed_at IS NULL`，同 call_id 重复回调不重复计）、`report_usage`（晚到/修正按新旧差额一次应用）、`record_call`（组合建账）；查询：明细本人可见、他人/全量需 trace.manage；排行保留 trace.view 语义，输出兼容旧字段（rank/user_id/username/total_tokens/api_calls/active_days）并新增 sources 分布。
- `backend/modules/usage/routes.py`：`/api/usage/ranking|calls|calls/{id}|me/daily`，注入式 authenticate。
- `backend/modules/models/{contracts,repository,api}.py`：chat/auxiliary/fallback 选择；密钥 AES-256-GCM 密文入库（派生盐与旧 crypto_utils 一致，存量密文可解），对外仅掩码；`select_for_run` 不要求管理权限；本机有界健康计数（无 Redis 熔断同步）；`SYSTEM_USER_ID=0` 显式系统主体。
- `backend/platform/migrations/0002_models_key.sql`：`api_key_ref` → `api_key_encrypted` 改名（0001 已提交不可改，遵循 checksum 纪律）。
- `tests/usage/test_calls.py|test_ranking.py`、`tests/models/test_configs.py`。

### 实际命令与结果

```
python -m pytest tests/models tests/usage tests/access tests/storage tests/architecture tests/contracts/test_app_factory.py tests/contracts/test_auth.py -q
→ 106 passed
python -m ruff check <新代码> → All checks passed!
迁移验证：applied=['0001','0002']，model_configs 列含 api_key_encrypted
```

### 计量负责人映射（Task 4 清单要求）

| 模型调用入口 | 计量负责人 | source |
|---|---|---|
| Web/微信聊天主模型（Task 5 runtime 接线） | runtime adapter 在请求前 begin_call、回调 complete_call | chat |
| 记忆提取/整理 | memory 模块调用方（auxiliary 选择） | memory |
| 进化评估/整理 | evolution worker | evolution |
| 定时/提醒生成 | scheduling 触发的 run | schedule |
| 旧 traced_llm / trace_observer | **不迁移直写路径**；旧 observer 对 daily_user_stats 的累加随模块退役删除（Task 15），迁移期不并存两套写入口 | - |

### 关键决策记录

- 日汇总以差额 UPSERT 为唯一写入方式：complete_call 首次累加；report_usage 按 (新-旧) 差额修正；重复提交差额为 0。同回调两次只计一次、NULL 补全一次加量、重试两次计两次均有测试。
- stat_date 按项目时区 Asia/Shanghai 从 UTC 时间转换（UTC 17:00 → 上海次日，已测）；时区规则变更必须重算对应区间汇总（架构 §5.2，实现注释已标注）。
- 系统主体 owner_id=0，排行显示"系统任务"，绝不归属 user_id=1（已测）。
- llm_calls 是计量权威，日汇总是可解释投影；清理明细不影响排行（已测）。重建汇总需覆盖全部明细保留区间。

### 未验证项

- usage routes 未接入 app 工厂（Task 6 显式装配时统一挂载）。
- Hermes 真实请求的 usage 映射（缓存/推理 token）在 Task 5 usage_bridge 联测；本模块的 NormalizedUsage 映射函数（旧 trace_usage 语义）迁移在 Task 5 完成。

### schema 版本

`0002_models_key`（0001 + 0002）。

### 下一项

Task 5：Hermes Runtime Adapter 与 SessionDB 恢复。

---

---

## Task 5：Hermes Runtime Adapter与SessionDB恢复 — 2026-11-03 完成（commit `47dbcd6`）

**状态：** 已完成（离线测试全绿；真实LLM/MCP联调列为integration未验证项）。

### 新建/修改文件

- `backend/runtime/hermes/paths.py`：`ensure_hermes_environment`（sys.path 注入 + HERMES_HOME 设置，幂等；必须在任何 Hermes 模块导入前调用）。
- `backend/runtime/hermes/tools.py`：安全项目工具注册（时间/待办/提醒/时间解析，经 LangChain `invoke()` 官方入口 + thread_id 注入）；`resolve_enabled_toolsets`（废弃 toolset fail-closed 过滤）。
- `backend/runtime/hermes/sessions.py`：`SessionMapper`——app.db `(owner_id, app_session_id)→hermes_session_id` 显式映射（owner 条件在 SQL 内）；`recover_conversation` 经 `SessionDB.resolve_session_id + get_messages_as_conversation(repair_alternation=True)` 只读恢复；压缩轮换 id 候选集；state.db 不可打开 → StorageUnavailableError（缺失=新安装无历史，返回空）。
- `backend/runtime/hermes/usage_bridge.py`：run 前后 `agent.session_*` 计数器差值 → `begin_call/complete_call`（api_calls 存 raw_usage JSON，不重复加总）。
- `backend/runtime/hermes/adapter.py`：`HermesRuntimeAdapter(ExecutionRuntime)`——execute 桥接（stream_delta/reasoning/step 回调 → 队列 → RuntimeEvent 流：token/thinking/tool_started/completed/failed，每轮挂回调 finally 置 None）；agent 缓存键=(owner, session, model_profile, policy_revision, permission_revision, allowed_tools, skills_digest)；LRU 8/闲置15min、运行中不回收；ContextVar `copy_context()` 传播到工作线程且不污染调用方；cancel 走 `agent.interrupt()` 协作取消（不 asyncio cancel）；usage 差值计量。
- `backend/runtime/hermes/agent_factory.py`：真实 AIAgent 构建（base_url 规范化/模型后缀剥离/reasoning_config/fallback链/SessionDB 必传/skip_memory=True/`_skill_nudge_interval=0` 关闭 Hermes 原生后台审查）；密钥解密仅在本层。
- `backend/integrations/mcp.py`：`McpAdapter`——配置归一化（url/凭证引用/allow-exclude glob/超时/结果上限）、错误分类（empty/auth/timeout/connection 明确区分）、refresh 失败保留上一次完整目录、本机健康状态与核心健康隔离（R04）；registrar 可注入（默认 Hermes `register_mcp_servers`）。
- `backend/tools/tools_decorator.py`：`get_project_tools` 移除 KB/KG/SQL/CodeMode/论文 提前导入（R03/R14），仅保留安全7工具；kg 工具移入惰性 `get_kg_tools()`；实测 import 顶层不再拉起 neo4j/pymilvus/chromadb/pymysql。
- `backend/platform/sqlite.py`：**journal 模式修正**——实测发现本机 SQLite 3.45.3 存在 WAL-reset 损坏 bug（Hermes 亦回退 DELETE）；平台按同规则加版本守卫（修复版 3.51.3+/回移 3.50.7/3.44.6 才启用 WAL；已是 WAL 不降级）。
- `backend/modules/models/{api,repository}.py`：新增 `resolve_api_key`（runtime 专用解密，不入日志）。
- 测试：`tests/contracts/test_runtime.py`（Protocol符合性/事件桥接/失败转事件/缓存键7维隔离/LRU运行中保护/ContextVar传播无泄漏/协作取消/usage差值一次计量）、`tests/contracts/test_mcp.py`（9项）、`tests/assistant/test_engine_history.py`（真实临时state.db：owner隔离/恢复顺序/压缩旧id不重复拼接/损坏明确报错）。

### 实际命令与结果

```
python -m pytest tests/assistant tests/contracts tests/storage tests/access tests/usage tests/models tests/architecture -q（等效全量新套件）
→ 133 passed in 45.40s
python -m ruff check backend/runtime backend/integrations ... → All checks passed!
tools_decorator 导入纯净性：无 neo4j/pymilvus/chromadb/pymysql；get_project_tools=7安全工具
```

### 关键决策记录

- **避免旁路**（源自对 hermes_adapter.py 的完整测绘，报告存档于会话）：绕过 run_conversation 直接 registry.dispatch 无 toolset 隔离（闸门在 conversation_loop 的 valid_tool_names）；Hermes 包内互用顶层模块名，必须 sys.path 注入且不可与 backend.hermes 混用；线程池必须 copy_context；禁用 asyncio cancel 强杀；per-agent 配置走构造参数不写全局 config.yaml；不传 session_db 等于静默关闭持久化。
- 会话历史连续性由 agent 绑定的 SessionDB 提供；UI 投影不在 run 时拼接（engine_history 测试覆盖"压缩后不重复"）。
- **Task 2 决策修正**：WAL 启用加版本守卫（原实现无条件 WAL）；tests/storage 断言随规则更新并记录边界值测试。
- 一次 run 一个 call_id 的局限：Hermes 无 per-request usage 回调，agent 多次迭代以 raw_usage.api_calls 记录；per-call 拆分列为后续改进（等 Hermes 暴露 per-request hook）。
- memory/skills 上下文为空可注入（skip_memory=True，原生后台审查关闭）；Task 9/10 通过公开接口桥接。

### 未验证项

- 真实 AIAgent 构造与真实 LLM 对话（需真实模型凭证）——可选 integration。
- 真实 WeKnora MCP 握手（空结果/401/超时/断线重连已用假registrar覆盖语义）。
- run_conversation 真实回调行为（屏蔽规则等）与生产流量的兼容——Task 6 Web 闭环联测。
- skills_digest 当前恒空串（Task 10 接入真实技能版本）。

### schema 版本

`0002_models_key`（无变化）。

### 下一项

Task 6：统一 Assistant、run 状态与 Web 兼容。

---

---

## Task 6：统一Assistant、run状态与Web兼容 — 2026-11-03 完成（commit `1105e38`）

**状态：** 已完成（离线 Web 聊天闭环全绿，FakeRuntime）。

### 新建/修改文件

- `backend/modules/assistant/events.py`：`EventBus`——run 内 seq 单调、token 合并（0.05s 窗口）、环形缓存 256帧/256KiB 取小、终态缓冲 TTL 5min、截断后续传先发 stream_reset。
- `backend/modules/assistant/repository.py`：sessions/runs/conversations 写入口；`create_run` 幂等（UNIQUE(owner,session,source,scope,client_message_id) 命中即 duplicate）；`transition_run` 条件状态机（cancelled 不可被 completed 覆盖）；`finish_run_with_projection`——终态+UI投影+注入回调（投递/学习job）同事务；`request_cancel` 幂等。
- `backend/modules/assistant/dispatcher.py`：唯一前台 worker（active=1，FIFO 天然会话串行）；取消→runtime.cancel 协作取消，完成后仍落 cancelled；**启动对账**——遗留 running/cancel_requested 标 interrupted 并发事件，不重跑有副作用工具；**热循环防护**——执行异常的 run 立即落 failed（发现并修复了 runs 表缺 updated_at 导致的无限重试）。
- `backend/modules/assistant/api.py`：`AssistantService.submit/events(iter_events)/cancel/create_session/get_or_create_session/session_messages/history 管理`；submit 校验 validate_principal+chat.use+会话归属+非空+容量（默认等待32，满则 BusyError）；用户输入先落 conversations 投影供 worker 取回。
- `backend/modules/assistant/routes.py`：旧契约薄适配——GET/POST /chat/stream（token 查询参数/Bearer；thread_id 兼容 `{uid}_{ts}` 旧格式映射 external_chat_id 与新 sess_ id；wx_ 前缀拒绝至 Task 7）、409 busy、`id:{seq}`+`data:` 帧、Last-Event-ID→from_seq=N+1、缓存失效→stream_reset+持久终态（completed 从 conversations 投影取 final_content，不重跑）、chat_complete 后 retry:86400000、GET/POST /chat/cancel、/api/history 列表/详情/改名/删除。
- `backend/bootstrap.py`：run_startup 装配 AssistantService（runtime+access 就绪时）并 seed；run_shutdown 逆序关闭 assistant→runtime→db。
- `backend/platform/migrations/0003_runs_updated_at.sql`：runs 补 updated_at 列（0001 遗漏，条件状态机需要）。
- 测试：`tests/assistant/test_runs.py`（9项：幂等单次执行/投影/跨用户不可见/FIFO顺序/busy/排队取消零执行/运行中取消协作/重启对账/校验）、`tests/contracts/test_web_chat.py`（6项：旧thread_id全流程帧序/409/取消端点/history四端点/未认证401）、`tests/contracts/test_sse.py`（6项：seq单调续传/token合并/截断resync/TTL清理/持久终态）。

### 实际命令与结果

```
python -m pytest tests/assistant tests/contracts tests/storage tests/access tests/usage tests/models tests/architecture -q
→ 152 passed in 46.75s
python -m ruff check <新代码> → All checks passed!
python -m compileall -q backend/modules/assistant backend/bootstrap.py → OK
```

### 关键决策记录

- **Runtime 协议约定**：事件流必须以 completed/failed/cancelled/interrupted 终态事件结束；无终态结束视为协议违规落 failed（FakeRuntime 测试已遵守）。tool_started 有桥接，tool_finished 尚无（Hermes step 回调语义所限），列为后续改进。
- **web busy 语义保留**：Web 契约 409 由容量与队列满触发；同会话并发提交由单 worker FIFO 串行（微信队列语义同源，Task 7 复用）。
- resync 语义：环形缓存缺失时发 stream_reset + 从 conversations 投影取持久 final_content 构造 chat_complete/error 帧——不重新执行 run。
- 修复过程中发现 runs 表缺 updated_at（0001 遗漏）导致条件 UPDATE 报错、worker 对同一 queued run 无限热循环——加迁移 0003 并给 worker 加失败即落 failed + 退避的护栏。

### 未验证项（含范围偏差声明）

- **main.py 切换推迟到 Task 15**：计划要求本任务末切换 main.py 到新工厂；当前旧 main.py 仍承载 100+ 尚未迁移的保留路由（cron/skills/email/platform-config 等），现在切换会使这些入口不可用，违反 A10（先恢复闭环再删旧实现）。Task 15 完成显式注册后一并切换。
- 新工厂 OpenAPI 与 144 条保留路由清单比对：等 Task 15 显式装配后导出核对。
- 真实 Hermes 链路的 /chat/stream 兼容（含 token_refresh、exec_approval 帧）：需真实模型凭证，属 integration。
- check_env.py 等旧启动辅助未动。

### schema 版本

`0003_runs_updated_at`（0001+0002+0003）。

### 下一项

Task 7：微信与多端归一化、身份绑定和持久去重。

---

---

## Task 7：微信与多端归一化、身份绑定和持久去重 — 2026-11-03 完成（commit `72aa14c` + 加固 `5cce711`、`08a4bd7`）

**状态：** 已完成（离线渠道闭环全绿：真实临时 SQLite + FakeTransport/FakeRuntime；真实 iLink 扫码/收发/CDN 未联调）。

### 新建/修改文件

- `backend/platform/migrations/0004_channels.sql`：账号生命周期列（`bot_user_id`/`sync_cursor`/`last_poll_at`/`last_error`）、事件处理结果列（`session_id`/`run_id`/`state`/`error`）、`channel_session_cursors`（每个微信聊天当前指向的 Assistant 会话）。0001–0003 未改动，checksum 不变。
- `backend/shared/crypto.py`：把 AES-256-GCM 部署密钥加解密从 models.repository 抽出为共享 codec（models 保持同名导入，行为不变）；渠道 bot token 只以密文存 `channel_accounts.credentials_ref`。
- `backend/modules/channels/contracts.py`：`ChannelAccount/ChannelBinding/MediaRef/InboundMessage/InboundOutcome/ListenerState/QrSessionView` 等冻结值对象；reason 常量；指纹窗口（默认 5s）、单消息媒体引用上限 10、媒体大小上限 50MB；监听状态 stopped/starting/running/backoff/error（没有假 running）。
- `backend/modules/channels/repository.py`：账号 upsert（按 platform+account_id 幂等）、绑定 upsert/禁用、事件原子插入（`ON CONFLICT(platform,account_id,external_event_id) DO NOTHING`）、会话指针读写、旧事件清理。事件唯一键与表约束一致，重复接收返回既有事件。
- `backend/modules/channels/wechat/parser.py`：iLink msg → InboundMessage；文本拼接、图片/语音/文件/视频只提取下载/解密描述（URL/encrypt_query_param/aes_key/文件名/声明大小），绝不保留字节；媒体引用按内容去重并截断到 10；稳定 `message_id` → `msg:<id>`，否则 `fp:<sha256>:<窗口桶>`，并记录 event_kind=fingerprint（窗口过后相同文本可再次处理）。
- `backend/modules/channels/wechat/account.py`：`IlinkTransport` Protocol + `AiohttpTransport`（GET/POST/流式下载，import 不建连）、iLink 头、`QrLoginManager` 扫码状态机（wait/scanned/confirmed/expired、scaned_but_redirect、过期最多刷新 3 次、内存会话有界）、`send_text`（1800 字符分块、块间 1.2s、ret≠0 抛错）。
- `backend/modules/channels/wechat/listener.py`：每账号一个长轮询 task；真实状态机（starting→running 仅在一次成功轮询后；失败→backoff 并持久化 last_error；errcode=-14→600s 风控退避；账号禁用/缺凭证→error 停止）；游标在消息处理完成后才推进（崩溃最多重复投递，由 channel_events 去重，不静默丢消息）。
- `backend/modules/channels/wechat/media.py`：`MediaFetcher` Protocol + `HttpMediaFetcher`——CDN 下载流式落盘、大小上限、扩展名白名单、AES-128-ECB 解密、sha256 分块计算；失败明确抛 `MediaFetchError`，不影响文字消息。
- `backend/modules/channels/api.py`：`ChannelService`——账号/绑定/扫码/监听管理（system.manage），入站 `handle_inbound`：事件幂等插入 → 账号启用 → 非空 → 绑定（JOIN users 校验状态）→ `access.snapshot_principal + chat.use` → 会话解析 → Assistant.submit(source='wechat')；拒绝也写事件。微信命令 /new /history /N /status /rename /rm /help，/model /send /restart 明确停用；未知 / 命令按旧语义交给模型。
- `backend/modules/channels/routes.py`：`/api/channels/accounts*`、`/listeners`、`/wechat/qr/*`、`/bindings*` 薄路由（认证后调 service，无 SQL）。
- `backend/modules/assistant/{api,repository}.py`：新增 `get_session`（owner 过滤）、`register_attachment`（附件元信息归 assistant）、`find_session_by_external_chat` 支持 source/channel 作用域（两个机器人账号下同一 openid 不共享会话）、`new_attachment_id`。
- `backend/bootstrap.py`：wechat_enabled 且有部署密钥时装配 ChannelService 并启动监听；shutdown 逆序关闭 channels。
- `backend/runtime/hermes/adapter.py`：**顺带修复**——cancel 在没有子 Agent 时不再导入 Hermes `tools.delegate_tool`；确有子 Agent 时先 `ensure_hermes_environment` 再导入。该导入在此前测试中会把 PYTHONPATH 里另一个 `tools` 命名空间包缓存进 `sys.modules`，导致后续 state.db 恢复报 `No module named 'tools.registry'`（本环境实测）。
- 测试：`tests/contracts/test_wechat.py`（26项：未绑定/禁用/解绑、跨账号同 message_id、稳定 ID 去重、两用户同 ID 都执行、指纹窗口不永久吞、解析无字节、媒体上限、附件与 RuntimeRequest、媒体失败不阻塞/纯媒体失败拒绝、/new 切换、命令停用、扫码凭证加密、监听 running/backoff、禁用账号、缺凭证、内部异常撤事件可重投、跨账号 /N 隔离、SSRF 拒绝、HTTP 路由认证/CRUD/QR）、`tests/assistant/test_channel_identity.py`（7项：绑定定 owner 不信昵称、同 openid 跨账号隔离、account_pk 伪造拒绝、未绑定不继承、重绑立即换 owner、跨端同 owner 会话独立、绑定创建/重启用权限）。

### 实际命令与结果

```
python -m pytest tests/architecture tests/contracts tests/access tests/assistant tests/models tests/storage tests/usage -q
→ 185 passed in 56.63s（Task 7 新增 33 项）
python -m compileall -q backend/modules/channels backend/shared/crypto.py
→ OK
git diff --check
→ 无输出（无空白错误）
```

首次全量运行曾出现 3 个 `test_engine_history` 失败，定位为测试执行顺序 + 本机 PYTHONPATH 存在另一个 `tools` 命名空间包；根因是 `adapter.cancel` 未引导 Hermes 环境就导入 `tools.delegate_tool`。按"陷阱 #3"修复后全绿（非本任务业务代码范围，单独说明）。

### 关键决策

- **事件先落、游标后推**：重复投递由唯一键去重，避免"游标已过、消息未处理"的静默丢失；拒绝事件也持久化，防同一条反复处理。
- **指纹窗口桶**：`fp:<hash>:<int(now/5s)>` 同时满足"窗口内去重"与"不永久吞相同文本"；指纹包含发送者、聊天、文本与媒体描述，跨用户/跨账号不互相抑制。
- **会话作用域**：Assistant 会话 `external_chat_id = "<bot_account_id>:<chat_id>"`，并用 `channel_session_cursors` 记住 /new /N 选择；绑定只决定 owner，昵称/openid 不参与归属。
- **媒体只存引用**：渠道层无 `_pending_images/_session_files` 全局字典；引用 → 磁盘 → attachments 元信息。单条消息最多 10 个引用，下载流式落盘，不把 50MB 文件整体读进内存（解密路径受 50MB 上限约束）。
- **凭证保护**：bot token AES-GCM 加密后存 `credentials_ref`，对外只出 has_credentials；扫码 `qrcode` 为可选依赖，缺失时返回 qr_content 而不伪造图片。
- **绑定创建是管理操作**：`bind_user` 一律要求 `system.manage`——任意外部 openid 不能作为自证身份（否则普通用户可抢绑他人微信）；扫码路径 `bind_after_qr` 使用 iLink 真实返回的 `ilink_user_id`，不经该入口。本人只能把**自己的**绑定置为 disabled（解绑），重新启用或操作他人绑定仍需 `system.manage`（commit `5cce711`）。
- **监听错误状态不被 finally 覆盖**：缺凭证/账号禁用导致的 `error` 在任务退出后保留，只有正常取消/普通退出才落 stopped（commit `5cce711`）。
- **内部异常撤事件而不是永久吞**：`handle_inbound` 在事件插入后的任何未预期异常都会删除该事件行再返回 `internal`，平台重投时可重新处理；已成功的 run 由 `client_message_id` 幂等命中，不会重复执行（commit `08a4bd7`）。
- **消息 ID 带发送者作用域**：稳定 ID 去重键改为 `msg:<from_user>:<id>`；账号维度仍由 `channel_events` 唯一键覆盖。这样即使 iLink 的 message_id 只是聊天内唯一，两个用户同 ID 也不会互相吞（commit `08a4bd7`）。
- **入站 URL 防 SSRF**：媒体下载只允许 `weixin.qq.com`/`wechat.com`/`qpic.cn` 的 https 地址，或由 `encrypt_query_param` 构造的固定 CDN 地址；其他 URL 直接拒绝且不发起请求（commit `08a4bd7`）。
- **/N 不跨机器人账号**：`_recent_sessions` 与游标复用都校验 `source=wechat` 且 `channel_account_id==当前账号`；`list_sessions` 补选渠道列（commit `08a4bd7`）。
- **配置接线**：`AppSettings.encryption_secret` 由 `EASYCHAT_ENCRYPTION_SECRET` 显式读取；bootstrap 同时注入 `HttpMediaFetcher`，缺失密钥时打印警告并保持关闭（commit `08a4bd7`）。
- **事件保留有界**：启动时清理 7 天前且非 `received` 的事件；`received` 保留供人工对账（commit `08a4bd7`）。
- **投递边界**：本任务只发送命令回复；run 最终答案的微信投递属于 Task 8（投递账本/分块/uncertain），未提前实现第二套发送路径。
- **路由挂载**：channels 路由构造器已提供，但未在 `create_app` 中挂载；等 Task 15 显式装配，与旧 main.py 保留路由一起切换（沿用 Task 6 的推迟决定）。

### 未验证项

- 真实 iLink 扫码、getupdates 长轮询、sendmessage、CDN 下载与 AES 解密：均需真实凭证，列为 integration，未联调。
- 渠道侧"媒体引用 → attachments → RuntimeRequest.attachment_ids"已测试；Hermes Adapter 如何把 attachment id 还原成图片 content blocks 未在本任务实现，真实多模态对话未验收。
- 微信 run 最终答案的投递（分块/失败重试/uncertain）未接，Task 8 完成。
- `qrcode` 包未安装，QR 图片仅返回内容 URL（前端兼容字段）。
- 群聊/room 语义仅按 chat_id 归一化，未真实联调。
- `/model`、`/send`、`/restart` 命令已停用并提示；如后续需要，应在 models/delivery 模块公开接口上重建，不能回到 handler 直连数据库。
- **channels HTTP 路由尚未挂载**：`build_channels_router` 已实现且有 HTTP 契约测试，但 `create_app` 仍未装配任何模块路由/access 构造（与 Task 6 的 main.py 推迟同一决定）；Task 15 显式装配后才能从真实进程访问账号/扫码接口。
- **队列满（Busy）目前记 rejected 不自动重试**：需要持久重试队列，留给 Task 8 投递/调度；当前只保证不重复执行。
- **指纹窗口桶边界**：重投若恰好跨过 `now//window` 边界会产生新事件并可能再执行一次；概率低，完全消除需要滑动窗口查询，列为后续改进。

### schema 版本

`0004_channels`（0001+0002+0003+0004）。

### 下一项

Task 8：投递账本、文本提醒与持久调度（delivery/scheduling，微信文本 Adapter、occurrence 去重、失败不重跑）。
