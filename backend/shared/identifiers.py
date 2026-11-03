"""run/session/call 等 ID 的构造与校验。

格式：`{kind}_{32位十六进制}`。kind 参与校验，防止把 session_id 误当 run_id 用。
"""
import re
import uuid

_ID_RE = re.compile(r"^[a-z][a-z0-9]{0,15}_[0-9a-f]{32}$")

_PREFIX_RUN = "run"
_PREFIX_SESSION = "sess"
_PREFIX_CALL = "call"
_PREFIX_JOB = "job"
_PREFIX_DELIVERY = "dlv"
_PREFIX_ARTIFACT = "art"
_PREFIX_ATTACHMENT = "att"
_PREFIX_CHANNEL_ACCOUNT = "chn"
_PREFIX_CHANNEL_BINDING = "bnd"
_PREFIX_CHANNEL_EVENT = "evt"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def new_run_id() -> str:
    return _new_id(_PREFIX_RUN)


def new_session_id() -> str:
    return _new_id(_PREFIX_SESSION)


def new_call_id() -> str:
    return _new_id(_PREFIX_CALL)


def new_job_id() -> str:
    return _new_id(_PREFIX_JOB)


def new_delivery_id() -> str:
    return _new_id(_PREFIX_DELIVERY)


def new_artifact_id() -> str:
    return _new_id(_PREFIX_ARTIFACT)


def new_attachment_id() -> str:
    return _new_id(_PREFIX_ATTACHMENT)


def new_channel_account_id() -> str:
    return _new_id(_PREFIX_CHANNEL_ACCOUNT)


def new_channel_binding_id() -> str:
    return _new_id(_PREFIX_CHANNEL_BINDING)


def new_channel_event_id() -> str:
    return _new_id(_PREFIX_CHANNEL_EVENT)


def is_valid_id(value: str, *, prefix: str | None = None) -> bool:
    """校验 ID 格式；给定 prefix 时还要求前缀匹配。"""
    if not isinstance(value, str) or not _ID_RE.match(value):
        return False
    if prefix is not None and not value.startswith(f"{prefix}_"):
        return False
    return True


def is_run_id(value: str) -> bool:
    return is_valid_id(value, prefix=_PREFIX_RUN)


def is_session_id(value: str) -> bool:
    return is_valid_id(value, prefix=_PREFIX_SESSION)


def is_call_id(value: str) -> bool:
    return is_valid_id(value, prefix=_PREFIX_CALL)
