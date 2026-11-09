"""语音：SILK/大小降级、云端协议、本地不可用、渠道转写接入。"""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from backend.integrations.speech import (
    AutoSTT,
    OpenAICompatibleSTT,
    SpeechError,
    Transcript,
    build_stt,
)
from backend.modules.channels.contracts import InboundMessage, MediaRef
from tests.support.wechat import make_channel_rig


def _settings(**kwargs):
    from backend.platform.settings import default_settings

    return default_settings().__class__(
        data_db_path=Path("data/app.db"), state_db_path=Path("data/state.db"),
        artifacts_dir=Path("data/artifacts"), **kwargs,
    )


@pytest.mark.asyncio
async def test_cloud_stt_posts_audio_and_parses_text(tmp_path) -> None:
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFFfake")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"text": "明天提醒我交周报", "language": "zh"})

    stt = OpenAICompatibleSTT(
        base_url="http://stt.local/v1", api_key="sk-test",
        transport=httpx.MockTransport(handler),
    )
    result = await stt.transcribe(audio, "audio/wav")
    assert result.text == "明天提醒我交周报"
    assert seen["url"].endswith("/audio/transcriptions")
    assert seen["auth"] == "Bearer sk-test"


@pytest.mark.asyncio
async def test_silk_fails_without_decoder(tmp_path) -> None:
    audio = tmp_path / "a.silk"
    audio.write_bytes(b"#!SILK_V3" + b"\x00" * 20)
    stt = OpenAICompatibleSTT(base_url="http://x", api_key="k")
    with pytest.raises(SpeechError, match="SILK"):
        await stt.transcribe(audio, "audio/silk")


@pytest.mark.asyncio
async def test_oversize_rejected_before_network(tmp_path) -> None:
    audio = tmp_path / "big.ogg"
    audio.write_bytes(b"x" * (20 * 1024 * 1024 + 1))
    stt = OpenAICompatibleSTT(base_url="http://x", api_key="k")
    with pytest.raises(SpeechError, match="20 MB"):
        await stt.transcribe(audio, "audio/ogg")


@pytest.mark.asyncio
async def test_auto_falls_back_to_second_provider(tmp_path) -> None:
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF")

    class Bad:
        async def transcribe(self, path, mime):
            raise SpeechError("云端失败")

    class Good:
        async def transcribe(self, path, mime):
            return Transcript("本地成功", "zh", None)

    result = await AutoSTT([Bad(), Good()]).transcribe(audio, "audio/wav")
    assert result.text == "本地成功"


def test_build_stt_off_returns_none() -> None:
    assert build_stt(_settings(stt_provider="off"), None) is None


def test_build_stt_default_voice_disabled_does_not_touch_models() -> None:
    class BoomModels:
        def select_for_run(self, **kwargs):
            raise AssertionError("关闭语音时不得读取模型配置")

    assert build_stt(_settings(), BoomModels()) is None


def test_voice_enabled_environment_flag(monkeypatch) -> None:
    from backend.platform.settings import settings_from_environment

    monkeypatch.setenv("EASYCHAT_VOICE_ENABLED", "true")
    assert settings_from_environment().voice_enabled is True
    monkeypatch.delenv("EASYCHAT_VOICE_ENABLED")
    assert settings_from_environment().voice_enabled is False


@pytest.mark.asyncio
async def test_channel_transcribes_voice_before_saving(tmp_path) -> None:
    rig, _transport, _fetcher = make_channel_rig(tmp_path)
    user = rig.seed_user(grants=("chat.use",))
    session = await rig.seed_session(user, source="wechat", external_chat_id="c1")

    class FakeSTT:
        async def transcribe(self, path, mime):
            return Transcript("帮我看看这个", "zh", 0.9)

    rig.channels.stt = FakeSTT()
    message = InboundMessage(
        platform="wechat", account_pk="a", external_account_id="bot",
        external_user_id="wx_ext_1", external_chat_id="c1",
        external_event_id="msg:voice-1",
        media=(MediaRef(kind="voice", file_name="v.ogg", url="https://example.invalid/v"),),
    )
    result = await rig.channels._ingest_media(user, session, "evt-1", message)
    assert result.transcripts == ("帮我看看这个",)
    assert len(result.attachment_ids) == 1
