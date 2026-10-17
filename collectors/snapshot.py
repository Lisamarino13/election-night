#!/usr/bin/env python3
"""Append-only daily snapshots -> data/snapshots/early-<ST>-<as_of>.json

WHY: ev.db was the only durable record, and a SQLite file that lives on one laptop cannot
move to a server, cannot be rebuilt if it is lost, and churns as a large binary in git.

So the durable record is now a small JSON file per state per state-reported day, and the
database is a DERIVED artifact rebuilt from them by `ingest.py --rebuild`. That makes the
whole pipeline reproducible and host-agnostic: whatever machine runs the cron commits a
few hundred KB of text, and anyone can reconstruct the exact database from the snapshots.

Naming is keyed on the STATE's as-of date, not the clock, so a second pull on the same day
overwrites that day's snapshot instead of creating a duplicate.
"""
import json, pathlib, sys
import store

SNAPS = pathlib.Path(__file__).resolve().parent.parent / "data" / "snapshots"


def save(payload):
    """Write one state-day snapshot. Returns (path, wrote_new)."""
    if "state" not in payload:
        raise RuntimeError("payload has no state field")
    as_of = store._as_of(payload)
    SNAPS.mkdir(parents=True, exist_ok=True)
    p = SNAPS / f"early-{payload['state']}-{as_of}.json"
    new = not p.exists()
    body = json.dumps(payload, indent=1, sort_keys=True)
    if not new and p.read_text() == body:
        return p, False                      # identical re-pull: leave the file untouched
    p.write_text(body)
    return p, new


def load_all():
    """Every snapshot, oldest first."""
    for p in sorted(SNAPS.glob("early-*.json")):
        try:
            yield p, json.loads(p.read_text())
        except Exception as e:
            print(f"  SKIP {p.name}: {e}", file=sys.stderr)


def main():
    """Fold today's live data/early-*.json into the snapshot archive."""
    data = pathlib.Path(__file__).resolve().parent.parent / "data"
    n = 0
    for f in sorted(data.glob("early-*.json")):
        payload = json.loads(f.read_text())
        if "state" not in payload:
            continue
        p, new = save(payload)
        print(f"  {'NEW ' if new else 'same'} {p.name}")
        n += 1
    print(f"{n} snapshot(s) in {SNAPS.relative_to(data.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
