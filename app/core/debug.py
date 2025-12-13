"""Shared debug logging utility."""

import json
import time
from pathlib import Path


def debug_log(location: str, message: str, data: dict, hypothesis_id: str = "A"):
    """Helper to safely write debug logs.

    Args:
        location: Source location identifier (e.g., "main.py:22")
        message: Log message
        data: Additional data to log
        hypothesis_id: Hypothesis identifier for debugging sessions
    """
    try:
        log_path = Path(".cursor/debug.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps({
                "timestamp": int(time.time() * 1000),
                "location": location,
                "message": message,
                "data": data,
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": hypothesis_id
            }) + "\n")
    except Exception:
        pass  # Silently fail if logging isn't possible
