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
_PREFIX_PART = "part"
_PREFIX_SCHEDULE = "sch"
_PREFIX_OCCURRENCE = "occ"
_PREFIX_MEMORY = "mem"
_PREFIX_REVISION = "rev"
_PREFIX_SIGNAL = "sig"
_PREFIX_SKILL = "skl"
_PREFIX_SKILL_VERSION = "skv"
_PREFIX_FILE = "fil"
_PREFIX_FILE_REF = "fref"
_PREFIX_UPLOAD_RECEIPT = "upr"
_PREFIX_EXTRACTION = "fex"
_PREFIX_LEDGER_ACCOUNT = "lac"
_PREFIX_LEDGER_IMPORT = "lim"
_PREFIX_LEDGER_ROW = "lrw"
_PREFIX_LEDGER_SOURCE = "lsr"
_PREFIX_LEDGER_TX = "ltx"
_PREFIX_LEDGER_REFUND = "lrf"
_PREFIX_LEDGER_CATEGORY = "lct"
_PREFIX_LEDGER_RULE = "lru"
_PREFIX_LEDGER_CHANGE = "lch"
_PREFIX_LEDGER_ANALYSIS = "lan"
_PREFIX_MOOD = "mood"
_PREFIX_INBOX = "inb"
_PREFIX_SUPERAGENT_TASK = "sag"
_PREFIX_SUPERAGENT_WEBHOOK_EVENT = "swe"
_PREFIX_SUPERAGENT_ATTEMPT = "sat"
_PREFIX_SUPERAGENT_INPUT = "sai"
_PREFIX_SUPERAGENT_REPORT = "sar"
_PREFIX_ACCEPTANCE_ROUND = "arnd"


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


def new_part_id() -> str:
    return _new_id(_PREFIX_PART)


def new_schedule_id() -> str:
    return _new_id(_PREFIX_SCHEDULE)


def new_occurrence_id() -> str:
    return _new_id(_PREFIX_OCCURRENCE)


def new_memory_id() -> str:
    return _new_id(_PREFIX_MEMORY)


def new_revision_id() -> str:
    return _new_id(_PREFIX_REVISION)


def new_signal_id() -> str:
    return _new_id(_PREFIX_SIGNAL)


def new_skill_id() -> str:
    return _new_id(_PREFIX_SKILL)


def new_skill_version_id() -> str:
    return _new_id(_PREFIX_SKILL_VERSION)


def new_artifact_id() -> str:
    return _new_id(_PREFIX_ARTIFACT)


def new_attachment_id() -> str:
    return _new_id(_PREFIX_ATTACHMENT)


def new_file_id() -> str:
    return _new_id(_PREFIX_FILE)


def new_file_reference_id() -> str:
    return _new_id(_PREFIX_FILE_REF)


def new_upload_receipt_id() -> str:
    return _new_id(_PREFIX_UPLOAD_RECEIPT)


def new_extraction_id() -> str:
    return _new_id(_PREFIX_EXTRACTION)


def new_ledger_account_id() -> str:
    return _new_id(_PREFIX_LEDGER_ACCOUNT)


def new_ledger_import_id() -> str:
    return _new_id(_PREFIX_LEDGER_IMPORT)


def new_source_row_id() -> str:
    return _new_id(_PREFIX_LEDGER_ROW)


def new_transaction_id() -> str:
    return _new_id(_PREFIX_LEDGER_TX)


def new_transaction_source_id() -> str:
    return _new_id(_PREFIX_LEDGER_SOURCE)


def new_refund_link_id() -> str:
    return _new_id(_PREFIX_LEDGER_REFUND)


def new_category_id() -> str:
    return _new_id(_PREFIX_LEDGER_CATEGORY)


def new_category_rule_id() -> str:
    return _new_id(_PREFIX_LEDGER_RULE)


def new_ledger_change_id() -> str:
    return _new_id(_PREFIX_LEDGER_CHANGE)


def new_analysis_id() -> str:
    return _new_id(_PREFIX_LEDGER_ANALYSIS)


def new_mood_id() -> str:
    return _new_id(_PREFIX_MOOD)


def new_inbox_id() -> str:
    return _new_id(_PREFIX_INBOX)


def new_superagent_task_id() -> str:
    return _new_id(_PREFIX_SUPERAGENT_TASK)


def new_superagent_attempt_id() -> str:
    return _new_id(_PREFIX_SUPERAGENT_ATTEMPT)


def new_superagent_input_id() -> str:
    return _new_id(_PREFIX_SUPERAGENT_INPUT)


def new_superagent_report_id() -> str:
    return _new_id(_PREFIX_SUPERAGENT_REPORT)


def new_superagent_webhook_event_id() -> str:
    return _new_id(_PREFIX_SUPERAGENT_WEBHOOK_EVENT)


def new_acceptance_round_id() -> str:
    return _new_id(_PREFIX_ACCEPTANCE_ROUND)


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
