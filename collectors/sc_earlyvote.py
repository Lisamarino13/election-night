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

MAIL COMES FROM A SECOND SOURCE, and the reason is worth stating. South Carolina's own
absentee workbook publishes applications REQUESTED and ballots ISSUED, but not ballots
RETURNED — and returned is the number that matters. The UF Election Lab does carry an
accepted figure for SC, so mail is taken from their county file and merged in per county.
In-person stays with the state, because only the state gives the day-by-day columns.

Both sources are named in the payload. If the Lab is unreachable the in-person half still
publishes and mail is reported as unavailable rather than zero.

The file is ~10MB, nearly all of it empty rows padding to Excel's limit, so parsing stops
once the data ends.

FAILS CLOSED: any fetch or parse problem raises and writes nothing.
"""
import json, csv, io, re, sys, pathlib, urllib.request
from datetime import datetime, timezone

PAGE = "https://scvotes.gov/elections-statistics/voter-participation/"
UF_MAIL = "https://election.lab.ufl.edu/data-downloads/earlyvote/2026/SC_county.csv"
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
    # The header for this column has already changed once mid-cycle: it was "Total Voters"
    # on 10-20 and "Total " (trailing space) on 10-21. Match on the prefix rather than the
    # exact string, and fall back to the column after the last date.
    tot_i = next((i for i, c in enumerate(hdr)
                  if c.strip().lower().startswith("total")), None)
    if tot_i is None and days:
        tot_i = days[-1][0] + 1
    if tot_i is None or tot_i >= len(hdr):
        raise RuntimeError(f"no total column in header {hdr} — layout changed")

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


def mail_by_county():
    """Mail requested/returned per county from the Election Lab. ({} if unreachable.)"""
    import csv as _csv, io as _io
    try:
        rows = list(_csv.DictReader(_io.StringIO(get(UF_MAIL, 60).decode("utf-8", "ignore"))))
    except Exception as e:
        print(f"   SC: mail unavailable ({e}) — publishing in-person only", file=sys.stderr)
        return {}
    if not rows or "accept_all" not in rows[0]:
        print("   SC: Lab mail file has no accept_all column — publishing in-person only",
              file=sys.stderr)
        return {}
    out = {}
    for r in rows:
        name = (r.get("county") or "").strip().title()
        if not name:
            continue
        num = lambda k: int((r.get(k) or "0").replace(",", "") or 0)
        out[name] = {"returned": num("accept_all"), "requested": num("request_all")}
    return out


def main():
    url, label = find_csv()
    statewide, counties, days, report_date = parse(get(url))
    mail = mail_by_county()
    mail_ret = sum(v["returned"] for v in mail.values())
    mail_req = sum(v["requested"] for v in mail.values())
    # Prefer the newest DAY COLUMN over the file's own "Report Date" header: on 10-22 the
    # header said 10/20 while the table already carried a 10/21 column. The data is the
    # better authority on how current it is.
    as_of = None
    if days:
        as_of = datetime.strptime(days[-1], "%m/%d/%Y").date().isoformat()
    elif report_date:
        as_of = datetime.strptime(report_date, "%m/%d/%Y").date().isoformat()

    payload = {
        "state": "SC", "unit": "county", "election": "2026 General",
        "as_of": as_of or days[-1],
        "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "party_available": False,          # South Carolina has no party registration
        "outstanding_available": False,
        "in_person": True, "in_person_reported": True,
        "counties": {c: {"in_person": v["total"],
                         "by_mail": mail.get(c, {}).get("returned", 0),
                         "total": v["total"] + mail.get(c, {}).get("returned", 0),
                         "registered": None, "by_day": v["by_day"],
                         "outstanding_derived": max(mail.get(c, {}).get("requested", 0)
                                                    - mail.get(c, {}).get("returned", 0), 0)}
                     for c, v in counties.items()},
        "state_totals": {"registered": 0, "by_mail": mail_ret,
                         "in_person": statewide["total"],
                         "total": statewide["total"] + mail_ret,
                         "requested": mail_req},
        "daily": statewide["by_day"],
        "source": url, "mail_source": UF_MAIL if mail else None,
        "notes": {"scope": "in-person early voting from the state's own daily report; mail "
                           "from the UF Election Lab, because South Carolina's absentee "
                           "workbook publishes requested and issued but not returned",
                  "party": "South Carolina does not register by party — any D/R split "
                           "published for SC elsewhere is a vendor model, not a count"},
    }
    out = pathlib.Path(__file__).resolve().parent.parent / "data" / "early-SC.json"
    out.write_text(json.dumps(payload, indent=1))
    print(f"SC ok: {len(counties)} counties, as of {payload['as_of']} "
          f"({len(days)} early-voting day{'s' if len(days)!=1 else ''})")
    print(f"   in-person early {statewide['total']:>9,}   [turnout only, no party registration]")
    if mail:
        print(f"   mail returned   {mail_ret:>9,}   (Election Lab; SC publishes issued, "
              f"not returned)")
        print(f"   TOTAL EARLY     {statewide['total'] + mail_ret:>9,}")
    else:
        print(f"   mail returned   {'unavailable':>9}")
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
