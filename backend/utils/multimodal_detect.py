"""多模态模型检测工具 — 三层策略

Layer 1 — 静态名称规则（即时，零开销，有漏判/误判风险）
Layer 2 — 厂商元数据接口（暂未实现，预留位置）
Layer 3 — 图片探测预检（权威判定，缓存 7 天）
"""

import re
import time
import hashlib
import base64
import urllib.request
import urllib.error
import json as _json
import ssl
from typing import Optional, Tuple

# ══════════════════════════════════════════════════════
# Layer 1 — 静态名称规则
# ══════════════════════════════════════════════════════

# 通用多模态关键词（高置信度，跨厂商通用）
_GENERIC_MULTIMODAL = [
    r"\bvl\b",          # 视觉语言模型标识
    r"\bvision\b",      # vision
    r"\bomni\b",        # omni（GPT-4o 全模态）
    r"\bmultimodal\b",  # 显式声明多模态
]

# 已知多模态模型模式（厂商特定）
_VENDOR_MULTIMODAL = [
    # OpenAI
    r"gpt-4o",              # gpt-4o, gpt-4o-mini
    r"gpt-4.*turbo",        # gpt-4-turbo
    r"o1",                  # o1, o1-mini, o1-pro
    r"o3",                  # o3, o3-mini
    # Anthropic Claude 3+
    r"claude-[3-9]",        # claude-3/3.5/4 全部多模态
    # Google Gemini（绝大多数版本支持图片）
    r"gemini-",             # 所有 Gemini 模型
    # 通义千问
    r"qwen3",               # qwen3 系列（全部多模态）
    r"qwen2?\.5",           # qwen2.5 系列（含多模态）
    # 月之暗面 Kimi
    r"kimi",                # kimi 系列全部支持多模态
    r"moonshot.*v",         # moonshot-v
    # 国产模型
    r"glm-4v",              # 智谱 GLM-4V
    r"glm-5",               # 智谱 GLM-5（支持多模态）
    r"cogview",             # 智谱 CogView
    r"cogvlm",
    r"internvl",            # InternVL
    r"minicpm.*v",          # MiniCPM-V
    r"yi.*vision",
    r"step.*vision",
    r"hunyuan.*vision",
    r"hunyuan.*vl",
    r"ernie-4",             # 文心 4.0
    r"ernie.*vl",
    r"doubao.*vision",
    # 海外模型
    r"llama.*vision",
    r"llava",
    r"bakllava",
    r"pixtral",
    r"phi.*vision",
    r"phi-[34].*v",
    r"molmo",
    r"paligemma",
    r"fuyu",
    r"idefics",
    r"video",               # 视频理解模型
]

# 纯文本模型排除规则（命中 任一 则判定为非多模态，优先级高于多模态规则）
_NON_MULTIMODAL = [
    r"\bcoder\b",           # deepseek-coder 等
    r"\bcode\b",            # code 系列
    r"\btext\b",            # text-embedding, text-moderation 等
    r"instruct[-_]?text",  # instruct-text 纯文本
    r"gpt-3\.5",            # GPT-3.5
    r"text-davinci",
    r"text-embedding",
    r"whisper",
    r"tts-",
    r"dall-e",
    r"davinci",
    r"babbage",
    r"curie",
    r"ada\b",
    r"moderation",
    r"rerank",
    r"sentence",            # sentence-transformers 等
]

# 编译正则
_GENERIC_COMPILED = [re.compile(p, re.IGNORECASE) for p in _GENERIC_MULTIMODAL]
_VENDOR_COMPILED = [re.compile(p, re.IGNORECASE) for p in _VENDOR_MULTIMODAL]
_NON_COMPILED = [re.compile(p, re.IGNORECASE) for p in _NON_MULTIMODAL]


def is_multimodal_model(model_name: str) -> bool:
    """Layer 1 — 静态名称规则判定。

    返回值仅供参考，不能作为最终权威判定。
    """
    if not model_name or not isinstance(model_name, str):
        return False
    name = model_name.strip().lower()
    if not name:
        return False

    # 纯文本排除规则优先
    for p in _NON_COMPILED:
        if p.search(name):
            return False

    # 通用多模态关键词
    for p in _GENERIC_COMPILED:
        if p.search(name):
            return True

    # 厂商特定模式
    for p in _VENDOR_COMPILED:
        if p.search(name):
            return True

    return False


