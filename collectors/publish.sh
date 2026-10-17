#!/bin/bash
# Commit today's pull and push it. Separate from run_all.sh on purpose: a local run should
# never push, and the cron host should never be the only place the data exists.
#
# Only data/ is committed — collectors are code and change by hand. data/ev.db is ignored
# (it is derived from data/snapshots/ and rebuilt by ingest.py --rebuild).
set -u
cd "$(dirname "$0")/.." || exit 1

if [ -z "$(git status --porcelain data/)" ]; then
  echo "publish: no data changes — nothing to push"
  exit 0
fi

# Stage by name, never `git add -A`: nothing outside data/ should ride along on a cron run.
git add data/early-*.json data/ev-history-*.json data/trend-ev.json data/snapshots/ 2>/dev/null
if [ -z "$(git diff --cached --name-only)" ]; then
  echo "publish: nothing staged — nothing to push"
  exit 0
fi

n=$(git diff --cached --name-only | wc -l | tr -d ' ')
git -c user.name="early-vote cron" -c user.email="cron@localhost" \
    commit -q -m "data: early-vote pull $(date -u '+%Y-%m-%d %H:%MZ') ($n files)" || exit 1

# Rebase on top of anything pushed from elsewhere rather than failing or force-pushing.
# --autostash so an unrelated edit in the working tree cannot block the data push: the
# cron host and the laptop both run this, and on the laptop there is often work in flight.
git pull --rebase --autostash --quiet origin main || {
  echo "publish: rebase failed — data is committed locally, push it once resolved" >&2
  exit 1; }
git push --quiet origin main || { echo "publish: push failed" >&2; exit 1; }
echo "publish: pushed $n file(s)"
