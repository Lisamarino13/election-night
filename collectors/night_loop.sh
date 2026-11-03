#!/bin/bash
# Election-night runner, as a detached loop rather than cron.
#
# cron cannot be used: macOS TCC blocks /usr/sbin/cron from anything under ~/Desktop,
# so every tick died with "Operation not permitted" before running a line. A process
# started from an app that already has disk access inherits it, so this is launched
# once with nohup and keeps going on its own. (setsid does not exist on macOS.)
#
# Kansas is on its own cadence. It is 105 sequential renders through a Cloudflare
# browser challenge - about 177s, more than the other twelve states and Georgia put
# together - and it is the least time-critical race on the board. Running it every
# pass made the cycle ~10 minutes; running it every fourth keeps the rest at ~4.
#
#   start:  nohup ./night_loop.sh >> ~/election-night-loop.log 2>&1 &
#   stop:   touch /tmp/election-night-STOP
#   watch:  tail -f ~/election-night-loop.log
cd "$(dirname "$0")" || exit 1
INTERVAL=${INTERVAL:-120}
KS_EVERY=${KS_EVERY:-4}
tick=0
while true; do
  if [ -f /tmp/election-night-STOP ]; then
    echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') STOP file present - exiting"; exit 0
  fi
  tick=$((tick+1))
  echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') --- tick $tick ---"
  ./run_results.sh main
  if [ $((tick % KS_EVERY)) -eq 1 ]; then
    echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') --- kansas sweep ---"
    ./run_results.sh ks
  fi
  ./publish.sh
  sleep "$INTERVAL"
done
