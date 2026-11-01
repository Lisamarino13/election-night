#!/usr/bin/env python3
"""Out-of-sample backtest -> data/backtest.json

The model's output is worthless without a measured error.  So run the exact
same machinery on the LAST midterm, where the answer is known, posing the
identical forward problem:

    2026 run:  2024 county margins + 2026 early vote  -> predict 2026
    backtest:  2020 county margins + 2022 early vote  -> predict 2022

2020 margins are all the model would have had in 2022, so nothing here is fit
to the answer.  The spread of the errors is the only honest range this model
can put on a 2026 number.

A second row runs 2024 margins against 2022, which is NOT a forecast test --
it uses the future to predict the past -- but it isolates whether the error
comes from the MECHANISM (county weighting, skew, banked share) or from the
BASELINE being out of date.  If the 2024-margin row is accurate and the
2020-margin row is not, the mechanism is fine and the baseline year is the
problem, which is exactly the question the reversion knob exists to answer.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
SKEW = -22.84  # NC within-county midterm mean, measured

# certified 2022 two-party results, top of the ticket
ACTUAL = {
    "TX": ("Governor  Abbott/O'Rourke", 4435558, 3553656),
    "NC": ("US Senate Budd/Beasley",    1905786, 1784049),
    "FL": ("Governor  DeSantis/Crist",  4614210, 3106313),
    "IA": ("Governor  Reynolds/DeJear",  709198,  482950),
}


def load(n):
    p = os.path.join(DATA, n)
    return json.load(open(p)) if os.path.exists(p) else None


def margin(r, d):
    return 100.0 * (r - d) / (r + d) if (r + d) else None


def main():
    ss = load("share-shift.json")["states"]
    series = load("county-series.json")["states"]
    base24 = load("county-2024.json")["states"]
    eavs = load("eavs.json")
    eavs = eavs.get("states") or eavs

    out, errs = {}, {"2020": [], "2024": []}
    for code, (lbl, R, D) in ACTUAL.items():
        if code not in ss:
            continue
        rows = ss[code]["county_rows"]
        act = margin(R, D)
        cty24 = base24[code]["counties"]
        by_name = {v["name"]: v for v in cty24.values()}
        m20 = {}
        for fips, c in (series.get(code, {}).get("2020", {}).get("counties", {})).items():
            mm = margin(c["R"], c["D"])
            if mm is not None:
                m20[c["name"]] = mm

        ed = (eavs.get(code) or {}).get("2022", {}).get("election_day")
        ev = sum(r["ev_2022"] for r in rows)
        if not ed:
            continue
        s = ev / (ev + ed)

        rec = {"race": lbl, "actual": round(act, 2), "ev_2022": ev,
               "eday_2022": ed, "banked_share": round(100 * s, 1), "runs": {}}
        for tag, getm in (("2020", lambda r: m20.get(r["county"])),
                          ("2024", lambda r: r["margin_2024"])):
            use = [r for r in rows if getm(r) is not None]
            if len(use) < 10:
                continue
            e = sum(r["ev_2022"] for r in use)
            bm = sum(r["ev_2022"] * getm(r) for r in use) / e
            rem = [(r, max((by_name.get(r["county"]) or {"R": 0, "D": 0})["R"]
                           + (by_name.get(r["county"]) or {"R": 0, "D": 0})["D"]
                           - r["ev_2022"], 0)) for r in use]
            rt = sum(x for _, x in rem)
            if not rt:
                continue
            em = sum(getm(r) * x for r, x in rem) / rt
            mev = bm + (1 - s) * SKEW
            med = em - s * SKEW
            pred = s * mev + (1 - s) * med
            rec["runs"][tag] = {"counties": len(use), "banked_mix": round(bm, 2),
                                "eday_mix": round(em, 2), "predicted": round(pred, 2),
                                "error": round(pred - act, 2)}
            errs[tag].append(pred - act)
        out[code] = rec

    summ = {}
    for tag, e in errs.items():
        if not e:
            continue
        n = len(e); mean = sum(e) / n
        var = sum((x - mean) ** 2 for x in e) / (n - 1) if n > 1 else 0
        mae = sum(abs(x) for x in e) / n
        summ[tag] = {"n": n, "mean_error": round(mean, 2), "mae": round(mae, 2),
                     "sd": round(var ** 0.5, 2),
                     "min": round(min(e), 2), "max": round(max(e), 2)}

    json.dump({"method": __doc__.strip(), "skew": SKEW,
               "states": out, "summary": summ},
              open(os.path.join(DATA, "backtest.json"), "w"), indent=1, sort_keys=True)

    print("BACKTEST on 2022, four states.  Margins R-positive.\n")
    print(f"{'st':3}{'race':28}{'bank%':>7}{'actual':>8}"
          f"{'pred(2020)':>12}{'err':>7}{'pred(2024)':>12}{'err':>7}")
    print("-" * 84)
    for code, r in out.items():
        a = r["runs"].get("2020", {}); b = r["runs"].get("2024", {})
        print(f"{code:3}{r['race']:28}{r['banked_share']:>6.1f}%{r['actual']:>+8.2f}"
              f"{a.get('predicted',0):>+12.2f}{a.get('error',0):>+7.2f}"
              f"{b.get('predicted',0):>+12.2f}{b.get('error',0):>+7.2f}")
    print()
    for tag in ("2020", "2024"):
        if tag not in summ:
            continue
        s_ = summ[tag]
        kind = "TRUE out-of-sample" if tag == "2020" else "mechanism only (uses the future)"
        print(f"  {tag} margins -- {kind}")
        print(f"    n={s_['n']}  mean error {s_['mean_error']:+.2f}  MAE {s_['mae']:.2f}"
              f"  sd {s_['sd']:.2f}  range {s_['min']:+.2f} to {s_['max']:+.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
