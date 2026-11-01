#!/usr/bin/env python3
"""Bank 2024 county-level presidential results as the per-county baseline.

Fail-closed: any state whose aggregate does not tie out to its certified
statewide total within TOL is dropped, not published.  NC is the hard check --
we hold NC's own precinct replay, so its county sum must match to the ballot.
"""
import json, csv, io, os, sys, urllib.request, collections, datetime

SRC = ("https://raw.githubusercontent.com/tonmcg/"
       "US_County_Level_Election_Results_08-24/master/"
       "2024_US_County_Level_Presidential_Results.csv")
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "county-2024.json")

STATES = {"North Carolina": "NC", "Georgia": "GA", "Texas": "TX", "Florida": "FL",
          "Michigan": "MI", "Ohio": "OH", "Minnesota": "MN", "Iowa": "IA",
          "Kansas": "KS", "Maine": "ME", "Nebraska": "NE", "South Carolina": "SC",
          "Alaska": "AK", "Louisiana": "LA"}

# Certified statewide 2024 presidential (R, D) and expected county/unit count.
# NC is from our own replay of the state's precinct file; the rest from each
# state's certified canvass.
CERT = {
    "NC": (2898423, 2715375, 100), "GA": (2663117, 2548017, 159),
    "TX": (6393597, 4835250, 254), "FL": (6110125, 4683038, 67),
    "MI": (2816636, 2736533, 83),  "OH": (3180116, 2533699, 88),
    "MN": (1519032, 1656979, 87),  "IA": (927019, 707278, 99),
    "KS": (758802, 544853, 105),   "ME": (377977, 435652, 16),
    "NE": (564816, 369995, 93),    "SC": (1483747, 1028452, 46),
    "AK": (184407, 139690, 40),    "LA": (1208505, 766870, 64),
}
TOL = 0.001  # 0.1%


def norm(name):
    """Strict county key: strip the unit suffix, then every non-alphanumeric.

    The joins on both sides MUST use this one function.  Miami-Dade vs
    MIAMI DADE, BEN HILL vs BENHILL and LA SALLE vs LASALLE each silently
    dropped a county -- and dropping Miami-Dade moved Florida 0.19 points.
    """
    n = str(name).strip().upper()
    for suf in (" COUNTY", " PARISH", " CENSUS AREA", " BOROUGH",
                " CITY AND BOROUGH", " MUNICIPALITY", " CITY"):
        if n.endswith(suf):
            n = n[: -len(suf)]
            break
    return "".join(ch for ch in n if ch.isalnum())


def main():
    refresh = "--refresh" in sys.argv
    if os.path.exists(OUT) and not refresh:
        print("cached; --refresh to re-pull", file=sys.stderr)
        return 0
    with urllib.request.urlopen(SRC, timeout=120) as r:
        raw = r.read().decode("utf-8")
    if len(raw) < 100000:
        raise SystemExit("source too small to be the county file")

    by_state = collections.defaultdict(dict)
    for row in csv.DictReader(io.StringIO(raw)):
        code = STATES.get(row["state_name"])
        if not code:
            continue
        r_ = int(float(row["votes_gop"]))
        d_ = int(float(row["votes_dem"]))
        t_ = int(float(row["total_votes"]))
        by_state[code][norm(row["county_name"])] = {
            "fips": row["county_fips"], "name": row["county_name"].strip(),
            "R": r_, "D": d_, "total": t_,
        }

    out, ties, dropped = {}, {}, {}
    for code, cty in sorted(by_state.items()):
        R = sum(c["R"] for c in cty.values())
        D = sum(c["D"] for c in cty.values())
        cr, cd, cn = CERT[code]
        dr, dd = abs(R - cr) / cr, abs(D - cd) / cd
        ok = dr <= TOL and dd <= TOL and len(cty) == cn
        rec = {"units": len(cty), "units_expected": cn, "R": R, "D": D,
               "certified_R": cr, "certified_D": cd,
               "delta_R_pct": round(100 * dr, 4), "delta_D_pct": round(100 * dd, 4),
               "exact": R == cr and D == cd, "pass": ok}
        if ok:
            out[code] = {"counties": cty, "R": R, "D": D,
                         "total": sum(c["total"] for c in cty.values())}
            ties[code] = rec
        else:
            dropped[code] = rec

    if "NC" not in out or not ties["NC"]["exact"]:
        raise SystemExit("NC did not tie out exactly to our own replay -- refusing to publish")

    json.dump({"election": "2024 General (president)", "source": SRC,
               "fetched": datetime.datetime.now(datetime.timezone.utc)
                          .isoformat(timespec="seconds"),
               "tolerance_pct": TOL * 100, "tie_out": ties, "dropped": dropped,
               "states": out},
              open(OUT, "w"), indent=1, sort_keys=True)
    print(f"banked {len(out)} states, {sum(len(v['counties']) for v in out.values())} counties"
          + (f"; DROPPED {sorted(dropped)}" if dropped else "; none dropped"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
