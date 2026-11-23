#!/usr/bin/env python3
"""Convert a Telegram Desktop JSON export (result.json) into daily Markdown notes."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any


class ExportError(Exception):
    """Raised when the export file is missing or malformed."""


def load_export(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ExportError(f"file not found: {path}")
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ExportError(f"bad JSON in {path}: line {exc.lineno}, col {exc.colno}") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise ExportError(f"cannot read {path}: {exc}") from None
    if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
        raise ExportError("unexpected structure: expected an object with a 'messages' list")
    return data


def flatten_text(text: Any) -> str:
    """Telegram stores text either as a plain string or as a list of strings/entities."""
    if isinstance(text, str):
        return text
    if isinstance(text, list):
        parts: list[str] = []
        for part in text:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "".join(parts)
    return ""


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {value!r}") from None


def collect_notes(
    messages: list[Any], since: date | None, tag: str | None
) -> dict[date, list[tuple[datetime, str]]]:
    notes: dict[date, list[tuple[datetime, str]]] = defaultdict(list)
    needle = f"#{tag.lstrip('#').lower()}" if tag else None
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("type") != "message":
            continue
        try:
            stamp = datetime.fromisoformat(str(msg.get("date", "")))
        except ValueError:
            continue
        text = flatten_text(msg.get("text")).strip()
        if not text:
            continue
        if since and stamp.date() < since:
            continue
        if needle and needle not in text.lower():
            continue
        notes[stamp.date()].append((stamp, text))
    return notes


def render_day(day: date, items: list[tuple[datetime, str]], chat: str) -> str:
    lines = [f"# {day.isoformat()}", "", f"_from: {chat}_", ""]
    for stamp, text in sorted(items, key=lambda item: item[0]):
        lines.append(f"## {stamp.strftime('%H:%M')}")
        lines.append("")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def write_notes(notes: dict[date, list[tuple[datetime, str]]], out_dir: Path, chat: str) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    for day, items in sorted(notes.items()):
        (out_dir / f"{day.isoformat()}.md").write_text(render_day(day, items, chat), encoding="utf-8")
    return len(notes)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram JSON export -> Markdown notes by day")
    parser.add_argument("--input", "-i", type=Path, default=Path("result.json"),
                        help="path to result.json (default: ./result.json)")
    parser.add_argument("--output-dir", "-o", type=Path, default=Path("notes"),
                        help="where to put YYYY-MM-DD.md files (default: ./notes)")
    parser.add_argument("--since", type=parse_date, help="skip messages before YYYY-MM-DD")
    parser.add_argument("--tag", help="keep only messages containing #tag")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        data = load_export(args.input)
        notes = collect_notes(data["messages"], args.since, args.tag)
        count = write_notes(notes, args.output_dir, str(data.get("name") or "Saved Messages"))
    except ExportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: cannot write notes: {exc}", file=sys.stderr)
        return 1
    total = sum(len(items) for items in notes.values())
    print(f"wrote {total} notes into {count} files in {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
