#!/usr/bin/env python3
"""Light a per-key RGB keyboard from Claude Code statusline stats via OpenRGB.

Data path:
  Claude Code statusLine hook  -->  $XDG_RUNTIME_DIR/claude-rgb/<session_id>.json
                                    (payload + tmux_pane + claude_pid)
  this daemon (polls files,    -->  OpenRGB SDK server (TCP 6742)  -->  keyboard
   follows the focused tmux    -->  $XDG_RUNTIME_DIR/claude-rgb/slots/<session_id>
   pane, assigns slots)             (slot key label, read back by the statusline;
                                    bgslots/<session_id> for the Z row)
                               -->  $XDG_RUNTIME_DIR/claude-rgb/targets.json
                                    (key label -> session + pane, read by claude-goto)
                               -->  ~/.local/state/claude-rgb/{slots,bgslots}.json
                                    (persistent slot maps)

Layout (Razer Cynosa Chroma, but any keyboard with OpenRGB key names works):
  F1-F12        context window used %     green / amber / red
                (of the session in the focused tmux pane; dark when that
                pane holds no Claude session)
  1..0 - =      one key per Claude session (its "slot", stable for the
                session's lifetime, Ctrl+Alt+<key> jumps to its tmux pane):
                  orange breathing  working (mid-turn)
                  blue breathing    blocked on you (permission, question, ...)
                  ice blue          finished since you last looked at it
                  grey              idle, seen
                  off               no session in this slot
                the focused session's key is at full brightness, others dim;
                a focused idle session is white instead of grey
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
from typing import Callable, Collection, Mapping, Optional

Colour = tuple[int, int, int]

BASE: Colour = (0, 0, 0)
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
FOCUS_IDLE: Colour = (255, 255, 255)  # white: the focused session when idle

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
BG_LABELS = list("ZXCVBNM,./")        # Z row: sessions with no tmux pane (background)
BG_KEYS = [f"Key: {k}" for k in BG_LABELS]
ALARM_AT = 90
BUSY_MAX_AGE = 15 * 60   # a transcript silent this long is not mid-turn
SLOT_GRACE = 60          # a slot outlives its session's last statusline write by this
# tmux's #{pane_current_command} while Claude Code runs in the pane. Tool
# subprocesses never take the tty foreground, so this holds mid-turn too.
CLAUDE_COMMANDS = {"claude", "node"}
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
    running: bool            # its pane runs claude and no newer session shares the pane (True if no pane)
    busy: bool
    blocked: bool
    live: bool               # (fresh or blocked) and running
    agent: bool              # a background subagent (never gets a key)
    payload: dict = field(compare=False, repr=False)

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
    has_session: bool = True      # False: focused pane holds no Claude session
    slots: tuple[Optional[SlotView], ...] = ()   # aligned with SLOT_KEYS
    bg: tuple[Optional[SlotView], ...] = ()      # aligned with BG_KEYS


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
    elif focused:
        return FOCUS_IDLE
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

    if s.has_session:
        bar(frame, names, F_ROW, s.ctx, GREEN, 60, 80)
    bar(frame, names, NUMPAD, s.h5, CYAN, 70, 90)
    bar(frame, names, NAV, s.d7, VIOLET, 50, 80)
    for key, view in zip(SLOT_KEYS, s.slots):
        paint(frame, names, [key], slot_colour(view, t))
    for key, view in zip(BG_KEYS, s.bg):
        paint(frame, names, [key], slot_colour(view, t))
    if "Logo" in names:
        frame[names.index("Logo")] = model_colour(s.model) if s.has_session else IDLE_LOGO
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
      continued-in               -> session handed off elsewhere -> idle
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
        if kind == "continued-in":
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

def parent_pid(pid: int) -> Optional[int]:
    try:
        with open(f"/proc/{pid}/stat") as fh:
            return int(fh.read().rsplit(")", 1)[1].split()[1])
    except (OSError, ValueError, IndexError):
        return None


def resolve_pane(pid: Optional[int], pane_pids: Mapping[int, str],
                 parent_of: Callable[[int], Optional[int]] = parent_pid) -> Optional[str]:
    """Walk up from a claude pid to the shell a tmux pane started
    (`pane_pid`), giving the pane. Forks and subagents are child processes
    without TMUX_PANE in their environment, so this is how they are placed."""
    seen = 0
    while pid and pid > 1 and seen < 32:
        if pid in pane_pids:
            return pane_pids[pid]
        pid = parent_of(pid)
        seen += 1
    return None


def is_agent(payload: dict) -> bool:
    """Background subagents run inside the parent's process with their own
    session id; they must not claim the parent's pane."""
    return bool(payload.get("agent_type") or payload.get("agent"))


