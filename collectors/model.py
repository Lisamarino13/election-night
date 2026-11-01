#!/usr/bin/env python3
"""Projection framework: how far behind is each side on the ballots already in
the box, and what does the other side need on election day to close it.

Margins are R-positive throughout: +5 means Republicans ahead by 5 points.
Nothing here is a forecast.  Every layer is arithmetic on a stated input.

LAYER 1 -- MIX, measured.  Join 2026 early ballots by county to that county's
own prior result and weight each county's margin by the ballots it has banked.
One question: if every county votes the way it did before, which way do the
ballots already counted lean?  The difference from the statewide margin is the
MIX EFFECT, and it comes from county pace alone.

LAYER 2 -- WITHIN-COUNTY EARLY-VOTE SKEW, a named knob.  Inside a single county
early voters are more Democratic than election-day voters.  North Carolina is
the only state we track whose precinct file splits the mode, so it is the only
place this is measured -- see collectors/nc_mode_series.py.  Two corrections
the first cut of this model got wrong:

  * The headline skew (early margin minus election-day margin statewide)
    INCLUDES a county-mix component of 1.5 to 6.2 points, which layer 1 already
    counts.  Stacking them double-counts.  The transportable figure is the
    WITHIN-county skew, averaged over counties: -19.6 in 2018 and -26.0 in
    2022, against -29.4 to -31.7 in COVID-era 2020.
  * The skew is the gap BETWEEN the two pools, so only (1-s) of it belongs on
    the early pool and -s on the election-day pool:
        m_early = m_mix + (1 - s) * skew
        m_eday  = m_mix - s * skew
    which holds s*m_early + (1-s)*m_eday equal to the baseline, as it must.

A consequence worth knowing: the GAP in layer 3 is algebraically INDEPENDENT of
the skew -- it cancels.  The skew changes how far down a side is right now; it
does not change the swing needed to tie.

LAYER 3 -- BANKED SHARE AND BREAK-EVEN.  The banked share is not guessed from
early-vote share.  Election-day ballots turn out to be close to mode-independent:
Texas counted 2.32M of them in 2018, 1.71M in 2020, 2.59M in 2022 and 2.33M in
2024 while its early vote swung between 5.5M and 9.6M.  So the band comes from
each state's own EAVS election-day counts in the last two midterms, and total
turnout is capped at that state's 2024 turnout -- a midterm does not outpoll a
presidential year, which the uncapped early-share method was happy to assume.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")

# within-county skew, NC-measured (collectors/nc_mode_series.py).
# 2020 is excluded: COVID mode-sorting, and not a midterm.
SKEW_WITHIN = {"2018": -19.64, "2022": -26.05, "2020_covid": -30.45}
DEFAULT_SKEW = round(sum(v for k, v in SKEW_WITHIN.items() if k != "2020_covid") / 2, 2)

# Baseline reversion.  A single year's county margins are a bad prior: 2024
# carries the Hispanic swing toward Trump, so a 2024-only baseline treats the
# peak of a one-cycle move as those counties' resting state.  K reverts that
# fraction of each county's own 2020->2024 swing.  K=0 pure 2024, K=1 pure 2020,
# K>1 carries past 2020.  2016 is not an option: that archive is missing ~1% of
# North Carolina's vote.
DEFAULT_K = 0.0
# A statewide K would revert Collin (swing +7.0) as hard as Maverick (+28.1).
# The claim is about the Hispanic counties, so K can be set for them alone.
HISP_CUT = 40.0

BIG = 15
MIDTERMS = ("2018", "2022")


def load(name):
    p = os.path.join(DATA, name)
    return json.load(open(p)) if os.path.exists(p) else None


def norm(name):
    """Strict county key: strip the unit suffix, then every non-alphanumeric.

    Both sides of the join MUST use this one function.  Miami-Dade vs
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
    if not isinstance(rec, dict):
        return None
    if isinstance(rec.get("total"), (int, float)):
        return int(rec["total"])
    tot, seen = 0, False
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


