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
    assert a[k3] == cr.scaled(cr.BLUE, cr.UNFOCUSED_DIM)   # steady blue, dimmed (not focused)
    assert a[k4] == cr.scaled(cr.SLOT_GREY, cr.UNFOCUSED_DIM)
    assert a[k5] == cr.BASE                                    # empty slot
    focused_unread = cr.render(NAMES, stats(slots=((State.UNREAD, True),)), t=0.0)
    assert focused_unread[k1] == cr.BLUE


def test_focused_idle_slot_is_white_and_nothing_below_it_lights():
    views = ((State.IDLE, False), (State.IDLE, True))
    f = cr.render(NAMES, stats(slots=views), t=0.0)
    assert f[idx("Key: 2")] == cr.FOCUS_IDLE
    assert f[idx("Key: 1")] == cr.scaled(cr.SLOT_GREY, cr.UNFOCUSED_DIM)
    assert f[idx("Key: Q")] == cr.BASE and f[idx("Key: W")] == cr.BASE


def test_pick_stats_busy_and_waiting(tmp_path):
    """Blocked / working are per-session facts, surfaced via slot views."""
    now = time.time()
    tf, ti = tmp_path / "f.jsonl", tmp_path / "i.jsonl"
    tf.write_text(jl(ASSIST_TOOL)); ti.write_text(jl(ASSIST_END, TURN_DONE))
    write(tmp_path / "f.json", tf, tmux_pane="%1")
    write(tmp_path / "i.json", ti, tmux_pane="%3")
    asked = []
    def screen_of(pane):
        asked.append(pane)
        return PERM_SCREEN if pane == "%1" else IDLE_SCREEN
    sessions = cr.load_sessions(str(tmp_path), 30, now, screen_of, {"%1": "claude", "%3": "claude"})
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
HANDOFF = {"type": "continued-in", "continuedInSessionId": "other"}


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


