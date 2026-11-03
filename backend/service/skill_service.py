"""
技能服务模块

负责技能的业务逻辑编排，包括技能的 CRUD、权限检查、内容池管理等。
底层操作分别由 skill_meta 和 skill_file_manager 提供。
"""
import os
import re
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any

from backend.utils.log_utils import log
from backend.service.skill.meta import (
    _meta_conn, _meta_insert, _meta_get, _meta_update, _meta_all,
    _get_item_status, toggle_item_status,
)
from backend.service.skill.file_manager import (
    _get_skills_dir, _parse_frontmatter, _strip_frontmatter,
    _validate_name, _validate_subpath, _list_supporting_files,
    _query_all_skills, get_skill_file, write_skill_file, delete_skill_file,
    get_skill_file_path, save_skill_file_binary, create_skill_dir,
)

logger = log

_AI_CATEGORY = "AI生成"

# ── 公共所有者定义 ──
# owner_id=1 历史上被当作"系统公共技能"，但这与第一个注册用户冲突。
# 明确定义：公共技能是由系统创建或标记为公共的技能，而非第一个用户的私有技能。
# 当前实现：owner_id=1 且 category 不是 "AI生成" 视为公共技能（向后兼容）。
# 未来改进：应该增加 is_public 字段或使用专门的 SYSTEM_OWNER_ID。
_PUBLIC_OWNER_ID = 1  # 系统公共所有者 ID


def can_access_skill(name: str, user_id: int = None, role: str = None) -> bool:
    """判断用户是否可查看/修改技能：所有者 / 超管 / skill.manage。"""
    from backend.permission.checker import has_permission
    meta = _meta_get(name)
    owner = meta.get("owner_id", 1) if meta else 1
    if role == "super_admin":
        return True
    if user_id and int(user_id) == int(owner):
        return True
    if user_id and has_permission(int(user_id), "skill.manage"):
        return True
    return False


# ── Skill listing / detail ──

def list_skills(user_id: int = None, role: str = None) -> dict:
    """返回技能列表。

    返回结构:
    {
        "my_skills": [...],           # 当前用户自己的技能
        "pool_available": [...],      # 池中可浏览/安装的（不包括已安装的）
        "pool_installed": [...],      # 已安装的池技能
        "categories": [...],          # 当前用户的分类列表
        "all_skills": [...]           # 所有用户技能（仅 skill.manage 权限）
    }

    AI 技能（author=AgentForge）仅超管可见。
    """
    from backend.permission.checker import has_permission

    all_skills_raw = _query_all_skills()
    is_admin = role == "super_admin" or (user_id and has_permission(user_id, "skill.manage"))

    # 分离 AI 技能和普通技能（只看 author 是否为 AgentForge）
    # AI 技能：author=AgentForge，仅管理员可见
    # 用户自己创建的 AI 技能（owner_id 匹配）也会在 my_skills 中显示
    ai_skills = [s for s in all_skills_raw if s.get("author") == "AgentForge"]
    normal_skills = [s for s in all_skills_raw if s.get("author") != "AgentForge"]

    user_id_int = int(user_id) if user_id else 0

    # 用户自己的技能（普通技能 + 自己创建的 AI 技能）
    my_skills = [s for s in normal_skills if s.get("owner_id") == user_id_int]
    # 用户自己创建的 AI 技能也加入 my_skills（但会标记为 AI 生成）
    my_ai_skills = [s for s in ai_skills if s.get("owner_id") == user_id_int]
    my_skills.extend(my_ai_skills)

    # 管理员看到的 all_skills：其他用户的普通技能（排除自己的，排除 AI）
    all_skills_for_admin = [s for s in normal_skills if s.get("owner_id") != user_id_int] if is_admin else []

    # 池中已安装的技能
    pool_installed = _query_pool_installed_skills(user_id)

    # 池中可浏览的技能（不包括已安装的）
    pool_installed_names = {s.get("name") for s in pool_installed}
    pool_available = [s for s in _query_pool_available() if s.get("name") not in pool_installed_names]

    # 用户自己的池记录（待审核/已上架/已拒绝）
    my_pool_records = _get_user_pool_records(user_id_int, "skill")

    # 用户自己的分类
    categories = get_user_categories(user_id_int) if user_id_int else []

    # AI 技能仅管理员可见
    ai_skills_list = ai_skills if is_admin else []

    result = {
        "my_skills": my_skills,
        "pool_available": pool_available,
        "pool_installed": pool_installed,
        "categories": categories,
        "my_pool_records": my_pool_records,
    }

    # 管理员额外返回其他用户技能 + AI 技能
    if is_admin:
        result["all_skills"] = all_skills_for_admin
        result["ai_skills"] = ai_skills_list

    return result


