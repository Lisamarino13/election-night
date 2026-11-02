#!/usr/bin/env python3
"""Texas county results, every statewide race, one flat table.
-> tx-county-races.csv  and  data/tx-county-races.json

county | race | R candidate | R votes | D votes | total votes | R % | D %

Source: the Texas Legislative Council returns API (ted.capitol.texas.gov),
published VTD by VTD. The first three digits of CNTYVTD are the county code.
Total votes includes every candidate on the ballot, not just the two majors.
Each race is checked against its published statewide totals and the delta is
recorded; nothing is silently adjusted.
"""
import csv, io, json, os, sys, urllib.request, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
API = "https://ted.capitol.texas.gov/api/Offices/{eid}/{oid}/vtd"
UA = {"User-Agent": "Mozilla/5.0"}

# (label, election id, office id, R surname, D surname, certified R, certified D)
RACES = [
    ("2018 Governor",  456, 37, "Abbott",  "Valdez",   4656196, 3546615),
    ("2018 US Senate", 456,  2, "Cruz",    "O'Rourke", 4260553, 4045632),
    ("2020 President", 377,  1, "Trump",   "Biden",    5890347, 5259126),
    ("2020 US Senate", 377,  2, "Cornyn",  "Hegar",    5962983, 4888764),
    ("2022 Governor",  497, 37, "Abbott",  "O'Rourke", 4435558, 3553656),
    ("2024 President", 510,  1, "Trump",   "Harris",   6393597, 4835250),
    ("2024 US Senate", 510,  2, "Cruz",    "Allred",   5990741, 5031249),
]


def fetch(eid, oid):
    req = urllib.request.Request(API.format(eid=eid, oid=oid), headers=UA)
    with urllib.request.urlopen(req, timeout=240) as r:
        return r.read().decode("utf-8-sig", "replace")


def main():
    names = {v["fips"].zfill(5): v["name"].replace(" County", "")
             for v in json.load(open(os.path.join(ROOT, "data", "county-2024.json")))
             ["states"]["TX"]["counties"].values()}
    out, checks = [], {}
    for label, eid, oid, rname, dname, cR, cD in RACES:
        rows = list(csv.DictReader(io.StringIO(fetch(eid, oid))))
        cols = [c for c in rows[0] if c not in ("CNTYVTD", "VTDKEY")]
        rcol = next((c for c in cols if c.startswith(rname)), None)
        dcol = next((c for c in cols if c.startswith(dname)), None)
        if not (rcol and dcol):
            print(f"  {label}: columns not found in {cols}", file=sys.stderr)
            continue
        cty = collections.defaultdict(lambda: {"R": 0, "D": 0, "total": 0})
        for r in rows:
            code = (r.get("CNTYVTD") or "").strip().strip('"')
            if len(code) < 4:
                continue
            c = cty["48" + code[:3]]
            for col in cols:
                try:
                    v = int(float(r[col] or 0))
                except (ValueError, TypeError):
                    continue
                c["total"] += v
                if col == rcol:
                    c["R"] += v
                elif col == dcol:
                    c["D"] += v
        R = sum(v["R"] for v in cty.values()); D = sum(v["D"] for v in cty.values())
        checks[label] = {"counties": len(cty), "R": R, "D": D,
                         "certified_R": cR, "certified_D": cD,
                         "delta_R": R - cR, "delta_D": D - cD,
                         "delta_R_pct": round(100 * abs(R - cR) / cR, 3),
                         "delta_D_pct": round(100 * abs(D - cD) / cD, 3)}
        for fips, v in cty.items():
            t = v["total"]
            out.append({"county": names.get(fips, fips), "race": label,
                        "R_candidate": rname, "D_candidate": dname,
                        "R_votes": v["R"], "D_votes": v["D"], "total_votes": t,
                        "R_pct": round(100 * v["R"] / t, 2) if t else None,
                        "D_pct": round(100 * v["D"] / t, 2) if t else None})

    out.sort(key=lambda r: (r["county"], r["race"]))
    path = os.path.join(ROOT, "tx-county-races.csv")
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    json.dump({"source": API, "checks": checks, "rows": out},
              open(os.path.join(ROOT, "data", "tx-county-races.json"), "w"), indent=1)

    print(f"{'race':16}{'cty':>5}{'R votes':>11}{'D votes':>11}{'dR':>9}{'dD':>9}{'worst':>8}")
    print("-" * 70)
    for label, c in checks.items():
        print(f"{label:16}{c['counties']:>5}{c['R']:>11,}{c['D']:>11,}"
              f"{c['delta_R']:>+9,}{c['delta_D']:>+9,}"
              f"{max(c['delta_R_pct'], c['delta_D_pct']):>7.3f}%")
    print(f"\n{len(out):,} rows -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
