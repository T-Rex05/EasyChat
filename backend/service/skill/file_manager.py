"""
技能文件管理模块

负责技能文件的读写操作，包括 SKILL.md 的解析、frontmatter 处理、附属文件管理等。
"""
import os
import re
from pathlib import Path
from typing import Dict, Any, List

from backend.utils.log_utils import log

logger = log

_ALLOWED_SUBDIRS = {"references", "templates", "scripts", "assets", "examples"}
_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_AI_CATEGORY = "AI生成"


def _get_skills_dir() -> Path:
    """获取技能目录路径"""
    hermes_home = os.environ.get("HERMES_HOME", "")
    if not hermes_home:
        project_root = Path(__file__).resolve().parent.parent.parent
        hermes_home = str(project_root / "hermes" / ".home")
    return Path(hermes_home) / "skills"


def _parse_frontmatter(content: str) -> Dict[str, Any]:
    """解析 YAML frontmatter"""
    if not content.startswith("---"):
        return {}
    end = content.find("---", 3)
    if end == -1:
        return {}
    yaml_block = content[3:end].strip()
    result = {}
    for line in yaml_block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            result[key] = value
    return result


def _strip_frontmatter(content: str) -> str:
    """移除 frontmatter，返回正文"""
    if not content.startswith("---"):
        return content
    end = content.find("---", 3)
    if end == -1:
        return content
    body = content[end + 3:]
    if body.startswith("\r\n"):
        body = body[2:]
    elif body.startswith("\n"):
        body = body[1:]
    return body


def _validate_name(name: str) -> None:
    """验证技能名称"""
    if not name or not _NAME_PATTERN.match(name):
        raise ValueError(f"技能名称不合法: '{name}'。")


def _validate_subpath(file_path: str) -> None:
    """验证附属文件路径"""
    if ".." in file_path:
        raise ValueError(f"不允许路径遍历: {file_path}")
    parts = Path(file_path).parts
    if not parts or parts[0] not in _ALLOWED_SUBDIRS:
        raise ValueError(f"附属文件必须在以下目录之一: {', '.join(sorted(_ALLOWED_SUBDIRS))}。")


def _list_supporting_files(skill_dir: Path) -> List[str]:
    """列出技能目录下的所有附属文件"""
    files = []
    for subdir in _ALLOWED_SUBDIRS:
        d = skill_dir / subdir
        if d.is_dir():
            for f in d.rglob("*"):
                if f.is_file():
                    files.append(str(f.relative_to(skill_dir)))
    return files


def _build_skill_summary(item: Path, mid: Path, fm: dict, status_map: dict, meta_row: dict = None) -> Dict[str, Any]:
    """构建技能摘要信息"""
    skills_dir = _get_skills_dir()
    name = fm.get("name", item.name)
    result = {
        "name": name,
        "description": fm.get("description", ""),
        "author": fm.get("author", "未知"),
        "category": meta_row.get("category") if meta_row else fm.get("category", "其他"),
        "version": fm.get("version", ""),
        "path": str(item.relative_to(skills_dir)) if item != mid.parent else str(mid.parent.relative_to(skills_dir)),
        "format": "directory",
        "enabled": status_map.get(name, True),
        "has_references": (mid.parent / "references").is_dir(),
        "status": meta_row.get("status", "approved") if meta_row else "approved",
        "locked": bool(meta_row.get("locked", 0)) if meta_row else False,
        "owner_id": meta_row.get("owner_id", 1) if meta_row else 1,
    }
    return result


def _query_all_skills() -> List[Dict[str, Any]]:
    """从文件系统读取全部技能列表（无过滤）"""
    from backend.service.skill.meta import _get_item_status, _meta_all

    skills_dir = _get_skills_dir()
    if not skills_dir.exists():
        return []

    status_map = _get_item_status("skill")
    meta_all = _meta_all()

    results = []
    for item in sorted(skills_dir.iterdir()):
        if item.name.startswith("."):
            continue
        if not item.is_dir():
            if item.suffix == ".md":
                content = item.read_text(encoding="utf-8", errors="replace")
                fm = _parse_frontmatter(content)
                name = fm.get("name", item.stem)
                meta = meta_all.get(name)
                r = {
                    "name": name,
                    "description": fm.get("description", ""),
                    "author": fm.get("author", "未知"),
                    "category": meta.get("category") if meta else fm.get("category", "其他"),
                    "path": str(item.relative_to(skills_dir)),
                    "format": "flat",
                    "enabled": status_map.get(name, True),
                    "status": meta.get("status", "approved") if meta else "approved",
                    "locked": bool(meta.get("locked", 0)) if meta else False,
                    "owner_id": meta.get("owner_id", 1) if meta else 1,
                }
                results.append(r)
            continue

        skill_md = item / "SKILL.md"
        if not skill_md.exists():
            for sub in item.rglob("SKILL.md"):
                content = sub.read_text(encoding="utf-8", errors="replace")
                fm = _parse_frontmatter(content)
                name = fm.get("name", sub.parent.name)
                meta = meta_all.get(name)
                results.append(_build_skill_summary(sub.parent, sub, fm, status_map, meta))
            continue

        content = skill_md.read_text(encoding="utf-8", errors="replace")
        fm = _parse_frontmatter(content)
        name = fm.get("name", item.name)
        meta = meta_all.get(name)
        results.append(_build_skill_summary(item, skill_md, fm, status_map, meta))

    # 批量查询 owner_name
    owner_ids = list(set(s.get("owner_id", 1) for s in results))
    if owner_ids:
        from backend.db.schema import get_conn
        conn = get_conn()
        try:
            placeholders = ",".join(["?" for _ in owner_ids])
            rows = conn.execute(
                f"SELECT id, username FROM users WHERE id IN ({placeholders})",
                owner_ids
            ).fetchall()
            owner_map = {row["id"]: row["username"] for row in rows}
            for s in results:
                s["owner_name"] = owner_map.get(s.get("owner_id", 1), "未知")
        finally:
            conn.close()

    return results