def eday_band(code, ev26, eavs, override=None):
    """Election-day ballots from the state's own last two midterms, then the
    turnout that implies -- capped at 2024, since a midterm does not outpoll a
    presidential year."""
    st = ((eavs or {}).get("states") or eavs or {}).get(code) or {}
    eds = [st.get(y, {}).get("election_day") for y in MIDTERMS]
    eds = [e for e in eds if e]
    if not eds:
        return None
    cap = (st.get("2024") or {}).get("total_ballots")
    out = {"eday_midterms": {y: st.get(y, {}).get("election_day") for y in MIDTERMS},
           "eday_2024": (st.get("2024") or {}).get("election_day"),
           "turnout_2024": cap, "cases": {}}
    cases = [("eday_low", min(eds)), ("eday_high", max(eds))]
    if override:
        cases.append(("eday_set", int(override)))
        out["eday_override"] = int(override)
    for tag, ed in cases:
        turnout = ev26 + ed
        capped = bool(cap and turnout > cap)
        if capped:
            turnout = cap
            ed = max(cap - ev26, 1)
        out["cases"][tag] = {"eday_ballots": ed, "turnout": turnout,
                             "capped_at_2024": capped,
                             "banked_share": round(100 * ev26 / turnout, 1)}
    return out


def model_state(code, base, ev, skew, k, series, k_hisp, race, eavs, eday_override=None):
    cty = base["counties"]
    hisp = {}
    if race and k_hisp is not None:
        hisp = {key: v.get("hispanic_pct") for key, v in (race.get(code) or {}).items()}
    m20 = {}
    if series:
        for fips, c in ((series.get(code) or {}).get("2020", {}).get("counties", {})).items():
            mm = margin(c["R"], c["D"])
            if mm is not None:
                m20[fips.zfill(5)] = mm

    rows, miss = [], []
    for name, rec in ev.items():
        n = norm(name)
        if n in ("NA", "", "TOTAL", "STATEWIDE"):
            continue
        b, t = cty.get(n), ev_total(rec)
        if b is None:
            if t:
                miss.append(name)
            continue
        if t is None:
            continue
        tp = b["R"] + b["D"]
        m24 = margin(b["R"], b["D"])
        prev = m20.get(b["fips"].zfill(5))
        swing = (m24 - prev) if (prev is not None and m24 is not None) else None
        kk = k_hisp if (k_hisp is not None and (hisp.get(n) or 0) >= HISP_CUT) else k
        rows.append({"county": b["name"], "ev_2026": t, "votes_2024": b["total"],
                     "twoparty_2024": tp, "R24": b["R"], "D24": b["D"],
                     "margin_2024": m24, "margin_2020": prev, "swing_20_24": swing,
                     "hispanic_pct": hisp.get(n),
                     "margin_base": (m24 - kk * swing) if swing is not None else m24,
                     "pace": (t / b["total"]) if b["total"] else None})
    rows = [r for r in rows if r["margin_base"] is not None and r["pace"] is not None]
    if len(rows) < 10:
        return None

    joined_ev = sum(r["ev_2026"] for r in rows)
    tp_all = sum(r["twoparty_2024"] for r in rows)
    state_m24 = margin(base["R"], base["D"])
    state_base = sum(r["margin_base"] * r["twoparty_2024"] for r in rows) / tp_all

    # layer 1
    banked_mix = sum(r["ev_2026"] * r["margin_base"] for r in rows) / joined_ev
    rem_w = [(r, max(r["twoparty_2024"] - r["ev_2026"], 0)) for r in rows]
    rem_tot = sum(x for _, x in rem_w)
    rem_mix = (sum(r["margin_base"] * x for r, x in rem_w) / rem_tot) if rem_tot else None

    sw = [r for r in rows if r["swing_20_24"] is not None]
    ev_swing = (sum(r["swing_20_24"] * r["ev_2026"] for r in sw)
                / sum(r["ev_2026"] for r in sw)) if sw else None

    # layers 2 + 3
    band = eday_band(code, joined_ev, eavs, eday_override)
    be = {}
    if band:
        for tag, c in band["cases"].items():
            s = min(joined_ev / c["turnout"], 0.999)
            m_ev = banked_mix + (1 - s) * skew
            m_ed = (rem_mix - s * skew) if rem_mix is not None else None
            needs = -s * m_ev / (1 - s)
            be[tag] = {**c,
                       "banked_margin": round(m_ev, 2),
                       "eday_margin_at_baseline": round(m_ed, 2) if m_ed is not None else None,
                       "ed_margin_R_needs": round(needs, 2),
                       "R_gap": round(needs - m_ed, 2) if m_ed is not None else None,
                       # NOT a reconciliation check: the two pools are weighted
                       # by the 2026 banked share, not by 2024's, so this is the
                       # PROJECTED final margin under the chosen baseline.  It is
                       # near-invariant to the skew (the skew cancels in the sum);
                       # the split between the two pools is not.
                       "projected_final": round(s * m_ev + (1 - s) * m_ed, 2)
                       if m_ed is not None else None}

    rows.sort(key=lambda r: -r["votes_2024"])

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

    return {"counties_joined": len(rows), "counties_unmatched": sorted(miss),
            "ev_joined": joined_ev,
            "turnout_2024_joined": sum(r["votes_2024"] for r in rows),
            "twoparty_2024_joined": tp_all,
            "margin_2024_statewide": round(state_m24, 2),
            "reversion_k": k, "reversion_k_hispanic": k_hisp,
            "margin_baseline_statewide": round(state_base, 2),
            "swing_20_24_ev_weighted": round(ev_swing, 2) if ev_swing is not None else None,
            "counties_with_2020": len(sw),
            "banked_mix": round(banked_mix, 2),
            "mix_effect": round(banked_mix - state_base, 2),
            "eday_mix": round(rem_mix, 2) if rem_mix is not None else None,
            "ev_skew_within_county": skew,
            "turnout": band, "break_even": be,
            "cut_big": cut(rows[:BIG]), "cut_small": cut(rows[BIG:]),
            "counties": rows}


