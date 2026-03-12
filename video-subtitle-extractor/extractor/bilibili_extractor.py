"""Bilibili subtitle extraction implementation."""

from __future__ import annotations

import json
import re
from typing import Any, Sequence

from config import (
    BILIBILI_SESSDATA,
    INCLUDE_TIMESTAMPS,
    SUBTITLE_LANG_PRIORITY,
    YTDLP_OPTS,
    build_bilibili_headers,
)
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


class SubtitleUnavailableError(RuntimeError):
    """Raised when Bilibili exposes no subtitles for a video."""


def _raise_missing_dependency(name: str) -> None:
    """Raise a consistent installation hint for missing dependencies."""

    raise RuntimeError(
        f"缺少第三方依赖 `{name}`，请先运行 `pip install -r requirements.txt`。"
    )


class BilibiliExtractor(BaseExtractor):
    """Extract titles and subtitles from Bilibili videos."""

    def __init__(
        self,
        subtitle_lang_priority: Sequence[str] | None = None,
        include_timestamps: bool = INCLUDE_TIMESTAMPS,
        sessdata: str = BILIBILI_SESSDATA,
    ) -> None:
        """Store runtime options and HTTP headers."""

        self.subtitle_lang_priority = list(subtitle_lang_priority or SUBTITLE_LANG_PRIORITY)
        self.include_timestamps = include_timestamps
        self.sessdata = sessdata
        self.headers = build_bilibili_headers(sessdata)

    def extract(self, video_id: str, url: str) -> VideoResult:
        """Extract a single Bilibili video's title and subtitle text."""

        title = self.get_title(video_id)
        language, subtitle_text = self.get_subtitle(video_id)
        return VideoResult(
            video_id=video_id,
            title=title,
            subtitle_text=subtitle_text,
            platform="bilibili",
            language=language,
            url=url,
        )

    def get_title(self, video_id: str) -> str:
        """Fetch the title from the Bilibili ``view`` API, with ``yt-dlp`` fallback."""

        try:
            data = self._get_view_data(video_id)
            title = data.get("title")
            if title:
                return str(title)
        except Exception:
            pass

        return self._get_title_via_ytdlp(video_id)

    def get_subtitle(self, video_id: str) -> tuple[str, str]:
        """Fetch subtitles from Bilibili Web APIs, with ``yt-dlp`` as a backup."""

        api_error: Exception | None = None
        try:
            return self._get_subtitle_via_api(video_id)
        except Exception as exc:
            api_error = exc

        try:
            return self._get_subtitle_via_ytdlp(video_id)
        except SubtitleUnavailableError:
            if isinstance(api_error, SubtitleUnavailableError):
                return ("unavailable", "⚠️ 该视频没有可用的字幕内容")
            if api_error is not None and self._looks_like_auth_error(str(api_error)):
                raise RuntimeError(str(api_error))
            if api_error is not None:
                raise RuntimeError(str(api_error)) from api_error
            return ("unavailable", "⚠️ 该视频没有可用的字幕内容")
        except Exception as exc:
            if api_error is not None and "缺少第三方依赖" in str(api_error):
                raise api_error
            raise RuntimeError(
                f"Bilibili 字幕提取失败（API: {api_error}; yt-dlp: {exc}）"
            ) from exc

    def _get_view_data(self, video_id: str) -> dict[str, Any]:
        """Load video metadata from the Bilibili ``view`` API."""

        self._ensure_httpx()
        params = self._build_video_params(video_id)
        response = retry(
            lambda: httpx.get(
                "https://api.bilibili.com/x/web-interface/view",
                params=params,
                headers=self.headers,
                timeout=30.0,
            ),
            operation_name="请求 Bilibili 视频信息",
        )
        response.raise_for_status()
        payload = response.json()
        self._raise_for_bilibili_error(payload, action="获取视频信息")
        data = payload.get("data") or {}
        if not data:
            raise RuntimeError(f"无法获取 Bilibili 视频信息: {video_id}")
        return data

    def _get_subtitle_via_api(self, video_id: str) -> tuple[str, str]:
        """Fetch subtitles through Bilibili's documented Web API flow."""

        view_data = self._get_view_data(video_id)
        cid = view_data.get("cid")
        if not cid:
            pages = view_data.get("pages") or []
            if pages:
                cid = pages[0].get("cid")
        if not cid:
            raise RuntimeError(f"无法获取 Bilibili 视频 CID: {video_id}")

        params = self._build_video_params(video_id)
        params["cid"] = cid
        response = retry(
            lambda: httpx.get(
                "https://api.bilibili.com/x/player/wbi/v2",
                params=params,
                headers=self.headers,
                timeout=30.0,
            ),
            operation_name="请求 Bilibili 字幕列表",
        )
        response.raise_for_status()
        payload = response.json()
        self._raise_for_bilibili_error(payload, action="获取字幕列表")

        subtitle_data = ((payload.get("data") or {}).get("subtitle") or {}).get("subtitles") or []
        if not subtitle_data:
            raise SubtitleUnavailableError("该视频没有可用的字幕内容")

        selected = self._pick_best_subtitle(subtitle_data)
        subtitle_url = str(selected.get("subtitle_url", ""))
        if not subtitle_url:
            raise SubtitleUnavailableError("该视频没有可用的字幕内容")
        if subtitle_url.startswith("//"):
            subtitle_url = f"https:{subtitle_url}"

        subtitle_response = retry(
            lambda: httpx.get(subtitle_url, headers=self.headers, timeout=30.0),
            operation_name="下载 Bilibili 字幕文件",
        )
        subtitle_response.raise_for_status()
        subtitle_payload = subtitle_response.json()
        return str(selected.get("lan", "unknown")), self._parse_bilibili_subtitle_body(
            subtitle_payload.get("body") or []
        )

    def _get_title_via_ytdlp(self, video_id: str) -> str:
        """Fallback title lookup via ``yt-dlp``."""

        self._ensure_yt_dlp()
        options = dict(YTDLP_OPTS)
        options.update({"skip_download": True})
        video_url = self._build_video_url(video_id)
        with yt_dlp.YoutubeDL(options) as downloader:
            info = retry(
                lambda: downloader.extract_info(video_url, download=False),
                operation_name="通过 yt-dlp 获取 Bilibili 标题",
            )
        title = (info or {}).get("title")
        if not title:
            raise RuntimeError(f"无法获取 Bilibili 视频标题: {video_id}")
        return str(title)

    def _get_subtitle_via_ytdlp(self, video_id: str) -> tuple[str, str]:
        """Fallback subtitle extraction through ``yt-dlp`` metadata URLs."""

        self._ensure_yt_dlp()
        self._ensure_httpx()

        options = dict(YTDLP_OPTS)
        options.update(
            {
                "subtitleslangs": self.subtitle_lang_priority,
                "skip_download": True,
            }
        )
        video_url = self._build_video_url(video_id)
        with yt_dlp.YoutubeDL(options) as downloader:
            info = retry(
                lambda: downloader.extract_info(video_url, download=False),
                operation_name="通过 yt-dlp 获取 Bilibili 字幕信息",
            )

        subtitles = (info or {}).get("subtitles") or {}
        candidate = self._pick_best_ytdlp_subtitle(subtitles)
        if candidate is None:
            raise SubtitleUnavailableError("该视频没有可用的字幕内容")

        response = retry(
            lambda: httpx.get(candidate["url"], headers=self.headers, timeout=30.0, follow_redirects=True),
            operation_name="通过 yt-dlp 下载 Bilibili 字幕文件",
        )
        response.raise_for_status()
        return candidate["language"], self._parse_generic_subtitle_payload(
            response.text,
            candidate["format"],
        )

    def _parse_bilibili_subtitle_body(self, body: Sequence[dict[str, Any]]) -> str:
        """Convert Bilibili subtitle JSON ``body`` items to cleaned text."""

        lines: list[str] = []
        for item in body:
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            start = float(item.get("from", 0.0) or 0.0)
            if self.include_timestamps:
                lines.append(f"[{format_timestamp(start)}] {content}")
            else:
                lines.append(content)
        text = clean_subtitle_text("\n".join(lines))
        return text or "⚠️ 该视频没有可用的字幕内容"

    def _pick_best_subtitle(self, subtitles: Sequence[dict[str, Any]]) -> dict[str, Any]:
        """Pick the best Bilibili subtitle entry by language preference."""

        for preferred in self.subtitle_lang_priority:
            for subtitle in subtitles:
                language = str(subtitle.get("lan", ""))
                if self._language_matches(language, preferred):
                    return subtitle
        return subtitles[0]

    def _pick_best_ytdlp_subtitle(
        self,
        subtitles: dict[str, list[dict[str, Any]]],
    ) -> dict[str, str] | None:
        """Pick the best ``yt-dlp`` subtitle candidate for Bilibili."""

        for preferred in self.subtitle_lang_priority:
            for language, entries in subtitles.items():
                if not self._language_matches(language, preferred):
                    continue
                selected = self._pick_best_format(entries)
                if selected:
                    return {"language": language, **selected}
        for language, entries in subtitles.items():
            selected = self._pick_best_format(entries)
            if selected:
                return {"language": language, **selected}
        return None

    def _pick_best_format(self, entries: Sequence[dict[str, Any]]) -> dict[str, str] | None:
        """Choose the most useful subtitle serialization format."""

        for preferred in ("json", "json3", "vtt", "srt"):
            for entry in entries:
                format_name = str(entry.get("ext") or entry.get("format_id") or "")
                if format_name != preferred:
                    continue
                url = entry.get("url")
                if url:
                    return {"url": str(url), "format": format_name}
        for entry in entries:
            url = entry.get("url")
            if url:
                return {
                    "url": str(url),
                    "format": str(entry.get("ext") or entry.get("format_id") or "unknown"),
                }
        return None

    def _parse_generic_subtitle_payload(self, payload: str, subtitle_format: str) -> str:
        """Parse fallback subtitle payloads exposed via ``yt-dlp``."""

        subtitle_format = subtitle_format.lower()
        if subtitle_format in {"json", "json3"}:
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                return clean_subtitle_text(payload)
            body = data.get("body")
            if isinstance(body, list):
                return self._parse_bilibili_subtitle_body(body)
            events = data.get("events")
            if isinstance(events, list):
                lines: list[str] = []
                for event in events:
                    segments = event.get("segs") or []
                    text = "".join(segment.get("utf8", "") for segment in segments).strip()
                    if not text:
                        continue
                    start = float(event.get("tStartMs", 0.0) or 0.0) / 1000.0
                    if self.include_timestamps:
                        lines.append(f"[{format_timestamp(start)}] {text}")
                    else:
                        lines.append(text)
                return clean_subtitle_text("\n".join(lines))
            return clean_subtitle_text(payload)
        if subtitle_format == "vtt":
            return self._parse_vtt(payload)
        if subtitle_format == "srt":
            return self._parse_srt(payload)
        return clean_subtitle_text(payload)

    def _parse_vtt(self, payload: str) -> str:
        """Parse WebVTT subtitles."""

        blocks = re.split(r"\n\s*\n", payload.replace("\r\n", "\n"))
        lines: list[str] = []
        for block in blocks:
            raw_lines = [line.strip() for line in block.splitlines() if line.strip()]
            if not raw_lines:
                continue
            if raw_lines[0].upper() == "WEBVTT":
                continue
            timestamp = None
            text_lines = raw_lines[:]
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
                lines.append(f"[{format_timestamp(self._parse_timestamp(timestamp))}] {text}")
            else:
                lines.append(text)
        return clean_subtitle_text("\n".join(lines))

    def _parse_srt(self, payload: str) -> str:
        """Parse SRT subtitles."""

        blocks = re.split(r"\n\s*\n", payload.replace("\r\n", "\n"))
        lines: list[str] = []
        for block in blocks:
            raw_lines = [line.strip() for line in block.splitlines() if line.strip()]
            if len(raw_lines) < 2:
                continue
            timestamp_line = raw_lines[1] if raw_lines[0].isdigit() and len(raw_lines) > 2 else raw_lines[0]
            text_lines = raw_lines[2:] if raw_lines[0].isdigit() and len(raw_lines) > 2 else raw_lines[1:]
            text = " ".join(text_lines).strip()
            if not text:
                continue
            if self.include_timestamps and "-->" in timestamp_line:
                start = timestamp_line.split("-->", 1)[0].strip()
                lines.append(f"[{format_timestamp(self._parse_timestamp(start))}] {text}")
            else:
                lines.append(text)
        return clean_subtitle_text("\n".join(lines))

    def _parse_timestamp(self, value: str) -> float:
        """Convert timestamp strings into seconds."""

        normalized = value.replace(",", ".")
        parts = normalized.split(":")
        if len(parts) == 3:
            hours, minutes, seconds = parts
        else:
            hours = "0"
            minutes, seconds = parts
        return (int(hours) * 3600) + (int(minutes) * 60) + float(seconds)

    def _build_video_params(self, video_id: str) -> dict[str, str | int]:
        """Build API parameters for ``bvid`` or ``aid`` identifiers."""

        if video_id.lower().startswith("av"):
            return {"aid": int(video_id[2:])}
        return {"bvid": video_id}

    def _build_video_url(self, video_id: str) -> str:
        """Build a canonical Bilibili URL from the normalized video ID."""

        return f"https://www.bilibili.com/video/{video_id}"

    def _language_matches(self, language_code: str, preferred_language: str) -> bool:
        """Match exact language codes or their base locales."""

        normalized_code = language_code.lower()
        normalized_preferred = preferred_language.lower()
        if normalized_code == normalized_preferred:
            return True
        return normalized_code.split("-")[0] == normalized_preferred.split("-")[0]

    def _raise_for_bilibili_error(self, payload: dict[str, Any], action: str) -> None:
        """Raise informative errors for non-zero Bilibili API responses."""

        code = payload.get("code", 0)
        if code == 0:
            return
        message = str(payload.get("message") or payload.get("msg") or "未知错误")
        if self._looks_like_auth_error(message):
            raise RuntimeError(f"{action}失败：{message}。该内容可能需要登录，请通过 `--cookie` 提供 SESSDATA。")
        raise RuntimeError(f"{action}失败：{message} (code={code})")

    def _looks_like_auth_error(self, message: str) -> bool:
        """Detect permission/login related Bilibili API failures."""

        normalized = message.lower()
        keywords = ["登录", "会员", "权限", "限制", "forbidden", "login", "vip"]
        return any(keyword in normalized for keyword in keywords)

    def _ensure_httpx(self) -> None:
        """Ensure ``httpx`` is installed before HTTP requests."""

        if httpx is None:
            _raise_missing_dependency("httpx")

    def _ensure_yt_dlp(self) -> None:
        """Ensure ``yt-dlp`` is installed before metadata extraction."""

        if yt_dlp is None:
            _raise_missing_dependency("yt-dlp")
