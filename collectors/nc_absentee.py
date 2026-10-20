#!/usr/bin/env python3
"""North Carolina absentee + one-stop early voting -> data/early-NC.json

Source: s3.amazonaws.com/dl.ncsbe.gov/ENRS/{YYYY_MM_DD}/absentee_{YYYYMMDD}.zip
One row per ballot, refreshed daily. NC breaks out BOTH streams by party and county:
  ballot_req_type   MAIL | EARLY VOTING (one-stop, in person)
  ballot_rtn_status ACCEPTED / ACCEPTED - CURED / PENDING CURE / ...

NOTE: this file contains ONLY ballots already returned. Verified 2026-10-17: every MAIL
row carries a disposition and zero rows have a send date without a return date. NC does
not publish outstanding mail ballots for this cycle (the absentee_stats_* files stopped
in 2010). So outstanding is reported as NULL, never 0 — a zero here would read as "none
left" and make a projection look certain when the quantity is simply unknown.
  voter_party_code  DEM | REP | UNA | LIB | GRE | ...

Streamed from inside the zip — the 2024 file is ~2GB uncompressed, so nothing is
extracted to disk and nothing is held in memory but the aggregate.

FAILS CLOSED: any fetch or parse problem raises and writes nothing.
"""
import json, io, csv, sys, zipfile, pathlib, urllib.request, collections
from datetime import datetime, timezone

ELECTION = ("2026_11_03", "20261103")
# Prior cycles live at the same path with the election date swapped, in the identical
# format — so history is the same parser, not a second one. These are FINAL files (the
# archive is the end-state of that election), which makes them a ceiling to pace against,
# not a same-day-in-cycle comparison.
HISTORY = {2020: ("2020_11_03", "20201103"),
           2022: ("2022_11_08", "20221108"),
           2024: ("2024_11_05", "20241105")}
URL = "https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/{}/absentee_{}.zip"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
PARTY = {"DEM": "D", "REP": "R", "UNA": "NPA"}        # everything else -> O
ACCEPTED = ("ACCEPTED",)                               # prefix match covers CURED / EXCEPTION
# NC RENAMED THIS VALUE between cycles: 2020 and 2022 say "ONE-STOP", 2024 and 2026 say
# "EARLY VOTING". Matching only the new spelling turned 4.1M in-person ballots in the 2020
# file into a silent zero — the aggregate still looked like a valid result. Any value not
# listed here now raises instead of being dropped, so the next rename is a failed run and
# not a wrong number on the board.
IN_PERSON = {"EARLY VOTING", "ONE-STOP", "ONE STOP", "ONESTOP"}
BY_MAIL = {"MAIL", "BY MAIL"}


def fetch(dirpart, filepart, cache=None, reuse=False):
    """Download the zip. reuse=True serves a cached copy; only safe for PAST elections.

    THIS CACHE WAS A BUG. It was unconditional, so the live 2026 file was downloaded once
    and never again: the collector kept reporting a fresh `fetched` timestamp while the
    numbers underneath were two days old. Stale data wearing a current timestamp is worse
    than a failed pull, because nothing looks wrong.

    Past elections are immutable, so --history still reuses its 230MB downloads. The live
    file never does.
    """
    p = pathlib.Path(cache or f"/tmp/nc_{filepart}.zip")
    if reuse and p.exists() and p.stat().st_size >= 1_000_000:
        return p
    req = urllib.request.Request(URL.format(dirpart, filepart), headers=UA)
    with urllib.request.urlopen(req, timeout=180) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}")
        body = r.read()
    if len(body) < 1_000_000:
        raise RuntimeError(f"{filepart}: {len(body)} bytes — refusing a truncated download")
    p.write_bytes(body)
    return p


def aggregate(zip_path):
    z = zipfile.ZipFile(zip_path)
    names = [n for n in z.namelist() if n.lower().endswith(".csv")]
    if not names:
        raise RuntimeError(f"{zip_path}: no csv inside")
    counties = collections.defaultdict(lambda: collections.defaultdict(
        lambda: {"R": 0, "D": 0, "NPA": 0, "O": 0, "total": 0}))
    rows = 0
    unknown = collections.Counter()
    with z.open(names[0]) as f:
        rd = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="ignore"))
        for col in ("county_desc", "ballot_req_type", "ballot_rtn_status", "voter_party_code"):
            if col not in (rd.fieldnames or []):
                raise RuntimeError(f"{zip_path}: column {col!r} missing — layout changed")
        for row in rd:
            rows += 1
            cty = (row.get("county_desc") or "").strip().title()
            if not cty:
                continue
            party = PARTY.get((row.get("voter_party_code") or "").strip().upper(), "O")
            typ = (row.get("ballot_req_type") or "").strip().upper()
            status = (row.get("ballot_rtn_status") or "").strip().upper()
            accepted = status.startswith(ACCEPTED)
            if typ in BY_MAIL:
                bucket = "mail_returned" if accepted else None
            elif typ in IN_PERSON:
                bucket = "early_in_person" if accepted else None
            else:
                unknown[typ] += 1
                bucket = None
            if bucket is None:
                continue                                 # cancelled, spoiled, pending cure
            rec = counties[cty][bucket]
            rec[party] += 1
            rec["total"] += 1
    if unknown:
        raise RuntimeError(
            f"{zip_path}: unrecognised ballot_req_type {dict(unknown.most_common(5))} "
            f"covering {sum(unknown.values()):,} rows. NC has renamed this value before "
            f"(ONE-STOP -> EARLY VOTING); add the new spelling to IN_PERSON/BY_MAIL rather "
            f"than letting these rows be dropped")
    if rows < 1000:
        raise RuntimeError(f"{zip_path}: only {rows} rows — refusing a partial file")
    if len(counties) < 90:
        raise RuntimeError(f"only {len(counties)} counties — NC has 100; refusing")
    return counties, rows


