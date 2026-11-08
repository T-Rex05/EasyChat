"""微信长轮询监听器：真实状态机、游标持久化、消息归一化后交给 ChannelService。

一个账号一个 asyncio task；running 只在成功轮询后成立，失败进入 backoff 并
记录最后错误。停止/重启不依赖进程内假标志。
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from backend.modules.channels.contracts import (
    ACCOUNT_ACTIVE,
    LISTENER_BACKOFF,
    LISTENER_ERROR,
    LISTENER_RUNNING,
    LISTENER_STARTING,
    LISTENER_STOPPED,
    ListenerState,
)
from backend.modules.channels.wechat.account import (
    CHANNEL_VERSION,
    EP_GET_UPDATES,
    IlinkTransport,
    TransportError,
    send_text,
)
from backend.modules.channels.wechat.parser import parse_inbound

logger = logging.getLogger(__name__)

DEFAULT_POLL_TIMEOUT = 60.0
DEFAULT_BACKOFF = (2.0, 5.0, 15.0, 30.0)
DEFAULT_POLL_INTERVAL = 0.05
THROTTLE_SLEEP_SECONDS = 600.0


class ListenerThrottled(RuntimeError):
    """iLink errcode=-14（风控/频率限制）：长时间退避，不是普通断线。"""


class WeChatListener:
    """按账号管理长轮询任务；service 提供账号凭证、游标与入站处理。"""

    def __init__(
        self,
        service: Any,
        transport: IlinkTransport,
        *,
        clock=time.time,
        poll_timeout: float = DEFAULT_POLL_TIMEOUT,
        backoff: tuple[float, ...] = DEFAULT_BACKOFF,
        throttle_sleep: float = THROTTLE_SLEEP_SECONDS,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> None:
        self.service = service
        self.transport = transport
        self.clock = clock
        self.poll_timeout = poll_timeout
        self.backoff = backoff or DEFAULT_BACKOFF
        self.throttle_sleep = throttle_sleep
        self.poll_interval = poll_interval
        self._tasks: dict[str, asyncio.Task] = {}
        self._states: dict[str, ListenerState] = {}

    # ---- 生命周期 ----------------------------------------------------------------

    def status(self, account_pk: str) -> ListenerState:
        state = self._states.get(account_pk)
        if state is None:
            return ListenerState(account_id=account_pk, status=LISTENER_STOPPED, since=self.clock())
        return state

    def statuses(self) -> list[ListenerState]:
        return list(self._states.values())

    async def start(self, account_pk: str) -> ListenerState:
        account, credentials = self.service.listener_account(account_pk)
        if account is None or account.status != ACCOUNT_ACTIVE or not credentials.get("token"):
            error = "账号不存在、已禁用或缺少凭证"
            self.service.record_poll(account_pk, error=error)  # 重启后仍可见
            return self._set_state(account_pk, LISTENER_ERROR, error=error)
        existing = self._tasks.get(account_pk)
        if existing is not None and not existing.done():
            return self._set_state(account_pk, LISTENER_RUNNING, error="")
        self._set_state(account_pk, LISTENER_STARTING)
        self._tasks[account_pk] = asyncio.ensure_future(self._run(account_pk))
        return self.status(account_pk)

    async def stop(self, account_pk: str) -> ListenerState:
        task = self._tasks.pop(account_pk, None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        return self._set_state(account_pk, LISTENER_STOPPED)

    async def stop_all(self) -> None:
        for account_pk in list(self._tasks):
            await self.stop(account_pk)
        self._tasks.clear()

    async def _run(self, account_pk: str) -> None:
        failures = 0
        try:
            while True:
                try:
                    await self.poll_once(account_pk)
                    failures = 0
                    if self.poll_interval > 0:
                        await asyncio.sleep(self.poll_interval)
                except asyncio.CancelledError:
                    raise
                except ListenerThrottled as exc:
                    self._set_state(account_pk, LISTENER_BACKOFF, error=str(exc), polls=self._polls(account_pk))
                    await asyncio.sleep(self.throttle_sleep)
                except StreamLookupError as exc:
                    self.service.record_poll(account_pk, error=str(exc))
                    self._set_state(account_pk, LISTENER_ERROR, error=str(exc), polls=self._polls(account_pk))
                    return
                except Exception as exc:  # noqa: BLE001  单次失败不终止监听
                    failures += 1
                    message = str(exc) or exc.__class__.__name__
                    self.service.record_poll(account_pk, error=message)
                    self._set_state(account_pk, LISTENER_BACKOFF, error=message, polls=self._polls(account_pk))
                    delay = self.backoff[min(failures - 1, len(self.backoff) - 1)]
                    await asyncio.sleep(delay)
        finally:
            current = self._states.get(account_pk)
            # 明确错误（缺凭证/账号禁用）保留 error 状态，供 UI/运维看见；
            # 正常取消或异常退出才落 stopped。
            if current is None or current.status != LISTENER_ERROR:
                self._states[account_pk] = ListenerState(
                    account_id=account_pk,
                    status=LISTENER_STOPPED,
                    since=self.clock(),
                    last_error=current.last_error if current else "",
                    polls=current.polls if current else 0,
                    last_poll_at=current.last_poll_at if current else None,
                )

    async def poll_once(self, account_pk: str) -> int:
        """执行一次 getupdates；返回本次处理的入站消息数（测试直接调用）。"""
        account, credentials = self.service.listener_account(account_pk)
        if account is None:
            raise StreamLookupError(f"渠道账号不存在: {account_pk}")
        if account.status != ACCOUNT_ACTIVE:
            raise StreamLookupError(f"渠道账号已禁用: {account_pk}")
        token = str(credentials.get("token") or "")
        if not token:
            raise StreamLookupError("渠道账号缺少 token")
        base_url = (account.base_url or credentials.get("base_url") or "").rstrip("/")
        if not base_url:
            raise StreamLookupError("渠道账号缺少 base_url")

        data = await self.transport.post_json(
            f"{base_url}{EP_GET_UPDATES}",
            {
                "get_updates_buf": account.sync_cursor,
                "base_info": {"channel_version": CHANNEL_VERSION},
            },
            token=token,
            timeout=self.poll_timeout,
        )
        ret = data.get("ret", 0)
        errcode = data.get("errcode", 0)
        if errcode == -14:
            raise ListenerThrottled("iLink 风控/频率限制（errcode=-14），暂停轮询")
        if ret not in (0, None) or errcode not in (0, None):
            raise TransportError(
                f"getupdates 失败 ret={ret} errcode={errcode}",
                ret=int(ret) if isinstance(ret, int) else None,
            )

        cursor = str(data.get("get_updates_buf") or "")
        processed = 0
        for raw in data.get("msgs") or []:
            if not isinstance(raw, dict):
                continue
            message = parse_inbound(
                account, raw, now=self.clock(),
                fingerprint_window=float(getattr(self.service, "fingerprint_window", 5.0)),
            )
            if message is None:
                continue
            outcome = await self.service.handle_inbound(message)
            processed += 1
            if outcome.reply_text:
                await send_text(
                    self.transport,
                    base_url=base_url,
                    token=token,
                    to_user_id=message.external_user_id,
                    text=outcome.reply_text,
                    context_token=message.context_token,
                )
        # 本地重放：处理失败的事件在退避后由本地重试（envelope 已持久化，
        # 游标推进安全，不依赖上游重投）。尽力而为，不阻塞本轮游标。
        try:
            await self.service.replay_due_events(limit=3)
        except Exception:  # noqa: BLE001
            logger.exception("本地事件重放失败 account=%s", account_pk)
        # 先处理再推进游标：崩溃后最多重复投递，由 channel_events 唯一键去重 +
        # 持久 inbox 本地重放兜底，不会出现“游标已过、消息未处理”的静默丢失。
        if cursor and cursor != account.sync_cursor:
            self.service.record_poll(account_pk, cursor=cursor)
        self.service.record_poll(account_pk, error="")
        state = self._states.get(account_pk)
        self._states[account_pk] = ListenerState(
            account_id=account_pk,
            status=LISTENER_RUNNING,
            since=state.since if state else self.clock(),
            last_error="",
            polls=self._polls(account_pk) + 1,
            last_poll_at=self.clock(),
        )
        return processed

    # ---- 内部 ------------------------------------------------------------------

    def _polls(self, account_pk: str) -> int:
        state = self._states.get(account_pk)
        return state.polls if state else 0

    def _set_state(self, account_pk: str, status: str, *, error: str = "", polls: int | None = None) -> ListenerState:
        previous = self._states.get(account_pk)
        state = ListenerState(
            account_id=account_pk,
            status=status,
            since=self.clock(),
            last_error=error,
            polls=polls if polls is not None else (previous.polls if previous else 0),
            last_poll_at=previous.last_poll_at if previous else None,
        )
        self._states[account_pk] = state
        return state


class StreamLookupError(RuntimeError):
    """账号/凭证不可用，监听无法继续。"""
