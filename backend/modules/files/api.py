"""files 模块唯一公开入口：保存 / 读取 / 引用 / 删除影响 / 对账 / 提取记录。

所有写操作的所有者由可信 Principal 决定；外部 metadata 不能指定 owner 或
storage_key。返回 FileRecord 不含绝对路径。

文件系统与 app.db 没有共享事务：保存顺序为
  收据(receiving) → staging 分块写+hash → 校验 → 原子移动 → 短事务提交 ready
任何一步失败都不返回“已保存”，中断由 `reconcile` 对账。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterable, BinaryIO, Iterable

from backend.modules.files.contracts import (
    DEFAULT_MAX_IMAGE_PIXELS,
    DEFAULT_MAX_XLSX_ENTRIES,
    DEFAULT_MAX_XLSX_UNCOMPRESSED,
    DELETE_SCOPE_FILE_AND_DATA,
    DELETE_SCOPE_FILE_ONLY,
    DELETE_SCOPE_UNLINK,
    DELETE_SCOPES,
    FILE_FAILED,
    FILE_FINALIZING,
    FILE_MISSING,
    FILE_READY,
    FILE_RECEIVING,
    FILE_REF_KINDS,
    KIND_DERIVED,
    KIND_REPORT,
    RETENTION_DERIVED,
    RETENTION_PERMANENT,
    REF_ATTACHMENT,
    REF_SESSION,
    DeleteImpact,
    FileRecord,
    ReconcileReport,
    SaveMetadata,
    UploadResult,
)
from backend.modules.files.local_store import (
    LocalFileStore,
    detect_content_mime,
    file_record_from_row,
    kind_for,
    verified_extension,
)
from backend.modules.files.validation import inspect_zip, validate_image_size
from backend.platform.sqlite import Database
from backend.shared.context import Principal
from backend.shared.errors import (
    AppError,
    ForbiddenError,
    InvalidInputError,
    NotFoundError,
    StorageUnavailableError,
)
from backend.shared.identifiers import new_file_id

logger = logging.getLogger(__name__)

MAX_ORIGINAL_NAME = 255
_PROBE_BYTES = 4096


class FileService:
    def __init__(
        self,
        db: Database,
        *,
        access: Any,
        store: LocalFileStore,
        clock=None,
        min_free_bytes: int = 0,
        delete_hook=None,
        max_image_pixels: int = DEFAULT_MAX_IMAGE_PIXELS,
        max_xlsx_entries: int = DEFAULT_MAX_XLSX_ENTRIES,
        max_xlsx_uncompressed: int = DEFAULT_MAX_XLSX_UNCOMPRESSED,
    ) -> None:
        from backend.modules.files.repository import FileRepository

        self.db = db
        self.repo = FileRepository(db)
        self.access = access
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.min_free_bytes = int(min_free_bytes)
        self.max_image_pixels = int(max_image_pixels)
        self.max_xlsx_entries = int(max_xlsx_entries)
        self.max_xlsx_uncompressed = int(max_xlsx_uncompressed)
        # 删除原件及其独占导入数据时，由 bootstrap 注入的协调函数清理账本侧数据
        self.delete_hook = delete_hook

    # ---- 授权 ------------------------------------------------------------------

    def _require(self, principal: Principal, permission: str) -> Principal:
        principal = self.access.validate_principal(principal)
        self.access.require_permission(principal, permission)
        return principal

    def _authorize(self, principal: Principal, owner_id: int) -> None:
        if not self.access.can_access_resource(principal, owner_id, "system.manage"):
            raise NotFoundError("文件不存在")

    # ---- 保存 ------------------------------------------------------------------

    async def save_stream(
        self,
        principal: Principal,
        chunks: AsyncIterable[bytes] | Iterable[bytes],
        metadata: SaveMetadata | None = None,
        request_id: str = "",
    ) -> UploadResult:
        return await self._save(
            principal, chunks, metadata or SaveMetadata(), request_id=request_id, prefix="uploads",
        )

    async def save_bytes(
        self,
        principal: Principal,
        payload: bytes,
        metadata: SaveMetadata | None = None,
        request_id: str = "",
    ) -> UploadResult:
        if not isinstance(payload, (bytes, bytearray)):
            raise InvalidInputError("save_bytes 只接受 bytes")
        return await self.save_stream(principal, [bytes(payload)], metadata, request_id)

    async def save_derived(
        self,
        principal: Principal,
        chunks: AsyncIterable[bytes] | Iterable[bytes],
        *,
        original_name: str,
        declared_mime: str = "",
        source: str = "derived",
        kind: str = "",
    ) -> UploadResult:
        metadata = SaveMetadata(
            original_name=original_name,
            declared_mime=declared_mime,
            kind=kind or KIND_DERIVED,
            source=source,
            retention_policy=RETENTION_DERIVED,
        )
        return await self._save(principal, chunks, metadata, request_id="", prefix="derived")

    async def save_report(
        self,
        principal: Principal,
        chunks: AsyncIterable[bytes] | Iterable[bytes],
        *,
        original_name: str,
        declared_mime: str = "application/pdf",
        request_id: str = "",
    ) -> UploadResult:
        metadata = SaveMetadata(
            original_name=original_name,
            declared_mime=declared_mime,
            kind=KIND_REPORT,
            source="report",
        )
        return await self._save(principal, chunks, metadata, request_id=request_id, prefix="reports")

    async def ingest_local_path(
        self,
        principal: Principal,
        source_path: Path,
        metadata: SaveMetadata | None = None,
        request_id: str = "",
        *,
        remove_source: bool = False,
    ) -> UploadResult:
        """接收已在本地暂存的文件（渠道下载/解密产物），流式复制进受管目录。"""
        source_path = Path(source_path)
        if not source_path.is_file():
            raise InvalidInputError("待保存文件不存在")

        def _chunks():
            with source_path.open("rb") as handle:
                while True:
                    block = handle.read(1024 * 1024)
                    if not block:
                        break
                    yield block

        result = await self._save(
            principal, _chunks(), metadata or SaveMetadata(), request_id=request_id, prefix="uploads",
        )
        if remove_source:
            try:
                source_path.unlink()
            except OSError:
                logger.warning("渠道暂存文件清理失败: %s", source_path)
        return result

    async def _save(
        self,
        principal: Principal,
        chunks: AsyncIterable[bytes] | Iterable[bytes],
        metadata: SaveMetadata,
        *,
        request_id: str,
        prefix: str,
    ) -> UploadResult:
        principal = self._require(principal, "file.upload")
        owner_id = principal.user_id
        original_name = _safe_display_name(metadata.original_name)
        limit = int(metadata.max_bytes or self.store.max_bytes)

        # 1. 幂等收据（Web request_id / 微信账号+事件+媒体序号）
        existing = self.repo.find_receipt(
            owner_id=owner_id,
            request_id=request_id,
            channel=metadata.channel,
            account_id=metadata.account_id,
            external_event_id=metadata.external_event_id,
            media_index=metadata.media_index,
        )
        if existing is not None:
            file_id = str(existing.get("file_id") or "")
            if existing.get("state") == FILE_READY and file_id:
                record = self.get(principal, file_id)
                return UploadResult(file=record, receipt_id=str(existing["id"]), duplicate=True)
            receipt_id = str(existing["id"])
            receipt_created = False
        else:
            receipt_id, receipt_created = self.repo.create_receipt(
                owner_id=owner_id,
                request_id=request_id,
                channel=metadata.channel,
                account_id=metadata.account_id,
                external_event_id=metadata.external_event_id,
                media_index=metadata.media_index,
                original_name=original_name,
            )
            existing = self.repo.get_receipt(receipt_id)

        if not receipt_created and existing is not None and existing.get("state") == FILE_READY:
            file_id = str(existing.get("file_id") or "")
            if file_id:
                return UploadResult(
                    file=self.get(principal, file_id), receipt_id=receipt_id, duplicate=True,
                )

        # 2. 磁盘低水位：明确拒绝，不删除旧原件腾空间
        if self.min_free_bytes and self.store.disk_free_bytes() < self.min_free_bytes:
            self.repo.update_receipt(receipt_id, state=FILE_FAILED, error="磁盘可用空间不足")
            raise InvalidInputError("磁盘可用空间不足，已拒绝本次保存")

        staging = self.store.staging_path(receipt_id)
        self.repo.update_receipt(receipt_id, state=FILE_RECEIVING, error=None, original_name=original_name)
        try:
            size, digest, head = await self.store.write_chunks(
                chunks, staging_path=staging, max_bytes=limit,
            )
        except BaseException as exc:  # 含外部流中断/取消：都不返回“已保存”
            self.repo.update_receipt(receipt_id, state=FILE_FAILED, error=str(exc)[:500])
            raise
        if size == 0:
            staging.unlink(missing_ok=True)
            self.repo.update_receipt(receipt_id, state=FILE_FAILED, error="空文件")
            raise InvalidInputError("空文件不能保存")

        verified_mime = detect_content_mime(head, original_name or metadata.declared_mime)
        extension = verified_extension(verified_mime, original_name)
        kind = kind_for(verified_mime, extension, declared=metadata.kind)
        # 内容上限：图片像素、压缩容器展开量（拒绝时不返回“已保存”）
        try:
            if verified_mime.startswith("image/"):
                validate_image_size(head, max_pixels=self.max_image_pixels)
            if verified_mime in (
                "application/zip",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ):
                inspect_zip(
                    staging,
                    max_entries=self.max_xlsx_entries,
                    max_uncompressed=self.max_xlsx_uncompressed,
                )
        except InvalidInputError as exc:
            staging.unlink(missing_ok=True)
            self.repo.update_receipt(receipt_id, state=FILE_FAILED, error=str(exc)[:500])
            raise
        retention = (
            metadata.retention_policy
            if metadata.retention_policy and not metadata.retention_policy.startswith("derived")
            else RETENTION_PERMANENT if prefix == "uploads" else RETENTION_DERIVED
        )

        # 3. 同 owner 同内容复用（收据/展示名仍独立）
        reused = self.repo.find_by_hash(owner_id, digest)
        if reused is not None:
            staging.unlink(missing_ok=True)
            self.repo.commit_ready(
                file_id=str(reused["id"]),
                receipt_id=receipt_id,
                ref_kind=REF_SESSION if metadata.session_id else "",
                ref_id=metadata.session_id,
            )
            return UploadResult(
                file=file_record_from_row(reused), receipt_id=receipt_id,
                reused_content=True,
            )

        # 4. 先登记 finalizing 元数据（含预期 key/hash），再原子移动
        file_id = new_file_id()
        storage_key = self.store.build_key(
            owner_id=owner_id, file_id=file_id, extension=extension,
            now=self.clock(), prefix=prefix,
        )
        self.repo.create_file(
            file_id=file_id,
            owner_id=owner_id,
            storage_key=storage_key,
            original_name=original_name,
            declared_mime=str(metadata.declared_mime or "")[:200],
            verified_mime=verified_mime,
            size_bytes=size,
            sha256=digest,
            kind=kind,
            status=FILE_FINALIZING,
            source=metadata.source[:40],
            retention_policy=retention,
        )
        self.repo.update_receipt(
            receipt_id, state=FILE_FINALIZING, expected_key=storage_key,
            expected_sha256=digest, expected_size=size,
        )
        try:
            self.store.finalize(staging, storage_key)
        except Exception as exc:
            self.repo.mark_failed(file_id=file_id, receipt_id=receipt_id, error=str(exc))
            raise

        # 移动后复核 hash：不一致说明落盘过程被破坏，不得提交 ready
        actual = self.store.sha256_of(storage_key)
        if actual != digest:
            self.store.delete(storage_key)
            self.repo.mark_failed(
                file_id=file_id, receipt_id=receipt_id, error="落盘后 hash 校验不一致",
            )
            raise StorageUnavailableError("文件落盘校验失败（hash 不一致）")

        # 5. 短事务提交 ready + 收据 + 引用
        self.repo.commit_ready(
            file_id=file_id,
            receipt_id=receipt_id,
            ref_kind=REF_SESSION if metadata.session_id else "",
            ref_id=metadata.session_id,
        )
        row = self.repo.get_file(file_id)
        assert row is not None
        return UploadResult(file=file_record_from_row(row), receipt_id=receipt_id)

    # ---- 读取 ------------------------------------------------------------------

    def get(self, principal: Principal, file_id: str) -> FileRecord:
        principal = self._require(principal, "file.read")
        row = self.repo.get_file(file_id)
        if row is None:
            raise NotFoundError("文件不存在")
        self._authorize(principal, int(row["owner_id"]))
        if row["status"] == "deleted":
            raise NotFoundError("文件已删除")
        return file_record_from_row(row)

    def list(
        self,
        principal: Principal,
        *,
        limit: int = 50,
        offset: int = 0,
        kind: str | None = None,
        all_owners: bool = False,
    ) -> list[FileRecord]:
        principal = self._require(principal, "file.read")
        owner_id: int | None = principal.user_id
        if all_owners:
            if not self.access.has_permission(principal, "system.manage"):
                raise ForbiddenError("缺少跨用户查看权限")
            owner_id = None
        rows = self.repo.list_files(
            owner_id=owner_id, limit=min(max(1, limit), 200), offset=max(0, offset), kind=kind,
        )
        return [file_record_from_row(r) for r in rows]

    def open_read(self, principal: Principal, file_id: str) -> BinaryIO:
        """受控读取句柄：只允许 ready 文件；不向调用者暴露物理路径。"""
        record = self.get(principal, file_id)
        if record.status == FILE_MISSING:
            raise NotFoundError("文件内容缺失（元数据存在但物理文件不可读）")
        if record.status != FILE_READY:
            raise InvalidInputError(f"文件不可读（状态 {record.status}）")
        row = self.repo.get_file(file_id)
        assert row is not None
        return self.store.open_read(str(row["storage_key"]))

    def read_sample(self, principal: Principal, file_id: str, limit: int = _PROBE_BYTES) -> bytes:
        with self.open_read(principal, file_id) as handle:
            return handle.read(max(1, min(limit, 64 * 1024)))

    # ---- 引用 ------------------------------------------------------------------

    def link(self, principal: Principal, file_id: str, ref_kind: str, ref_id: str) -> bool:
        principal = self._require(principal, "file.read")
        if ref_kind not in FILE_REF_KINDS:
            raise InvalidInputError(f"未知引用类型: {ref_kind}")
        if not ref_id:
            raise InvalidInputError("引用 ID 不能为空")
        row = self.repo.get_file(file_id)
        if row is None:
            raise NotFoundError("文件不存在")
        self._authorize(principal, int(row["owner_id"]))
        return self.repo.add_reference(
            file_id=file_id, owner_id=int(row["owner_id"]), ref_kind=ref_kind, ref_id=ref_id,
        )

    def unlink(self, principal: Principal, file_id: str, ref_kind: str, ref_id: str) -> bool:
        principal = self._require(principal, "file.delete")
        row = self.repo.get_file(file_id)
        if row is None:
            raise NotFoundError("文件不存在")
        self._authorize(principal, int(row["owner_id"]))
        return self.repo.remove_reference(file_id=file_id, ref_kind=ref_kind, ref_id=ref_id)

    def reference_counts(self, principal: Principal, file_id: str) -> dict[str, int]:
        principal = self._require(principal, "file.read")
        row = self.repo.get_file(file_id)
        if row is None:
            raise NotFoundError("文件不存在")
        self._authorize(principal, int(row["owner_id"]))
        return self.repo.reference_counts(file_id)

    def files_for_target(self, principal: Principal, ref_kind: str, ref_id: str) -> list[str]:
        """按业务引用取文件 ID（调用方仍需逐个鉴权读取）。"""
        self._require(principal, "file.read")
        return self.repo.files_for_target(ref_kind, ref_id)

    # ---- 删除影响 ----------------------------------------------------------------

    def delete_impact(self, principal: Principal, file_id: str) -> DeleteImpact:
        principal = self._require(principal, "file.delete")
        row = self.repo.get_file(file_id)
        if row is None:
            raise NotFoundError("文件不存在")
        self._authorize(principal, int(row["owner_id"]))
        counts = self.repo.reference_counts(file_id)
        return DeleteImpact(
            file_id=file_id,
            reference_counts=counts,
            scope="preview",
            allowed=row["status"] != "deleted",
            reason="" if row["status"] != "deleted" else "文件已删除",
        )

    def request_delete(
        self,
        principal: Principal,
        file_id: str,
        scope: str,
        *,
        ref_kind: str = "",
        ref_id: str = "",
    ) -> DeleteImpact:
        """三种删除范围；不静默级联删账，账本数据清理由注入的协调函数处理。

        scope=unlink 时给了 ref_kind/ref_id 只撤这一条引用；未指定则撤掉全部
        展示引用（attachment/session），原件与账本来源保留。
        """
        if scope not in DELETE_SCOPES:
            raise InvalidInputError(f"未知删除范围: {scope}")
        principal = self._require(principal, "file.delete")
        row = self.repo.get_file(file_id)
        if row is None:
            raise NotFoundError("文件不存在")
        self._authorize(principal, int(row["owner_id"]))
        counts = self.repo.reference_counts(file_id)

        if scope == DELETE_SCOPE_UNLINK:
            removed = 0
            if ref_kind and ref_id:
                if self.repo.remove_reference(file_id=file_id, ref_kind=ref_kind, ref_id=ref_id):
                    removed = 1
                return DeleteImpact(
                    file_id=file_id, reference_counts=counts, scope=scope,
                    allowed=True, reason=f"已移除 {removed} 个引用，原件保留",
                )
            for ref in self.repo.references(file_id):
                if str(ref["ref_kind"]) in (REF_ATTACHMENT, REF_SESSION):
                    if self.repo.remove_reference(
                        file_id=file_id, ref_kind=str(ref["ref_kind"]), ref_id=str(ref["ref_id"])
                    ):
                        removed += 1
            return DeleteImpact(
                file_id=file_id, reference_counts=counts, scope=scope,
                allowed=True, reason=f"已移除 {removed} 个展示引用，原件保留",
            )

        if scope == DELETE_SCOPE_FILE_AND_DATA and self.delete_hook is not None:
            self.delete_hook(principal, file_id)

        # 文件墓碑：先撤引用再删物理文件；失败由 lifecycle 任务重试
        for ref in self.repo.references(file_id):
            self.repo.remove_reference(
                file_id=file_id, ref_kind=str(ref["ref_kind"]), ref_id=str(ref["ref_id"])
            )
        storage_key = str(row["storage_key"])
        self.repo.mark_deleted(file_id)
        try:
            self.store.delete(storage_key)
        except Exception:  # noqa: BLE001  墓碑已写，物理删除由 lifecycle 重试
            logger.warning("原件物理删除失败，等待 lifecycle 重试 file_id=%s", file_id)
        return DeleteImpact(
            file_id=file_id, reference_counts=counts, scope=scope, allowed=True,
            reason="原件已删除（墓碑阻止异步任务重生）"
            if scope == DELETE_SCOPE_FILE_ONLY else "原件及引用已删除",
        )

    # ---- 提取记录（供 ledger 等模块写入） ------------------------------------------

    def record_extraction(
        self,
        principal: Principal,
        file_id: str,
        *,
        extractor: str,
        extractor_version: str,
        input_hash: str,
        state: str,
        derived_file_id: str | None = None,
        quality: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> str:
        principal = self._require(principal, "file.read")
        row = self.repo.get_file(file_id)
        if row is None:
            raise NotFoundError("文件不存在")
        self._authorize(principal, int(row["owner_id"]))
        import json

        return self.repo.upsert_extraction(
            file_id=file_id, owner_id=int(row["owner_id"]), extractor=extractor,
            extractor_version=extractor_version, input_hash=input_hash, state=state,
            derived_file_id=derived_file_id,
            quality_summary=json.dumps(quality or {}, ensure_ascii=False), error=error,
        )

    def latest_extraction(self, principal: Principal, file_id: str, extractor: str) -> dict[str, Any] | None:
        principal = self._require(principal, "file.read")
        row = self.repo.get_file(file_id)
        if row is None:
            raise NotFoundError("文件不存在")
        self._authorize(principal, int(row["owner_id"]))
        return self.repo.latest_extraction(file_id, extractor)

    # ---- 对账 ------------------------------------------------------------------

    def reconcile(self, *, limit: int = 50, grace_hours: int = 24) -> ReconcileReport:
        from backend.modules.files.reconcile import reconcile_files

        return reconcile_files(self, limit=limit, grace_hours=grace_hours)


def _safe_display_name(name: str) -> str:
    """展示名清洗：去掉目录成分、控制字符与换行（不参与路径定位）。"""
    raw = str(name or "").replace("\\", "/").split("/")[-1]
    cleaned = "".join(ch for ch in raw if ch.isprintable() and ch not in "\r\n\t")
    cleaned = cleaned.strip().lstrip(".")
    if not cleaned:
        cleaned = "未命名文件"
    return cleaned[:MAX_ORIGINAL_NAME]
