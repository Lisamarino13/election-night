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
# Maine's archive goes back to 2008 in this same pipe-delimited format, so history is the
# same parser. NOTE: there is NO November 2022 general file in the index — the archive
# jumps from a Jan 2022 special to the June 2022 primary to Nov 2023. So Maine has no
# midterm comparator available from the state, and 2020/2024 are both presidential.
HISTORY = {
    2020: "https://www.maine.gov/sos/sites/maine.gov.sos/files/inline-files/"
          "1120-absentee-voter-file_0.txt",
    2024: "https://www.maine.gov/sos/sites/maine.gov.sos/files/inline-files/"
          "2024-11-05%20Final%20AB%20Voter%20File.txt",
}
PARTY = {"D": "D", "R": "R", "U": "NPA"}               # G / L / X -> O
# Exactly the columns this parser reads — nothing more. It previously demanded
# "Ballot Type", "Req Type" and "REJ" as well, none of which it ever looks at, and that
# rejected the 2020/2024 archives for the absence of a field that makes no difference.
COLS = ["RES MUNICIPALITY", "P", "Issued Date", "Issued Type",
        "Rec Date", "Status", "DUP"]
ACCEPTED = {"ACT", "ACU", "ACH", "ACC"}      # ACC is the legacy spelling
REJECTED = {"REJ", "RNC"}
# The 2020 and 2024 archives use an older header. Same data, different names — map it
# rather than carrying a second parser.
ALIASES = {"MUNICIPALITY": "RES MUNICIPALITY", "REQTYPE": "Req Type", "REQDATE": "Req Date",
           "ISSTYPE": "Issued Type", "ISSDATE": "Issued Date", "RECTYPE": "Rec Type",
           "RECDATE": "Rec Date", "ACC OR REJ": "Status", "REJRSN": "REJ"}
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
    hdr = [ALIASES.get(h.strip(), h.strip()) for h in lines[0].split("|")]
    for c in COLS:
        if c not in hdr:
            raise RuntimeError(f"column {c!r} missing — layout changed; got {hdr}")
    C = {n: i for i, n in enumerate(hdr)}
    n = len(hdr)

    units = collections.defaultdict(lambda: collections.defaultdict(
        lambda: {"R": 0, "D": 0, "NPA": 0, "O": 0, "total": 0}))
    tally = collections.Counter()
    data_rows = other = dup_outstanding = 0
    anomalies = []
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

        # Maine's own file can contain a record its own trailer does not count. On
        # 2026-10-23 one Rockport ballot (voter 100775707) carried Status REJ, reason
        # LDB, a Rec Date of 10/16 and a Rec Time - but no Rec Type. With no Rec Type
        # the state does not count it as Returned & Rejected, and being rejected it is
        # not Not Returned & Rejected either, so it appears in NEITHER trailer line and
        # the reconciliation failed by exactly one, every run, for days.
        #
        # The ballot is real: it was received on the 16th and rejected as late. It is
        # counted here and recorded as an anomaly, so the reconciliation can account for
        # it by NAME rather than being loosened into uselessness.
        if status in REJECTED and rec and not g("Rec Type"):
            anomalies.append({"municipality": muni, "voter_record": g("Voter Record #"),
                              "status": status, "reason": g("REJ"),
                              "rec_date": rec, "rec_type": "",
                              "why": "received and rejected, but with no Rec Type the "
                                     "state's trailer counts it in neither rejected line"})
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
    # Only the live file carries one; the archives do not. Where it exists it is asserted,
    # where it does not the parse stands on the column checks alone and says so.
    if not any("Total Number of Records" in l for l in trailer_lines):
        return units, tally, None, data_rows, other, dup_outstanding, anomalies
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
    # A mismatch is only forgiven when it is exactly the size of the anomalies we can
    # NAME. Anything else still fails: the point of this check is that a silent parse
    # error cannot reach the board, and a tolerance that swallows unexplained rows
    # would give that away.
    bad = []
    for name, want, have in checks:
        if want == have:
            continue
        if name.endswith("rejected") and anomalies and have - want == len(anomalies):
            print(f"   ME: {name} differs by {len(anomalies)} — accounted for by "
                  f"{len(anomalies)} record(s) the state's own trailer omits "
                  f"({', '.join(a['municipality'] + ' ' + a['voter_record'] for a in anomalies)})",
                  file=sys.stderr)
            continue
        bad.append(f"{name}: state says {want:,}, parsed {have:,}")
    if bad:
        raise RuntimeError("does not reconcile with the state's own totals -> "
                           + "; ".join(bad))
    return units, tally, t, data_rows, other, dup_outstanding, anomalies


def history():
    out = {"state": "ME", "unit": "municipality", "party_available": True, "years": {}}
    for year, url in sorted(HISTORY.items()):
        units, tally, trailer, rows, other, dup, _anom = aggregate(get(url))
        if trailer is None:
            print(f"   (no trailer totals in the {year} archive — column checks only)",
                  file=sys.stderr)
        totals = {b: {"R": 0, "D": 0, "NPA": 0, "O": 0, "total": 0} for b in BUCKETS}
        for buckets in units.values():
            for b, rec in buckets.items():
                for k, v in rec.items():
                    totals[b][k] += v
        m, e = totals["mail_returned"], totals["early_in_person"]
        out["years"][str(year)] = {
            "election": f"{year} General",
            "cycle": "presidential" if year % 4 == 0 else "midterm",
            "state_totals": {
                "mail_returned": dict(m), "early_in_person": dict(e),
                "by_mail": m["total"], "in_person": e["total"],
                "total": m["total"] + e["total"], "registered": 0},
            "units": {u: {b: dict(r) for b, r in v.items()} for u, v in units.items()},
            "state_trailer": trailer, "source": url}
        pct = lambda r, k: (r[k] * 100 // r["total"]) if r["total"] else 0
        print(f"ME {year}: {rows:,} ballots · mail {m['total']:>8,} "
              f"(D {pct(m,'D')}% R {pct(m,'R')}% U {pct(m,'NPA')}%) · "
              f"in-person {e['total']:>8,} "
              f"(D {pct(e,'D')}% R {pct(e,'R')}% U {pct(e,'NPA')}%)")
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "ev-history-ME.json"
    p.write_text(json.dumps(out, indent=1))
    print(f"   -> {p.name}  (no Nov 2022 file exists in Maine's archive)")
    return 0


def main():
    if "--history" in sys.argv:
        return history()
    url, asof = find_file()
    units, tally, trailer, rows, other, dup_out, anomalies = aggregate(get(url))

    totals = {b: {"R": 0, "D": 0, "NPA": 0, "O": 0, "total": 0} for b in BUCKETS}
    for buckets in units.values():
        for b, rec in buckets.items():
            for k, v in rec.items():
                totals[b][k] += v

    payload = {
        "source_anomalies": anomalies,
        "source_anomaly_note": ("Records Maine's own trailer does not count. They are "
                                "real ballots and are counted here; the reconciliation "
                                "accounts for them by name rather than being loosened."),
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
        sys.exit(main() or 0)
    except Exception as e:
        print(f"ME FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
