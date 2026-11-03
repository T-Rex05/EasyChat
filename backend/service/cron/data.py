"""
定时任务数据访问层

负责 cron_jobs 和 cron_executions 表的 CRUD 操作。
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from backend.db.schema import get_conn


class CronDataMapper:
    """定时任务数据访问 — 使用 schema.get_conn() 获取 MySQL 连接。"""

    @staticmethod
    def _row_to_dict(row) -> dict:
        """pymysql dict → 统一 dict。"""
        if row is None:
            return None
        if hasattr(row, "keys"):
            return dict(row)
        if hasattr(row, "_mapping"):
            return dict(row._mapping)
        return dict(row)

    @staticmethod
    def _rows_to_list(cur) -> list:
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        return [CronDataMapper._row_to_dict(r) for r in rows]

    # ── cron_jobs CRUD ──

    def list_jobs(self, user_id: int, enabled_only: bool = False) -> list:
        conn = get_conn()
        try:
            sql = "SELECT * FROM cron_jobs WHERE user_id = ?"
            if enabled_only:
                sql += " AND enabled = 1"
            sql += " ORDER BY created_at DESC"
            cur = conn.execute(sql, (user_id,))
            return self._rows_to_list(cur)
        finally:
            conn.close()

    def list_all_enabled_jobs(self) -> list:
        """获取所有启用的定时任务（启动恢复用）。"""
        conn = get_conn()
        try:
            cur = conn.execute(
                "SELECT * FROM cron_jobs WHERE enabled = 1 ORDER BY id"
            )
            return self._rows_to_list(cur)
        finally:
            conn.close()

    def get_job(self, job_id: int) -> Optional[dict]:
        conn = get_conn()
        try:
            cur = conn.execute("SELECT * FROM cron_jobs WHERE id = %s", (job_id,))
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            if not rows:
                return None
            return self._row_to_dict(rows[0])
        finally:
            conn.close()

    def create_job(self, user_id: int, name: str, prompt: str,
                   schedule_type: str, schedule_value: str,
                   deliver_to: str = "wechat",
                   email_sender_id: Optional[int] = None,
                   email_receiver_id: Optional[int] = None,
                   receiver_email: str = "",
                   report_format: str = "pdf") -> int:
        conn = get_conn()
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur = conn.execute(
                """INSERT INTO cron_jobs (user_id, name, prompt, schedule_type, schedule_value,
                   deliver_to, report_format, email_sender_id, email_receiver_id, receiver_email,
                   enabled, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s)""",
                (int(user_id), name, prompt, schedule_type, schedule_value,
                 deliver_to, report_format, email_sender_id, email_receiver_id, receiver_email,
                 now, now),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def update_job(self, job_id: int, **kwargs) -> bool:
        allowed = {"name", "prompt", "schedule_type", "schedule_value", "deliver_to", "enabled",
                   "email_sender_id", "email_receiver_id", "report_format"}
        updates = {}
        for k, v in kwargs.items():
            if k in allowed and v is not None:
                updates[k] = v
        if not updates:
            return False
        conn = get_conn()
        try:
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            vals = list(updates.values())
            vals.append(job_id)
            cur = conn.execute(
                f"UPDATE cron_jobs SET {set_clause}, updated_at = %s WHERE id = %s",
                (*updates.values(), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), job_id),
            )
            conn.commit()
            return cur.rowcount > 0 if hasattr(cur, "rowcount") else True
        finally:
            conn.close()

    def delete_job(self, job_id: int) -> bool:
        conn = get_conn()
        try:
            cur = conn.execute("DELETE FROM cron_jobs WHERE id = %s", (job_id,))
            conn.commit()
            return cur.rowcount > 0 if hasattr(cur, "rowcount") else True
        finally:
            conn.close()

    def mark_run(self, job_id: int, status: int, error_message: str = ""):
        conn = get_conn()
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """UPDATE cron_jobs SET last_run_at = %s, updated_at = %s WHERE id = %s""",
                (now, now, job_id),
            )
            conn.commit()
        finally:
            conn.close()

    def set_next_run(self, job_id: int, next_time: datetime):
        conn = get_conn()
        try:
            conn.execute(
                "UPDATE cron_jobs SET next_run_at = %s WHERE id = %s",
                (next_time.strftime("%Y-%m-%d %H:%M:%S"), job_id),
            )
            conn.commit()
        finally:
            conn.close()

    # ── cron_executions CRUD ──

    def create_execution(self, job_id: int, session_id: str = "") -> int:
        conn = get_conn()
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur = conn.execute(
                """INSERT INTO cron_executions (job_id, session_id, status, started_at)
                   VALUES (?, ?, 0, ?)""",
                (job_id, session_id, now),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def finish_execution(self, execution_id: int, status: int,
                         result_text: str = "", error_message: str = "",
                         deliver_status: str = "", quality_issues: str = ""):
        conn = get_conn()
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """UPDATE cron_executions
                   SET status = ?, result_text = ?, error_message = ?,
                       deliver_status = ?, quality_issues = ?, finished_at = ?
                   WHERE id = ?""",
                (status, result_text, error_message, deliver_status, quality_issues, now, execution_id),
            )
            conn.commit()
        finally:
            conn.close()

    def list_executions(self, job_id: int, limit: int = 20) -> list:
        conn = get_conn()
        try:
            cur = conn.execute(
                "SELECT * FROM cron_executions WHERE job_id = ? ORDER BY started_at DESC LIMIT ?",
                (job_id, limit),
            )
            return self._rows_to_list(cur)
        finally:
            conn.close()
