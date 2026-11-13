#!/usr/bin/env bash
# Build an eval fixture as a fresh git repo: base/ committed on main, then each
# branch/<step>/ overlaid and committed in order on the branch named in branch.name.
# Usage: build-fixture.sh <fixture-name> <dest-dir>   (dest must not exist)
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
src="$here/fixtures/$1"
dest=$2
[[ -d $src ]] || { echo "no fixture: $1" >&2; exit 1; }
[[ ! -e $dest ]] || { echo "dest exists: $dest" >&2; exit 1; }
g() { git -C "$dest" -c user.name="Fixture Author" -c user.email=fixture@example.invalid \
        -c commit.gpgsign=false -c core.hooksPath=/dev/null "$@"; }
mkdir -p "$dest"
git -C "$dest" init -q -b main
cp -a "$src/base/." "$dest/"
g add -A
g commit -qm "$(cat "$src/base.message")"
g checkout -qb "$(cat "$src/branch.name")"
for step in $(cd "$src/branch" && ls -d */ | sort); do
  step=${step%/}
  cp -a "$src/branch/$step/." "$dest/"
  g add -A -f
  g commit -qm "$(cat "$src/branch/$step.message")"
done
echo "$dest"
