#!/usr/bin/env python3
"""Light a per-key RGB keyboard from Claude Code statusline stats via OpenRGB.

Data path:
  Claude Code statusLine hook  -->  $XDG_RUNTIME_DIR/claude-rgb/<session_id>.json
  this daemon (polls files,    -->  OpenRGB SDK server (TCP 6742)  -->  keyboard
   follows the focused tmux    -->  $XDG_RUNTIME_DIR/claude-rgb/slots/<session_id>
   pane, assigns slots)             (slot key label, read back by the statusline)
                               -->  ~/.local/state/claude-rgb/slots.json
                                    (persistent slot map, read by claude-goto)

Layout (Razer Cynosa Chroma, but any keyboard with OpenRGB key names works):
  F1-F12        context window used %     green / amber / red
  1..0 - =      one key per Claude session (its "slot", stable for the
                session's lifetime, Ctrl+Alt+<key> jumps to its tmux pane):
                  orange breathing  working (mid-turn)
                  blue breathing    blocked on you (permission, question, ...)
                  ice blue          finished since you last looked at it
                  grey              idle, seen
                  off               no session in this slot
                the focused session's key is at full brightness, others dim,
                and the two keys straddling it on the row below light in the
                same colour so the three form a triangle
  numpad 1-9,0  5-hour rate limit used %  cyan  / amber / red
  Ins..PgDn     7-day rate limit used %   violet/ amber / red
  Logo          model (Fable violet, Opus amber, Sonnet teal, Haiku green)
  Escape        red when any limit >= 90 %
  everything else: dim base, pulsing red while an alarm is active

The pure part (Session, Stats, SlotMap, render, snapshot) is unit tested and
has no OpenRGB dependency; only main() talks to the server and tmux.
"""
from __future__ import annotations

import enum
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Collection, Optional

Colour = tuple[int, int, int]

BASE: Colour = (6, 6, 10)
UNKNOWN: Colour = (18, 18, 18)
WHITE: Colour = (90, 90, 90)
IDLE_LOGO: Colour = (20, 20, 20)
GREEN: Colour = (0, 140, 30)
CYAN: Colour = (0, 110, 140)
VIOLET: Colour = (90, 0, 140)
AMBER: Colour = (200, 110, 0)
RED: Colour = (220, 0, 0)
ORANGE: Colour = (255, 70, 0)
BLUE: Colour = (0, 90, 255)
SLOT_UNREAD: Colour = (90, 190, 255)   # ice blue, steady (blocked is deep blue, breathing)
SLOT_GREY: Colour = (130, 130, 150)

MODEL_COLOURS: dict[str, Colour] = {
    "fable": (150, 0, 200),
    "opus": (220, 120, 0),
    "sonnet": (0, 150, 150),
    "haiku": (0, 170, 60),
}

F_ROW = [f"Key: F{i}" for i in range(1, 13)]
SLOT_LABELS = list("1234567890-=")
SLOT_KEYS = [f"Key: {k}" for k in SLOT_LABELS]
NUMPAD = [f"Key: Number Pad {k}" for k in "1234567890"]
NAV = [f"Key: {k}" for k in ("Insert", "Home", "Page Up", "Delete", "End", "Page Down")]
ALARM_AT = 90
# The row below the slot keys is offset by half a key, so each slot key sits
# above two keys: lighting those with the slot forms a triangle.
_BELOW = ["Key: Tab"] + [f"Key: {c}" for c in "QWERTYUIOP"] + ["Key: [", "Key: ]"]
TRIANGLE = {key: (_BELOW[i], _BELOW[i + 1]) for i, key in enumerate(SLOT_KEYS)}
BUSY_MAX_AGE = 15 * 60   # a transcript silent this long is not mid-turn
SLOT_GRACE = 60          # a slot outlives its session's last statusline write by this
UNFOCUSED_DIM = 0.65

# A Claude Code dialog (permission, AskUserQuestion, plan approval, folder
# trust) shows its selected option as a cursor on a numbered line, or ends
# with an Enter/Esc footer. The ordinary input prompt is "❯ " + free text.
DIALOG_RE = re.compile(r"^\s*❯\s*\d+\.\s|Enter to (confirm|select) · .*Esc to cancel", re.M)


class State(enum.Enum):
    WORKING = "working"    # mid-turn
    BLOCKED = "blocked"    # mid-turn and a dialog is on screen
    UNREAD = "unread"      # turn ended since the pane was last focused
    IDLE = "idle"          # turn ended, seen


