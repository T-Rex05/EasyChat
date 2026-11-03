---
name: mysql-backend-extension
author: AgentForge
category: AI生成
description: "扩展/改 FastAPI+MySQL 后端：加列双写、GROUP BY 排序、中文 JSON 测试。"
version: 1.0.0
metadata:
  hermes:
    tags: [Backend, FastAPI, MySQL, SQL, SchemaEvolution, Testing]
    requires_toolsets:
      - terminal
---

# FastAPI + MySQL 后端功能扩展与深坑

用于「在现有 Python-FastAPI-MySQL 后端上新增/修改功能」（典型场景：AgentForge 项目）时，需要遵守的 schema 演进、SQL 写法、数据库连接与测试方法。聚焦后端，前端状态坑见 `event-driven-state-debugging`。

## 何时使用

- 给某张表加一个新列（或字段），并让 API 能读写它。
- 新增/修改 `UPDATE`/`INSERT`/`SELECT` 却只改了 SQL、没同步建表语句。
- `pymysql.err.OperationalError (1055 ... only_full_group_by)`。
- Windows 下 `curl` 发中文 JSON body 报 `'utf-8' codec can't decode`。
- 新建一个自包含的控制器（绕过不兼容的 mapper/旧体系），含建表、CRUD、加密、测试端点、前端列表+表单。 → 参考模板 `references/model-config-controller-pattern.md`。

## 核心规约

1. **改列要「数据库 + 建表语句 + 所有 mapper 类」三写**。只 `ALTER TABLE` 改当前库，重建库时列会丢；只改 `CREATE TABLE`，现有库不会加上；改了建表语句但没改 mapper 类的 `INSERT`/`SELECT`，运行时报 `unexpected keyword argument`。
   - 对现有库执行**幂等 ALTER**（先查 `SHOW COLUMNS`，不存在才 `ADD COLUMN`）。
   - 同步更新项目里所有版本的建表语句（本项目 MySQL 有 `backend/db/mysql_impl.py` 与 `backend/db/schema.py` 两处，都要加）。
   - **⚠️ 本项目有三套 mapper**：`MySQLMapper`（`backend/db/mysql_impl.py`）、`ConversationStore`（`backend/db/conversation_store.py`）、以及 `schema.py` 的建表 DDL。三者都实现了 `insert_conversation` / `get_conversations_by_session` 等方法，签名和 SQL 各自独立。加列时必须**全部同步**，否则运行时 `insert_conversation() got an unexpected keyword argument 'xxx'`。排查此类错误时 `grep -rn 'def insert_conversation' backend/db/` 定位所有实现。
2. **一个会话可能对应多行**（如 `conversations` 按 `session_id` 分组）。按会话更新的字段（如会话标题 `session_title`）要 `UPDATE ... WHERE session_id=%s` 更新该会话所有行，并 `SET ... , updated_at = CURRENT_TIMESTAMP`。
3. **改完后，读列表/读单条的 SQL 也要带上/优先新字段**，否则改了也显示不出（标题优先级常是「自定义字段 > 首条内容」）。

## MySQL ONLY_FULL_GROUP_BY 坑

`GROUP BY` 时 `ORDER BY` 引用**非聚合列**会报：

```
pymysql.err.OperationalError: (1055, "Expression #1 of ORDER BY clause ... not in GROUP BY clause and contains nonaggregated column ... incompatible with sql_mode=only_full_group_by")
```

- 修法：`ORDER BY` 改用聚合列，如 `ORDER BY MIN(created_at)` / `MAX(updated_at)`。
- 凡是 `GROUP BY` + `ORDER BY` + `MAX(x) as alias` 组合，别在 `ORDER BY` 里直接写裸列名。
- 先在 `python -c` 里用项目同款连接参数跑一遍 SQL 确认合法，再进控制器（本会话就是这么定位的）。

## Windows 下测试中文 JSON body 的正确姿势

**症状**：Windows git-bash 里 `curl -d '{"title":"中文"}'` 报

```
{"detail":"'utf-8' codec can't decode byte 0xb2 in position 10: invalid start byte"}
```

**根因**：shell 把内联 `-d` 的中文字节按 GBK 编码送出，后端按 UTF-8 解就崩。**这是测试姿势问题，不代表后端/接口坏了**——浏览器端 axios/fetch 恒用 UTF-8，不会踩到。

**正确做法**：用 Python `urllib.request` 构造 UTF-8 body 测试：

```python
import json, urllib.request, urllib.error
body = json.dumps({'title':'中文标题'}).encode('utf-8')
req = urllib.request.Request(url, data=body, method='PUT',
    headers={'Content-Type':'application/json; charset=utf-8','Authorization':'Bearer '+token})
try:
    resp = urllib.request.urlopen(req, timeout=5)
    print(resp.status, resp.read().decode())
except urllib.error.HTTPError as e:
    print('HTTPError', e.code, e.read().decode())
```

测试留下的脏数据要清理（把测试用的新字段值 `UPDATE ... SET 字段=NULL` 还原），别污染线上数据。

## 验证流程（后端改动）

1. `python -c "import ast; ast.parse(open('...py', encoding='utf-8').read())"` 语法检查。
2. 用项目 `pymysql` 连接参数直接跑新 SQL，确认不报 `ONLY_FULL_GROUP_BY`、影响行数符合预期。
3. 跑真实 API（login 拿 token → PUT/DELETE/GET），并用 DB 抽查字段是否真的写入/读出。
4. 改的是 Python 文件时需**重启后端进程**（本项目 `reload=False`，不热加载）；只改前端则 `npm run build` 重出 dist，后端从磁盘实时服务新包。
5. **前端 type-check 跑 `vue-tsc --noEmit` 后过滤到你的文件**（如 `grep -i "ChatSidebar"`）——全量跑会输出一个 pre-existing 的 `tsconfig.json baseUrl` 弃用错误，与业务代码无关。只关心你改的文件是否零报错。

## 本项目环境要点（AgentForge）

- `DB_TYPE=mysql`，MySQL 库 `agentforge`；`conversations` 表结构在 `backend/db/mysql_impl.py` 与 `backend/db/schema.py`。
- 连接参数在 `.env`（MYSQL_HOST/PORT/USER/PASSWORD/DATABASE）；测试脚本可 `import pymysql` 直连。
- 认证：`POST /api/auth/login` 拿 token，后续请求带 `Authorization: Bearer <token>`；默认管理员 `admin / admin123`（仅测试/开发）。
- 会话表 `conversations` 无 `session_title` 时，`PUT /api/history/{chat_id}`（重命名）会因列不存在失败——需先加列。

## 相关技能

- `event-driven-state-debugging` — 同一项目的 Vue 前端状态 bug（点击/选中、受控 `<details>`）。后端与前端分别排查，互不混为一谈。

## 参考文件

- `references/session-rename-recipes.md` — 端到端示例：给历史会话加"重命名标题"功能（加列、修 UPDATE、读列表优先新字段、前端 inline 编辑）。
- `references/model-config-controller-pattern.md` — 完整模板：从零建表、自建控制器（绕开不兼容的 mapper）、加密/脱敏 API Key、打通聊天流读取激活配置、前端列表+编辑+测试按钮。
- `references/model-config-test-endpoint.md` — 测试连接端点的多轮调试过程：OpenAI /v1/models → Anthropic POST → Windows SSL 绕过 → 连通 vs 鉴权区分。
- `references/ide-web-api-pattern.md` — IDE Web 模式：后端文件树与文件读写 API，含 `_safe_join` 路径穿越防护、隐藏文件/二进制过滤、与前端 splitpanes+Monaco 的分工。

