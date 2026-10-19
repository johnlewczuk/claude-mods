"""Tests for the pure logic of claude_rgb (no OpenRGB / tmux)."""
import json
import os
import time

import claude_rgb as cr
from claude_rgb import State

NAMES = ["", "Key: Escape", ""] + [f"Key: F{i}" for i in range(1, 13)] + ["Logo"] + cr.SLOT_KEYS + [
    "Key: A", "Key: Tab", "Key: [", "Key: ]"] + cr.NUMPAD + cr.NAV + [f"Key: {c}" for c in "QWERTYUIOP"]


def idx(name):
    return NAMES.index(name)


def stats(**kw):
    s = dict(ctx=None, h5=None, d7=None, model=None, has_session=True, slots=())
    s.update(kw)
    return cr.Stats(**s)


# --- bars -------------------------------------------------------------------

def test_lit_count_endpoints_and_rounding():
    assert cr.lit_count(0, 12) == 0
    assert cr.lit_count(100, 12) == 12
    assert cr.lit_count(None, 12) is None
    assert cr.lit_count(1, 12) == 1
    assert cr.lit_count(50, 12) == 6
    assert cr.lit_count(51, 12) == 7
    assert cr.lit_count(150, 10) == 10


def test_f_row_shows_context_usage_with_ramp_colour():
    frame = cr.render(NAMES, stats(ctx=50), t=0.0)
    assert frame[idx("Key: F6")] == cr.GREEN
    assert frame[idx("Key: F7")] == cr.BASE
    assert cr.render(NAMES, stats(ctx=70), t=0.0)[idx("Key: F1")] == cr.AMBER
    assert cr.render(NAMES, stats(ctx=85), t=0.0)[idx("Key: F1")] == cr.RED


def test_numpad_shows_five_hour_usage():
    frame = cr.render(NAMES, stats(h5=30), t=0.0)
    assert frame[idx("Key: Number Pad 1")] == cr.CYAN
    assert frame[idx("Key: Number Pad 3")] == cr.CYAN
    assert frame[idx("Key: Number Pad 4")] == cr.BASE
    assert frame[idx("Key: Number Pad 0")] == cr.BASE
    assert cr.render(NAMES, stats(h5=95), t=0.0)[idx("Key: Number Pad 1")] == cr.RED


def test_nav_cluster_shows_seven_day_usage():
    frame = cr.render(NAMES, stats(d7=10), t=0.0)
    assert frame[idx("Key: Insert")] == cr.VIOLET
    assert frame[idx("Key: Home")] == cr.BASE
    assert cr.render(NAMES, stats(d7=100), t=0.0)[idx("Key: Page Down")] == cr.RED


def test_unknown_rate_limit_renders_as_unknown_not_zero():
    frame = cr.render(NAMES, stats(h5=None), t=0.0)
    for k in cr.NUMPAD:
        assert frame[idx(k)] == cr.UNKNOWN


def test_logo_colour_follows_model():
    assert cr.render(NAMES, stats(model="Fable"), t=0.0)[idx("Logo")] == cr.MODEL_COLOURS["fable"]
    assert cr.render(NAMES, stats(model="Opus 5.5"), t=0.0)[idx("Logo")] == cr.MODEL_COLOURS["opus"]
    assert cr.render(NAMES, stats(model=None), t=0.0)[idx("Logo")] == cr.WHITE


def test_alarm_pulses_base_keys_red_and_lights_escape():
    quiet = cr.render(NAMES, stats(h5=50), t=0.0)
    assert quiet[idx("Key: A")] == cr.BASE
    assert quiet[idx("Key: Escape")] == cr.BASE
    hot_a = cr.render(NAMES, stats(h5=95), t=0.0)
    hot_b = cr.render(NAMES, stats(h5=95), t=0.5)
    assert hot_a[idx("Key: Escape")] == cr.RED
    assert hot_a[idx("Key: A")] != hot_b[idx("Key: A")]
    assert hot_a[idx("Key: A")][0] > hot_a[idx("Key: A")][1]


def test_no_focused_session_darkens_context_and_logo_but_keeps_rate_limits():
    f = cr.render(NAMES, stats(ctx=50, h5=30, model="Fable", has_session=False,
                               slots=((State.WORKING, False),)), t=0.0)
    assert f[idx("Key: F1")] == cr.BASE
    assert f[idx("Logo")] == cr.IDLE_LOGO
    assert f[idx("Key: Number Pad 1")] == cr.CYAN
    assert f[idx("Key: 1")] != cr.BASE