@dataclass(frozen=True)
class Candidate:
    """A session that might be the one a pane is displaying."""
    id: str
    name: Optional[str]
    fresh: bool
    tagged: bool        # the hook saw TMUX_PANE: the pane's own foreground claude
    mid_turn: bool
    mtime: float


def pane_owner(cands: list[Candidate], screen: str) -> Candidate:
    """Which of several sessions sharing a pane is the one on screen.
    Claude Code can host extra sessions (forks, /resume targets) in
    background ptys and attach the pane to one of them; all of them keep
    writing their mirror file every second, so "newest file" would flap.
      1. An attached session shows its name in the separator above the
         prompt; a fork's name extends its parent's, so the longest name
         found on screen wins.
      2. A dialog on screen belongs to the displayed session, whose
         statusline is frozen: the stale mid-turn one.
      3. Otherwise the pane's own foreground claude (tagged), if fresh.
      4. Otherwise the newest fresh one, else the newest."""
    named = [c for c in cands if c.name and c.name[:40] in screen]
    if named:
        return max(named, key=lambda c: len(c.name))
    if has_dialog(screen):
        frozen = [c for c in cands if c.mid_turn and not c.fresh]
        if frozen:
            return max(frozen, key=lambda c: c.mtime)
    fresh = [c for c in cands if c.fresh]
    tagged = [c for c in fresh if c.tagged]
    if tagged:
        return max(tagged, key=lambda c: c.mtime)
    return max(fresh or cands, key=lambda c: c.mtime)


def load_sessions(state_dir: str, max_age: float, now: float,
                  screen_of: Callable[[str], str], panes: Mapping[str, str],
                  pane_pids: Mapping[int, str] = {},
                  parent_of: Callable[[int], Optional[int]] = parent_pid,
                  pane_tags: Mapping[str, str] = {}) -> list[Session]:
    """One Session per mirror file. A half-written file (statusline
    mid-write) is skipped for this tick. `panes` maps every existing tmux
    pane id to its foreground command, `pane_pids` each pane's shell pid to
    the pane id, `pane_tags` pane id -> the session claude-goto attached
    there, and screen_of(pane) returns the pane's visible text (it is only
    called for panes that need it). A session's pane is its tmux_pane tag if
    the hook had one, else a pane tagged with its id, else the pane found by
    walking up from claude_pid; background agents get none.

    A session is `fresh` when the statusline wrote recently, and `running`
    when its pane still runs claude AND it is the session that pane displays
    (pane_owner): after /exit the pane lives on as a shell and the last
    mirror file stays fresh for a while; /clear, /resume or a restart in the
    same pane leaves the previous session's file behind; and background-
    hosted sessions share the pane with the foreground one. It is `blocked`
    when running, its transcript ends mid-turn and a dialog is on screen;
    Claude Code freezes the statusline while a dialog is up, so a blocked
    session is usually NOT fresh and must be recognised this way."""
    try:
        files = [f for f in os.listdir(state_dir) if f.endswith(".json")]
    except FileNotFoundError:
        return []
    loaded = []
    for f in files:
        path = os.path.join(state_dir, f)
        try:
            with open(path) as fh:
                loaded.append((f, os.stat(path).st_mtime, json.load(fh)))
        except (OSError, ValueError):
            continue
    attached = {sid: pane for pane, sid in pane_tags.items()}

    def pane_of(p: dict) -> Optional[str]:
        if is_agent(p):
            return None
        return (p.get("tmux_pane") or attached.get(p.get("session_id") or "")
                or resolve_pane(p.get("claude_pid"), pane_pids, parent_of))

    rows = []
    for f, mtime, p in loaded:
        if not isinstance(p, dict) or not p.get("session_id"):
            continue    # not a mirror file (targets.json lives here too)
        transcript = p.get("transcript_path")
        try:
            activity = os.stat(transcript).st_mtime
        except (TypeError, OSError):
            activity = mtime
        rows.append(dict(
            id=p["session_id"], pane=pane_of(p), transcript=transcript,
            mtime=mtime, activity=activity, fresh=now - mtime <= max_age,
            mid_turn=busy_from_transcript(transcript, now, max_age=None), payload=p))

    # One screen capture per pane that needs one: several sessions to choose
    # between, or a mid-turn session to check for a dialog.
    screens: dict[str, str] = {}
    by_pane: dict[str, list[dict]] = {}
    for r in rows:
        if r["pane"] and panes.get(r["pane"]) in CLAUDE_COMMANDS:
            by_pane.setdefault(r["pane"], []).append(r)
    owner: dict[str, str] = {}
    for pane, rs in by_pane.items():
        if len(rs) > 1 or any(r["mid_turn"] for r in rs):
            screens[pane] = screen_of(pane)
        if len(rs) == 1:
            owner[pane] = rs[0]["id"]
        else:
            cands = [Candidate(r["id"], r["payload"].get("session_name"), r["fresh"],
                               bool(r["payload"].get("tmux_pane")), r["mid_turn"], r["mtime"]) for r in rs]
            owner[pane] = pane_owner(cands, screens[pane]).id

    out = []
    for r in rows:
        pane = r["pane"]
        running = pane is None or owner.get(pane) == r["id"]
        blocked = bool(pane) and running and r["mid_turn"] and has_dialog(screens.get(pane, ""))
        out.append(Session(
            id=r["id"], pane=pane, transcript=r["transcript"],
            file_mtime=r["mtime"], activity=r["activity"], fresh=r["fresh"], running=running,
            busy=r["mid_turn"] and (blocked or now - r["activity"] <= BUSY_MAX_AGE),
            blocked=blocked, live=(r["fresh"] or blocked) and running,
            agent=is_agent(r["payload"]), payload=r["payload"]))
    return out


