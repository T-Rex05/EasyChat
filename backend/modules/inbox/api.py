"""收件箱服务：owner 隔离、同 URL 去重更新、链接富化入队。"""
from __future__ import annotations

import sqlite3
from typing import Any
from urllib.parse import urlsplit

from backend.modules.inbox.contracts import (
    ENRICH_FAILED,
    ENRICH_PENDING,
    ENRICH_READY,
    ENRICH_SKIPPED,
    INBOX_ARCHIVED,
    INBOX_READ,
    INBOX_UNREAD,
    KIND_FILE,
    KIND_LINK,
    InboxItem,
)
from backend.modules.inbox.repository import InboxRepository
from backend.shared.context import Principal
from backend.shared.errors import InvalidInputError, NotFoundError
from backend.shared.identifiers import new_inbox_id

ENRICH_DAILY_LIMIT = 20


class InboxService:
    def __init__(
        self, db, *, access: Any, queue: Any = None, files: Any = None,
        clock=__import__("time").time, timezone_name: str = "Asia/Shanghai",
    ) -> None:
        self.db = db
        self.access = access
        self.queue = queue
        self.files = files
        self.clock = clock
        self.timezone_name = timezone_name
        self.repo = InboxRepository(db)

    def save(
        self,
        actor: Principal,
        *,
        url: str = "",
        file_id: str = "",
        note: str = "",
        title: str = "",
        tags: list[str] | tuple[str, ...] = (),
        source_run_id: str = "",
        source: str = "wechat",
    ) -> InboxItem:
        principal = self.access.validate_principal(actor)
        self.access.require_permission(principal, "chat.use")
        url = url.strip()
        file_id = file_id.strip()
        if not url and not file_id and not note.strip():
            raise InvalidInputError("链接、附件和备注至少需要一个")
        if url:
            try:
                parts = urlsplit(url)
                host = parts.hostname
            except ValueError as exc:
                raise InvalidInputError("链接格式不合法") from exc
            if parts.scheme not in ("http", "https") or not host:
                raise InvalidInputError("只支持 http/https 链接")
            if parts.username or parts.password:
                raise InvalidInputError("链接不能包含账号密码")
            url = url[:2000]
            kind = KIND_LINK
        else:
            kind = KIND_FILE
        file_name = ""
        if file_id:
            if self.files is None:
                raise InvalidInputError("文件服务未启用")
            record = self.files.get(principal, file_id)
            file_name = record.original_name
        tags = tuple(dict.fromkeys(t.strip()[:24] for t in tags if t.strip()))[:12]
        if url:
            existing = self.repo.get_by_url(principal.user_id, url)
            if existing is not None:
                merged_note = note.strip() or existing.note
                merged_title = title.strip() or existing.title
                merged_tags = tuple(dict.fromkeys((*existing.tags, *tags)))[:12]
                item = self.repo.update(
                    principal.user_id, existing.item_id,
                    title=merged_title[:200], note=merged_note[:2000],
                    tags_json=self._tags_json(merged_tags),
                )
                self._enqueue_enrich(item)
                return self.repo.get(principal.user_id, item.item_id) or item
        guessed_title = (
            title.strip() or file_name
            or (urlsplit(url).hostname if url else "")
            or note.strip()[:60]
        )
        try:
            item = self.repo.insert(
                principal.user_id,
                item_id=new_inbox_id(),
                kind=kind,
                title=guessed_title,
                url=url,
                file_id=file_id,
                note=note.strip(),
                tags=tags,
                status=INBOX_UNREAD,
                enrich_state=ENRICH_PENDING if url else ENRICH_READY,
                source_run_id=source_run_id,
            )
        except sqlite3.IntegrityError:
            # 并发保存同一 URL：唯一索引兜底，合并到已有条目而不是 500。
            existing = self.repo.get_by_url(principal.user_id, url) if url else None
            if existing is None:
                raise
            item = self.repo.update(
                principal.user_id, existing.item_id,
                title=title.strip() or existing.title,
                note=note.strip() or existing.note,
                tags_json=self._tags_json(
                    tuple(dict.fromkeys((*existing.tags, *tags)))[:12]
                ),
            )
        if url:
            self._enqueue_enrich(item)
            item = self.repo.get(principal.user_id, item.item_id) or item
        return item

    def _enqueue_enrich(self, item: InboxItem) -> None:
        if not item.url:
            return
        if urlsplit(item.url).scheme.lower() != "https":
            # http 仍可保存，但不抓取正文，避免把收件箱当明文爬虫入口。
            self.repo.update(
                item.owner_id, item.item_id, enrich_state=ENRICH_SKIPPED
            )
            return
        if self.queue is None:
            return
        from datetime import datetime
        from zoneinfo import ZoneInfo

        local_date = datetime.fromtimestamp(
            self.clock(), ZoneInfo(self.timezone_name)
        ).date().isoformat()
        used = self.queue.count_for_owner(
            kind="inbox.enrich", owner_id=item.owner_id,
            payload_field="date", payload_value=local_date,
        )
        if used >= ENRICH_DAILY_LIMIT:
            # 只保存不抓取；仍可在下一天由新的保存/更新重新入队。
            self.repo.update(
                item.owner_id, item.item_id, enrich_state=ENRICH_SKIPPED
            )
            return
        revision = item.updated_at.replace(":", "").replace(".", "").replace("+", "")
        self.queue.enqueue(
            kind="inbox.enrich",
            dedup_key=f"inbox:{item.item_id}:{revision}",
            payload={
                "item_id": item.item_id, "owner_id": item.owner_id,
                "date": local_date,
            },
            owner_id=item.owner_id,
        )

    def list(self, actor: Principal, *, status: str = "", limit: int = 20) -> list[InboxItem]:
        principal = self.access.validate_principal(actor)
        self.access.require_permission(principal, "chat.use")
        return self.repo.list(principal.user_id, status=status, limit=limit)

    def search(self, actor: Principal, query: str, limit: int = 5) -> list[InboxItem]:
        principal = self.access.validate_principal(actor)
        self.access.require_permission(principal, "chat.use")
        query = query.strip()
        if not query:
            raise InvalidInputError("搜索词不能为空")
        return self.repo.search(principal.user_id, query, limit=limit)

    def archive(self, actor: Principal, item_id: str) -> InboxItem:
        principal = self.access.validate_principal(actor)
        self._owned(principal, item_id)
        return self.repo.update(principal.user_id, item_id, status=INBOX_ARCHIVED)

    def mark_read(self, actor: Principal, item_id: str) -> InboxItem:
        principal = self.access.validate_principal(actor)
        self._owned(principal, item_id)
        return self.repo.update(principal.user_id, item_id, status=INBOX_READ)

    def delete(self, actor: Principal, item_id: str) -> None:
        principal = self.access.validate_principal(actor)
        self._owned(principal, item_id)
        if not self.repo.delete(principal.user_id, item_id):
            raise NotFoundError("收件箱条目不存在")

    def unread_count(self, owner_id: int) -> int:
        return self.repo.unread_count(int(owner_id))

    def enrich(self, item_id: str, fetcher: Any) -> InboxItem:
        """worker 调用：无 Principal，按条目 owner 更新；不改变可见性。"""
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT owner_id,url,title FROM inbox_items WHERE id=?", (item_id,)
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            raise KeyError(item_id)
        owner_id, url, current_title = int(row["owner_id"]), str(row["url"]), str(row["title"] or "")
        if not url:
            return self.repo.update(owner_id, item_id, enrich_state=ENRICH_READY)
        if urlsplit(url).scheme.lower() != "https":
            return self.repo.update(owner_id, item_id, enrich_state=ENRICH_SKIPPED)
        try:
            title, summary = fetcher(url)
        except Exception:  # noqa: BLE001  富化失败保留条目
            return self.repo.update(owner_id, item_id, enrich_state=ENRICH_FAILED)
        # 网页没有标题/摘要时保留用户自己填写的标题，绝不清空。
        updates: dict[str, Any] = {"enrich_state": ENRICH_READY}
        if not current_title.strip() and title.strip():
            updates["title"] = title.strip()[:200]
        if summary.strip():
            updates["summary"] = summary.strip()[:1000]
        return self.repo.update(owner_id, item_id, **updates)

    def _owned(self, principal: Principal, item_id: str) -> InboxItem:
        item = self.repo.get(principal.user_id, item_id)
        if item is None:
            raise NotFoundError("收件箱条目不存在")
        return item

    @staticmethod
    def _tags_json(tags: tuple[str, ...]) -> str:
        import json

        return json.dumps(list(tags), ensure_ascii=False)
