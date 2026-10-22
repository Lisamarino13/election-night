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
import json, csv, io, re, sys, pathlib, urllib.request, zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, date, timedelta

PAGE = "https://scvotes.gov/elections-statistics/voter-participation/"
UF_MAIL = "https://election.lab.ufl.edu/data-downloads/earlyvote/2026/SC_county.csv"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept-Encoding": "identity"}
COUNTIES_EXPECTED = 46

# Prior cycles. South Carolina had NO no-excuse early voting before 2022 — Act 150 created
# it that May — so the 2020 archive contains absentee reports only and there is nothing to
# compare. That is a fact about the state, not a gap in the data.
HISTORY = {
    2022: ("https://scvotes.gov/wp-content/uploads/2022/12/"
           "2022-Historical-Absentee-EV-Reports.zip", "EV Stats (2022 GE"),
    2024: ("https://scvotes.gov/wp-content/uploads/2025/06/"
           "2024-Historical-Absentee-EV-Reports-1.zip", "2024-GE-Early-Voting"),
}
XLNS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def xlsx_rows(data):
    """Minimal xlsx reader: zipped XML, stdlib only. The cron host has no pip."""
    xz = zipfile.ZipFile(io.BytesIO(data))
    shared = []
    if "xl/sharedStrings.xml" in xz.namelist():
        r = ET.fromstring(xz.read("xl/sharedStrings.xml"))
        for si in r.findall(XLNS + "si"):
            shared.append("".join(t.text or "" for t in si.iter(XLNS + "t")))
    sheets = sorted(n for n in xz.namelist() if n.startswith("xl/worksheets/sheet"))
    if not sheets:
        raise RuntimeError("workbook has no worksheets")
    sh = ET.fromstring(xz.read(sheets[0]))
    out = []
    for row in sh.find(XLNS + "sheetData"):
        cells = {}
        for c in row.findall(XLNS + "c"):
            col = re.match(r"([A-Z]+)", c.get("r")).group(1)
            if c.get("t") == "inlineStr":
                is_ = c.find(XLNS + "is")
                v = "".join(t.text or "" for t in is_.iter(XLNS + "t")) if is_ is not None else ""
            elif c.get("t") == "s":
                vv = c.find(XLNS + "v")
                v = shared[int(vv.text)] if vv is not None else ""
            else:
                vv = c.find(XLNS + "v")
                v = vv.text if vv is not None else ""
            if v not in ("", None):
                cells[col] = v
        if cells:
            out.append(cells)
    return out


def _coldate(v):
    """A header cell that is a date: either 'mm/dd/yyyy' or an Excel serial number."""
    v = (v or "").strip()
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", v)
    if m:
        return date(int(m.group(3)), int(m.group(1)), int(m.group(2))).isoformat()
    if re.fullmatch(r"\d{5}", v):            # Excel serial, epoch 1899-12-30
        return (date(1899, 12, 30) + timedelta(days=int(v))).isoformat()
    return None


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


