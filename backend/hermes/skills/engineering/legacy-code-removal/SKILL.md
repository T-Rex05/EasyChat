---
name: legacy-code-removal
author: AgentForge
category: AI生成
description: "移除过时/旧版前端或死代码时的安全清理流程。当用户要删除旧 HTML 前端、弃用双前端路由时激活。"
version: 1.0.0
metadata:
  hermes:
    tags: [Engineering, Refactoring]
    requires_toolsets:
      - file
      - terminal
---

# 旧代码 / 旧前端安全移除

当用户要求「删干净」「移除旧版 X」「避免再路由到旧 X 导致报错」时，先把它当**代码迁移/清理**类任务，而不是直接 `rm -rf`。

## 何时使用

- 项目存在新旧双前端（如 Vue/Vite + 旧纯 HTML），用户想淘汰旧前端
- 删除某目录/文件前，想确认没有别的代码还在引用它
- 清理死掉的 fallback 分支、废弃的路由挂载、不再被引用的静态服务代码

## 关键原则

1. **先改源码路由，后删目录。** 移除旧前端的路由逻辑（引用点），再用实际运行验证，最后才做不可逆的目录删除。顺序错了会导致服务在旧目录缺失时崩溃。
2. **删除是破坏性操作，删除前确认 git 状态。** `git ls-files <dir>` 看是否被跟踪，`git status --short <dir>` 看是否有未提交改动。有**未提交的本地修改**时，直接删除会永久丢失——务必向用户说明并让其选择「直接删」还是「先备份再删」。
3. **搜索引用要先做全，别只搜目标字符串本身。** 用 `search_files`（content 模式）找后端/源码里对旧目录的引用；对端口号、目录名都要搜。很多坑是引用藏在 `main.py`、`app.mount`、`config`、`.bat` 启动脚本里。

## 步骤

1. **盘点结构**：确认哪个是新前端、哪个是旧前端（如 `agent_frontend`/Vite vs `agent_frontend_html`/静态）。看入口文件（`main.py`、`run.py`、`app.py`、启动脚本）里前端服务的逻辑。
2. **全量搜索引用**：`search_files` 搜旧目录名 + 相关端口号在源码、配置、`.bat`、`.md` 里的出现。
3. **改源码路由**：用 `patch` 删除/改写对旧前端的 fallback 分支（例：把 `elif os.path.exists(old_frontend_path)` 的整块静态挂载逻辑剪掉）。保留新前端路径（Vite dist）。不要留死引用变量。
4. **验证**：
   - 语法层：`python -c "import ast; ast.parse(open('main.py',encoding='utf-8').read())"`。
   - 启动/导入层：`python -c "import main; a = main.create_app(); print([r.path for r in a.routes if getattr(r,'path','')=='/'])"`，确认只挂载新前端、根路由 `/` 仍在。
5. **删除目录前停下来确认用户**：确认跟踪与未提交状态后，把「直接删 / 先备份再删」两个选项交给用户，不要擅自杀。

## 常见坑

- **端口引用 ≠ 前端目录唯一标识**：有时用户说「8001 的前端」，但 8001 只是后端端口，真正的旧前端是 `agent_frontend_html`。先确认服务于该端口的是什么。
- **`rm -rf` 整个目录前**：务必检查 `git status`。本项目 `agent_frontend_html` 曾带 4 个未提交修改文件，直接删会丢改动。
- **删完要确认没有残留引用**：删目录后 `search_files` 再搜一遍旧目录名应无命中（源码里），确认不会因残留路径报错。
- **验证碰到 loguru 文件锁**（Windows）：`create_app()` 打印日志时若 `logs/audit.log` 被占用会报 `PermissionError`，但应用本身创建成功、路由正常——loguru 的 handler 报错不阻断运行，可忽略。

## 备份示例

确认删除前若需备份：
```bash
cd "<项目根>"
tar -czf "<备份路径>/agent_frontend_html_backup_$(date +%Y%m%d).tar.gz" agent_frontend_html
```
或确认已 `git add` + `git commit` 后再删（此时 git 历史即备份）。
