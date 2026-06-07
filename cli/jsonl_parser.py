"""Shared JSONL parsing and formatting helpers."""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from typing import TextIO


@dataclass(slots=True)
class ParsedEvent:
    """One parsed event extracted from a JSONL line."""

    ts: str
    text: str
    kind: str


def _extract_time(obj: dict) -> str:
    ts_str = obj.get("timestamp", "")
    if ts_str and isinstance(ts_str, str):
        try:
            dt = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            return dt.strftime("%H:%M:%S")
        except (ValueError, TypeError):
            pass
    return ""


def _collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def _truncate(text: str, n: int = 80) -> str:
    collapsed = _collapse_whitespace(text)
    if len(collapsed) <= n:
        return collapsed
    return collapsed[: n - 1] + "…"


def _short_tool_id(tool_id: str) -> str:
    if "_" in tool_id:
        return tool_id.split("_")[-1][:8]
    return tool_id[:8]


def parse_jsonl_line(line: str, prev_ts: str = "") -> list[ParsedEvent]:
    """Parse one JSONL line into zero or more logical events."""
    line = line.strip()
    if not line.startswith("{"):
        return []

    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return []

    ts = _extract_time(obj) or prev_ts
    t = obj.get("type", "")
    events: list[ParsedEvent] = []

    if t == "stream_event":
        se = obj.get("event", {})
        et = se.get("type", "")
        if et == "content_block_start":
            cb = se.get("content_block", {})
            if cb.get("type") == "tool_use":
                name = cb.get("name", "?")
                tool_id = cb.get("id", "")
                events.append(ParsedEvent(ts, f"{name} {_short_tool_id(tool_id)}", "tool"))
        elif et == "message_start":
            model = se.get("message", {}).get("model", "")
            if model:
                events.append(ParsedEvent(ts, f"model: {model}", "info"))

    elif t == "assistant":
        for content in obj.get("message", {}).get("content", []):
            ct = content.get("type", "")
            if ct == "text":
                text = content.get("text", "")
                if isinstance(text, str) and text.strip():
                    events.append(ParsedEvent(ts, text, "text"))
            elif ct == "tool_use":
                name = content.get("name", "?")
                tool_id = content.get("id", "")
                events.append(ParsedEvent(ts, f"{name} {_short_tool_id(tool_id)}", "tool"))

    elif t == "user":
        content = obj.get("message", {}).get("content", [])
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    result = item.get("content", "")
                    if isinstance(result, str) and result.strip():
                        events.append(ParsedEvent(ts, result, "info"))

    elif t == "system":
        subtype = obj.get("subtype", "")
        if subtype == "status":
            status = obj.get("status", "")
            if status:
                events.append(ParsedEvent(ts, f"status: {status}", "info"))
        elif subtype == "task_started":
            desc = obj.get("description", "")
            if desc:
                events.append(ParsedEvent(ts, desc, "task"))

    elif t == "result":
        subtype = obj.get("subtype", "")
        is_success = subtype == "success" and not obj.get("is_error", False)
        duration = obj.get("duration_ms", 0)
        cost = obj.get("total_cost_usd", 0)
        turns = obj.get("num_turns", 0)
        dur_str = f"{duration / 1000:.0f}s" if duration else "?"
        summary = f"Done  {dur_str}  {turns} turns  ${cost:.4f}"
        if is_success:
            events.append(ParsedEvent(ts, summary, "result"))
        else:
            events.append(ParsedEvent(ts, f"ERROR: {summary}", "error"))

        result_text = obj.get("result", "")
        if isinstance(result_text, str) and result_text:
            result_kind = "result_text" if is_success else "error_text"
            events.append(ParsedEvent(ts, result_text, result_kind))

    return events


def read_events(handle: TextIO, prev_ts: str = "") -> tuple[list[ParsedEvent], str]:
    """Read all remaining lines from a file handle into parsed events."""
    last_ts = prev_ts
    events: list[ParsedEvent] = []
    for line in handle:
        parsed = parse_jsonl_line(line, last_ts)
        for event in parsed:
            if event.ts:
                last_ts = event.ts
            events.append(event)
    return events, last_ts


def format_event_for_viewer(event: ParsedEvent) -> str | None:
    """Format one parsed event into a compact list-view line."""
    if event.kind == "result_text":
        return None

    ts = event.ts or " " * 8
    kind_mark = {
        "tool": "▷",
        "text": "✎",
        "result": "✓",
        "error": "✗",
        "task": "▶",
        "info": "·",
    }.get(event.kind, " ")
    return f"`{ts}` {kind_mark} {_truncate(event.text)}"


def format_event_for_stream(event: ParsedEvent) -> str | None:
    """Return the single-line text stream shown during `ds-cli run`."""
    if event.kind != "text":
        return None
    text = _collapse_whitespace(event.text)
    return text or None


def extract_result(jsonl_path: str) -> str | None:
    """Return the last successful result text from a JSONL file."""
    try:
        with open(jsonl_path, "r") as handle:
            last_result = None
            events, _ = read_events(handle)
            for event in events:
                if event.kind == "result_text":
                    last_result = event.text
            return last_result
    except FileNotFoundError:
        return None