def history():
    """Prior cycles, each with its own day-by-day series -> data/ev-history-SC.json."""
    out = {"state": "SC", "unit": "county", "party_available": False, "years": {},
           "notes": {"2020": "South Carolina had no no-excuse early voting before 2022 "
                             "(Act 150, May 2022), so there is no 2020 early vote to "
                             "compare — the 2020 archive holds absentee reports only"}}
    for year, (zurl, needle) in sorted(HISTORY.items()):
        z = zipfile.ZipFile(io.BytesIO(get(zurl, 180)))
        names = [n for n in z.namelist() if needle in n and n.lower().endswith(".xlsx")
                 and "__MACOSX" not in n]
        if not names:
            raise RuntimeError(f"{year}: no sheet matching {needle!r} in {zurl}")
        rows = xlsx_rows(z.read(names[0]))
        hdr_i = next((i for i, r in enumerate(rows[:12])
                      if any(str(v).strip() in ("Jurisdiction", "County") for v in r.values())), None)
        if hdr_i is None:
            raise RuntimeError(f"{year}: no header row")
        hdr = rows[hdr_i]
        days = [(c, _coldate(v)) for c, v in hdr.items() if _coldate(v)]
        days.sort(key=lambda x: x[1])
        tot_col = next((c for c, v in hdr.items()
                        if str(v).strip().lower().startswith("total")), None)
        if not days or not tot_col:
            raise RuntimeError(f"{year}: header has no day columns or no total ({hdr})")
        num = lambda v: int(re.sub(r"[^\d-]", "", str(v or "")) or 0)

        # TWO LAYOUTS. 2024 and 2026 put the jurisdiction in column A, the polling place in
        # column C, and carry a "South Carolina" statewide row. 2022 has no statewide row at
        # all: county rows are "<County> Total" and the rows beneath them are polling places
        # with plain names. Detect which one this is rather than assume.
        # The statewide row is called "South Carolina" in 2024/2026 and "Statewide Total"
        # in 2022. Counting it as a county is how 2022 came to 47.
        is_statewide = lambda v: re.sub(r"\s*total\s*$", "", v.strip(), flags=re.I).lower() in (
            "south carolina", "statewide")
        # Distinguish the layouts by what column C IS, read from the header — not by
        # whether column C has data. In 2024/2026 it is "Poll Place"; in 2022 it is a DAY
        # column holding counts, so testing for data there skipped every row and summed the
        # counties to zero.
        day_cols = {c for c, _ in days}
        uses_col_c = ("C" not in day_cols
                      and str(hdr.get("C", "")).strip().lower().startswith("poll"))
        statewide, counties = None, {}
        for r in rows[hdr_i + 1:]:
            first = (r.get("A") or "").strip()
            if not first:
                continue
            rec = {"total": num(r.get(tot_col)),
                   "by_day": {d: num(r.get(c)) for c, d in days}}
            if is_statewide(first):
                statewide = rec
                continue
            if uses_col_c:
                if (r.get("C") or "").strip():
                    continue                  # polling-place sub-row
                name = first
            else:
                if not first.lower().endswith("total"):
                    continue                  # polling place under the county above it
                name = re.sub(r"\s*total\s*$", "", first, flags=re.I)
            counties[re.sub(r"^\d+\s+", "", name).strip().title()] = rec

        summed = sum(c["total"] for c in counties.values())
        if statewide is None:
            # 2022 publishes no statewide row; build it from the counties and say so
            by_day = {d: sum(c["by_day"].get(d, 0) for c in counties.values())
                      for _, d in days}
            statewide = {"total": summed, "by_day": by_day}
        elif summed != statewide["total"]:
            raise RuntimeError(f"{year}: counties sum to {summed:,}, statewide row says "
                               f"{statewide['total']:,}")
        if len(counties) != COUNTIES_EXPECTED:
            raise RuntimeError(f"{year}: {len(counties)} counties, South Carolina has "
                               f"{COUNTIES_EXPECTED}")
        run, series = 0, {}
        for d in [x[1] for x in days]:
            run += statewide["by_day"][d]
            series[d] = run
        out["years"][str(year)] = {
            "election": f"{year} General", "cycle": "presidential" if year % 4 == 0 else "midterm",
            "counties": len(counties),
            "state_totals": {"in_person": statewide["total"], "by_mail": 0,
                             "total": statewide["total"], "registered": 0},
            "daily": statewide["by_day"], "running": series,
            "days": [x[1] for x in days], "source": zurl}
        print(f"SC {year}: {len(counties)} counties, {len(days)} early-voting days, "
              f"final in-person {statewide['total']:,}")
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "ev-history-SC.json"
    p.write_text(json.dumps(out, indent=1))
    print(f"   -> {p.name}   (no 2020: early voting did not exist in SC until 2022)")
    return 0


def main():
    if "--history" in sys.argv:
        return history()
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
