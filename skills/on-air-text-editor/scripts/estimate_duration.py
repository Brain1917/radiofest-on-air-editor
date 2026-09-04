#!/usr/bin/env python3
"""Estimate spoken duration from Russian or mixed-language plain text."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

WORD_PATTERN = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+(?:[-'][0-9A-Za-zА-Яа-яЁё]+)*")


def count_words(text: str) -> int:
    """Count readable word-like tokens in plain text."""
    return len(WORD_PATTERN.findall(text))


def estimate_seconds(word_count: int, words_per_minute: float) -> int:
    """Return a conservative whole-second estimate."""
    if words_per_minute <= 0:
        raise ValueError("Темп должен быть больше нуля.")
    return math.ceil(word_count * 60 / words_per_minute)


def format_duration(seconds: int) -> str:
    """Format seconds as MM:SS."""
    minutes, remainder = divmod(seconds, 60)
    return f"{minutes:02d}:{remainder:02d}"


def read_input(text: str | None, file_path: Path | None) -> str:
    """Read text from exactly one CLI input source."""
    if text is not None:
        return text
    if file_path is None:
        raise ValueError("Передайте --text или --file.")
    if not file_path.is_file():
        raise ValueError(f"Файл не найден: {file_path}")
    return file_path.read_text(encoding="utf-8")


def build_result(
    text: str,
    words_per_minute: float,
    limit_seconds: int | None,
) -> dict[str, int | float | str | bool | None]:
    """Build a JSON-serializable duration result."""
    word_count = count_words(text)
    duration = estimate_seconds(word_count, words_per_minute)
    over_limit = None if limit_seconds is None else max(0, duration - limit_seconds)
    fits = None if limit_seconds is None else duration <= limit_seconds
    return {
        "word_count": word_count,
        "words_per_minute": words_per_minute,
        "estimated_seconds": duration,
        "estimated_mm_ss": format_duration(duration),
        "limit_seconds": limit_seconds,
        "fits_limit": fits,
        "over_limit_seconds": over_limit,
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="Текст для подсчёта.")
    source.add_argument("--file", type=Path, help="UTF-8 файл с чистым эфирным текстом.")
    parser.add_argument("--wpm", type=float, required=True, help="Темп ведущего в словах в минуту.")
    parser.add_argument("--limit-seconds", type=int, help="Лимит слота в секундах.")
    return parser.parse_args()


def main() -> int:
    """Run the duration estimator CLI."""
    args = parse_args()
    try:
        if args.limit_seconds is not None and args.limit_seconds <= 0:
            raise ValueError("Лимит должен быть больше нуля.")
        text = read_input(args.text, args.file)
        result = build_result(text, args.wpm, args.limit_seconds)
    except (OSError, UnicodeError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
