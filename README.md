# claude-mods

Mods for [Claude Code](https://claude.com/claude-code).

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
