#!/usr/bin/env python3
"""ClaudeWatch — macOS menu bar app for Claude Code alerts & usage."""

import json
import os
import socket
import threading
import time
from datetime import datetime

import rumps

import alert
import config
import usage

SOCK_PATH = "/tmp/claudewatch.sock"


class ClaudeWatchApp(rumps.App):
    def __init__(self):
        self.cfg = config.load()
        icon_title = "\U0001f515" if self.cfg.get("muted") else "\U0001f514"
        super().__init__(icon_title, quit_button=None)

        self.last_alert_time = None
        self._build_menu()
        self._start_ipc_listener()

    # ── Menu Construction ──────────────────────────────────────────────

    def _build_menu(self):
        """Build the full menu from scratch."""
        self.menu.clear()

        weekly = usage.get_weekly_stats()
        session = usage.get_session_stats()

        # Weekly Usage submenu
        weekly_menu = rumps.MenuItem("Weekly Usage")
        weekly_menu.add(rumps.MenuItem(
            f"Messages: {weekly['messages']:,}", callback=None
        ))
        weekly_menu.add(rumps.MenuItem(
            f"Sessions: {weekly['sessions']:,}", callback=None
        ))
        weekly_menu.add(rumps.MenuItem(
            f"Tool Calls: {weekly['tool_calls']:,}", callback=None
        ))
        weekly_menu.add(rumps.separator)
        weekly_menu.add(rumps.MenuItem("Tokens by Model:", callback=None))
        if weekly["tokens_by_model"]:
            for model, count in sorted(
                weekly["tokens_by_model"].items(), key=lambda x: -x[1]
            ):
                weekly_menu.add(rumps.MenuItem(
                    f"  {model}: {usage._format_tokens(count)}", callback=None
                ))
        else:
            weekly_menu.add(rumps.MenuItem("  (none this week)", callback=None))

        self.menu.add(weekly_menu)
        self.menu.add(rumps.separator)

        # Current Session submenu
        session_menu = rumps.MenuItem("Current Session")
        summary = session["summary"]
        if len(summary) > 40:
            summary = summary[:37] + "..."
        session_menu.add(rumps.MenuItem(f"Summary: {summary}", callback=None))
        session_menu.add(rumps.MenuItem(
            f"Messages: {session['messages']:,}", callback=None
        ))
        session_menu.add(rumps.MenuItem(
            f"Duration: {session['duration']}", callback=None
        ))
        session_menu.add(rumps.separator)
        session_menu.add(rumps.MenuItem(
            f"Input: {usage._format_tokens(session['input_tokens'])}", callback=None
        ))
        session_menu.add(rumps.MenuItem(
            f"Output: {usage._format_tokens(session['output_tokens'])}", callback=None
        ))
        session_menu.add(rumps.MenuItem(
            f"Cache Read: {usage._format_tokens(session['cache_read'])}", callback=None
        ))
        session_menu.add(rumps.MenuItem(
            f"Cache Create: {usage._format_tokens(session['cache_create'])}",
            callback=None,
        ))

        self.menu.add(session_menu)
        self.menu.add(rumps.separator)

        # Last Alert
        if self.last_alert_time:
            last_str = self.last_alert_time.strftime("%H:%M:%S")
        else:
            last_str = "None"
        self.menu.add(rumps.MenuItem(f"Last Alert: {last_str}", callback=None))
        self.menu.add(rumps.separator)

        # Toggle items
        sound_item = rumps.MenuItem(
            f"Sound: {'ON' if self.cfg['sound_enabled'] else 'OFF'}",
            callback=self._toggle_sound,
        )
        flash_item = rumps.MenuItem(
            f"Flash: {'ON' if self.cfg['flash_enabled'] else 'OFF'}",
            callback=self._toggle_flash,
        )
        mute_item = rumps.MenuItem(
            "Unmute All" if self.cfg["muted"] else "Mute All",
            callback=self._toggle_mute,
        )

        self.menu.add(sound_item)
        self.menu.add(flash_item)
        self.menu.add(mute_item)
        self.menu.add(rumps.separator)

        # Volume submenu
        volume_menu = rumps.MenuItem("Volume")
        for level in ("loud", "medium", "low"):
            prefix = "\u2713 " if self.cfg["volume"] == level else "  "
            item = rumps.MenuItem(
                f"{prefix}{level.capitalize()}",
                callback=lambda sender, lv=level: self._set_volume(lv),
            )
            volume_menu.add(item)
        self.menu.add(volume_menu)
        self.menu.add(rumps.separator)

        # Info & actions
        self.menu.add(rumps.MenuItem("Refreshes every 30s", callback=None))
        self.menu.add(rumps.MenuItem("Refresh Now", callback=self._refresh))
        self.menu.add(rumps.MenuItem("Test Alert", callback=self._test_alert))
        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("Quit ClaudeWatch", callback=self._quit))

    # ── Callbacks ──────────────────────────────────────────────────────

    def _toggle_sound(self, sender):
        self.cfg["sound_enabled"] = not self.cfg["sound_enabled"]
        config.save(self.cfg)
        self._build_menu()

    def _toggle_flash(self, sender):
        self.cfg["flash_enabled"] = not self.cfg["flash_enabled"]
        config.save(self.cfg)
        self._build_menu()

    def _toggle_mute(self, sender):
        self.cfg["muted"] = not self.cfg["muted"]
        config.save(self.cfg)
        self.title = "\U0001f515" if self.cfg["muted"] else "\U0001f514"
        self._build_menu()

    def _set_volume(self, level):
        self.cfg["volume"] = level
        config.save(self.cfg)
        self._build_menu()

    def _refresh(self, sender=None):
        # Invalidate usage caches
        usage._cache["stats_mtime"] = 0
        usage._cache["stats_data"] = None
        usage._cache["session_mtime"] = 0
        usage._cache["session_data"] = None
        self._build_menu()

    def _test_alert(self, sender):
        self._fire_alert()

    def _quit(self, sender):
        self._cleanup_socket()
        rumps.quit_application()

    # ── Alert Dispatch ─────────────────────────────────────────────────

    def _fire_alert(self):
        """Fire alert respecting mute and per-channel settings."""
        self.last_alert_time = datetime.now()

        if self.cfg.get("muted"):
            self._build_menu()
            return

        vol = config.get_volume_float(self.cfg)
        alert.trigger_alert(
            volume=vol,
            sound_enabled=self.cfg.get("sound_enabled", True),
            flash_enabled=self.cfg.get("flash_enabled", True),
        )
        self._build_menu()

    # ── IPC Listener ───────────────────────────────────────────────────

    def _start_ipc_listener(self):
        """Start a background thread listening on the Unix socket."""
        self._cleanup_socket()
        t = threading.Thread(target=self._ipc_loop, daemon=True)
        t.start()

    def _cleanup_socket(self):
        try:
            os.unlink(SOCK_PATH)
        except OSError:
            pass

    def _ipc_loop(self):
        """Accept connections on the Unix socket and fire alerts."""
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(SOCK_PATH)
        server.listen(5)
        # Make socket world-writable so hook can connect
        os.chmod(SOCK_PATH, 0o777)

        while True:
            try:
                conn, _ = server.accept()
                data = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                conn.close()

                if data:
                    # Dispatch alert to main thread via rumps timer trick
                    rumps.Timer(self._on_ipc_message, 0).start()
            except Exception:
                continue

    def _on_ipc_message(self, timer):
        """Called on main thread when IPC message received."""
        timer.stop()
        self._fire_alert()

    # ── Periodic Refresh ───────────────────────────────────────────────

    @rumps.timer(30)
    def _auto_refresh(self, sender):
        """Refresh usage stats every 30 seconds."""
        self._build_menu()


if __name__ == "__main__":
    ClaudeWatchApp().run()
