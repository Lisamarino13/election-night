#!/usr/bin/env python3
"""Texas county results for the last two MIDTERMS -> data/tx-midterms.json

Everything else in this model baselines on presidential years, which is the
wrong prior for a midterm.  These are the two midterms Texas has actually run
with the current county map: 2018 and 2022 Governor.

Source is the Texas Legislative Council's own returns API (ted.capitol.texas.gov),
published VTD by VTD; the first three digits of CNTYVTD are the county code.
Both years are gated at 0.1% against the published statewide totals, the same
tolerance the rest of this project uses.  They come in at 0.04% and 0.03%.  The
residual is not necessarily the API's: the comparison totals are the widely
published ones rather than the official canvass, and the TLC reallocates votes
to VTDs, so a few hundred ballots move.  The exact deltas are recorded in the
output so nothing downstream can claim an exact tie-out.

Why not the obvious sources: the Secretary of State publishes no county-level
page, and OpenElections' 2022 Texas file covers 98 of 254 counties and 42% of
the vote, which silently produces a wrong answer if aggregated.
"""
import csv, io, json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "tx-midterms.json")
API = "https://ted.capitol.texas.gov/api/Offices/{eid}/37/vtd"
UA = {"User-Agent": "Mozilla/5.0"}
YEARS = {
    "2018": {"eid": 456, "R": "AbbottR", "D": "ValdezD",
             "certified": (4656196, 3546615), "race": "Governor Abbott/Valdez"},
    "2022": {"eid": 497, "R": "AbbottR", "D": "O'RourkeD",
             "certified": (4435558, 3553656), "race": "Governor Abbott/O'Rourke"},
}


def fetch(eid):
    req = urllib.request.Request(API.format(eid=eid), headers=UA)
    with urllib.request.urlopen(req, timeout=240) as r:
        return r.read().decode("utf-8-sig", "replace")


def main():
    if os.path.exists(OUT) and "--refresh" not in sys.argv:
        print("cached; --refresh to re-pull", file=sys.stderr)
        return 0
    base = json.load(open(os.path.join(HERE, "..", "data", "county-2024.json")))
    names = {v["fips"].zfill(5): v["name"] for v in base["states"]["TX"]["counties"].values()}

    out, checks = {}, {}
    for year, spec in YEARS.items():
        rows = list(csv.DictReader(io.StringIO(fetch(spec["eid"]))))
        rcol = next((c for c in rows[0] if c.startswith(spec["R"])), None)
        dcol = next((c for c in rows[0] if c.startswith(spec["D"])), None)
        if not (rcol and dcol):
            raise SystemExit(f"{year}: cannot find candidate columns in {list(rows[0])}")
        cty = {}
        for r in rows:
            code = (r.get("CNTYVTD") or "").strip().strip('"')
            if len(code) < 4:
                continue
            fips = "48" + code[:3]
            c = cty.setdefault(fips, {"R": 0, "D": 0})
            try:
                c["R"] += int(float(r[rcol] or 0)); c["D"] += int(float(r[dcol] or 0))
            except ValueError:
                continue
        R = sum(c["R"] for c in cty.values()); D = sum(c["D"] for c in cty.values())
        cR, cD = spec["certified"]
        exact = (R == cR and D == cD)
        ok = abs(R - cR) / cR <= 0.001 and abs(D - cD) / cD <= 0.001
        checks[year] = {"counties": len(cty), "R": R, "D": D,
                        "certified_R": cR, "certified_D": cD,
                        "delta_R": R - cR, "delta_D": D - cD, "exact": exact,
                        "within_0.1pct": ok,
                        "delta_R_pct": round(100 * abs(R - cR) / cR, 4),
                        "delta_D_pct": round(100 * abs(D - cD) / cD, 4)}
        if not ok:
            print(f"  {year}: R {R:,} vs {cR:,}, D {D:,} vs {cD:,} -- NOT exact",
                  file=sys.stderr)
            continue
        for f, c in cty.items():
            c["name"] = names.get(f, f)
            c["margin"] = round(100 * (c["R"] - c["D"]) / (c["R"] + c["D"]), 3) \
                if (c["R"] + c["D"]) else None
        out[year] = {"race": spec["race"], "R": R, "D": D,
                     "margin": round(100 * (R - D) / (R + D), 3), "counties": cty}

    if len(out) != len(YEARS):
        raise SystemExit("a year missed the 0.1% tie-out -- refusing to publish")

    json.dump({"state": "TX", "source": API, "checks": checks, "years": out},
              open(OUT, "w"), indent=1, sort_keys=True)
    print(f"{'yr':6}{'cty':>5}{'R':>11}{'D':>11}{'margin':>9}  tie-out")
    for y, v in sorted(out.items()):
        c = checks[y]
        print(f"{y:6}{c['counties']:>5}{v['R']:>11,}{v['D']:>11,}{v['margin']:>+9.2f}"
              f"  delta R {c['delta_R']:+,} ({c['delta_R_pct']:.3f}%)"
              f"  D {c['delta_D']:+,} ({c['delta_D_pct']:.3f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
