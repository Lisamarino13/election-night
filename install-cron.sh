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
LOCK="/tmp/election-night-cron.lock"        # distinct from any lock the job itself takes:
                                            # an outer flock sharing the job's own lock path
                                            # makes the job block on itself and never tick.
LOG="$HOME/election-night-cron.log"

echo "repo:    $REPO_DIR"
command -v python3 >/dev/null || { echo "ERROR: python3 not found" >&2; exit 1; }
command -v git     >/dev/null || { echo "ERROR: git not found" >&2; exit 1; }
command -v flock   >/dev/null || { echo "ERROR: flock not found (util-linux)" >&2; exit 1; }
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
DAILY="15 13 * * * /usr/bin/flock -n $LOCK $REPO_DIR/collectors/run_all.sh >> $LOG 2>&1 && $REPO_DIR/collectors/publish.sh >> $LOG 2>&1"
NIGHT="#7,37 * * * * /usr/bin/flock -n $LOCK $REPO_DIR/collectors/run_all.sh >> $LOG 2>&1 && $REPO_DIR/collectors/publish.sh >> $LOG 2>&1   # election night: uncomment Nov 3"
( crontab -l 2>/dev/null | grep -v 'election-night'; echo "$DAILY"; echo "$NIGHT" ) | crontab -
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
