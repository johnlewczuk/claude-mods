# claude-mods

Mods and companion programs for [Claude Code](https://claude.com/claude-code).

- Mods (installable plugins): [path-links](#path-links), [copy-code](#copy-code)
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

## Programs

Not plugins: scripts and services that sit beside Claude Code. Each folder
has its own notes.

- [`programs/claude-rgb`](programs/claude-rgb): keyboard RGB driven by Claude
  Code statusline stats via OpenRGB, plus Ctrl+Alt+key jumps between sessions.
- [`programs/statusline`](programs/statusline): the adaptive statusline
  script, which also feeds claude-rgb.
- [`programs/vocalize`](programs/vocalize): speaks a short message aloud when
  Claude needs a physical action, plus the skill that tells Claude when.
