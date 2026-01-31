#!/usr/bin/env python3
"""Lightweight hook script for Claude Code hooks.

Called by Claude Code on Stop (response finishes) and Notification
(permission prompts, alerts) events. Reads JSON from stdin and forwards
it to ClaudeWatch via Unix socket at /tmp/claudewatch.sock.

All exceptions are caught silently so this never blocks Claude Code.
"""

import json
import socket
import sys

SOCK_PATH = "/tmp/claudewatch.sock"
TIMEOUT = 3  # seconds (under hook's 5-second limit)


def main():
    try:
        data = sys.stdin.read()
        # Validate it's JSON
        json.loads(data)

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        sock.connect(SOCK_PATH)
        sock.sendall(data.encode("utf-8"))
        sock.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