def get_skill(name: str, user_id: int = None, role: str = None) -> Dict[str, Any]:
    """获取技能详情"""
    skills_dir = _get_skills_dir()
    skill_dir = skills_dir / name
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.exists():
        for sub in skills_dir.rglob("**/" + name + "/SKILL.md"):
            skill_md = sub
            skill_dir = sub.parent
            break

    if not skill_md.exists():
        flat = skills_dir / f"{name}.md"
        if flat.exists():
            content = flat.read_text(encoding="utf-8", errors="replace")
            fm = _parse_frontmatter(content)
            body = _strip_frontmatter(content)
            return {
                "name": fm.get("name", name),
                "description": fm.get("description", ""),
                "author": fm.get("author", ""),
                "category": fm.get("category", "其他"),
                "content": content,
                "body": body,
                "frontmatter": fm,
                "files": [],
                "format": "flat",
            }

    if not skill_md.exists():
        raise FileNotFoundError(f"技能不存在: {name}")

    content = skill_md.read_text(encoding="utf-8", errors="replace")
    fm = _parse_frontmatter(content)
    body = _strip_frontmatter(content)

    meta = _meta_get(fm.get("name", name))
    cat = meta.get("category") if meta else fm.get("category", "其他")

    # Permission check
    from backend.permission.checker import has_permission
    if role == "super_admin":
        pass  # super admin sees all
    elif user_id and has_permission(int(user_id), "skill.manage"):
        pass  # 管理员可查看全部（与 list_skills 的 all_skills 一致）
    elif not meta:
        # meta 缺失：无归属信息，仅超管/管理员可看（上面已放行），其余拒绝
        raise FileNotFoundError(f"技能不存在: {name}")
    elif meta.get("locked"):
        raise ValueError(f"技能 '{name}' 已被锁定，无法使用")
    elif user_id:
        owner = meta.get("owner_id", 1)
        cat = meta.get("category", "")
        is_owner = (owner == user_id)
        # 公共技能定义：系统所有者(_PUBLIC_OWNER_ID=1) 且非 AI 生成的技能
        # 注意：第一个注册用户（user_id=1）创建的私有技能也会被误判为公共技能
        # 这是历史遗留问题，建议未来增加 is_public 字段明确区分
        is_public = (owner == _PUBLIC_OWNER_ID and cat != _AI_CATEGORY)
        if not is_owner and not is_public:
            raise FileNotFoundError(f"技能不存在: {name}")

    return {
        "name": fm.get("name", name),
        "description": fm.get("description", ""),
        "author": fm.get("author", ""),
        "category": cat,
        "version": fm.get("version", ""),
        "content": content,
        "body": body,
        "frontmatter": fm,
        "files": _list_supporting_files(skill_dir),
        "format": "directory",
        "status": meta.get("status") if meta else "approved",
        "locked": bool(meta.get("locked", 0)) if meta else False,
        "owner_id": meta.get("owner_id") if meta else 1,
    }


# ── Create / Update / Delete ──

