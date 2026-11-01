#!/usr/bin/env python3
"""North Carolina's mode split, election by election -> data/nc-mode-series.json

NC is the only state we track whose precinct file splits every contest by mode,
so it is the only place the early-vote skew -- how much more Democratic the
early pool is than the election-day pool -- can be MEASURED rather than assumed.

The measurement does not support treating the skew as a constant, and it does
not support deriving it from the early-vote share either:

    EV 55.5%  skew -21.16   2018 Supreme Court
    EV 58.5%  skew -29.63   2022 US Senate
    EV 79.5%  skew  -5.59   2024 Governor
    EV 83.9%  skew -37.85   2020 President

2020 is the COVID election: Democrats voted by mail at scale and Republicans
voted in person, which is why it carries the largest skew in the series.  2024
is the mirror-image outlier -- Republicans were told to vote early and did, and
the skew collapsed to a sixth of 2022's.  So the skew is a behavioural
parameter that has moved by 32 points inside six years, and the honest thing a
model can do is take it as a named knob with the measured series beside it.

The two clean midterms, which are what 2026 is, read -21 and -29.

Layouts differ: 2018/2020/2022 carry the modes as COLUMNS (Election Day /
One Stop / Absentee by Mail / Provisional), 2024 carries them as rows and is
read by replay_nc2024.py instead.
"""
import collections, csv, io, json, os, pathlib, sys, urllib.request, zipfile
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent / "data" / "nc-mode-series.json"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
URL = "https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/{dir}/results_pct_{stamp}.zip"
YEARS = {"2018": ("2018_11_06", "20181106"),
         "2020": ("2020_11_03", "20201103"),
         "2022": ("2022_11_08", "20221108")}
MODES = ["Election Day", "One Stop", "Absentee by Mail", "Provisional"]
EARLY = ("One Stop", "Absentee by Mail")
# the statewide partisan contest(s) in each of those years
CONTESTS = {"2018": ["NC SUPREME COURT ASSOCIATE JUSTICE SEAT 1",
                     "NC COURT OF APPEALS JUDGE SEAT 3"],
            "2020": ["US PRESIDENT", "US SENATE", "NC GOVERNOR"],
            "2022": ["US SENATE", "NC SUPREME COURT ASSOCIATE JUSTICE SEAT 03"]}
# measured by replay_nc2024.py off the 2024 file's row-wise mode layout
SKEW_2024 = {"US PRESIDENT": {"ev_share": 0.793, "skew": -11.78},
             "NC GOVERNOR": {"ev_share": 0.795, "skew": -5.59}}


def num(v):
    v = (v or "").strip().replace(",", "")
    return int(v) if v.lstrip("-").isdigit() else 0


def margin(r, d):
    return 100.0 * (r - d) / (r + d) if (r + d) else None


def fetch(year):
    d, stamp = YEARS[year]
    cache = pathlib.Path(f"/tmp/ncpct/{year}.zip")
    if cache.exists() and cache.stat().st_size > 500_000:
        return cache.read_bytes()
    req = urllib.request.Request(URL.format(dir=d, stamp=stamp), headers=UA)
    with urllib.request.urlopen(req, timeout=300) as r:
        body = r.read()
    if len(body) < 500_000:
        raise RuntimeError(f"{year}: {len(body)} bytes -- refusing a truncated download")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(body)
    return body


def one_year(year):
    z = zipfile.ZipFile(io.BytesIO(fetch(year)))
    with z.open(z.namelist()[0]) as fh:
        rows = list(csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8", errors="ignore"),
                                   delimiter="\t"))
    if "One Stop" not in (rows[0] if rows else {}):
        raise RuntimeError(f"{year}: unexpected layout, no 'One Stop' column")
    out = {}
    for name in CONTESTS[year]:
        tot = collections.defaultdict(collections.Counter)
        cty = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
        for r in rows:
            if (r["Contest Name"] or "").strip() != name:
                continue
            p = (r["Choice Party"] or "").strip()
            if p not in ("DEM", "REP"):
                continue
            c = (r["County"] or "").strip()
            for m in MODES:
                tot[p][m] += num(r[m])
                cty[c][p][m] += num(r[m])
        if not tot:
            continue
        eR = sum(tot["REP"][m] for m in EARLY); eD = sum(tot["DEM"][m] for m in EARLY)
        dR, dD = tot["REP"]["Election Day"], tot["DEM"]["Election Day"]
        if not (eR + eD and dR + dD):
            continue
        me, md = margin(eR, eD), margin(dR, dD)
        allR = sum(tot["REP"][m] for m in MODES); allD = sum(tot["DEM"][m] for m in MODES)
        out[name] = {
            "early": {"R": eR, "D": eD, "margin": round(me, 3)},
            "election_day": {"R": dR, "D": dD, "margin": round(md, 3)},
            "final": {"R": allR, "D": allD, "margin": round(margin(allR, allD), 3)},
            "ev_share_twoparty": round((eR + eD) / (eR + eD + dR + dD), 4),
            "skew": round(me - md, 2),
            "counties": {c: {p: dict(v) for p, v in d.items()} for c, d in cty.items()},
        }
    return out


def main():
    if OUT.exists() and "--refresh" not in sys.argv:
        print("cached; --refresh to re-pull", file=sys.stderr)
        return 0
    years = {y: one_year(y) for y in YEARS}
    years["2024"] = {k: dict(v) for k, v in SKEW_2024.items()}

    flat = []
    for y, contests in years.items():
        for name, v in contests.items():
            flat.append((v.get("ev_share_twoparty", v.get("ev_share")), v["skew"], y, name))
    flat.sort()
    mid = [s for sh, s, y, n in flat if y in ("2018", "2022")]

    json.dump({"state": "NC",
               "why": "the only state we track whose precinct file splits every contest by mode",
               "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "skew_definition": "early+mail two-party margin minus election-day two-party "
                                  "margin, R-positive; negative = early vote more Democratic",
               "notes": {"2020": "COVID: D voted by mail, R voted in person -- largest skew",
                         "2024": "R embraced early voting -- smallest skew in the series",
                         "2026": "a midterm; the clean midterm readings are 2018 and 2022"},
               "midterm_range": [min(mid), max(mid)],
               "midterm_mean": round(sum(mid) / len(mid), 2),
               "years": years}, open(OUT, "w"), indent=1, sort_keys=True)

    print(f"{'EVshr':>6} {'skew':>8}  {'yr':5} contest")
    for sh, s, y, n in flat:
        print(f"{100*sh:>5.1f}% {s:>+8.2f}  {y:5} {n}")
    print(f"\nmidterm (2018+2022) range {min(mid):+.2f} .. {max(mid):+.2f}, "
          f"mean {sum(mid)/len(mid):+.2f}")
    print("2020 is COVID; 2024 is the Republican early-vote adoption. Neither is a midterm.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
