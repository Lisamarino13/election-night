#!/usr/bin/env python3
"""Maine absentee + in-person early voting -> data/early-ME.json

Source: maine.gov/sos/cec/elec/data/index.html -> "Statewide Absentee Voter Data File (Text)"
The filename carries its own as-of date ("11-3-26 AB Voter File as of 10-16-26.txt"), so the
link is discovered from the index page every run rather than hardcoded.

Pipe-delimited, one row per ballot, 23 columns, ~16MB. Maine is the richest of the states:
it publishes BOTH streams AND a real outstanding count, by party, per municipality.

  P           D Democratic | R Republican | U Unenrolled | G Green Independent | L Libertarian
  Issued Type VP = "Voted in Clerk's Presence"  -> in-person early voting
  Status      ACT/ACU/ACH accepted | REJ/RNC rejected | PEN pending cure | blank not returned

Buckets (verified against the state's own trailer totals 2026-10-17):
  mail_returned      accepted AND has a return date      -> "Total Returned & Accepted"
  mail_outstanding   issued, no return, no status         -> "Total Not Returned/Unresolved"
  early_in_person    Issued Type VP (returned by definition — you vote at the counter)
  requested_not_issued  no issue date yet — requested but not mailed
  rejected           REJ / RNC

The file ends with the state's own totals. Those lines are parsed and asserted against this
script's aggregation; a mismatch raises. That is a free end-to-end check on the whole parse,
so a silent column shift cannot turn into a wrong number on the board.

Maine reports by MUNICIPALITY (560 of them), not county — finer than county, and both the
Senate and Governor races are statewide, so no county rollup is needed to project.

FAILS CLOSED: any fetch, parse, or reconciliation problem raises and writes nothing.
"""
import json, re, sys, pathlib, urllib.request, urllib.parse, collections
from datetime import datetime, timezone

INDEX = "https://www.maine.gov/sos/cec/elec/data/index.html"
BASE = "https://www.maine.gov"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept-Encoding": "identity"}
PARTY = {"D": "D", "R": "R", "U": "NPA"}               # G / L / X -> O
COLS = ["RES MUNICIPALITY", "P", "Ballot Type", "Req Type", "Issued Date",
        "Rec Date", "Status", "REJ", "DUP"]            # the ones this script depends on
ACCEPTED = {"ACT", "ACU", "ACH"}
REJECTED = {"REJ", "RNC"}
BUCKETS = ("mail_returned", "mail_outstanding", "early_in_person",
           "requested_not_issued", "rejected", "pending_cure")


def get(url, timeout=180):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status} for {url}")
        return r.read()


def find_file():
    """Discover the current absentee text file from the index page."""
    html = get(INDEX, 60).decode("utf-8", "ignore")
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        href, txt = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
        if re.search(r"Statewide Absentee Voter Data File\s*\(Text\)", txt, re.I):
            url = href if href.startswith("http") else BASE + href
            asof = re.search(r"as of ([\d-]+)", urllib.parse.unquote(href), re.I)
            return url, (asof.group(1) if asof else None)
    raise RuntimeError("index page has no 'Statewide Absentee Voter Data File (Text)' link "
                       "— page structure changed")


def parse_trailer(tail_lines):
    """The state's own totals from the end of the file -> {label: int}."""
    want = {"Total Number of Records": "records", "Total Requested": "requested",
            "Total Issued": "issued", "Total Returned & Accepted": "returned_accepted",
            "Total Returned & Rejected": "returned_rejected",
            "Total Returned & Pending Cure": "pending_cure",
            "Total Not Returned & Rejected": "notreturned_rejected",
            "Total Not Returned/Unresolved": "not_returned"}
    got = {}
    for line in tail_lines:
        for label, key in want.items():
            m = re.match(re.escape(label) + r"\s*:\s*([\d,]+)\s*$", line.strip())
            if m:
                got[key] = int(m.group(1).replace(",", ""))
    missing = set(want.values()) - set(got)
    if missing:
        raise RuntimeError(f"file trailer missing {sorted(missing)} — cannot reconcile")
    return got


