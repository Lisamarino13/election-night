#!/bin/bash
# Daily early-vote pull. One entry point for cron.
#
#   crontab -e
#   15 13 * * *  $HOME/election-night/collectors/run_all.sh   # 13:15 UTC: after FL compiles ~8am ET >> $HOME/election-night-cron.log 2>&1
#
# Runs anywhere with python3 and git: the durable record is data/snapshots/*.json and the
# SQLite store is rebuilt from it, so no state is tied to the machine that happens to run it.
#
# Each collector fails closed: on any fetch or parse problem it writes nothing and exits
# non-zero, so the previous good data/early-XX.json stays in place and the board keeps
# showing yesterday's number with yesterday's timestamp rather than a blank or a zero.
#
# Exit 2 is "the state has not published this yet" (Texas before the SOS opens the 2026
# election). Exit 3 is "a dependency is missing" (Iowa needs pdfplumber; every other
# collector is pure stdlib). Both are expected states, not failures, and are logged quietly.
#
# Everything is appended to collectors/run.log.

cd "$(dirname "$0")" || exit 1
LOG="run.log"

# Self-locking, so cron does not need flock. macOS has no flock at all, and depending on a
# binary that is not everywhere turned the install into a hard failure on a Mac. mkdir is
# atomic on every POSIX filesystem, so it is the portable primitive.
LOCKDIR="${TMPDIR:-/tmp}/election-night-run.lock"
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  if [ -f "$LOCKDIR/pid" ] && ! kill -0 "$(cat "$LOCKDIR/pid" 2>/dev/null)" 2>/dev/null; then
    rm -rf "$LOCKDIR"                       # stale lock from a killed run
    mkdir "$LOCKDIR" 2>/dev/null || { echo "another run holds the lock"; exit 0; }
  else
    echo "another run is in progress — skipping this tick"
    exit 0
  fi
fi
echo $$ > "$LOCKDIR/pid"
trap 'rm -rf "$LOCKDIR"' EXIT INT TERM
# Prefer a project venv when one exists: the cron host may have no pip, so Iowa's PDF
# dependency lives in ../.venv rather than in the system Python.
if [ -x "../.venv/bin/python3" ]; then PY="$(cd .. && pwd)/.venv/bin/python3"
else PY=$(command -v python3) || { echo "no python3" >&2; exit 1; }; fi

say(){ printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" | tee -a "$LOG"; }

say "=== early-vote pull starting ==="
ok=0; pending=0; failed=0; failed_names=""

for c in fl_vbm.py nc_absentee.py me_absentee.py ia_absentee.py tx_earlyvote.py; do
  [ -f "$c" ] || { say "SKIP $c (not present)"; continue; }
  out=$("$PY" "$c" 2>&1); rc=$?
  printf '%s\n' "$out" >> "$LOG"
  case $rc in
    0) ok=$((ok+1));      say "OK      $c";;
    2) pending=$((pending+1)); say "PENDING $c -- $(printf '%s' "$out" | tail -1)";;
    3) pending=$((pending+1)); say "DEPS    $c -- $(printf '%s' "$out" | tail -1)";;
    *) failed=$((failed+1)); failed_names="$failed_names $c"
       say "FAILED  $c -- $(printf '%s' "$out" | tail -1) (previous data left in place)";;
  esac
done

# Pick up any hand-downloaded files (GA / MN / OH) before ingest. States behind
# bot-management cannot be fetched here; whatever is in data/manual/ gets parsed.
man=$("$PY" manual_import.py 2>&1); mrc=$?
printf '%s\n' "$man" >> "$LOG"
[ $mrc -eq 0 ] && say "MANUAL  $(printf '%s' "$man" | grep -cE '^[A-Z]{2} ok:') state(s) imported from data/manual" \
               || say "MANUAL  import problem -- $(printf '%s' "$man" | tail -1)"

# Ingest into SQLite and re-export the trend view. This runs even when a collector failed:
# the files that DID refresh still belong in the store, and ingest is keyed on each state's
# own as-of date, so re-reading an unchanged file is a no-op rather than a double count.
ing=$("$PY" ingest.py 2>&1); irc=$?
printf '%s\n' "$ing" >> "$LOG"
if [ $irc -eq 0 ]; then
  say "INGEST  $(printf '%s' "$ing" | grep -E 'observations in' | tail -1)"
else
  failed=$((failed+1)); failed_names="$failed_names ingest.py"
  say "FAILED  ingest.py -- $(printf '%s' "$ing" | tail -1)"
fi

say "=== done: $ok ok, $pending pending, $failed failed$failed_names ==="
[ "$failed" -eq 0 ]
