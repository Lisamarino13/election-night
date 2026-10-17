#!/usr/bin/env python3
"""Iowa absentee + in-person early voting -> data/early-IA.json

Source: sos.iowa.gov/sites/default/files/<YYYY-MM>/AbsenteeCounty2026.pdf
There is no standing index page for this file, so the month folder is discovered by probing
the current month and the two either side of it. The name differs from the primary's
("Absentee County 2026.pdf" with spaces) — do not assume one from the other.

Structure is hierarchical, three columns (Requested, Issued, Received):

    Adair                              303  303   48     <- county
      Democrat                         106  106   20     <-   party
        Counter / In-Office             20   20   20     <-     receipt method
        Ballot not yet returned by voter 86  86          <-     OUTSTANDING (2 cols)

So Iowa gives everything at once: county, party, mail vs in person, and a real outstanding
count. Only Maine is as complete.

Receipt methods seen 2026-10-17 (including "In-Person", which appears once in the
whole file for a single ballot), all of them classified below — an unrecognised one raises
rather than being dropped, because a silently ignored method is a silently wrong total
(that is exactly how North Carolina's 4.1M in-person ballots became a zero).

The PDF ends with a "Grand Total" row and a "Prepared by ... <date>" footer. Both are used:
the date is the as-of, and the grand total is asserted against this script's own sum.

NOTE: needs pdfplumber (the only collector that does). If it is missing this exits 3 with
an install hint rather than pretending Iowa has no data.

FAILS CLOSED: any fetch, parse, or reconciliation problem raises and writes nothing.
"""
import json, re, sys, pathlib, urllib.request, collections
from datetime import datetime, timezone, date

BASE = "https://sos.iowa.gov/sites/default/files/{month}/AbsenteeCounty2026.pdf"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
PARTY = {"Democrat": "D", "Republican": "R", "No Party": "NPA", "Other": "O"}
IN_PERSON = {"Counter / In-Office", "Satellite", "Health Care Facility", "In-Person"}
BY_MAIL = {"Mail", "E-Mail"}
OUTSTANDING = "Ballot not yet returned by voter"
SKIP = re.compile(r"^(Absentee Ballot Statistics|November \d+, General Election|"
                  r"County/|Data Pulled:|Prepared by the Office)")
EMPTY = {"R": 0, "D": 0, "NPA": 0, "O": 0, "total": 0}


def fetch():
    today = date.today()
    months, seen = [], set()
    for delta in (0, -1, 1):
        m = (today.month - 1 + delta) % 12 + 1
        y = today.year + (today.month - 1 + delta) // 12
        key = f"{y:04d}-{m:02d}"
        if key not in seen:
            seen.add(key); months.append(key)
    last = None
    for month in months:
        url = BASE.format(month=month)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                if r.status == 200:
                    body = r.read()
                    if body[:4] == b"%PDF":
                        return url, body
                    last = f"{url}: not a PDF"
        except Exception as e:
            last = f"{url}: {e}"
    raise RuntimeError(f"no AbsenteeCounty2026.pdf in {months} (last: {last})")


