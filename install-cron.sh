#!/bin/bash
# Install the early-vote cron on a server (Azure VM, or anything with python3 + git).
#
#   git clone https://github.com/Lisamarino13/election-night.git ~/election-night
#   ~/election-night/install-cron.sh
#
# Clone over HTTPS: the repo is public so reading needs no credential, and the deploy key
# that pushes does not exist until this script creates it. The remote is switched to SSH
# below, once there is a key for it to use.
#
# The daily collectors use ONLY the Python standard library — no pip, no venv. (pdfplumber
# is needed solely by fl_history.py, a one-shot historical pull whose output is already
# committed, so the cron never needs it.)
#
# Writing back to GitHub uses a repo-scoped DEPLOY KEY generated here. The private key never
# leaves this machine and this script never asks for, stores, or transmits any credential of
# yours — it prints a PUBLIC key for you to paste into the repo's settings yourself.
set -u
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
KEY="$HOME/.ssh/election_night_deploy"
LOCK="/tmp/election-night-cron.lock"        # DISTINCT from the job's own lock dir: an outer
                                            # flock sharing the job's lock path makes the job
                                            # block on itself and never tick.
LOG="$HOME/election-night-cron.log"

echo "repo:    $REPO_DIR"
command -v python3 >/dev/null || { echo "ERROR: python3 not found" >&2; exit 1; }
command -v git     >/dev/null || { echo "ERROR: git not found" >&2; exit 1; }
# flock is NOT required: run_all.sh locks itself with mkdir, which works everywhere
# including macOS. If flock happens to exist, cron gets a belt-and-braces outer guard too.
if command -v flock >/dev/null; then FLOCK="$(command -v flock) -n $LOCK"; else FLOCK=""; fi
echo "python:  $(python3 -V)"
python3 - <<'PY' || { echo "ERROR: stdlib check failed" >&2; exit 1; }
import sqlite3, zipfile, csv, urllib.request, json, http.cookiejar
print("stdlib:  sqlite3, zipfile, csv, urllib, json, http.cookiejar all present")
PY

# --- deploy key -----------------------------------------------------------------------
if [ ! -f "$KEY" ]; then
  ssh-keygen -t ed25519 -f "$KEY" -N "" -C "election-night-cron@$(hostname)" >/dev/null
  echo "generated deploy key $KEY"
fi
if ! grep -q "election_night_deploy" "$HOME/.ssh/config" 2>/dev/null; then
  mkdir -p "$HOME/.ssh"; chmod 700 "$HOME/.ssh"
  printf 'Host github.com\n  IdentityFile %s\n  IdentitiesOnly yes\n' "$KEY" >> "$HOME/.ssh/config"
  echo "added github.com entry to ~/.ssh/config"
fi

# point the remote at SSH so the deploy key is what pushes
if git -C "$REPO_DIR" remote get-url origin 2>/dev/null | grep -q '^https://'; then
  git -C "$REPO_DIR" remote set-url origin git@github.com:Lisamarino13/election-night.git
  echo "remote switched to SSH (deploy key will authenticate the push)"
fi

# --- cron -----------------------------------------------------------------------------
DAILY="15 13 * * * $FLOCK $REPO_DIR/collectors/run_all.sh >> $LOG 2>&1; $REPO_DIR/collectors/publish.sh >> $LOG 2>&1"
NIGHT="#7,37 * * * * $FLOCK $REPO_DIR/collectors/run_all.sh >> $LOG 2>&1; $REPO_DIR/collectors/publish.sh >> $LOG 2>&1   # election night: uncomment Nov 3"
# BACK UP FIRST. This box may run other people's jobs — on Lisa's cron VM it runs the
# Dopple prune / PG-stop / session-sweep lines. Rewriting a crontab without a backup is
# how you lose them.
BAK="$HOME/crontab.bak-election-night-$(date -u +%Y%m%dT%H%M%SZ)"
if crontab -l > "$BAK" 2>/dev/null; then
  echo "backed up existing crontab -> $BAK ($(wc -l < "$BAK" | tr -d ' ') lines)"
else
  echo "no existing crontab to back up"; : > "$BAK"
fi
( cat "$BAK" | grep -v 'election-night'; echo "$DAILY"; echo "$NIGHT" ) | crontab -

# Verify nothing else was dropped.
BEFORE=$(grep -vc 'election-night' "$BAK" 2>/dev/null || echo 0)
AFTER=$(crontab -l 2>/dev/null | grep -vc 'election-night' || echo 0)
if [ "$BEFORE" -ne "$AFTER" ]; then
  echo "ERROR: other crontab lines changed ($BEFORE -> $AFTER). Restoring." >&2
  crontab "$BAK"; exit 1
fi
echo "other crontab lines preserved: $AFTER"
echo "installed cron:"
crontab -l | grep election-night | sed 's/^/   /'

cat <<MSG

NEXT — one manual step, because it needs your GitHub account:

  1. Copy this public key:

$(cat "$KEY.pub")

  2. Paste it at:
       https://github.com/Lisamarino13/election-night/settings/keys/new
     Title: "cron VM"   —   TICK "Allow write access"

  3. Prove it works end to end, and confirm a REAL tick rather than assuming:
       ssh -T git@github.com                      # expect: "successfully authenticated"
       $REPO_DIR/collectors/run_all.sh && $REPO_DIR/collectors/publish.sh
       tail -5 $LOG

     Then after 13:15 UTC tomorrow (07:15 MST), check the log shows an unattended run. A cron that was
     never observed firing is not installed, it is just written down.
MSG