def test_idle_frame_is_all_base_with_dim_logo():
    frame = cr.render(NAMES, None, t=0.0)
    assert frame[idx("Key: F1")] == cr.BASE
    assert frame[idx("Logo")] == cr.IDLE_LOGO
    assert len(frame) == len(NAMES)


# --- slot keys ----------------------------------------------------------------

def test_slot_keys_show_state_colours_and_focus_brightness():
    views = ((State.WORKING, True), (State.BLOCKED, False), (State.UNREAD, False),
             (State.IDLE, False), None)
    a = cr.render(NAMES, stats(slots=views), t=0.0)
    b = cr.render(NAMES, stats(slots=views), t=0.7)
    k1, k2, k3, k4, k5 = (idx(f"Key: {c}") for c in "12345")
    assert a[k1][0] > a[k1][2] and a[k1] != b[k1]              # orange, breathing
    assert a[k2][2] > a[k2][0] and a[k2] != b[k2]              # blue, breathing
    assert a[k3] == cr.scaled(cr.SLOT_UNREAD, cr.UNFOCUSED_DIM)   # ice blue, dimmed (not focused)
    assert a[k4] == cr.scaled(cr.SLOT_GREY, cr.UNFOCUSED_DIM)
    assert a[k5] == cr.BASE                                    # empty slot
    focused_unread = cr.render(NAMES, stats(slots=((State.UNREAD, True),)), t=0.0)
    assert focused_unread[k1] == cr.SLOT_UNREAD


def test_focused_slot_lights_the_two_keys_below_it_as_a_triangle():
    views = ((State.IDLE, False), (State.UNREAD, True), (State.IDLE, False))
    f = cr.render(NAMES, stats(slots=views), t=0.0)
    assert f[idx("Key: Q")] == cr.SLOT_UNREAD and f[idx("Key: W")] == cr.SLOT_UNREAD   # under "2"
    assert f[idx("Key: Tab")] == cr.BASE and f[idx("Key: E")] == cr.BASE          # not under "2"
    assert f[idx("Key: 1")] == cr.scaled(cr.SLOT_GREY, cr.UNFOCUSED_DIM)
    first = cr.render(NAMES, stats(slots=((State.IDLE, True),)), t=0.0)
    assert first[idx("Key: Tab")] == cr.SLOT_GREY and first[idx("Key: Q")] == cr.SLOT_GREY
    last = cr.render(NAMES, stats(slots=(None,) * 11 + ((State.IDLE, True),)), t=0.0)
    assert last[idx("Key: [")] == cr.SLOT_GREY and last[idx("Key: ]")] == cr.SLOT_GREY
    nothing = cr.render(NAMES, stats(slots=((State.IDLE, False),)), t=0.0)
    assert nothing[idx("Key: Q")] == cr.BASE


def test_pick_stats_busy_and_waiting(tmp_path):
    """Blocked / working are per-session facts, surfaced via slot views."""
    now = time.time()
    tf, ti = tmp_path / "f.jsonl", tmp_path / "i.jsonl"
    tf.write_text(jl(ASSIST_TOOL)); ti.write_text(jl(ASSIST_END, TURN_DONE))
    write(tmp_path / "f.json", tf, tmux_pane="%1")
    write(tmp_path / "i.json", ti, tmux_pane="%3")
    asked = []
    def dialog_open(pane):
        asked.append(pane)
        return pane == "%1"
    sessions = cr.load_sessions(str(tmp_path), 30, now, dialog_open, {"%1": "claude", "%3": "claude"})
    by = {x.id: x for x in sessions}
    assert (by["f"].busy, by["f"].blocked, by["i"].busy, by["i"].blocked) == (True, True, False, False)
    assert "%3" not in asked                       # idle sessions are never screen-scraped


# --- transcript ---------------------------------------------------------------

def jl(*entries):
    return "".join(json.dumps(e) + "\n" for e in entries)

