"""情绪采样的受控模型路径：严格 JSON 校验，失败跳过而不是猜。"""
from __future__ import annotations

import asyncio

from backend.modules.profiles.api import ProfilesService
from tests.support.rig import FakeClock, make_rig

BASE = 1762300800.0


class FakeGenerator:
    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.calls: list[dict] = []

    async def generate(self, system: str, user: str, **kwargs):
        self.calls.append({"system": system, "user": user, **kwargs})
        return self.raw


def _service(tmp_path, raw: str | None = None):
    rig = make_rig(tmp_path, clock=FakeClock(BASE), seed_access=True)
    user = rig.seed_user()
    generator = FakeGenerator(raw) if raw is not None else None
    service = ProfilesService(rig.db, access=rig.access, clock=rig.clock, generator=generator)
    service.set_mood_enabled(user, True)
    return service, user, generator


def test_model_json_is_validated_and_recorded(tmp_path) -> None:
    raw = '{"score": -1, "labels": ["加班"], "evidence": "今天加班到很晚"}'
    service, user, generator = _service(tmp_path, raw)
    entry = asyncio.run(service.sample_run_for_owner_async(
        user.user_id, "今天加班到很晚，好累", run_id="run_model"
    ))
    assert entry is not None
    assert entry.score == -1
    assert entry.labels == ("加班",)
    assert entry.evidence == ("今天加班到很晚",)
    assert generator.calls and generator.calls[0]["max_chars"] == 400


def test_model_can_wrap_json_in_markdown_fence(tmp_path) -> None:
    service, user, _generator = _service(tmp_path, '```json\n{"score": 1, "labels": ["开心"], "evidence": "今天很开心"}\n```')
    entry = asyncio.run(service.sample_run_for_owner_async(
        user.user_id, "今天很开心", run_id="run_fence"
    ))
    assert entry is not None and entry.score == 1


def test_model_evidence_must_be_original_substring(tmp_path) -> None:
    service, user, _generator = _service(
        tmp_path, '{"score": -1, "labels": ["低落"], "evidence": "没有这句"}'
    )
    assert asyncio.run(service.sample_run_for_owner_async(
        user.user_id, "今天有点低落", run_id="run_bad_evidence"
    )) is None


def test_model_rejects_unknown_labels_and_bad_score(tmp_path) -> None:
    service, user, _generator = _service(
        tmp_path, '{"score": -3, "labels": ["抑郁"], "evidence": "难受"}'
    )
    assert asyncio.run(service.sample_run_for_owner_async(
        user.user_id, "今天很难受", run_id="run_bad_model"
    )) is None


def test_model_empty_output_skips_day(tmp_path) -> None:
    service, user, _generator = _service(tmp_path, "")
    assert asyncio.run(service.sample_run_for_owner_async(
        user.user_id, "今天很难受", run_id="run_empty_model"
    )) is None


def test_no_generator_keeps_deterministic_fallback(tmp_path) -> None:
    service, user, generator = _service(tmp_path, None)
    assert generator is None
    entry = asyncio.run(service.sample_run_for_owner_async(
        user.user_id, "今天加班到很晚，好累", run_id="run_fallback"
    ))
    assert entry is not None and entry.score <= -1
