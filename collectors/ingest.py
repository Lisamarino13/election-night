#!/usr/bin/env python3
"""data/early-*.json -> data/ev.db, then export the trend view the board reads.

Run after the collectors. Separating ingest from collection means one normalisation point
instead of four, and it means re-ingesting yesterday's files is a no-op rather than a
double count (the primary key is the state's own as-of date, so a repeat pull replaces).

Also writes data/trend-ev.json: the per-day statewide series the board graphs. GitHub Pages
serves static files only, so SQLite is the system of record locally and the JSON is the
published view of it.
"""
import json, sys, pathlib, sqlite3, collections
import store, snapshot

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"


def ingest_all(con):
    """Archive today's pull, then load the whole snapshot history into the store.

    The snapshots are the durable record; the database is derived from them. Loading all
    of them every run (rather than only today's) means the store is always a pure function
    of the archive, so a corrupted or deleted ev.db is a rebuild, not a data loss.
    """
    for f in sorted(DATA.glob("early-*.json")):
        try:
            payload = json.loads(f.read_text())
        except Exception as e:
            print(f"  SKIP {f.name}: unreadable ({e})", file=sys.stderr)
            continue
        if "state" in payload:
            p, new = snapshot.save(payload)
            if new:
                print(f"  archived {p.name}")

    total = 0
    for p, payload in snapshot.load_all():
        rows, as_of = store.ingest_payload(con, payload)
        store.log(con, payload["state"], "ev", "ok", rows, f"as_of {as_of}")
        total += rows
        print(f"  {payload['state']}  as_of {as_of:<12} {rows:>6,} rows  <- {p.name}")
    con.commit()
    return total


def export_trend(con):
    """Statewide series per state per day -> data/trend-ev.json (what the board graphs)."""
    q = """
      SELECT state, as_of, stream, bucket, party, count
        FROM ev_observation
       WHERE unit = 'STATEWIDE'
       ORDER BY state, as_of
    """
    series = collections.defaultdict(lambda: collections.defaultdict(dict))
    for state, as_of, stream, bucket, party, count in con.execute(q):
        key = f"{stream}_{bucket}"
        series[state][as_of].setdefault(key, {})[party] = count

    reg = collections.defaultdict(dict)
    for state, as_of, registered in con.execute(
            "SELECT state, as_of, registered FROM ev_registered WHERE unit='STATEWIDE'"):
        reg[state][as_of] = registered

    out = {}
    for state, days in series.items():
        out[state] = {
            "days": [
                {"as_of": d, "registered": reg.get(state, {}).get(d), **vals}
                for d, vals in sorted(days.items())
            ]
        }
    p = DATA / "trend-ev.json"
    p.write_text(json.dumps({"states": out}, indent=1))
    return p, {s: len(v["days"]) for s, v in out.items()}


def main():
    if "--rebuild" in sys.argv and store.DB.exists():
        store.DB.unlink()
        for ext in ("-wal", "-shm"):
            q = store.DB.with_name(store.DB.name + ext)
            if q.exists():
                q.unlink()
        print(f"rebuilt {store.DB.name} from snapshots")
    con = store.connect()
    print("ingest:")
    rows = ingest_all(con)
    p, counts = export_trend(con)
    con.commit()
    print(f"\n{rows:,} observations in {store.DB.name}")
    print(f"trend -> {p.name}: " + ", ".join(f"{s} {n}d" for s, n in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
