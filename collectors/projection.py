#!/usr/bin/env python3
"""Where turnout is heading, and which counties are driving it -> data/projection.json

TURNOUT. The early vote alone cannot say whether turnout is up: the same ballots can
mean more voters, or the same voters voting earlier. So this gives a BAND rather than a
number. The early share in a midterm will plausibly land between the last midterm's and
the last presidential's, because early voting keeps growing, and those two shares are
the two ends:

    low  = EV 2026 / the HIGHER share   (most of the vote already in -> least to come)
    high = EV 2026 / the LOWER share

A state-year whose modes did not decompose carries no usable share and is skipped
rather than counted as zero - Iowa filed no breakdown at all in 2024 and its entire
1,674,011 ballots landed in 'other'.

COUNTIES. The state number hides the thing worth seeing. Each county's 2026 early vote
is set against ITS OWN 2022, which controls for size, and the counties are split by how
much early vote they cast in 2022. In Texas the fifteen largest are running 1.44x
against 1.28x for the 110 smaller ones, and the sharpest are South Texas - Hidalgo
1.60x, El Paso 1.57x - not the suburbs.

Both halves are recomputed every pull; the EAVS county figures behind them do not move.
"""
import json, pathlib, statistics, sys

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


def current_ev():
    out = {}
    for p in DATA.glob("early-*.json"):
        d = json.loads(p.read_text())
        S = d.get("state_totals") or {}
        def t(k):
            v = S.get(k)
            v = v.get("total") if isinstance(v, dict) else v
            return v if isinstance(v, (int, float)) else None
        mail = next((t(k) for k in ("by_mail", "mail_returned", "returned")
                     if t(k) is not None), 0)
        ip = next((t(k) for k in ("in_person", "early_in_person")
                   if t(k) is not None), 0)
        out[d["state"]] = {"ev": (mail or 0) + (ip or 0),
                           "counties": d.get("counties") or d.get("units") or {},
                           "unit": d.get("unit") or "county",
                           "as_of": d.get("as_of")}
    return out


def usable_share(cell):
    """The early share, or None when the modes did not decompose."""
    if not cell or not cell.get("total_ballots"):
        return None
    tot = cell["total_ballots"]
    if (cell.get("other") or 0) > 0.20 * tot:
        return None
    ev = cell.get("early_total")
    return (ev / tot) if ev else None


def county_pace(st, now_counties, prior_counties):
    """Each county's 2026 early vote against its own 2022, split big against small."""
    def key(s):
        return "".join(c for c in str(s).upper() if c.isalnum() or c == " ")\
                 .replace(" COUNTY", "").strip()
    now = {}
    for name, b in (now_counties or {}).items():
        if key(name) in ("STATEWIDE", "STATE", "TOTAL"):
            continue
        g = lambda k: (b[k].get("total") if isinstance(b.get(k), dict) else b.get(k)) or 0
        mail = next((g(k) for k in ("by_mail", "mail_returned", "returned") if g(k)), 0)
        ip = next((g(k) for k in ("in_person", "early_in_person") if g(k)), 0)
        now[key(name)] = mail + ip
    pairs = [(c, now[c], prior_counties[c]) for c in now
             if c in prior_counties and prior_counties[c] > 2000]
    if len(pairs) < 8:
        return None
    pairs.sort(key=lambda x: -x[2])
    big = pairs[:15]
    small = [p for p in pairs if p[2] < 15000]
    r = lambda ps: statistics.median([a / b for _, a, b in ps]) if ps else None
    hot = sorted(pairs, key=lambda x: -(x[1] / x[2]))[:8]
    return {"compared": len(pairs),
            "largest_15_ratio": r(big),
            "smaller_ratio": r(small),
            "smaller_n": len(small),
            "counties": [{"county": c, "ev_2026": a, "ev_2022": b, "ratio": a / b}
                         for c, a, b in pairs],
            "fastest": [{"county": c, "ratio": a / b} for c, a, b in hot]}


def main():
    eavs = json.loads((DATA / "eavs.json").read_text())["states"] \
        if (DATA / "eavs.json").exists() else {}
    cty_prior = json.loads((DATA / "eavs-counties.json").read_text())["states"] \
        if (DATA / "eavs-counties.json").exists() else {}
    cur = current_ev()
    out = {}
    for st, c in sorted(cur.items()):
        e = eavs.get(st) or {}
        s22, s24 = usable_share(e.get("2022")), usable_share(e.get("2024"))
        row = {"ev_2026": c["ev"], "as_of": c["as_of"],
               "share_2022": s22, "share_2024": s24,
               "turnout_2022": (e.get("2022") or {}).get("total_ballots"),
               "ev_2022": (e.get("2022") or {}).get("early_total")}
        shares = [x for x in (s22, s24) if x]
        if shares:
            row["projected"] = {"low": round(c["ev"] / max(shares)),
                                "high": round(c["ev"] / min(shares)),
                                "basis": "EV 2026 over the last midterm and last "
                                         "presidential early shares"}
        if row["ev_2022"]:
            row["ev_vs_2022"] = c["ev"] / row["ev_2022"]
        # Maine reports by MUNICIPALITY. Matched against county names it found a
        # handful of accidental hits and reported 0.05x, which is not a pace, it is a
        # failed join.
        p = (county_pace(st, c["counties"], cty_prior.get(st) or {})
             if c.get("unit") == "county" else None)
        if c.get("unit") != "county":
            row["county_pace_unavailable"] = (
                f"this state reports by {c.get('unit')}, the survey by county")
        if p:
            row["county_pace"] = p
        out[st] = row
    doc = {"note": ("A turnout BAND, not a number: the early vote cannot say by itself "
                    "whether more people are voting or the same people are voting "
                    "earlier. County pace sets each county against its own 2022."),
           "states": out}
    (DATA / "projection.json").write_text(json.dumps(doc, indent=1) + "\n")
    print(f"{'st':4s} {'EV 2026':>10s} {'vs22':>6s} {'low':>11s} {'high':>11s} "
          f"{'2022':>11s}  counties big/small")
    for st, r in sorted(out.items()):
        pr = r.get("projected") or {}
        cp = r.get("county_pace") or {}
        bs = (f"{cp['largest_15_ratio']:.2f}x / {cp['smaller_ratio']:.2f}x"
              if cp.get("largest_15_ratio") and cp.get("smaller_ratio") else "")
        v = r.get("ev_vs_2022")
        vs = ("%.2fx" % v) if v else "-"
        print(f"{st:4s} {r['ev_2026']:>10,} {vs:>6s} "
              f"{pr.get('low',0):>11,} {pr.get('high',0):>11,} "
              f"{(r.get('turnout_2022') or 0):>11,}  {bs}")
    print(f"   -> projection.json")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as e:
        print(f"PROJECTION FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
