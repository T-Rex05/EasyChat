"""Trusted, bounded CodeMode output sidecars, independent of application services."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from threading import Lock


MAX_CAPTURE_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class CapturedOutput:
    content: str
    raw_complete: bool
    captured_bytes: int
    dropped_bytes: int | None
    attempt_id: int
    closed_reason: str


class OutputSink:
    """A UTF-8 prefix with a hard byte quota and immutable close semantics.

    A timed-out worker can retain this object, but cannot modify its snapshot.
    Writes are encoded in chunks so a large print does not allocate a second
    unbounded byte string. After the first omitted byte, all later text is dropped
    to keep the captured text a contiguous prefix of the emitted stream.
    """

    def __init__(self, max_bytes: int, attempt_id: int):
        self._max_bytes = max_bytes
        self._attempt_id = attempt_id
        self._buffer = bytearray()
        self._dropped_bytes = 0
        self._truncated = False
        self._encoding_replaced = False
        self._snapshot: CapturedOutput | None = None
        self._lock = Lock()

    def write(self, text: str) -> bool:
        """Return False only when closed, so callers can fence late output."""
        with self._lock:
            if self._snapshot is not None:
                return False
            for offset in range(0, len(text), 4096):
                chunk = text[offset:offset + 4096]
                try:
                    encoded = chunk.encode("utf-8")
                except UnicodeEncodeError:
                    encoded = chunk.encode("utf-8", errors="replace")
                    self._encoding_replaced = True
                if self._truncated:
                    self._dropped_bytes += len(encoded)
                    continue
                available = self._max_bytes - len(self._buffer)
                if len(encoded) <= available:
                    self._buffer.extend(encoded)
                    continue
                prefix = encoded[:available].decode("utf-8", errors="ignore").encode("utf-8")
                self._buffer.extend(prefix)
                self._dropped_bytes += len(encoded) - len(prefix)
                self._truncated = True
            return True

    def close(self, reason: str = "completed") -> CapturedOutput:
        with self._lock:
            if self._snapshot is None:
                interrupted = reason not in {"completed", "error"}
                self._snapshot = CapturedOutput(
                    content=self._buffer.decode("utf-8"),
                    raw_complete=not (self._truncated or interrupted or self._encoding_replaced),
                    captured_bytes=len(self._buffer),
                    dropped_bytes=None if interrupted or self._encoding_replaced else self._dropped_bytes,
                    attempt_id=self._attempt_id,
                    closed_reason=reason,
                )
                self._buffer.clear()
            return self._snapshot

    @property
    def snapshot(self) -> CapturedOutput | None:
        with self._lock:
            return self._snapshot


class CaptureSession:
    """One host tool call; retries create separate sinks within this holder."""

    def __init__(self, max_bytes: int = MAX_CAPTURE_BYTES):
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
            raise ValueError("capture max_bytes must be a positive integer")
        self.max_bytes = min(max_bytes, MAX_CAPTURE_BYTES)
        self._sinks: list[OutputSink] = []
        self._closed = False
        self._lock = Lock()

    def new_attempt(self) -> OutputSink:
        with self._lock:
            if self._closed:
                raise RuntimeError("capture session is closed")
            sink = OutputSink(self.max_bytes, len(self._sinks) + 1)
            self._sinks.append(sink)
            return sink

    @property
    def attempts(self) -> tuple[CapturedOutput, ...]:
        with self._lock:
            return tuple(
                snapshot for sink in self._sinks
                if (snapshot := sink.snapshot) is not None
            )

    @property
    def latest(self) -> CapturedOutput | None:
        with self._lock:
            return self._sinks[-1].snapshot if self._sinks else None

    def close(self) -> None:
        with self._lock:
            self._closed = True
            for sink in self._sinks:
                sink.close("cancelled")


_CAPTURE_SESSION: ContextVar[CaptureSession | None] = ContextVar(
    "code_mode_capture_session", default=None,
)


def get_capture_session() -> CaptureSession | None:
    return _CAPTURE_SESSION.get()


@contextmanager
def capture_context(max_bytes: int = MAX_CAPTURE_BYTES):
    """Bind a fresh host-owned holder; never infer sidecars from tool text."""
    holder = CaptureSession(max_bytes=max_bytes)
    token = _CAPTURE_SESSION.set(holder)
    try:
        yield holder
    finally:
        holder.close()
        _CAPTURE_SESSION.reset(token)
