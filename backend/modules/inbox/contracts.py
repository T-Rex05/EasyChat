"""收件箱公开契约。"""
from __future__ import annotations

from dataclasses import dataclass

INBOX_UNREAD = "unread"
INBOX_READ = "read"
INBOX_ARCHIVED = "archived"
INBOX_STATUSES = (INBOX_UNREAD, INBOX_READ, INBOX_ARCHIVED)

ENRICH_PENDING = "pending"
ENRICH_READY = "ready"
ENRICH_FAILED = "failed"
ENRICH_SKIPPED = "skipped"

KIND_LINK = "link"
KIND_FILE = "file"
KIND_IMAGE = "image"
KIND_NOTE = "note"


@dataclass(frozen=True, slots=True)
class InboxItem:
    item_id: str
    owner_id: int
    kind: str
    title: str
    url: str
    file_id: str
    note: str
    summary: str
    tags: tuple[str, ...]
    status: str
    enrich_state: str
    source_run_id: str
    created_at: str
    updated_at: str

    def brief(self, width: int = 60) -> str:
        name = self.title or self.url or self.note or "未命名"
        return f"{name[:width]}（{self.item_id[:12]}，{self.status}）"