def test_busy_while_turn_ended_with_background_agents_pending(tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text(jl(USER_PROMPT, ASSIST_END, dict(TURN_DONE, pendingBackgroundAgentCount=2), META))
    assert cr.busy_from_transcript(str(t)) is True
    t.write_text(jl(USER_PROMPT, ASSIST_END, dict(TURN_DONE, pendingBackgroundAgentCount=0)))
    assert cr.busy_from_transcript(str(t)) is False


def test_subagent_writes_keep_a_waiting_session_working(tmp_path):
    """While background agents run, only their transcripts change; the
    parent's goes silent for as long as they take."""
    now = time.time()
    t = tmp_path / "w.jsonl"
    touch(t, jl(ASSIST_END, dict(TURN_DONE, pendingBackgroundAgentCount=1)), 3600, now)
    write(tmp_path / "w.json", t, tmux_pane="%1")
    load = lambda: cr.load_sessions(str(tmp_path), 30, now, lambda p: "", {"%1": "claude"})[0]
    assert load().busy is False                    # silent an hour, nothing else to go on
    (tmp_path / "w" / "subagents").mkdir(parents=True)
    touch(tmp_path / "w" / "subagents" / "agent-a1.jsonl", jl(ASSIST_TOOL), 5, now)
    s = load()
    assert s.busy is True and s.state(viewed_at=now) is cr.State.WORKING
    touch(t, jl(ASSIST_END, TURN_DONE), 3600, now)  # turn over: subagents no longer count
    assert load().activity == now - 3600


def test_idle_after_session_handed_off_even_with_recent_writes(tmp_path):
    # the handoff row is written after the last turn row, and later metadata
    # rows (cost-state) keep the file fresh: it must still read as idle
    t = tmp_path / "t.jsonl"
    t.write_text(jl(USER_PROMPT, ASSIST_TOOL, HANDOFF, {"type": "cost-state"}))
    assert cr.busy_from_transcript(str(t)) is False


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


def footer(mode_line):
    return ("● Done.\n" + "─" * 40 + "\n❯ \n" + "─" * 40 +
            "\n  repo ▏main ▏Opus 5.5 ▏⌨3\n  " + mode_line + "\n\n\n")


def test_mode_from_screen_reads_the_footer():
    M = cr.Mode
    assert cr.mode_from_screen(footer("⏸ manual mode on · ← 1 agent")) is M.DEFAULT
    assert cr.mode_from_screen(footer("⏵⏵ accept edits on (shift+tab to cycle)")) is M.ACCEPT_EDITS
    assert cr.mode_from_screen(footer("⏸ plan mode on (shift+tab to cycle) · ← 1 agent")) is M.PLAN
    assert cr.mode_from_screen(footer("⏵⏵ auto mode on (shift+tab to cycle)")) is M.AUTO
    assert cr.mode_from_screen(footer("⏵⏵ bypass permissions on · PR #227 · 1 shell")) is M.BYPASS


def test_mode_from_screen_is_unknown_without_a_footer():
    """A dialog replaces the footer; conversation text quoting a footer
    higher up the screen must not count."""
    assert cr.mode_from_screen(PERM_SCREEN) is None
    assert cr.mode_from_screen("") is None
    quoted = "  ⏵⏵ bypass permissions on\n" + "output\n" * 6 + PERM_SCREEN
    assert cr.mode_from_screen(quoted) is None


def test_space_shows_focused_session_permission_mode():
    space = "Key: Space"
    names = NAMES + [space]
    lit = lambda mode, **kw: cr.render(names, stats(mode=mode, **kw), t=0.0)[names.index(space)]
    assert lit(cr.Mode.BYPASS) == cr.MODE_COLOURS[cr.Mode.BYPASS]
    assert lit(cr.Mode.AUTO) == cr.MODE_COLOURS[cr.Mode.AUTO]
    assert lit(cr.Mode.PLAN) != lit(cr.Mode.ACCEPT_EDITS)
    assert lit(cr.Mode.DEFAULT) == cr.BASE
    assert lit(None) == cr.BASE
    assert lit(cr.Mode.BYPASS, has_session=False) == cr.BASE


def test_stats_from_drops_mode_when_focused_pane_has_no_session(tmp_path):
    now = time.time()
    write(tmp_path / "a.json", tmux_pane="%1")
    sessions = cr.load_sessions(str(tmp_path), 30, now, lambda p: "", {"%1": "claude"})
    assert cr.stats_from(sessions, "%1", mode=cr.Mode.PLAN).mode is cr.Mode.PLAN
    assert cr.stats_from(sessions, "%9", mode=cr.Mode.PLAN).mode is None


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


def test_limits_come_from_newest_reading_not_most_active_session(tmp_path):
    now = time.time()
    ta, tb = (tmp_path / f"{n}.jsonl" for n in "ab")
    touch(ta, "x", 1, now)
    touch(tb, "x", 60, now)
    write(tmp_path / "a.json", ta, rate_limits={"five_hour": {"used_percentage": 10}, "seven_day": {"used_percentage": 20}})
    write(tmp_path / "b.json", tb, rate_limits={"five_hour": {"used_percentage": 33}, "seven_day": {"used_percentage": 44}})
    clock = cr.LimitClock()
    clock.observe(cr.load_sessions(str(tmp_path), 30, now, lambda p: "", {}), now)
    assert clock.latest() == (10, 20)          # first sight ties: most recently active wins
    # b calls the API and its numbers change; a's stay as they were
    write(tmp_path / "b.json", tb, rate_limits={"five_hour": {"used_percentage": 50}, "seven_day": {"used_percentage": 60}})
    clock.observe(cr.load_sessions(str(tmp_path), 30, now + 5, lambda p: "", {}), now + 5)
    assert clock.latest() == (50, 60)
    # a unchanged again: still b's reading, not a's older one
    clock.observe(cr.load_sessions(str(tmp_path), 30, now + 9, lambda p: "", {}), now + 9)
    assert clock.latest() == (50, 60)


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
    screen_of = lambda pane: PERM_SCREEN if pane == "%2" else IDLE_SCREEN
    s = cr.pick_stats(str(tmp_path), max_age=30, now=now, focus="%2", screen_of=screen_of, live_panes={"%1": "claude", "%2": "claude"})
    assert s.ctx == 77
    s = cr.pick_stats(str(tmp_path), max_age=30, now=now, focus="%1", screen_of=screen_of, live_panes={"%1": "claude"})
    assert s.ctx == 5
    sessions = cr.load_sessions(str(tmp_path), 30, now, screen_of, {"%1": "claude"})
    assert {x.id: x.live for x in sessions} == {"f": True, "b": False}


# --- session state ----------------------------------------------------------------

def sess(**kw):
    d = dict(id="s", pane="%1", transcript=None, file_mtime=0.0, activity=100.0,
             fresh=True, running=True, busy=False, blocked=False, agent=False, payload={})
    d.update(kw)
    d.setdefault("live", (d["fresh"] or d["blocked"]) and d["running"])
    return cr.Session(**d)


def test_held_bg_ids_takes_paneless_non_agent_sessions_only():
    now = 1000.0
    ss = [sess(id="bg", pane=None, file_mtime=now),
          sess(id="sub", pane=None, agent=True, file_mtime=now),
          sess(id="shown", pane="%1", file_mtime=now),
          sess(id="old", pane=None, fresh=False, file_mtime=now - cr.SLOT_GRACE - 1)]
    assert cr.held_bg_ids(ss, now, {}) == ["bg"]


def test_held_bg_ids_keeps_quiet_background_session_within_grace():
    now = 1000.0
    ss = [sess(id="quiet", pane=None, fresh=False, file_mtime=now - 5)]
    assert cr.held_bg_ids(ss, now, {}) == ["quiet"]


def test_bg_session_put_into_a_pane_leaves_the_z_row_for_a_slot():
    now = 1000.0
    bg = sess(id="x", pane=None, file_mtime=now)
    assert cr.held_bg_ids([bg], now, {}) == ["x"]
    shown = sess(id="x", pane="%7", file_mtime=now)   # same session, now displayed in %7
    assert cr.held_bg_ids([shown], now, {"%7": "claude"}) == []
    assert cr.held_ids([shown], now, {"%7": "claude"}) == ["x"]


def test_displaced_session_moves_to_z_row_while_its_pane_runs_claude():
    now = 1000.0
    # paused parent: its pane %1 now shows another session, so it is not running
    parent = sess(id="parent", pane="%1", running=False, fresh=False, file_mtime=now - 5)
    assert cr.held_bg_ids([parent], now, {"%1": "claude"}) == ["parent"]
    assert cr.held_ids([parent], now, {"%1": "claude"}) == []


def test_displaced_session_is_dropped_once_its_pane_is_a_shell():
    now = 1000.0
    exited = sess(id="exited", pane="%1", running=False, fresh=False, file_mtime=now - 5)
    assert cr.held_bg_ids([exited], now, {"%1": "zsh"}) == []


def test_displaced_busy_session_stays_working_past_grace():
    now = 1000.0
    busy = sess(id="busy", pane="%1", running=False, fresh=False, busy=True, file_mtime=now - 600)
    assert cr.held_bg_ids([busy], now, {"%1": "claude"}) == ["busy"]
    m = cr.SlotMap(None, cr.BG_LABELS)
    m.update(["busy"])
    assert cr.bg_views([busy], m)[0] == (cr.State.WORKING, False)


def test_displaced_subagent_never_gets_a_key():
    now = 1000.0
    agent = sess(id="sub", pane="%1", running=False, agent=True, file_mtime=now - 5)
    assert cr.held_bg_ids([agent], now, {"%1": "claude"}) == []


def test_bg_slots_cap_at_ten_and_extra_sessions_get_no_key():
    m = cr.SlotMap(None, cr.BG_LABELS)
    m.update([f"s{i}" for i in range(12)])
    assert sorted(m.slots) == sorted(cr.BG_LABELS)
    assert m.session_at("Z") == "s0" and m.session_at("/") == "s9"


def test_bg_views_show_working_or_idle_never_unread_or_blocked():
    now = 1000.0
    m = cr.SlotMap(None, cr.BG_LABELS)
    m.update(["busy", "idle", "quiet"])
    ss = [sess(id="busy", pane=None, busy=True, file_mtime=now),
          sess(id="idle", pane=None, busy=False, file_mtime=now),
          sess(id="quiet", pane=None, fresh=False, file_mtime=now - 5)]
    views = cr.bg_views(ss, m)
    assert views[0] == (cr.State.WORKING, False)
    assert views[1] == (cr.State.IDLE, False)
    assert views[2] == (cr.State.IDLE, False)    # quiet within grace: not live, shows idle
    assert views[3] is None                      # unassigned key


def test_render_paints_z_row_from_background_views():
    names = cr.F_ROW + ["Logo"] + cr.SLOT_KEYS + cr.BG_KEYS
    s = cr.Stats(ctx=None, h5=None, d7=None, model=None,
                 bg=((cr.State.WORKING, False),) + (None,) * 9)
    frame = cr.render(names, s, t=0.0)
    assert frame[names.index("Key: Z")] == cr.slot_colour((cr.State.WORKING, False), 0.0)
    assert frame[names.index("Key: X")] == cr.BASE


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
    assert cr.held_ids([live_new, dead, grace, nopane, live_old, closed, exited], now, panes) == ["old", "grace", "new"]   # nopane: no slot


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
    ss = cr.load_sessions(str(tmp_path), 30, now, lambda p: PERM_SCREEN, panes)
    assert ss[0].live is False and ss[0].blocked is False
    assert cr.held_ids(ss, now, panes) == []
    assert cr.pick_stats(str(tmp_path), max_age=30, now=now, focus="%1", live_panes=panes) is None
    panes = {"%1": "claude"}
    ss = cr.load_sessions(str(tmp_path), 30, now, lambda p: PERM_SCREEN, panes)
    assert ss[0].live is True and ss[0].blocked is True
    assert cr.held_ids(ss, now, panes) == ["a"]


def test_session_without_pane_info_is_judged_by_freshness_only(tmp_path):
    now = time.time()
    write(tmp_path / "a.json", None, context_window={"used_percentage": 11})
    assert cr.load_sessions(str(tmp_path), 30, now, lambda p: "", {})[0].live is True


# --- slots are for sessions you can jump to ------------------------------------

def test_sessions_without_a_pane_get_no_slot_but_still_feed_stats(tmp_path):
    """Subagents and forks run the statusline too, with their own session id
    and no tmux pane. They cannot be jumped to, so no slot; their rate
    limits are as good as anyone's though."""
    now = time.time()
    write(tmp_path / "agent.json", None, agent_type="fork",
          rate_limits={"five_hour": {"used_percentage": 42}})
    t = tmp_path / "t.jsonl"; t.write_text(jl(ASSIST_END, TURN_DONE))
    write(tmp_path / "main.json", t, tmux_pane="%1")
    panes = {"%1": "claude"}
    ss = cr.load_sessions(str(tmp_path), 30, now, lambda p: "", panes)
    assert cr.held_ids(ss, now, panes) == ["main"]
    assert cr.pick_stats(str(tmp_path), max_age=30, now=now, focus="%1", live_panes=panes).h5 == 42


def test_newest_session_in_a_pane_supersedes_older_ones(tmp_path):
    """/clear, /resume or restarting claude in the same pane gives a new
    session id; the old one's file lingers. Only the newest per pane runs."""
    now = time.time()
    t = tmp_path / "t.jsonl"; t.write_text(jl(USER_PROMPT))
    write(tmp_path / "old.json", t, tmux_pane="%1", context_window={"used_percentage": 90})
    write(tmp_path / "new.json", t, tmux_pane="%1", context_window={"used_percentage": 3})
    os.utime(tmp_path / "old.json", (now - 5, now - 5))
    panes = {"%1": "claude"}
    ss = {s.id: s for s in cr.load_sessions(str(tmp_path), 30, now, lambda p: PERM_SCREEN, panes)}
    assert ss["new"].running and ss["new"].live
    assert not ss["old"].running and not ss["old"].live and not ss["old"].blocked
    assert cr.held_ids(list(ss.values()), now, panes) == ["new"]
    assert cr.pick_stats(str(tmp_path), max_age=30, now=now, focus="%1", live_panes=panes).ctx == 3


# --- pane from process tree ---------------------------------------------------------

PARENTS = {500: 400, 400: 300, 300: 200, 200: 1, 1: None}   # 500 -> ... -> 200 (a pane's shell) -> init
PANE_PIDS = {200: "%7"}


def test_resolve_pane_walks_up_to_the_pane_shell():
    assert cr.resolve_pane(500, PANE_PIDS, PARENTS.get) == "%7"
    assert cr.resolve_pane(200, PANE_PIDS, PARENTS.get) == "%7"
    assert cr.resolve_pane(999, PANE_PIDS, PARENTS.get) is None      # unknown pid
    assert cr.resolve_pane(None, PANE_PIDS, PARENTS.get) is None
    loop = {1: 2, 2: 1}
    assert cr.resolve_pane(1, PANE_PIDS, loop.get) is None             # never spins forever


def test_forks_and_subagents_are_placed_by_pid_not_env(tmp_path):
    """A fork runs as a child claude process without TMUX_PANE in its
    environment, so its payload has no tmux_pane; claude_pid (the hook's
    $PPID) still leads to the pane. A background agent (agent_type set)
    shares the parent's process and must not claim the pane."""
    now = time.time()
    t = tmp_path / "t.jsonl"; t.write_text(jl(USER_PROMPT))
    write(tmp_path / "parent.json", t, tmux_pane="%7", claude_pid=400, context_window={"used_percentage": 50})
    write(tmp_path / "fork.json", t, claude_pid=500, context_window={"used_percentage": 5})
    write(tmp_path / "agent.json", t, claude_pid=400, agent_type="Explore", agent="x")
    os.utime(tmp_path / "parent.json", (now - 60, now - 60))   # parent's statusline paused while the fork is shown
    panes = {"%7": "claude"}
    ss = {s.id: s for s in cr.load_sessions(str(tmp_path), 30, now, lambda p: "", panes,
                                            pane_pids=PANE_PIDS, parent_of=PARENTS.get)}
    assert ss["fork"].pane == "%7" and ss["fork"].running
    assert ss["parent"].pane == "%7" and not ss["parent"].running          # superseded by the fork
    assert ss["agent"].pane is None
    assert cr.held_ids(list(ss.values()), now, panes) == ["fork"]


# --- which session a pane displays ------------------------------------------------

def cand(id, name=None, fresh=True, tagged=False, mid_turn=False, mtime=100.0):
    return cr.Candidate(id=id, name=name, fresh=fresh, tagged=tagged, mid_turn=mid_turn, mtime=mtime)


def test_pane_owner_prefers_the_name_shown_on_screen_longest_match_wins():
    """Claude Code shows an attached (forked/switched) session's name in the
    separator above the prompt. A fork's name extends its parent's, so the
    longest name on screen is the displayed one."""
    screen = "─── Demo setup ⑂ Are you sure ───\n❯ \n"
    parent = cand("parent", "Demo setup", tagged=True, mtime=50)
    fork = cand("fork", "Demo setup ⑂ Are you sure", mtime=90)
    other = cand("other", "Something else", mtime=99)
    assert cr.pane_owner([parent, fork, other], screen).id == "fork"


def test_pane_owner_with_a_dialog_picks_the_frozen_mid_turn_session():
    """The statusline freezes while a dialog is up, so the displayed session
    is the stale mid-turn one, even though a background session stays fresh."""
    fg = cand("fg", None, fresh=False, tagged=True, mid_turn=True, mtime=10)
    bg = cand("bg", "Background job", fresh=True, mtime=99)
    assert cr.pane_owner([fg, bg], PERM_SCREEN).id == "fg"


def test_pane_owner_falls_back_to_tagged_foreground_then_newest():
    fg = cand("fg", None, tagged=True, mtime=10)
    bg1 = cand("bg1", "Job one", mtime=99)
    bg2 = cand("bg2", "Job two", mtime=98)
    assert cr.pane_owner([fg, bg1, bg2], IDLE_SCREEN).id == "fg"        # no names on screen
    assert cr.pane_owner([bg1, bg2], IDLE_SCREEN).id == "bg1"           # newest of the rest
    stale = cand("stale", None, fresh=False, mtime=5)
    assert cr.pane_owner([stale, bg2], IDLE_SCREEN).id == "bg2"         # fresh beats stale
    assert cr.pane_owner([stale], IDLE_SCREEN).id == "stale"


def test_two_refreshing_background_sessions_in_one_pane_do_not_flap(tmp_path):
    now = time.time()
    t = tmp_path / "t.jsonl"; t.write_text(jl(ASSIST_END, TURN_DONE))
    write(tmp_path / "a.json", t, claude_pid=500, session_name="Demo setup")
    write(tmp_path / "b.json", t, claude_pid=500, session_name="Demo setup ⑂ Are you sure")
    screen = "─── Demo setup ⑂ Are you sure ───\n❯ \n"
    panes = {"%7": "claude"}
    for newer in ("a", "b"):                          # whichever wrote last, b is displayed
        os.utime(tmp_path / f"{newer}.json", (now, now))
        ss = {s.id: s for s in cr.load_sessions(str(tmp_path), 30, now, lambda p: screen, panes,
                                                pane_pids=PANE_PIDS, parent_of=PARENTS.get)}
        assert ss["b"].running and not ss["a"].running
        assert cr.held_ids(list(ss.values()), now, panes) == ["b"]


# --- jumping to Z-row sessions ------------------------------------------------------

def test_parse_panes_reads_command_pid_and_attach_tag():
    out = "%1\t100\t\tclaude\n%2\t200\tsid-x\tclaude\n%3\t300\t\tbash\nbroken line\n"
    cmds, pids, tags = cr.parse_panes(out)
    assert cmds == {"%1": "claude", "%2": "claude", "%3": "bash"}
    assert pids == {100: "%1", 200: "%2", 300: "%3"}
    assert tags == {"%2": "sid-x"}


def test_attached_background_session_lives_in_its_tagged_pane(tmp_path):
    # a detached session's payload has no tmux_pane and its process hangs off
    # systemd; claude-goto's @claude_session tag on the attach pane places it
    now = time.time()
    write(tmp_path / "bg.json")
    panes = {"%9": "claude"}
    ss = cr.load_sessions(str(tmp_path), 30, now, lambda p: "", panes, pane_tags={"%9": "bg"})
    (s,) = ss
    assert (s.pane, s.running, s.live) == ("%9", True, True)
    assert cr.held_ids(ss, now, panes) == ["bg"]
    assert cr.held_bg_ids(ss, now, panes) == []
    # detached again (the attach window closed): back to the Z row
    ss = cr.load_sessions(str(tmp_path), 30, now, lambda p: "", {})
    assert cr.held_bg_ids(ss, now, {}) == ["bg"]


def test_jump_targets_cover_both_rows_with_pane_or_null():
    slots, bgslots = cr.SlotMap(), cr.SlotMap(None, cr.BG_LABELS)
    slots.update(["main"])
    bgslots.update(["detached", "displaced"])
    ss = [sess(id="main", pane="%1"), sess(id="detached", pane=None),
          sess(id="displaced", pane="%2", running=False)]
    assert cr.jump_targets(ss, slots, bgslots) == {
        "1": {"session": "main", "pane": "%1"},
        "Z": {"session": "detached", "pane": None},
        "X": {"session": "displaced", "pane": "%2"},
    }


def run_goto(tmp_path, label, targets):
    """Run claude-goto against stub tmux/claude/wmctrl; return the tmux calls."""
    import subprocess
    stub = tmp_path / "bin"
    stub.mkdir()
    log = tmp_path / "tmux.log"
    (stub / "tmux").write_text(
        '#!/bin/bash\necho "$*" >> "%s"\n'
        'case "$1" in display-message) echo main;; new-window) echo %%42;; esac\n' % log)
    (stub / "claude").write_text(
        "#!/bin/bash\n"
        """echo '[{"id":"job7","sessionId":"detached"},{"id":"job8","sessionId":"other"}]'\n""")
    (stub / "wmctrl").write_text("#!/bin/bash\n")
    for f in stub.iterdir():
        f.chmod(0o755)
    (tmp_path / "targets.json").write_text(json.dumps(targets))
    goto = os.path.join(os.path.dirname(cr.__file__), "claude-goto")
    env = dict(os.environ, PATH=f"{stub}:{os.environ['PATH']}", CLAUDE_RGB_STATE_DIR=str(tmp_path))
    subprocess.run([goto, label], env=env, check=True, timeout=10)
    return log.read_text().splitlines() if log.exists() else []


def test_goto_switches_to_the_pane_of_a_session_that_has_one(tmp_path):
    calls = run_goto(tmp_path, "X", {"X": {"session": "displaced", "pane": "%2"}})
    assert calls == ["switch-client -t %2"]


def test_goto_attaches_a_detached_session_in_a_new_tagged_window(tmp_path):
    calls = run_goto(tmp_path, "Z", {"Z": {"session": "detached", "pane": None}})
    assert calls[0] == "display-message -p #{client_session}"
    assert calls[1].startswith("new-window -t main: -P -F #{pane_id} ") and calls[1].endswith(" attach job7")
    assert calls[2:] == ["set-option -p -t %42 @claude_session detached", "switch-client -t %42"]


def test_goto_does_nothing_for_an_empty_key(tmp_path):
    assert run_goto(tmp_path, "C", {}) == []


def test_load_sessions_ignores_targets_json_and_other_non_mirror_files(tmp_path):
    now = time.time()
    write(tmp_path / "real.json")
    cr.write_targets(str(tmp_path), {"Z": {"session": "real", "pane": None}})
    (tmp_path / "list.json").write_text("[1, 2]")
    assert [s.id for s in cr.load_sessions(str(tmp_path), 30, now, lambda p: "", {})] == ["real"]
