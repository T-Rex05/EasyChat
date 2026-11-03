# EasyChat 依赖盘点（Task 0）

日期：2026-11-03。本文件记录复制基线的实际依赖状态与已确认差异；版本固定与安装入口合并到 Task 15/16 完成。**本盘点不等于已安装验证，目标Linux镜像在 Task 16 重新核验。**

## Python

| 项 | 值 | 依据 |
|---|---|---|
| pyproject requires-python | >=3.10 | 旧pyproject（仓库根目录，原本被.gitignore忽略） |
| 本机开发/运行环境 | Python 3.12.8（pip 26.0.1） | `python --version`，AgentForge 工作区在该环境开发运行 |
| 目标镜像 | Task 16 在 Linux 上安装核验，需与本表关键版本一致 | 实施计划 Task 16 |
| Hermes 运行时 | 内嵌于 `backend/hermes/`，非独立安装包；支持 3.10+（使用 `tomllib`/`tomli` 回退、dataclass slots 等 3.10 特性） | 源码扫描 |

当前环境未安装、但被部分代码引用的包（默认链路未加载或功能未启用）：

- `croniter`：仅 `backend/hermes/cron/jobs.py` 引用；未安装。迁移调度到 `backend/platform/jobs.py` 后评估是否仍需要。
- `weasyprint`、`markdown`：PDF 能力可选依赖，未安装。Task 14 定义 pdf 可选依赖组。
- `tomli`：Python 3.12 自带 `tomllib`，无需安装。

## 关键包：当前环境实测版本 vs requirements.txt 固定值

| 包 | 环境实测 | requirements.txt | 差异处理 |
|---|---|---|---|
| fastapi | 0.143.0 | ==0.121.0 | 以实测为准；Task 15 合并元数据时更新 |
| uvicorn | 0.39.0 | ==0.38.0 | 以实测为准 |
| pydantic | 2.14.1 | >=2.13.4 | 满足约束 |
| openai | 3.29.0 | >=2.24.0,<3.0.0 | **约束冲突**：requirements 的上限过时，实测 3.x 与 langchain-openai 1.7.0 共存运行；Task 15 修正元数据 |
| langchain | 1.0.3 | >=1.0.3 | 一致 |
| langchain-openai | 1.7.0 | >=1.0.2 | 满足 |
| langchain-core | 元数据损坏（version=None）但可导入 | >=1.4.9 | 环境元数据异常，Task 15 重装/锁定时修复 |
| tiktoken | 0.14.0 | ==0.12.0 | 以实测为准 |
| loguru | 0.7.0 | ==0.7.0 | 一致 |
| httpx | 0.28.1 | >=0.27.0 | 满足 |
| PyMySQL | 1.1.2 | ==1.1.2 | **计划移除**（R02 SQLite化，Task 15 删依赖） |
| DBUtils | 未单独核验 | ==3.1.0 | 计划移除（架构§5.4 明确不保留连接池） |
| redis | 7.4.0 | >=5.0.0 | 计划移除（权限缓存改本机有界缓存） |
| apscheduler | 3.11.2 | ==3.11.2 | Task 8 评估：统一调度器是否仍需要 |
| pytest | 9.1.1 | >=8.0.0 | 满足 |
| pytest-asyncio | 1.4.0 | >=0.23.0 | 满足；asyncio_mode 配置在 Task 1 核验写法 |
| ruff | 0.15.12 | dev组 | 满足 |
| mcp | 1.30.0 | 未列 | Hermes MCP 复用所需，Task 15 补入元数据 |
| jsonschema | 4.26.0 | 未列 | 同上 |

结论：requirements.txt 的固定值相对实际运行环境已过时（环境在开发中持续升级未回写）。**复现安装以 Task 15 合并后的 pyproject 为准**；在那之前不按 requirements.txt 重装环境。当前环境共 359 个安装包，其中大量属于已确认移除模块（RAG/评测/图谱），Task 15 随模块删除收敛 core 依赖组。

RAG/评测依赖（ragas、deepeval、langchain-chroma、python-louvain、leidenalg、igraph、jieba、rank-bm25、pypdf、python-docx、python-pptx、openpyxl 等）在 requirements.txt 中启用，但对应模块属确认移除范围（R03/R14）；Task 15 从元数据删除，环境卸载在 Task 16 干净镜像验证时自然脱离。

## 前端

| 项 | 决定 | 依据 |
|---|---|---|
| 包管理器 | **npm**（package-lock.json） | 部署脚本 restart-all.bat / restart-full.bat 均用 `npm run dev`；package-lock.json（2026-09-27）比 pnpm-lock.yaml（2026-09-07）新 |
| 待删除 | pnpm-lock.yaml、pnpm-workspace.yaml | Task 15 执行，避免双锁文件漂移 |
| 构建/检查命令 | `npm run type-check`、`npm run build`（Task 15 执行） | package.json scripts |
| 图谱/论文依赖 | graphology/sigma/vue-flow 等待确认无调用者后删除 | Task 15，删除前先查依赖图 |

## 仓库根目录杂物（复制自旧工作区，保留在磁盘不入基线提交）

`=1.2.2`、`=2.13.4`、`=2.24.0`（Windows 下 `pip install pkg>=x.y.z` 未加引号的 Shell 残留物）、`coverage.xml`、`rubric_result.json`、`test_paper_full.py`、`test_paper_parse.py`（论文复现遗留测试，R14 移除范围）、`out/`（本次盘点扫描产物，gitignore 排除）。均已在 copy-manifest 中登记；磁盘不删（交接文档要求不丢弃复制内容），git 基线通过 .gitignore 排除。

## pyproject.toml 现状问题（Task 15 处理）

- `[project.scripts] agentforge = "agentforge_cli:main"` 指向不存在的 `agentforge_cli` 模块。
- 依赖组缺 pdf/dev 细分，缺 pytest markers 注册（integration/resources）。
- `[tool.pytest.ini_options] asyncio_mode = "auto"`：Task 1 按已装 pytest-asyncio 1.4.0 核验写法（新版推荐 `asyncio_mode = "auto"` 仍受支持，需实际验证）。
