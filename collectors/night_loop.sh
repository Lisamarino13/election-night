#!/bin/bash
# Main election-night runner: the twelve states plus Georgia, then publish.
#
# cron cannot be used: macOS TCC blocks /usr/sbin/cron from anything under ~/Desktop,
# so every tick died with "Operation not permitted". A process started from an app that
# already has disk access inherits it, so this is launched once with nohup.
#
# Kansas is NOT here - it runs as its own process (ks_loop.sh) because it is 105
# sequential renders through a Cloudflare challenge, longer than everything else put
# together, and it must not hold up Georgia or Texas.
#
#   start:  nohup ./night_loop.sh >> ~/election-night-loop.log 2>&1 &
#   stop:   touch /tmp/election-night-STOP
cd "$(dirname "$0")" || exit 1
INTERVAL=${INTERVAL:-120}
PUBLOCK=/tmp/election-night-publishing
tick=0
while true; do
  [ -f /tmp/election-night-STOP ] && { echo "$(date -u '+%FT%TZ') STOP - exiting"; exit 0; }
  tick=$((tick+1))
  echo "$(date -u '+%FT%TZ') --- tick $tick ---"
  ./run_results.sh main
  # publish.sh force-resets the tree to origin/main, so nothing else may be writing
  # into data/ while it runs. ks_loop.sh waits on this same marker.
  touch "$PUBLOCK"; ./publish.sh; rm -f "$PUBLOCK"
  sleep "$INTERVAL"
done
