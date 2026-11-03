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

---

---

## Task 8：投递账本、文本提醒与持久调度 — 2026-11-03 完成（commit `ba1c79f`）

**状态：** 已完成（离线投递/提醒闭环全绿，FakeSender；真实微信/SMTP 发送未联调）。

### 新建/修改文件

- `backend/platform/migrations/0005_delivery.sql`：`artifacts`（不可变产物引用）、`deliveries`（目标/内容/去重键/状态/重试时刻）、`delivery_parts`（分块 seq 唯一、已发块保留）、`scheduled_jobs`（once/interval/daily + next_run_at）、`scheduled_occurrences`（每计划 scheduled_at 唯一）；`channel_session_cursors` 补 `context_token`。
- `backend/shared/text.py`：渠道发送与投递共用的 1800 字符切分；`channels/wechat/account.py` 改为复用，避免两套规则漂移。
- `backend/modules/delivery/contracts.py`：`DeliveryTarget`、`SendResult`（sent/retry/uncertain/failed）、`DeliverySender` Protocol、`DeliveryLease/View`。
- `backend/modules/delivery/repository.py`：账本写入口；`enqueue_in_transaction` 供助手完成事务与提醒 tick 复用；认领/终态/重试/分块/SQLite 事务内恢复 sending→uncertain；artifacts 最小写读。
- `backend/modules/delivery/api.py`：`DeliveryService`——同 dedup_key 只建一条；发送前 `can_deliver`（解绑/禁用立即停止）；分块逐条发送、已发送块跳过；retry 只重发失败块；uncertain 不自动重发；`enqueue_run_in_transaction` 与 run 终态同事务。
- `backend/modules/delivery/worker.py`：唯一投递 worker；启动时 `recover_inflight`，周期 `tick`，单次最多 100 条，异常不终止循环。
- `backend/modules/delivery/wechat.py`：`WeChatTextSender` 通过 channels 公开方法校验绑定并发送；异常→uncertain。
- `backend/modules/scheduling/{contracts,repository,api,scheduler}.py`：计划 CRUD/权限（cron.create）、once/interval/daily、到期只生成最新未完成实例并记录 missed、occurrence 唯一、tick 内“实例+投递”同事务；`Scheduler` 唯一生命周期入口。
- `backend/modules/channels/`：会话游标保存/刷新 `context_token`、`find_session_route`、`delivery_target_for_run`、绑定有效性检查、`send_wechat_text` 公开发送入口（投递模块不碰 channels 私有表/协议）。
- `backend/bootstrap.py`：装配 DeliveryService/Worker/Scheduler；run 完成回调在 assistant 终态事务内取已落库最终回复并写投递请求；shutdown 逆序停 scheduler→worker→channels→assistant。
- 测试：`tests/delivery/test_delivery.py`（8项：成功一次、分块失败续发、uncertain 不重发、解绑停止、dedup、重启 sending→uncertain、run 完成同事务且重试不重跑、owner 隔离）、`tests/delivery/test_schedule.py`（7项：once 精确一次、interval 错过只补最新、daily 时区、禁用不发、重启不重复、owner/权限、非法输入）。

### 实际命令与结果

```
python -m pytest tests/delivery -q
→ 15 passed in 3.68s
python -m pytest tests/architecture tests/contracts tests/access tests/assistant tests/models tests/storage tests/usage tests/delivery -q
→ 200 passed in 59.94s
python -m ruff check backend/modules/delivery backend/modules/scheduling backend/modules/channels backend/shared/text.py backend/bootstrap.py
→ All checks passed!
```

### 关键决策

- **生成与投递分离**：delivery 只保存/重发已确定内容；run 完成回调在 `finish_run_with_projection` 事务内入队，失败重试不会再次调用 Runtime（测试用 `execute_count` 断言）。
- **分块续发**：`delivery_parts` 以 `(delivery_id, seq)` 唯一；已发送块在重试时跳过，避免重复发送前几段。
- **uncertain 语义**：发送异常/结果未知进入 `uncertain`，不自动重发；进程重启时 `sending` 同样转 uncertain，不假装必达。
- **错过收敛**：interval/daily 到期只生成“最新未完成实例”，`missed` 记录跳过次数；occurrence 唯一键保证重复 tick/重启不重复。
- **提醒目标**：计划保存 kind/ref/channel_account_id；发送前仍校验绑定有效，解绑/禁用后不再发送。
- **唯一调度器**：Scheduler 只在 bootstrap 启动一次；旧 main.py 的 cron 仍在旧进程，等 Task 15 切换时迁移/删除，不新增第二套后台循环。

### 未验证项

- 真实微信文本发送（Task 7 的 send_text + 本模块 Worker）与真实 SMTP（Task 14）：均需真实凭证，integration 未联调。
- 渠道 HTTP/提醒路由尚未挂载；提醒只能由 service/测试触发，Task 15 显式装配后提供入口。
- 邮件/PDF 目标、artifact 发送、分块附件尚未实现（Task 14）。
- 旧 cron 任务没有自动迁移；现有提醒仅覆盖新 API 创建的 once/interval/daily。
- 调度精度为 tick 间隔（默认 1s），未做多进程协调（单 worker 设计）。

