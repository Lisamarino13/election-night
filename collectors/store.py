#!/usr/bin/env python3
"""SQLite store for the board. Schema + ingest.

WHY THIS EXISTS: every collector writes data/early-XX.json by overwriting it, so only the
most recent pull survives. Early-vote pacing is a time series — "how is 2026 tracking against
2022 at the same point" needs one row per day, not one row. This file is the system of record;
the JSON the page reads is a published view of it.

sqlite3 is in the standard library: no server, no dependency, one file at data/ev.db.

GRAIN
  ev_observation: one row per state x unit x as_of x stream x bucket x party.

  as_of is THE STATE'S OWN DATE, not my clock. That is what makes the cron idempotent:
  running it three times in a morning produces one row, not three, because the primary key
  collides and the row is replaced. It also means a state that has not refreshed shows up as
  "no new as_of" rather than as three identical pulls.

  count is NULLABLE and NULL means "this state does not publish this quantity." It is never
  0. North Carolina does not report un-returned mail ballots; writing 0 there would say "none
  left to count" and make a projection look certain. The schema enforces the distinction that
  the rest of the board depends on.

  party is 'ALL' for states with no party registration (TX, OH, MI, MN, SC, GA) so that a
  turnout-only state is representable without inventing a split.

  Election night is a different grain: there, pulled_at IS the key, because county results
  change through the night and every 30-minute poll is its own fact.
"""
import sqlite3, pathlib, json
from datetime import datetime, timezone

DB = pathlib.Path(__file__).resolve().parent.parent / "data" / "ev.db"

SCHEMA = """
PRAGMA journal_mode=WAL;

-- ---------- early / mail vote, one row per state-unit-day-stream-bucket-party ----------
CREATE TABLE IF NOT EXISTS ev_observation (
  state      TEXT    NOT NULL,          -- 'FL'
  unit       TEXT    NOT NULL,          -- county or municipality; 'STATEWIDE' for the rollup
  unit_kind  TEXT    NOT NULL,          -- 'county' | 'municipality' | 'state'
  as_of      TEXT    NOT NULL,          -- the state's own as-of date (ISO where derivable)
  stream     TEXT    NOT NULL,          -- 'mail' | 'in_person'
  bucket     TEXT    NOT NULL,          -- 'returned' | 'outstanding' | 'requested_not_issued' | 'rejected'
  party      TEXT    NOT NULL,          -- 'D' | 'R' | 'NPA' | 'O' | 'ALL'
  count      INTEGER,                   -- NULL = not published by this state. NEVER 0 for unknown.
  pulled_at  TEXT    NOT NULL,          -- my clock, provenance only
  source     TEXT    NOT NULL,
  PRIMARY KEY (state, unit, as_of, stream, bucket, party)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS ix_ev_state_day   ON ev_observation (state, as_of);
CREATE INDEX IF NOT EXISTS ix_ev_statewide   ON ev_observation (state, unit, as_of)
  WHERE unit = 'STATEWIDE';

-- registered voters, the only honest denominator for a turnout-only state
CREATE TABLE IF NOT EXISTS ev_registered (
  state TEXT NOT NULL, unit TEXT NOT NULL, as_of TEXT NOT NULL,
  registered INTEGER, pulled_at TEXT NOT NULL,
  PRIMARY KEY (state, unit, as_of)
) WITHOUT ROWID;

-- ---------- election night: pulled_at IS the grain, results move all evening ----------
CREATE TABLE IF NOT EXISTS result_observation (
  state TEXT NOT NULL, unit TEXT NOT NULL, race TEXT NOT NULL,   -- 'senate' | 'governor'
  candidate TEXT NOT NULL, pulled_at TEXT NOT NULL,
  votes INTEGER,
  PRIMARY KEY (state, unit, race, candidate, pulled_at)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS unit_progress (
  state TEXT NOT NULL, unit TEXT NOT NULL, race TEXT NOT NULL, pulled_at TEXT NOT NULL,
  outstanding INTEGER,        -- NULL when the county does not say. never 0 for unknown.
  reporting   INTEGER,        -- precincts reported
  precincts   INTEGER,        -- precincts expected
  PRIMARY KEY (state, unit, race, pulled_at)
) WITHOUT ROWID;

-- ---------- what ran, and what happened ----------
CREATE TABLE IF NOT EXISTS pull_log (
  pulled_at TEXT NOT NULL, state TEXT NOT NULL, kind TEXT NOT NULL,
  status TEXT NOT NULL,                 -- 'ok' | 'pending' | 'failed'
  rows INTEGER, detail TEXT
);
"""

PARTIES = ("D", "R", "NPA", "O")
# payload bucket name -> (stream, bucket) in the store
BUCKETS = {
    "mail_returned":        ("mail", "returned"),
    "mail_outstanding":     ("mail", "outstanding"),
    "early_in_person":      ("in_person", "returned"),
    "requested_not_issued": ("mail", "requested_not_issued"),
    "rejected":             ("mail", "rejected"),
}
# The payloads also carry "returned"/"outstanding" as aliases, because the board reads those
# two keys for every state. They map to the same grain as the canonical names above, so they
# are only used when the canonical key is absent — otherwise each fact is emitted twice under
# one primary key and the "rows written" count lies about how much was actually stored.
ALIASES = {"returned": "mail_returned", "outstanding": "mail_outstanding"}


