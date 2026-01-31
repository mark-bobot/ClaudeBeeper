#!/bin/bash
# ClaudeWatch uninstaller — removes LaunchAgent, hook config, and config dir.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
HOOK_SCRIPT="$SCRIPT_DIR/hook_notify.py"
PLIST_DST="$HOME/Library/LaunchAgents/com.claudewatch.plist"
SETTINGS="$HOME/.claude/settings.json"
SOCK_PATH="/tmp/claudewatch.sock"

echo "=== ClaudeWatch Uninstaller ==="
echo ""

# 1. Stop and remove LaunchAgent
echo "[1/3] Removing LaunchAgent..."
launchctl unload "$PLIST_DST" 2>/dev/null || true
rm -f "$PLIST_DST"
echo "  Done."

# 2. Remove Stop hook from Claude Code settings
echo "[2/3] Removing Claude Code Stop hook..."
if [ -f "$SETTINGS" ]; then
    python3 - "$SETTINGS" "$HOOK_SCRIPT" <<'PYEOF'
import json
import sys

settings_path = sys.argv[1]
hook_script = sys.argv[2]

with open(settings_path, "r") as f:
    settings = json.load(f)

hooks = settings.get("hooks", {})
stop_hooks = hooks.get("Stop", [])

# Filter out groups containing our hook
new_stop = []
for group in stop_hooks:
    filtered = [h for h in group.get("hooks", []) if hook_script not in h.get("command", "")]
    if filtered:
        group["hooks"] = filtered
        new_stop.append(group)

if new_stop:
    hooks["Stop"] = new_stop
else:
    hooks.pop("Stop", None)

if not hooks:
    settings.pop("hooks", None)

with open(settings_path, "w") as f:
    json.dump(settings, f, indent=2)

print("  Hook removed.")
PYEOF
else
    echo "  No settings file found, skipping."
fi

# 3. Clean up socket, config, and venv
echo "[3/3] Cleaning up..."
rm -f "$SOCK_PATH"
rm -rf "$HOME/.claudewatch"
rm -rf "$VENV_DIR"
echo "  Done."

echo ""
echo "=== Uninstall complete ==="
echo "ClaudeWatch has been fully removed."
echo "You can delete the $SCRIPT_DIR directory if desired."
