#!/bin/bash
# Daily early-vote pull. One entry point for cron.
#
#   crontab -e
#   15 9 * * *  $HOME/election-night/collectors/run_all.sh >> $HOME/election-night-cron.log 2>&1
#
# Runs anywhere with python3 and git: the durable record is data/snapshots/*.json and the
# SQLite store is rebuilt from it, so no state is tied to the machine that happens to run it.
#
# Each collector fails closed: on any fetch or parse problem it writes nothing and exits
# non-zero, so the previous good data/early-XX.json stays in place and the board keeps
# showing yesterday's number with yesterday's timestamp rather than a blank or a zero.
#
# Exit 2 is "the state has not published this yet" (Texas before the SOS opens the 2026
# election). That is expected, not a failure, and is logged quietly.
#
# Everything is appended to collectors/run.log.

cd "$(dirname "$0")" || exit 1
LOG="run.log"
PY=$(command -v python3) || { echo "no python3" >&2; exit 1; }

say(){ printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" | tee -a "$LOG"; }

say "=== early-vote pull starting ==="
ok=0; pending=0; failed=0; failed_names=""

for c in fl_vbm.py nc_absentee.py me_absentee.py tx_earlyvote.py; do
  [ -f "$c" ] || { say "SKIP $c (not present)"; continue; }
  out=$("$PY" "$c" 2>&1); rc=$?
  printf '%s\n' "$out" >> "$LOG"
  case $rc in
    0) ok=$((ok+1));      say "OK      $c";;
    2) pending=$((pending+1)); say "PENDING $c -- $(printf '%s' "$out" | tail -1)";;
    *) failed=$((failed+1)); failed_names="$failed_names $c"
       say "FAILED  $c -- $(printf '%s' "$out" | tail -1) (previous data left in place)";;
  esac
done

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
