#!/usr/bin/env python3
"""Citizen voting-age population by county and race -> data/cvap.json

The denominator that matters. Turnout and electorate composition have to be
measured against CITIZENS of voting age, not against the adult population --
the Brennan Center's racial-turnout-gap work uses CVAP for exactly this reason.

In Texas the difference is not cosmetic. Only 72% of Hispanic adults are
citizens, against ~100% of white adults, so:

    Hispanic share of ADULTS 20+   37.1%
    Hispanic share of CITIZENS     31.3%
    white share of ADULTS 20+      42.1%
    white share of CITIZENS        49.1%

Weighting counties by their votes, white share of the electorate reads 44.6%
on adult population and 51.0% on CVAP. Using population as the denominator
charges 7 points of a citizenship gap to a turnout gap.

Source: Census CVAP Special Tabulation from the ACS 5-year file, the
redistricting data office's published county table. Race lines under
"Not Hispanic or Latino" are non-Hispanic single-race; "Hispanic or Latino"
is its own line, so the groups do not double count.
"""
import csv, io, json, os, sys, urllib.request, zipfile, collections

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "cvap.json")
URL = ("https://www2.census.gov/programs-surveys/decennial/rdo/datasets/"
       "2023/2023-cvap/CVAP_2019-2023_ACS_csv_files.zip")
STATES = {"Texas": "TX", "North Carolina": "NC", "Georgia": "GA", "Florida": "FL",
          "Michigan": "MI", "Ohio": "OH", "Minnesota": "MN", "Iowa": "IA",
          "Kansas": "KS", "Maine": "ME", "Nebraska": "NE", "South Carolina": "SC",
          "Alaska": "AK", "Louisiana": "LA"}
# Every race line the file publishes. "Not Hispanic or Latino" is deliberately
# NOT mapped: it is a SUBTOTAL of the single-race lines, so including it as a group
# double counts. The single-race lines plus Hispanic cover 97.98% of Texas CVAP;
# the remaining 2.02% is the four multiracial combinations, carried separately.
LINES = {"Total": "total", "White Alone": "white",
         "Black or African American Alone": "black", "Asian Alone": "asian",
         "American Indian or Alaska Native Alone": "native",
         "Native Hawaiian or Other Pacific Islander Alone": "nhpi",
         "Hispanic or Latino": "hispanic",
         "American Indian or Alaska Native and White": "mr_aian_white",
         "Asian and White": "mr_asian_white",
         "Black or African American and White": "mr_black_white",
         "American Indian or Alaska Native and Black or African American": "mr_aian_black",
         "Remainder of Two or More Race Responses": "mr_other"}
# AAPI is Asian Alone plus Native Hawaiian / Pacific Islander Alone, the standard
# combination; the file does not publish it as its own line.
DERIVED = {"aapi": ("asian", "nhpi"),
           "multiracial": ("mr_aian_white", "mr_asian_white", "mr_black_white",
                           "mr_aian_black", "mr_other")}


def norm(name):
    n = name.strip().upper()
    for suf in (" COUNTY", " PARISH", " CENSUS AREA", " BOROUGH",
                " CITY AND BOROUGH", " MUNICIPALITY", " CITY"):
        if n.endswith(suf):
            n = n[: -len(suf)]
            break
    return "".join(c for c in n if c.isalnum())


def main():
    if os.path.exists(OUT) and "--refresh" not in sys.argv:
        print("cached; --refresh to re-pull", file=sys.stderr)
        return 0
    cache = "/tmp/cvap/cvap.zip"
    if os.path.exists(cache) and os.path.getsize(cache) > 10_000_000:
        blob = open(cache, "rb").read()
    else:
        with urllib.request.urlopen(URL, timeout=600) as r:
            blob = r.read()
    z = zipfile.ZipFile(io.BytesIO(blob))
    name = next(n for n in z.namelist() if n.endswith("County.csv"))
    text = z.read(name).decode("latin-1")

    out = collections.defaultdict(dict)
    for r in csv.DictReader(io.StringIO(text)):
        geo = r["geoname"]
        if ", " not in geo:
            continue
        cty, _, st = geo.rpartition(", ")
        code = STATES.get(st)
        field = LINES.get(r["lntitle"])
        if not (code and field):
            continue
        try:
            v = int(r["cvap_est"])
        except ValueError:
            continue
        rec = out[code].setdefault(norm(cty),
                                   {"name": cty.replace(" County", "")})
        rec[field] = v

    groups = [v for v in LINES.values() if v != "total"]
    for code, cties in out.items():
        for rec in cties.values():
            for name, parts in DERIVED.items():
                rec[name] = sum(rec.get(p, 0) for p in parts)
            t = rec.get("total") or 0
            for g in groups + list(DERIVED):
                rec[g + "_pct"] = round(100 * rec.get(g, 0) / t, 2) if t else None

    json.dump({"source": URL,
               "universe": "citizen voting-age population (18+), ACS 2019-2023 5-year",
               "why": "turnout and electorate composition need citizens as the "
                      "denominator, not adult population",
               "states": out}, open(OUT, "w"), indent=1, sort_keys=True)

    print(f"{'st':4}{'cty':>5}{'CVAP':>13}{'white':>8}{'Black':>8}{'Hisp':>8}"
          f"{'AAPI':>8}{'AIAN':>8}{'multi':>8}")
    print("-" * 74)
    for code in sorted(out):
        c = out[code]
        t = sum(v.get("total", 0) for v in c.values())
        f = lambda g: 100 * sum(v.get(g, 0) for v in c.values()) / t if t else 0
        print(f"{code:4}{len(c):>5}{t:>13,}{f('white'):>7.1f}%{f('black'):>7.1f}%"
              f"{f('hispanic'):>7.1f}%{f('aapi'):>7.1f}%{f('native'):>7.1f}%"
              f"{f('multiracial'):>7.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
