"""
技能元数据管理模块

负责技能元数据的数据库操作，包括 skill_meta、item_status、user_categories 等表的操作。
"""
from typing import Dict, Any, Optional, List
from backend.utils.log_utils import log
from backend.db.schema import get_conn

logger = log


def _meta_conn():
    """获取数据库连接"""
    return get_conn()


def _meta_insert(name: str, owner_id: int, category: str, status: str = "approved") -> None:
    """插入技能元数据，同时初始化 item_status 为启用状态"""
    conn = _meta_conn()
    try:
        cur = conn.execute("SELECT id FROM skill_meta WHERE name = %s", (name,))
        rows = cur.fetchall() if hasattr(cur, 'fetchall') else [r for r in (cur or [])]
        if not rows:
            conn.execute(
                "INSERT INTO skill_meta (name, owner_id, category, status, locked) VALUES (%s, %s, %s, %s, 0)",
                (name, owner_id, category, status),
            )
            # 同时在 item_status 中插入启用状态记录
            conn.execute(
                "INSERT IGNORE INTO item_status (item_type, item_name, enabled) VALUES ('skill', %s, 1)",
                (name,),
            )
            conn.commit()
    finally:
        conn.close()


def _meta_get(name: str) -> Optional[Dict[str, Any]]:
    """获取技能元数据"""
    conn = _meta_conn()
    try:
        cur = conn.execute("SELECT * FROM skill_meta WHERE name = %s", (name,))
        rows = cur.fetchall() if hasattr(cur, 'fetchall') else [r for r in (cur or [])]
        return dict(rows[0]) if rows else None
    except Exception as e:
        logger.warning(f"_meta_get {name}: {e}")
        return None
    finally:
        conn.close()


def _meta_update(name: str, **kwargs) -> None:
    """更新技能元数据"""
    if not kwargs:
        return
    conn = _meta_conn()
    try:
        # 先检查记录是否存在
        cur = conn.execute("SELECT id FROM skill_meta WHERE name = %s", (name,))
        rows = cur.fetchall() if hasattr(cur, 'fetchall') else [r for r in (cur or [])]
        if rows:
            sets = [f"{k} = %s" for k in kwargs]
            vals = list(kwargs.values()) + [name]
            conn.execute(f"UPDATE skill_meta SET {', '.join(sets)} WHERE name = %s", vals)
        else:
            # 不存在则插入：默认 owner_id=1, category='', status='approved'
            fields = ["name", "owner_id", "category", "status"]
            values = [name, 1, "", "approved"]
            placeholders = ["%s", "%s", "%s", "%s"]
            for k, v in kwargs.items():
                if k not in fields:
                    fields.append(k)
                    values.append(v)
                    placeholders.append("%s")
            conn.execute(
                f"INSERT INTO skill_meta ({', '.join(fields)}) VALUES ({', '.join(placeholders)})",
                values,
            )
        conn.commit()
    finally:
        conn.close()


def _meta_all() -> Dict[str, Dict[str, Any]]:
    """获取所有技能元数据"""
    conn = _meta_conn()
    try:
        cur = conn.execute("SELECT * FROM skill_meta")
        rows = cur.fetchall() if hasattr(cur, 'fetchall') else [r for r in (cur or [])]
        return {r["name"]: dict(r) for r in rows}
    except Exception:
        return {}
    finally:
        conn.close()


def _get_item_status(item_type: str) -> Dict[str, bool]:
    """获取项目启用状态"""
    try:
        conn = get_conn()
        try:
            rows = conn.execute("SELECT item_name, enabled FROM item_status WHERE item_type = %s", (item_type,)).fetchall()
            return {r["item_name"]: bool(r["enabled"]) for r in rows}
        finally:
            conn.close()
    except Exception:
        return {}


def toggle_item_status(item_type: str, item_name: str) -> bool:
    """切换项目启用状态"""
    conn = get_conn()
    try:
        cur = conn.execute("SELECT enabled FROM item_status WHERE item_type = %s AND item_name = %s", (item_type, item_name))
        rows = cur.fetchall() if hasattr(cur, 'fetchall') else [r for r in (cur or [])]
        current = rows[0]["enabled"] if rows else 1
        new_val = 0 if current == 1 else 1
        conn.execute("UPDATE item_status SET enabled = %s WHERE item_type = %s AND item_name = %s", (new_val, item_type, item_name))
        check = conn.execute("SELECT id FROM item_status WHERE item_type = %s AND item_name = %s", (item_type, item_name))
        check_rows = check.fetchall() if hasattr(check, 'fetchall') else [r for r in (check or [])]
        if not check_rows:
            conn.execute("INSERT INTO item_status (item_type, item_name, enabled) VALUES (%s, %s, %s)", (item_type, item_name, new_val))
        conn.commit()
        return bool(new_val)
    except Exception as e:
        logger.warning(f"toggle_item_status failed: {e}")
        try:
            conn.execute("INSERT IGNORE INTO item_status (item_type, item_name, enabled) VALUES (%s, %s, %s)", (item_type, item_name, 0))
            conn.commit()
            return False
        except Exception:
            return True
    finally:
        conn.close()


def sync_item_status_for_skills() -> int:
    """同步所有技能到 item_status 表（用于迁移）
    
    将 skill_meta 中存在的技能同步到 item_status，确保每个技能都有状态记录。
    返回新增的记录数。
    """
    conn = get_conn()
    try:
        # 获取所有技能名称
        cur = conn.execute("SELECT name FROM skill_meta")
        rows = cur.fetchall() if hasattr(cur, 'fetchall') else [r for r in (cur or [])]
        skill_names = [r["name"] for r in rows]
        
        # 获取已存在的 item_status 记录
        cur = conn.execute("SELECT item_name FROM item_status WHERE item_type = 'skill'")
        existing = {r["item_name"] for r in (cur.fetchall() if hasattr(cur, 'fetchall') else [])}
        
        # 插入缺失的记录
        added = 0
        for name in skill_names:
            if name not in existing:
                conn.execute(
                    "INSERT IGNORE INTO item_status (item_type, item_name, enabled) VALUES ('skill', %s, 1)",
                    (name,),
                )
                added += 1
        
        # 清理废弃记录（item_status 中存在但 skill_meta 中不存在的）
        cur = conn.execute("SELECT item_name FROM item_status WHERE item_type = 'agent'")
        agent_names = [r["item_name"] for r in (cur.fetchall() if hasattr(cur, 'fetchall') else [])]
        # agent 类型已废弃，删除所有 agent 记录
        if agent_names:
            conn.execute("DELETE FROM item_status WHERE item_type = 'agent'")
            logger.info(f"清理废弃的 agent 记录: {len(agent_names)} 条")
        
        conn.commit()
        if added:
            logger.info(f"同步技能到 item_status: 新增 {added} 条记录")
        return added
    except Exception as e:
        logger.warning(f"sync_item_status_for_skills 失败: {e}")
        return 0
    finally:
        conn.close()
