#!/bin/bash
# Kansas, on its own process and its own clock.
#
# 105 county pages, each a full browser render through a Cloudflare challenge: about
# 3-4 minutes, more than every other state combined, for the least time-critical race
# on the board. Run inside the main loop it delayed Georgia and Texas by that much
# every pass.
#
# This writes data/results-KS.json and does NOT publish. The main loop's next publish
# picks the file up, which keeps a single writer to git. It waits out a publish in
# flight, because publish.sh force-resets the working tree.
#
#   start:  nohup ./ks_loop.sh >> ~/election-night-ks.log 2>&1 &
#   stop:   touch /tmp/election-night-STOP
cd "$(dirname "$0")" || exit 1
INTERVAL=${INTERVAL:-600}
PUBLOCK=/tmp/election-night-publishing
while true; do
  [ -f /tmp/election-night-STOP ] && { echo "$(date -u '+%FT%TZ') STOP - exiting"; exit 0; }
  for _ in $(seq 1 60); do [ -f "$PUBLOCK" ] || break; sleep 2; done
  echo "$(date -u '+%FT%TZ') --- kansas ---"
  ./run_results.sh ks
  sleep "$INTERVAL"
done