### schema 版本

`0005_delivery`（0001–0005）。

### 下一项

Task 9：事实/事件/经验记忆、纠正与遗忘（memory 模块、20 条脱敏用例、中文检索与来源）。

---

---

## Task 9：事实/事件/经验记忆、纠正与遗忘 — 2026-11-03 完成（commit `bebd4cd`）

**状态：** 已完成（离线记忆闭环全绿，真实模型提取未联调）。

### 新建/修改文件

- `backend/platform/migrations/0006_memory.sql`：`memories`（kind/content/source_refs/scope/event_at/version/status/pinned/confidence/source_type/supersedes）、`memory_revisions`（版本历史，UNIQUE(memory_id,version)）、`memory_tags`、`memory_feedback`（UNIQUE(memory_id,source_event_id)）、`forget_rules`（只存 target_hash，不存原文）、`memory_signals`（UNIQUE(owner,source_event_id) 幂等信号）。
- `backend/modules/memory/contracts.py`：`MemoryCandidate/MemoryRecord/SourceRef/RecallResult/ForgetResult/SignalReceipt`；kind/status/source_type/信号常量；80 候选、top5、2000 token 预算；中文同义词表与“旧事”提示词。
- `backend/modules/memory/repository.py`：单 SQLite 写入口；创建即写 revision v1；条件版本更新；反馈幂等；遗忘清空正文并删除全部 revisions（墓碑只留哈希）；信号幂等插入；`purge_deleted_content` 兜底。
- `backend/modules/memory/extractor.py`：候选结构校验 + 保守过滤（来源必填、2–2000 字、假设/转述在 model_inferred 下不写成事实）；`validate_candidate` 同时用于直接构造候选，防止绕过。
- `backend/modules/memory/retrieval.py`：中文 2-gram/单字/ASCII 词 + 同义词扩展；相关性 + 置信度/pin + 近期性；默认只召回 active，查询含“上次/以前/之前/还记得/曾经/过去/早先”才带 archived；top_k/2000 token 预算；0 条明确“无相关记忆（不调用模型编造）”。
- `backend/modules/memory/api.py`：`remember/revise/recall/forget/list/record_feedback/enqueue_signal/apply_signal`；owner + memory.view/edit；expected_version 冲突；遗忘支持 memory_id/source_ref/query 三种选择，按 memory_id 时同时登记内容与来源墓碑。
- `backend/modules/memory/worker.py`：认领 `memory.signal` job，幂等应用；确定性 rejected 不重试，依赖/存储异常 retry。
- `backend/runtime/hermes/memory_bridge.py`：`MemoryBridge.prefetch/remember` 只调 memory 公开接口，无 Hermes import；无结果返回“【记忆】无相关记忆”，有结果带来源。
- `backend/modules/memory/routes.py`：`/api/memory` 列表、`/recall`、`/remember`、`PUT /{id}`、`/{id}/feedback`、`/forget`、`DELETE /{id}` 薄路由。
- `backend/bootstrap.py`：装配 MemoryService + MemoryWorker（JobQueue）；shutdown 逆序停止。
- `tests/fixtures/memory/cases.json`：20 条脱敏用例，覆盖担心/别名/时间/相似事件/短期指令/长期偏好/archived/权限隔离/缺失来源/假设；4 条固定回归。
- 测试：`tests/memory/test_retrieval.py`（9项：20用例核对、命中带来源、相似事件排序、无结果明确、archived 需旧事提示、来源缺失/假设拒绝、同义词、top5+预算、权限隔离）、`test_revision.py`（9项：版本递增、陈旧版本冲突、空修改拒绝、反馈幂等、来源类型保留、信号 job 只处理一次、correct 版本、stage no-op、无来源直接构造拒绝/权限）、`test_forgetting.py`（7项：按 id 清理正文/版本、阻止重提取、按来源级联、按内容、先墓碑后提取、跨用户、已删不可改）、`test_bridge.py`（3项）。

### 实际命令与结果

```
python -m pytest tests/memory -q
→ 29 passed in 8.07s
python -m pytest tests/architecture tests/contracts tests/access tests/assistant tests/models tests/storage tests/usage tests/delivery tests/memory -q
→ 229 passed in 72.82s
python -m ruff check backend/modules/memory backend/runtime/hermes/memory_bridge.py backend/bootstrap.py tests/memory
→ All checks passed!
```

### 关键决策

