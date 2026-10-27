# claude-mods

Mods and companion programs for [Claude Code](https://claude.com/claude-code).

- Mods (installable plugins): [path-links](#path-links), [copy-code](#copy-code),
  [reply-timestamp](#reply-timestamp)
- Programs: [claude-rgb](programs/claude-rgb), [statusline](programs/statusline), [vocalize](programs/vocalize)

## path-links

Turns file paths in Claude's replies into `file://` links, so ctrl+click in
your terminal opens them with your default app for that file type (`xdg-open`
on Linux).

- Links absolute, `~/`, and cwd-relative paths, bare filenames, `path:line`
  references and paths in `inline code` — only when the path exists on disk.
- Leaves fenced code blocks, existing links and URLs untouched.
- A `:line` suffix stays in the text; the file opens at the top.

### Install

```
/plugin install path-links --marketplace johnlewczuk/claude-mods
```

### tmux

tmux drops hyperlinks unless told to pass them through. Add to `~/.tmux.conf`,
then detach and reattach:

```
set -as terminal-features ",*:hyperlinks"
```

With `set -g mouse on`, use ctrl+shift+click so the click reaches the terminal.

## copy-code

Adds a copy button to every fenced code block in Claude's replies. Hover a
block and a grey ` copy ` appears at its top-left corner; click it to put the
block's exact source on the clipboard, without the reply's indent.

- Fullscreen terminal layout only: hover and clicks reach the transcript
  there alone. Elsewhere replies are drawn as usual.
- Shows once the reply has finished streaming.

### Install

```
/plugin install copy-code --marketplace johnlewczuk/claude-mods
```

## reply-timestamp

Puts the reply's time on the turn line when Claude Code leaves it off. Each
reply normally ends with `✻ Baked for 3s · done 12:18 PM`, but a reply that
ends while background agents or workflows still run gets
`✻ Waiting for 2 background agents to finish` with no time. This mod draws
that line again with the time on it, in the built-in style:

```
✻ Waiting for 2 background agents to finish · done 12:18 PM
```

- Every other turn line is drawn by Claude Code, untouched.
- Times read as the built-in ones do: `12:18 PM` today, `Monday 12:18 PM`
  this week, `Monday, Oct 20, 12:18 PM` before that.
- Interrupted turns have no turn line to put a time on, and a line written
  only after team tasks finish keeps the time it was written.
- Only replies made while the mod is loaded have a recorded time; older
  waiting lines (a resumed session) stay as Claude Code draws them.

### Install

```
/plugin install reply-timestamp --marketplace johnlewczuk/claude-mods
```

## Programs

Not plugins: scripts and services that sit beside Claude Code. Each folder
has its own notes.

- [`programs/claude-rgb`](programs/claude-rgb): keyboard RGB driven by Claude
  Code statusline stats via OpenRGB, plus Ctrl+Alt+key jumps between sessions.
- [`programs/statusline`](programs/statusline): the adaptive statusline
  script, which also feeds claude-rgb.
- [`programs/vocalize`](programs/vocalize): speaks a short message aloud when
  Claude needs a physical action, plus the skill that tells Claude when.
