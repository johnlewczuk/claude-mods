# claude-rgb: Claude Code stats on your keyboard

Lights a per-key RGB keyboard from Claude Code's statusline payload through
OpenRGB: context and rate-limit bars, one key per running session showing
whether it is working, blocked on you, finished, or idle, and Ctrl+Alt+<key>
to jump to that session's tmux pane. Built on a Razer Cynosa Chroma; any
keyboard OpenRGB exposes with "Key: ..." LED names should work.

Linux only. Assumes Claude Code runs inside tmux, GNOME on X11 for the jump
shortcuts (the lighting works without either).

## Install
1. OpenRGB >= 1.0. On Ubuntu 24.04 the .deb builds need a newer hidapi than
   the distro ships, so use the AppImage: extract it once
   (`./OpenRGB-x86_64.AppImage --appimage-extract`) to
   `~/.local/opt/openrgb/squashfs-root` so systemd can run `AppRun` directly
   (AppImageLauncher's binfmt hook otherwise intercepts it). Check
   `openrgb --list-devices` sees your keyboard; add OpenRGB's udev rules if not.
2. `./install.sh` creates the venv, installs the two `systemd --user` units,
   symlinks `claude-goto` into `~/.local/bin` and registers the twelve GNOME
   shortcuts.
3. Paste `statusline-hook.sh` into your Claude Code statusline script right
   after it reads stdin into `$input` (set `statusLine.command` in
   `~/.claude/settings.json` if you have none; any script that prints a line
   will do). It mirrors the payload for the daemon and reads back `$rgbslot`,
   which you can print as `⌨$rgbslot`.
4. Edit `CLAUDE_RGB_DEVICE` in `systemd/claude-rgb.service` if your keyboard
   is not a Cynosa (substring of the OpenRGB device name), and the key lists
   at the top of `claude_rgb.py` if its LED names differ.

## Layout
| Keys          | Stat                        | Colour                         |
|---------------|-----------------------------|--------------------------------|
| F1..F12       | context window used % of the session in the focused pane (dark if that pane has no Claude session) | green, amber >=60, red >=80 |
| 1..0 - =      | one Claude session per key ("slot"); Ctrl+Alt+<key> jumps to it | orange breathing = working, blue breathing = blocked on you, ice blue (steady) = finished since you last looked, grey = idle/seen, off = empty. Focused session full brightness (white when idle), others dim |
| numpad 1..9,0 | 5-hour rate limit used %    | cyan, amber >=70, red >=90     |
| Ins Home PgUp Del End PgDn | 7-day rate limit used % | violet, amber >=50, red >=80 |
| Logo          | model                       | Fable violet, Opus amber, Sonnet teal, Haiku green |
| Escape        | alarm (any stat >= 90 %)    | red; all other keys pulse red  |
| rest          | idle base                   | off; faint grey = unknown      |

No fresh session for 30 s -> everything off, dim logo.

"Mid-turn" is read from the session's transcript tail: the last turn-state
entry is a user prompt / tool_result or an assistant message -> busy; a
`system/turn_duration` row or "[Request interrupted" -> idle. A transcript
silent for 15 min is never busy.

"Blocked on you" cannot be read from the transcript (a pending permission
prompt looks exactly like a slow tool) and no hook fires when a dialog is
answered, so the daemon reads the tmux pane's screen (`tmux capture-pane`):
a Claude Code dialog shows its selected option as `❯ 1. ...` or ends with an
`Enter to ... · Esc to cancel` footer. Only mid-turn sessions are screened,
at 2 Hz. Claude Code freezes the statusline while a dialog is up, so a
blocked session's mirror file goes stale; it still counts as long as its
tmux pane exists and shows the dialog.

"Finished since you last looked" (ice blue) uses the daemon's own focus
tracking: the pane's transcript changed after the pane was last focused.
Everything counts as seen at daemon start, so a restart is not a wall of blue.

## Slots and Ctrl+Alt+<key>
Slots are keyed by session_id, first free wins, and persisted in
`~/.local/state/claude-rgb/slots.json` so a daemon restart does not reshuffle
them. A session counts only while its tmux pane still runs `claude` (tmux's
`pane_current_command`; tool subprocesses never take the tty foreground, so
it holds mid-turn). After /exit the pane lives on as a shell and the last
mirror file stays fresh for 30 s, which is why freshness alone is not
enough. Only the newest session in a pane counts (/clear, /resume or a restart in
the same pane leaves the old session's file behind). A slot is held while
the session is live (fresh or blocked on a dialog) and for 60 s after it
goes quiet; a session whose pane is gone or no longer runs claude is
released at once. Subagents and forks run the statusline too, with their
own session id and no tmux pane: they feed the rate-limit bars but get no
slot, since there is nothing to jump to. A fork shown in a pane takes the
pane over from its paused parent (newest file wins) and gets a slot. A 13th session gets no slot
until one frees. Each session's statusline shows its key as `⌨3`; the daemon
writes `$XDG_RUNTIME_DIR/claude-rgb/slots/<session_id>` for that.

`claude-goto <key>` (in ~/.local/bin) reads the map and runs
`tmux switch-client -t <pane>` on the most recently used tmux client, then
`wmctrl -xa gnome-terminal-server.Gnome-terminal` to raise the terminal.
It is bound to Ctrl+Alt+1..0,-,= as GNOME custom shortcuts (gsettings
`org.gnome.settings-daemon.plugins.media-keys custom-keybindings`,
entries `claude-goto-0..11`). Why not a tmux binding: gnome-terminal
collapses Ctrl+Alt+<digit> to Alt+<digit> and drops Ctrl+<digit> entirely
(tested with tmux 3.4 + extended-keys on), so tmux never sees the chord.
A GNOME shortcut also works when the terminal is not focused.

## Data path
1. `~/.claude/statusline-command.sh` mirrors each payload to
   `$XDG_RUNTIME_DIR/claude-rgb/<session_id>.json` (atomic mv, one bash regex,
   no extra fork).
   The hook also tags the payload with its `TMUX_PANE` and claude's pid
   (`$PPID`); forks and subagents are child processes without `TMUX_PANE`,
   and the daemon places them by walking the process tree up to the pane's
   shell (`tmux list-panes -F '#{pane_pid}'`).
2. `claude_rgb.py` (systemd --user `claude-rgb.service`) polls that dir 2x/s (renders 8x/s),
   asks tmux for the active pane of the most recently used client
   (`tmux display-message -p '#{pane_id}'`) and shows the session in that
   pane. With no Claude there (or no tmux) it falls back to the session whose
   *transcript* changed most recently (file mtime is useless: every session
   rewrites its file every second). Rate limits come from the first session in
   that same order that reports any. A frame is pushed only when it changed.
3. OpenRGB SDK server (`openrgb-server.service`, extracted AppImage at
   `~/.local/opt/openrgb/squashfs-root/AppRun`, 127.0.0.1:6742, Direct mode).

## Ops
    systemctl --user status openrgb-server claude-rgb
    journalctl --user -u claude-rgb -f
    ./venv/bin/python -m pytest -q          # pure render/selection logic
    openrgb --list-devices                  # ~/.local/bin/openrgb -> AppRun

Env knobs on the daemon: OPENRGB_HOST/PORT, CLAUDE_RGB_DEVICE (name substring,
default "Cynosa"), CLAUDE_RGB_STATE_DIR, CLAUDE_RGB_MAX_AGE (s), CLAUDE_RGB_TICK.
The OpenRGB GUI (`openrgb` with no args) will fight the daemon for the device;
stop claude-rgb first.

Install notes: OpenRGB 1.0 .deb builds need hidapi 0.15 (Ubuntu 24.04 has 0.14),
hence the AppImage. On a stock Ubuntu desktop hidraw access for the active
seat already works via the logind uaccess ACL; no udev rule was needed.
