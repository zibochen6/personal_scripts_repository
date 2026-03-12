"""URL parsing and platform detection helpers."""

from __future__ import annotations

import re
from enum import Enum
from urllib.parse import urljoin, urlparse

try:
    import httpx
except ImportError:  # pragma: no cover - depends on runtime environment
    httpx = None


class Platform(Enum):
    """Supported video platforms."""

    YOUTUBE = "youtube"
    BILIBILI = "bilibili"


YOUTUBE_PATTERN = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)([\w-]{11})",
    re.IGNORECASE,
)
BILIBILI_PATTERN = re.compile(
    r"bilibili\.com/video/((?:BV[\w]+)|(?:av\d+))",
    re.IGNORECASE,
)


def parse_url(url: str) -> tuple[Platform, str]:
    """Parse a raw URL and return ``(platform, normalized_video_id)``."""

    normalized_url = url.strip()
    if not normalized_url:
        raise ValueError("URL 不能为空。")

    youtube_match = YOUTUBE_PATTERN.search(normalized_url)
    if youtube_match:
        return Platform.YOUTUBE, youtube_match.group(1)

    bilibili_match = BILIBILI_PATTERN.search(normalized_url)
    if bilibili_match:
        return Platform.BILIBILI, bilibili_match.group(1)

    parsed = urlparse(normalized_url)
    hostname = (parsed.hostname or "").lower()
    if hostname == "b23.tv" or hostname.endswith(".b23.tv"):
        resolved_url = _resolve_b23_url(normalized_url)
        bilibili_match = BILIBILI_PATTERN.search(resolved_url)
        if bilibili_match:
            return Platform.BILIBILI, bilibili_match.group(1)
        raise ValueError(f"无法从 b23.tv 短链解析出 Bilibili 视频 URL: {url}")

    raise ValueError(f"无法识别的视频链接: {url}")


def _resolve_b23_url(url: str) -> str:
    """Resolve a ``b23.tv`` short link into its redirected Bilibili URL."""

    if httpx is None:
        raise RuntimeError("缺少第三方依赖 `httpx`，请先运行 `pip install -r requirements.txt`。")

    try:
        response = httpx.head(url, timeout=15.0, follow_redirects=False)
        location = response.headers.get("Location") or response.headers.get("location")
        if location:
            return urljoin(url, location)
        if response.status_code not in {405, 403}:
            response.raise_for_status()
    except httpx.HTTPError:
        pass

    response = httpx.get(url, timeout=15.0, follow_redirects=True)
    response.raise_for_status()
    return str(response.url)