- **单 SQLite 模型**：fact/preference/event/experience 同表，不做 episodic/semantic 跨库晋升；原始聊天历史仍归 state.db。
- **来源硬门槛**：无 source_refs 的候选直接拒绝（服务层也校验，不依赖路由）；模型推断与用户确认分列 `source_type`/`confidence`。
- **遗忘墓碑**：只存 sha256(target) 与类型，删除正文和全部 revisions；按 memory_id 遗忘时额外登记 content/source_ref 墓碑，阻止旧消息重提取。
- **召回预算**：候选最多 80，top5，2000 token；单条超预算时截断正文并保留来源，不静默丢弃。
- **幂等信号**：`memory_signals` 唯一键 + JobQueue `memory.signal`；worker 只应用一次，rejected 语义（缺来源/已遗忘）不重试。
- **旧 provider/Dreaming**：继续由 Task 5 的 `skip_memory=True` / `_skill_nudge_interval=0` 关闭；本任务不复活旧后台路径。

### 未验证项

- 真实 LLM 自动提取/纠正（需要模型凭证）：未联调；当前只接受显式信号与显式 remember。
- MemoryBridge 尚未注入 Hermes 运行时（Adapter 无 memory_provider 扩展点）；桥接契约与纯格式化已测试，真实会话召回待后续接入。
- 中文检索是 2-gram + 同义词回退，不承诺语义全覆盖；FTS5 加速未启用。
- 记忆 HTTP 路由尚未在 app 工厂挂载（Task 15 显式装配）。
- 衰减/used 信号只记录，不自动物理删除低分记忆（符合架构首版）。

### schema 版本

`0006_memory`（0001–0006）。

### 下一项

Task 10：个人技能、不可变版本与 Hermes 写入桥接（skills 模块、激活 compare-swap、pin/归档、路径与 hash 校验）。

---

---

## Task 10：个人技能、不可变版本与 Hermes 写入桥接 — 2026-11-03 完成（commit `ce3eaf4`）

**状态：** 已完成（离线版本/激活/回滚/权限全绿；真实 Hermes 工具写入路径尚未接线）。

### 新建/修改文件

- `backend/platform/migrations/0007_skills.sql`：`skills`（owner/name 唯一、origin、pinned、archived、active_version_id）、`skill_versions`（版本序号唯一、content_path/hash、parent、source、status）。
- `backend/modules/skills/contracts.py`：`SkillView/SkillVersionView/SkillSnapshot`；来源/状态常量；200KB 内容上限、64 字符名。
- `backend/modules/skills/versions.py`：`SkillContentStore`——版本文件路径只由模块生成的 `skl_/skv_` ID 决定；临时文件 + fsync + `os.replace`；已存在版本拒绝覆盖；读取校验 sha256；拒绝绝对路径/`..`/符号链接/越界。
- `backend/modules/skills/repository.py`：技能/版本写入口；`ensure_skill`、`create_version` 版本序号条件分配、`compare_and_swap_active` 条件更新、pin/归档、按 owner 列表、读取版本。
- `backend/modules/skills/api.py`：`propose`（文件先写、元数据后提交；background/evolution 不得改 pinned；跨 owner 需 skill.manage）、`activate`（先校验版本归属与文件 hash，再 CAS）、`rollback`、`set_pinned/set_archived`、`list/read_active_content/list_for_runtime`；运行时快照固定版本+内容。
- `backend/runtime/hermes/skills_bridge.py`：`SkillsBridge` 只调 skills 公开接口，无 Hermes import。
- `backend/modules/skills/routes.py`：列表/详情/propose/activate/rollback/pin+archive 薄路由。
- `backend/bootstrap.py`：装配 SkillService（内容根 `artifacts/skills`）。
- 测试：`tests/skills/test_versions.py`（不可变文件/显式激活、陈旧指针冲突、回滚、恶意名/路径/符号链接、篡改 hash 阻止激活与读取、缺失文件不破坏旧 active、pin 阻止自动来源、owner/manage 权限、重启恢复、归档、大小限制、parent 归属）、`tests/skills/test_hermes_bridge.py`（桥接只走公开接口/快照 owner 过滤/无 Hermes import）。

### 实际命令与结果

```
python -m pytest tests/skills -q
→ 25 passed in 7.47s
python -m ruff check backend/modules/skills backend/runtime/hermes/skills_bridge.py tests/skills
→ All checks passed!
```

### 关键决策

- **内容路径与用户 name 解耦**：路径由 `skill_id/version_id` 生成，name 只做展示/唯一键；伪造 content_path 会在读取时越界/hash 校验失败。
- **先文件后元数据**：中断只留孤立文件，不覆盖有效版本；active 指针是 DB 权威，坏版本激活前先验 hash，失败不改变旧指针。
- **CAS 激活**：`expected_active_version_id` 条件更新，陈旧期望返回 Conflict，不静默覆盖。
- **pin/归档**：background/evolution 不能改 pinned；用户显式写入仍可；归档不删内容，只从运行时列表隐藏。

### 未验证项

- **File/Terminal/CodeMode/Runner 受保护路径规则尚未接线**：`SkillContentStore` 已拒绝篡改/越界，但通用工具还没有统一的“禁止直接写技能 active 内容”的 guard；需在 Task 13 受限 Runner 或工具层补上。
- Hermes 原生 `skill_manage` 与后台 review 仍走旧写入路径；SkillsBridge 已提供 propose/activate，但 Adapter 尚未注入，Task 15 前不得声称三条写入口已统一。
- 既有 `skill_usage` 侧写数据未迁移/未读兼容；本任务只建立新技能/版本权威。
- 技能 HTTP 路由尚未挂载（Task 15）。
- 真实并发多进程激活只测到同进程模拟的陈旧期望。