def rank(sessions: list[Session], focus: Optional[str]) -> list[Session]:
    """Focused session first, then by most recent activity. (The mirror
    file's mtime is useless for this: every session rewrites it every second.)"""
    ranked = sorted(sessions, key=lambda s: s.activity, reverse=True)
    if focus is not None:
        ranked.sort(key=lambda s: s.pane != focus)   # stable: focused to front
    return ranked


@dataclass
class LimitClock:
    """Latest rate-limit reading from any session. Rate limits are account-wide,
    but a session learns them only from its own API responses, so one payload
    can carry numbers hours old, and no payload says when they were read. The
    daemon dates each session's reading by when it first appeared or last
    changed in its view (it polls at 2 Hz, close to when the statusline runs)."""
    readings: dict[str, tuple[float, float, Optional[float], Optional[float]]] = field(default_factory=dict)
    # session id -> (wall time seen, transcript activity, five_hour %, seven_day %)

    def observe(self, sessions: list[Session], wall: float) -> None:
        for s in sessions:
            rl = s.payload.get("rate_limits") or {}
            h5 = (rl.get("five_hour") or {}).get("used_percentage")
            d7 = (rl.get("seven_day") or {}).get("used_percentage")
            if h5 is None and d7 is None:
                continue
            seen = self.readings.get(s.id)
            if seen is None or seen[2:] != (h5, d7):
                self.readings[s.id] = (wall, s.activity, h5, d7)

    def latest(self) -> tuple[Optional[float], Optional[float]]:
        """(five_hour %, seven_day %) of the most recently dated reading. Ties
        (sessions first seen in the same tick) go to the most recently active."""
        if not self.readings:
            return None, None
        _, _, h5, d7 = max(self.readings.values(), key=lambda r: r[:2])
        return h5, d7


def stats_from(sessions: list[Session], focus: Optional[str],
               slots: tuple[Optional[SlotView], ...] = (),
               limits: tuple[Optional[float], Optional[float]] = (None, None),
               bg: tuple[Optional[SlotView], ...] = ()) -> Optional[Stats]:
    """Context % and model describe the session in the focused tmux pane.
    A focused pane with no Claude session shows none (has_session=False)
    rather than someone else's; outside tmux (focus None) the most recently
    active session stands in. `limits` is the account-wide (five_hour, seven_day)
    reading, supplied by the caller's LimitClock."""
    live = [s for s in sessions if s.live]
    if not live:
        return None
    ranked = rank(live, focus)
    active = ranked[0]
    has_session = focus is None or active.pane == focus
    h5, d7 = limits
    if not has_session:
        return Stats(ctx=None, h5=h5, d7=d7, model=None, has_session=False, slots=slots, bg=bg)
    return Stats(
        ctx=(active.payload.get("context_window") or {}).get("used_percentage"),
        h5=h5, d7=d7,
        model=(active.payload.get("model") or {}).get("display_name"),
        slots=slots, bg=bg,
    )


