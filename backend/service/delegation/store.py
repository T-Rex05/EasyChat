"""多 Agent 委派留痕 —— delegation_tasks 表读写

为什么需要它：Hermes 的 `delegate_task` 全链路是 best-effort 的（富化异常静默跳过、
SSE 帧丢失静默跳过、后台结果投进 completion_queue）。一旦出问题，宿主侧"什么都没留下"。
本模块把委派的每个阶段落库，让"派了什么/跑到哪/回来没有/为什么没回来"可查。

两个写入点：
  1. 生命周期（hermes_adapter 的子 Agent 事件回调）：started → tool → completed
  2. 结果回流（drain completion event 时）：按 Hermes 的权威事件回填
     delegation_id / summary / tokens / api_calls —— 这一路即使前面全丢也能补上

设计约束：
  - 全链路 fail-soft：DB 不可用或任何异常只记 debug，绝不阻断委派/对话
  - 幂等：subagent_id 唯一键 + INSERT ... ON DUPLICATE KEY UPDATE，重放不会翻倍
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 数据库熔断 ──
# 连接池在 MySQL 不可用时每次要重试 3 次（实测约 15 秒）。留痕是"锦上添花"的旁路，
# 绝不能因为 DB 抖动把 Agent 主循环卡住或把日志刷爆，所以：失败即跳闸，冷却期内直接跳过。
_BREAKER_FAIL_THRESHOLD = 1
_BREAKER_COOLDOWN_SECONDS = 60.0
_breaker_lock = threading.Lock()
_breaker = {"failures": 0, "open_until": 0.0}


def _db_available() -> bool:
    with _breaker_lock:
        return time.time() >= _breaker["open_until"]


def _note_success() -> None:
    with _breaker_lock:
        _breaker["failures"] = 0
        _breaker["open_until"] = 0.0


def _note_failure(err: Any) -> None:
    with _breaker_lock:
        _breaker["failures"] += 1
        if _breaker["failures"] >= _BREAKER_FAIL_THRESHOLD:
            _breaker["open_until"] = time.time() + _BREAKER_COOLDOWN_SECONDS
            logger.warning(
                "[delegation.store] 留痕写库失败，暂停 %.0fs（不影响委派与对话）: %s",
                _BREAKER_COOLDOWN_SECONDS,
                err,
            )


def reset_breaker() -> None:
    """测试/运维用：手动复位熔断。"""
    with _breaker_lock:
        _breaker["failures"] = 0
        _breaker["open_until"] = 0.0

# Hermes 的 results[].status → 我们表里的状态
_STATUS_MAP = {
    "completed": "completed",
    "success": "completed",
    "error": "error",
    "failed": "error",
    "timeout": "interrupted",
    "interrupted": "interrupted",
    "cancelled": "interrupted",
    "canceled": "interrupted",
    "stalled": "error",
    # 进程重启后由 Hermes 的 async_delegations WAL 恢复出来的未知态
    "unknown": "runtime_lost",
}

_MAX_SUMMARY_CHARS = 20000


class _StoreUnavailable(Exception):
    """熔断期占位异常：让各写入函数走各自的 except 兜底，快速失败而不是等连接池重试。"""


def _conn():
    """取连接，并把熔断状态维护收敛在这一处。

    - 熔断打开时立刻抛异常（各调用方的 except 兜底，绝不阻塞调用线程）
    - 连接失败 → 记一次失败并跳闸（连接池在 DB 不可用时单次要约 15s）
    - 连接成功 → 复位熔断
    """
    if not _db_available():
        raise _StoreUnavailable("留痕熔断中，跳过本次写入")
    try:
        from backend.db.schema import get_conn

        conn = get_conn()
    except Exception as e:
        _note_failure(e)
        raise
    _note_success()
    return conn


def _parse_task_index(subagent_id: Optional[str]) -> Optional[int]:
    """从 subagent_id 解析批内序号（Hermes 格式：sa-<task_index>-<hex8>）。"""
    if not subagent_id:
        return None
    parts = str(subagent_id).split("-")
    if len(parts) >= 3 and parts[0] == "sa":
        try:
            return int(parts[1])
        except (TypeError, ValueError):
            return None
    return None


def _clip(text: Any, limit: int = _MAX_SUMMARY_CHARS) -> Optional[str]:
    if text is None:
        return None
    s = str(text)
    return s[:limit]


# ──────────────────────────────────────────────────────────────
# 写入点 1：生命周期（子 Agent 事件）
# ──────────────────────────────────────────────────────────────


def record_subagent_started(
    *,
    subagent_id: str,
    goal: str = "",
    model: Optional[str] = None,
    depth: int = 0,
    thread_id: Optional[str] = None,
    user_id: int = 0,
    parent_session_id: Optional[str] = None,
    child_session_id: Optional[str] = None,
) -> None:
    """子 Agent 开始执行。幂等（同一 subagent_id 重放只刷新状态）。"""
    if not subagent_id:
        return
    conn = None
    try:
        conn = _conn()
        conn.execute(
            """INSERT INTO delegation_tasks
               (subagent_id, task_index, child_session_id, parent_session_id, thread_id,
                user_id, goal, model, depth, status, started_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'running', NOW())
               ON DUPLICATE KEY UPDATE
                 status = VALUES(status),
                 goal = VALUES(goal),
                 model = VALUES(model),
                 depth = VALUES(depth),
                 thread_id = VALUES(thread_id),
                 user_id = VALUES(user_id),
                 child_session_id = COALESCE(VALUES(child_session_id), child_session_id)""",
            (
                str(subagent_id),
                _parse_task_index(subagent_id),
                child_session_id or None,
                parent_session_id,
                thread_id,
                int(user_id or 0),
                _clip(goal, 4000) or "",
                model,
                int(depth or 0),
            ),
        )
        conn.commit()
    except Exception as e:
        logger.debug("委派留痕写入失败(started): %s", e)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def record_subagent_tool(subagent_id: str) -> None:
    """子 Agent 调用一次工具 → 计数 +1。"""
    if not subagent_id:
        return
    conn = None
    try:
        conn = _conn()
        conn.execute(
            "UPDATE delegation_tasks SET tool_count = tool_count + 1 WHERE subagent_id = %s",
            (str(subagent_id),),
        )
        conn.commit()
    except Exception as e:
        logger.debug("委派留痕写入失败(tool): %s", e)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def set_tool_count(subagent_id: str, count: int) -> None:
    """按绝对值写工具调用次数。

    逐次调用都写库会把共享线程池（safe_executor 只有 4 个 worker，记忆提取/事件发布
    也在用）灌满，所以调用方按批次落库；最终值由 complete 事件权威覆盖。
    """
    if not subagent_id:
        return
    conn = None
    try:
        conn = _conn()
        conn.execute(
            "UPDATE delegation_tasks SET tool_count = %s WHERE subagent_id = %s",
            (int(count or 0), str(subagent_id)),
        )
        conn.commit()
    except Exception as e:
        logger.debug("委派留痕写入失败(tool_count): %s", e)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def record_subagent_completed(
    *,
    subagent_id: str,
    status: str = "completed",
    tool_count: Optional[int] = None,
    api_calls: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    duration_seconds: float = 0,
    summary: Optional[str] = None,
    error: Optional[str] = None,
    child_session_id: Optional[str] = None,
) -> None:
    """子 Agent 执行结束（实时事件路径，权威校准在结果回流时进行）。"""
    if not subagent_id:
        return
    conn = None
    try:
        conn = _conn()
        sets = [
            "status = %s",
            "api_calls = %s",
            "input_tokens = %s",
            "output_tokens = %s",
            "duration_seconds = %s",
            "completed_at = NOW()",
        ]
        params: List[Any] = [
            _STATUS_MAP.get(str(status), str(status) or "completed"),
            int(api_calls or 0),
            int(input_tokens or 0),
            int(output_tokens or 0),
            float(duration_seconds or 0),
        ]
        if tool_count is not None:
            sets.append("tool_count = %s")
            params.append(int(tool_count))
        if summary:
            sets.append("summary = %s")
            params.append(_clip(summary))
        if error:
            sets.append("error_message = %s")
            params.append(_clip(error, 4000))
        if child_session_id:
            sets.append("child_session_id = COALESCE(child_session_id, %s)")
            params.append(str(child_session_id))
        params.append(str(subagent_id))
        conn.execute(
            f"UPDATE delegation_tasks SET {', '.join(sets)} WHERE subagent_id = %s",
            tuple(params),
        )
        conn.commit()
    except Exception as e:
        logger.debug("委派留痕写入失败(completed): %s", e)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def attach_result_by_child_session(child_session_id: str, summary: str) -> int:
    """把子 Agent 的最终产出按 child_session_id 回填（Hermes on_delegation 路径）。

    on_delegation 与结果回流是两条独立通道，谁先到都能把 summary 补上；
    这里只在 summary 还空着时写入，避免覆盖回流通道的权威值。
    """
    if not child_session_id or not summary:
        return 0
    conn = None
    try:
        conn = _conn()
        cur = conn.execute(
            """UPDATE delegation_tasks
               SET summary = %s,
                   status = CASE WHEN status = 'running' THEN 'completed' ELSE status END,
                   completed_at = COALESCE(completed_at, NOW())
               WHERE child_session_id = %s
                 AND (summary IS NULL OR summary = '')""",
            (_clip(summary), str(child_session_id)),
        )
        conn.commit()
        return int(getattr(cur, "rowcount", 0) or 0)
    except Exception as e:
        logger.debug("委派留痕写入失败(on_delegation): %s", e)
        return 0
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def record_rejected_sync(
    *,
    goals: List[str],
    thread_id: Optional[str] = None,
    user_id: int = 0,
    parent_session_id: Optional[str] = None,
    reason: str = "",
) -> None:
    """后台委派池满 → Hermes 静默降级为同步执行。留一条痕，避免"父轮被阻塞"无据可查。"""
    conn = None
    try:
        conn = _conn()
        merged = "; ".join(str(g)[:200] for g in (goals or [])[:5])
        conn.execute(
            """INSERT INTO delegation_tasks
               (parent_session_id, thread_id, user_id, goal, status, error_message,
                started_at, completed_at)
               VALUES (%s, %s, %s, %s, 'rejected_sync', %s, NOW(), NOW())""",
            (
                parent_session_id,
                thread_id,
                int(user_id or 0),
                f"[后台池满·同步降级] {merged}",
                _clip(reason, 1000) or "async delegation pool at capacity",
            ),
        )
        conn.commit()
    except Exception as e:
        logger.debug("委派留痕写入失败(rejected_sync): %s", e)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ──────────────────────────────────────────────────────────────
# 写入点 2：结果回流时的权威校准
# ──────────────────────────────────────────────────────────────


def reconcile_from_completion_event(
    evt: Dict[str, Any],
    *,
    thread_id: Optional[str] = None,
    user_id: int = 0,
    parent_session_id: Optional[str] = None,
) -> Dict[str, int]:
    """用 Hermes 的 completion 事件校准本批委派的落库结果。

    匹配策略（宽进严出）：
      1. 优先按 (parent_session_id, task_index) 找还没绑定 delegation_id 的活跃行 → 回填；
      2. 候选不唯一时用 goal 精确匹配消歧；
      3. 完全匹配不上（例如本进程没收到过生命周期事件）→ 直接按事件内容插入新行。
    这样即使生命周期事件全丢，留痕也不会缺失。
    """
    delegation_id = str(evt.get("delegation_id") or "") or None
    results = evt.get("results") or []
    goals = evt.get("goals") or []
    live_transcripts = evt.get("live_transcripts") or []
    total_duration = evt.get("total_duration_seconds")
    evt_status = str(evt.get("status") or "completed")
    batch_error = evt.get("error")

    stats = {"linked": 0, "inserted": 0, "failed": 0}
    conn = None
    try:
        conn = _conn()

        if not results:
            # 整批失败 / 无逐任务结果：只留一条汇总痕
            insert_res = conn.execute(
                """INSERT INTO delegation_tasks
                   (delegation_id, parent_session_id, thread_id, user_id, goal,
                    status, error_message, duration_seconds, started_at, completed_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())""",
                (
                    delegation_id,
                    parent_session_id,
                    thread_id,
                    int(user_id or 0),
                    _clip(evt.get("goal") or "; ".join(str(g) for g in goals), 4000) or "",
                    _STATUS_MAP.get(evt_status, evt_status),
                    _clip(batch_error, 4000),
                    float(total_duration or 0),
                ),
            )
            stats["inserted"] = 1 if insert_res is not None else 0
            conn.commit()
            return stats

        for r in results:
            if not isinstance(r, dict):
                continue
            task_index = r.get("task_index")
            status = _STATUS_MAP.get(str(r.get("status") or ""), str(r.get("status") or "completed"))
            tokens = r.get("tokens") or {}
            goal = ""
            if isinstance(task_index, int) and 0 <= task_index < len(goals):
                goal = str(goals[task_index] or "")
            transcript = ""
            if isinstance(task_index, int) and 0 <= task_index < len(live_transcripts):
                transcript = str(live_transcripts[task_index] or "")

            row_id = _find_live_row(conn, parent_session_id, task_index, goal)
            if row_id is not None:
                conn.execute(
                    """UPDATE delegation_tasks
                       SET delegation_id = %s, status = %s, api_calls = %s,
                           input_tokens = %s, output_tokens = %s, duration_seconds = %s,
                           summary = %s, error_message = %s, live_transcript = %s,
                           model = COALESCE(%s, model), completed_at = NOW()
                       WHERE id = %s""",
                    (
                        delegation_id,
                        status,
                        int(r.get("api_calls") or 0),
                        int((tokens or {}).get("input") or 0),
                        int((tokens or {}).get("output") or 0),
                        float(r.get("duration_seconds") or 0),
                        _clip(r.get("summary")),
                        _clip(r.get("error"), 4000),
                        transcript or None,
                        r.get("model"),
                        row_id,
                    ),
                )
                stats["linked"] += 1
            else:
                conn.execute(
                    """INSERT INTO delegation_tasks
                       (delegation_id, task_index, parent_session_id, thread_id, user_id,
                        goal, model, status, api_calls, input_tokens, output_tokens,
                        duration_seconds, summary, error_message, live_transcript,
                        started_at, completed_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                               NOW(), NOW())""",
                    (
                        delegation_id,
                        task_index if isinstance(task_index, int) else None,
                        parent_session_id,
                        thread_id,
                        int(user_id or 0),
                        _clip(goal, 4000) or "",
                        r.get("model"),
                        status,
                        int(r.get("api_calls") or 0),
                        int((tokens or {}).get("input") or 0),
                        int((tokens or {}).get("output") or 0),
                        float(r.get("duration_seconds") or 0),
                        _clip(r.get("summary")),
                        _clip(r.get("error"), 4000),
                        transcript or None,
                    ),
                )
                stats["inserted"] += 1

        conn.commit()
    except Exception as e:
        stats["failed"] = 1
        logger.debug("委派留痕写入失败(reconcile): %s", e)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    return stats


def _find_live_row(conn, parent_session_id: Optional[str], task_index: Any, goal: str) -> Optional[int]:
    """找本批里还没绑定 delegation_id 的生命周期行（用于回填）。"""
    if not parent_session_id or not isinstance(task_index, int):
        return None
    cur = conn.execute(
        """SELECT id, goal FROM delegation_tasks
           WHERE parent_session_id = %s AND task_index = %s AND delegation_id IS NULL
           ORDER BY started_at DESC LIMIT 5""",
        (parent_session_id, task_index),
    )
    rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    if not rows:
        return None
    if len(rows) == 1:
        return int(rows[0]["id"])
    # 候选不唯一：用 goal 精确消歧，仍不唯一则取最新一条
    if goal:
        for row in rows:
            if str(row.get("goal") or "").strip() == goal.strip():
                return int(row["id"])
    return int(rows[0]["id"])


def mark_delivered(delegation_id: str) -> int:
    """标记本批结果已回流进父对话。返回受影响行数（0 表示库里没有这批的痕）。"""
    if not delegation_id:
        return 0
    conn = None
    try:
        conn = _conn()
        cur = conn.execute(
            "UPDATE delegation_tasks SET delivered = 1 WHERE delegation_id = %s",
            (str(delegation_id),),
        )
        conn.commit()
        return int(getattr(cur, "rowcount", 0) or 0)
    except Exception as e:
        logger.debug("委派留痕写入失败(delivered): %s", e)
        return 0
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ──────────────────────────────────────────────────────────────
# 只读查询（前端历史回填）
# ──────────────────────────────────────────────────────────────


def list_by_thread(thread_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """按 AgentForge 会话列出委派记录（新→旧）。DB 不可用时返回空列表。"""
    if not thread_id:
        return []
    conn = None
    try:
        conn = _conn()
        cur = conn.execute(
            """SELECT delegation_id, subagent_id, task_index, child_session_id,
                      goal, model, depth, status,
                      tool_count, api_calls, input_tokens, output_tokens,
                      duration_seconds, summary, error_message,
                      delivered, duplicate_hint, started_at, completed_at
               FROM delegation_tasks
               WHERE thread_id = %s
               ORDER BY started_at DESC, id DESC
               LIMIT %s""",
            (str(thread_id), int(limit)),
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        return [dict(r) for r in rows]
    except Exception as e:
        logger.debug("委派留痕查询失败: %s", e)
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