def create_skill(
    name: str,
    content: str,
    description: str = "",
    category: Optional[str] = None,
    author: str = "",
    user_id: int = 1,
    role: str = "user",
    from_agent: bool = False,
) -> Dict[str, Any]:
    """创建新技能（需要 skill.create 权限，可在角色编辑里勾选）。"""
    from backend.permission.checker import has_permission
    if not (user_id and has_permission(int(user_id), "skill.create")):
        raise ValueError("缺少 skill.create 权限，无法创建技能")

    _validate_name(name)
    skills_dir = _get_skills_dir()

    if not content.startswith("---"):
        frontmatter_lines = ["---", f"name: {name}", f"description: {description or name}"]
        if author:
            frontmatter_lines.append(f"author: {author}")
        frontmatter_lines.append("---")
        full_content = f"{chr(10).join(frontmatter_lines)}\n\n# {name}\n\n{content}"
    else:
        full_content = content

    if category:
        skill_dir = skills_dir / category / name
    else:
        skill_dir = skills_dir / name

    if skill_dir.exists():
        raise FileExistsError(f"技能已存在: {name}")

    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(full_content, encoding="utf-8")

    # Skill 创建直接生效，无需审核
    fm = _parse_frontmatter(full_content)
    final_category = category or fm.get("category", "")
    status = "approved"

    _meta_insert(name, user_id, final_category, status)

    logger.info(f"创建技能: {name} → {skill_dir} (status={status})")
    return {
        "name": name,
        "description": description or name,
        "path": str(skill_dir.relative_to(skills_dir)),
        "content": full_content,
        "status": status,
    }


def update_skill(name: str, content: str, category: Optional[str] = None, description: Optional[str] = None, user_id: int = None, role: str = None) -> Dict[str, Any]:
    """更新技能"""
    from backend.permission.checker import has_permission
    meta = _meta_get(name)
    owner = meta.get("owner_id", 1) if meta else 1
    is_owner = (user_id == owner)
    is_super = (role == "super_admin")
    can_manage = has_permission(user_id, "skill.manage") if user_id else False

    # 权限检查
    if not is_owner and not is_super and not can_manage:
        raise ValueError(f"无权修改此技能（所有者 ID: {owner}）")

    # 锁定检查：被锁定的技能只有超管能修改
    if meta and meta.get("locked") and not is_super:
        raise ValueError("此技能已被锁定，无法修改")

    skills_dir = _get_skills_dir()
    skill_dir = None
    direct = skills_dir / name
    if direct.is_dir():
        skill_dir = direct
    else:
        for sub in skills_dir.rglob(name):
            if sub.is_dir():
                skill_dir = sub
                break
    if skill_dir is None:
        raise FileNotFoundError(f"技能不存在: {name}")

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise FileNotFoundError(f"技能 SKILL.md 不存在: {name}")

    old_content = skill_md.read_text(encoding="utf-8", errors="replace")
    old_fm = _parse_frontmatter(old_content)
    old_category = old_fm.get("category", "")

    skill_md.write_text(content, encoding="utf-8")
    fm = _parse_frontmatter(content)

    new_category = category if category is not None else old_category
    if new_category and new_category != old_category:
        new_dir = skills_dir / new_category / name
        if new_dir.exists():
            raise ValueError(f"目标分类下已存在同名技能: {name}")
        new_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(skill_dir), str(new_dir))
        skill_dir = new_dir
        _meta_update(name, category=new_category)
        logger.info(f"移动技能: {name} → {new_category}/{name}")

    logger.info(f"更新技能: {name}")
    return {"name": fm.get("name", name), "description": fm.get("description", ""), "content": content}


