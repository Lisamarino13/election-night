#!/bin/bash
# Commit today's pull and push it. Separate from run_all.sh on purpose: a local run should
# never push, and the cron host should never be the only place the data exists.
#
# NO REBASE. This used to `git pull --rebase`, which checks out the upstream commit —
# detaching HEAD — before replaying. One conflict on a data file left the cron VM detached
# permanently: it kept committing to nowhere and logged "rebase failed" on every tick for a
# day while the published site went stale.
#
# The data here is DERIVED and whole-file: snapshots are keyed on each state's own as-of
# date, and early-<ST>.json is regenerated from scratch every run. There is nothing to
# merge — the newest write simply wins. So instead of rebasing, this sets the branch to
# origin/main and lays the freshly generated files on top. That cannot conflict, and it
# cannot wedge the repository.
set -u
cd "$(dirname "$0")/.." || exit 1

PATHS="data/early-*.json data/ev-history-*.json data/trend-ev.json data/snapshots"

if [ -z "$(git status --porcelain data/)" ]; then
  echo "publish: no data changes — nothing to push"
  exit 0
fi

# A detached HEAD means a previous run left this repo wedged. Say so and repair it rather
# than committing into the void again.
branch=$(git rev-parse --abbrev-ref HEAD)
if [ "$branch" != "main" ]; then
  echo "publish: HEAD was detached at $(git rev-parse --short HEAD) — reattaching to main" >&2
  git rebase --abort 2>/dev/null
  git merge --abort 2>/dev/null
fi

# Keep the freshly generated files, take the remote exactly, then put them back.
tmp=$(mktemp -d) || { echo "publish: no temp dir" >&2; exit 1; }
trap 'rm -rf "$tmp"' EXIT
# shellcheck disable=SC2086
for f in $PATHS; do [ -e "$f" ] && cp -R "$f" "$tmp/" 2>/dev/null; done

git fetch -q origin main || { echo "publish: fetch failed" >&2; exit 1; }
git checkout -q -B main origin/main || { echo "publish: could not set main" >&2; exit 1; }

mkdir -p data/snapshots
cp -R "$tmp"/early-*.json "$tmp"/ev-history-*.json "$tmp"/trend-ev.json data/ 2>/dev/null
[ -d "$tmp/snapshots" ] && cp -R "$tmp"/snapshots/. data/snapshots/ 2>/dev/null

# Stage by name, never `git add -A`: nothing outside data/ rides along on a cron run.
# shellcheck disable=SC2086
git add $PATHS 2>/dev/null
if [ -z "$(git diff --cached --name-only)" ]; then
  echo "publish: nothing changed against origin — nothing to push"
  exit 0
fi

n=$(git diff --cached --name-only | wc -l | tr -d ' ')
git -c user.name="early-vote cron" -c user.email="cron@localhost" \
    commit -q -m "data: early-vote pull $(date -u '+%Y-%m-%d %H:%MZ') ($n files)" || exit 1
git push -q origin main || { echo "publish: push failed — commit is local" >&2; exit 1; }
echo "publish: pushed $n file(s)"