def main():
    skew, k, k_hisp, edays = DEFAULT_SKEW, DEFAULT_K, None, {}
    for a in sys.argv[1:]:
        if a.startswith("--skew="):
            skew = float(a.split("=", 1)[1])
        elif a.startswith("--revert-hispanic="):
            k_hisp = float(a.split("=", 1)[1])
        elif a.startswith("--revert="):
            k = float(a.split("=", 1)[1])
        elif a.startswith("--eday="):
            # --eday=TX:2500000  -- an election-day ballot count set by hand,
            # for when the EAVS midterm band is not the constraint that binds
            for part in a.split("=", 1)[1].split(","):
                st, _, n = part.partition(":")
                edays[st.strip().upper()] = int(float(n))
    base = load("county-2024.json")
    if not base:
        raise SystemExit("run collectors/county_baseline.py first")
    series = (load("county-series.json") or {}).get("states")
    race = (load("county-race.json") or {}).get("states")
    eavs = load("eavs.json")

    out = {}
    for code, b in sorted(base["states"].items()):
        ev = load(f"early-{code}.json")
        if not ev or not isinstance(ev.get("counties"), dict) or not ev["counties"]:
            continue
        m = model_state(code, b, ev["counties"], skew, k, series, k_hisp, race, eavs,
                        edays.get(code))
        if m:
            m["as_of"] = ev.get("as_of")
            out[code] = m
    json.dump({"basis": __doc__.strip().splitlines()[0],
               "margin_convention": "R-positive: +5 = Republican ahead by 5 points",
               "skew_within_county_measured": SKEW_WITHIN, "ev_skew_applied": skew,
               "reversion_k": k, "reversion_k_hispanic": k_hisp,
               "hispanic_cut_pct": HISP_CUT,
               "states": out}, open(os.path.join(DATA, "model.json"), "w"),
              indent=1, sort_keys=True)

    hdr = ("st   cty    EV 2026 | eday band   turnout  bank% | basel    mix  banked"
           "  eday | R needs   R GAP")
    print(hdr); print("-" * len(hdr))
    for code, m in out.items():
        lo = (m["break_even"].get("eday_set")
              or m["break_even"].get("eday_high"))  # most election-day ballots = best for R
        hi = m["break_even"].get("eday_low")
        if not lo:
            continue
        f = lambda v, w: ("%+*.2f" % (w, v)) if v is not None else "-".rjust(w)
        cap = "*" if lo["capped_at_2024"] else " "
        print("%-3s %4d %10s | %9s %9s %5.1f%%%s| %6s %6s %7s %6s | %8s %7s" % (
            code, m["counties_joined"], format(m["ev_joined"], ","),
            format(lo["eday_ballots"], ","), format(lo["turnout"], ","),
            lo["banked_share"], cap,
            f(m["margin_baseline_statewide"], 6), f(m["mix_effect"], 6),
            f(lo["banked_margin"], 7), f(lo["eday_margin_at_baseline"], 6),
            f(lo["ed_margin_R_needs"], 8), f(lo["R_gap"], 7)))
    print("\nskew applied %+.2f (NC within-county, midterm mean of 2018 %+.2f and 2022 %+.2f)"
          % (skew, SKEW_WITHIN["2018"], SKEW_WITHIN["2022"]))
    print("baseline k=%g%s" % (k, "" if k_hisp is None else ", k_hispanic=%g" % k_hisp))
    print("eday band = the state's own larger midterm election-day count (2018 vs 2022);")
    print("  * = turnout capped at the state's 2024 total.  bank% = EV / that turnout.")
    print("R GAP = points R must beat the baseline by on election day to tie.")
    print("  It is algebraically independent of the skew -- the skew cancels.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
