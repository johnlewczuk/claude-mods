# statusline

An adaptive [statusline](https://docs.claude.com/en/docs/claude-code/statusline)
for Claude Code: path, git branch (brown when dirty), model, context %, 5h and
7d usage with a reset countdown, and a few situational chips. Fields are shed
right-to-left when the line will not fit; path, context and 5h are never shed.

One `jq` process per render and no git forks on the hot path (a detached
background job refreshes the dirty flag), so it is cheap at a 1s refresh.

It also mirrors each payload to `$XDG_RUNTIME_DIR/claude-rgb/` for
[claude-rgb](../claude-rgb) when that folder exists, and shows the session's
keyboard slot (`⌨3`).

## Install

Needs `jq`. In `~/.claude/settings.json`:

```json
"statusLine": {
  "type": "command",
  "command": "bash /path/to/statusline-command.sh",
  "padding": 0,
  "refreshInterval": 1
}
```

Set `CLAUDE_STATUSLINE_COLS` to widen the line past 80 columns.