@dataclass(frozen=True)
class Session:
    id: str
    pane: Optional[str]
    transcript: Optional[str]
    file_mtime: float
    activity: float          # transcript mtime: when it last did something
    fresh: bool              # statusline wrote recently
    busy: bool
    blocked: bool
    payload: dict = field(compare=False, repr=False)

    @property
    def live(self) -> bool:
        return self.fresh or self.blocked

    def state(self, viewed_at: float) -> State:
        if self.blocked:
            return State.BLOCKED
        if self.busy:
            return State.WORKING
        if self.pane and self.activity > viewed_at:
            return State.UNREAD
        return State.IDLE


SlotView = tuple[State, bool]      # (state, is the focused session)


@dataclass(frozen=True)
class Stats:
    ctx: Optional[float]
    h5: Optional[float]
    d7: Optional[float]
    model: Optional[str]
    slots: tuple[Optional[SlotView], ...] = ()   # aligned with SLOT_KEYS


# --- rendering ----------------------------------------------------------------

def lit_count(pct: Optional[float], n: int) -> Optional[int]:
    """How many of n keys to light for pct%. Any non-zero usage lights >= 1."""
    if pct is None:
        return None
    return max(0, min(n, math.ceil(pct / 100 * n)))


def ramp(pct: Optional[float], ok: Colour, warn: int, crit: int) -> Colour:
    if pct is None:
        return UNKNOWN
    if pct >= crit:
        return RED
    if pct >= warn:
        return AMBER
    return ok


def bar(frame: list[Colour], names: list[str], keys: list[str],
        pct: Optional[float], ok: Colour, warn: int, crit: int) -> None:
    n = lit_count(pct, len(keys))
    colour = ramp(pct, ok, warn, crit)
    for i, key in enumerate(keys):
        if key not in names:
            continue
        if n is None:
            frame[names.index(key)] = UNKNOWN
        elif i < n:
            frame[names.index(key)] = colour


def model_colour(model: Optional[str]) -> Colour:
    if not model:
        return WHITE
    m = model.lower()
    for key, colour in MODEL_COLOURS.items():
        if key in m:
            return colour
    return WHITE


def breathe(t: float, period: float) -> float:
    """0..1 cosine breathe with the given period in seconds."""
    return (1 - math.cos(2 * math.pi * t / period)) / 2


def pulse(t: float) -> Colour:
    """Slow red breathe for alarm state; t is seconds."""
    return (int(30 + breathe(t, 2.0) * 80), 0, 0)   # never dips to BASE


def scaled(colour: Colour, k: float) -> Colour:
    return tuple(int(c * k) for c in colour)


def paint(frame: list[Colour], names: list[str], keys: Collection[str], colour: Colour) -> None:
    for key in keys:
        if key in names:
            frame[names.index(key)] = colour


def slot_colour(view: Optional[SlotView], t: float) -> Colour:
    if view is None:
        return BASE
    state, focused = view
    if state is State.WORKING:
        c = scaled(ORANGE, 0.5 + 0.5 * breathe(t, 2.0))
    elif state is State.BLOCKED:
        c = scaled(BLUE, 0.5 + 0.5 * breathe(t, 1.5))
    elif state is State.UNREAD:
        c = SLOT_UNREAD
    else:
        c = SLOT_GREY
    return c if focused else scaled(c, UNFOCUSED_DIM)


def render(names: list[str], s: Optional[Stats], t: float) -> list[Colour]:
    """Pure: LED names + stats + time -> one colour per LED."""
    if s is None:
        frame = [BASE] * len(names)
        if "Logo" in names:
            frame[names.index("Logo")] = IDLE_LOGO
        return frame

    alarm = any(v is not None and v >= ALARM_AT for v in (s.ctx, s.h5, s.d7))
    base = pulse(t) if alarm else BASE
    frame = [base] * len(names)

    bar(frame, names, F_ROW, s.ctx, GREEN, 60, 80)
    bar(frame, names, NUMPAD, s.h5, CYAN, 70, 90)
    bar(frame, names, NAV, s.d7, VIOLET, 50, 80)
    for key, view in zip(SLOT_KEYS, s.slots):
        colour = slot_colour(view, t)
        paint(frame, names, [key], colour)
        if view is not None and view[1]:
            paint(frame, names, TRIANGLE[key], colour)
    if "Logo" in names:
        frame[names.index("Logo")] = model_colour(s.model)
    if alarm and "Key: Escape" in names:
        frame[names.index("Key: Escape")] = RED
    return frame


