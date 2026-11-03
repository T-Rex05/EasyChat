"""报告生成与投递（Task 14）：先落不可变 artifact，再入投递账本。

渲染失败不建 artifact；邮件失败只重试同一文件，不重新渲染/重跑 Agent。
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from backend.integrations.pdf import PdfRenderer
from backend.modules.delivery.api import DeliveryService
from backend.modules.delivery.contracts import DeliveryTarget
from backend.shared.errors import InvalidInputError


class ReportService:
    def __init__(
        self, *, delivery: DeliveryService, renderer: PdfRenderer, artifacts_dir: Path
    ) -> None:
        self.delivery = delivery
        self.renderer = renderer
        self.artifacts_dir = Path(artifacts_dir)

    async def create_pdf_artifact(
        self, *, owner_id: int, html: str, title: str, timeout: float = 60.0
    ) -> str:
        if not html.strip():
            raise InvalidInputError("报告内容为空")
        destination = self.artifacts_dir / "reports" / f"{uuid.uuid4().hex}.pdf"
        await self.renderer.render(html, destination, timeout=timeout)
        payload = destination.read_bytes()
        artifact_id = self.delivery.repo.create_artifact(
            owner_id=owner_id, kind="report", file_path=str(destination),
            sha256=hashlib.sha256(payload).hexdigest(), file_size=len(payload),
            mime="application/pdf",
        )
        return artifact_id

    def enqueue_email_report(
        self,
        *,
        owner_id: int,
        target: DeliveryTarget,
        artifact_id: str,
        subject: str,
        body: str = "见附件。",
    ) -> str:
        return self.delivery.enqueue_text(
            owner_id=owner_id, target=target, text=body,
            dedup_key=f"report:{artifact_id}:{target.kind}:{target.ref}",
            source="report", artifact_id=artifact_id, subject=subject,
        )