# ══════════════════════════════════════════════════════
# Layer 2 — 厂商元数据接口（待实现）
# ══════════════════════════════════════════════════════
# TODO: 调用服务商模型元信息接口，读取 vision/multimodal 字段


# ══════════════════════════════════════════════════════
# Layer 3 — 图片探测预检（权威判定）
# ══════════════════════════════════════════════════════

# 极简 1x1 白色 PNG（84 字节）
_MINI_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJ"
    "RU5ErkJggg=="
)

# 探测缓存（进程内存，key = sha256(model_name + api_key)）
_IMAGE_PROBE_CACHE: dict = {}
_PROBE_CACHE_TTL = 7 * 24 * 3600  # 7 天


def _probe_cache_key(model_name: str, api_url: str, api_key: str) -> str:
    raw = f"{model_name}|{api_url}|{api_key}"
    return hashlib.sha256(raw.encode()).hexdigest()


def probe_image_support(
    api_url: str,
    api_key: str,
    model_name: str,
    timeout: int = 20,
) -> Tuple[Optional[bool], str]:
    """Layer 3 — 图片探测预检。

    发送一张极小测试图片，根据响应判定模型是否支持图片输入。

    Returns:
        (is_multimodal, detail_message)
        is_multimodal=True   — 探测通过，支持图片
        is_multimodal=False  — 探测不通过，纯文本模型
        is_multimodal=None   — 探测无结论，应回退到静态规则检测
    """
    # 检查缓存
    cache_key = _probe_cache_key(model_name, api_url, api_key)
    cached = _IMAGE_PROBE_CACHE.get(cache_key)
    if cached:
        ts, result = cached
        if time.time() - ts < _PROBE_CACHE_TTL:
            return result
        # 过期，删除
        del _IMAGE_PROBE_CACHE[cache_key]

    # 构造请求体：发送图片 + 短文本，极低 max_tokens
    image_url = f"data:image/png;base64,{_MINI_PNG_BASE64}"
    body = {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": "What color is this? Answer with one word."},
                ],
            }
        ],
        "max_tokens": 5,
        "temperature": 0,
    }

    url = api_url.rstrip("/")
    # Anthropic 端点走 /v1/messages
    if "/anthropic" in url:
        if not url.endswith("/v1/messages") and not url.endswith("/messages"):
            url = f"{url}/v1/messages"
    else:
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["x-api-key"] = api_key

    method = "POST"
    data = _json.dumps(body).encode()
    import ssl
    ctx = ssl.create_default_context() if hasattr(ssl, "create_default_context") else None

    try:
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            # 200 → 多模态
            result = (True, "支持图片识别（探测通过）")
            _IMAGE_PROBE_CACHE[cache_key] = (time.time(), result)
            return result
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace").lower()
        # 400 + 提示仅文本 → 纯文本
        if e.code == 400:
            text_only_indicators = [
                "only text", "text only", "does not support image",
                "doesn't support image", "does not support media",
                "not supported", "invalid content type", "no image",
                "不支持图片", "不支持图像", "不支持媒体",
                "仅支持文本", "纯文本", "text-only",
                "unsupported", "multimodal content is not supported",
            ]
            if any(indicator in detail for indicator in text_only_indicators):
                result = (False, "纯文本模型（图片探测被拒绝）")
                _IMAGE_PROBE_CACHE[cache_key] = (time.time(), result)
                return result
            # 其他 400（格式不兼容/反序列化失败等）→ 无结论，回退静态规则
            result = (None, f"图片探测因 API 格式不兼容未能判定，回退静态规则")
            return result
        # 404 / 403 → 模型支持但账号无权限
        if e.code in (404, 403):
            result = (False, f"探测返回 HTTP {e.code}，模型可能支持但账号无权限")
            _IMAGE_PROBE_CACHE[cache_key] = (time.time(), result)
            return result
        result = (None, f"图片探测返回 HTTP {e.code}，无法判定")
        return result
    except Exception as e:
        result = (None, f"图片探测请求异常，无法判定: {e}")
        return result


def check_model_multimodal(model_config: dict) -> bool:
    """检查模型配置是否支持多模态。显式标记优先，名称匹配兜底。"""
    if not model_config:
        return False
    if model_config.get("is_multimodal"):
        return True
    return is_multimodal_model(model_config.get("model_name", ""))
