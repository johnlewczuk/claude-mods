#!/bin/bash
# Minimal adaptive statusline for Claude Code.
#
#   myproject ▏main ▏Opus ▏ctx 38% ▏5h 12%
#
# Always shown: path, context %, 5h usage  (priority 0 -- never trimmed).
# Shown when relevant, dropped right-to-left if the line will not fit:
#   branch (brown when the work tree is dirty), model, keyboard slot (⌨3),
#   7d >= 50%, fast mode, thinking off,
#   non-default output style, PR number.
# A reset countdown appears next to 5h once it is >= 70%, or once the
# window has 2h or less remaining (whichever comes first).
#
# One jq process per render -- no whoami/hostname/git forks. This runs at
# statusLine.refreshInterval, currently 1s.

input=$(cat)
rgbslot=""
rgbbg=""

# Mirror the raw payload for the keyboard-RGB daemon (claude-rgb.service,
# ~/.local/opt/openrgb-claude). One file per session so concurrent sessions do
# not clobber each other; the daemon follows the newest. session_id is pulled
# with a bash regex -- no extra jq fork. mv gives the daemon an atomic swap.
_rgbdir="${XDG_RUNTIME_DIR:-/tmp}/claude-rgb"
if [ -d "$_rgbdir" ] && [[ $input =~ \"session_id\":\"([A-Za-z0-9_-]+)\" ]]; then
    _rgbsid="${BASH_REMATCH[1]}"
    _rgbf="$_rgbdir/$_rgbsid.json"
    # Tag the payload with our tmux pane so the daemon can follow pane focus,
    # and with claude's pid so forks and subagents, whose environment lacks
    # TMUX_PANE, can still be placed by walking the process tree. Claude runs
    # the statusline as claude -> bash -c wrapper -> this script, so claude is
    # $PPID's parent: field 4 of /proc/$PPID/stat (a read, not a fork).
    _rgbpid=$PPID
    read -r _ _ _ _rgbpid _ < "/proc/$PPID/stat" 2>/dev/null || _rgbpid=$PPID
    _rgbin="{\"claude_pid\":$_rgbpid,${input#\{}"
    [[ ${TMUX_PANE:-} =~ ^%[0-9]+$ ]] && _rgbin="{\"tmux_pane\":\"$TMUX_PANE\",${_rgbin#\{}"
    printf '%s' "$_rgbin" > "$_rgbf.$$" 2>/dev/null && mv -f "$_rgbf.$$" "$_rgbf" 2>/dev/null
    # The daemon answers with this session's keyboard slot (Ctrl+Alt+<key>).
    [ -r "$_rgbdir/slots/$_rgbsid" ] && read -r rgbslot < "$_rgbdir/slots/$_rgbsid"
    # Background sessions (no pane) get a Z-row key instead.
    [ -r "$_rgbdir/bgslots/$_rgbsid" ] && read -r rgbbg < "$_rgbdir/bgslots/$_rgbsid"
fi

# Host chip only when remote; on the workstation it is constant noise.
host=""
[ -n "$SSH_CONNECTION" ] && host="${HOSTNAME:-$(cat /etc/hostname 2>/dev/null)}"

# Branch: the payload carries workspace.repo.{host,owner,name} but no branch,
# so read .git/HEAD directly. Pure bash, no subprocess -- this runs every second.
# A .git *file* (rather than dir) means a linked worktree or submodule.
gitbranch=""; wtflag=""
_d="$PWD"
while [ -n "$_d" ] && [ "$_d" != "/" ] && [ ! -e "$_d/.git" ]; do _d="${_d%/*}"; done
_gd=""
if [ -d "$_d/.git" ]; then
    _gd="$_d/.git"
elif [ -f "$_d/.git" ]; then
    read -r _ _gd < "$_d/.git" 2>/dev/null   # "gitdir: /path/to/worktrees/name"
    wtflag="1"
fi
if [ -n "$_gd" ] && [ -r "$_gd/HEAD" ]; then
    read -r _head < "$_gd/HEAD" 2>/dev/null
    case "$_head" in
        "ref: refs/heads/"*) gitbranch="${_head#ref: refs/heads/}" ;;
        "")                  ;;
        *)                   gitbranch="${_head:0:7}" ;;   # detached HEAD
    esac
