"""Alert system for ClaudeWatch — sound + red screen flash."""

import time
import threading

from AppKit import (
    NSSound,
    NSWindow,
    NSColor,
    NSScreen,
    NSBorderlessWindowMask,
    NSApplication,
)
from Quartz import CGShieldingWindowLevel


def _play_beeps(volume=1.0, count=3, gap=0.25):
    """Play system Ping sound `count` times with `gap` seconds between."""
    for i in range(count):
        sound = NSSound.soundNamed_("Ping")
        if sound:
            sound.setVolume_(volume)
            sound.play()
            # Wait for sound to finish or gap
            time.sleep(gap)
            sound.stop()


def _flash_screens(count=3, on_ms=150, off_ms=100, alpha=0.35):
    """Flash all screens red. Must be called on the main thread."""
    screens = NSScreen.screens()
    windows = []

    for screen in screens:
        frame = screen.frame()
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            NSBorderlessWindowMask,
            2,  # NSBackingStoreBuffered
            False,
        )
        win.setLevel_(CGShieldingWindowLevel() + 1)
        win.setBackgroundColor_(NSColor.redColor().colorWithAlphaComponent_(alpha))
        win.setOpaque_(False)
        win.setIgnoresMouseEvents_(True)
        win.setCollectionBehavior_(1 << 0 | 1 << 1)  # canJoinAllSpaces | fullScreen
        windows.append(win)

    for i in range(count):
        for win in windows:
            win.orderFrontRegardless()
        time.sleep(on_ms / 1000.0)
        for win in windows:
            win.orderOut_(None)
        if i < count - 1:
            time.sleep(off_ms / 1000.0)

    for win in windows:
        win.close()


def trigger_alert(volume=1.0, sound_enabled=True, flash_enabled=True):
    """Fire the full alert (sound + flash). Safe to call from any thread."""
    if sound_enabled:
        threading.Thread(target=_play_beeps, args=(volume,), daemon=True).start()

    if flash_enabled:
        # Flash must run on main thread for NSWindow operations
        from PyObjCTools import AppHelper

        AppHelper.callAfter(_flash_screens)