# --- transcript ----------------------------------------------------------------

def busy_from_transcript(path: Optional[str], now: Optional[float] = None,
                         max_age: Optional[float] = BUSY_MAX_AGE) -> bool:
    """Is this session mid-turn? Scan the transcript tail backwards for the
    last entry that says anything about turn state:
      user prompt / tool_result  -> Claude owes a response      -> busy
      assistant (tool_use etc.)  -> tool running or streaming   -> busy
      system/turn_duration       -> turn finished               -> idle
      '[Request interrupted ...' -> user hit Esc                -> idle
    Metadata rows (ai-title, mode, api-request, ...) are skipped.
    max_age=None disables the silence cap (a dialog can sit for hours)."""
    now = time.time() if now is None else now
    if not path:
        return False
    try:
        st = os.stat(path)
        if max_age is not None and now - st.st_mtime > max_age:
            return False
        with open(path, "rb") as fh:
            fh.seek(max(0, st.st_size - 512 * 1024))
            tail = fh.read()
    except OSError:
        return False
    for line in reversed(tail.splitlines()):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        kind = e.get("type")
        if kind == "system" and e.get("subtype") == "turn_duration":
            return False
        if kind == "assistant":
            return True
        if kind == "user":
            content = (e.get("message") or {}).get("content")
            return not (isinstance(content, str) and content.startswith("[Request interrupted"))
    return False


def has_dialog(screen: str) -> bool:
    return DIALOG_RE.search(screen) is not None


# --- sessions -------------------------------------------------------------------

def load_sessions(state_dir: str, max_age: float, now: float,
                  dialog_open: Callable[[str], bool], live_panes: Collection[str]) -> list[Session]:
    """One Session per mirror file. A half-written file (statusline
    mid-write) is skipped for this tick.

    A session is `fresh` when the statusline wrote recently. It is `blocked`
    when its pane still exists, its transcript ends mid-turn and a dialog is
    on screen; Claude Code freezes the statusline while a dialog is up, so a
    blocked session is usually NOT fresh and must be recognised this way.
    Only mid-turn sessions with a live pane are screen-scraped."""
    try:
        files = [f for f in os.listdir(state_dir) if f.endswith(".json")]
    except FileNotFoundError:
        return []
    out = []
    for f in files:
        path = os.path.join(state_dir, f)
        try:
            with open(path) as fh:
                mtime = os.stat(path).st_mtime
                p = json.load(fh)
        except (OSError, ValueError):
            continue
        pane, transcript = p.get("tmux_pane"), p.get("transcript_path")
        try:
            activity = os.stat(transcript).st_mtime
        except (TypeError, OSError):
            activity = mtime
        mid_turn = busy_from_transcript(transcript, now, max_age=None)
        blocked = bool(pane) and pane in live_panes and mid_turn and dialog_open(pane)
        out.append(Session(
            id=p.get("session_id") or f[:-5], pane=pane, transcript=transcript,
            file_mtime=mtime, activity=activity, fresh=now - mtime <= max_age,
            busy=mid_turn and (blocked or now - activity <= BUSY_MAX_AGE),
            blocked=blocked, payload=p))
    return out


def rank(sessions: list[Session], focus: Optional[str]) -> list[Session]:
    """Focused session first, then by most recent activity. (The mirror
    file's mtime is useless for this: every session rewrites it every second.)"""
    ranked = sorted(sessions, key=lambda s: s.activity, reverse=True)
    if focus is not None:
        ranked.sort(key=lambda s: s.pane != focus)   # stable: focused to front
    return ranked


def stats_from(sessions: list[Session], focus: Optional[str],
               slots: tuple[Optional[SlotView], ...] = ()) -> Optional[Stats]:
    """Context % and model come from the focused session if there is one,
    else from the most recently active. Rate limits are account-wide, but a
    session only learns them from its own API responses, so an idle session
    carries stale numbers and some carry none: take them from the first
    session in that same order that has any."""
    live = [s for s in sessions if s.live]
    if not live:
        return None
    ranked = rank(live, focus)
    active = ranked[0]
    h5 = d7 = None
    for s in ranked:
        rl = s.payload.get("rate_limits") or {}
        if rl:
            h5 = (rl.get("five_hour") or {}).get("used_percentage")
            d7 = (rl.get("seven_day") or {}).get("used_percentage")
            break
    return Stats(
        ctx=(active.payload.get("context_window") or {}).get("used_percentage"),
        h5=h5, d7=d7,
        model=(active.payload.get("model") or {}).get("display_name"),
        slots=slots,
    )


