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

`（Task 1 提交后回填）`

### 下一项

Task 2：SQLite 平台、版本迁移与首批业务表。

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
