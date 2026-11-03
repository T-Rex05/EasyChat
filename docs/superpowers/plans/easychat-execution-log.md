# EasyChat 执行日志

执行者按 `EASYCHAT_HANDOFF.md` 与 `docs/superpowers/plans/2026-11-03-easychat-implementation.md` 推进，每任务记录：已完成ID、commit、实际命令/结果、未验证项、schema版本、下一项。

---

## Task 1：公开契约、显式装配与无副作用工厂 — 2026-11-03 完成

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

## Task 0：源基线、依赖及协议盘点 — 2026-11-03 完成

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

## Task 4：模型配置与唯一用量计量入口 — 2026-11-03 完成

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
