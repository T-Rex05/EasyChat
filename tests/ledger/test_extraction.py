"""账单截图识别候选（F6）单测：字段归一、置信度、缺失字段、修正与 Adapter 端口。

全部使用 ``fake_vision_payload`` 与本地假 Adapter，不读真实截图、不访问网络。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from backend.modules.ledger.contracts import DIRECTION_UNKNOWN, review_fields
from backend.modules.ledger.extraction import (
    MIN_FIELD_CONFIDENCE,
    REQUIRED_FIELDS,
    VisionField,
    VisionPort,
    apply_corrections,
    candidate_from_vision,
    candidate_payload,
    extract_candidate,
    is_ready_for_confirmation,
)
from backend.shared.errors import InvalidInputError
from tests.support.ledger_fixtures import fake_vision_payload


def _candidate(payload: Any = None, **kwargs: Any):
    """默认用假视觉结果（0.93 置信、字段完整）构造候选。"""
    return candidate_from_vision(
        candidate_id="cand-1",
        image_file_id="file-1",
        payload=fake_vision_payload() if payload is None else payload,
        **kwargs,
    )


class FakeVision:
    """测试内假视觉 Adapter：只回放给定 payload 或抛给定异常。"""

    def __init__(self, payload: dict[str, Any] | None = None, error: Exception | None = None):
        self.payload = fake_vision_payload() if payload is None else payload
        self.error = error
        self.calls: list[tuple[Path, str]] = []

    async def extract(self, path: Path, *, prompt: str = "") -> dict[str, Any]:
        self.calls.append((Path(path), prompt))
        if self.error is not None:
            raise self.error
        return self.payload


# ---- 基本路径 ----------------------------------------------------------------


def test_default_payload_is_ready_for_confirmation():
    candidate = _candidate()

    assert candidate.candidate_id == "cand-1"
    assert candidate.image_file_id == "file-1"
    assert candidate.amount_minor == 2350
    assert candidate.occurred_at is not None
    assert candidate.occurred_at.startswith("2026-10-02T12:00:00")
    assert candidate.direction == "expense"
    assert candidate.currency == "CNY"
    assert candidate.merchant == "示例便利店"
    assert candidate.missing_fields == ()
    assert candidate.needs_review is False
    assert review_fields(candidate) == ()
    assert is_ready_for_confirmation(candidate) is True


def test_raw_text_is_truncated_to_4000_chars():
    candidate = _candidate(fake_vision_payload(text="账" * 5000))

    assert len(candidate.raw_text) == 4000


# ---- 缺失/无法解析：绝不猜成 0 ------------------------------------------------


def test_missing_amount_is_none_not_zero():
    candidate = _candidate(fake_vision_payload(amount=None))

    assert candidate.amount_minor is None
    assert "amount" in candidate.missing_fields
    assert candidate.needs_review is True
    assert is_ready_for_confirmation(candidate) is False
    assert "amount" in review_fields(candidate)
    assert any("金额缺失" in note for note in candidate.notes)


def test_unparsable_amount_keeps_none_with_chinese_note():
    candidate = _candidate(fake_vision_payload(amount="abc"))

    assert candidate.amount_minor is None
    assert "amount" in candidate.missing_fields
    assert candidate.needs_review is True
    assert is_ready_for_confirmation(candidate) is False
    assert any("金额无法解析" in note for note in candidate.notes)


def test_missing_direction_becomes_unknown():
    candidate = _candidate(fake_vision_payload(direction=None))

    assert candidate.direction == DIRECTION_UNKNOWN
    assert "direction" in candidate.missing_fields
    assert candidate.needs_review is True
    assert is_ready_for_confirmation(candidate) is False
    assert any("方向" in note for note in candidate.notes)


def test_missing_occurred_at_marks_field_and_blocks_confirmation():
    candidate = _candidate(fake_vision_payload(occurred=None))

    assert candidate.occurred_at is None
    assert "occurred_at" in candidate.missing_fields
    assert candidate.needs_review is True
    assert is_ready_for_confirmation(candidate) is False


def test_fields_key_missing_raises_invalid_input():
    with pytest.raises(InvalidInputError) as excinfo:
        candidate_from_vision(
            candidate_id="cand-1",
            image_file_id="file-1",
            payload={"text": "只有原文，没有字段"},
        )

    assert "视觉结果缺少 fields" in str(excinfo.value)

    with pytest.raises(InvalidInputError):
        candidate_from_vision(
            candidate_id="cand-1",
            image_file_id="file-1",
            payload={"fields": ["amount"]},
        )


# ---- 置信度 ------------------------------------------------------------------


def test_low_confidence_marks_required_fields_for_review():
    candidate = _candidate(fake_vision_payload(confidence=0.5))

    for name in REQUIRED_FIELDS:
        assert candidate.fields[name].needs_review is True
        assert candidate.fields[name].confidence == pytest.approx(0.5)
    assert candidate.needs_review is True
    assert is_ready_for_confirmation(candidate) is False
    assert any("置信度低" in note for note in candidate.notes)


def test_missing_confidence_defaults_to_zero():
    payload = fake_vision_payload()
    payload.pop("confidence")

    candidate = _candidate(payload)

    assert candidate.fields["amount"].confidence == 0.0
    assert candidate.fields["amount"].needs_review is True
    assert candidate.needs_review is True
    assert is_ready_for_confirmation(candidate) is False


def test_original_field_name_confidence_wins():
    payload = {
        "fields": {"金额": "23.50", "交易时间": "2026-10-02 12:00:00", "收/支": "支出"},
        "confidence": {"金额": 0.99, "amount": 0.10, "交易时间": 0.99, "收/支": 0.99},
        "text": "支付成功 ¥23.50",
    }

    candidate = _candidate(payload)

    # 原字段名 0.99 优先，不能被归一后的 amount=0.10 覆盖
    assert candidate.fields["amount"].confidence == pytest.approx(0.99)
    assert candidate.fields["amount"].needs_review is False
    assert candidate.needs_review is False


def test_confidence_falls_back_to_normalized_name():
    payload = {
        "fields": {"金额": "23.50", "交易时间": "2026-10-02 12:00:00", "收/支": "支出"},
        "confidence": {"amount": 0.40},
        "text": "",
    }

    candidate = _candidate(payload)

    assert candidate.fields["amount"].confidence == pytest.approx(0.40)
    assert candidate.fields["amount"].needs_review is True
    assert candidate.needs_review is True


# ---- 字段别名与币种 -----------------------------------------------------------


def test_field_aliases_are_recognized():
    payload = {
        "fields": {"金额": "12.34", "时间": "2026-10-02 12:00:00", "收/支": "支出"},
        "confidence": {"金额": 0.93, "时间": 0.93, "收/支": 0.93},
        "text": "支出 12.34",
    }

    candidate = _candidate(payload)

    assert candidate.amount_minor == 1234
    assert candidate.direction == "expense"
    assert candidate.occurred_at is not None
    assert candidate.occurred_at.startswith("2026-10-02T12:00:00")
    assert candidate.needs_review is False


def test_currency_field_preserved_and_symbol_detected():
    with_field = _candidate(fake_vision_payload(currency="USD"))
    assert with_field.currency == "USD"

    payload = {
        "fields": {"amount": "$12.34", "occurred_at": "2026-10-02 12:00:00", "direction": "支出"},
        "confidence": {"amount": 0.93, "occurred_at": 0.93, "direction": 0.93},
        "text": "Paid $12.34",
    }
    detected = _candidate(payload)

    assert detected.amount_minor == 1234
    assert detected.currency == "USD"


# ---- 用户修正 -----------------------------------------------------------------


def test_apply_corrections_reparses_amount():
    candidate = _candidate()

    corrected = apply_corrections(candidate, {"amount": "88.80"}, reviewer_id=7)

    assert corrected is not candidate
    assert corrected.amount_minor == 8880
    assert corrected.fields["amount"].value == "88.80"
    assert corrected.fields["amount"].confidence == 1.0
    assert corrected.fields["amount"].needs_review is False
    assert corrected.needs_review is False
    assert is_ready_for_confirmation(corrected) is True
    assert corrected.candidate_id == candidate.candidate_id
    assert corrected.image_file_id == candidate.image_file_id


def test_apply_corrections_recomputes_needs_review():
    low = _candidate(fake_vision_payload(confidence=0.5))
    assert low.needs_review is True

    amount_fixed = apply_corrections(low, {"amount": "88.80"}, reviewer_id=7)
    # 金额已确认，但时间/方向仍是低置信 → 整体仍需核对
    assert amount_fixed.fields["amount"].needs_review is False
    assert amount_fixed.needs_review is True
    assert is_ready_for_confirmation(amount_fixed) is False

    fully_fixed = apply_corrections(
        amount_fixed,
        {"occurred_at": "2026-10-02 12:00:00", "direction": "expense"},
        reviewer_id=7,
    )
    assert fully_fixed.needs_review is False
    assert is_ready_for_confirmation(fully_fixed) is True


def test_apply_corrections_does_not_mutate_original():
    candidate = _candidate()

    corrected = apply_corrections(candidate, {"amount": "88.80"}, reviewer_id=7)

    assert candidate.amount_minor == 2350
    assert candidate.fields["amount"].value == "23.50"
    assert candidate.fields["amount"].confidence == pytest.approx(0.93)
    assert corrected.fields is not candidate.fields


def test_apply_corrections_rejects_unknown_key():
    candidate = _candidate()

    with pytest.raises(InvalidInputError) as excinfo:
        apply_corrections(candidate, {"category": "餐饮"}, reviewer_id=1)

    assert "不支持修正的字段" in str(excinfo.value)
    assert "category" in str(excinfo.value)


def test_apply_corrections_with_bad_amount_still_missing():
    candidate = _candidate()

    corrected = apply_corrections(candidate, {"amount": "abc"}, reviewer_id=1)

    assert corrected.amount_minor is None
    assert "amount" in corrected.missing_fields
    assert corrected.needs_review is True
    assert any("金额无法解析" in note for note in corrected.notes)


# ---- JSON 视图 ----------------------------------------------------------------


def test_candidate_payload_is_json_safe_and_has_no_paths():
    candidate = _candidate()

    payload = candidate_payload(candidate)
    text = json.dumps(payload, ensure_ascii=False)
    decoded = json.loads(text)

    assert decoded["candidate_id"] == "cand-1"
    assert decoded["image_file_id"] == "file-1"
    assert decoded["amount_minor"] == 2350
    assert decoded["missing_fields"] == []
    assert set(decoded["fields"]["amount"]) == {
        "value",
        "confidence",
        "source_text",
        "needs_review",
    }
    for key in (
        "candidate_id",
        "image_file_id",
        "fields",
        "missing_fields",
        "confidence",
        "merchant",
        "amount_minor",
        "direction",
        "occurred_at",
        "currency",
        "needs_review",
        "notes",
        "raw_text",
    ):
        assert key in decoded
    # 不得下传路径或二进制内容
    assert "path" not in text
    assert "image_path" not in decoded


def test_candidate_payload_for_missing_amount_is_still_json_safe():
    payload = candidate_payload(_candidate(fake_vision_payload(amount=None)))

    text = json.dumps(payload, ensure_ascii=False)

    assert json.loads(text)["amount_minor"] is None
    assert "amount" in json.loads(text)["missing_fields"]


# ---- 视觉端口 -----------------------------------------------------------------


async def test_extract_candidate_success_path():
    vision = FakeVision()

    candidate = await extract_candidate(
        vision,
        image_path=Path("shots/pay.png"),
        image_file_id="file-1",
        candidate_id="cand-1",
    )

    assert candidate.amount_minor == 2350
    assert candidate.needs_review is False
    assert len(vision.calls) == 1
    called_path, called_prompt = vision.calls[0]
    assert called_path == Path("shots/pay.png")
    assert called_prompt  # 传入了中文提示词


async def test_extract_candidate_propagates_adapter_error():
    vision = FakeVision(error=RuntimeError("视觉服务不可用"))

    with pytest.raises(RuntimeError, match="视觉服务不可用"):
        await extract_candidate(
            vision,
            image_path=Path("shots/pay.png"),
            image_file_id="file-1",
            candidate_id="cand-1",
        )


def test_vision_port_is_a_protocol_and_vision_field_defaults():
    assert getattr(VisionPort, "_is_protocol", False) is True

    field = VisionField(name="amount", value="23.50", confidence=0.93)
    assert field.needs_review is False
    assert MIN_FIELD_CONFIDENCE == 0.85