def delete_skill(name: str, user_id: int = None, role: str = None) -> bool:
    """删除技能"""
    from backend.permission.checker import has_permission
    meta = _meta_get(name)
    owner = meta.get("owner_id", 1) if meta else 1
    is_owner = (user_id == owner)
    is_super = (role == "super_admin")
    can_manage = has_permission(user_id, "skill.manage") if user_id else False

    # 权限检查
    if not is_owner and not is_super and not can_manage:
        raise ValueError(f"无权删除此技能（所有者 ID: {owner}）")

    # 锁定检查：被锁定的技能只有超管能删除
    if meta and meta.get("locked") and not is_super:
        raise ValueError("此技能已被锁定，无法删除")

    skills_dir = _get_skills_dir()
    
    # 查找技能目录（可能在分类子目录下）
    skill_dir = None
    
    # 首先检查根目录
    direct = skills_dir / name
    if direct.is_dir():
        skill_dir = direct
    else:
        # 尝试在分类子目录中查找
        for category_dir in skills_dir.iterdir():
            if category_dir.is_dir():
                candidate = category_dir / name
                if candidate.is_dir():
                    skill_dir = candidate
                    break
    
    # 验证找到技能目录
    if skill_dir is None or not skill_dir.exists():
        raise FileNotFoundError(f"技能不存在: {name}")
    
    # 路径安全检查：确保解析后的路径仍在 skills_dir 内
    resolved = skill_dir.resolve()
    if not str(resolved).startswith(str(skills_dir.resolve())):
        raise ValueError(f"路径安全检查失败: {name}")
    shutil.rmtree(resolved)
    # Remove from meta + 清理内容池残留（避免同名重建后"复活"上架）
    conn = _meta_conn()
    try:
        conn.execute("DELETE FROM skill_meta WHERE name = %s", (name,))
        conn.execute("DELETE FROM content_pool WHERE content_type = 'skill' AND content_name = %s", (name,))
        conn.execute("DELETE FROM content_installs WHERE content_type = 'skill' AND content_name = %s", (name,))
        # 清理 item_status 中的状态记录
        conn.execute("DELETE FROM item_status WHERE item_type = 'skill' AND item_name = %s", (name,))
        conn.commit()
    finally:
        conn.close()
    logger.info(f"删除技能: {name}")
    return True


# ── Content Pool (通用内容池) ──

def _query_pool_available() -> List[Dict[str, Any]]:
    """查询池中可浏览/安装的技能（status='active'）。"""
    conn = _meta_conn()
    try:
        cur = conn.execute("""
            SELECT cp.content_name, cp.owner_id, u.username as owner_name
            FROM content_pool cp
            LEFT JOIN users u ON cp.owner_id = u.id
            WHERE cp.content_type = 'skill' AND cp.status = 'active'
        """)
        rows = cur.fetchall() if hasattr(cur, 'fetchall') else [r for r in (cur or [])]
        pool_items = {dict(r)["content_name"]: dict(r) for r in rows}
    except Exception:
        pool_items = {}
    finally:
        conn.close()

    # 交叉匹配文件系统技能
    all_skills = _query_all_skills()
    result = []
    for s in all_skills:
        name = s.get("name")
        if name in pool_items:
            item = pool_items[name]
            s["owner_name"] = item.get("owner_name") or "未知"
            s["owner_id"] = item.get("owner_id")
            result.append(s)
    return result


