"""Abstract extractor definitions shared by all video platforms."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class VideoResult:
    """Structured result for a single extracted video."""

    video_id: str
    title: str
    subtitle_text: str
    platform: str
    language: str
    url: str


class BaseExtractor(ABC):
    """Base class for platform-specific subtitle extractors."""

    @abstractmethod
    def extract(self, video_id: str, url: str) -> VideoResult:
        """Extract the title and subtitle text for a single video."""

    @abstractmethod
    def get_title(self, video_id: str) -> str:
        """Fetch the video title for the given video identifier."""

    @abstractmethod
    def get_subtitle(self, video_id: str) -> tuple[str, str]:
        """Fetch subtitle text and return ``(language_code, subtitle_text)``."""