fi

# Dirty working tree. This is the one thing that genuinely needs git, so the
# result is cached and refreshed by a DETACHED background job -- the render
# itself only reads a small file and never blocks. Cache holds "<epoch> <0|1>";
# the timestamp is stored *in* the file because bash has no builtin stat.
dirty="0"
if [ -n "$_gd" ]; then
    _cdir="${XDG_CACHE_HOME:-$HOME/.cache}/claude-statusline"
    _cf="$_cdir/${_d//\//_}.dirty"
    _ts=0
    [ -r "$_cf" ] && read -r _ts dirty < "$_cf" 2>/dev/null
    printf -v _now '%(%s)T' -1
    case "$_ts" in ''|*[!0-9]*) _ts=0 ;; esac
    case "$dirty" in 0|1) ;; *) dirty="0" ;; esac
    if [ $(( _now - _ts )) -ge 5 ]; then
        ( mkdir -p "$_cdir" 2>/dev/null
          if [ -n "$(git -C "$_d" --no-optional-locks status --porcelain 2>/dev/null | head -c 1)" ]
            then _v=1; else _v=0; fi
          printf '%s %s\n' "$_now" "$_v" > "$_cf.$$" 2>/dev/null && mv -f "$_cf.$$" "$_cf" 2>/dev/null
        ) >/dev/null 2>&1 &
        disown 2>/dev/null
    fi
fi

# No width is supplied in the payload and there is usually no tty, so this
# lands on 80 unless overridden. Export CLAUDE_STATUSLINE_COLS to widen.
cols=${CLAUDE_STATUSLINE_COLS:-$(tput cols 2>/dev/null || echo 80)}
case "$cols" in ''|*[!0-9]*) cols=80 ;; esac

