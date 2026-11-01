#!/usr/bin/env python3
"""Texas two-tier model -> data/tx-twotier.json

Tier 1 is PACE, at county level: what each county has banked in 2026 against
what it banked in 2022.  Both windows are 34 days, so this is the one
apples-to-apples pace measure -- dividing by 2024 TOTAL votes instead measures
presidential drop-off as much as enthusiasm, and on that denominator Texas reads
backwards (Travis looks hot because its presidential drop-off is low).

Tier 2 is the OVERLAY: each county's adult population and its racial make-up.
Weighting county race shares by the ballots each county has actually banked
gives the estimated racial composition of the ballots in the box, and the same
weighting on the residual gives the composition of what is left for election day.

What the two tiers say separately, and why pooling them misleads:
  PACE tracks county SIZE.  Every metro band sits at 1.41-1.44 and every
  small-county band at 1.28-1.32, with race barely moving pace inside a size band.
  THE 2024 SWING tracks RACE.  Inside every size band the Hispanic-majority
  cell swung hardest (+11.6 / +17.9 / +9.9 against +3.2 to +6.4 elsewhere).
So a one-dimensional cut by race alone blends Collin and Denton (big suburban,
R+12) with Parker and Wise (small rural, R+67) and reports their average.

CAVEAT that travels with every racial number here: the mix is ADULT POPULATION
from the Census, so it describes the places the ballots came from, not the
voters.  Turnout differs by race inside a county.  The 2022->2026 SHIFT is the
defensible figure; the levels are not.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
STATE = "TX"
SIZE = [("metro 250k+", 250000, 10**9), ("mid 50-250k", 50000, 250000),
        ("small <50k", 0, 50000)]
HISP = [("Hispanic 50%+", 50, 101), ("Hispanic 25-50%", 25, 50), ("Hispanic <25%", 0, 25)]
BLACK = [("Black 20%+", 20, 101), ("Black 10-20%", 10, 20), ("Black <10%", 0, 10)]


def load(n):
    p = os.path.join(DATA, n)
    return json.load(open(p)) if os.path.exists(p) else None


def norm(name):
    n = str(name).strip().upper()
    for suf in (" COUNTY", " PARISH"):
        if n.endswith(suf):
            n = n[: -len(suf)]
            break
    return "".join(c for c in n if c.isalnum())


def main():
    model = load("model.json")["states"][STATE]
    race = load("county-race.json")["states"][STATE]
    hist = load("ev-history-TX.json")["years"]
    cur = load("early-TX.json")
    band = load("projection.json")["states"][STATE]["projected"]
    skew = load("nc-mode-series.json")

    ev22 = {norm(k): v.get("total") for k, v in hist["2022"]["counties"].items()}
    ev26 = {norm(k): v.get("total") for k, v in cur["counties"].items()}

    rows, dropped = [], []
    for r in model["counties"]:
        k = norm(r["county"])
        rr, a, b = race.get(k), ev22.get(k), ev26.get(k)
        if not (rr and a and b and r["swing_20_24"] is not None):
            dropped.append(r["county"]); continue
        rows.append({"county": r["county"], "key": k,
                     "ev_2022": a, "ev_2026": b, "pace": round(b / a, 4),
                     "votes_2024": r["votes_2024"], "twoparty_2024": r["twoparty_2024"],
                     "margin_2020": round(r["margin_2020"], 2),
                     "margin_2024": round(r["margin_2024"], 2),
                     "swing_20_24": round(r["swing_20_24"], 2),
                     "pop_20plus": rr["pop_20plus"],
                     "white": rr["white_pct"], "black": rr["black_pct"],
                     "hispanic": rr["hispanic_pct"]})

    GR = ("white", "black", "hispanic")

    def mix(weight):
        tot = sum(weight(r) for r in rows)
        if not tot:
            return None, 0
        return {g: round(sum(weight(r) * r[g] for r in rows) / tot, 3) for g in GR}, tot

    tp24 = sum(r["twoparty_2024"] for r in rows)
    v24 = sum(r["votes_2024"] for r in rows)
    comp = {"adult_population": mix(lambda r: r["pop_20plus"])[0],
            "votes_2024": mix(lambda r: r["twoparty_2024"])[0]}
    comp["banked_2022"], t22 = mix(lambda r: r["ev_2022"])
    comp["banked_2026"], t26 = mix(lambda r: r["ev_2026"])
    comp["shift_2022_2026"] = {g: round(comp["banked_2026"][g] - comp["banked_2022"][g], 3)
                               for g in GR}
    comp["election_day"] = {}
    for tag in ("low", "high"):
        T = band.get(tag)
        if not T:
            continue
        sc = T / v24
        m, tot = mix(lambda r: max(r["twoparty_2024"] * sc - r["ev_2026"], 0))
        comp["election_day"][tag] = {"turnout": T, "ballots_left": round(tot),
                                     "mix": m,
                                     "vs_banked": {g: round(m[g] - comp["banked_2026"][g], 3)
                                                   for g in GR}}

    def cell(sub):
        if not sub:
            return None
        tp = sum(r["twoparty_2024"] for r in sub)
        e26 = sum(r["ev_2026"] for r in sub); e22 = sum(r["ev_2022"] for r in sub)
        w = lambda f: sum(r[f] * r["twoparty_2024"] for r in sub) / tp
        return {"counties": len(sub), "ev_2026": e26, "ev_2022": e22,
                "pace": round(e26 / e22, 4),
                "margin_2020": round(w("margin_2020"), 2),
                "margin_2024": round(w("margin_2024"), 2),
                "swing": round(w("margin_2024") - w("margin_2020"), 2),
                "share_2026": round(100 * e26 / t26, 3),
                "share_2022": round(100 * e22 / t22, 3),
                "share_change": round(100 * e26 / t26 - 100 * e22 / t22, 3),
                "pop_20plus": sum(r["pop_20plus"] for r in sub),
                **{g: round(sum(r[g] * r["pop_20plus"] for r in sub)
                            / sum(r["pop_20plus"] for r in sub), 2) for g in GR}}

    grid = []
    for sl, slo, shi in SIZE:
        for hl, hlo, hhi in HISP:
            c = cell([r for r in rows if slo <= r["votes_2024"] < shi
                      and hlo <= r["hispanic"] < hhi])
            if c:
                grid.append({"size": sl, "race": hl, **c})
    grid_black = []
    for sl, slo, shi in SIZE:
        for bl, blo, bhi in BLACK:
            c = cell([r for r in rows if slo <= r["votes_2024"] < shi
                      and blo <= r["black"] < bhi])
            if c:
                grid_black.append({"size": sl, "race": bl, **c})

    out = {"state": STATE, "as_of": cur.get("as_of"),
           "method": __doc__.strip(),
           "turnout_band": band,
           "counties_joined": len(rows), "counties_dropped": dropped,
           "ev_2022_total": t22, "ev_2026_total": t26,
           "statewide": {"margin_2020": model.get("margin_baseline_statewide"),
                         "margin_2024": model["margin_2024_statewide"],
                         "swing_ev_weighted": model["swing_20_24_ev_weighted"],
                         "pace": round(t26 / t22, 4)},
           "ev_skew_measured_NC": (skew or {}).get("years"),
           "ev_skew_midterm_range": (skew or {}).get("midterm_range"),
           "ev_skew_midterm_mean": (skew or {}).get("midterm_mean"),
           "composition": comp,
           "grid_hispanic": grid, "grid_black": grid_black,
           "by_size": [{"size": s, **cell([r for r in rows
                        if lo <= r["votes_2024"] < hi])} for s, lo, hi in SIZE],
           "by_hispanic": [{"race": l, **cell([r for r in rows if lo <= r["hispanic"] < hi])}
                           for l, lo, hi in HISP],
           "by_black": [{"race": l, **cell([r for r in rows if lo <= r["black"] < hi])}
                        for l, lo, hi in BLACK],
           "counties": rows}
    json.dump(out, open(os.path.join(DATA, "tx-twotier.json"), "w"), indent=1, sort_keys=True)

    print(f"TX two-tier: {len(rows)} counties joined"
          + (f", dropped {dropped}" if dropped else ", none dropped"))
    print(f"  statewide pace {t26/t22:.3f}  ({t22:,} -> {t26:,})")
    print(f"\n  {'banked pool mix':26} " + " ".join(f"{g:>9}" for g in GR))
    for lbl, key in (("2022 banked", "banked_2022"), ("2026 banked", "banked_2026"),
                     ("shift", "shift_2022_2026")):
        print(f"  {lbl:26} " + " ".join(f"{comp[key][g]:>+8.2f} " for g in GR))
    return 0


if __name__ == "__main__":
    sys.exit(main())