def _buckets_in(d):
    """Bucket names to read from a payload dict, aliases resolved, no duplicates."""
    names = [k for k in d if k in BUCKETS]
    for alias, canon in ALIASES.items():
        if alias in d and canon not in d:
            names.append(alias)
    return names


def connect(path=DB):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def _as_of(payload):
    """The state's own date, normalised to ISO where we can read it; else the pull date."""
    raw = payload.get("as_of") or payload.get("through")
    comp = payload.get("compiled")
    if not raw and isinstance(comp, dict) and comp:
        raw = list(comp.values())[0]
    if not raw:
        return (payload.get("fetched") or datetime.now(timezone.utc).isoformat())[:10]
    s = str(raw).strip()
    # Pull the DATE out by pattern instead of splitting on whitespace. Florida's compile
    # stamp is "10/16/2026  8:04AM" one day and "10/15/2026 11:01AM" the next — a one- vs
    # two-space difference that made a naive split fall through to the raw string. That
    # string then reached a filename, where its slashes became directory separators and
    # took down the whole ingest.
    import re as _re
    for pat, fmt in ((r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
                     (r"\d{1,2}/\d{1,2}/\d{4}", "%m/%d/%Y"),
                     (r"\d{1,2}-\d{1,2}-\d{4}", "%m-%d-%Y"),
                     (r"\d{1,2}/\d{1,2}/\d{2}(?!\d)", "%m/%d/%y"),
                     (r"\d{1,2}-\d{1,2}-\d{2}(?!\d)", "%m-%d-%y"),
                     (r"[A-Z][a-z]+ \d{1,2},\s*\d{4}", "%B %d, %Y")):
        m = _re.search(pat, s)
        if m:
            try:
                txt = _re.sub(r",\s*", ", ", m.group(0))
                return datetime.strptime(txt, fmt).date().isoformat()
            except ValueError:
                continue
    return s                                    # keep it verbatim rather than guess wrong


def ingest_payload(con, payload):
    """One collector payload -> ev_observation rows. Returns rows written."""
    state = payload["state"]
    kind = payload.get("unit", "county")
    as_of = _as_of(payload)
    pulled = payload.get("fetched") or datetime.now(timezone.utc).isoformat(timespec="seconds")
    src = payload.get("source", "")
    party_ok = payload.get("party_available", True)
    rows = []

    def emit(unit, unit_kind, bucket_name, rec):
        mapped = BUCKETS.get(ALIASES.get(bucket_name, bucket_name))
        if not mapped:
            return
        stream, bucket = mapped
        if rec is None:
            # The state does not publish this quantity. Write NULL across the same party
            # shape the state uses elsewhere, so "unknown" has the same grain as "known"
            # and a query cannot mistake a missing party for a zero.
            for p in (PARTIES if party_ok else ("ALL",)):
                rows.append((state, unit, unit_kind, as_of, stream, bucket, p,
                             None, pulled, src))
            return
        if party_ok:
            for p in PARTIES:
                if p in rec:
                    rows.append((state, unit, unit_kind, as_of, stream, bucket, p,
                                 rec.get(p), pulled, src))
        else:
            rows.append((state, unit, unit_kind, as_of, stream, bucket, "ALL",
                         rec.get("total"), pulled, src))

    # --- statewide rollup -------------------------------------------------------------
    st = payload.get("state_totals") or {}
    if party_ok:
        for name in _buckets_in(st):
            emit("STATEWIDE", "state", name, st[name])
    else:
        # turnout-only shape: {registered, in_person, by_mail, total}
        emit("STATEWIDE", "state", "early_in_person", {"total": st.get("in_person")})
        emit("STATEWIDE", "state", "mail_returned",   {"total": st.get("by_mail")})
        if st.get("registered") is not None:
            con.execute("INSERT OR REPLACE INTO ev_registered VALUES (?,?,?,?,?)",
                        (state, "STATEWIDE", as_of, st["registered"], pulled))

    # --- per unit ---------------------------------------------------------------------
    units = payload.get("units") or payload.get("counties") or {}
    for unit, v in units.items():
        if unit == "STATEWIDE":
            continue
        if party_ok:
            for name in _buckets_in(v):
                emit(unit, kind, name, v[name])
        else:
            emit(unit, kind, "early_in_person", {"total": v.get("in_person")})
            emit(unit, kind, "mail_returned",   {"total": v.get("by_mail")})
            if v.get("registered") is not None:
                con.execute("INSERT OR REPLACE INTO ev_registered VALUES (?,?,?,?,?)",
                            (state, unit, as_of, v["registered"], pulled))

    distinct = len({r[:7] for r in rows})
    if distinct != len(rows):
        raise RuntimeError(f"{state}: {len(rows)-distinct} duplicate keys in one payload — "
                           f"two payload buckets map to the same grain")
    con.executemany("INSERT OR REPLACE INTO ev_observation VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows), as_of


def log(con, state, kind, status, rows=None, detail=""):
    con.execute("INSERT INTO pull_log VALUES (?,?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 state, kind, status, rows, detail))
