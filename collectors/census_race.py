#!/usr/bin/env python3
"""County race/ethnicity from the Census population estimates, for the states
whose voter file carries no race (Texas above all).

Uses the Vintage 2024 county estimates (YEAR=6 is the 7/1/2024 estimate).
Counts AGEGRP 5..18 -- age 20 and over -- not total population: the Hispanic
population is markedly younger, so total population overstates its share of
the ELECTORATE.  Ages 18-19 are not a clean group in this file and are left
out; that is a known, stated gap, not a rounding choice.

The Census API now demands a key, so this reads the published bulk file.
"""
import csv, io, json, os, sys, urllib.request, collections, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "county-race.json")
URL = ("https://www2.census.gov/programs-surveys/popest/datasets/"
       "2020-2024/counties/asrh/cc-est2024-alldata-{fips}.csv")

FIPS = {"AK": "02", "FL": "12", "GA": "13", "IA": "19", "KS": "20", "LA": "22",
        "ME": "23", "MI": "26", "MN": "27", "NC": "37", "NE": "31", "OH": "39",
        "SC": "45", "TX": "48"}
YEAR, AGES = "6", {str(i) for i in range(5, 19)}  # 7/1/2024 estimate, age 20+

GROUPS = {"white": ("NHWA_MALE", "NHWA_FEMALE"),
          "black": ("NHBA_MALE", "NHBA_FEMALE"),
          "asian": ("NHAA_MALE", "NHAA_FEMALE"),
          "native": ("NHIA_MALE", "NHIA_FEMALE"),
          "hispanic": ("H_MALE", "H_FEMALE")}


def norm(name):
    n = str(name).strip().upper()
    for suf in (" COUNTY", " PARISH", " CENSUS AREA", " BOROUGH",
                " CITY AND BOROUGH", " MUNICIPALITY", " CITY"):
        if n.endswith(suf):
            n = n[: -len(suf)]
            break
    return "".join(ch for ch in n if ch.isalnum())


def one_state(code):
    with urllib.request.urlopen(URL.format(fips=FIPS[code]), timeout=180) as r:
        raw = r.read().decode("utf-8-sig", "replace")
    rows = list(csv.DictReader(io.StringIO(raw)))
    if not rows or "NHWA_MALE" not in rows[0]:
        raise SystemExit(f"{code}: unexpected Census layout")
    acc = collections.defaultdict(lambda: collections.Counter())
    for r in rows:
        if r["YEAR"] != YEAR or r["AGEGRP"] not in AGES:
            continue
        a = acc[norm(r["CTYNAME"])]
        a["name"] = 0
        a["vap20"] += int(r["TOT_POP"])
        for g, cols in GROUPS.items():
            a[g] += sum(int(r[c]) for c in cols)
    out = {}
    names = {norm(r["CTYNAME"]): r["CTYNAME"] for r in rows}
    for key, a in acc.items():
        tot = a["vap20"]
        if not tot:
            continue
        out[key] = {"name": names[key], "pop_20plus": tot,
                    **{g: a[g] for g in GROUPS},
                    **{g + "_pct": round(100 * a[g] / tot, 2) for g in GROUPS}}
    return out


def main():
    want = [a.upper() for a in sys.argv[1:] if not a.startswith("-")] or sorted(FIPS)
    if os.path.exists(OUT) and "--refresh" not in sys.argv:
        print("cached; --refresh to re-pull", file=sys.stderr)
        return 0
    states = {}
    for code in want:
        states[code] = one_state(code)
        print(f"  {code}: {len(states[code])} counties", file=sys.stderr)
    json.dump({"source": URL, "vintage": "Census Vintage 2024 county estimates, 7/1/2024",
               "universe": "age 20 and over (AGEGRP 5-18); ages 18-19 excluded",
               "fetched": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
               "states": states}, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"banked race for {len(states)} states, "
          f"{sum(len(v) for v in states.values())} counties")
    return 0


if __name__ == "__main__":
    sys.exit(main())