def _get_user_pool_records(user_id: int, content_type: str) -> List[Dict[str, Any]]:
    """获取用户提交到池子的记录（待审核/已上架/已拒绝）。"""
    if not user_id:
        return []
    conn = _meta_conn()
    try:
        cur = conn.execute("""
            SELECT id, content_type, content_name, status, reject_reason, created_at, reviewed_at
            FROM content_pool
            WHERE owner_id = %s AND content_type = %s
            ORDER BY created_at DESC
        """, (int(user_id), content_type))
        rows = cur.fetchall() if hasattr(cur, 'fetchall') else [r for r in (cur or [])]
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def _query_pool_installed_skills(user_id: int = None) -> List[Dict[str, Any]]:
    """从 content_installs 表查询用户已安装的池内容。"""
    if not user_id:
        return []
    conn = _meta_conn()
    try:
        cur = conn.execute(
            "SELECT content_type, content_name FROM content_installs WHERE user_id = %s",
            (int(user_id),),
        )
        rows = cur.fetchall() if hasattr(cur, 'fetchall') else [r for r in (cur or [])]
        installed = [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()

    # 交叉匹配文件系统技能
    all_skills = _query_all_skills()
    pool_skills = []
    for inst in installed:
        for s in all_skills:
            if s.get("name") == inst.get("content_name"):
                pool_skills.append(s)
                break
    return pool_skills


def publish_to_pool(content_type: str, content_name: str, user_id: int) -> dict:
    """提交内容到池子（用户侧）。

    校验：内容必须存在、必须属于提交者（或提交者有对应 manage 权限）。
    提交者拥有对应审核权限（admin/super_admin 角色或 share 权限）时免审，
    直接上架（status=active）；否则进入待审核（status=pending）。
    """
    from backend.permission.checker import has_permission

    owner = None
    if content_type == "skill":
        all_skills = _query_all_skills()
        skill = next((s for s in all_skills if s.get("name") == content_name), None)
        if not skill:
            raise FileNotFoundError(f"技能不存在: {content_name}")
        owner = skill.get("owner_id")
        manage_perm = "skill.manage"
    else:
        raise ValueError(f"不支持的内容类型: {content_type}")

    is_owner = owner is not None and int(owner) == int(user_id)
    can_manage = bool(user_id and has_permission(int(user_id), manage_perm))
    if not is_owner and not can_manage:
        raise ValueError("只能发布自己的内容")

    conn = _meta_conn()
    try:
        status = "active" if _can_skip_review(user_id, content_type) else "pending"
        conn.execute(
            """REPLACE INTO content_pool
               (content_type, content_name, owner_id, submitted_by, status)
               VALUES (%s, %s, %s, %s, %s)""",
            (content_type, content_name, int(owner or user_id), user_id, status),
        )
        conn.commit()
        return {"ok": True, "content_type": content_type, "content_name": content_name, "status": status}
    finally:
        conn.close()


def _can_skip_review(user_id: int, content_type: str) -> bool:
    """提交者本人是否拥有该内容类型的审核权限。

    有审核权限的用户提交内容时无需再审，直接上架（status=active）。
    需要 skill.manage 权限（可在角色编辑里勾选）。
    """
    from backend.permission.checker import get_user_permissions

    if not user_id:
        return False
    uid = int(user_id)
    perms = get_user_permissions(uid)
    if content_type == "skill":
        return "skill.manage" in perms
    return False


def check_toolset_permission(content_type: str, content_name: str, user_id: int) -> dict:
    """检查用户是否有安装该内容所需的 toolset 权限。

    返回 {"ok": True} 或 {"ok": False, "missing": ["terminal"]}。
    """
    from backend.permission.checker import get_user_hermes_tools
    user_toolsets = set(get_user_hermes_tools(user_id))

    required = set()
    if content_type == "skill":
        # 读取技能 frontmatter 中的 requires_toolsets
        try:
            import yaml
            skills_dir = _get_skills_dir()
            for skill_file in skills_dir.rglob(f"{content_name}/SKILL.md"):
                text = skill_file.read_text(encoding="utf-8")
                if text.startswith("---"):
                    parts = text.split("---", 2)
                    if len(parts) >= 2:
                        fm = yaml.safe_load(parts[1]) or {}
                        hermes_meta = (fm.get("metadata") or {}).get("hermes") or {}
                        required = set(hermes_meta.get("requires_toolsets", []))
                break
            # 也检查扁平文件形式 <name>.md
            if not required:
                flat_file = skills_dir / f"{content_name}.md"
                if flat_file.exists():
                    text = flat_file.read_text(encoding="utf-8")
                    if text.startswith("---"):
                        parts = text.split("---", 2)
                        if len(parts) >= 2:
                            fm = yaml.safe_load(parts[1]) or {}
                            hermes_meta = (fm.get("metadata") or {}).get("hermes") or {}
                            required = set(hermes_meta.get("requires_toolsets", []))
        except Exception as e:
            logger.warning(f"check_toolset_permission(skill={content_name}): {e}")
    else:
        raise ValueError(f"不支持的内容类型: {content_type}")

    missing = required - user_toolsets
    if missing:
        return {"ok": False, "missing": sorted(missing)}
    return {"ok": True}


def install_from_pool(content_type: str, content_name: str, user_id: int) -> dict:
    """从池子安装内容。"""
    # 校验 toolset 权限
    perm_check = check_toolset_permission(content_type, content_name, user_id)
    if not perm_check["ok"]:
        missing_labels = ", ".join(perm_check["missing"])
        raise ValueError(f"安装失败: 需要 [{missing_labels}] 工具组权限，请联系管理员")

    conn = _meta_conn()
    try:
        # 验证池中存在且 active，并获取 owner_id
        cur = conn.execute(
            "SELECT id, owner_id FROM content_pool WHERE content_type = %s AND content_name = %s AND status = 'active'",
            (content_type, content_name),
        )
        row = cur.fetchone() if hasattr(cur, 'fetchone') else None
        if not row:
            raise ValueError("该内容不在池中或已下架")

        # 检查是否是自己的内容
        row_dict = dict(row) if not isinstance(row, dict) else row
        if row_dict.get("owner_id") == int(user_id):
            raise ValueError("不能安装自己发布的内容")

        conn.execute(
            "INSERT IGNORE INTO content_installs (content_type, content_name, user_id) VALUES (%s, %s, %s)",
            (content_type, content_name, user_id),
        )
        conn.commit()
        return {"ok": True, "content_type": content_type, "content_name": content_name}
    finally:
        conn.close()


def uninstall_from_pool(content_type: str, content_name: str, user_id: int) -> dict:
    """从用户账号卸载池中的内容。"""
    conn = _meta_conn()
    try:
        cur = conn.execute(
            "DELETE FROM content_installs WHERE content_type = %s AND content_name = %s AND user_id = %s",
            (content_type, content_name, int(user_id)),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise FileNotFoundError(f"未安装该内容: {content_name}")
        return {"ok": True, "content_type": content_type, "content_name": content_name}
    finally:
        conn.close()


def list_pool(content_type: str, user_id: int = None) -> list:
    """浏览池中 active 内容。"""
    conn = _meta_conn()
    try:
        cur = conn.execute(
            """SELECT cp.*, u.username as owner_name
               FROM content_pool cp
               JOIN users u ON cp.owner_id = u.id
               WHERE cp.content_type = %s AND cp.status = 'active'
               ORDER BY cp.created_at DESC""",
            (content_type,),
        )
        rows = cur.fetchall() if hasattr(cur, 'fetchall') else [r for r in (cur or [])]
        results = [dict(r) for r in rows]

        # 标记已安装
        if user_id:
            cur2 = conn.execute(
                "SELECT content_name FROM content_installs WHERE content_type = %s AND user_id = %s",
                (content_type, user_id),
            )
            installed_rows = cur2.fetchall() if hasattr(cur2, 'fetchall') else [r for r in (cur2 or [])]
            installed_names = {r["content_name"] for r in installed_rows}
            for item in results:
                item["installed"] = item["content_name"] in installed_names

        return results
    finally:
        conn.close()


# ── Lock / Unlock ──

def lock_skill(name: str) -> Dict[str, Any]:
    """锁定技能"""
    _meta_update(name, locked=1)
    logger.info(f"锁定技能: {name}")
    return {"name": name, "locked": True}


def unlock_skill(name: str) -> Dict[str, Any]:
    """解锁技能"""
    _meta_update(name, locked=0)
    logger.info(f"解锁技能: {name}")
    return {"name": name, "locked": False}


# ── Categories ──

def list_categories(user_role: str = None) -> List[str]:
    """列出所有分类"""
    data = list_skills()
    # list_skills() 返回 dict: {my_skills, pool_skills, all_skills?}
    # 提取所有技能合并为一个列表
    all_skills = []
    if isinstance(data, dict):
        if "all_skills" in data:
            all_skills = data["all_skills"]
        else:
            all_skills = data.get("my_skills", []) + data.get("pool_skills", [])
    else:
        all_skills = data  # 兼容旧返回格式
    cats = set()
    for s in all_skills:
        cat = s.get("category", "其他")
        if cat and (user_role == "super_admin" or cat != _AI_CATEGORY):
            cats.add(cat)
    skills_dir = _get_skills_dir()
    if skills_dir.exists():
        for d in skills_dir.iterdir():
            if d.is_dir() and not d.name.startswith("."):
                has_sub = any(d.rglob("SKILL.md"))
                if not (d / "SKILL.md").exists() and not has_sub:
                    if user_role == "super_admin" or d.name != _AI_CATEGORY:
                        cats.add(d.name)
    return sorted(cats)


def _validate_category_name(name: str) -> None:
    """严格校验分类名称：仅允许字母、数字、下划线、中划线、中文。"""
    if not name or not re.match(r'^[\w一-鿿-]+$', name):
        raise ValueError(f"分类名称不合法: '{name}'。仅允许字母、数字、下划线、中划线和中文")
    # 额外防御：拒绝包含路径分隔符的名称
    if "/" in name or "\\" in name or ".." in name:
        raise ValueError(f"分类名称不合法: '{name}'")


def create_category(name: str) -> Dict[str, str]:
    """创建分类"""
    _validate_category_name(name)
    skills_dir = _get_skills_dir()
    cat_dir = skills_dir / name
    # 安全校验：确保解析后的路径仍在 skills_dir 内
    if not str(cat_dir.resolve()).startswith(str(skills_dir.resolve() / "")):
        raise ValueError(f"分类名称不合法: '{name}'")
    if cat_dir.exists():
        raise ValueError(f"分类已存在: {name}")
    cat_dir.mkdir(parents=True, exist_ok=True)
    (cat_dir / ".gitkeep").touch()
    logger.info(f"创建分类: {name}")
    return {"name": name, "path": str(cat_dir.relative_to(skills_dir))}


def rename_category(old_name: str, new_name: str) -> Dict[str, Any]:
    """重命名分类"""
    _validate_category_name(old_name)
    _validate_category_name(new_name)
    skills_dir = _get_skills_dir()
    old_dir = skills_dir / old_name
    new_dir = skills_dir / new_name
    # 安全校验：确保解析后的路径仍在 skills_dir 内
    if not str(old_dir.resolve()).startswith(str(skills_dir.resolve() / "")):
        raise ValueError(f"分类名称不合法: '{old_name}'")
    if not str(new_dir.resolve()).startswith(str(skills_dir.resolve() / "")):
        raise ValueError(f"分类名称不合法: '{new_name}'")
    if not old_dir.exists():
        raise FileNotFoundError(f"分类不存在: {old_name}")
    if new_dir.exists():
        raise ValueError(f"目标分类已存在: {new_name}")
    shutil.move(str(old_dir), str(new_dir))
    updated = 0
    for md in new_dir.rglob("SKILL.md"):
        text = md.read_text(encoding="utf-8", errors="replace")
        new_text = re.sub(r'(?m)^category:\s*.*$', f'category: {new_name}', text)
        if new_text != text:
            md.write_text(new_text, encoding="utf-8")
            updated += 1
    # Update meta
    conn = _meta_conn()
    try:
        conn.execute("UPDATE skill_meta SET category = %s WHERE category = %s", (new_name, old_name))
        conn.commit()
    finally:
        conn.close()
    logger.info(f"重命名分类: {old_name} → {new_name}（{updated} 个 skill 更新）")
    return {"old_name": old_name, "new_name": new_name, "skills_updated": updated}


def delete_category(name: str) -> Dict[str, Any]:
    """删除分类"""
    _validate_category_name(name)
    skills_dir = _get_skills_dir()
    cat_dir = skills_dir / name
    # 安全校验：确保解析后的路径仍在 skills_dir 内
    if not str(cat_dir.resolve()).startswith(str(skills_dir.resolve() / "")):
        raise ValueError(f"分类名称不合法: '{name}'")
    if not cat_dir.exists():
        raise FileNotFoundError(f"分类不存在: {name}")
    data = list_skills()
    all_skills = (data.get("all_skills") or data.get("my_skills", []) + data.get("pool_skills", [])) if isinstance(data, dict) else data
    in_use = [s["name"] for s in all_skills if s.get("category") == name]
    if in_use:
        raise ValueError(f"无法删除分类 '{name}'，仍有 {len(in_use)} 个技能属于该分类: {', '.join(in_use[:5])}" + ("..." if len(in_use) > 5 else ""))
    shutil.rmtree(str(cat_dir))
    logger.info(f"删除分类: {name}")
    return {"name": name, "deleted": True}


# ── 用户自定义分类（虚拟标签） ──

def get_user_categories(user_id: int) -> List[str]:
    """获取用户自定义的分类列表。"""
    if not user_id:
        return []
    conn = _meta_conn()
    try:
        cur = conn.execute(
            "SELECT category FROM user_categories WHERE user_id = %s ORDER BY category",
            (int(user_id),),
        )
        rows = cur.fetchall() if hasattr(cur, 'fetchall') else [r for r in (cur or [])]
        return [r["category"] if hasattr(r, '__getitem__') else r[0] for r in rows]
    except Exception:
        # 表不存在时，从用户的技能中提取分类
        all_skills = _query_all_skills()
        user_skills = [s for s in all_skills if s.get("owner_id") == int(user_id)]
        cats = set()
        for s in user_skills:
            cat = s.get("category", "")
            if cat and cat != "AI生成":
                cats.add(cat)
        return sorted(cats)
    finally:
        conn.close()


def create_user_category(user_id: int, category: str) -> Dict[str, str]:
    """创建用户自定义分类。"""
    if not category or not category.strip():
        raise ValueError("分类名称不能为空")
    category = category.strip()
    conn = _meta_conn()
    try:
        conn.execute(
            "INSERT IGNORE INTO user_categories (user_id, category) VALUES (%s, %s)",
            (int(user_id), category),
        )
        conn.commit()
        logger.info(f"用户 {user_id} 创建分类: {category}")
        return {"category": category}
    finally:
        conn.close()


def rename_user_category(user_id: int, old_name: str, new_name: str) -> Dict[str, Any]:
    """重命名用户自定义分类。"""
    if not new_name or not new_name.strip():
        raise ValueError("新分类名称不能为空")
    new_name = new_name.strip()
    conn = _meta_conn()
    try:
        # 更新分类表
        conn.execute(
            "UPDATE user_categories SET category = %s WHERE user_id = %s AND category = %s",
            (new_name, int(user_id), old_name),
        )
        # 更新技能 meta 中的分类
        conn.execute(
            "UPDATE skill_meta SET category = %s WHERE owner_id = %s AND category = %s",
            (new_name, int(user_id), old_name),
        )
        conn.commit()
        logger.info(f"用户 {user_id} 重命名分类: {old_name} → {new_name}")
        return {"old_name": old_name, "new_name": new_name}
    finally:
        conn.close()


def delete_user_category(user_id: int, category: str) -> Dict[str, Any]:
    """删除用户自定义分类（不删除技能，只移除分类标签）。"""
    conn = _meta_conn()
    try:
        conn.execute(
            "DELETE FROM user_categories WHERE user_id = %s AND category = %s",
            (int(user_id), category),
        )
        conn.commit()
        logger.info(f"用户 {user_id} 删除分类: {category}")
        return {"category": category, "deleted": True}
    finally:
        conn.close()


def set_skill_category(user_id: int, skill_name: str, category: str) -> Dict[str, Any]:
    """设置技能的分类（用户自己的技能）。"""
    # 检查是否是用户自己的技能
    all_skills = _query_all_skills()
    skill = next((s for s in all_skills if s.get("name") == skill_name), None)
    if not skill:
        raise FileNotFoundError(f"技能不存在: {skill_name}")
    if skill.get("owner_id") != int(user_id):
        raise ValueError("无权修改此技能的分类")

    _meta_update(skill_name, category=category)

    # 自动添加到用户分类列表（如果不存在）
    conn = _meta_conn()
    try:
        conn.execute(
            "INSERT IGNORE INTO user_categories (user_id, category) VALUES (%s, %s)",
            (int(user_id), category),
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(f"技能 {skill_name} 分类设为: {category}")
    return {"name": skill_name, "category": category}