### schema 版本

`0007_skills`（0001–0007）。

### 下一项

Task 11：唯一学习调度、证据与预算（evolution 模块、去重、暂停/撤权、预算预留核销）。

---

---

## Task 11：唯一学习调度、证据与预算 — 2026-11-03 完成（commit `401ba91`）

**状态：** 已完成（离线学习调度/预算全绿；真实 LLM 学习与候选生成留给 Task 12）。

### 新建/修改文件

- `backend/platform/migrations/0008_evolution.sql`：`evolution_tasks`（owner+source_event 唯一、证据 JSON、预算字段、状态）、`evolution_experiences`（经验/条件/反例/置信度/来源）、`evolution_budgets`（按上海日期 + 用户唯一，reserved/used）。
- `backend/modules/evolution/contracts.py`：`LearningEvidence/LearningResult/EvolutionTaskView/ExperienceView`；`SYSTEM_USER_ID=0`；明确禁止 `source=evolution` 自触发。
- `backend/modules/evolution/budget.py`：每日 20k/单次 5k 默认；发送前预留、已知 usage 释放+计入、未知 usage 保留预留；按项目时区日切；跨实例持久化。
- `backend/modules/evolution/repository.py`：任务幂等插入（同 owner/source_event 一条）、证据读取、状态/预算更新、经验写入、暂停开关（app_settings）。
- `backend/modules/evolution/evidence.py`：默认确定性 learner（不调用模型）把反馈整理为经验；用户确认与模型推断分列。
- `backend/modules/evolution/api.py`：`enqueue_feedback`（chat.use；自触发拒绝）、`enqueue_system_feedback`（owner=0）、`pause/resume`、`process_task`（暂停不处理、禁用/撤权拒绝、超预算 paused、未知 usage 保留预留、经验写入）。
- `backend/modules/evolution/worker.py`：唯一 `evolution.learn` worker，单并发 claim；暂停时不认领；lease 恢复沿用 JobQueue。
- `backend/bootstrap.py`：装配 EvolutionService/Worker + BudgetManager；shutdown 逆序停止。
- 测试：`tests/evolution/test_signals.py`（重复反馈只学一次、禁用/撤权阻止、暂停、自触发拒绝、系统主体、过期 lease 恢复）、`tests/evolution/test_budget.py`（预留/核销、未知 usage、日/单次上限、日切、持久化、超预算不发 learner）。

### 实际命令与结果

```
python -m pytest tests/evolution -q
→ 13 passed in 3.71s
python -m pytest tests/architecture tests/contracts tests/access tests/assistant tests/models tests/storage tests/usage tests/delivery tests/memory tests/skills tests/evolution -q
→ 267 passed in 88.76s
python -m ruff check backend/modules/evolution tests/evolution
→ All checks passed!
```

### 关键决策

- **唯一后台并发**：单 EvolutionWorker；暂停开关在 claim 前检查，避免“暂停后仍认领”。
- **不学自己**：`source='evolution'` 直接拒绝；学习完成不递归入队。
- **预算先预留**：LLM 调用前 reserve；未知 usage 保留预留直到对账，不立即返还；超预算任务标 paused 而不是继续调用。
- **系统主体**：`SYSTEM_USER_ID=0` 显式传入，不猜 user_id=1；系统任务跳过用户权限校验但仍走预算。
- **证据可追溯**：任务保存 run/source/feedback/反例；经验记录 `source_type`，模型自评不当用户事实。

### 未验证项

- 真实 LLM 学习/候选生成：Task 12；默认 learner 只做确定性整理，tokens_used=0。
- 暂停任务不会在恢复后自动重新入队（当前需新信号或手动处理）；超预算 paused 同样需人工/后续策略。
- 学习预算与 usage 模块的真实 token 计量尚未对接（Task 12 接真实调用时需沿用唯一计量入口）。
- 进化 HTTP 路由尚未挂载（Task 15）。

### schema 版本

`0008_evolution`（0001–0008）。

### 下一项

Task 12：候选生成、回放比较、激活与回滚（proposal/validation/adoption、回归 fixture）。

---

---

## Task 12：候选生成、回放比较、激活与回滚 — 2026-11-03 完成（commit `6ee4973`）

**状态：** 已完成（离线验证/采用/回滚全绿；真实模型候选与真实回放未联调）。

### 新建/修改文件

