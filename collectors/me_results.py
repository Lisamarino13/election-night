#!/usr/bin/env python3
"""Maine election-night results by municipality -> data/results-ME.json

Maine does not run an election-night results service. It posts a SPREADSHEET per
contest to its results index, one row per municipality, grouped by county, and those
files only appear once counting is under way. So there is nothing to poll before the
night and nothing to read but xlsx.

    index: maine.gov/sos/cec/elec/results/index.html
    files: /sos/sites/maine.gov.sos/files/inline-files/<contest>[ <party>] - FINAL.xlsx

Two things make Maine different from every other state here.

MUNICIPALITIES, NOT COUNTIES. Maine reports ~500 towns, and the county is a grouping
header inside the file rather than the reporting unit. The projection works the same
way - a unit's own counted share applied to its own remaining ballots - it just has
five hundred units instead of sixteen. The early-vote collector already keys on
municipality, so the two line up.

IT CANNOT RUN ON THE CRON HOST. maine.gov refuses that datacenter IP, which is why
Maine's early vote already comes from laptop.sh. This has the same constraint and says
so loudly rather than failing mysteriously at 8pm on the night. It is also easy to
rate-limit yourself off maine.gov by probing it - that happened while this was being
written - so the index is fetched once and the files are fetched one at a time.

Exit 2 means the general-election files are not posted yet, which is the expected
answer until polls close.
"""
import io, json, pathlib, re, sys, urllib.parse, urllib.request, zipfile, collections
from datetime import datetime, timezone
import election_day

INDEX = "https://www.maine.gov/sos/cec/elec/results/index.html"
BASE = "https://www.maine.gov"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
      "Accept-Language": "en-US,en;q=0.9", "Referer": INDEX}
# Maine's 16 county abbreviations appear as grouping rows inside each file.
COUNTIES = {"AND": "Androscoggin", "ARO": "Aroostook", "CUM": "Cumberland",
            "FRA": "Franklin", "HAN": "Hancock", "KEN": "Kennebec", "KNO": "Knox",
            "LIN": "Lincoln", "OXF": "Oxford", "PEN": "Penobscot", "PIS": "Piscataquis",
            "SAG": "Sagadahoc", "SOM": "Somerset", "WAL": "Waldo", "WAS": "Washington",
            "YOR": "York"}
WANT = {"senate": r"US\s*Senate", "governor": r"\bGovernor\b"}
# A primary file carries a party in its name; a general does not. Reading a primary as
# the general would publish one party's contest as the whole race.
PRIMARY = re.compile(r"\b(DEM|REP|Democratic|Republican|Primary|UOCAVA|RCV)\b", re.I)


def get(url, timeout=120):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError(f"{url}: HTTP {r.status}")
        return r.read()


def xlsx_rows(data):
    """Minimal xlsx reader: zipped XML, stdlib only. Same approach as sc_earlyvote."""
    xz = zipfile.ZipFile(io.BytesIO(data))
    shared = []
    if "xl/sharedStrings.xml" in xz.namelist():
        sst = xz.read("xl/sharedStrings.xml").decode("utf-8", "ignore")
        shared = [re.sub(r"<[^>]+>", "", s)
                  for s in re.findall(r"<si>(.*?)</si>", sst, re.S)]
    sheets = [n for n in xz.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)]
    if not sheets:
        raise RuntimeError("xlsx: no worksheet")
    ws = xz.read(sorted(sheets)[0]).decode("utf-8", "ignore")
    out = []
    for row in re.findall(r"<row[^>]*>(.*?)</row>", ws, re.S):
        vals = []
        for c in re.finditer(r'<c([^>]*)>(?:<v>([^<]*)</v>|<is>(.*?)</is>)?</c>', row, re.S):
            attrs, v, inline = c.group(1), c.group(2), c.group(3)
            if inline is not None:
                vals.append(re.sub(r"<[^>]+>", "", inline))
            elif v is None:
                vals.append("")
            elif 't="s"' in attrs:
                i = int(v)
                vals.append(shared[i] if 0 <= i < len(shared) else "")
            else:
                vals.append(v)
        out.append(vals)
    return out


def find_files():
    """{race: (url, label)} for the GENERAL election files, if they are posted."""
    html = get(INDEX, 90).decode("utf-8", "ignore")
    found = {}
    for href, _ in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        if not href.lower().endswith((".xlsx", ".xls")):
            continue
        name = urllib.parse.unquote(href.rsplit("/", 1)[-1])
        if PRIMARY.search(name):
            continue                      # a primary file is one party's contest, not the race
        race = next((k for k, pat in WANT.items() if re.search(pat, name, re.I)), None)
        if race is None:
            continue
        url = href if href.startswith("http") else BASE + href
        if race in found and found[race][1] != name:
            raise RuntimeError(f"{race!r} matched two files: {found[race][1]!r} and {name!r}")
        found[race] = (url, name)
    return found


