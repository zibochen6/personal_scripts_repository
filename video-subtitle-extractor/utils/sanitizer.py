"""Filename sanitization helpers."""

from __future__ import annotations

import re
from datetime import datetime


def sanitize_filename(title: str) -> str:
    """Convert a video title into a safe filename while preserving Unicode text."""

    cleaned = re.sub(r'[\\/*?:"<>|]', "_", title or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = re.sub(r"\s*_\s*", "_", cleaned)
    cleaned = cleaned.strip(" ._")

    if not cleaned:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        cleaned = f"untitled_{timestamp}"

    if len(cleaned) > 200:
        cleaned = cleaned[:200].rstrip(" ._")

    return cleaned or "untitled"
