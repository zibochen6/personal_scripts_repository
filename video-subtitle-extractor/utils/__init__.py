"""Shared utility helpers for subtitle formatting and retry logic."""

from __future__ import annotations

import re
import time
from html import unescape
from typing import Callable, TypeVar

T = TypeVar("T")


def format_timestamp(seconds: float) -> str:
    """Convert seconds to ``HH:MM:SS`` or ``MM:SS`` display format."""

    total_seconds = max(int(seconds), 0)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    remaining_seconds = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"
    return f"{minutes:02d}:{remaining_seconds:02d}"


def clean_subtitle_text(text: str) -> str:
    """Normalize subtitle text, remove tags, and collapse noisy repeats."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"<[^>]+>", "", normalized)
    normalized = unescape(normalized)

    raw_lines = [line.strip() for line in normalized.split("\n")]
    deduplicated: list[str] = []
    for line in raw_lines:
        if not line:
            if deduplicated and deduplicated[-1] != "":
                deduplicated.append("")
            continue
        if deduplicated and deduplicated[-1] == line:
            continue
        deduplicated.append(line)

    merged: list[str] = []
    for line in deduplicated:
        if not line:
            if merged and merged[-1] != "":
                merged.append("")
            continue
        if merged and _should_merge_with_previous(merged[-1], line):
            merged[-1] = f"{merged[-1]} {line}".strip()
        else:
            merged.append(line)

    result = "\n".join(merged)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def retry(
    func: Callable[[], T],
    retries: int = 3,
    delay: float = 2.0,
    operation_name: str = "operation",
) -> T:
    """Retry a callable a few times before re-raising the last exception."""

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return func()
        except Exception as exc:  # pragma: no cover - retry behavior is timing-dependent
            last_error = exc
            if attempt >= retries:
                break
            print(f"⚠️ {operation_name}失败，第 {attempt} 次重试后继续：{exc}")
            time.sleep(delay)
    if last_error is None:  # pragma: no cover - defensive branch
        raise RuntimeError(f"{operation_name}失败，但没有捕获到异常信息。")
    raise last_error


def _should_merge_with_previous(previous: str, current: str) -> bool:
    """Merge fragmented transcript lines into a more natural paragraph."""

    if not previous or previous.startswith("[") or current.startswith("["):
        return False
    if re.search(r"[。！？!?\.]$", previous):
        return False
    if re.match(r"^[a-z0-9\u4e00-\u9fff]", current):
        return True
    return False


__all__ = ["format_timestamp", "clean_subtitle_text", "retry"]