def pick_stats(state_dir: str, max_age: float, now: Optional[float] = None,
               focus: Optional[str] = None,
               dialog_open: Callable[[str], bool] = lambda pane: False,
               live_panes: Collection[str] = ()) -> Optional[Stats]:
    """Convenience: load + stats_from, without slots."""
    now = time.time() if now is None else now
    return stats_from(load_sessions(state_dir, max_age, now, dialog_open, live_panes), focus)


# --- slots ------------------------------------------------------------------------

class SlotMap:
    """Stable session -> key assignment, persisted so a daemon restart does
    not reshuffle what you have learned. First free slot wins; a slot is
    released when its session is no longer held."""

    def __init__(self, path: Optional[str] = None):
        self.path = path
        self.slots: dict[str, str] = {}      # label -> session id
        if path:
            try:
                with open(path) as fh:
                    data = json.load(fh).get("slots", {})
                self.slots = {k: v for k, v in data.items() if k in SLOT_LABELS and isinstance(v, str)}
            except (OSError, ValueError, AttributeError):
                pass

    def update(self, held: Collection[str]) -> bool:
        """Release slots of sessions not in `held`, assign free slots to new
        ones (in the given order). Returns True if anything changed."""
        before = dict(self.slots)
        self.slots = {k: v for k, v in self.slots.items() if v in held}
        taken = set(self.slots.values())
        free = [k for k in SLOT_LABELS if k not in self.slots]
        for sid in held:
            if sid in taken or not free:
                continue
            self.slots[free.pop(0)] = sid
            taken.add(sid)
        changed = self.slots != before
        if changed and self.path:
            self.save()
        return changed

    def label_of(self, session_id: str) -> Optional[str]:
        for k, v in self.slots.items():
            if v == session_id:
                return k
        return None

    def session_at(self, label: str) -> Optional[str]:
        return self.slots.get(label)

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = f"{self.path}.{os.getpid()}"
        with open(tmp, "w") as fh:
            json.dump({"slots": self.slots}, fh, indent=1)
        os.replace(tmp, self.path)


def held_ids(sessions: list[Session], now: float, live_panes: Collection[str]) -> list[str]:
    """Sessions that keep (or get) a slot: live ones, plus ones that went
    quiet within the grace period so a statusline hiccup does not reshuffle
    keys. A session whose tmux pane no longer exists is gone for certain and
    is released at once. Ordered oldest first so allocation is deterministic."""
    def present(s: Session) -> bool:
        return s.pane is None or s.pane in live_panes
    keep = [s for s in sessions if s.live or (present(s) and now - s.file_mtime <= SLOT_GRACE)]
    return [s.id for s in sorted(keep, key=lambda s: s.file_mtime)]


def slot_views(sessions: list[Session], slots: SlotMap, focus: Optional[str],
               viewed: dict[str, float], default_viewed: float) -> tuple[Optional[SlotView], ...]:
    """What each slot key shows. `viewed` maps pane -> when it was last
    focused; a pane never focused since the daemon started counts as viewed
    at `default_viewed` (daemon start), so a restart does not light every
    idle session unread-blue. A session in its grace period (not live) is idle."""
    by_id = {s.id: s for s in sessions}
    out: list[Optional[SlotView]] = []
    for label in SLOT_LABELS:
        s = by_id.get(slots.session_at(label) or "")
        if s is None:
            out.append(None)
        elif not s.live:
            out.append((State.IDLE, False))
        else:
            out.append((s.state(viewed.get(s.pane or "", default_viewed)), s.pane == focus))
    return tuple(out)


def write_slot_labels(state_dir: str, slots: SlotMap) -> None:
    """One tiny file per session holding its key label, for the statusline
    to read back (a bash `read`, no fork). Removed when the slot is released."""
    d = os.path.join(state_dir, "slots")
    os.makedirs(d, exist_ok=True)
    want = {sid: label for label, sid in slots.slots.items()}
    for f in os.listdir(d):
        if f not in want:
            try:
                os.remove(os.path.join(d, f))
            except OSError:
                pass
    for sid, label in want.items():
        path = os.path.join(d, sid)
        try:
            with open(path) as fh:
                if fh.read().strip() == label:
                    continue
        except OSError:
            pass
        with open(path, "w") as fh:
            fh.write(label + "\n")


