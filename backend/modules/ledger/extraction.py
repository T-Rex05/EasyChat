"""账单截图识别候选（F6，设计 §7 图片识别）。

视觉 Adapter 只负责“看见”，本模块负责把视觉结果转成可核对的候选：

- 字段名归一（中英文别名）、字段级置信度、缺失字段与中文提示；
- 金额/时间/方向走确定性解析，解析失败保留 ``None`` 并进入 ``missing_fields``，
  绝不把“没认出金额”当成 0，也不猜交易方向或时间；
- 用户修正后重新解析（同一套内部逻辑），并保持不可变对象语义。

纯函数，不写数据库；``VisionPort`` 只是端口协议，不导入任何真实视觉 SDK。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from backend.modules.ledger.contracts import (
    DIRECTION_EXPENSE,
    DIRECTION_INCOME,
    DIRECTION_NEUTRAL,
    DIRECTION_UNKNOWN,
    ExtractedField,
    ImageCandidate,
)
from backend.modules.ledger.normalization import (
    DEFAULT_TIMEZONE,
    clean_text,
    detect_currency,
    normalize_direction,
    parse_money,
    parse_occurred_at,
)
from backend.shared.errors import InvalidInputError

# 字段级置信度阈值：低于它就必须让用户核对（设计 §7：无法确定进入 review）。
MIN_FIELD_CONFIDENCE = 0.85
# 入账必需字段：金额、交易时间、收支方向。缺任何一个都不能直接入账。
REQUIRED_FIELDS: tuple[str, ...] = ("amount", "occurred_at", "direction")

# 原文/字段文本的截断长度：原文只用于核对，不无限透传。
RAW_TEXT_LIMIT = 4000
FIELD_TEXT_LIMIT = 200

# 视觉 Adapter 的字段名别名表：canonical 名在前，中文/口语写法在后。
# 归一顺序即优先级：同时出现 amount 与 金额 时以 amount 为准。
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "amount": ("amount", "金额"),
    "occurred_at": ("occurred_at", "交易时间", "时间", "time"),
    "direction": ("direction", "收/支"),
    "merchant": ("merchant", "商户", "交易对方"),
    "currency": ("currency", "币种"),
    "product": ("product", "商品"),
    "tx_type": ("tx_type", "交易类型"),
    "external_id": ("external_id", "交易单号"),
    "note": ("note", "备注"),
}

# 允许用户手工修正的字段：必需字段 + 影响入账/展示的可选字段。
CORRECTABLE_FIELDS: frozenset[str] = frozenset(
    set(REQUIRED_FIELDS)
    | {"merchant", "product", "note", "currency", "tx_type", "external_id"}
)

# 只有确定的方向才允许确认入账；unknown 必须人工选择。
_CONFIRMABLE_DIRECTIONS = frozenset(
    {DIRECTION_EXPENSE, DIRECTION_INCOME, DIRECTION_NEUTRAL}
)

# 发给视觉 Adapter 的默认提示词：要求结构化输出，并明确禁止猜测金额。
VISION_PROMPT = (
    "请识别这张支付账单截图，只返回 JSON，不要返回解释。结构："
    '{"fields": {"amount": "金额", "occurred_at": "交易时间", "direction": "支出/收入", '
    '"merchant": "商户", "currency": "币种", "product": "商品", '
    '"tx_type": "交易类型", "external_id": "交易单号", "note": "备注"}, '
    '"confidence": {"字段名": 0 到 1 之间的小数}, "text": "截图全文", '
    '"regions": [{"field": "字段名", "box": [x1, y1, x2, y2]}]}。'
    "看不清的字段请留空，不要猜测金额或时间。"
)


@dataclass(frozen=True, slots=True)
class VisionField:
    """Adapter 侧的单字段输出形状（便于假 Adapter/测试构造，非必需类型）。

    只描述“识别到了什么”：值、置信度以及是否已经需要人工核对。
    """

    name: str
    value: str
    confidence: float
    needs_review: bool = False


@dataclass(frozen=True, slots=True)
class _FieldInput:
    """归一后的单字段输入：原始识别值（不做任何猜测/清洗）+ 置信度。"""

    value: Any
    confidence: float


class VisionPort(Protocol):
    """视觉识别端口：只约定一次异步调用，不绑定任何真实 SDK。

    Adapter 抛出的异常必须由调用方原样上抛（计入失败），本模块不吞异常。
    """

    async def extract(self, path: Path, *, prompt: str = "") -> Mapping[str, Any]: ...


def candidate_from_vision(
    *,
    candidate_id: str,
    image_file_id: str,
    payload: Mapping[str, Any],
    timezone: str = DEFAULT_TIMEZONE,
    default_currency: str = "CNY",
    min_confidence: float = MIN_FIELD_CONFIDENCE,
) -> ImageCandidate:
    """视觉 Adapter 输出 → ``ImageCandidate``。

    ``payload`` 结构：``{"fields": {...}, "confidence": {字段: float},
    "text": "...", "regions": [...]}``。``fields`` 缺失或不是 Mapping 时抛
    ``InvalidInputError``；``confidence`` 缺失时按 0.0 处理（全部字段需核对）。

    整体 ``confidence``：必需字段全部存在时取三者最小值；任一必需字段缺失或
    无法解析时为 0.0（表示“整体不可直接采用”，不代表金额是 0）。
    """
    fields = payload.get("fields") if isinstance(payload, Mapping) else None
    if not isinstance(fields, Mapping):
        raise InvalidInputError("视觉结果缺少 fields")

    raw_confidence = payload.get("confidence")
    confidence_map: Mapping[str, Any] = (
        raw_confidence if isinstance(raw_confidence, Mapping) else {}
    )

    inputs = _normalize_payload_fields(fields, confidence_map)
    raw_text = clean_text(payload.get("text"), limit=RAW_TEXT_LIMIT)
    return _build_candidate(
        candidate_id=candidate_id,
        image_file_id=image_file_id,
        inputs=inputs,
        raw_text=raw_text,
        timezone=timezone,
        default_currency=default_currency,
        min_confidence=min_confidence,
    )


def apply_corrections(
    candidate: ImageCandidate,
    corrections: Mapping[str, str],
    *,
    reviewer_id: int,
) -> ImageCandidate:
    """用户修正后返回**新**候选：只接受白名单字段，其余键报错。

    修正字段置信度置 1.0；随后用与 ``candidate_from_vision`` 相同的内部函数
    重新解析金额/时间/方向，因此“改坏的金额”依旧回到 ``missing_fields``，
    不会被猜成 0。候选不保存时区，重建时统一使用账本默认时区。
    """
    unknown = [key for key in corrections if key not in CORRECTABLE_FIELDS]
    if unknown:
        raise InvalidInputError(f"不支持修正的字段: {', '.join(unknown)}")

    inputs: dict[str, _FieldInput] = {
        name: _FieldInput(value=item.value, confidence=item.confidence)
        for name, item in candidate.fields.items()
    }
    applied: list[str] = []
    for name, value in corrections.items():
        # 用户确认过的值直接信任：置信度 1.0，不再要求核对。
        inputs[name] = _FieldInput(value=value, confidence=1.0)
        applied.append(name)

    notes: tuple[str, ...] = ()
    if applied:
        notes = (f"已按用户修正：{', '.join(applied)}（校对者 {reviewer_id}）",)
    return _build_candidate(
        candidate_id=candidate.candidate_id,
        image_file_id=candidate.image_file_id,
        inputs=inputs,
        raw_text=candidate.raw_text,
        timezone=DEFAULT_TIMEZONE,
        default_currency=candidate.currency or "CNY",
        min_confidence=MIN_FIELD_CONFIDENCE,
        notes=notes,
    )


def is_ready_for_confirmation(candidate: ImageCandidate) -> bool:
    """是否可以进入“用户确认后入账”：无需核对且三个必需字段都可用。"""
    return (
        not candidate.needs_review
        and candidate.amount_minor is not None
        and bool(candidate.occurred_at)
        and candidate.direction in _CONFIRMABLE_DIRECTIONS
    )


def candidate_payload(candidate: ImageCandidate) -> dict[str, Any]:
    """JSON 安全视图（供 API / LLM 工具返回）：不含路径、不含二进制。"""
    return {
        "candidate_id": str(candidate.candidate_id),
        "image_file_id": str(candidate.image_file_id),
        "fields": {
            name: {
                "value": item.value,
                "confidence": float(item.confidence),
                "source_text": item.source_text,
                "needs_review": bool(item.needs_review),
            }
            for name, item in sorted(candidate.fields.items())
        },
        "missing_fields": list(candidate.missing_fields),
        "confidence": float(candidate.confidence),
        "merchant": candidate.merchant,
        "amount_minor": candidate.amount_minor,
        "direction": candidate.direction,
        "occurred_at": candidate.occurred_at,
        "currency": candidate.currency,
        "needs_review": bool(candidate.needs_review),
        "notes": list(candidate.notes),
        "raw_text": candidate.raw_text,
    }


async def extract_candidate(
    vision: VisionPort,
    *,
    image_path: Path,
    image_file_id: str,
    candidate_id: str,
    timezone: str = DEFAULT_TIMEZONE,
    default_currency: str = "CNY",
) -> ImageCandidate:
    """调用视觉 Adapter 并转成候选；Adapter 异常原样上抛，由上层计入失败。"""
    payload = await vision.extract(image_path, prompt=VISION_PROMPT)
    return candidate_from_vision(
        candidate_id=candidate_id,
        image_file_id=image_file_id,
        payload=payload,
        timezone=timezone,
        default_currency=default_currency,
    )


# ---- 内部实现（唯一解析入口：candidate_from_vision / apply_corrections 共用） ------


def _normalize_payload_fields(
    fields: Mapping[str, Any], confidence: Mapping[str, Any]
) -> dict[str, _FieldInput]:
    """按别名表把 Adapter 字段名归一成 canonical 名，并解析字段级置信度。"""
    normalized: dict[str, _FieldInput] = {}
    for canonical, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias not in fields:
                continue
            normalized[canonical] = _FieldInput(
                value=fields[alias],
                confidence=_lookup_confidence(confidence, alias, canonical),
            )
            break
    return normalized


def _lookup_confidence(
    confidence: Mapping[str, Any], original_name: str, canonical_name: str
) -> float:
    """置信度查找：原字段名优先，找不到再按归一后的名字找，都没有按 0.0。"""
    for key in (original_name, canonical_name):
        if key in confidence:
            return _coerce_confidence(confidence[key])
    return 0.0


def _coerce_confidence(value: object) -> float:
    """把 Adapter 给的值压成 [0, 1]；非法值按 0.0（宁可多核对，不可放宽）。"""
    if value is None or isinstance(value, bool):
        return 0.0
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(number):
        return 0.0
    return min(1.0, max(0.0, number))


def _is_blank(value: object) -> bool:
    """空值判定：None 与纯空白字符串视为缺失（0 不是空）。"""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _build_candidate(
    *,
    candidate_id: str,
    image_file_id: str,
    inputs: Mapping[str, _FieldInput],
    raw_text: str,
    timezone: str,
    default_currency: str,
    min_confidence: float,
    notes: Sequence[str] = (),
) -> ImageCandidate:
    """唯一构造入口：解析金额/时间/方向，汇总缺失字段、置信度与提示。"""
    notes_out: list[str] = list(notes)
    missing: list[str] = []

    # 币种：显式字段优先，其次从金额文本识别（如 $、USD），最后用默认币种。
    currency_input = inputs.get("currency")
    has_currency_field = currency_input is not None and not _is_blank(currency_input.value)
    currency = default_currency
    if currency_input is not None and has_currency_field:
        currency = detect_currency(str(currency_input.value), default=default_currency)

    amount_minor: int | None = None
    amount_input = inputs.get("amount")
    if amount_input is None or _is_blank(amount_input.value):
        missing.append("amount")
        notes_out.append("金额缺失，需人工核对（不按 0 入账）")
    else:
        amount_minor, money_currency, amount_error = parse_money(
            amount_input.value, default_currency=currency
        )
        if amount_error is not None or amount_minor is None:
            # 识别失败绝不猜数字：金额保持 None，交给用户修正。
            amount_minor = None
            missing.append("amount")
            notes_out.append(f"金额无法解析：{amount_error or '未知原因'}")
        elif not has_currency_field:
            currency = money_currency

    occurred_at: str | None = None
    occurred_input = inputs.get("occurred_at")
    if occurred_input is None or _is_blank(occurred_input.value):
        missing.append("occurred_at")
        notes_out.append("交易时间缺失，不能用上传时间代替")
    else:
        occurred_at, time_error = parse_occurred_at(
            occurred_input.value, timezone=timezone
        )
        if occurred_at is None:
            missing.append("occurred_at")
            notes_out.append(f"交易时间无法解析：{time_error or '未知原因'}")

    direction_input = inputs.get("direction")
    direction = (
        DIRECTION_UNKNOWN
        if direction_input is None
        else normalize_direction(direction_input.value)
    )
    if direction == DIRECTION_UNKNOWN:
        missing.append("direction")
        notes_out.append("交易方向缺失或无法识别（不以金额正负推断）")

    missing_fields = tuple(dict.fromkeys(missing))
    missing_set = set(missing_fields)

    fields_out: dict[str, ExtractedField] = {}
    for name in sorted(inputs):
        item = inputs[name]
        low_confidence = item.confidence < min_confidence
        if low_confidence:
            notes_out.append(
                f"字段识别置信度低：{name}={item.confidence:.2f}"
                f"（阈值 {min_confidence:.2f}）"
            )
        text = clean_text(item.value, limit=FIELD_TEXT_LIMIT)
        fields_out[name] = ExtractedField(
            value=text,
            confidence=item.confidence,
            source_text=text,
            needs_review=low_confidence or name in missing_set,
        )

    # 任一必需字段缺失/解析失败 → 整体置信度 0.0；否则取必需字段最小值。
    if missing_fields:
        overall_confidence = 0.0
    else:
        overall_confidence = round(
            min(inputs[name].confidence for name in REQUIRED_FIELDS), 4
        )

    needs_review = bool(missing_fields) or any(
        name in inputs and inputs[name].confidence < min_confidence
        for name in REQUIRED_FIELDS
    )

    merchant_input = inputs.get("merchant")
    merchant = (
        ""
        if merchant_input is None
        else clean_text(merchant_input.value, limit=FIELD_TEXT_LIMIT)
    )

    return ImageCandidate(
        candidate_id=candidate_id,
        image_file_id=image_file_id,
        fields=fields_out,
        missing_fields=missing_fields,
        confidence=overall_confidence,
        raw_text=clean_text(raw_text, limit=RAW_TEXT_LIMIT),
        merchant=merchant,
        amount_minor=amount_minor,
        direction=direction,
        occurred_at=occurred_at,
        currency=currency,
        needs_review=needs_review,
        notes=tuple(dict.fromkeys(notes_out)),
    )


__all__ = [
    "CORRECTABLE_FIELDS",
    "FIELD_ALIASES",
    "MIN_FIELD_CONFIDENCE",
    "RAW_TEXT_LIMIT",
    "REQUIRED_FIELDS",
    "VISION_PROMPT",
    "VisionField",
    "VisionPort",
    "apply_corrections",
    "candidate_from_vision",
    "candidate_payload",
    "extract_candidate",
    "is_ready_for_confirmation",
]
