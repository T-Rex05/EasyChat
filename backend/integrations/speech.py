"""语音转写适配：云端 OpenAI 兼容优先，本地 faster-whisper 可选。

真实音频不写入日志；未安装/未配置时明确不可用，不自动下载模型。
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import NamedTuple, Protocol

import httpx

logger = logging.getLogger(__name__)

MAX_AUDIO_SECONDS = 300
MAX_AUDIO_BYTES = 20 * 1024 * 1024
SILK_MAGIC = b"#!SILK_V3"


class Transcript(NamedTuple):
    text: str
    language: str
    confidence: float | None


class SpeechError(RuntimeError):
    """可向用户展示的语音失败。"""


class SpeechToText(Protocol):
    async def transcribe(self, path: Path, mime: str) -> Transcript: ...


def _is_silk(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(len(SILK_MAGIC)) == SILK_MAGIC
    except OSError:
        return False


def _duration_seconds(path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        output = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return float(output.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _to_wav(path: Path) -> Path | None:
    """有 ffmpeg 时转 16k 单声道 WAV；失败回退原文件。"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    fd, name = tempfile.mkstemp(suffix=".wav")
    os.close(fd)  # mkstemp 返回的 fd 必须关闭，否则每次语音泄漏一个句柄
    target = Path(name)
    try:
        result = subprocess.run(
            [ffmpeg, "-y", "-i", str(path), "-ar", "16000", "-ac", "1", str(target)],
            capture_output=True, timeout=30, check=False,
        )
        if result.returncode == 0 and target.stat().st_size > 0:
            return target
    except (OSError, subprocess.SubprocessError):
        pass
    target.unlink(missing_ok=True)
    return None


class OpenAICompatibleSTT:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str = "whisper-1",
        language: str = "zh",
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.language = language
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def transcribe(self, path: Path, mime: str) -> Transcript:
        # ffprobe/ffmpeg 是阻塞子进程，不能卡住渠道事件循环。
        await asyncio.to_thread(self._check, path)
        converted = await asyncio.to_thread(_to_wav, path)
        upload = converted or path
        try:
            data = await asyncio.to_thread(upload.read_bytes)
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = await client.post(
                    self.base_url + "/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files={"file": (upload.name, data, mime or "application/octet-stream")},
                    data={
                        "model": self.model,
                        "language": self.language,
                        "response_format": "json",
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            raise SpeechError("语音服务暂时不可用") from exc
        except (OSError, ValueError) as exc:
            raise SpeechError("语音文件读取失败") from exc
        finally:
            if converted is not None:
                converted.unlink(missing_ok=True)
        text = str(payload.get("text") or "").strip()
        if not text:
            raise SpeechError("没有识别出文字")
        return Transcript(text=text, language=str(payload.get("language") or self.language),
                          confidence=payload.get("confidence"))

    @staticmethod
    def _check(path: Path) -> None:
        if not path.exists():
            raise SpeechError("语音文件不存在")
        if path.stat().st_size > MAX_AUDIO_BYTES:
            raise SpeechError("语音超过 20 MB，先压缩或分段再发")
        if _is_silk(path):
            # 没有 SILK 解码器时不把二进制丢给云端模型
            raise SpeechError("这条语音是 SILK 格式，当前设备无法解码")
        duration = _duration_seconds(path)
        if duration is not None and duration > MAX_AUDIO_SECONDS:
            raise SpeechError("语音超过 5 分钟，先分段再发")


class LocalFasterWhisperSTT:
    def __init__(self, *, model: str = "small", language: str = "zh") -> None:
        try:
            from faster_whisper import WhisperModel  # type: ignore[import-not-found]
        except ImportError as exc:
            raise SpeechError("本地语音模型未安装") from exc
        # 只使用已下载的模型，绝不在收消息时隐式联网下载。
        self._model = WhisperModel(
            model, device="cpu", compute_type="int8", local_files_only=True
        )
        self.language = language

    async def transcribe(self, path: Path, mime: str) -> Transcript:
        OpenAICompatibleSTT._check(path)

        def _run() -> Transcript:
            segments, info = self._model.transcribe(
                str(path), language=self.language, vad_filter=True
            )
            text = "".join(segment.text for segment in segments).strip()
            if not text:
                raise SpeechError("没有识别出文字")
            return Transcript(text, str(info.language or self.language), None)

        return await asyncio.to_thread(_run)


class AutoSTT:
    def __init__(self, providers: list[SpeechToText]) -> None:
        self.providers = providers

    async def transcribe(self, path: Path, mime: str) -> Transcript:
        errors = []
        for provider in self.providers:
            try:
                return await provider.transcribe(path, mime)
            except SpeechError as exc:
                errors.append(str(exc))
        raise SpeechError(errors[-1] if errors else "语音转写不可用")


def build_stt(settings, models) -> SpeechToText | None:
    # 总开关关闭时不得读取模型配置或导入/加载本地模型。
    if not bool(getattr(settings, "voice_enabled", False)):
        return None
    provider = str(settings.stt_provider or "auto").lower()
    if provider == "off":
        return None
    providers: list[SpeechToText] = []
    if provider in ("auto", "openai") and models is not None:
        try:
            selection = models.select_for_run(auxiliary=True)
            profile = selection.chat
            api_key = models.resolve_api_key(profile.config_id)
            if (
                profile.provider.lower() in (
                    "openai", "openai-compatible", "deepseek", "custom"
                )
                and profile.base_url and api_key
            ):
                providers.append(OpenAICompatibleSTT(
                    base_url=profile.base_url,
                    api_key=api_key,
                    model=settings.stt_model,
                    language=settings.stt_language,
                    timeout_seconds=settings.stt_timeout_seconds,
                ))
        except Exception:  # noqa: BLE001  没模型配置就尝试本地
            logger.info("未找到可用的云端 STT 配置")
    if provider in ("auto", "local"):
        try:
            providers.append(LocalFasterWhisperSTT(
                model=settings.stt_model_local, language=settings.stt_language
            ))
        except Exception:  # noqa: BLE001  本地模型缺失/下载失败不能阻塞启动
            logger.info("本地 faster-whisper 不可用", exc_info=True)
    return AutoSTT(providers) if providers else None