# --- tmux ------------------------------------------------------------------------

def focused_pane() -> Optional[str]:
    """Active pane of the most recently used tmux client, e.g. "%222", or
    None when tmux is absent or has no clients."""
    if not shutil.which("tmux"):
        return None
    try:
        r = subprocess.run(["tmux", "display-message", "-p", "#{pane_id}"],
                           capture_output=True, text=True, timeout=1)
    except (OSError, subprocess.SubprocessError):
        return None
    pane = r.stdout.strip()
    return pane if r.returncode == 0 and pane.startswith("%") else None


def live_panes() -> set[str]:
    """Every pane id tmux currently has, across all sessions."""
    try:
        r = subprocess.run(["tmux", "list-panes", "-a", "-F", "#{pane_id}"],
                           capture_output=True, text=True, timeout=1)
    except (OSError, subprocess.SubprocessError):
        return set()
    return set(r.stdout.split()) if r.returncode == 0 else set()


def pane_has_dialog(pane: str) -> bool:
    """Is a Claude Code dialog on screen in this tmux pane right now? The
    transcript cannot tell a pending permission prompt from a slow tool, and
    no hook fires when a dialog is answered, so the screen is the one source
    that is right the instant you answer."""
    try:
        r = subprocess.run(["tmux", "capture-pane", "-p", "-t", pane],
                           capture_output=True, text=True, timeout=1)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0 and has_dialog(r.stdout)


# --- daemon ------------------------------------------------------------------------

def main() -> int:
    from openrgb import OpenRGBClient
    from openrgb.utils import RGBColor

    host = os.environ.get("OPENRGB_HOST", "127.0.0.1")
    port = int(os.environ.get("OPENRGB_PORT", "6742"))
    match = os.environ.get("CLAUDE_RGB_DEVICE", "Cynosa").lower()
    state_dir = os.environ.get(
        "CLAUDE_RGB_STATE_DIR",
        os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "claude-rgb"))
    slots_path = os.environ.get(
        "CLAUDE_RGB_SLOTS",
        os.path.join(os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")),
                     "claude-rgb", "slots.json"))
    max_age = float(os.environ.get("CLAUDE_RGB_MAX_AGE", "30"))
    tick = float(os.environ.get("CLAUDE_RGB_TICK", "0.125"))
    stats_every = 0.5    # tmux lookups (focus, dialog screens) happen at this rate
    os.makedirs(state_dir, exist_ok=True)
    slots = SlotMap(slots_path)
    print(f"claude-rgb: state={state_dir} slots={slots_path} server={host}:{port} device~{match!r}", flush=True)

    client = dev = None
    names: list[str] = []
    last: Optional[list[Colour]] = None
    stats, stats_at = None, -1.0
    viewed: dict[str, float] = {}       # pane -> wall time last focused
    started = time.time()
    while True:
        try:
            if dev is None:
                client = OpenRGBClient(host, port, "claude-rgb")
                cands = [d for d in client.devices if match in d.name.lower()]
                if not cands:
                    raise RuntimeError(f"no device matching {match!r}: {[d.name for d in client.devices]}")
                dev = cands[0]
                dev.set_mode("Direct")
                names = [l.name for l in dev.leds]
                last = None
                print(f"claude-rgb: driving {dev.name} ({len(names)} leds)", flush=True)

            now = time.monotonic()
            if now - stats_at >= stats_every:
                wall = time.time()
                focus = focused_pane()
                if focus:
                    viewed[focus] = wall
                panes = live_panes()
                sessions = load_sessions(state_dir, max_age, wall, pane_has_dialog, panes)
                if slots.update(held_ids(sessions, wall, panes)):
                    print(f"claude-rgb: slots {slots.slots}", flush=True)
                write_slot_labels(state_dir, slots)
                stats = stats_from(sessions, focus, slot_views(sessions, slots, focus, viewed, started))
                stats_at = now
            frame = render(names, stats, now)
            if frame != last:
                dev.set_colors([RGBColor(*c) for c in frame], fast=True)
                last = frame
        except KeyboardInterrupt:
            return 0
        except Exception as e:  # server down, USB unplugged, ...: retry
            print(f"claude-rgb: {e.__class__.__name__}: {e}; reconnecting in 5s", flush=True)
            try:
                if client:
                    client.disconnect()
            except Exception:
                pass
            client = dev = None
            time.sleep(5)
            continue
        time.sleep(tick)


if __name__ == "__main__":
    sys.exit(main())
