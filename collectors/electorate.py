#!/usr/bin/env python3
"""The racial composition of each state's ELECTORATE -> data/electorate.json

Three inputs, all measured, none modelled:

  1. CVAP by county and race (collectors/cvap.py) -- the citizen voting-age
     population. The right denominator. Adult population is the wrong one:
     in Texas only 72% of Hispanic adults are citizens against ~100% of white
     adults, so using population charges a citizenship gap to turnout.
  2. Turnout rate by race, per state, November 2024 -- KFF's tabulation of the
     Census Voting and Registration Supplement (CPS), banked at
     data/manual/kff-turnout-by-race-2024.csv.
  3. electorate share = CVAP share x turnout rate, normalised.

What this corrects: weighting counties by their race shares gives Texas a 44.6%
white electorate, which forces the white Democratic vote to an impossible 19.5%.
CVAP alone lifts it to 51.0%. CVAP x measured turnout gives 53.4%, and the white
Democratic share lands at a believable 24%.

The surprise in the Texas numbers is that its white-Black turnout gap is 0.4
points -- essentially closed -- while its white-Hispanic gap is 13.6. The room
for turnout growth is Hispanic, not Black, and that is state-specific: the
national white-Black gap is 7.7 points.
"""
import csv, io, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
KFF = os.path.join(DATA, "manual", "kff-turnout-by-race-2024.csv")
OUT = os.path.join(DATA, "electorate.json")
NAMES = {"Texas": "TX", "North Carolina": "NC", "Georgia": "GA", "Florida": "FL",
         "Michigan": "MI", "Ohio": "OH", "Minnesota": "MN", "Iowa": "IA",
         "Kansas": "KS", "Maine": "ME", "Nebraska": "NE", "South Carolina": "SC",
         "Alaska": "AK", "Louisiana": "LA", "United States": "US"}
VOT = "Percent of Voter Population that Voted by Race/Ethnicity__"
REG = "Percent of Voter Population Registered to Vote by Race/Ethnicity__"
COLS = {"white": "White", "black": "Black", "asian": "Asian", "hispanic": "Hispanic"}


def main():
    lines = open(KFF, encoding="utf-8-sig").read().splitlines()
    i = next(n for n, l in enumerate(lines) if l.startswith('"Location"'))
    rows = list(csv.DictReader(io.StringIO("\n".join(lines[i:]))))
    cvap = json.load(open(os.path.join(DATA, "cvap.json")))["states"]

    def num(r, k):
        try:
            return float(r.get(k, ""))
        except ValueError:
            return None

    out, skipped = {}, {}
    for r in rows:
        code = NAMES.get((r.get("Location") or "").strip())
        if not code or code not in cvap:
            continue
        cv = cvap[code]
        tot = sum(v.get("total", 0) for v in cv.values())
        if not tot:
            continue
        share = {g: sum(v.get(g, 0) for v in cv.values()) / tot
                 for g in ("white", "black", "asian", "hispanic")}
        share["other"] = max(1 - sum(share.values()), 0.0)
        turn = {g: num(r, VOT + c) for g, c in COLS.items()}
        turn["other"] = turn.get("asian")
        missing = [g for g, v in turn.items() if v is None]
        if missing:
            skipped[code] = missing
            continue
        votes = {g: share[g] * turn[g] for g in share}
        tv = sum(votes.values())
        elect = {g: votes[g] / tv for g in votes}
        nws = sum(share[g] for g in share if g != "white")
        nwt = sum(share[g] * turn[g] for g in share if g != "white") / nws
        out[code] = {
            "cvap_total": tot,
            "cvap_share": {g: round(v, 5) for g, v in share.items()},
            "turnout_2024": {g: round(v, 4) for g, v in turn.items()},
            "registered_2024": {g: num(r, REG + c) for g, c in COLS.items()},
            "electorate_share": {g: round(v, 5) for g, v in elect.items()},
            "turnout_overall": round(tv, 4),
            "white_nonwhite_ratio": round(turn["white"] / nwt, 3),
            "gap_white_black_pts": round(100 * (turn["white"] - turn["black"]), 1),
            "gap_white_hispanic_pts": round(100 * (turn["white"] - turn["hispanic"]), 1),
        }

    json.dump({"cvap_source": "Census CVAP special tabulation, ACS 2019-2023",
               "turnout_source": "KFF tabulation of the Census Voting and "
                                 "Registration Supplement (CPS), November 2024",
               "method": "electorate share = CVAP share x turnout rate, normalised",
               "states": out, "incomplete": skipped},
              open(OUT, "w"), indent=1, sort_keys=True)

    print(f"{'st':4}{'CVAP':>12} | {'turnout by race':^34} | "
          f"{'electorate':^16} | {'ratio':>6}{'W-B':>6}{'W-H':>6}")
    print(f"{'':4}{'':>12} | {'white':>8}{'Black':>8}{'Hisp':>9}{'Asian':>9} | "
          f"{'% white':>8}{'% Hisp':>8} | {'w:nw':>6}{'gap':>6}{'gap':>6}")
    print("-" * 96)
    for code in sorted(out):
        v = out[code]
        t, e = v["turnout_2024"], v["electorate_share"]
        print(f"{code:4}{v['cvap_total']:>12,} | {100*t['white']:>7.1f}%{100*t['black']:>7.1f}%"
              f"{100*t['hispanic']:>8.1f}%{100*t['asian']:>8.1f}% | "
              f"{100*e['white']:>7.1f}%{100*e['hispanic']:>7.1f}% | "
              f"{v['white_nonwhite_ratio']:>6.2f}{v['gap_white_black_pts']:>6.1f}"
              f"{v['gap_white_hispanic_pts']:>6.1f}")
    if skipped:
        print(f"\n  incomplete (CPS sample too small for a group): {skipped}")
    print("\n  'electorate % white' is what a model must use, NOT the population share.")
    print("  W-B / W-H are the white-Black and white-Hispanic turnout gaps in points.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
