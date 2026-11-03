"""投递/提醒测试替身：FakeSender 脚本化返回 sent/retry/uncertain/failed。"""
from __future__ import annotations

from typing import Any

from backend.modules.delivery.contracts import DeliveryTarget, SendResult


class FakeSender:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.artifacts: list[dict[str, Any]] = []
        self.scripted: list[Any] = []
        self.deliverable = True
        self.can_deliver_calls = 0

    def script(self, *results: Any) -> None:
        self.scripted.extend(results)

    async def can_deliver(self, target: DeliveryTarget) -> bool:
        self.can_deliver_calls += 1
        return self.deliverable

    async def send_text(
        self, target: DeliveryTarget, text: str, *, context_token: str = ""
    ) -> SendResult:
        self.sent.append({
            "target": target, "text": text, "context_token": context_token,
        })
        if not self.scripted:
            return SendResult.sent(external_id=f"ext-{len(self.sent)}")
        item = self.scripted.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def send_artifact(
        self, target: DeliveryTarget, artifact_path: str, *, subject: str, body: str = ""
    ) -> SendResult:
        self.artifacts.append({
            "target": target, "path": artifact_path, "subject": subject, "body": body,
        })
        if not self.scripted:
            return SendResult.sent(external_id=f"art-{len(self.artifacts)}")
        item = self.scripted.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
