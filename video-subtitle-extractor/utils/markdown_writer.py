"""Write extracted subtitle results to Markdown files."""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone

from extractor.base import VideoResult
from utils.sanitizer import sanitize_filename

_WRITE_LOCK = threading.Lock()


def write_markdown(result: VideoResult, output_dir: str) -> str:
    """Write one ``VideoResult`` to a unique UTF-8 Markdown file."""

    os.makedirs(output_dir, exist_ok=True)
    safe_title = sanitize_filename(result.title)
    platform_name = "YouTube" if result.platform == "youtube" else "Bilibili"
    extracted_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    content = (
        f"# {result.title}\n\n"
        f"> **平台**：{platform_name}  \n"
        f"> **链接**：[原始链接]({result.url})  \n"
        f"> **字幕语言**：{result.language}  \n"
        f"> **提取时间**：{extracted_at}\n\n"
        "---\n\n"
        f"{result.subtitle_text.strip()}\n\n"
        "---\n"
    )

    with _WRITE_LOCK:
        file_path = _build_unique_path(output_dir, safe_title)
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(content)
    return file_path


def _build_unique_path(output_dir: str, safe_title: str) -> str:
    """Build a unique Markdown path by appending numeric suffixes if needed."""

    base_path = os.path.join(output_dir, f"{safe_title}.md")
    if not os.path.exists(base_path):
        return base_path

    counter = 1
    while True:
        candidate = os.path.join(output_dir, f"{safe_title}_{counter}.md")
        if not os.path.exists(candidate):
            return candidate
        counter += 1