printf '%s' "$input" | jq -j \
  --arg home "$HOME" --arg sshhost "$host" --argjson cols "$cols" \
  --arg gitbranch "$gitbranch" --arg wtflag "$wtflag" --arg dirty "$dirty" --arg rgbslot "$rgbslot" --arg rgbbg "$rgbbg" '
  def c($n): "\u001b[38;5;\($n)m";
  def b: "\u001b[1m";
  def r: "\u001b[0m";
  def dim: c(240);

  # healthy stays grey; colour only appears as a value climbs
  def ramp($v; $w; $x):
    if $v == null then 245 elif $v >= $x then 174 elif $v >= $w then 179 else 245 end;
  def pct($v): if $v == null then "—" else "\($v|round)%" end;

  def clip($n): if length > $n then "⋯" + .[-($n-1):] else . end;

  # Branches read better clipped from the tail: feature/deep-branch-n⋯
  def tailclip($n): if length > $n then .[0:$n-1] + "⋯" else . end;

  # Clip a path without losing its head: myproject/a/b/c/d -> myproject/⋯/d
  def pathclip($n):
    if length <= $n then .
    else (split("/")) as $s
      | if ($s|length) <= 2 then clip($n)
        else ($s[0] + "/⋯/" + $s[-1]) as $t
          | if ($t|length) <= $n then $t else clip($n) end
        end
    end;

  # Anchor on the project/repo name so "which repo" is never ambiguous:
  #   $HOME                               -> ~
  #   ~/repos/myproject                   -> myproject
  #   ~/repos/myproject/svc/api           -> myproject/svc/api
  # Paths outside the project fall back to a home-relative form.
  def shortpath($proj):
    . as $d
    | if $d == $home then "~"
      elif ($proj|length) > 0 and ($d == $proj or ($d|startswith($proj + "/")))
        then (($proj|split("/")|last) + $d[($proj|length):])
      elif ($home|length) > 0 and ($d|startswith($home + "/"))
        then "~" + $d[($home|length):]
      else $d end
    | pathclip(26);

  . as $in
  | ($in.workspace.current_dir // $in.cwd // "") as $cwd
  | (if $wtflag != "" then $wtflag
     else ($in.worktree.name // $in.workspace.git_worktree.name // null) end) as $wt
  | (if $gitbranch != "" then $gitbranch
     else ($in.worktree.branch // $in.workspace.git_worktree.branch // null) end) as $branch
  | ($in.model.display_name // null) as $model
  | ($in.context_window.used_percentage // null) as $ctx
  | ($in.rate_limits.five_hour.used_percentage // null) as $h5
  | ($in.rate_limits.seven_day.used_percentage // null) as $d7
  | ($in.output_style.name // "default") as $style
  | ($in.fast_mode // false) as $fast
  | (($in.thinking.enabled) != false) as $think
  | ($in.pr.number // null) as $pr
  | ($in.rate_limits.five_hour.resets_at // null) as $reset

  # seconds until the 5h window resets; tolerate ISO-with-ms, epoch, or junk
  | (if $reset == null then null
     elif ($reset|type) == "number" then ($reset - now)
     else (try (($reset | sub("\\.[0-9]+Z$"; "Z") | fromdateiso8601) - now) catch null)
     end) as $rsec
  | (if $rsec == null or $rsec <= 0 then null
     else (($rsec/60)|floor) as $m
       | (if $m >= 60 then "\(($m/60)|floor)h\($m%60)m" else "\($m)m" end)
     end) as $rtxt
  | (if ($rtxt != null and (($h5 != null and $h5 >= 70) or $rsec <= 7200)) then " ↻ " + $rtxt else "" end) as $rsuf

  # {prio, plain, styled} -- prio 0 is protected, higher numbers are shed first
  | [
      (if $sshhost != "" then
         {prio:1, plain:$sshhost, styled:(c(114) + $sshhost + r)} else empty end),

      (($cwd|shortpath($in.workspace.project_dir // "")) as $p | if $p == "" then empty else
         {prio:0, plain:$p, styled:(b + c(252) + $p + r)} end),

      (if $branch == null then empty else
         (((if $wt != null then "⎇ " else "" end) + ($branch|tailclip(22)))) as $t
         | {prio:2, plain:$t,
            styled:(c(if $dirty == "1" then 137 else 245 end) + $t + r)} end),

      (if $model == null then empty else
         {prio:3, plain:$model, styled:(c(245) + $model + r)} end),

      (if $rgbslot == "" then empty else
         ("⌨" + $rgbslot) as $t | {prio:4, plain:$t, styled:(c(245) + $t + r)} end),
      (if $rgbbg == "" then empty else
         ("⌨" + $rgbbg) as $t | {prio:4, plain:$t, styled:(c(245) + $t + r)} end),

      {prio:0, plain:("ctx " + pct($ctx)),
       styled:(dim + "ctx " + r + c(ramp($ctx;60;80)) + pct($ctx) + r)},

      {prio:0, plain:("5h " + pct($h5) + $rsuf),
       styled:(dim + "5h " + r + c(ramp($h5;70;90)) + pct($h5) + r
               + (if $rsuf == "" then "" else dim + $rsuf + r end))},

      (if ($d7 == null or $d7 < 50) then empty else
         ("7d \($d7|round)%") as $t
         | {prio:5, plain:$t, styled:(dim + "7d " + r + c(ramp($d7;50;80)) + "\($d7|round)%" + r)} end),

      (if $fast|not then empty else
         {prio:6, plain:"⚡fast", styled:(c(179) + "⚡fast" + r)} end),

      (if $think then empty else
         {prio:7, plain:"think off", styled:(dim + "think off" + r)} end),

      (if $style == "default" then empty else
         {prio:8, plain:$style, styled:(c(245) + $style + r)} end),

      (if $pr == null then empty else
         ("#\($pr)") as $t | {prio:9, plain:$t, styled:(c(245) + $t + r)} end)
    ] as $parts

  # shed the least-important field until the line fits; prio 0 is never shed
  | (def fit:
       ((map(.plain|length)|add // 0) + ((length - 1) * 2)) as $w
       | (map(.prio)|max // 0) as $mx
       | if $w <= ($cols - 2) or $mx == 0 then .
         else del(.[ map(.prio) | index($mx) ]) | fit end;
     $parts | fit)

  | map(.styled) | join(c(238) + " ▏" + r)
' 2>/dev/null || printf '\033[1;38;5;252m%s\033[0m' "${PWD/#$HOME/\~}"
