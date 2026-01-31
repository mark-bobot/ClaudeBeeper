"""Parse Claude Code stats and session data for ClaudeWatch."""

import glob
import json
import os
from datetime import datetime, timedelta

CLAUDE_DIR = os.path.expanduser("~/.claude")
STATS_PATH = os.path.join(CLAUDE_DIR, "stats-cache.json")
PROJECTS_DIR = os.path.join(CLAUDE_DIR, "projects")

# mtime-based cache
_cache = {
    "stats_mtime": 0,
    "stats_data": None,
    "session_path": None,
    "session_mtime": 0,
    "session_data": None,
}


def _current_week_bounds():
    """Return (monday, sunday) date strings for the current ISO week."""
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()


def _format_tokens(n):
    """Format a token count for display (e.g. 1234567 -> '1.2M')."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _friendly_model_name(model_id):
    """Convert a model ID to a friendly display name."""
    mapping = {
        "claude-opus-4-5-20251101": "Opus 4.5",
        "claude-sonnet-4-5-20250929": "Sonnet 4.5",
        "claude-haiku-4-5-20251001": "Haiku 4.5",
    }
    for key, name in mapping.items():
        if key in model_id:
            return name
    return model_id


def get_weekly_stats():
    """Return weekly usage stats from stats-cache.json.

    Returns dict with keys: messages, sessions, tool_calls, tokens_by_model.
    Uses mtime caching.
    """
    result = {
        "messages": 0,
        "sessions": 0,
        "tool_calls": 0,
        "tokens_by_model": {},
    }

    try:
        mtime = os.path.getmtime(STATS_PATH)
    except OSError:
        return result

    if mtime == _cache["stats_mtime"] and _cache["stats_data"] is not None:
        return _cache["stats_data"]

    try:
        with open(STATS_PATH, "r") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return result

    mon, sun = _current_week_bounds()

    for day in data.get("dailyActivity", []):
        d = day.get("date", "")
        if mon <= d <= sun:
            result["messages"] += day.get("messageCount", 0)
            result["sessions"] += day.get("sessionCount", 0)
            result["tool_calls"] += day.get("toolCallCount", 0)

    for day in data.get("dailyModelTokens", []):
        d = day.get("date", "")
        if mon <= d <= sun:
            for model, count in day.get("tokensByModel", {}).items():
                friendly = _friendly_model_name(model)
                result["tokens_by_model"][friendly] = (
                    result["tokens_by_model"].get(friendly, 0) + count
                )

    _cache["stats_mtime"] = mtime
    _cache["stats_data"] = result
    return result


def _find_latest_session():
    """Find the most recently modified session across all projects.

    Returns (session_entry, jsonl_path) or (None, None).
    """
    best_entry = None
    best_mtime = 0
    best_path = None

    pattern = os.path.join(PROJECTS_DIR, "*/sessions-index.json")
    for index_path in glob.glob(pattern):
        try:
            with open(index_path, "r") as f:
                index = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue

        for entry in index.get("entries", []):
            mtime = entry.get("fileMtime", 0)
            if mtime > best_mtime:
                jsonl_path = entry.get("fullPath", "")
                if os.path.isfile(jsonl_path):
                    best_mtime = mtime
                    best_entry = entry
                    best_path = jsonl_path

    return best_entry, best_path


def get_session_stats():
    """Return current (latest) session stats.

    Returns dict with keys: summary, messages, duration, input_tokens,
    output_tokens, cache_read, cache_create, session_id.
    Uses mtime caching.
    """
    result = {
        "summary": "No active session",
        "messages": 0,
        "duration": "0s",
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read": 0,
        "cache_create": 0,
        "session_id": None,
    }

    entry, jsonl_path = _find_latest_session()
    if entry is None or jsonl_path is None:
        return result

    try:
        mtime = os.path.getmtime(jsonl_path)
    except OSError:
        return result

    if (
        jsonl_path == _cache["session_path"]
        and mtime == _cache["session_mtime"]
        and _cache["session_data"] is not None
    ):
        return _cache["session_data"]

    result["summary"] = entry.get("summary", "") or entry.get("firstPrompt", "")[:50]
    result["session_id"] = entry.get("sessionId", "")

    # Parse timestamps for duration
    created = entry.get("created")
    modified = entry.get("modified")
    if created and modified:
        try:
            t0 = datetime.fromisoformat(created.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(modified.replace("Z", "+00:00"))
            delta = t1 - t0
            total_secs = int(delta.total_seconds())
            if total_secs >= 3600:
                h = total_secs // 3600
                m = (total_secs % 3600) // 60
                s = total_secs % 60
                result["duration"] = f"{h}h {m}m {s}s"
            elif total_secs >= 60:
                m = total_secs // 60
                s = total_secs % 60
                result["duration"] = f"{m}m {s}s"
            else:
                result["duration"] = f"{total_secs}s"
        except (ValueError, TypeError):
            pass

    # Parse JSONL for token counts — deduplicate by requestId
    seen_request_ids = set()
    msg_count = 0

    try:
        with open(jsonl_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                obj_type = obj.get("type")

                if obj_type == "user" and not obj.get("isMeta"):
                    msg = obj.get("message", {})
                    if msg.get("role") == "user":
                        content = msg.get("content", "")
                        # Only count real user messages (not tool results)
                        if isinstance(content, str) and content:
                            msg_count += 1

                if obj_type == "assistant":
                    msg = obj.get("message", {})
                    usage = msg.get("usage", {})
                    req_id = obj.get("requestId", "")

                    if req_id and req_id in seen_request_ids:
                        continue
                    if req_id:
                        seen_request_ids.add(req_id)

                    result["input_tokens"] += usage.get("input_tokens", 0)
                    result["output_tokens"] += usage.get("output_tokens", 0)
                    result["cache_read"] += usage.get("cache_read_input_tokens", 0)
                    result["cache_create"] += usage.get(
                        "cache_creation_input_tokens", 0
                    )
    except OSError:
        pass

    result["messages"] = msg_count

    _cache["session_path"] = jsonl_path
    _cache["session_mtime"] = mtime
    _cache["session_data"] = result
    return result
