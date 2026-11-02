#!/usr/bin/env python3
"""Texas vote by ethnicity, MEASURED -> data/tx-vote-by-ethnicity.json

Texas has no race on its voter file and no state reports votes by race, so the
usual answers are exit polls (a survey, and they disagreed by 20 points on Texas
Hispanics in 2024) or ecological regression (which on Texas counties returns an
implied Black margin of -131 points, outside the possible range).

There is a third way that is neither. The Texas Legislative Council publishes
election returns AND voting-age population by race on the SAME geography -- the
voting district. So in precincts where almost everyone of voting age is a single
group, the counted result IS that group's vote. No model, no survey: ballots.

THE JOIN. Do not key on the published CNTYVTD column. The returns use county FIPS
(001-507, odd) while the 2024 population file uses a sequential county number
(1-254), and the population files drop leading zeros. Keying on CNTYVTD as
published matches 243 of 9,712 precincts in 2024 -- and still matched 7,341 in
2022, which looks like a working join and is not: it silently keeps only the
counties with three-digit codes. Build the key from CountyFIPS + VTD instead and
both years land above 98%.

WHAT IT CANNOT DO. A 90%-Hispanic precinct is 90% Hispanic by RESIDENTS, not by
voters, and such precincts are not a random sample of their group -- Texas's
are concentrated on the border and in urban cores. Read these as the vote in
those places, which is what they are.
"""
import csv, json, os, sys, urllib.request, io, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "tx-vote-by-ethnicity.json")
API = "https://ted.capitol.texas.gov/api/Offices/{eid}/{oid}/vtd"
POP = {"2022": "https://data.capitol.texas.gov/dataset/4d8298d0-d176-4c19-b174-42837027b73e/"
                "resource/c2f5a857-0b16-473b-8237-5268c2e25ac2/download/vtds_22g_pop.zip",
       "2024": "https://data.capitol.texas.gov/dataset/4d8298d0-d176-4c19-b174-42837027b73e/"
                "resource/bf9b54a8-090c-41d0-8f00-e263fc1789c5/download/vtds_24pg_pop.zip"}
RACES = [("2018 Governor",  456, 37, "Abbott", "Valdez",   "2022"),
         ("2018 US Senate", 456,  2, "Cruz",   "O'Rourke", "2022"),
         ("2022 Governor",  497, 37, "Abbott", "O'Rourke", "2022"),
         ("2024 President", 510,  1, "Trump",  "Harris",   "2024"),
         ("2024 US Senate", 510,  2, "Cruz",   "Allred",   "2024")]
CUTS = [("anglo", "Anglo (white)", 0.90), ("anglo", "Anglo (white)", 0.80),
        ("hisp", "Hispanic", 0.90), ("hisp", "Hispanic", 0.80),
        ("black", "Black", 0.70), ("black", "Black", 0.50),
        ("asian", "Asian", 0.40)]
UA = {"User-Agent": "Mozilla/5.0"}


def get(url, timeout=240):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def population(year):
    blob = get(POP[year])
    z = zipfile.ZipFile(io.BytesIO(blob))
    name = next(n for n in z.namelist() if n.lower().endswith((".txt", ".csv")))
    out = {}
    for r in csv.DictReader(io.StringIO(z.read(name).decode("utf-8-sig", "replace"))):
        f = (r.get("CountyFIPS") or "").strip().strip('"')
        v = (r.get("VTD") or "").strip().strip('"')
        if not (f and v):
            continue
        try:
            vap = int(float(r["vap"] or 0))
            if vap <= 0:
                continue
            out[f.zfill(3) + v.zfill(4)] = {
                "vap": vap, "anglo": int(float(r["anglovap"] or 0)),
                "black": int(float(r["blackvap"] or 0)),
                "hisp": int(float(r["hispvap"] or 0)),
                "asian": int(float(r["asianvap"] or 0))}
        except (ValueError, TypeError, KeyError):
            continue
    return out


def returns(eid, oid, rname, dname):
    rows = list(csv.DictReader(io.StringIO(get(API.format(eid=eid, oid=oid))
                                           .decode("utf-8-sig", "replace"))))
    rc = next((c for c in rows[0] if c.startswith(rname)), None)
    dc = next((c for c in rows[0] if c.startswith(dname)), None)
    if not (rc and dc):
        raise SystemExit(f"candidate columns not found: {list(rows[0])[:8]}")
    out = {}
    for r in rows:
        k = (r.get("CNTYVTD") or "").strip().strip('"').zfill(7)
        try:
            out[k] = (int(float(r[rc] or 0)), int(float(r[dc] or 0)))
        except (ValueError, TypeError):
            continue
    return out


def main():
    if os.path.exists(OUT) and "--refresh" not in sys.argv:
        print("cached; --refresh to re-pull", file=sys.stderr)
        return 0
    pops = {y: population(y) for y in POP}
    out = {}
    for label, eid, oid, rn, dn, pyear in RACES:
        rr, pp = returns(eid, oid, rn, dn), pops[pyear]
        joined = [(rr[k], pp[k]) for k in rr if k in pp]
        cov = len(joined) / len(rr) if rr else 0
        if cov < 0.90:
            print(f"  {label}: only {100*cov:.1f}% of precincts joined -- DROPPED",
                  file=sys.stderr)
            continue
        groups = []
        for field, name, thr in CUTS:
            sub = [(v, p) for v, p in joined if p[field] / p["vap"] >= thr]
            R = sum(v[0] for v, _ in sub); D = sum(v[1] for v, _ in sub)
            if len(sub) < 5 or R + D < 1000:
                continue
            groups.append({"group": name, "threshold": thr, "precincts": len(sub),
                           "R": R, "D": D, "votes": R + D,
                           "D_share": round(100 * D / (R + D), 2),
                           "margin_R": round(100 * (R - D) / (R + D), 2)})
        out[label] = {"R_candidate": rn, "D_candidate": dn,
                      "population_year": pyear,
                      "precincts_joined": len(joined), "precincts_total": len(rr),
                      "coverage_pct": round(100 * cov, 1), "groups": groups}
    json.dump({"method": __doc__.strip(), "source_returns": API,
               "source_population": POP, "races": out},
              open(OUT, "w"), indent=1, sort_keys=True)
    for label, v in out.items():
        print(f"\n{label}  ({v['R_candidate']}/{v['D_candidate']})  "
              f"{v['precincts_joined']:,}/{v['precincts_total']:,} precincts "
              f"({v['coverage_pct']}%)")
        print(f"  {'group':22}{'cut':>6}{'prec':>7}{'votes':>11}{'D share':>9}{'margin':>9}")
        for g in v["groups"]:
            print(f"  {g['group']:22}{int(100*g['threshold']):>5}%{g['precincts']:>7,}"
                  f"{g['votes']:>11,}{g['D_share']:>8.1f}%{g['margin_R']:>+9.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