USER_PROMPT = {"type": "user", "message": {"role": "user", "content": "do the thing"}}
TOOL_RESULT = {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result"}]}}
ASSIST_TOOL = {"type": "assistant", "message": {"role": "assistant", "stop_reason": "tool_use", "content": [{"type": "tool_use"}]}}
ASSIST_END = {"type": "assistant", "message": {"role": "assistant", "stop_reason": "end_turn", "content": [{"type": "text"}]}}
TURN_DONE = {"type": "system", "subtype": "turn_duration"}
META = {"type": "ai-title"}
INTERRUPTED = {"type": "user", "message": {"role": "user", "content": "[Request interrupted by user]"}}


def test_busy_when_turn_in_progress(tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text(jl(USER_PROMPT, {"type": "api-request"}))
    assert cr.busy_from_transcript(str(t)) is True
    t.write_text(jl(USER_PROMPT, ASSIST_TOOL))
    assert cr.busy_from_transcript(str(t)) is True
    t.write_text(jl(ASSIST_TOOL, TOOL_RESULT, META))
    assert cr.busy_from_transcript(str(t)) is True


def test_idle_after_turn_ends_or_interrupt(tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text(jl(USER_PROMPT, ASSIST_END, TURN_DONE, META, META))
    assert cr.busy_from_transcript(str(t)) is False
    t.write_text(jl(USER_PROMPT, ASSIST_TOOL, INTERRUPTED))
    assert cr.busy_from_transcript(str(t)) is False
    assert cr.busy_from_transcript(str(tmp_path / "nope.jsonl")) is False


def test_stale_transcript_is_not_busy(tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text(jl(USER_PROMPT))
    old = time.time() - 3600
    os.utime(t, (old, old))
    assert cr.busy_from_transcript(str(t)) is False
    assert cr.busy_from_transcript(str(t), max_age=None) is True


PERM_SCREEN = " Do you want to proceed?\n ❯ 1. Yes\n   2. No\n Esc to cancel · Tab to amend\n"
QUESTION_SCREEN = "Do you prefer red or blue?\n❯ 1. Red\n  2. Blue\nEnter to select · ↑/↓ to navigate · Esc to cancel\n"
TRUST_SCREEN = " ❯ No, exit\n   Yes, I trust this folder\n Enter to confirm · Esc to cancel\n"
IDLE_SCREEN = "● Done. Press Esc to cancel next time.\n❯ run it with the 1. first option\n  ⏵⏵ bypass permissions on\n"


def test_dialog_signature():
    assert cr.has_dialog(PERM_SCREEN)
    assert cr.has_dialog(QUESTION_SCREEN)
    assert cr.has_dialog(TRUST_SCREEN)
    assert not cr.has_dialog(IDLE_SCREEN)
    assert not cr.has_dialog("")


# --- sessions -------------------------------------------------------------------

def write(path, transcript=None, **payload):
    payload.setdefault("session_id", path.stem)
    if transcript is not None:
        payload["transcript_path"] = str(transcript)
    path.write_text(json.dumps(payload))


def touch(path, text, age, now):
    path.write_text(text)
    os.utime(path, (now - age, now - age))


def test_pick_stats_prefers_focused_pane_then_newest_transcript(tmp_path):
    now = time.time()
    ta, tb = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    touch(ta, "x", 5, now); touch(tb, "y", 300, now)
    write(tmp_path / "a.json", ta, tmux_pane="%1", context_window={"used_percentage": 11}, model={"display_name": "Fable"})
    write(tmp_path / "b.json", tb, tmux_pane="%2", context_window={"used_percentage": 99}, model={"display_name": "Opus"})
    os.utime(tmp_path / "b.json", (now, now))   # b's statusline wrote most recently -- irrelevant
    panes = {"%1": "claude", "%2": "claude"}
    s = cr.pick_stats(str(tmp_path), max_age=30, now=now, live_panes=panes)
    assert (s.ctx, s.model) == (11, "Fable")
    assert cr.pick_stats(str(tmp_path), max_age=30, now=now, focus="%2", live_panes=panes).ctx == 99
    # a focused pane with no Claude session shows no session (not someone else's)
    s = cr.pick_stats(str(tmp_path), max_age=30, now=now, focus="%9", live_panes=panes)
    assert (s.has_session, s.ctx, s.model) == (False, None, None)
    assert s.h5 is None and s.d7 is None or True          # rate limits still come from any session


def test_pick_stats_takes_rate_limits_from_most_recently_active_session_that_has_them(tmp_path):
    now = time.time()
    ta, tb, tc = (tmp_path / f"{n}.jsonl" for n in "abc")
    for t, age in ((ta, 1), (tb, 60), (tc, 600)):
        touch(t, "x", age, now)
    write(tmp_path / "a.json", ta, context_window={"used_percentage": 11})
    write(tmp_path / "b.json", tb, rate_limits={"five_hour": {"used_percentage": 33}, "seven_day": {"used_percentage": 44}})
    write(tmp_path / "c.json", tc, rate_limits={"five_hour": {"used_percentage": 1}, "seven_day": {"used_percentage": 2}})
    os.utime(tmp_path / "c.json", (now, now))
    s = cr.pick_stats(str(tmp_path), max_age=30, now=now)
    assert (s.ctx, s.h5, s.d7, s.model) == (11, 33, 44, None)


def test_pick_stats_ignores_stale_missing_and_half_written(tmp_path):
    write(tmp_path / "a.json", None, context_window={"used_percentage": 11})
    assert cr.pick_stats(str(tmp_path), max_age=30, now=time.time() + 60) is None
    assert cr.pick_stats(str(tmp_path / "missing"), max_age=30) is None
    (tmp_path / "x.json").write_text('{"context_window": {"used_per')
    assert cr.pick_stats(str(tmp_path), max_age=30).ctx == 11


def test_blocked_session_with_frozen_statusline_still_counts(tmp_path):
    """Claude Code stops refreshing the statusline while a dialog is open."""
    now = time.time()
    tf, tb = tmp_path / "f.jsonl", tmp_path / "b.jsonl"
    tf.write_text(jl(ASSIST_END, TURN_DONE)); touch(tb, jl(ASSIST_TOOL), 3600, now)
    write(tmp_path / "f.json", tf, tmux_pane="%1", context_window={"used_percentage": 5})
    write(tmp_path / "b.json", tb, tmux_pane="%2", context_window={"used_percentage": 77})
    os.utime(tmp_path / "b.json", (now - 600, now - 600))
    dialog_open = lambda pane: pane == "%2"
    s = cr.pick_stats(str(tmp_path), max_age=30, now=now, focus="%2", dialog_open=dialog_open, live_panes={"%1": "claude", "%2": "claude"})
    assert s.ctx == 77
    s = cr.pick_stats(str(tmp_path), max_age=30, now=now, focus="%1", dialog_open=dialog_open, live_panes={"%1": "claude"})
    assert s.ctx == 5
    sessions = cr.load_sessions(str(tmp_path), 30, now, dialog_open, {"%1": "claude"})
    assert {x.id: x.live for x in sessions} == {"f": True, "b": False}


# --- session state ----------------------------------------------------------------

def sess(**kw):
    d = dict(id="s", pane="%1", transcript=None, file_mtime=0.0, activity=100.0,
             fresh=True, running=True, busy=False, blocked=False, payload={})
    d.update(kw)
    d.setdefault("live", (d["fresh"] or d["blocked"]) and d["running"])
    return cr.Session(**d)


def test_session_state_precedence():
    assert sess(busy=True, blocked=True).state(viewed_at=0) is State.BLOCKED
    assert sess(busy=True).state(viewed_at=0) is State.WORKING
    assert sess(activity=100).state(viewed_at=50) is State.UNREAD     # finished after last look
    assert sess(activity=100).state(viewed_at=150) is State.IDLE      # seen since
    assert sess(activity=100, pane=None).state(viewed_at=0) is State.IDLE   # cannot be "looked at"


# --- slot map ----------------------------------------------------------------------

def test_slotmap_assigns_first_free_and_is_stable(tmp_path):
    m = cr.SlotMap(str(tmp_path / "slots.json"))
    assert m.update(["a", "b"]) is True
    assert (m.label_of("a"), m.label_of("b")) == ("1", "2")
    assert m.update(["b", "a"]) is False                    # order of held does not reshuffle
    assert m.update(["b", "c"]) is True                     # a gone: slot 1 freed, c takes it
    assert (m.label_of("a"), m.label_of("b"), m.label_of("c")) == (None, "2", "1")
    reloaded = cr.SlotMap(str(tmp_path / "slots.json"))    # persisted across restarts
    assert reloaded.slots == m.slots
    assert reloaded.session_at("2") == "b"


def test_slotmap_overflow_leaves_extra_sessions_unassigned():
    m = cr.SlotMap()
    ids = [f"s{i}" for i in range(15)]
    m.update(ids)
    assert [m.label_of(i) for i in ids[:12]] == cr.SLOT_LABELS
    assert all(m.label_of(i) is None for i in ids[12:])
    m.update(ids[1:])                                       # s0 ends: next unassigned gets its key
    assert m.label_of("s12") == "1"


def test_slotmap_tolerates_bad_file(tmp_path):
    p = tmp_path / "slots.json"
    p.write_text("not json")
    assert cr.SlotMap(str(p)).slots == {}
    p.write_text(json.dumps({"slots": {"1": "a", "zz": "b", "2": 5}}))
    assert cr.SlotMap(str(p)).slots == {"1": "a"}


def test_held_ids_keeps_live_and_grace_sessions_in_arrival_order():
    now = 10_000.0
    live_new = sess(id="new", pane="%1", file_mtime=now - 1)
    live_old = sess(id="old", pane="%2", file_mtime=now - 5000, fresh=False, blocked=True)
    grace = sess(id="grace", pane="%3", file_mtime=now - 40, fresh=False)
    nopane = sess(id="nopane", pane=None, file_mtime=now - 40, fresh=False)
    dead = sess(id="dead", pane="%4", file_mtime=now - 3600, fresh=False)
    closed = sess(id="closed", pane="%9", file_mtime=now - 5, fresh=False, running=False)   # pane vanished
    exited = sess(id="exited", pane="%5", file_mtime=now - 5, fresh=True, running=False)   # pane is a shell now
    panes = {"%1": "claude", "%2": "claude", "%3": "claude", "%4": "claude", "%5": "bash"}
    assert cr.held_ids([live_new, dead, grace, nopane, live_old, closed, exited], now, panes) == ["old", "grace", "nopane", "new"]


def test_slot_views_follow_state_focus_and_grace(tmp_path):
    m = cr.SlotMap()
    a = sess(id="a", pane="%1", busy=True)
    b = sess(id="b", pane="%2", activity=500)
    c = sess(id="c", pane="%3", fresh=False, file_mtime=0)       # grace period
    m.update(["a", "b", "c"])
    views = cr.slot_views([a, b, c], m, focus="%1", viewed={"%2": 400}, default_viewed=1000)
    assert views[0] == (State.WORKING, True)
    assert views[1] == (State.UNREAD, False)                     # b finished after %2 was last viewed
    assert views[2] == (State.IDLE, False)
    assert views[3] is None
    views = cr.slot_views([a, b, c], m, focus=None, viewed={}, default_viewed=1000)
    assert views[1] == (State.IDLE, False)                       # never viewed since start: seen


def test_write_slot_labels_creates_and_removes_files(tmp_path):
    m = cr.SlotMap(); m.update(["a", "b"])
    cr.write_slot_labels(str(tmp_path), m)
    assert (tmp_path / "slots" / "a").read_text() == "1\n"
    assert (tmp_path / "slots" / "b").read_text() == "2\n"
    m.update(["b"])
    cr.write_slot_labels(str(tmp_path), m)
    assert not (tmp_path / "slots" / "a").exists()
    assert (tmp_path / "slots" / "b").read_text() == "2\n"


# --- exited sessions ------------------------------------------------------------

def test_session_whose_pane_no_longer_runs_claude_is_dead(tmp_path):
    """After /exit the pane survives as a shell and the statusline's last
    file stays fresh for a while; the pane's foreground command is the
    truth. Claude's tool subprocesses never take the tty foreground, so
    `claude` stays the pane command throughout a turn."""
    now = time.time()
    t = tmp_path / "t.jsonl"; t.write_text(jl(USER_PROMPT))
    write(tmp_path / "a.json", t, tmux_pane="%1", context_window={"used_percentage": 11})
    panes = {"%1": "bash"}
    ss = cr.load_sessions(str(tmp_path), 30, now, lambda p: True, panes)
    assert ss[0].live is False and ss[0].blocked is False
    assert cr.held_ids(ss, now, panes) == []
    assert cr.pick_stats(str(tmp_path), max_age=30, now=now, focus="%1", live_panes=panes) is None
    panes = {"%1": "claude"}
    ss = cr.load_sessions(str(tmp_path), 30, now, lambda p: True, panes)
    assert ss[0].live is True and ss[0].blocked is True
    assert cr.held_ids(ss, now, panes) == ["a"]


def test_session_without_pane_info_is_judged_by_freshness_only(tmp_path):
    now = time.time()
    write(tmp_path / "a.json", None, context_window={"used_percentage": 11})
    assert cr.load_sessions(str(tmp_path), 30, now, lambda p: False, {})[0].live is True
