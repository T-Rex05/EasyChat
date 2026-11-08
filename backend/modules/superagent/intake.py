"""superagent 微信命令入口（T5，方案 §4 微信交互）。

确定性命令与自然语言工具进入同一 SuperagentService：
  /开发 <需求>            受理任务（幂等键 = 平台事件 ID；回执目标 = 本条消息来源）
  /任务 或 /任务列表      最近 5 个任务（短号 = task_id 末 6 位）
  /任务 <短号|sag_xxx>    任务详情
  /补充 <短号|sag_xxx> <内容>   追问回答/补充需求（幂等键 = 平台事件 ID）
  /取消 <短号|sag_xxx>    取消
  /重试 <短号|sag_xxx>    重试（新 attempt）

短号解析限定在"当前用户自己的任务"内，歧义时列出候选；所有命令都有
确定性解析与权限校验（service 层 Principal 判定）。
"""
from __future__ import annotations

import logging

from backend.modules.channels.contracts import InboundMessage
from backend.modules.delivery.contracts import DeliveryTarget
from backend.modules.superagent.api import SuperagentService
from backend.modules.superagent.contracts import (
    SOURCE_WECHAT,
    STATUS_LABELS,
    TASK_QUEUED,
    TASK_RUNNING,
)

logger = logging.getLogger(__name__)

_STATUS_TEXT = dict(STATUS_LABELS)
_STATUS_TEXT.setdefault(TASK_RUNNING, "执行中")
_LIST_LIMIT = 5
_TITLE_MAX = 40