- `backend/platform/migrations/0009_evolution_validation.sql`：`evolution_validations`（baseline/candidate/report/passed）与 `evolution_adoptions`（adopt/rollback/keep 证据）。
- `backend/modules/evolution/proposal.py`：`ProposalService` 只调用 `skills.propose`，候选内容由注入 builder 产生，不拼提示词、不写文件。
- `backend/modules/evolution/validation.py`：固定顺序——schema/版本归属 → baseline 与 candidate 同环境回放 → 必需用例 → 回归/改善判定；`ValidationReport/CaseOutcome/RegressionCase`；无基线不能证明无回归；坏内容不可读即失败。
- `backend/modules/evolution/adoption.py`：验证通过才 CAS 激活；pin 技能自动采用直接保留原版；陈旧 expected 由 skills.activate 抛 Conflict；验证/采用/回滚写证据；回滚恢复旧 active。
- `backend/modules/evolution/routes.py`：经验列表 + 显式回滚薄路由。
- `backend/modules/skills/api.py`：新增 `get_version/read_version_content` 公开读取（仍校验归属与 sha256），验证回放不需要碰内部 repository。
- 测试：`tests/evolution/test_validation.py`（通过/原版更好/无改善/无基线/回放零副作用）、`test_adoption.py`（采用+回滚、失败保留、pin 不自动改、陈旧指针 Conflict）、`tests/fixtures/evolution/regression.json`（4 用例）。

### 实际命令与结果

```
python -m pytest tests/evolution -q
→ 22 passed in 7.19s
python -m pytest tests/architecture tests/contracts tests/access tests/assistant tests/models tests/storage tests/usage tests/delivery tests/memory tests/skills tests/evolution -q
→ 276 passed in 116.56s
python -m ruff check backend/modules/evolution tests/evolution
→ All checks passed!
```

### 关键决策

- **验证与采用分离**：报告可重放；采用只切 active 指针，证据写 `evolution_adoptions`。
- **无基线不采用**：新技能没有 baseline 时无法证明“无回归”，验证失败；纯修复候选需目标用例转通过。
- **自动采用不碰 pin**：pinned 技能即使验证通过也返回 None 并记 keep；用户显式操作走 skills API。
- **回放零副作用**：replayer 注入纯函数/替身，测试断言没有 deliveries/runs 行。
- **陈旧父版本**：CAS 冲突向上抛，不覆盖新 active。

### 未验证项

- 真实模型候选生成（复用 Hermes review 提示）未接入；proposal 只接受注入 builder。
- 真实回放需要无副作用执行器；当前测试用纯函数，Task 13 Runner 验收后才可声明真实自动执行。
- 验证报告/采用证据的 HTTP 查询与审批 UI 未实现；进化路由未挂载。
- 观测到激活后失败自动回退的监控循环未实现（仅提供显式 rollback）。

### schema 版本

`0009_evolution_validation`（0001–0009）。

### 下一项

Task 13：脚本 Runner 与权限范围（受限执行契约、假 Runner、Linux 隔离验收保持关闭）。

---

---

## Task 13：脚本 Runner 与权限范围 — 2026-11-03 完成（commit `5044c61`；真实隔离未验收）

**状态：** 契约与默认关闭实现完成；真实 Linux 隔离验收未执行，自动执行保持关闭。

### 新建文件

- `backend/modules/evolution/runner_contracts.py`：`RunnerLimits`（deadline/memory/output 校验）、`RunnerCapabilities`（read/write/network/env 白名单）、`RunnerInput`（artifact/workspace/argv/input artifacts，不接收整包凭证）、`RunnerResult`（exit/timeout/denied/error + 受限 stdout/stderr + artifacts）、`ScriptRunner` Protocol。
- `backend/integrations/script_runner.py`：`DisabledScriptRunner`（默认 denied）；`LocalSubprocessRunner`（仅 Linux、显式 enabled、workdir/读写路径根内校验、拒绝网络能力、env 白名单排除密钥、超时硬终止、输出截断）；`build_default_runner` 无 `bwrap`/非 Linux/未启用一律 disabled。
- 测试：`tests/evolution/test_runner_contract.py`（限制值校验、默认 denied、假 Runner 流程、路径/网络拒绝、未启用拒绝）、`tests/integration/test_linux_runner.py`（integration 标记；Linux 真实越界/超时验收，未通过时自动执行保持关闭）。

### 实际命令与结果

```
python -m pytest tests/evolution/test_runner_contract.py -q
→ 5 passed in 0.34s
python -m pytest tests/architecture tests/contracts tests/access tests/assistant tests/models tests/storage tests/usage tests/delivery tests/memory tests/skills tests/evolution -q
→ 281 passed in 87.36s
python -m ruff check ...
→ All checks passed!
```

### 关键决策

- **默认 disabled**：没有通过隔离验收的 Runner 时，任何执行请求都返回 denied；不把“子进程 + 参数过滤”当成安全隔离。
- **能力显式**：RunnerInput 只给 artifact/workspace/argv 与显式能力；不携带 API key/SMTP 密码/部署密钥。
- **本地 Runner 有边界**：拒绝网络能力（无法强制网络隔离）；workdir/读写路径必须在 workspace/artifacts 根内；超时 kill + wait 回收。

### 未验证项