def rollup(counties):
    totals = collections.defaultdict(lambda: {"R": 0, "D": 0, "NPA": 0, "O": 0, "total": 0})
    for buckets in counties.values():
        for b, rec in buckets.items():
            for k, v in rec.items():
                totals[b][k] += v
    return {b: dict(r) for b, r in totals.items()}


def history():
    out = {"state": "NC", "unit": "county", "years": {}}
    for year, elec in sorted(HISTORY.items()):
        zp = fetch(*elec, reuse=True)   # past elections never change
        counties, rows = aggregate(zp)
        st = rollup(counties)
        out["years"][str(year)] = {
            "election": f"{year} General", "rows": rows,
            "state_totals": st,
            "counties": {c: {b: dict(r) for b, r in v.items()} for c, v in counties.items()},
            "source": URL.format(*elec)}
        m, e = st.get("mail_returned", {}), st.get("early_in_person", {})
        pct = lambda r, k: (r.get(k, 0) * 100 // r["total"]) if r.get("total") else 0
        print(f"NC {year}: {rows:,} ballots · mail {m.get('total',0):>9,} "
              f"(D {pct(m,'D')}% R {pct(m,'R')}% NPA {pct(m,'NPA')}%) · "
              f"in-person {e.get('total',0):>9,} "
              f"(D {pct(e,'D')}% R {pct(e,'R')}% NPA {pct(e,'NPA')}%)")
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "ev-history-NC.json"
    p.write_text(json.dumps(out, indent=1))
    print(f"   -> {p.name}")
    return 0


def main():
    if "--history" in sys.argv:
        return history()
    zp = fetch(*ELECTION)
    counties, rows = aggregate(zp)
    totals = collections.defaultdict(lambda: {"R": 0, "D": 0, "NPA": 0, "O": 0, "total": 0})
    for cty, buckets in counties.items():
        for b, rec in buckets.items():
            for k, v in rec.items():
                totals[b][k] += v
    payload = {"state": "NC", "unit": "county", "election": "2026 General",
               "as_of": datetime.fromtimestamp(zp.stat().st_mtime,
                                               timezone.utc).date().isoformat(),
               "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "rows": rows, "in_person": "early_in_person" in totals,
               "counties": {c: {b: dict(r) for b, r in v.items()} for c, v in counties.items()},
               "state_totals": {b: dict(r) for b, r in totals.items()},
               "source": URL.format(*ELECTION)}
    # match the shape the board reads for Florida. outstanding is NULL, not zero:
    # NC does not publish un-returned mail ballots, and an explicit null keeps the board
    # from showing a confident "0 left".
    st = payload["state_totals"]
    payload["outstanding_available"] = False
    payload["state_totals"]["returned"] = st.get("mail_returned", {})
    payload["state_totals"]["outstanding"] = None
    for c, v in payload["counties"].items():
        v["returned"] = v.get("mail_returned", {"R":0,"D":0,"NPA":0,"O":0,"total":0})
        v["outstanding"] = None
    out = pathlib.Path(__file__).resolve().parent.parent / "data" / "early-NC.json"
    out.write_text(json.dumps(payload, indent=1))
    m, e = st.get("mail_returned", {}), st.get("early_in_person", {})
    print(f"NC ok: {len(counties)} counties, {rows:,} ballot rows")
    print(f"   mail returned {m.get('total',0):>9,}  R{m.get('R',0):>8,} D{m.get('D',0):>8,} NPA{m.get('NPA',0):>8,}")
    print(f"   mail out      {'not published by NC':>9}")
    print(f"   in-person EV  {e.get('total',0):>9,}  R{e.get('R',0):>8,} D{e.get('D',0):>8,} NPA{e.get('NPA',0):>8,}")
    print(f"   -> {out.name}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as e:
        print(f"NC FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
