"""CLI entry point for batch video subtitle extraction."""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Sequence

import config
from extractor.bilibili_extractor import BilibiliExtractor
from extractor.youtube_extractor import YouTubeExtractor
from utils.markdown_writer import write_markdown
from utils.url_parser import Platform, parse_url


def configure_console_output() -> None:
    """Configure console streams so emoji progress logs do not fail on Windows."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                continue


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description="批量提取 YouTube / Bilibili 视频字幕并保存为 Markdown 文件。"
    )
    parser.add_argument("urls", nargs="*", help="一个或多个视频 URL。")
    parser.add_argument("-f", "--file", help="从文本文件中读取 URL，每行一个。")
    parser.add_argument("-i", "--interactive", action="store_true", help="交互式粘贴 URL，输入空行结束。")
    parser.add_argument(
        "-o",
        "--output",
        default=config.OUTPUT_DIR,
        help=f"输出目录，默认 {config.OUTPUT_DIR}",
    )
    parser.add_argument(
        "-t",
        "--timestamps",
        action="store_true",
        help="在字幕文本中保留时间戳。",
    )
    parser.add_argument(
        "-l",
        "--lang",
        default=",".join(config.SUBTITLE_LANG_PRIORITY),
        help="字幕语言优先级，逗号分隔，如 zh-CN,en。",
    )
    parser.add_argument(
        "-c",
        "--concurrent",
        type=int,
        default=config.MAX_CONCURRENT,
        help=f"并发数量，默认 {config.MAX_CONCURRENT}",
    )
    parser.add_argument(
        "--cookie",
        default=config.BILIBILI_SESSDATA,
        help="Bilibili 的 SESSDATA Cookie 值。",
    )
    return parser.parse_args(argv)


def collect_urls(args: argparse.Namespace) -> list[str]:
    """Collect URLs from CLI arguments, file input, and interactive mode."""

    urls: list[str] = [item.strip() for item in args.urls if item.strip()]

    if args.file:
        file_path = Path(args.file)
        with file_path.open("r", encoding="utf-8") as file:
            for line in file:
                candidate = line.strip()
                if candidate:
                    urls.append(candidate)

    if args.interactive:
        print("⏳ 请输入视频 URL，每行一个，输入空行结束：")
        while True:
            try:
                line = input().strip()
            except EOFError:
                break
            if not line:
                break
            urls.append(line)

    deduplicated = list(dict.fromkeys(urls))
    if not deduplicated:
        raise ValueError("请至少提供一个视频 URL，或使用 -f / -i 输入。")
    return deduplicated


def parse_language_priority(raw_value: str) -> list[str]:
    """Parse a comma-separated language preference string."""

    languages = [item.strip() for item in raw_value.split(",") if item.strip()]
    if not languages:
        return list(config.SUBTITLE_LANG_PRIORITY)
    return languages


def process_url(
    url: str,
    output_dir: str,
    subtitle_lang_priority: Sequence[str],
    include_timestamps: bool,
    sessdata: str,
) -> tuple[str, str, str]:
    """Process one URL and return ``(url, file_path, title)``."""

    platform, video_id = parse_url(url)
    if platform == Platform.YOUTUBE:
        extractor = YouTubeExtractor(
            subtitle_lang_priority=subtitle_lang_priority,
            include_timestamps=include_timestamps,
        )
    else:
        extractor = BilibiliExtractor(
            subtitle_lang_priority=subtitle_lang_priority,
            include_timestamps=include_timestamps,
            sessdata=sessdata,
        )

    result = extractor.extract(video_id, url)
    file_path = write_markdown(result, output_dir)
    return url, file_path, result.title


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""

    configure_console_output()
    args = parse_args(argv)
    try:
        urls = collect_urls(args)
    except Exception as exc:
        print(f"❌ {exc}")
        return 1

    subtitle_lang_priority = parse_language_priority(args.lang)
    max_workers = max(1, args.concurrent)

    print(f"⏳ 共检测到 {len(urls)} 个唯一链接，准备开始处理...")
    print(f"⏳ 输出目录：{args.output}")
    print(f"⏳ 并发数量：{max_workers}")

    results: list[tuple[str, str]] = []
    errors: list[tuple[str, str]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(
                process_url,
                url,
                args.output,
                subtitle_lang_priority,
                args.timestamps,
                args.cookie,
            ): url
            for url in urls
        }

        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                _, file_path, title = future.result()
                results.append((url, file_path))
                print(f"✅ {title} -> {file_path}")
            except Exception as exc:
                errors.append((url, str(exc)))
                print(f"❌ {url}: {exc}")

    print(f"\n完成: {len(results)} 成功, {len(errors)} 失败")
    if errors:
        print("失败列表:")
        for url, error in errors:
            print(f"  - {url}: {error}")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
