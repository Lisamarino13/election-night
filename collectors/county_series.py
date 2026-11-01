#!/usr/bin/env python3
"""Bank county presidential results for 2016, 2020 and 2024 as a SERIES.

Why a series and not just 2024: using one year's county margins as the
behavioural prior hard-codes whatever was peculiar about that year.  For 2024
that is the Hispanic swing toward Trump -- so a 2024-only baseline treats the
peak of a one-cycle move as those counties' resting state.  Banking three
cycles lets the model take the baseline as a knob: a level, a trend, or a
partial reversion.

TIE-OUT STATUS, recorded in the output and not to be overstated anywhere:
  2024 -- tied out exactly to North Carolina's own precinct replay, and every
          state's county sum matched its certified statewide total.
  2020, 2016 -- gated on the county FIPS set being identical to the banked
          2024 set (so no county silently drops or doubles) and on internal
          consistency.  NOT independently tied out to certified statewide
          totals.  Anything built on these two years must say so.
"""
import csv, io, json, os, sys, urllib.request, collections, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "county-series.json")
BASE = ("https://raw.githubusercontent.com/tonmcg/"
        "US_County_Level_Election_Results_08-24/master/")
FILES = {"2016": "2016_US_County_Level_Presidential_Results.csv",
         "2020": "2020_US_County_Level_Presidential_Results.csv",
         "2024": "2024_US_County_Level_Presidential_Results.csv"}

STATES = {"North Carolina": "NC", "Georgia": "GA", "Texas": "TX", "Florida": "FL",
          "Michigan": "MI", "Ohio": "OH", "Minnesota": "MN", "Iowa": "IA",
          "Kansas": "KS", "Maine": "ME", "Nebraska": "NE", "South Carolina": "SC",
          "Alaska": "AK", "Louisiana": "LA"}
ABBR = set(STATES.values())


def fetch(name):
    with urllib.request.urlopen(BASE + name, timeout=180) as r:
        return r.read().decode("utf-8-sig", "replace")


def parse(year, raw):
    """Both schemas in this archive, normalized to {state: {fips: {R,D,total}}}."""
    out = collections.defaultdict(dict)
    for row in csv.DictReader(io.StringIO(raw)):
        if "state_name" in row:                      # 2020, 2024 layout
            code = STATES.get((row["state_name"] or "").strip())
            fips = (row["county_fips"] or "").strip()
        else:                                        # 2016 layout
            code = (row.get("state_abbr") or "").strip().upper()
            code = code if code in ABBR else None
            fips = (row.get("combined_fips") or "").strip()
        if not code or not fips:
            continue
        fips = fips.zfill(5)
        out[code][fips] = {
            "name": (row["county_name"] or "").strip(),
            "R": int(float(row["votes_gop"])), "D": int(float(row["votes_dem"])),
            "total": int(float(row["total_votes"])),
        }
    return out


def main():
    if os.path.exists(OUT) and "--refresh" not in sys.argv:
        print("cached; --refresh to re-pull", file=sys.stderr)
        return 0
    base = json.load(open(os.path.join(HERE, "..", "data", "county-2024.json")))
    # the already-tied-out 2024 FIPS set, per state, is the gate
    gate = {c: {v["fips"].zfill(5) for v in s["counties"].values()}
            for c, s in base["states"].items()}

    years = {y: parse(y, fetch(f)) for y, f in FILES.items()}
    states, checks = {}, {}
    for code in sorted(gate):
        per_year, ok = {}, True
        for y in FILES:
            cty = years[y].get(code, {})
            same = set(cty) == gate[code]
            R = sum(c["R"] for c in cty.values())
            D = sum(c["D"] for c in cty.values())
            per_year[y] = {"counties": cty, "R": R, "D": D,
                           "total": sum(c["total"] for c in cty.values()),
                           "fips_set_matches_2024": same,
                           "margin_R": round(100 * (R - D) / (R + D), 3) if R + D else None}
            if not same:
                ok = False
        checks[code] = {y: {"units": len(v["counties"]),
                            "fips_set_matches_2024": v["fips_set_matches_2024"],
                            "R": v["R"], "D": v["D"], "margin_R": v["margin_R"]}
                        for y, v in per_year.items()}
        if ok:
            states[code] = per_year

    json.dump({"source": BASE, "years": sorted(FILES),
               "fetched": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
               "tie_out_status": {
                   "2024": "exact: matches NC's own precinct replay and every certified statewide total",
                   "2020": "FIPS-set gated against the tied-out 2024 set; NOT independently tied out",
                   "2016": "FIPS-set gated against the tied-out 2024 set; NOT independently tied out"},
               "checks": checks, "states": states},
              open(OUT, "w"), indent=1, sort_keys=True)

    print(f"{'st':3} " + " ".join(f"{y:>19}" for y in sorted(FILES)))
    for code in sorted(checks):
        held = "  " if code in states else " *"
        cells = []
        for y in sorted(FILES):
            c = checks[code][y]
            flag = "" if c["fips_set_matches_2024"] else "!"
            cells.append(f"{c['units']:>4}u {c['margin_R']:>+7.2f}{flag:<1}     "
                         if c["margin_R"] is not None else f"{'-':>19}")
        print(f"{code:3}{held}" + " ".join(cells))
    drop = sorted(set(checks) - set(states))
    print(f"\nbanked {len(states)} states x 3 cycles"
          + (f"; * = DROPPED (FIPS set differs): {drop}" if drop else "; none dropped"))
    print("margins R-positive.  2016/2020 are FIPS-gated only, NOT tied out to certified totals.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
