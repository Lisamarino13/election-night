#!/usr/bin/env python3
"""Who gained share of the early vote, and what it is worth in points.
-> data/share-shift.json

This is the most defensible number in the whole model, because it is the only
one built from MEASURED TURNOUT rather than assumed behaviour.  It never asks
how anyone votes in 2026.  It asks: which counties are banking more of the
state's early vote than they banked in the last midterm, and what did those
counties do last time.

The identity is exact and fully additive.  Write s_Y,g for a group's share of
all early ballots in year Y, and m_Y,g for the ballot-weighted 2024 margin of
the counties in that group:

    implied margin of the early pool in year Y  =  SUM_g  s_Y,g * m_Y,g
    SHIFT  =  implied_2026 - implied_2022  =  SUM_g ( s26*m26 - s22*m22 )

and each group's contribution splits cleanly in two:

    composition  =  (s26 - s22) * m22     <- the group banked a bigger slice
    internal     =  s26 * (m26 - m22)     <- different counties INSIDE the group

Both are measured.  Neither requires a baseline year, a reversion knob, a skew,
or a turnout projection -- the four inputs that carry every judgement call
elsewhere in this model.  What it does NOT say is how 2026 will vote; it says
how the composition of who has already voted has moved, priced at 2024 behaviour.

Only four states can be done: the rest publish no county-level 2022 early vote.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
STATES = ("TX", "NC", "FL", "IA")
PRIOR = "2022"

SIZE = [("metro 250k+", 250000, 10**9), ("mid 50-250k", 50000, 250000),
        ("small <50k", 0, 50000)]
HISP = [("Hispanic 50%+", 50, 101), ("Hispanic 25-50%", 25, 50), ("Hispanic <25%", 0, 25)]
BLACK = [("Black 20%+", 20, 101), ("Black 10-20%", 10, 20), ("Black <10%", 0, 10)]
# How Republican the county actually VOTED, 2024 two-party.  This is the cut
# that answers "who voted R historically" directly, with no demographic proxy.
RVOTE = [("R+50 and up", 50, 1000), ("R+35 to +50", 35, 50), ("R+20 to +35", 20, 35),
         ("R+5 to +20", 5, 20), ("within 5 pts", -5, 5), ("D counties", -1000, -5)]
CUTS = [("how it VOTED 2024", RVOTE, lambda r: r["margin_2024"]),
        ("county size", SIZE, lambda r: r["votes_2024"]),
        ("Hispanic share", HISP, lambda r: r["hispanic"]),
        ("Black share", BLACK, lambda r: r["black"])]


def load(n):
    p = os.path.join(DATA, n)
    return json.load(open(p)) if os.path.exists(p) else None


def norm(name):
    n = str(name).strip().upper()
    for suf in (" COUNTY", " PARISH", " CENSUS AREA", " BOROUGH",
                " CITY AND BOROUGH", " MUNICIPALITY", " CITY"):
        if n.endswith(suf):
            n = n[: -len(suf)]
            break
    return "".join(c for c in n if c.isalnum())


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
            break
    return tot if seen else None


def one_state(code, base, race, hist, cur):
    prior = (hist.get("years") or {}).get(PRIOR, {}).get("counties") or {}
    ev22 = {norm(k): ev_total(v) for k, v in prior.items()}
    ev26 = {norm(k): ev_total(v) for k, v in (cur.get("counties") or {}).items()}
    cty = base["counties"]
    rr = race.get(code) or {}
    rows, dropped = [], []
    for key in set(ev22) | set(ev26):
        if key in ("NA", "", "TOTAL", "STATEWIDE"):
            continue
        b, d = cty.get(key), rr.get(key)
        a, c = ev22.get(key), ev26.get(key)
        if not (b and d and a and c):
            if a or c:
                dropped.append(key)
            continue
        m = 100.0 * (b["R"] - b["D"]) / (b["R"] + b["D"]) if (b["R"] + b["D"]) else None
        if m is None:
            continue
        rows.append({"county": b["name"], "ev_2022": a, "ev_2026": c,
                     "margin_2024": m, "votes_2024": b["total"],
                     "hispanic": d["hispanic_pct"], "black": d["black_pct"]})
    if len(rows) < 10:
        return None
    T22 = sum(r["ev_2022"] for r in rows); T26 = sum(r["ev_2026"] for r in rows)
    imp22 = sum(r["ev_2022"] * r["margin_2024"] for r in rows) / T22
    imp26 = sum(r["ev_2026"] * r["margin_2024"] for r in rows) / T26

    cuts = {}
    for cname, bands, field in CUTS:
        out, chk = [], 0.0
        for lbl, lo, hi in bands:
            sub = [r for r in rows if lo <= field(r) < hi]
            if not sub:
                continue
            e22 = sum(r["ev_2022"] for r in sub); e26 = sum(r["ev_2026"] for r in sub)
            if not (e22 and e26):
                continue
            s22, s26 = e22 / T22, e26 / T26
            m22 = sum(r["ev_2022"] * r["margin_2024"] for r in sub) / e22
            m26 = sum(r["ev_2026"] * r["margin_2024"] for r in sub) / e26
            comp, intern = (s26 - s22) * m22, s26 * (m26 - m22)
            chk += comp + intern
            out.append({"group": lbl, "counties": len(sub),
                        "ev_2022": e22, "ev_2026": e26,
                        "pace": round(e26 / e22, 4),
                        "share_2022": round(100 * s22, 3),
                        "share_2026": round(100 * s26, 3),
                        "share_change": round(100 * (s26 - s22), 3),
                        "margin_2024": round(m26, 2),
                        "pts_composition": round(comp, 3),
                        "pts_internal": round(intern, 3),
                        "pts_total": round(comp + intern, 3)})
        cuts[cname] = {"groups": out, "sums_to": round(chk, 3)}
    return {"counties": len(rows), "dropped": sorted(dropped),
            "ev_2022": T22, "ev_2026": T26, "pace": round(T26 / T22, 4),
            "implied_margin_2022": round(imp22, 2),
            "implied_margin_2026": round(imp26, 2),
            "shift": round(imp26 - imp22, 3),
            "cuts": cuts, "county_rows": rows}


def main():
    base, race = load("county-2024.json"), load("county-race.json")
    if not (base and race):
        raise SystemExit("run county_baseline.py and census_race.py first")
    out = {}
    for code in STATES:
        hist, cur = load(f"ev-history-{code}.json"), load(f"early-{code}.json")
        if not (hist and cur):
            continue
        r = one_state(code, base["states"][code], race["states"], hist, cur)
        if r:
            r["as_of"] = cur.get("as_of")
            out[code] = r
    json.dump({"prior": PRIOR, "method": __doc__.strip(),
               "margin_convention": "R-positive; the early pool priced at 2024 county behaviour",
               "states": out}, open(os.path.join(DATA, "share-shift.json"), "w"),
              indent=1, sort_keys=True)

    for code, s in out.items():
        print(f"\n{'='*78}\n{code}  {s['counties']} counties  "
              f"{s['ev_2022']:,} -> {s['ev_2026']:,}  (pace {s['pace']:.2f})")
        print(f"  early pool priced at 2024 behaviour: 2022 R{s['implied_margin_2022']:+.2f}"
              f"  ->  2026 R{s['implied_margin_2026']:+.2f}"
              f"   SHIFT {s['shift']:+.2f} pts")
        for cname, c in s["cuts"].items():
            print(f"\n  {cname:18}{'cty':>4}{'pace':>7}{'share22':>9}{'share26':>9}"
                  f"{'change':>8}{'2024 mgn':>10}{'PTS':>8}")
            for g in c["groups"]:
                print(f"    {g['group']:16}{g['counties']:>4}{g['pace']:>7.2f}"
                      f"{g['share_2022']:>8.2f}%{g['share_2026']:>8.2f}%"
                      f"{g['share_change']:>+8.2f}{g['margin_2024']:>+10.2f}"
                      f"{g['pts_total']:>+8.2f}")
            print(f"    {'sums to':16}{'':>4}{'':>7}{'':>9}{'':>9}{'':>8}{'':>10}"
                  f"{c['sums_to']:>+8.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