- **真实 Linux 隔离未验收**：未安装/验证 bubblewrap 等隔离；`tests/integration/test_linux_runner.py` 未在目标 Linux 运行，自动执行保持关闭。
- 生成/静态检查/执行验证三种状态尚未接入 UI/记录；未连接候选激活流程。
- 环境凭证不可见/内存限制/输出限制只在代码路径实现，未做真实攻击样例验证。
- Remote Runner 未实现。

### schema 版本

无新迁移（0001–0009）。

### 下一项

Task 14：邮件/PDF 按需启用与历史任务兼容（SMTP 配置/收件人、PDF artifact、失败只重发文件）。

---

---

## Task 14：邮件/PDF 按需启用与历史任务兼容 — 2026-11-03 完成（commit `10ffc03`）

**状态：** 已完成（离线 SMTP/PDF 能力全绿，假 SMTP/假渲染器；真实发信与真实渲染未联调）。

### 新建/修改文件

- `backend/platform/migrations/0010_delivery_email.sql`：`email_configs`（单行全局配置，password 只存密文）、`email_recipients`（owner+address 唯一、active）；`deliveries` 补 `subject`。
- `backend/integrations/pdf.py`：`PdfRenderer` Protocol、`DisabledPdfRenderer`（明确 CapabilityUnavailable）、`SubprocessPdfRenderer`（独立 Python 子进程 + 超时 kill + 临时 HTML 清理，不把 weasyprint 依赖带进主进程）、`build_pdf_renderer`（未启用/缺依赖保持 disabled）。
- `backend/modules/delivery/smtp.py`：`EmailRepository`（AES-GCM 密码、掩码视图、收件人 CRUD）、`EmailService`（system.config / system.manage 权限）、`SmtpEmailSender`（默认关闭；未启用不建连；文本/PDF 附件；超时→retry、认证/收件人→failed、连接后未知→uncertain；环境凭证不进日志）。
- `backend/modules/delivery/reports.py`：`ReportService`——先渲染成不可变 artifact 再入投递账本；邮件失败只重试同一文件，不重新渲染。
- `backend/modules/delivery/{api,contracts,repository}.py`：deliveries 支持 `subject` 与 artifact 附件发送；`_deliver_artifact` 校验产物存在、发送器支持附件，失败分类沿用 sent/retry/uncertain/failed。
- 测试：`tests/delivery/test_email.py`（配置加密/掩码、system.config 权限、默认不建连、假 SMTP 发送、timeout/auth/uncertain 分类、PDF 附件、缺失附件不发信、收件人权限/停用）、`tests/delivery/test_reports.py`（artifact+邮件投递不重渲染、投递后文件保留、PDF 关闭明确失败且不建 artifact、渲染超时明确失败、能力默认 lazy disabled）。

### 实际命令与结果

```
python -m pytest tests/delivery -q
→ 27 passed in 7.51s
python -m pytest tests/architecture tests/contracts tests/access tests/assistant tests/models tests/storage tests/usage tests/delivery tests/memory tests/skills tests/evolution -q
→ 293 passed in 95.03s
python -m ruff check backend/integrations/pdf.py backend/modules/delivery ...
→ All checks passed!
```

### 关键决策

- **能力默认关闭**：PDF 未启用/缺 weasyprint → disabled，不 import 渲染栈；SMTP 未启用 → `can_deliver=False`，连 socket 都不建立。
- **生成与投递分离**：先渲染 artifact 并登记 hash/size/MIME，再入投递账本；发送失败重试同一文件，禁止重新渲染或重跑 Agent。
- **发送结果分类**：连接/超时→retry；认证/收件人拒绝→failed；连接后异常→uncertain；不把“可能已发”记成必达。
- **凭证保护**：SMTP 密码只存 AES-GCM 密文，视图只出掩码；邮件配置接口要求 system.config，跨用户收件人要求 system.manage。

### 未验证项

- 真实 SMTP 发信（需用户提供测试端点）与真实 PDF 渲染（weasyprint/字体）未联调，均属 integration。
- SMTP 配置/收件人路由尚未挂载（Task 15）。
- 旧 PDF 任务格式只做了 artifact/字段兼容，未导入旧库历史任务；迁移策略留到 Task 15。
- 附件仅支持 PDF；邮件正文分块、退信解析、DKIM 未实现。

### schema 版本

`0010_delivery_email`（0001–0010）。

### 下一项

Task 15：前端、API 契约与旧模块删除（显式路由装配、旧 mapper/provider 清理、前端构建验证）。

---

---

## Task 15（部分完成）：显式路由装配与 API 兼容守卫 — 2026-11-03（commit `986c5d3`）

**状态：** 后端装配部分完成；前端迁移、旧模块删除、main.py 切换**尚未完成**，Task 15 不标完成。

### 已完成

