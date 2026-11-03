# IDE Web 模式：后端文件树与文件读写 API

## 适用场景

给一个 FastAPI 后端新增"在线 IDE"文件浏览器能力：前端通过 API 浏览、读取、保存服务器本地文件系统的文件，后端做路径穿越防护和文件类型过滤。

AgentForge 项目实现了这个模式在 `backend/controller/ide_controller.py`。

## 端点设计

| 方法 | 路径 | 功能 | 安全约束 |
|---|---|---|---|
| POST | `/api/ide/root` | 设置工作根目录 | 需登录；校验路径是真实目录 |
| GET | `/api/ide/root` | 获取当前根目录 | 需登录 |
| GET | `/api/ide/tree?path=` | 获取目录树（一层） | 拒绝 `../` 穿越；跳过隐藏文件和二进制 |
| GET | `/api/ide/file?path=` | 读取文件内容 | 拒绝穿越；检查文件大小（>2MB 拒绝） |
| PUT | `/api/ide/file?path=` | 保存/写入文件 | 拒绝穿越；接收 `{"content": "..."}` |

## 路径穿越防护：`_safe_join`

```python
import os

def _safe_join(root: str, *paths: str) -> str:
    """安全的路径拼接：拒绝 ../ 穿越。"""
    resolved = os.path.normpath(os.path.join(root, *paths))
    root_resolved = os.path.normpath(root)
    if not resolved.startswith(root_resolved + os.sep) and resolved != root_resolved:
        raise HTTPException(status_code=403, detail="路径穿越被禁止")
    return resolved
```

**关键点**：`os.path.normpath` 把 `../../etc/passwd` 解析为真实路径 `/etc/passwd`，然后检查是否仍以 `root` 为前缀。每一条读/写端点都调用此方法。

## 文件过滤策略

**跳过的隐藏项**（目录树）：
- 以 `.` 开头的文件/目录（`.git`、`.env`、`.vscode`）
- 以 `__` 开头的目录（`__pycache__`、`__init__.py` 作为文件不过滤但 `__pycache__` 目录跳过）

**跳过的二进制文件**（不展示在树里）：通过扩展名黑名单过滤（`.exe/.dll/.png/.jpg/.zip/.gz/.ttf/.pdf/.pyc/.class` 等），避免用户无意点击大文件或二进制文件导致无意义的输出。

**文件大小限制**：读取时检查 `os.stat(filepath).st_size > MAX_FILE_SIZE`（默认 2MB），拒绝超大文件。

## 根目录存储（内存）

当前实现用内存字典 `_ide_roots: Dict[int, str]` 按 user_id 存储根目录路径（服务重启丢失）。可改为落库 `user_configs` 表持久化。

## 与 IDE 前端的分工

后端只负责「把文件系统映射为 HTTP API」：
- 目录树 → JSON 数组 `[{name, type:"dir"|"file", path, size?, ext?}]`
- 文件内容 → `{path, name, content, size}`（UTF-8 文本）

前端负责：
- 用 splitpanes 做可拖拽三面板布局
- 文件树用递归组件渲染（文件夹点击展开/折叠，文件点击→打开）
- Monaco Editor 处理语法高亮、多 Tab 页、Ctrl+S 保存回写 PUT 接口

## 安全需注意

- 此 API 给服务器本地文件系统开了读/写口子。必须上登录鉴权（`Depends(get_current_user)`）。
- 生产部署需额外限制：只允许访问受信的目录范围、加操作审计日志。当前版本是开发/内网用途。
- `os.scandir` 比 `os.listdir` 好：返回的对象自带 `is_dir()/.is_file()` 和 `stat()` 信息，避免额外系统调用。
