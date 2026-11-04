"""files 模块公开契约。

FileRecord 是给调用者/前端看的元数据：**不含绝对路径、不含解密凭证**。
原始文件名只是展示元数据；路径由 `storage_key`（相对）唯一决定，外部不能指定。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

# ---- 文件完整性状态（与分析状态分开） ------------------------------------------
FILE_RECEIVING = "receiving"
FILE_FINALIZING = "finalizing"
FILE_READY = "ready"
FILE_FAILED = "failed"
FILE_MISSING = "missing"  # 元数据在、物理文件缺失（backfill/reconcile 发现）
FILE_DELETED = "deleted"

FILE_STATUSES: frozenset[str] = frozenset(
    {FILE_RECEIVING, FILE_FINALIZING, FILE_READY, FILE_FAILED, FILE_MISSING, FILE_DELETED}
)

# ---- 文件种类 ------------------------------------------------------------------
KIND_IMAGE = "image"
KIND_SPREADSHEET = "spreadsheet"
KIND_DOCUMENT = "document"
KIND_REPORT = "report"
KIND_DERIVED = "derived"
KIND_OTHER = "other"

FILE_KINDS: frozenset[str] = frozenset(
    {KIND_IMAGE, KIND_SPREADSHEET, KIND_DOCUMENT, KIND_REPORT, KIND_DERIVED, KIND_OTHER}
)

# ---- 引用类型 ------------------------------------------------------------------
REF_SESSION = "session"
REF_ATTACHMENT = "attachment"
REF_IMPORT = "import"
REF_REPORT = "report"
REF_DELIVERY = "delivery"
REF_ANALYSIS = "analysis"
REF_RUN = "run"

FILE_REF_KINDS: frozenset[str] = frozenset(
    {REF_SESSION, REF_ATTACHMENT, REF_IMPORT, REF_REPORT, REF_DELIVERY, REF_ANALYSIS, REF_RUN}
)

# ---- 提取状态 ------------------------------------------------------------------
EXTRACTION_PENDING = "pending"
EXTRACTION_RUNNING = "running"
EXTRACTION_SUCCEEDED = "succeeded"
EXTRACTION_FAILED = "failed"
EXTRACTION_SKIPPED = "skipped"

# ---- 保留策略 ------------------------------------------------------------------
RETENTION_PERMANENT = "permanent"  # 合法原始上传默认长期保留
RETENTION_DERIVED = "derived_7d"
RETENTION_REPORT = "report_default"

# 初始可配置上限（设计 §6），不是已测量结论
DEFAULT_MAX_FILE_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_ATTACHMENTS = 10
DEFAULT_MAX_XLSX_UNCOMPRESSED = 200 * 1024 * 1024
DEFAULT_MAX_XLSX_ENTRIES = 2000
DEFAULT_MAX_IMAGE_PIXELS = 20_000_000
DEFAULT_MAX_TABLE_ROWS = 100_000


@dataclass(frozen=True, slots=True)
class SaveMetadata:
    """保存请求的元数据。owner/storage_key 由可信 Principal 与服务端决定。"""

    original_name: str = ""
    declared_mime: str = ""
    kind: str = ""
    source: str = "web"
    retention_policy: str = RETENTION_PERMANENT
    # 幂等作用域：Web 用 request_id，微信媒体用 (channel, account_id, event, media_index)
    channel: str = ""
    account_id: str = ""
    external_event_id: str = ""
    media_index: int = -1
    session_id: str = ""
    max_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class FileRecord:
    """对外可见的文件元数据（无绝对路径）。"""

    file_id: str
    owner_id: int
    original_name: str
    verified_mime: str
    size_bytes: int
    sha256: str
    status: str
    kind: str
    source: str
    retention_policy: str
    created_at: str
    deleted_at: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class UploadResult:
    """一次保存的结果；duplicate=True 表示命中收据/同内容，未产生新文件。"""

    file: FileRecord
    receipt_id: str
    duplicate: bool = False
    reused_content: bool = False


@dataclass(frozen=True, slots=True)
class DeleteImpact:
    """删除前的影响范围（必须先展示，不能静默级联删账）。"""

    file_id: str
    reference_counts: Mapping[str, int] = field(default_factory=dict)
    scope: str = ""
    allowed: bool = True
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ReconcileReport:
    recovered: int = 0
    marked_missing: int = 0
    marked_failed: int = 0
    orphans: tuple[str, ...] = ()
    checked_receipts: int = 0
    details: tuple[str, ...] = ()


# 删除作用域：只撤销引用 / 删原件保留账目 / 删原件及独占导入数据
DELETE_SCOPE_UNLINK = "unlink"
DELETE_SCOPE_FILE_ONLY = "file_only"
DELETE_SCOPE_FILE_AND_DATA = "file_and_data"
DELETE_SCOPES: frozenset[str] = frozenset(
    {DELETE_SCOPE_UNLINK, DELETE_SCOPE_FILE_ONLY, DELETE_SCOPE_FILE_AND_DATA}
)
