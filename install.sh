#!/bin/bash
# ClaudeWatch installer — sets up venv, dependencies, hook config, and LaunchAgent.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
HOOK_SCRIPT="$SCRIPT_DIR/hook_notify.py"
PLIST_SRC="$SCRIPT_DIR/com.claudewatch.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.claudewatch.plist"
SETTINGS="$HOME/.claude/settings.json"

echo "=== ClaudeWatch Installer ==="
echo ""

# 1. Create venv and install dependencies
echo "[1/4] Creating virtual environment..."
python3 -m venv "$VENV_DIR"
echo "  Created at $VENV_DIR"

echo "[2/4] Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --quiet rumps pyobjc-framework-Cocoa pyobjc-framework-Quartz
echo "  Done."

# 3. Add Stop hook to Claude Code settings
echo "[3/4] Configuring Claude Code Stop hook..."
mkdir -p "$HOME/.claude"

if [ ! -f "$SETTINGS" ]; then
    echo '{}' > "$SETTINGS"
fi

# Use python3 to safely merge the hook config
python3 - "$SETTINGS" "$HOOK_SCRIPT" <<'PYEOF'
import json
import sys

settings_path = sys.argv[1]
hook_script = sys.argv[2]

with open(settings_path, "r") as f:
    settings = json.load(f)

hook_entry = {
    "type": "command",
    "command": f"python3 {hook_script}",
    "timeout": 5
}

# Navigate/create the hooks structure
hooks = settings.setdefault("hooks", {})

# Add hooks for both Stop and Notification events
hook_types = ["Stop", "Notification"]
added_any = False

for hook_type in hook_types:
    type_hooks = hooks.setdefault(hook_type, [])

    # Check if our hook is already present
    already = False
    for group in type_hooks:
        for h in group.get("hooks", []):
            if hook_script in h.get("command", ""):
                already = True
                break

    if not already:
        type_hooks.append({"hooks": [hook_entry]})
        added_any = True
        print(f"  {hook_type} hook added.")
    else:
        print(f"  {hook_type} hook already configured.")

if added_any:
    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)

PYEOF

# 4. Generate and install LaunchAgent (with correct venv python path)
echo "[4/4] Installing LaunchAgent for auto-start..."
mkdir -p "$HOME/Library/LaunchAgents"

# Stop existing agent if running
launchctl unload "$PLIST_DST" 2>/dev/null || true

# Write plist with the venv python path
cat > "$PLIST_DST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claudewatch</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_DIR/bin/python3</string>
        <string>$SCRIPT_DIR/claudewatch.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>/tmp/claudewatch.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/claudewatch.stderr.log</string>
</dict>
</plist>
PLISTEOF

launchctl load "$PLIST_DST"
echo "  LaunchAgent installed and loaded."

echo ""
echo "=== Installation complete ==="
echo ""
echo "ClaudeWatch is now running in your menu bar."
echo "It will auto-start on login and alert you when Claude Code finishes."
echo ""
echo "To run manually:  $VENV_DIR/bin/python3 $SCRIPT_DIR/claudewatch.py"
echo "To uninstall:     bash $SCRIPT_DIR/uninstall.sh"