- `backend/app.py`：`_LazyModule` 请求期解析模块（未就绪→503）；`_register_explicit_routers` 显式挂载 access/usage/assistant(Web SSE+history)/channels/memory/skills/evolution；不再扫描 `backend/controller`。
- `backend/bootstrap.py`：启动时自动构造 AccessService（JWT secret 缺省进程内随机）+ UsageService（注入 `lambda principal: access.effective_permissions(principal.user_id)`）；可选 `hermes_enabled` 构造 Runtime；shutdown 释放 access/models/usage，保证再次 lifespan 重建（修复重启幂等测试）。
- `backend/platform/settings.py`：`jwt_secret`、`hermes_enabled` 显式环境配置。
- 测试：`tests/contracts/test_api_compatibility.py`（显式路由/health/ready、注册登录、memory/skills/usage、未就绪 503、旧前缀不暴露）、`tests/architecture/test_removed_dependencies.py`（新装配路径不得 import backend.rag/graphrag/service.kb/controller/pymysql/dbutils/redis/neo4j/pymilvus/chromadb）。

### 实际命令与结果

```
python -m pytest tests/contracts/test_api_compatibility.py tests/architecture/test_removed_dependencies.py -q
→ 6 passed
python -m pytest tests/...（新套件） -q
→ 299 passed in 100.85s
ruff check（app/bootstrap/settings/新测试）→ All checks passed
```

### 未完成（Task 15 剩余）

- **前端未迁移**：`agent_frontend/node_modules` 不存在，无法离线执行 `npm run type-check/build`；聊天/Token/技能/提醒/记忆/进化页面与菜单未收敛。
- **旧模块未删除**：`backend/controller|service|db|rag|graphrag` 等仍在；旧 main.py 仍可启动旧系统，未切换；旧 mapper/provider/MySQL 启动未清理。
- **路由兼容未全量核对**：新 app OpenAPI 与 144 条保留路由的逐条比对未完成；旧测试/样本未删除。
- main.py 切换与旧桥接删除必须在前端/保留路由迁移后执行，否则会切断 cron/skills/email 等入口（A10）。

### schema 版本

无新迁移（0001–0010）。

### 下一项

继续 Task 15 剩余：前端页面/API 收敛、旧模块删除与 main.py 切换；之后 Task 16 干净镜像/资源/交付。

---

---

## Task 15（继续）：前端页面收敛与提醒/邮件/投递 API — 2026-11-03（commit `80f0327`）

**状态：** 前端移除与构建验证完成；旧后端模块删除/main.py 切换仍未完成。

### 已完成

- 前端删除 KB/RAG 测评/图谱/图谱审核/社区/技能池/论文复现页面与 API 模块（`kb.ts`、`kbEval.ts`、`graphrag.ts`、`notification.ts`），router/菜单/权限判断同步移除；移除 `@vue-flow/*`、graphology、sigma、vis-* 依赖并更新 package-lock。
- 新增后端 HTTP 面：`/api/schedules`（提醒 CRUD/停用/实例，默认目标取有效微信绑定，可显式邮箱）、`/api/email/config`+`/recipients`（密码掩码）、`/api/deliveries`（只读状态）；app 显式挂载。
- `backend/server.py`：新架构启动入口（`uvicorn backend.server:app`），import 不连库/不迁移。
- 投递更稳健：无渠道时构造 `DisabledDeliverySender` 账本仍可用；email/report 独立于微信装配。
- 测试：`tests/contracts/test_frontend_compat.py`（前端不得再引用已删 API/路由/依赖）、`test_api_compatibility.py` 扩展 schedules/email/deliveries 路径与 503/权限语义。
- 前端验证：`npm run type-check` 通过；`npm run build` 通过（仅 chunk 大小警告）。

### 实际命令与结果

```
npm ci --ignore-scripts --no-audit --no-fund → added 161 packages
npm run type-check → 通过（0 errors）
npm run build → ✓ built in 12.99s
python -m pytest tests/...（新套件） -q → 302 passed in 107.30s
ruff check（app/bootstrap/routes/新测试）→ All checks passed
```

### 未完成

- **旧后端模块未删除**：`backend/controller|service|db|rag|graphrag`、旧 mapper/provider、MySQL 启动仍在；旧 main.py 未切换。
- 144 条保留路由与新 OpenAPI 的逐条核对未完成；旧测试/样本未删除。
- 前端尚未新增提醒/进化/投递管理页面（API 已就绪；当前只有核心页面收敛）。
- 真实浏览器联调未做（仅 type-check/build）。

### 下一项

完成旧后端删除/main.py 切换与保留路由核对，然后 Task 16 干净镜像/资源/恢复/最终交付。

---

---

## Task 15（继续 2）：模型配置/fallback 兼容路由 — 2026-11-03（commit `0367cca`）

**状态：** Config 页所需核心模型配置 HTTP 契约已迁移；旧后端删除/main.py 仍未完成。

### 已完成

