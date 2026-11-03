"""
定时任务投递层

负责将定时任务执行结果通过邮件、微信等渠道投递给用户。
"""
import asyncio
import re
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.header import Header
from email.utils import formataddr
from pathlib import Path
from typing import Optional, Dict, Any

from backend.db.schema import get_conn
from backend.utils.log_utils import log

logger = log


class CronDelivery:
    """定时任务投递服务"""

    @staticmethod
    def _get_user_email_config(user_id: int, sender_id: Optional[int] = None) -> Optional[dict]:
        """查询用户的 SMTP 邮箱配置。如指定 sender_id 则优先用指定配置。"""
        conn = get_conn()
        try:
            if sender_id:
                cur = conn.execute(
                    "SELECT * FROM email_configs WHERE id = ? AND enabled = 1",
                    (sender_id,),
                )
            else:
                cur = conn.execute(
                    """SELECT * FROM email_configs
                       WHERE (user_id = ? OR user_id = 1) AND is_current = 1 AND enabled = 1
                       ORDER BY user_id DESC LIMIT 1""",
                    (user_id,),
                )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            if rows:
                row = rows[0]
                return dict(row) if hasattr(row, "keys") else {"id": row[0], "host": row[2], "port": row[3], "sender_email": row[4], "sender_name": row[5], "password": row[6]}
            return None
        finally:
            conn.close()

    @staticmethod
    def _get_docs_dir(user_id: int, task_name: str = "") -> Path:
        """获取用户报告目录 docker/volumes/cron_reports/{用户名}/，自动创建。"""
        from backend.config.paths import get_cron_reports_dir
        # 获取用户名
        username = f"user_{user_id}"
        conn = get_conn()
        try:
            cur = conn.execute("SELECT username FROM users WHERE id = %s", (user_id,))
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            if rows:
                row = rows[0]
                username = row["username"] if isinstance(row, dict) else row[0]
        except Exception:
            pass
        finally:
            conn.close()
        
        # 使用统一的报告目录
        return get_cron_reports_dir(username)

    @staticmethod
    def get_report_dir(user_id: int) -> Path:
        """获取用户报告目录（供外部调用）"""
        return CronDelivery._get_docs_dir(user_id)

    @staticmethod
    def safe_filename(name: str) -> str:
        """把任务名称转为安全的文件名。"""
        return CronDelivery._safe_filename(name)

    @staticmethod
    def _safe_filename(name: str) -> str:
        """把任务名称转为安全的文件名。

        - 移除/替换不允许在文件名中出现的字符
        - 处理 Unicode box-drawing 字符（在 PDF 中无法渲染）
        - 限制长度，防止路径过长
        """
        safe = str(name or "")
        # 移除控制字符和特殊字符
        safe = re.sub(r'[\x00-\x1f\x7f]', '', safe)
        # 替换不允许的文件名字符
        safe = re.sub(r'[\\/:*?"<>|]', '_', safe)
        # 移除 emoji 和其他辅助平面字符
        safe = re.sub(r'[\U00010000-\U0010ffff]', '', safe)
        # 替换 box-drawing 字符为 ASCII
        box_chars = {
            '\u2500': '-', '\u2501': '=', '\u2502': '|', '\u2503': '|',
            '\u250c': '+', '\u250d': '+', '\u250e': '+', '\u250f': '+',
            '\u2510': '+', '\u2511': '+', '\u2512': '+', '\u2513': '+',
            '\u2514': '+', '\u2515': '+', '\u2516': '+', '\u2517': '+',
            '\u2518': '+', '\u2519': '+', '\u251a': '+', '\u251b': '+',
            '\u251c': '+', '\u251d': '+', '\u251e': '+', '\u251f': '+',
            '\u2520': '+', '\u2521': '+', '\u2522': '+', '\u2523': '+',
            '\u2524': '+', '\u2525': '+', '\u2526': '+', '\u2527': '+',
            '\u2528': '+', '\u2529': '+', '\u252a': '+', '\u252b': '+',
            '\u253c': '+', '\u253d': '+', '\u253e': '+', '\u253f': '+',
            '\u2540': '+', '\u2541': '+', '\u2542': '+', '\u2543': '+',
            '\u2544': '+', '\u2545': '+', '\u2546': '+', '\u2547': '+',
            '\u2548': '+', '\u2549': '+', '\u254a': '+', '\u254b': '+',
            '\u2550': '=', '\u2551': '|',
            '\u2554': '+', '\u2555': '+', '\u2556': '+', '\u2557': '+',
            '\u2558': '+', '\u2559': '+', '\u255a': '+', '\u255b': '+',
            '\u255c': '+', '\u255d': '+', '\u255e': '+', '\u255f': '+',
            '\u2560': '+', '\u2561': '+', '\u2562': '+', '\u2563': '+',
            '\u2564': '+', '\u2565': '+', '\u2566': '+', '\u2567': '+',
            '\u2568': '+', '\u2569': '+', '\u256a': '+', '\u256b': '+',
            '\u256c': '+',
            '\u256d': '+', '\u256e': '+', '\u256f': '+', '\u2570': '+',
            '\u2571': '/', '\u2572': '\\', '\u2573': 'X',
        }
        for box, ascii_char in box_chars.items():
            safe = safe.replace(box, ascii_char)
        # 清理空白和点
        safe = safe.strip().rstrip('.') or 'report'
        # 限制长度
        return safe[:80]

    @staticmethod
    def _get_user_receiver_email(user_id: int, receiver_id: Optional[int] = None) -> Optional[str]:
        """查询用户个人邮箱地址。如指定 receiver_id 则优先用指定邮箱。"""
        conn = get_conn()
        try:
            if receiver_id:
                cur = conn.execute(
                    "SELECT email FROM personal_emails WHERE id = ?",
                    (receiver_id,),
                )
            else:
                cur = conn.execute(
                    """SELECT email FROM personal_emails
                       WHERE user_id = ? AND is_current = 1 LIMIT 1""",
                    (user_id,),
                )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            if rows:
                row = rows[0]
                return row["email"] if isinstance(row, dict) else row[0]
            return None
        finally:
            conn.close()

    async def deliver_email(self, task: dict, subject: str, body: str,
                            user_id: int):
        """通过 SMTP 发送邮件报告（含 PDF 附件）。返回 (是否成功, 失败原因)。"""
        try:
            sender_id = task.get("email_sender_id")
            receiver_id = task.get("email_receiver_id")
            email_config = self._get_user_email_config(user_id, sender_id)

            if not email_config:
                logger.warning(f"[cron] 用户未配置邮箱，跳过邮件投递: user_id={user_id}")
                return False, "未配置发件邮箱（SMTP）"

            # 优先使用 receiver_email 字段（AI 对话创建时直接指定）
            receiver = task.get("receiver_email")
            if not receiver:
                # 回退到 personal_emails 表查询
                receiver = self._get_user_receiver_email(user_id, receiver_id)

            if not receiver:
                return False, "未配置收件邮箱"

            # 使用 SMTP 配置发邮件
            ok = self._send_smtp_email(email_config, receiver, subject, body, task)
            return (True, "") if ok else (False, "SMTP 发送失败，请检查邮箱配置")

        except Exception as e:
            logger.error(f"[cron] 邮件投递失败: {e}")
            return False, f"邮件投递异常: {e}"

    def _send_smtp_email(self, config: dict, receiver: str, subject: str,
                         body: str, task: dict) -> bool:
        """SMTP 发送（根据 report_format 决定格式：pdf 附件 / markdown HTML / 纯文本）。"""
        host = config.get("host") or ""
        port = int(config.get("port") or 587)
        sender = config.get("sender_email") or ""
        password = config.get("password") or ""
        sender_name = config.get("sender_name") or "AgentForge"
        report_format = (task.get("report_format") or "pdf").strip().lower()

        if not host or not sender or not password:
            logger.warning("[cron] 邮箱配置不完整")
            return False

        to_addr = receiver or sender

        msg = MIMEMultipart()
        msg["From"] = formataddr((sender_name, sender))
        msg["To"] = to_addr
        msg["Subject"] = Header(subject, "utf-8")

        # ── 根据格式构造正文 ──
        if report_format == "markdown":
            # 简单 markdown → HTML
            html = re.sub(r"```(\w*)\n(.*?)```", r"<pre><code>\2</code></pre>", body, flags=re.DOTALL)
            html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
            html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
            html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
            html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html)
            html = re.sub(r"\*(.+?)\*", r"<i>\1</i>", html)
            html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
            html_body = f"""<html><body style="font-family:system-ui,sans-serif;max-width:720px;margin:0 auto;padding:16px;">
<h2>{subject}</h2>
<div style="line-height:1.7;">{html}</div>
<hr><p style="color:#999;font-size:12px;">本报告由 AgentForge 定时任务自动生成 · Markdown 格式</p>
</body></html>"""
        elif report_format == "text":
            html_body = f"""<html><body style="font-family:system-ui,sans-serif;max-width:720px;margin:0 auto;padding:16px;">
<h2>{subject}</h2>
<pre style="white-space:pre-wrap;font-family:monospace;background:#f7f8fa;padding:12px;border-radius:8px;">{body[:8000]}</pre>
<hr><p style="color:#999;font-size:12px;">本报告由 AgentForge 定时任务自动生成 · 纯文本格式</p>
</body></html>"""
        else:  # pdf
            html_body = f"""<html><body style="font-family:system-ui,sans-serif;max-width:720px;margin:0 auto;padding:16px;">
<h2>{subject}</h2>
<p style="color:#666;">📎 报告 PDF 见附件。</p>
<hr><p style="color:#999;font-size:12px;">本报告由 AgentForge 定时任务自动生成</p>
</body></html>"""
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        # PDF 附件（仅 pdf 模式）
        if report_format == "pdf":
            try:
                # 统一使用通用 PDF 生成器
                pdf_bytes = self._generate_report_pdf(subject, body)
                
                if pdf_bytes:
                    pdf_part = MIMEBase("application", "pdf")
                    pdf_part.set_payload(pdf_bytes)
                    encoders.encode_base64(pdf_part)
                    # 使用统一的文件名规范（安全文件名 + 时间戳）
                    from backend.service.report.report_naming import build_report_filename
                    safe_name = self._safe_filename(subject)
                    pdf_filename = build_report_filename(safe_name, ext=".pdf")
                    # 使用 RFC 2231 编码处理中文文件名
                    pdf_part.add_header(
                        "Content-Disposition",
                        "attachment",
                        filename=("utf-8", "", pdf_filename),
                    )
                    msg.attach(pdf_part)
            except Exception as e:
                logger.warning(f"[cron] PDF 生成失败，发送纯文本邮件: {e}")

        server = None
        try:
            if port == 465:
                server = smtplib.SMTP_SSL(host, port, timeout=15)
            else:
                server = smtplib.SMTP(host, port, timeout=15)
                server.starttls()
            server.login(sender, password)
            server.sendmail(sender, [to_addr], msg.as_string())
            return True
        except Exception as e:
            logger.error(f"[cron] SMTP 发送失败: {e}")
            return False
        finally:
            if server:
                try:
                    server.quit()
                except Exception:
                    pass

    def _generate_report_pdf(self, subject: str, body: str) -> Optional[bytes]:
        """生成 PDF 报告（优先使用 WeasyPrint，回退到 reportlab）。"""
        try:
            # 优先使用 WeasyPrint（更美观）
            try:
                from backend.tools.pdf_generator_weasyprint import generate_report_pdf
                pdf_bytes = generate_report_pdf(subject, body)
                if pdf_bytes:
                    return pdf_bytes
                # WeasyPrint 失败，继续尝试 reportlab
            except ImportError:
                logger.debug("[cron] WeasyPrint 不可用，使用 reportlab")
            except Exception as e:
                logger.warning(f"[cron] WeasyPrint 生成失败，回退到 reportlab: {e}")

            # 回退到 reportlab
            from backend.tools.pdf_generator import generate_report_pdf as _generate_reportlab
            return _generate_reportlab(subject, body)
        except Exception as e:
            logger.opt(exception=True).error(f"[cron] PDF 生成失败: {e}")
            return None

    async def deliver_wechat(self, task: dict, subject: str, body: str,
                             user_id: int):
        """通过 iLink 发送文件到微信（PDF / Markdown / 纯文本）。

        返回 (是否成功, 失败原因)。失败原因会写入执行记录的 error_message。

        根据 report_format:
          - pdf      → 统一使用通用 PDF 生成器 → 以文件附件发送 + caption 文字
          - markdown → 写 .md 临时文件 → 以文件附件发送 + caption 文字
          - text     → 写 .txt 临时文件 → 以文件附件发送 + caption 文字
        """
        import aiohttp
        from backend.wechat import send_file_to_wechat
        from backend.controller.wechat.config import _get_wechat_config

        wx_config = _get_wechat_config()
        if not wx_config:
            logger.warning("[cron] 微信配置不可用，跳过微信投递")
            return False, "微信平台配置不可用"

        token = wx_config.get("token") or ""
        account_id = wx_config.get("account_id") or ""
        base_url = wx_config.get("base_url") or "https://ilinkai.weixin.qq.com"

        if not token or not account_id:
            logger.warning("[cron] 微信 token 或 account_id 为空")
            return False, "微信 token 或 account_id 为空"

        # 查找该用户的微信绑定
        conn = get_conn()
        wx_user_id = None
        try:
            cur = conn.execute(
                "SELECT open_id FROM user_bindings WHERE user_id = ? AND platform = 'wechat' AND enabled = 1 LIMIT 1",
                (user_id,),
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            if rows:
                row = rows[0]
                wx_user_id = row["open_id"] if isinstance(row, dict) else row[0]
        finally:
            conn.close()

        if not wx_user_id:
            logger.warning(f"[cron] 用户未绑定微信: user_id={user_id}")
            return False, "用户未绑定微信"

        report_format = (task.get("report_format") or "pdf").strip().lower()
        caption = f"📋【{subject}】"

        # ── 根据格式生成文件，保存到 data/cron_reports/{用户名}/ ──
        docs_dir = self._get_docs_dir(user_id, subject)
        safe_name = self._safe_filename(subject)
        # AgentForge-PATCH: 统一命名（时间戳防覆盖，借鉴 Eyes report_naming）
        from backend.service.report.report_naming import build_report_filename
        tmp_path = None
        try:
            if report_format == "pdf":
                # 统一使用通用 PDF 生成器
                pdf_bytes = self._generate_report_pdf(subject, body)
                if pdf_bytes:
                    file_path = docs_dir / build_report_filename(safe_name, ext=".pdf")
                    file_path.write_bytes(pdf_bytes)
                    tmp_path = str(file_path)
                    logger.info(f"[cron] PDF 已保存: {tmp_path}")
                else:
                    logger.error("[cron] PDF 生成失败，回退到文本")
                    report_format = "text"
                    # fall through to text

            if report_format in ("markdown", "text") and tmp_path is None:
                ext = ".md" if report_format == "markdown" else ".txt"
                file_path = docs_dir / build_report_filename(safe_name, ext=ext)
                file_path.write_text(body, encoding="utf-8")
                tmp_path = str(file_path)
                logger.info(f"[cron] 文件已保存: {tmp_path}")

            if not tmp_path:
                logger.error("[cron] 无法生成报告文件")
                return False, "报告文件生成失败"

            # ── 发送文件到微信 ──
            async with aiohttp.ClientSession() as session:
                ok, reason = await send_file_to_wechat(
                    session,
                    file_path=tmp_path,
                    to_user_id=wx_user_id,
                    token=token,
                    base_url=base_url,
                    caption=caption,
                )
            if ok:
                logger.info(f"[cron] 微信文件已发送: {Path(tmp_path).name}")
                return True, ""
            return False, reason or "微信文件发送失败"

        except Exception as e:
            logger.error(f"[cron] 微信投递失败: {e}")
            return False, f"微信投递异常: {e}"


# 全局单例
cron_delivery = CronDelivery()