def parse(body):
    import pdfplumber, io
    counties = collections.defaultdict(lambda: collections.defaultdict(lambda: dict(EMPTY)))
    grand, as_of, county, party = None, None, None, None
    unknown = collections.Counter()
    totals_seen = {}

    with pdfplumber.open(io.BytesIO(body)) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").splitlines():
                line = line.strip()
                if not line:
                    continue
                m = re.search(r"Prepared by the Office of Iowa Secretary of State\s+"
                              r"(\d{1,2}/\d{1,2}/\d{4})", line)
                if m and not as_of:
                    as_of = datetime.strptime(m.group(1), "%m/%d/%Y").date().isoformat()
                if SKIP.match(line):
                    continue
                g = re.match(r"^(.*?)((?:\s+[\d,]+)+)$", line)
                if not g:
                    continue
                label = g.group(1).strip()
                nums = [int(x.replace(",", "")) for x in g.group(2).split()]

                if label == "Grand Total":
                    grand = nums
                    continue
                if label in PARTY:
                    party = PARTY[label]
                    continue
                if label == OUTSTANDING:
                    if county and party:
                        rec = counties[county]["mail_outstanding"]
                        rec[party] += nums[0]; rec["total"] += nums[0]
                    continue
                if label in IN_PERSON or label in BY_MAIL:
                    if county and party and len(nums) >= 3:
                        key = "early_in_person" if label in IN_PERSON else "mail_returned"
                        rec = counties[county][key]
                        rec[party] += nums[2]; rec["total"] += nums[2]
                    continue
                # anything else with numbers at this indent level is a county header
                if re.match(r"^[A-Z][A-Za-z'’. ]+$", label) and len(nums) >= 2:
                    county, party = label, None
                    totals_seen[county] = nums
                    continue
                unknown[label] += 1

    if unknown:
        raise RuntimeError(f"unrecognised row labels {dict(unknown.most_common(5))} — Iowa "
                           f"added a receipt method or party; classify it rather than "
                           f"dropping the rows")
    if len(counties) != 99:
        raise RuntimeError(f"{len(counties)} counties, Iowa has 99 — refusing")
    if not as_of:
        raise RuntimeError("no 'Prepared by ... <date>' footer — cannot date this pull")
    if not grand:
        raise RuntimeError("no Grand Total row — cannot reconcile")

    # --- reconcile received against the state's own Grand Total -----------------------
    got = sum(c["mail_returned"]["total"] + c["early_in_person"]["total"]
              for c in counties.values())
    if got != grand[2]:
        raise RuntimeError(f"received total {got:,} != Grand Total {grand[2]:,} — parse is "
                           f"dropping or double counting rows")
    return counties, as_of, grand


def main():
    try:
        import pdfplumber  # noqa: F401
    except ImportError:
        print("IA needs pdfplumber:  python3 -m pip install --user pdfplumber",
              file=sys.stderr)
        return 3
    url, body = fetch()
    counties, as_of, grand = parse(body)

    totals = {b: dict(EMPTY) for b in ("mail_returned", "early_in_person", "mail_outstanding")}
    for buckets in counties.values():
        for b, rec in buckets.items():
            for k, v in rec.items():
                totals[b][k] += v

    payload = {"state": "IA", "unit": "county", "election": "2026 General",
               "as_of": as_of, "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "in_person": totals["early_in_person"]["total"] > 0,
               "outstanding_available": True,
               "counties": {c: {b: dict(r) for b, r in v.items()} for c, v in counties.items()},
               "state_totals": {b: dict(r) for b, r in totals.items()},
               "grand_total": {"requested": grand[0], "issued": grand[1], "received": grand[2]},
               "source": url}
    payload["state_totals"]["returned"] = dict(totals["mail_returned"])
    payload["state_totals"]["outstanding"] = dict(totals["mail_outstanding"])
    for v in payload["counties"].values():
        v["returned"] = v.get("mail_returned", dict(EMPTY))
        v["outstanding"] = v.get("mail_outstanding", dict(EMPTY))

    out = pathlib.Path(__file__).resolve().parent.parent / "data" / "early-IA.json"
    out.write_text(json.dumps(payload, indent=1))

    def row(lab, r):
        t = r["total"] or 1
        return (f"   {lab:<18}{r['total']:>9,}   D {r['D']*100//t:>2}%  R {r['R']*100//t:>2}%"
                f"  NP {r['NPA']*100//t:>2}%")
    print(f"IA ok: {len(counties)} counties, as of {as_of} (reconciled to the state's Grand Total)")
    print(row("mail returned", totals["mail_returned"]))
    print(row("mail outstanding", totals["mail_outstanding"]))
    print(row("in-person early", totals["early_in_person"]))
    print(f"   -> {out.name}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"IA FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