class SuperagentIntake:
    """微信侧确定性命令 → SuperagentService；身份来自绑定 Principal。"""

    def __init__(self, service: SuperagentService) -> None:
        self.service = service

    async def handle(self, principal, message: InboundMessage) -> str | None:
        text = message.text.strip()
        if not text.startswith("/"):
            return None
        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""
        if command == "/开发":
            return await self._create(principal, message, rest)
        if command in ("/任务", "/任务列表"):
            return await self._list_or_detail(principal, rest)
        if command == "/补充":
            return await self._append_input(principal, message, rest)
        if command == "/取消":
            return await self._cancel(principal, rest)
        if command == "/重试":
            return await self._retry(principal, rest)
        return None

    # ---- /开发 ------------------------------------------------------------------

    async def _create(self, principal, message: InboundMessage, requirement: str) -> str:
        if not requirement:
            return (
                "用法：/开发 <需求描述>\n"
                "例如：/开发 修复导出 CSV 中文乱码，并补一个回归测试\n"
                "需求尽量写清楚目标和验收标准；信息不足时代理会追问。"
            )
        if len(requirement) > 4000:
            return "需求太长了（≤4000 字），请精简后重发。"
        target = DeliveryTarget(
            kind=message.platform,
            ref=message.external_user_id,
            channel_account_id=message.account_pk,
            context_token=message.context_token,
        )
        event_ref = message.external_event_id
        if event_ref.startswith("msg:"):
            event_ref = event_ref[4:]
        try:
            task = self.service.create_task(
                principal,
                title=requirement.splitlines()[0][:_TITLE_MAX],
                requirement=requirement,
                source=SOURCE_WECHAT,
                session_id="",
                idempotency_key=event_ref,
                source_target=target,
            )
        except Exception as exc:  # noqa: BLE001  AppError 消息本身面向用户
            reason = getattr(exc, "message", None) or str(exc)
            return f"任务受理失败：{reason}"
        label = "已受理" if task.status == TASK_QUEUED else f"当前状态：{_STATUS_TEXT.get(task.status, task.status)}"
        return (
            f"✅ {label}：{task.title}\n"
            f"任务号 {task.task_id}\n"
            f"短号 {short_id(task.task_id)} · 分支 {task.branch}\n"
            "后台代理会自动编码并创建 Draft PR，完成后回信通知你。\n"
            f"查询：/任务 {short_id(task.task_id)}；补充：/补充 {short_id(task.task_id)} <内容>"
        )

    # ---- 查询 ------------------------------------------------------------------

    async def _list_or_detail(self, principal, rest: str) -> str:
        token = rest.split()[0] if rest.strip() else ""
        if token:
            return await self._detail(principal, token)
        try:
            tasks = self.service.list_tasks(principal, limit=_LIST_LIMIT)
        except Exception as exc:  # noqa: BLE001
            return f"查询失败：{getattr(exc, 'message', None) or exc}"
        if not tasks:
            return "还没有编码任务。发「/开发 <需求>」创建。"
        lines = ["最近任务："]
        for task in tasks:
            lines.append(
                f"· {short_id(task.task_id)} {_STATUS_TEXT.get(task.status, task.status)} {task.title[:30]}"
                + (f" PR#{task.pr_number}" if task.pr_number else "")
            )
        lines.append("详情：/任务 <短号>")
        return "\n".join(lines)

    async def _detail(self, principal, token: str) -> str:
        try:
            task = self._resolve(principal, token)
        except _AmbiguousTask as exc:
            return str(exc)
        except Exception as exc:  # noqa: BLE001
            return f"查询失败：{getattr(exc, 'message', None) or exc}"
        lines = [f"{task.title}", f"状态：{_STATUS_TEXT.get(task.status, task.status)}"]
        if task.phase:
            lines[1] += f"（{task.phase}）"
        lines.append(f"任务号 {task.task_id}")
        lines.append(f"分支 {task.branch}")
        if task.pr_url:
            lines.append(f"PR：{task.pr_url}")
        if task.result_summary:
            lines.append(f"摘要：{task.result_summary[:200]}")
        if task.error:
            lines.append(f"最近错误：{task.error[:200]}")
        lines.append("补充：/补充 <短号> <内容>；取消：/取消 <短号>")
        return "\n".join(lines)

    # ---- 补充 / 取消 / 重试 ----------------------------------------------------------

    async def _append_input(self, principal, message: InboundMessage, rest: str) -> str:
        parts = rest.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            return "用法：/补充 <短号> <补充内容>"
        token, text = parts[0].strip(), parts[1].strip()
        try:
            task = self._resolve(principal, token)
            event_ref = message.external_event_id
            if event_ref.startswith("msg:"):
                event_ref = event_ref[4:]
            self.service.append_task_input(
                principal, task.task_id, text=text, source="wechat",
                external_event_id=event_ref,
            )
        except _AmbiguousTask as exc:
            return str(exc)
        except Exception as exc:  # noqa: BLE001
            return f"补充失败：{getattr(exc, 'message', None) or exc}"
        return f"✅ 已补充到任务 {short_id(task.task_id)}：{text[:80]}"

    async def _cancel(self, principal, token: str) -> str:
        if not token:
            return "用法：/取消 <短号>"
        try:
            task = self._resolve(principal, token)
            task = await self.service.cancel_task(principal, task.task_id)
        except _AmbiguousTask as exc:
            return str(exc)
        except Exception as exc:  # noqa: BLE001
            return f"取消失败：{getattr(exc, 'message', None) or exc}"
        return f"任务 {short_id(task.task_id)}：{_STATUS_TEXT.get(task.status, task.status)}"

    async def _retry(self, principal, token: str) -> str:
        if not token:
            return "用法：/重试 <短号>"
        try:
            task = self._resolve(principal, token)
            task = self.service.retry_task(principal, task.task_id)
        except _AmbiguousTask as exc:
            return str(exc)
        except Exception as exc:  # noqa: BLE001
            return f"重试失败：{getattr(exc, 'message', None) or exc}"
        return f"✅ 任务 {short_id(task.task_id)} 已重新入队"

    # ---- 解析 ------------------------------------------------------------------

    def _resolve(self, principal, token: str):
        """完整 ID 或末 6 位短号 → 任务；限定当前用户自己的任务。"""
        from backend.shared.identifiers import is_valid_id

        token = token.strip()
        if is_valid_id(token, prefix="sag"):
            return self.service.get_task(principal, token)
        tasks = self.service.list_tasks(principal, limit=50)
        matches = [t for t in tasks if t.task_id.endswith(token)]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise _AmbiguousTask(f"找不到任务 {token}；用 /任务 查看你的任务短号")
        lines = [f"短号 {token} 有多个匹配，请用完整任务号："]
        for task in matches:
            lines.append(f"· {task.task_id} {_STATUS_TEXT.get(task.status, task.status)} {task.title[:24]}")
        raise _AmbiguousTask("\n".join(lines))


class _AmbiguousTask(Exception):
    pass


def short_id(task_id: str) -> str:
    return task_id[-6:]