def pick_stats(state_dir: str, max_age: float, now: Optional[float] = None,
               focus: Optional[str] = None,
               screen_of: Callable[[str], str] = lambda pane: "",
               live_panes: Mapping[str, str] = {}) -> Optional[Stats]:
    """Convenience: load + stats_from, without slots. One observation only, so
    the limits come from the most recently active session that reports them."""
    now = time.time() if now is None else now
    sessions = load_sessions(state_dir, max_age, now, screen_of, live_panes)
    clock = LimitClock()
    clock.observe(sessions, now)
    return stats_from(sessions, focus, limits=clock.latest())


# --- slots ------------------------------------------------------------------------

class SlotMap:
    """Stable session -> key assignment, persisted so a daemon restart does
    not reshuffle what you have learned. First free slot wins; a slot is
    released when its session is no longer held."""

    def __init__(self, path: Optional[str] = None, labels: list[str] = SLOT_LABELS):
        self.path = path
        self.labels = labels
        self.slots: dict[str, str] = {}      # label -> session id
        if path:
            try:
                with open(path) as fh:
                    data = json.load(fh).get("slots", {})
                self.slots = {k: v for k, v in data.items() if k in labels and isinstance(v, str)}
            except (OSError, ValueError, AttributeError):
                pass

    def update(self, held: Collection[str]) -> bool:
        """Release slots of sessions not in `held`, assign free slots to new
        ones (in the given order). Returns True if anything changed."""
        before = dict(self.slots)
        self.slots = {k: v for k, v in self.slots.items() if v in held}
        taken = set(self.slots.values())
        free = [k for k in self.labels if k not in self.slots]
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


def held_ids(sessions: list[Session], now: float, panes: Mapping[str, str]) -> list[str]:
    """Sessions that keep (or get) a slot: live ones, plus running ones that
    went quiet within the grace period so a statusline hiccup does not
    reshuffle keys. A session whose pane is gone or no longer runs claude is
    released at once. Sessions without a tmux pane (subagents, forks, claude
    outside tmux) cannot be jumped to and get no slot. Ordered oldest first
    so allocation is deterministic."""
    keep = [s for s in sessions
            if s.pane and (s.live or (s.running and now - s.file_mtime <= SLOT_GRACE))]
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


def is_background(s: Session, panes: Mapping[str, str]) -> bool:
    """Not on screen: no tmux pane at all, or its pane still runs claude but
    displays another session (the one that was paused when a background
    session was put into the pane). A pane that went back to a shell (after
    /exit) does not count."""
    if s.agent:
        return False
    return s.pane is None or (not s.running and panes.get(s.pane) in CLAUDE_COMMANDS)


def held_bg_ids(sessions: list[Session], now: float, panes: Mapping[str, str]) -> list[str]:
    """Background sessions that keep or get a Z-row key: live or busy ones,
    plus those quiet within the grace period. A displaced session's statusline
    freezes while another session holds its pane, so busy is what keeps it
    working on the keyboard. Ordered oldest first so allocation is stable."""
    keep = [s for s in sessions
            if is_background(s, panes) and (s.live or s.busy or now - s.file_mtime <= SLOT_GRACE)]
    return [s.id for s in sorted(keep, key=lambda s: s.file_mtime)]


def bg_views(sessions: list[Session], bgslots: SlotMap) -> tuple[Optional[SlotView], ...]:
    """What each Z-row key shows: working while mid-turn, otherwise idle. A
    background session never has a pane it could be unread on or blocked in,
    so ice blue and blue do not occur on this row."""
    by_id = {s.id: s for s in sessions}
    out: list[Optional[SlotView]] = []
    for label in BG_LABELS:
        s = by_id.get(bgslots.session_at(label) or "")
        if s is None:
            out.append(None)
        else:
            out.append((State.WORKING if s.busy else State.IDLE, False))
    return tuple(out)


