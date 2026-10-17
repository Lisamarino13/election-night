#!/bin/bash
# Pull Maine and publish it, from a machine that can actually reach maine.gov.
#
#   ~/election-night/maine.sh
#
# WHY THIS IS SEPARATE: maine.gov returns 403 to the Azure cron VM's IP no matter what
# headers are sent, while it answers a laptop normally. It is IP-level blocking of
# datacenter ranges, not a header or rate problem, so Maine cannot be pulled from the
# cron host at all. Every other state runs there unattended; this is the one that has to
# run somewhere with a residential address.
#
# Safe to run any time, as often as you like. The snapshot is keyed on Maine's own as-of
# date, so a second run on the same day overwrites that day rather than adding a duplicate,
# and publish.sh pushes only when something actually changed.
set -u
cd "$(dirname "$0")" || exit 1

echo "updating repo..."
git pull -q --rebase --autostash origin main || { echo "could not update — resolve and retry" >&2; exit 1; }

echo "pulling Maine..."
if ! python3 collectors/me_absentee.py; then
  echo "Maine pull failed — nothing written, nothing published." >&2
  exit 1
fi

echo "ingesting..."
python3 collectors/ingest.py >/dev/null || { echo "ingest failed" >&2; exit 1; }

collectors/publish.sh