def parse(rows):
    """{municipality: {candidate: votes}} and each town's county.

    The layout is a header row then one row per town:

        CTY | Municipality | COSTELLO, DAVID A | MILLS, JANET T | ... | BLANK | TBC
        AND | Auburn      |               280 |            564 | ... |     72

    The county is a COLUMN, not a grouping row - reading it as a grouping row found
    no municipalities at all, which the ~500 guard caught rather than publishing an
    empty state. BLANK (blank ballots) and TBC are counted separately from candidates
    so they cannot be mistaken for one.
    """
    hdr_i = None
    for i, r in enumerate(rows[:40]):
        cells = [str(c).strip().upper() for c in r]
        if "CTY" in cells and any(c.startswith("MUNICIPAL") for c in cells):
            hdr_i = i
            break
    if hdr_i is None:
        raise RuntimeError("could not find the 'CTY / Municipality' header row")
    header = [str(c).strip() for c in rows[hdr_i]]
    up = [c.upper() for c in header]
    cty_col = up.index("CTY")
    muni_col = next(j for j, c in enumerate(up) if c.startswith("MUNICIPAL"))
    cand_cols, extra_cols = {}, {}
    for j, c in enumerate(header):
        if j in (cty_col, muni_col) or not c:
            continue
        (extra_cols if c.upper() in ("BLANK", "TBC") else cand_cols)[j] = c

    units, county_of, extras = {}, {}, {}
    for r in rows[hdr_i + 1:]:
        if len(r) <= muni_col:
            continue
        muni = str(r[muni_col]).strip()
        cty = str(r[cty_col]).strip().upper() if len(r) > cty_col else ""
        if not muni or cty not in COUNTIES:
            continue                       # totals rows and the write-in legend
        grab = lambda cols: {name: int(float(str(r[j]).strip()))
                             for j, name in cols.items()
                             if j < len(r) and re.fullmatch(
                                 r"-?\d+(?:\.0+)?", str(r[j]).strip() or "x")}
        tally = grab(cand_cols)
        if not tally:
            continue
        units[muni] = tally
        county_of[muni] = COUNTIES[cty]
        extras[muni] = grab(extra_cols)
    if len(units) < 300:
        raise RuntimeError(f"only {len(units)} municipalities \u2014 Maine has ~500; refusing")
    return units, county_of, extras


def early_cast():
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "early-ME.json"
    if not p.exists():
        return {}, None
    d = json.loads(p.read_text())
    out = {}
    for muni, b in (d.get("counties") or d.get("units") or {}).items():
        g = lambda k: (b[k].get("total") if isinstance(b.get(k), dict) else b.get(k)) or 0
        out[muni.strip().title()] = g("mail_returned") + g("early_in_person")
    return out, d.get("as_of")


def main():
    if "--proof" in sys.argv:
        i = sys.argv.index("--proof")
        rows = xlsx_rows(get(sys.argv[i + 1]))
        units, county_of, extras = parse(rows)
        tot = collections.Counter()
        for t in units.values():
            tot.update(t)
        print(f"ME proof: {len(units)} municipalities across "
              f"{len(set(v for v in county_of.values() if v))} counties")
        for c, v in tot.most_common(5):
            print(f"   {c:34} {v:>9,}")
        return 0

    files = find_files()
    if not files:
        print("ME: no general-election result files posted yet (Maine posts a spreadsheet "
              "per contest once counting is under way)")
        return 2
    cast, cast_as_of = early_cast()
    units_out, totals = {}, {}
    for race, (url, label) in sorted(files.items()):
        units, county_of, extras = parse(xlsx_rows(get(url)))
        tally = collections.Counter()
        for muni, t in units.items():
            rec = units_out.setdefault(muni, {"county": county_of.get(muni), "races": {}})
            rec["races"][race] = {
                "choices": {c: {"party": "O", "votes": v}
                            for c, v in sorted(t.items(), key=lambda x: -x[1])},
                "counted": sum(t.values()),
                "early_and_mail_cast": cast.get(muni.strip().title()),
                "blank_and_tbc": extras.get(muni) or {},
            }
            tally.update(t)
        totals[race] = {"contest_name": label, "choices": dict(tally.most_common()),
                        "total": sum(tally.values()), "units": len(units)}
    payload = {
        "state": "ME", "unit": "municipality", "source_kind": "maine-sos-xlsx",
        "election": "2026 General",
        "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "early_cast_as_of": cast_as_of,
        "counties": units_out, "state_totals": totals,
        "source": INDEX,
        "notes": {
            "unit": "Maine reports by municipality (~500), not county; the county is a "
                    "grouping inside each file. The projection runs per municipality.",
            "host": "maine.gov refuses the cron host's datacenter IP, so this must run "
                    "from the laptop, like Maine's early-vote pull.",
            "modes": "Maine's result files carry no early/election-day split, so the "
                     "precinct scaling stays off here.",
        },
    }
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "results-ME.json"
    rc = election_day.write_or_hold("ME", p, payload, totals)
    if rc:
        return rc
    for race, t in totals.items():
        print(f"ME {race}: {t['total']:,} votes across {t['units']} municipalities")
    print(f"   -> {p.name}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as e:
        msg = str(e)
        if "403" in msg or "Request blocked" in msg:
            print(f"ME: maine.gov refused this host ({msg[:90]}) — it blocks datacenter "
                  f"IPs, so this must run from the laptop", file=sys.stderr)
            sys.exit(2)
        print(f"ME RESULTS FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
