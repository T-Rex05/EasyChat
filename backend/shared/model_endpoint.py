"""OpenAI-compatible base URL for chat, including self-hosted servers."""
import re
from urllib.parse import urlsplit


def model_base_url(base_url: str, provider: str) -> str:
    url = base_url.strip().rstrip("/")
    if not url or "anthropic" in provider.lower() or "anthropic" in url.lower():
        return url
    if url.endswith("/chat/completions"):
        return url.removesuffix("/chat/completions")
    # Preserve the existing /v1 default for unversioned gateway prefixes.
    path = urlsplit(url).path
    return url if re.search(r"/v[0-9]+(?:/|$)", path) else url + "/v1"
