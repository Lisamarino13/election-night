#!/bin/bash
# THE early-voting command. Pulls every state this machine can reach, then publishes.
#
#   ~/election-night/laptop.sh
#
# A laptop can do strictly more than the cron VM, so this is the complete pull:
#
#   Florida, North Carolina, Iowa, Texas   also run unattended on the VM at 13:15 UTC
#   Maine                                  ONLY here — maine.gov 403s the VM's datacenter IP
#   Georgia / Minnesota / Ohio             whatever you downloaded into data/manual/
#
# Running it when the VM has already pulled is harmless: snapshots are keyed on each
# state's own as-of date, so a second pull of the same day replaces it rather than adding
# a duplicate, and nothing is pushed unless something actually changed.
#
# This covers EARLY VOTING only. Election-night county results are a separate pipeline.
set -u
cd "$(dirname "$0")" || exit 1

echo "updating repo..."
git pull -q --rebase --autostash origin main || {
  echo "could not update — resolve and retry" >&2; exit 1; }

./collectors/run_all.sh
rc=$?

echo
./collectors/publish.sh

# run_all exits non-zero if any single state failed. That is worth surfacing, but it is
# not a reason to call the whole run a failure — the states that succeeded are published.
if [ $rc -ne 0 ]; then
  echo
  echo "note: at least one state failed above. Everything that succeeded has been"
  echo "published; the failed ones kept their previous data rather than blanking."
fi
