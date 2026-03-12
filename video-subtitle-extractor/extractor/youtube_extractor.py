"""YouTube subtitle extraction implementation."""

from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from typing import Any, Iterable, Sequence

from config import INCLUDE_TIMESTAMPS, SUBTITLE_LANG_PRIORITY, YTDLP_OPTS
from extractor.base import BaseExtractor, VideoResult
from utils import clean_subtitle_text, format_timestamp, retry

try:
    import httpx
except ImportError:  # pragma: no cover - depends on runtime environment
    httpx = None

try:
    import yt_dlp
except ImportError:  # pragma: no cover - depends on runtime environment
    yt_dlp = None

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:  # pragma: no cover - depends on runtime environment
    YouTubeTranscriptApi = None


class SubtitleUnavailableError(RuntimeError):
    """Raised when a video does not expose usable subtitles."""


def _raise_missing_dependency(name: str) -> None:
    """Raise a consistent installation hint for missing dependencies."""

    raise RuntimeError(
        f"缺少第三方依赖 `{name}`，请先运行 `pip install -r requirements.txt`。"
    )


class YouTubeExtractor(BaseExtractor):
    """Extract titles and subtitles from YouTube videos."""

    def __init__(
        self,
        subtitle_lang_priority: Sequence[str] | None = None,
        include_timestamps: bool = INCLUDE_TIMESTAMPS,
    ) -> None:
        """Store runtime options for subtitle extraction."""

        self.subtitle_lang_priority = list(subtitle_lang_priority or SUBTITLE_LANG_PRIORITY)
        self.include_timestamps = include_timestamps

    def extract(self, video_id: str, url: str) -> VideoResult:
        """Extract a single YouTube video's title and subtitle text."""

        title = self.get_title(video_id)
        language, subtitle_text = self.get_subtitle(video_id)
        return VideoResult(
            video_id=video_id,
            title=title,
            subtitle_text=subtitle_text,
            platform="youtube",
            language=language,
            url=url,
        )

    def get_title(self, video_id: str) -> str:
        """Fetch the YouTube title through ``yt-dlp`` metadata extraction."""

        self._ensure_yt_dlp()
        options = dict(YTDLP_OPTS)
        options.update({"skip_download": True})
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        with yt_dlp.YoutubeDL(options) as downloader:
            info = retry(
                lambda: downloader.extract_info(video_url, download=False),
                operation_name="获取 YouTube 视频标题",
            )
        title = (info or {}).get("title")
        if not title:
            raise RuntimeError(f"无法获取 YouTube 视频标题: {video_id}")
        return str(title)

    def get_subtitle(self, video_id: str) -> tuple[str, str]:
        """Try transcript API first, then fall back to subtitle URLs from ``yt-dlp``."""

        transcript_error: Exception | None = None
        try:
            return self._get_subtitle_via_transcript_api(video_id)
        except SubtitleUnavailableError as exc:
            transcript_error = exc
        except Exception as exc:  # pragma: no cover - depends on remote responses
            transcript_error = exc

        try:
            return self._get_subtitle_via_ytdlp(video_id)
        except SubtitleUnavailableError:
            return ("unavailable", "⚠️ 该视频没有可用的字幕内容")
        except Exception as exc:
            if self._is_missing_dependency_error(exc):
                raise
            if transcript_error is not None and self._is_missing_dependency_error(transcript_error):
                raise transcript_error
            raise RuntimeError(
                f"YouTube 字幕提取失败（Transcript API: {transcript_error}; yt-dlp: {exc}）"
            ) from exc

    def _get_subtitle_via_transcript_api(self, video_id: str) -> tuple[str, str]:
        """Use ``youtube-transcript-api`` for fast transcript extraction."""

        if YouTubeTranscriptApi is None:
            raise RuntimeError("缺少第三方依赖 `youtube-transcript-api`，请先运行 `pip install -r requirements.txt`。")

        transcripts = retry(
            lambda: YouTubeTranscriptApi.list_transcripts(video_id),
            operation_name="列出 YouTube 字幕",
        )
        transcript_entries = list(transcripts)
        if not transcript_entries:
            raise SubtitleUnavailableError("该视频没有可用字幕")

        selected = self._pick_best_transcript(transcript_entries)
        translated_language: str | None = None

        if selected is None:
            translated_language = self.subtitle_lang_priority[0] if self.subtitle_lang_priority else "zh-Hans"
            source = self._pick_translatable_transcript(transcript_entries)
            if source is None or not getattr(source, "is_translatable", False):
                raise SubtitleUnavailableError("该视频没有可用字幕")
            try:
                selected = source.translate(translated_language)
            except Exception as exc:  # pragma: no cover - depends on remote responses
                raise SubtitleUnavailableError("无法翻译现有字幕") from exc

        try:
            transcript_items = selected.fetch()
        except Exception as exc:  # pragma: no cover - depends on remote responses
            if self._is_transcript_missing_error(exc):
                raise SubtitleUnavailableError("该视频没有可用字幕") from exc
            raise

        language_code = translated_language or str(getattr(selected, "language_code", "unknown"))
        return language_code, self._transcript_items_to_text(transcript_items)

    def _get_subtitle_via_ytdlp(self, video_id: str) -> tuple[str, str]:
        """Use subtitle metadata exposed by ``yt-dlp`` as a fallback path."""

        self._ensure_yt_dlp()
        self._ensure_httpx()

        options = dict(YTDLP_OPTS)
        options.update(
            {
                "subtitleslangs": self.subtitle_lang_priority,
                "skip_download": True,
            }
        )
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        with yt_dlp.YoutubeDL(options) as downloader:
            info = retry(
                lambda: downloader.extract_info(video_url, download=False),
                operation_name="通过 yt-dlp 获取 YouTube 字幕信息",
            )

        subtitles = (info or {}).get("subtitles") or {}
        automatic_captions = (info or {}).get("automatic_captions") or {}
        candidate = self._pick_best_subtitle_candidate(subtitles, automatic_captions)
        if candidate is None:
            raise SubtitleUnavailableError("该视频没有可用字幕")

        response = retry(
            lambda: httpx.get(candidate["url"], timeout=30.0, follow_redirects=True),
            operation_name="下载 YouTube 字幕文件",
        )
        response.raise_for_status()
        text = self._parse_subtitle_payload(response.text, candidate["format"])
        return candidate["language"], text

    def _pick_best_transcript(self, transcripts: Sequence[Any]) -> Any | None:
        """Choose the best transcript by language priority and manual-vs-auto preference."""

        for preferred in self.subtitle_lang_priority:
            manual_matches = [
                item
                for item in transcripts
                if not getattr(item, "is_generated", False)
                and self._language_matches(str(getattr(item, "language_code", "")), preferred)
            ]
            if manual_matches:
                return manual_matches[0]
            generated_matches = [
                item
                for item in transcripts
                if getattr(item, "is_generated", False)
                and self._language_matches(str(getattr(item, "language_code", "")), preferred)
            ]
            if generated_matches:
                return generated_matches[0]
        return None

    def _pick_translatable_transcript(self, transcripts: Sequence[Any]) -> Any | None:
        """Pick a fallback transcript that supports translation."""

        manual = [item for item in transcripts if not getattr(item, "is_generated", False)]
        generated = [item for item in transcripts if getattr(item, "is_generated", False)]
        for candidate in manual + generated:
            if getattr(candidate, "is_translatable", False):
                return candidate
        return (manual + generated)[0] if manual or generated else None

    def _transcript_items_to_text(self, items: Iterable[Any]) -> str:
        """Convert transcript items into cleaned plain text."""

        lines: list[str] = []
        for item in items:
            text = self._item_value(item, "text")
            if not text:
                continue
            start = float(self._item_value(item, "start", 0.0) or 0.0)
            line = html.unescape(str(text)).replace("\n", " ").strip()
            if not line:
                continue
            if self.include_timestamps:
                lines.append(f"[{format_timestamp(start)}] {line}")
            else:
                lines.append(line)
        result = "\n".join(lines).strip()
        return clean_subtitle_text(result) if result else "⚠️ 该视频没有可用的字幕内容"

    def _pick_best_subtitle_candidate(
        self,
        subtitles: dict[str, list[dict[str, Any]]],
        automatic_captions: dict[str, list[dict[str, Any]]],
    ) -> dict[str, str] | None:
        """Choose the best subtitle URL from ``yt-dlp`` metadata."""

        for language in self.subtitle_lang_priority:
            manual = self._pick_format_for_language(subtitles, language)
            if manual is not None:
                return manual
            automatic = self._pick_format_for_language(automatic_captions, language)
            if automatic is not None:
                return automatic
        return self._pick_any_candidate(subtitles) or self._pick_any_candidate(automatic_captions)

    def _pick_format_for_language(
        self,
        subtitle_map: dict[str, list[dict[str, Any]]],
        preferred_language: str,
    ) -> dict[str, str] | None:
        """Pick the best subtitle format for a specific preferred language."""

        for language_code, entries in subtitle_map.items():
            if not self._language_matches(language_code, preferred_language):
                continue
            selected_format = self._pick_best_format(entries)
            if selected_format is not None:
                return {"language": language_code, **selected_format}
        return None

    def _pick_any_candidate(
        self,
        subtitle_map: dict[str, list[dict[str, Any]]],
    ) -> dict[str, str] | None:
        """Pick the first available candidate when no preferred language exists."""

        for language_code, entries in subtitle_map.items():
            selected_format = self._pick_best_format(entries)
            if selected_format is not None:
                return {"language": language_code, **selected_format}
        return None

    def _pick_best_format(self, entries: Sequence[dict[str, Any]]) -> dict[str, str] | None:
        """Choose a preferred subtitle serialization format."""

        ordered_formats = ["srv3", "json3", "vtt", "ttml", "srv2", "srv1"]
        for subtitle_format in ordered_formats:
            for entry in entries:
                format_name = str(entry.get("ext") or entry.get("format_id") or "")
                if format_name != subtitle_format:
                    continue
                url = entry.get("url")
                if url:
                    return {"url": str(url), "format": subtitle_format}
        for entry in entries:
            url = entry.get("url")
            if url:
                format_name = str(entry.get("ext") or entry.get("format_id") or "unknown")
                return {"url": str(url), "format": format_name}
        return None

    def _parse_subtitle_payload(self, payload: str, subtitle_format: str) -> str:
        """Parse subtitle payloads returned by ``yt-dlp`` URLs."""

        subtitle_format = subtitle_format.lower()
        if subtitle_format in {"json3", "json"}:
            return self._parse_json3_payload(payload)
        if subtitle_format.startswith("srv") or subtitle_format in {"ttml", "xml"}:
            return self._parse_xml_payload(payload)
        if subtitle_format == "vtt":
            return self._parse_vtt_payload(payload)
        return clean_subtitle_text(payload)

    def _parse_json3_payload(self, payload: str) -> str:
        """Parse YouTube ``json3`` subtitle payloads."""

        data = json.loads(payload)
        lines: list[str] = []
        for event in data.get("events", []):
            segments = event.get("segs") or []
            text = "".join(segment.get("utf8", "") for segment in segments).strip()
            if not text:
                continue
            start_ms = float(event.get("tStartMs", 0.0) or 0.0)
            line = html.unescape(text).replace("\n", " ").strip()
            if self.include_timestamps:
                lines.append(f"[{format_timestamp(start_ms / 1000.0)}] {line}")
            else:
                lines.append(line)
        return clean_subtitle_text("\n".join(lines))

    def _parse_xml_payload(self, payload: str) -> str:
        """Parse XML subtitle payloads such as ``srv3`` or TTML."""

        root = ET.fromstring(payload)
        lines: list[str] = []
        for element in root.iter():
            tag_name = element.tag.split("}")[-1]
            if tag_name not in {"text", "p"}:
                continue
            text = "".join(element.itertext()).strip()
            if not text:
                continue
            text = html.unescape(text).replace("\n", " ").strip()
            start_seconds = self._extract_xml_start_time(element)
            if self.include_timestamps:
                lines.append(f"[{format_timestamp(start_seconds)}] {text}")
            else:
                lines.append(text)
        return clean_subtitle_text("\n".join(lines))

    def _parse_vtt_payload(self, payload: str) -> str:
        """Parse WebVTT subtitle text."""

        blocks = re.split(r"\n\s*\n", payload.replace("\r\n", "\n"))
        lines: list[str] = []
        for block in blocks:
            raw_lines = [line.strip() for line in block.splitlines() if line.strip()]
            if not raw_lines:
                continue
            if raw_lines[0].upper() == "WEBVTT":
                continue
            text_lines = raw_lines[:]
            timestamp = None
            if "-->" in raw_lines[0]:
                timestamp = raw_lines[0].split("-->", 1)[0].strip()
                text_lines = raw_lines[1:]
            elif len(raw_lines) > 1 and "-->" in raw_lines[1]:
                timestamp = raw_lines[1].split("-->", 1)[0].strip()
                text_lines = raw_lines[2:]
            text = " ".join(text_lines).strip()
            if not text:
                continue
            if self.include_timestamps and timestamp:
                timestamp_seconds = self._parse_vtt_timestamp(timestamp)
                lines.append(f"[{format_timestamp(timestamp_seconds)}] {text}")
            else:
                lines.append(text)
        return clean_subtitle_text("\n".join(lines))

    def _extract_xml_start_time(self, element: ET.Element) -> float:
        """Read a subtitle cue's start time from XML attributes."""

        if "start" in element.attrib:
            return float(element.attrib["start"])
        if "t" in element.attrib:
            return float(element.attrib["t"]) / 1000.0
        if "begin" in element.attrib:
            return self._parse_vtt_timestamp(element.attrib["begin"])
        return 0.0

    def _parse_vtt_timestamp(self, value: str) -> float:
        """Convert ``HH:MM:SS.mmm`` or ``MM:SS.mmm`` to seconds."""

        parts = value.replace(",", ".").split(":")
        if len(parts) == 3:
            hours, minutes, seconds = parts
        else:
            hours = "0"
            minutes, seconds = parts
        return (int(hours) * 3600) + (int(minutes) * 60) + float(seconds)

    def _language_matches(self, language_code: str, preferred_language: str) -> bool:
        """Match exact language codes or the same base locale."""

        normalized_code = language_code.lower()
        normalized_preferred = preferred_language.lower()
        if normalized_code == normalized_preferred:
            return True
        return normalized_code.split("-")[0] == normalized_preferred.split("-")[0]

    def _is_transcript_missing_error(self, exc: Exception) -> bool:
        """Check whether transcript API errors indicate unavailable captions."""

        error_name = exc.__class__.__name__
        return error_name in {
            "TranscriptsDisabled",
            "NoTranscriptFound",
            "VideoUnavailable",
            "NoTranscriptAvailable",
        }

    def _is_missing_dependency_error(self, exc: Exception) -> bool:
        """Detect dependency-related failures emitted by this module."""

        return "缺少第三方依赖" in str(exc)

    def _item_value(self, item: Any, key: str, default: Any = "") -> Any:
        """Read transcript item data from dict-like or object-like entries."""

        if isinstance(item, dict):
            return item.get(key, default)
        return getattr(item, key, default)

    def _ensure_httpx(self) -> None:
        """Ensure ``httpx`` is installed before network operations."""

        if httpx is None:
            _raise_missing_dependency("httpx")

    def _ensure_yt_dlp(self) -> None:
        """Ensure ``yt-dlp`` is installed before metadata extraction."""

        if yt_dlp is None:
            _raise_missing_dependency("yt-dlp")
