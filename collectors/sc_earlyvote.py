#!/usr/bin/env python3
"""South Carolina early voting by county -> data/early-SC.json

Source: scvotes.gov "Early Voting Turnout Report", a CSV linked from
  https://scvotes.gov/elections-statistics/voter-participation/
The filename carries its own date (EV-Totals-10-20-26-1.csv), so the link is discovered
from that page every run rather than guessed.

Layout:
    row 0/1   Election Date, Report Date
    row 3     Jurisdiction | Election Name | Poll Place | ... | <one column per EV day> | Total
    row 4     South Carolina  <- statewide
    then      a county row (Jurisdiction and Election Name set, Poll Place empty)
              followed by one row per polling place (Poll Place set) which are its parts

A COLUMN PER DAY is the thing worth having here: most states publish a running total only,
so South Carolina gives a real daily series for free rather than one we have to accumulate.

NO PARTY. South Carolina does not register voters by party, so this is turnout only. The
D/R split shown for SC on national trackers is TargetSmart's model, not a count, and is
deliberately not reproduced here. The state does publish absentee statistics by RACE in a
separate file; that is not folded in, because race is not party.

This is EARLY IN-PERSON voting only — absentee/mail is a separate SC report.

The file is ~10MB, nearly all of it empty rows padding to Excel's limit, so parsing stops
once the data ends.

FAILS CLOSED: any fetch or parse problem raises and writes nothing.
"""
import json, csv, io, re, sys, pathlib, urllib.request
from datetime import datetime, timezone

PAGE = "https://scvotes.gov/elections-statistics/voter-participation/"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept-Encoding": "identity"}
COUNTIES_EXPECTED = 46


def get(url, timeout=120):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status} for {url}")
        return r.read()


def find_csv():
    """Newest EV-Totals CSV linked from the participation page."""
    html = get(PAGE, 60).decode("utf-8", "ignore")
    hits = []
    for m in re.finditer(r'href="([^"]*EV-Totals[^"]*\.csv)"[^>]*>(.*?)</a>', html, re.S | re.I):
        url, label = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        d = re.search(r"(\d{1,2})-(\d{1,2})-(\d{2})", url)
        key = (f"20{d.group(3)}", d.group(1).zfill(2), d.group(2).zfill(2)) if d else ("0", "0", "0")
        hits.append((key, url, label))
    if not hits:
        raise RuntimeError("no EV-Totals CSV linked on the participation page — "
                           "page structure changed or early voting has not started")
    hits.sort()
    return hits[-1][1], hits[-1][2]


def parse(body):
    rows = list(csv.reader(io.StringIO(body.decode("utf-8", "ignore"))))
    hdr_i = next((i for i, r in enumerate(rows[:20])
                  if r and r[0].strip() == "Jurisdiction"), None)
    if hdr_i is None:
        raise RuntimeError("no 'Jurisdiction' header row — layout changed")
    hdr = rows[hdr_i]
    days = [(i, c.strip()) for i, c in enumerate(hdr)
            if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", c.strip())]
    if not days:
        raise RuntimeError(f"no date columns in header {hdr} — layout changed")
    tot_i = next((i for i, c in enumerate(hdr) if c.strip().lower() == "total voters"), None)
    if tot_i is None:
        raise RuntimeError("no 'Total Voters' column — layout changed")

    report_date = None
    for r in rows[:hdr_i]:
        for c in r:
            m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", c or "")
            if m and "/2026" in m.group(1):
                report_date = m.group(1)
    num = lambda s: int(re.sub(r"[^\d-]", "", s or "") or 0)

    statewide, counties = None, {}
    for r in rows[hdr_i + 1:]:
        if len(r) <= tot_i or not any(x.strip() for x in r):
            if counties and len(counties) >= COUNTIES_EXPECTED:
                break                       # past the data; the rest is Excel padding
            continue
        juris, elec, place = r[0].strip(), r[1].strip(), r[2].strip()
        if not juris or place:
            continue                        # polling-place sub-row, already in its county
        rec = {"total": num(r[tot_i]),
               "by_day": {d: num(r[i]) for i, d in days}}
        if juris.lower() == "south carolina":
            statewide = rec
        elif elec:
            counties[juris] = rec

    if statewide is None:
        raise RuntimeError("no 'South Carolina' statewide row — refusing")
    if len(counties) != COUNTIES_EXPECTED:
        raise RuntimeError(f"{len(counties)} counties, South Carolina has "
                           f"{COUNTIES_EXPECTED} — refusing")
    summed = sum(c["total"] for c in counties.values())
    if summed != statewide["total"]:
        raise RuntimeError(f"counties sum to {summed:,} but the statewide row says "
                           f"{statewide['total']:,} — parse is dropping or double counting")
    return statewide, counties, [d for _, d in days], report_date


def main():
    url, label = find_csv()
    statewide, counties, days, report_date = parse(get(url))
    as_of = None
    if report_date:
        as_of = datetime.strptime(report_date, "%m/%d/%Y").date().isoformat()

    payload = {
        "state": "SC", "unit": "county", "election": "2026 General",
        "as_of": as_of or days[-1],
        "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "party_available": False,          # South Carolina has no party registration
        "outstanding_available": False,
        "in_person": True, "in_person_reported": True,
        "counties": {c: {"in_person": v["total"], "by_mail": 0, "total": v["total"],
                         "registered": None, "by_day": v["by_day"]}
                     for c, v in counties.items()},
        "state_totals": {"registered": 0, "by_mail": 0,
                         "in_person": statewide["total"], "total": statewide["total"]},
        "daily": statewide["by_day"],
        "source": url,
        "notes": {"scope": "early IN-PERSON voting only; absentee/mail is a separate SC report",
                  "party": "South Carolina does not register by party — any D/R split "
                           "published for SC elsewhere is a vendor model, not a count"},
    }
    out = pathlib.Path(__file__).resolve().parent.parent / "data" / "early-SC.json"
    out.write_text(json.dumps(payload, indent=1))
    print(f"SC ok: {len(counties)} counties, as of {payload['as_of']} "
          f"({len(days)} early-voting day{'s' if len(days)!=1 else ''})")
    print(f"   in-person early {statewide['total']:>9,}   [turnout only, no party registration]")
    for d in days:
        print(f"      {d}  {statewide['by_day'][d]:>9,}")
    print(f"   -> {out.name}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"SC FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