- `backend/modules/models/routes.py`：`GET/POST /api/model-configs`、PUT（更新/激活/多模态）、DELETE、fallback-chain GET/PUT；旧字段（config_name/config_type/api_url/model_name/category）映射到 ModelsService。
- embedding/场景路由/reasoning-effort 批量设置/真实连通性测试明确 503（能力已移除或需外网），不伪装成功。
- bootstrap：有部署密钥时构造 ModelsService（`permission_check=access.require_permission`）；app 显式挂载模型路由。
- 测试：API 兼容路径集合加入 model-configs/fallback；离线全量 302 passed。

### 未完成

- **旧后端模块仍未删除/main.py 未切换**；保留路由仍缺 cron/email/memory-items/skills 旧别名、上传/反馈/exec-approval、host/command 黑名单等；144 路由逐条核对未完成。
- 模型真实连接测试、场景路由 UI 未迁移。

### 下一项

继续 Task 15 的保留路由迁移与旧模块删除；随后 Task 16。

---

---

## Task 16：干净镜像、资源、恢复与最终交付 — 2026-11-03 完成（部署部分，commit `979187d` + `94dbf38`）

**状态：** 单 worker 镜像已真实构建/启动/健康检查通过；Hermes 启用模式启动通过；SPA 可访问；资源采样通过。Task 15 的旧模块删除仍未完成，因此整体交付不标“全部完成”。

### 已完成

- `docker/Dockerfile`：多阶段（Node 构建前端 → Python 3.12-slim runtime），单 worker `uvicorn backend.server:app`，健康检查 `/healthz`。
- `docker/requirements-core.txt`：仅 fastapi/uvicorn/pydantic/httpx/cryptography/aiohttp/tzdata，无 MySQL/Redis/Neo4j/Milvus/RAG；`requirements-hermes.txt` 提供 Hermes 运行时依赖（openai/langchain-core/tiktoken/loguru/pytz 等）。
- `docker/docker-compose.yml`：只有 easychat + `easychat_data` 卷；无外部数据库；内存 limit 1G；单副本。
- `.dockerignore` 修正：排除 node_modules/data，但保留前端源码/锁与 operations.md。
- `backend/app.py`：存在 `static/index.html` 时最后挂载 SPA，不吞 API 路由。
- `backend/runtime/hermes/tools.py`：按 vendored Hermes `ToolRegistry.register(name, toolset, schema, handler...)` 修正注册参数（原 parameters/description 旧假设在镜像中暴露）。
- `docs/architecture/operations.md`：构建/启动、数据权威、能力开关、单 worker、备份恢复、资源目标与未验证项。
- `tests/resources/test_resource_sample.py`：真实 uvicorn 子进程 + psutil RSS 采样（marker=resources）。

### 实际命令与结果

```
docker build -f docker/Dockerfile -t easychat:test . → 成功（image 496MB）
docker run ... easychat:test → /healthz 200 /readyz ready
GET / → 200（前端 SPA）
容器内注册/登录 /api/auth/me、/api/memory、/api/skills → 200
docker stats --no-stream → easychat 40.44MiB RSS（空载，目标 <1GiB）
EASYCHAT_HERMES_ENABLED=true 容器 → /readyz ready（Hermes Runtime 启动成功）
docker compose -f docker/docker-compose.yml config --quiet → OK
python -m pytest tests/resources -m resources -q → 1 passed
python -m pytest tests/...（新套件） -q → 302 passed
```

### 未验证/限制

- 真实 LLM 对话未联调（镜像无模型配置/API key）；Hermes 启用启动已通过，但真实 API 调用未验收。
- 真实微信/MCP/SMTP/PDF 未联调；邮件/PDF 可选依赖未安装到镜像（按需构建）。
- Docker 构建依赖外部网络拉取 base image/依赖；资源测量是空载值，不是压力测试结论。
- Task 15 旧模块删除/main.py 切换仍未完成，镜像使用新入口但仓库仍保留旧代码。

### schema 版本

`0010_delivery_email`（0001–0010；Task 16 无新迁移）。

### 下一项

Task 15 收尾：迁移/删除旧路由与旧模块、切换 main.py、144 路由核对；然后整体里程碑四验收。

---

---

## Task 15（继续 3）：记忆页迁移到新 API — 2026-11-03（commit `27da0d3`）

### 已完成

- 新增 `agent_frontend/src/views/MemoryView.vue`：列表、检索（/recall）、新增（/remember，强制来源）、按版本修订、遗忘（墓碑）；不再使用旧 `/api/memories*` 形状。
- 路由 `/memory` 指向新页，删除 `/memory-dashboard`；侧边栏移除“记忆监控”。
- 删除 `MemoryItemsView.vue`、`MemoryDashboardView.vue`、`api/memoryItems.ts`、`api/memory.ts`；前端契约测试新增旧路径/文件断言。
- 验证：`npm run type-check`、`npm run build` 通过；全量 302 passed。

### 未完成

- Skills/Cron(ChatSidebar)/Trace/Admin 前端仍用旧 API 形状；旧 memory-items 后端 controller 未删除（留待 main 切换时统一清理）。
- 旧后端模块/main.py 未切换。

### 下一项

继续迁移 Skills 页与提醒入口，再删除旧模块并切换 main.py。
