# vocalize

Speaks a short message through the speakers, so a Claude Code session that
needs a physical action (press a button, unplug a cable, approve on a phone)
gets noticed even when you are away from the screen.

- `vocalize`: the command. Tries Microsoft Edge neural voices (online), then
  piper (local), then espeak; never fails its caller. `--repeat N`,
  `--no-chime`, and `--home` to speak on another machine over SSH instead.
  `vocalize --help` lists the environment variables.
- `skill/`: the Claude Code skill that tells Claude when to call it. Link or
  copy it to `~/.claude/skills/vocalize`.

## Install

```
ln -s "$PWD/vocalize" ~/.local/bin/vocalize
ln -s "$PWD/skill" ~/.claude/skills/vocalize
```

For the edge and piper engines, make a venv at `~/.local/share/vocalize/venv`
with `pip install edge-tts piper-tts` (piper voices go in
`~/.local/share/vocalize/voices`); `ffplay` plays edge's audio. espeak needs
`spd-say`.
