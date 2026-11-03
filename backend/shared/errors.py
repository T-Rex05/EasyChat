"""跨模块错误码（架构 §11）。

小集合、有明确语义；HTTP 边界统一映射状态码。
业务模块抛 AppError 子类或直接构造 AppError，不允许把所有异常吞成 200 空结果。
"""
from enum import Enum
from typing import Any, Mapping


class ErrorCode(str, Enum):
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    INVALID_INPUT = "invalid_input"
    BUSY = "busy"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    DEPENDENCY_TIMEOUT = "dependency_timeout"
    STORAGE_UNAVAILABLE = "storage_unavailable"
    INTERRUPTED = "interrupted"


_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.INVALID_INPUT: 422,
    ErrorCode.BUSY: 429,
    ErrorCode.CAPABILITY_UNAVAILABLE: 503,
    ErrorCode.DEPENDENCY_TIMEOUT: 504,
    ErrorCode.STORAGE_UNAVAILABLE: 503,
    ErrorCode.INTERRUPTED: 500,
}


class AppError(Exception):
    """业务错误基类：携带稳定错误码与可选细节。"""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})

    @property
    def http_status(self) -> int:
        return _HTTP_STATUS[self.code]

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"error": self.code.value, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


class UnauthenticatedError(AppError):
    def __init__(self, message: str = "未认证或凭证已失效") -> None:
        super().__init__(ErrorCode.UNAUTHENTICATED, message)


class ForbiddenError(AppError):
    def __init__(self, message: str = "无权执行该操作") -> None:
        super().__init__(ErrorCode.FORBIDDEN, message)


class NotFoundError(AppError):
    def __init__(self, message: str = "资源不存在") -> None:
        super().__init__(ErrorCode.NOT_FOUND, message)


class ConflictError(AppError):
    def __init__(self, message: str = "状态冲突") -> None:
        super().__init__(ErrorCode.CONFLICT, message)


class InvalidInputError(AppError):
    def __init__(self, message: str = "输入不合法", *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(ErrorCode.INVALID_INPUT, message, details=details)


class BusyError(AppError):
    def __init__(self, message: str = "忙：已有正在执行的任务") -> None:
        super().__init__(ErrorCode.BUSY, message)


class CapabilityUnavailableError(AppError):
    def __init__(self, message: str = "能力未启用或依赖缺失") -> None:
        super().__init__(ErrorCode.CAPABILITY_UNAVAILABLE, message)


class DependencyTimeoutError(AppError):
    def __init__(self, message: str = "依赖超时") -> None:
        super().__init__(ErrorCode.DEPENDENCY_TIMEOUT, message)


class StorageUnavailableError(AppError):
    def __init__(self, message: str = "存储不可用") -> None:
        super().__init__(ErrorCode.STORAGE_UNAVAILABLE, message)


class InterruptedError_(AppError):
    """run 因进程重启等原因中断；区别于取消（cancelled）。"""

    def __init__(self, message: str = "执行被中断") -> None:
        super().__init__(ErrorCode.INTERRUPTED, message)