def _resolve_skill_dir(name: str) -> Path:
    """解析技能的实际目录（可能在分类子目录下）"""
    skills_dir = _get_skills_dir()
    # 先尝试直接路径
    direct = skills_dir / name
    if direct.exists() and (direct / "SKILL.md").exists():
        return direct
    # 搜索分类子目录
    for sub in skills_dir.rglob(f"*/{name}"):
        if sub.is_dir() and (sub / "SKILL.md").exists():
            return sub
    # 兜底：即使没有 SKILL.md，只要目录存在就返回
    if direct.exists():
        return direct
    for sub in skills_dir.rglob(f"*/{name}"):
        if sub.is_dir():
            return sub
    raise FileNotFoundError(f"技能不存在: {name}")


def get_skill_file(name: str, file_path: str) -> str:
    """读取技能附属文件"""
    _validate_subpath(file_path)
    skill_dir = _resolve_skill_dir(name)
    full_path = (skill_dir / file_path).resolve()
    if not str(full_path).startswith(str(skill_dir.resolve())):
        raise ValueError(f"路径遍历被拒绝: {file_path}")
    if not full_path.is_file():
        raise FileNotFoundError(f"文件不存在: {name}/{file_path}")
    return full_path.read_text(encoding="utf-8", errors="replace")


def write_skill_file(name: str, file_path: str, content: str) -> Dict[str, str]:
    """写入技能附属文件"""
    _validate_subpath(file_path)
    skill_dir = _resolve_skill_dir(name)
    full_path = (skill_dir / file_path).resolve()
    if not str(full_path).startswith(str(skill_dir.resolve())):
        raise ValueError(f"路径遍历被拒绝: {file_path}")
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")
    logger.info(f"写入技能附属文件: {name}/{file_path}")
    return {"name": name, "file_path": file_path, "size": len(content)}


def delete_skill_file(name: str, file_path: str) -> Dict[str, str]:
    """删除技能附属文件"""
    _validate_subpath(file_path)
    skill_dir = _resolve_skill_dir(name)
    full_path = (skill_dir / file_path).resolve()
    if not str(full_path).startswith(str(skill_dir.resolve())):
        raise ValueError(f"路径遍历被拒绝: {file_path}")
    if not full_path.is_file():
        raise FileNotFoundError(f"文件不存在: {name}/{file_path}")
    full_path.unlink()
    logger.info(f"删除技能附属文件: {name}/{file_path}")
    return {"name": name, "file_path": file_path, "deleted": True}


def get_skill_file_path(name: str, file_path: str) -> str:
    """获取技能附属文件的绝对路径（用于文件下载）"""
    _validate_subpath(file_path)
    skill_dir = _resolve_skill_dir(name)
    full_path = (skill_dir / file_path).resolve()
    if not str(full_path).startswith(str(skill_dir.resolve())):
        raise ValueError(f"路径遍历被拒绝: {file_path}")
    if not full_path.is_file():
        raise FileNotFoundError(f"文件不存在: {name}/{file_path}")
    return str(full_path)


def save_skill_file_binary(name: str, file_path: str, content: bytes) -> Dict[str, Any]:
    """保存二进制文件到技能目录"""
    _validate_subpath(file_path)
    skill_dir = _resolve_skill_dir(name)
    full_path = (skill_dir / file_path).resolve()
    if not str(full_path).startswith(str(skill_dir.resolve())):
        raise ValueError(f"路径遍历被拒绝: {file_path}")
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(content)
    size = len(content)
    logger.info(f"保存二进制文件: {name}/{file_path} ({size} bytes)")
    return {"name": name, "file_path": file_path, "size": size}


def create_skill_dir(name: str, dir_path: str) -> Dict[str, str]:
    """在技能目录下创建子目录"""
    _validate_subpath(dir_path)
    skill_dir = _resolve_skill_dir(name)
    full_path = (skill_dir / dir_path).resolve()
    if not str(full_path).startswith(str(skill_dir.resolve())):
        raise ValueError(f"路径遍历被拒绝: {dir_path}")
    full_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"创建技能子目录: {name}/{dir_path}")
    return {"name": name, "dir_path": dir_path, "created": True}
