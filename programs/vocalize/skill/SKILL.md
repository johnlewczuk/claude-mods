---
name: vocalize
description: Use whenever a task reaches a step that needs the user to physically act or do something outside the terminal — press a button, plug/unplug a cable, power-cycle or reset a board, put a device into boot/recovery mode, swap an SD card, read an LED or screen, approve on a phone/2FA device. Speaks the request aloud via the `vocalize` command so the user hears it even when away from the screen.
---

# Vocalize

The user often steps away while you work on hardware. When you need them to
*do something physically* (or anywhere off the terminal), announce it through
the speakers with the `vocalize` command before you stop and wait.

## When to use

Use it for:
- Physical actions: press/hold a button, plug or unplug a cable, power-cycle, jumper changes, insert/remove SD card or USB stick.
- Boot/recovery modes: "hold BOOT and press RESET".
- Observations only a human can make: LED colour, what's on a display, a beep.
- Out-of-band approvals: 2FA on a phone, a login in a browser, a sudo password.

Do NOT use it for:
- Ordinary clarifying questions or design choices (those are fine as text).
- Tool permission prompts, "task complete" messages, progress updates.

## How

1. Run it via Bash **before** ending your turn or starting a wait loop:
   ```bash
   vocalize "Sir, please unplug the USB cable from the dev board, then plug it back in."
   ```
2. Keep the spoken text to **one or two short sentences**: imperative, plain
   words, no paths, IPs, hex, or code (TTS mangles them). Name the device the
   way a human would ("the dev board", "the camera on the bench").
   Address the user as "sir" (e.g. "Sir, please press the reset button on
   the dev board.").
   Never put secrets, credentials or customer data in the spoken text: it is
   sent to an online TTS service (Microsoft Edge voices).
3. Still write the full detailed instructions in the terminal: the voice is
   the alert, the text is the reference.
4. If you are polling for the action (e.g. waiting for a USB device to
   re-enumerate) and it has not happened after a few minutes, vocalize once
   more with `--repeat 1`. Do not nag more than that.
5. For time-critical sequences (e.g. "press reset now"), speak each step as its
   own `vocalize` call at the moment it is needed.

## Home vs. office

Plain `vocalize` speaks on this (office) machine. Add `--home` to speak on the
user's home PC instead (the Windows PC named by `VOCALIZE_HOME_HOST`, reached over SSH):

```bash
vocalize --home "Sir, please power-cycle the camera on your desk at home."
```

Use `--home` when the action has to happen at home: the device is at the
user's house, the user said they are working from home, or the request is
about something there. If you can't tell where the user is, call both (office
first, then `--home`) rather than guess. A failure to reach the home PC only
prints a warning.

Options: `--home`, `--repeat N` (say it N times), `--no-chime`. The command never fails;
if audio is unavailable it just prints the message. `VOCALIZE_MUTE=1` in the
environment means the user has muted it. That's fine, carry on normally.
