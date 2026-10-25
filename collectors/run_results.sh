#!/bin/bash
# Election-night pull. Separate from run_all.sh because the cadence is different:
# the early-vote collectors run hourly for weeks, these run every few minutes for one
# night. Both are idempotent, so an overlap costs nothing.
#
#   election night only:
#   */3 * * * *  $HOME/election-night/collectors/run_results.sh
#
# Each collector fails closed. Exit 2 is "the state has not staged its election yet",
# which is the expected answer every day until the feeds go live, not a failure.
cd "$(dirname "$0")" || exit 1
LOG="results.log"
LOCKDIR="${TMPDIR:-/tmp}/election-night-results.lock"
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  if [ -f "$LOCKDIR/pid" ] && ! kill -0 "$(cat "$LOCKDIR/pid" 2>/dev/null)" 2>/dev/null; then
    rm -rf "$LOCKDIR"; mkdir "$LOCKDIR" 2>/dev/null || exit 0
  else
    echo "another results run is in progress - skipping"; exit 0
  fi
fi
echo $$ > "$LOCKDIR/pid"
trap 'rm -rf "$LOCKDIR"' EXIT INT TERM
if [ -x "../.venv/bin/python3" ]; then PY="$(cd .. && pwd)/.venv/bin/python3"
else PY=$(command -v python3) || { echo "no python3" >&2; exit 1; }; fi
say(){ printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" | tee -a "$LOG"; }

say "=== results pull starting ==="
ok=0; pending=0; failed=0
for c in nc_results.py oh_results.py fl_results.py tx_results.py ne_results.py clarity_results.py; do
  [ -f "$c" ] || { say "SKIP $c"; continue; }
  out=$("$PY" "$c" 2>&1); rc=$?
  printf '%s\n' "$out" >> "$LOG"
  case $rc in
    0) ok=$((ok+1));      say "OK      $c -- $(printf '%s' "$out" | tail -1)";;
    2) pending=$((pending+1)); say "PENDING $c -- not staged yet";;
    *) failed=$((failed+1)); say "FAILED  $c -- $(printf '%s' "$out" | tail -1) (previous data left in place)";;
  esac
done
bld=$("$PY" build_results.py 2>&1); brc=$?
printf '%s\n' "$bld" >> "$LOG"
[ $brc -eq 0 ] && say "BUILD   $(printf '%s' "$bld" | tail -1)" \
               || { failed=$((failed+1)); say "FAILED  build_results.py -- $(printf '%s' "$bld" | tail -1)"; }
say "=== done: $ok ok, $pending pending, $failed failed ==="
[ "$failed" -eq 0 ]
