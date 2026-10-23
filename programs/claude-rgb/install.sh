#!/bin/bash
# Install claude-rgb for the current user. Idempotent. Needs: python3 -m venv,
# tmux, jq, wmctrl (optional, raises the terminal), OpenRGB >= 1.0 reachable
# as `openrgb` or at ~/.local/opt/openrgb/squashfs-root/AppRun (see README).
set -eu
here=$(cd "$(dirname "$0")" && pwd)

[ -d "$here/venv" ] || python3 -m venv "$here/venv"
"$here/venv/bin/pip" install -q -r "$here/requirements.txt"

mkdir -p ~/.local/bin ~/.config/systemd/user
ln -sf "$here/claude-goto" ~/.local/bin/claude-goto
for u in openrgb-server claude-rgb; do
    sed "s|%h/.local/opt/openrgb-claude|$here|g" "$here/systemd/$u.service" > ~/.config/systemd/user/$u.service
done
systemctl --user daemon-reload
systemctl --user enable --now openrgb-server.service claude-rgb.service

# Ctrl+Alt+<key> -> claude-goto for the session row (1..=) and the background
# row (Z../), as GNOME global shortcuts (see README for why these cannot be
# tmux bindings). Each entry is <GNOME key name>:<label claude_rgb.py uses>.
base=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings
if command -v gsettings >/dev/null; then
    existing=$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings | tr -d "[]' " | tr ',' '\n' | grep -v '^$' | grep -v claude-goto || true)
    paths=()
    i=0
    for kl in 1:1 2:2 3:3 4:4 5:5 6:6 7:7 8:8 9:9 0:0 minus:- equal:= \
              z:Z x:X c:C v:V b:B n:N m:M comma:, period:. slash:/; do
        k=${kl%%:*} label=${kl#*:}
        p="$base/claude-goto-$i/"; paths+=("$p")
        s="org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$p"
        gsettings set "$s" name "claude-goto $label"
        gsettings set "$s" binding "<Control><Alt>$k"
        gsettings set "$s" command "$HOME/.local/bin/claude-goto '$label'"
        i=$((i+1))
    done
    all=$(printf "'%s'," $existing "${paths[@]}"); all="[${all%,}]"
    gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$all"
fi

cat <<MSG
Installed. Remaining manual step: append statusline-hook.sh to the script
named in ~/.claude/settings.json statusLine.command (right after it reads
stdin into \$input), and optionally show \$rgbslot in the line.
MSG