def write_slot_labels(state_dir: str, slots: SlotMap, subdir: str = "slots") -> None:
    """One tiny file per session holding its key label, for the statusline
    to read back (a bash `read`, no fork). Removed when the slot is released."""
    d = os.path.join(state_dir, subdir)
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


def jump_targets(sessions: list[Session], *maps: SlotMap) -> dict[str, dict]:
    """label -> {"session": id, "pane": pane id or None} for every assigned
    key, read by claude-goto. A null pane is a detached background session,
    which claude-goto opens with `claude attach` in a new tmux window."""
    pane_of = {s.id: s.pane for s in sessions}
    return {label: {"session": sid, "pane": pane_of.get(sid)}
            for m in maps for label, sid in m.slots.items()}


def write_targets(state_dir: str, targets: dict[str, dict]) -> None:
    """Atomically replace targets.json, only when it changed."""
    path = os.path.join(state_dir, "targets.json")
    try:
        with open(path) as fh:
            if json.load(fh) == targets:
                return
    except (OSError, ValueError):
        pass
    tmp = f"{path}.{os.getpid()}"
    with open(tmp, "w") as fh:
        json.dump(targets, fh)
    os.replace(tmp, path)


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


PANES_FORMAT = "#{pane_id}\t#{pane_pid}\t#{@claude_session}\t#{pane_current_command}"


def parse_panes(out: str) -> tuple[dict[str, str], dict[int, str], dict[str, str]]:
    """`tmux list-panes -F PANES_FORMAT` output -> (pane id -> foreground
    command, pane shell pid -> pane id, pane id -> @claude_session tag).
    claude-goto tags the windows it opens with `claude attach`, since the
    attached session's own process (and so its payload) knows no pane."""
    cmds: dict[str, str] = {}
    pids: dict[int, str] = {}
    tags: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split("\t", 3)
        if len(parts) == 4 and parts[1].isdigit():
            cmds[parts[0]] = parts[3]
            pids[int(parts[1])] = parts[0]
            if parts[2]:
                tags[parts[0]] = parts[2]
    return cmds, pids, tags


def live_panes() -> tuple[dict[str, str], dict[int, str], dict[str, str]]:
    """parse_panes() for every pane tmux currently has."""
    try:
        r = subprocess.run(["tmux", "list-panes", "-a", "-F", PANES_FORMAT],
                           capture_output=True, text=True, timeout=1)
    except (OSError, subprocess.SubprocessError):
        return {}, {}, {}
    return parse_panes(r.stdout) if r.returncode == 0 else ({}, {}, {})


def pane_screen(pane: str) -> str:
    """The visible text of a tmux pane. It tells us two things the files
    cannot: whether a Claude Code dialog is up (the transcript cannot tell a
    pending permission prompt from a slow tool, and no hook fires when a
    dialog is answered), and which of several hosted sessions the pane is
    showing (its name in the separator)."""
    try:
        r = subprocess.run(["tmux", "capture-pane", "-p", "-t", pane],
                           capture_output=True, text=True, timeout=1)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if r.returncode == 0 else ""


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
    bgslots = SlotMap(os.path.join(os.path.dirname(slots_path), "bgslots.json"), BG_LABELS)
    print(f"claude-rgb: state={state_dir} slots={slots_path} server={host}:{port} device~{match!r}", flush=True)

    client = dev = None
    names: list[str] = []
    last: Optional[list[Colour]] = None
    stats, stats_at = None, -1.0
    viewed: dict[str, float] = {}       # pane -> wall time last focused
    limits = LimitClock()
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
                panes, pane_pids, pane_tags = live_panes()
                sessions = load_sessions(state_dir, max_age, wall, pane_screen, panes, pane_pids,
                                         pane_tags=pane_tags)
                if slots.update(held_ids(sessions, wall, panes)):
                    print(f"claude-rgb: slots {slots.slots}", flush=True)
                write_slot_labels(state_dir, slots)
                if bgslots.update(held_bg_ids(sessions, wall, panes)):
                    print(f"claude-rgb: background {bgslots.slots}", flush=True)
                write_slot_labels(state_dir, bgslots, "bgslots")
                write_targets(state_dir, jump_targets(sessions, slots, bgslots))
                limits.observe(sessions, wall)
                stats = stats_from(sessions, focus, slot_views(sessions, slots, focus, viewed, started),
                                   limits=limits.latest(), bg=bg_views(sessions, bgslots))
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