def aggregate(raw):
    lines = raw.decode("utf-8", "ignore").splitlines()
    if not lines:
        raise RuntimeError("empty file")
    hdr = lines[0].split("|")
    for c in COLS:
        if c not in hdr:
            raise RuntimeError(f"column {c!r} missing — layout changed; got {hdr}")
    C = {n: i for i, n in enumerate(hdr)}
    n = len(hdr)

    units = collections.defaultdict(lambda: collections.defaultdict(
        lambda: {"R": 0, "D": 0, "NPA": 0, "O": 0, "total": 0}))
    tally = collections.Counter()
    data_rows = other = dup_outstanding = 0
    trailer_lines = []

    for line in lines[1:]:
        f = line.split("|")
        if len(f) != n:
            trailer_lines.append(line)                  # the state's totals block
            continue
        data_rows += 1
        g = lambda k: f[C[k]].strip()
        muni = g("RES MUNICIPALITY")
        if not muni:
            raise RuntimeError(f"row with no municipality: {line[:90]!r}")
        party = PARTY.get(g("P").upper(), "O")
        status, rec, issued = g("Status").upper(), g("Rec Date"), g("Issued Date")

        if status in ACCEPTED and rec:
            bucket = "early_in_person" if g("Issued Type").upper() == "VP" else "mail_returned"
        elif status in REJECTED:
            bucket = "rejected"
        elif status == "PEN":
            bucket = "pending_cure"
        elif not status and not rec:
            if not issued:
                bucket = "requested_not_issued"
            else:
                bucket = "mail_outstanding"
                if g("DUP"):
                    dup_outstanding += 1
        else:
            other += 1                                  # accepted w/o a return date (~34)
            continue
        r = units[muni][bucket]
        r[party] += 1
        r["total"] += 1
        tally[bucket] += 1

    if data_rows < 10_000:
        raise RuntimeError(f"only {data_rows} ballot rows — refusing a partial file")
    if len(units) < 400:
        raise RuntimeError(f"only {len(units)} municipalities — Maine has ~500; refusing")

    # --- reconcile against the state's own trailer ---------------------------------
    t = parse_trailer(trailer_lines)
    checks = [
        ("records", t["records"], data_rows),
        ("not_returned", t["not_returned"], tally["mail_outstanding"]),
        ("pending_cure", t["pending_cure"], tally["pending_cure"]),
        ("issued", t["issued"], data_rows - tally["requested_not_issued"]),
        ("returned+notreturned rejected", t["returned_rejected"] + t["notreturned_rejected"],
         tally["rejected"]),
        ("returned_accepted", t["returned_accepted"],
         tally["mail_returned"] + tally["early_in_person"]),
    ]
    bad = [f"{name}: state says {want:,}, parsed {have:,}"
           for name, want, have in checks if want != have]
    if bad:
        raise RuntimeError("does not reconcile with the state's own totals -> "
                           + "; ".join(bad))
    return units, tally, t, data_rows, other, dup_outstanding


def main():
    url, asof = find_file()
    units, tally, trailer, rows, other, dup_out = aggregate(get(url))

    totals = {b: {"R": 0, "D": 0, "NPA": 0, "O": 0, "total": 0} for b in BUCKETS}
    for buckets in units.values():
        for b, rec in buckets.items():
            for k, v in rec.items():
                totals[b][k] += v

    payload = {
        "state": "ME", "unit": "municipality", "election": "2026 General",
        "as_of": asof, "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": rows, "in_person": totals["early_in_person"]["total"] > 0,
        "outstanding_available": True,
        "units": {u: {b: dict(r) for b, r in v.items()} for u, v in units.items()},
        "state_totals": {b: dict(r) for b, r in totals.items()},
        # the board reads these two keys for every state:
        "source": url, "state_trailer": trailer,
        "notes": {
            "unclassified_rows": other,
            "duplicate_flagged_outstanding": dup_out,
            "requested_not_issued": tally["requested_not_issued"],
        },
    }
    payload["state_totals"]["returned"] = dict(totals["mail_returned"])
    payload["state_totals"]["outstanding"] = dict(totals["mail_outstanding"])
    for u, v in payload["units"].items():
        v["returned"] = v.get("mail_returned", {"R": 0, "D": 0, "NPA": 0, "O": 0, "total": 0})
        v["outstanding"] = v.get("mail_outstanding", {"R": 0, "D": 0, "NPA": 0, "O": 0, "total": 0})

    out = pathlib.Path(__file__).resolve().parent.parent / "data" / "early-ME.json"
    out.write_text(json.dumps(payload, indent=1))

    def row(label, r):
        t = r["total"] or 1
        return (f"   {label:<18}{r['total']:>9,}   D {r['D']*100//t:>2}%  R {r['R']*100//t:>2}%"
                f"  U {r['NPA']*100//t:>2}%")
    print(f"ME ok: {len(units)} municipalities, {rows:,} ballot rows, as of {asof}")
    print(f"   reconciled against the state's own trailer totals")
    print(row("mail returned", totals["mail_returned"]))
    print(row("mail outstanding", totals["mail_outstanding"]))
    print(row("in-person early", totals["early_in_person"]))
    print(f"   requested, not yet issued {tally['requested_not_issued']:,}"
          f" · rejected {tally['rejected']:,} · unclassified {other}")
    print(f"   -> {out.name}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ME FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
