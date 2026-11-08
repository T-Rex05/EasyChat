"""语音链路：纯语音转写失败不得提交 run；混合媒体不阻塞图片。"""
from __future__ import annotations

import pytest

from backend.integrations.speech import SpeechError, Transcript
from tests.contracts.test_wechat import _admin, _bind, _register, _user
from tests.support.wechat import inbound, make_channel_rig


def _voice(url: str = "https://cdn.example/v.silk", name: str = "v.silk") -> dict:
    return {
        "from_user_id": "wx_voice",
        "item_list": [{"type": 3, "voice_item": {"url": url, "file_name": name}}],
        "context_token": "ctx-voice",
    }


def _voice_with_text() -> dict:
    return {
        "from_user_id": "wx_voice",
        "item_list": [
            {"type": 1, "text_item": {"text": "语音听不清，我打字说"}},
            {"type": 3, "voice_item": {"url": "https://cdn.example/v.silk", "file_name": "v.silk"}},
        ],
        "context_token": "ctx-voice",
    }


def _voice_with_image() -> dict:
    return {
        "from_user_id": "wx_voice",
        "item_list": [
            {"type": 3, "voice_item": {"url": "https://cdn.example/v.silk", "file_name": "v.silk"}},
            {"type": 2, "image_item": {"url": "https://cdn.example/a.png", "file_name": "a.png"}},
        ],
        "context_token": "ctx-voice",
    }


class FailingSTT:
    async def transcribe(self, path, mime):
        raise SpeechError("测试注入转写失败")


class FixedSTT:
    async def transcribe(self, path, mime):
        return Transcript(text="今晚九点提醒我交周报", language="zh", confidence=0.9)


@pytest.fixture
async def env(tmp_path):
    rig, _transport, _media = make_channel_rig(tmp_path)
    await rig.start_assistant()
    yield rig
    await rig.aclose()


async def _bound_user(rig):
    admin = _admin(rig)
    user = _user(rig)
    account = _register(rig, admin)
    _bind(rig, admin, account, "wx_voice", user)
    return user, account


def _attachment_count(rig, session_id: str) -> int:
    conn = rig.db.connect()
    try:
        return int(conn.execute(
            "SELECT count(*) FROM attachments WHERE session_id=?", (session_id,)
        ).fetchone()[0])
    finally:
        conn.close()


async def test_failed_voice_save_is_not_submitted_as_processed(env) -> None:
    rig = env
    _user_row, account = await _bound_user(rig)
    rig.channels.stt = FailingSTT()
    outcome = await rig.channels.handle_inbound(
        inbound(rig, account, _voice(), now=rig.clock())
    )
    assert outcome.accepted is True
    assert outcome.reply_text == "这条语音我没转出来，能打字或再说一遍吗？"
    assert _attachment_count(rig, outcome.session_id) >= 1  # 音频保存成功不参与判据
    await rig.drain_runs()
    assert rig.runtime.execute_count == 0


async def test_successful_transcript_submits_text(env) -> None:
    rig = env
    _user_row, account = await _bound_user(rig)
    rig.channels.stt = FixedSTT()
    outcome = await rig.channels.handle_inbound(
        inbound(rig, account, _voice(), now=rig.clock())
    )
    assert outcome.accepted is True
    assert "我没转出来" not in (outcome.reply_text or "")
    await rig.drain_runs()
    assert rig.runtime.execute_count == 1
    assert rig.runtime.requests[0].text == "今晚九点提醒我交周报"


async def test_voice_plus_text_uses_text_when_transcript_fails(env) -> None:
    rig = env
    _user_row, account = await _bound_user(rig)
    rig.channels.stt = FailingSTT()
    outcome = await rig.channels.handle_inbound(
        inbound(rig, account, _voice_with_text(), now=rig.clock())
    )
    assert outcome.accepted is True
    assert "我没转出来" not in (outcome.reply_text or "")
    await rig.drain_runs()
    assert rig.runtime.execute_count == 1
    assert rig.runtime.requests[0].text == "语音听不清，我打字说"


async def test_voice_plus_image_still_processes_image_when_transcript_fails(env) -> None:
    rig = env
    _user_row, account = await _bound_user(rig)
    rig.channels.stt = FailingSTT()
    outcome = await rig.channels.handle_inbound(
        inbound(rig, account, _voice_with_image(), now=rig.clock())
    )
    assert outcome.accepted is True
    assert "我没转出来" not in (outcome.reply_text or "")
    await rig.drain_runs()
    assert rig.runtime.execute_count == 1
    assert rig.runtime.requests[0].attachment_ids
