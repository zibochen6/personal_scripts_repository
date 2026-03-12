"""Global configuration defaults for the video subtitle extractor CLI."""

from __future__ import annotations

OUTPUT_DIR = "./output"

SUBTITLE_LANG_PRIORITY = ["zh-Hans", "zh-CN", "zh", "en", "en-US", "ja"]

INCLUDE_TIMESTAMPS = False

MAX_CONCURRENT = 5

YTDLP_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "writesubtitles": True,
    "writeautomaticsub": True,
}

BILIBILI_SESSDATA = ""

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def build_bilibili_headers(sessdata: str = BILIBILI_SESSDATA) -> dict[str, str]:
    """Build headers required by Bilibili Web APIs."""

    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Referer": "https://www.bilibili.com",
        "Accept": "application/json",
    }
    if sessdata:
        headers["Cookie"] = f"SESSDATA={sessdata}"
    return headers


BILIBILI_HEADERS = build_bilibili_headers()
