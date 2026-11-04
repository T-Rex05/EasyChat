"""账本模块公开入口（业务只允许从这里取 LedgerService）。"""
from __future__ import annotations

from backend.modules.ledger.api import LedgerService

__all__ = ["LedgerService"]
