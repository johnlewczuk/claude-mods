# Mirror the raw payload for the keyboard-RGB daemon (claude-rgb.service,
# ~/.local/opt/openrgb-claude). One file per session so concurrent sessions do
# not clobber each other; the daemon follows the newest. session_id is pulled
# with a bash regex -- no extra jq fork. mv gives the daemon an atomic swap.
_rgbdir="${XDG_RUNTIME_DIR:-/tmp}/claude-rgb"
if [ -d "$_rgbdir" ] && [[ $input =~ \"session_id\":\"([A-Za-z0-9_-]+)\" ]]; then
    _rgbsid="${BASH_REMATCH[1]}"
    _rgbf="$_rgbdir/$_rgbsid.json"
    # Tag the payload with our tmux pane so the daemon can follow pane focus,
    # and with claude's pid ($PPID: this script is claude's direct child) so
    # forks and subagents, whose environment lacks TMUX_PANE, can still be
    # placed by walking the process tree.
    _rgbin="{\"claude_pid\":$PPID,${input#\{}"
    [[ ${TMUX_PANE:-} =~ ^%[0-9]+$ ]] && _rgbin="{\"tmux_pane\":\"$TMUX_PANE\",${_rgbin#\{}"
    printf '%s' "$_rgbin" > "$_rgbf.$$" 2>/dev/null && mv -f "$_rgbf.$$" "$_rgbf" 2>/dev/null
    # The daemon answers with this session's keyboard slot (Ctrl+Alt+<key>).
    [ -r "$_rgbdir/slots/$_rgbsid" ] && read -r rgbslot < "$_rgbdir/slots/$_rgbsid"
fi
