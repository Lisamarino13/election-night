#!/usr/bin/env python3
"""Projection framework: how far behind is each party on banked ballots, and
what does the other side need on election day to close it.

Three layers, kept separate so each can be checked on its own:

 1. MECHANICAL.  Join 2026 early ballots by county to that county's 2024
    result.  Weight each county's 2024 margin by the ballots it has actually
    banked.  This asks one question only: "if every county votes the way it
    voted in 2024, which way do the ballots already in the box lean?"  The
    answer differs from the 2024 statewide margin purely because the counties
    are banking at different rates -- that difference is the MIX EFFECT, and
    it is measured, not assumed.

 2. WITHIN-COUNTY EV SKEW.  Layer 1 understates the Democratic lean of the
    early pool, because inside a single county early voters are more
    Democratic than election-day voters.  North Carolina 2024 is the one place
    we can measure this: its precinct file splits the mode.  Measured there at
    11.78 pts (president) and 5.59 pts (governor).  Applied as a named knob,
    offset against the election-day pool so the state total is unchanged.

 3. BREAK-EVEN.  Given the banked share of the final vote (a band, from the
    turnout model -- early vote alone cannot say whether more people are
    voting or the same people are voting earlier), what margin does each side
    need on the remaining election-day vote to reach a tie.

Margins are R-positive throughout: +5 means R ahead by 5 points.
Nothing here is a forecast.  Layer 3 is arithmetic on a stated assumption.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")

# Measured from data/replay-NC-2024.json (NC precinct file, mode-split).
# EV+mail margin minus election-day margin, R-positive, so negative = EV more D.
EV_SKEW_MEASURED = {"president": -11.78, "governor": -5.59}
DEFAULT_SKEW = EV_SKEW_MEASURED["governor"]  # 2026 is a midterm: no president on it

BIG = 15  # "big counties" cut, by 2024 turnout

# Baseline reversion.  A single year's county margins are a bad prior: 2024
# carries the Hispanic swing toward Trump, so a 2024-only baseline treats the
# peak of a one-cycle move as those counties' resting state.  K reverts that
# fraction of each county's own 2020->2024 swing:
#     margin = m24 - K * (m24 - m20)
# K=0 is pure 2024, K=1 is pure 2020, K>1 lets a county carry PAST 2020 --
# which is the case for a county whose 2026 early vote is first-time voters
# rather than the 2024 electorate returning.
#
# 2016 is deliberately NOT an option: that archive is missing 23,028 R and
# 27,242 D votes in North Carolina alone, about 1% of the state.  2020
# reproduces NC to 2 votes and Texas exactly, so the series stops at 2020.
DEFAULT_K = 0.0

# A single statewide K applies the same reversion to Collin (2020->2024 swing
# +7.0) as to Maverick (+28.1), which is not the claim anyone is making.  The
# claim is about the Hispanic counties specifically, so K can be set separately
# for counties at or above HISP_CUT percent Hispanic (age 20+, Census).  That
# needs data/county-race.json; without it the group K is ignored.
HISP_CUT = 40.0


def load(name):
    p = os.path.join(DATA, name)
    return json.load(open(p)) if os.path.exists(p) else None


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


def ev_total(rec):
    """Ballots banked for one county, across whichever streams the state names."""
    if not isinstance(rec, dict):
        return None
    if isinstance(rec.get("total"), (int, float)):
        return int(rec["total"])
    tot = 0
    seen = False
    for k in ("early_in_person", "in_person", "mail_returned", "returned", "by_mail"):
        v = rec.get(k)
        if isinstance(v, dict) and isinstance(v.get("total"), (int, float)):
            tot += int(v["total"]); seen = True
        elif isinstance(v, (int, float)):
            tot += int(v); seen = True
        if k == "mail_returned" and isinstance(rec.get("returned"), dict):
            break  # returned is the same stream under a second name
    return tot if seen else None


def margin(r, d):
    return 100.0 * (r - d) / (r + d) if (r + d) else None


def model_state(code, base, ev, band, skew, k=0.0, series=None,
                k_hisp=None, race=None):
    cty = base["counties"]
    # per-county 2020 two-party margin, joined on FIPS
    hisp = {}
    if race and k_hisp is not None:
        hisp = {key: v.get("hispanic_pct") for key, v in race.get(code, {}).items()}
    m20 = {}
    if series:
        for fips, c in (series.get(code, {}).get("2020", {}).get("counties", {})).items():
            mm = margin(c["R"], c["D"])
            if mm is not None:
                m20[fips.zfill(5)] = mm
    rows, miss = [], []
    for name, rec in ev.items():
        n = norm(name)
        if n in ("NA", "", "TOTAL", "STATEWIDE"):
            continue
        b = cty.get(n)
        t = ev_total(rec)
        if b is None:
            if t:
                miss.append(name)
            continue
        if t is None:
            continue
        # two-party base: the margin is a two-party figure, so it must be
        # weighted by two-party votes, not by a total that carries third party
        tp = b["R"] + b["D"]
        m24 = margin(b["R"], b["D"])
        prev = m20.get(b["fips"].zfill(5))
        swing = (m24 - prev) if (prev is not None and m24 is not None) else None
        rows.append({"county": b["name"], "ev_2026": t, "votes_2024": b["total"],
                     "twoparty_2024": tp, "R24": b["R"], "D24": b["D"],
                     "margin_2024": m24, "margin_2020": prev,
                     "swing_20_24": swing,
                     # the baseline the model actually runs on
                     "hispanic_pct": hisp.get(n),
                     "margin_base": (m24 - (k_hisp if (k_hisp is not None
                                            and (hisp.get(n) or 0) >= HISP_CUT) else k) * swing)
                                    if swing is not None else m24,
                     "pace": (t / b["total"]) if b["total"] else None})
    rows = [r for r in rows if r["margin_base"] is not None and r["pace"] is not None]
    if len(rows) < 10:
        return None

    joined_ev = sum(r["ev_2026"] for r in rows)
    state_m24 = margin(base["R"], base["D"])
    # the statewide margin IMPLIED by the chosen baseline (= certified 2024 at k=0)
    tp_all = sum(r["twoparty_2024"] for r in rows)
    state_base = sum(r["margin_base"] * r["twoparty_2024"] for r in rows) / tp_all
    # how much of the baseline is the 2020->2024 swing, weighted by banked ballots
    sw = [r for r in rows if r["swing_20_24"] is not None]
    ev_swing = (sum(r["swing_20_24"] * r["ev_2026"] for r in sw)
                / sum(r["ev_2026"] for r in sw)) if sw else None

    # --- layer 1: mix effect -------------------------------------------------
    banked = sum(r["ev_2026"] * r["margin_base"] for r in rows) / joined_ev
    remaining = [(r, max(r["twoparty_2024"] - r["ev_2026"], 0)) for r in rows]
    rem_tot = sum(x for _, x in remaining)
    rem_m = (sum(r["margin_base"] * x for r, x in remaining) / rem_tot) if rem_tot else None

    # --- layer 2: within-county EV skew -------------------------------------
    # 2024-equivalent share, used only to offset the skew so the state is whole
    s24 = joined_ev / sum(r["twoparty_2024"] for r in rows)
    banked_adj = banked + skew
    rem_adj = (rem_m - skew * s24 / (1 - s24)) if (rem_m is not None and s24 < 1) else None

    # --- layer 3: break-even -------------------------------------------------
    be = {}
    for tag, turnout in (("high_turnout", band.get("high")), ("low_turnout", band.get("low"))):
        if not turnout:
            continue
        s = min(joined_ev / turnout, 0.999)
        be[tag] = {
            "turnout": turnout, "banked_share": round(100 * s, 1),
            # R-positive election-day margin needed for a statewide tie
            "ed_margin_R_needs": round(-s * banked_adj / (1 - s), 2),
        }

    rows.sort(key=lambda r: -r["votes_2024"])
    big, small = rows[:BIG], rows[BIG:]

    def cut(sub):
        if not sub:
            return None
        e = sum(r["ev_2026"] for r in sub); v = sum(r["votes_2024"] for r in sub)
        R = sum(r["R24"] for r in sub); D = sum(r["D24"] for r in sub)
        s2 = [r for r in sub if r["swing_20_24"] is not None]
        return {"counties": len(sub), "ev_2026": e, "votes_2024": v,
                "pace": round(e / v, 4) if v else None,
                "margin_2024": round(margin(R, D), 2),
                "swing_20_24": (round(sum(r["swing_20_24"] * r["twoparty_2024"] for r in s2)
                                      / sum(r["twoparty_2024"] for r in s2), 2) if s2 else None),
                "share_of_state_ev": round(100 * e / joined_ev, 1)}

    return {
        "counties_joined": len(rows), "counties_unmatched": sorted(miss),
        "ev_joined": joined_ev, "turnout_2024_joined": sum(r["votes_2024"] for r in rows),
        "twoparty_2024_joined": sum(r["twoparty_2024"] for r in rows),
        "margin_2024_statewide": round(state_m24, 2),
        "reversion_k": k,
        "margin_baseline_statewide": round(state_base, 2),
        "swing_20_24_ev_weighted": round(ev_swing, 2) if ev_swing is not None else None,
        "counties_with_2020": len(sw),
        "banked_at_2024_behavior": round(banked, 2),
        "mix_effect": round(banked - state_m24, 2),
        "remaining_at_2024_behavior": round(rem_m, 2) if rem_m is not None else None,
        "ev_skew_applied": skew,
        "banked_margin": round(banked_adj, 2),
        "remaining_margin": round(rem_adj, 2) if rem_adj is not None else None,
        "break_even": be,
        "cut_big": cut(big), "cut_small": cut(small),
        "counties": rows,
    }


def main():
    skew, k, k_hisp = DEFAULT_SKEW, DEFAULT_K, None
    for a in sys.argv[1:]:
        if a.startswith("--skew="):
            skew = float(a.split("=", 1)[1])
        elif a.startswith("--revert="):
            k = float(a.split("=", 1)[1])
        elif a.startswith("--revert-hispanic="):
            k_hisp = float(a.split("=", 1)[1])
    base = load("county-2024.json")
    proj = load("projection.json")
    series = (load("county-series.json") or {}).get("states")
    race = (load("county-race.json") or {}).get("states")
    if not base:
        raise SystemExit("run collectors/county_baseline.py first")
    out = {}
    for code, b in sorted(base["states"].items()):
        ev = load(f"early-{code}.json")
        if not ev or not isinstance(ev.get("counties"), dict) or not ev["counties"]:
            continue
        band = ((proj or {}).get("states", {}).get(code, {}) or {}).get("projected", {}) or {}
        m = model_state(code, b, ev["counties"], band, skew, k, series, k_hisp, race)
        if m:
            m["as_of"] = ev.get("as_of")
            out[code] = m
    json.dump({"basis": __doc__.strip().splitlines()[0],
               "ev_skew_measured": EV_SKEW_MEASURED, "ev_skew_applied": skew,
               "reversion_k": k, "reversion_k_hispanic": k_hisp,
               "hispanic_cut_pct": HISP_CUT,
               "baseline": ("2024 county margins" if k == 0 else
                            f"2024 margins with {k:g} of each county's 2020->2024 swing reverted"),
               "margin_convention": "R-positive: +5 = Republican ahead by 5 points",
               "states": out},
              open(os.path.join(DATA, "model.json"), "w"), indent=1, sort_keys=True)

    hdr = ("st   cty    EV 2026 pace  bank% |    2024    mix  banked remain |"
           "  R needs   R GAP")
    print(hdr); print("-" * len(hdr))
    for code, m in out.items():
        be = m["break_even"].get("low_turnout") or next(iter(m["break_even"].values()), {})
        need, rem, bs = be.get("ed_margin_R_needs"), m["remaining_margin"], be.get("banked_share")
        gap = (need - rem) if (need is not None and rem is not None) else None
        fmt = lambda v, w: (("%+*.2f" % (w, v)) if v is not None else "-".rjust(w))
        print("%-3s %4d %10s %5.2f %6s | %7s %6s %7s %7s | %8s %7s" % (
            code, m["counties_joined"], format(m["ev_joined"], ","),
            m["ev_joined"] / m["turnout_2024_joined"],
            ("%.1f%%" % bs) if bs else "-",
            fmt(m["margin_2024_statewide"], 7), fmt(m["mix_effect"], 6),
            fmt(m["banked_margin"], 7), fmt(rem, 7), fmt(need, 8), fmt(gap, 7)))
    nm = "president" if skew == EV_SKEW_MEASURED["president"] else "governor"
    print("\nbaseline: k=%g (%s)" % (k, "pure 2024" if k == 0 else
          ("pure 2020" if k == 1 else "%g%% of the 2020->2024 swing reverted" % (100 * k))))
    print("\nEV skew applied: %+.2f pts (NC-measured 2024 %s).  Margins R-positive." % (skew, nm))
    print("mix     = banked ballots vs the 2024 statewide electorate, from county pace alone (measured)")
    print("banked  = mix plus the within-county early-vote skew")
    print("remain  = what the un-banked vote gives R if every county repeats 2024")
    print("R needs = election-day margin R needs for a statewide TIE, at the low-turnout band")
    print("R GAP   = how much R must BEAT their own 2024 county behavior on election day to tie")
    return 0


if __name__ == "__main__":
    sys.exit(main())
