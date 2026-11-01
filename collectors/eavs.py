#!/usr/bin/env python3
"""Total ballots and the mode split, every state, every federal election -> data/eavs.json

The early-vote files carry no turnout, and the Lab's early-vote archive only goes back
to 2024, so five states had nothing before 2024 and the rest had gaps. The EAC's
Election Administration and Voting Survey has both for every state and every cycle: it
is the survey every jurisdiction files after each federal election.

Two releases are read, because the EAC changed its column names between them:

  2018/2020/2022  the data-interactive extract: f1a total, f1b election day in person,
                  f1mail by mail, f1f early in person
  2024            the public release: F1a total, F1b election day in person,
                  F1d by mail, F1f early in person

In both, the mode columns sum EXACTLY to the total in every state, which is the check
that the mapping is right. The totals also tie to the Lab's turnout figures - Ohio 2022
4,201,368 and Michigan 2022 4,500,400 to the ballot, Georgia within 0.04%.

These are historical surveys and do not change, so the derived file is kept and the
source workbooks are only fetched when it is missing or --refresh is passed. They are
3MB and 13MB; re-downloading them every half hour would be rude and pointless.
"""
import json, pathlib, sys, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import xlsx

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
OUT = DATA / "eavs.json"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}

SOURCES = [
    {"url": "https://www.eac.gov/sites/default/files/2023-10/"
            "EAVS_2022_Data_Interactive_Raw_Data.xlsx",
     "state": "PostalCode", "year": "Year",
     "cols": {"total": "f1a", "election_day": "f1b", "mail": "f1mail",
              "early_in_person": "f1f"}},
    {"url": "https://www.eac.gov/sites/default/files/2025-06/"
            "2024_EAVS_for_Public_Release_V1_xlsx.xlsx",
     "state": "State_Abbr", "year": None, "fixed_year": "2024",
     "cols": {"total": "F1a", "election_day": "F1b", "mail": "F1d",
              "early_in_person": "F1f"}},
]


def num(v):
    try:
        f = float(str(v).replace(",", "").strip() or 0)
    except ValueError:
        return 0
    # EAVS uses negative sentinels (-99 and friends) for "not reported".
    return int(f) if f >= 0 else 0


def pull(src):
    with urllib.request.urlopen(urllib.request.Request(src["url"], headers=UA),
                                timeout=300) as r:
        body = r.read()
    rows = xlsx.rows(body)
    if not rows:
        raise RuntimeError(f"{src['url']}: no rows")
    hdr = [str(h).strip() for h in rows[0]]
    ix = {h: i for i, h in enumerate(hdr)}
    for need in [src["state"]] + list(src["cols"].values()):
        if need not in ix:
            raise RuntimeError(f"{src['url']}: column {need!r} missing — layout changed")
    cty_col = next((c for c in ("County", "Jurisdiction_Name") if c in ix), None)
    out, counties = {}, {}
    for row in rows[1:]:
        st = str(row[ix[src["state"]]]).strip().upper()
        yr = (src.get("fixed_year") or str(row[ix[src["year"]]]).strip())
        if not st or not yr or len(st) != 2:
            continue
        cell = out.setdefault((st, yr), dict.fromkeys(src["cols"], 0))
        for name, col in src["cols"].items():
            cell[name] += num(row[ix[col]])
        # Keep the county rows as well. The state number hides which places are
        # actually driving a change, and each county set against its own prior cycle
        # controls for size.
        if cty_col:
            nm = "".join(ch for ch in str(row[ix[cty_col]]).upper()
                         if ch.isalnum() or ch == " ").replace(" COUNTY", "").strip()
            if nm:
                ev = num(row[ix[src["cols"]["mail"]]]) + \
                     num(row[ix[src["cols"]["early_in_person"]]])
                d = counties.setdefault(yr, {}).setdefault(st, {})
                d[nm] = d.get(nm, 0) + ev
    return out, counties


def main(argv):
    if OUT.exists() and "--refresh" not in argv:
        print(f"eavs: {OUT.name} already built (pass --refresh to re-download); "
              f"these are historical surveys and do not change")
        return 0
    states, all_cty = {}, {}
    for src in SOURCES:
        got, counties = pull(src)
        for yr, per_state in counties.items():
            for st, d in per_state.items():
                all_cty.setdefault(yr, {}).setdefault(st, {}).update(d)
        for (st, yr), cell in got.items():
            parts = cell["election_day"] + cell["mail"] + cell["early_in_person"]
            states.setdefault(st, {})[yr] = {
                "total_ballots": cell["total"],
                "election_day": cell["election_day"],
                "mail": cell["mail"],
                "early_in_person": cell["early_in_person"],
                "early_total": cell["mail"] + cell["early_in_person"],
                # What the three named modes leave over: provisional and anything the
                # jurisdiction filed under another line. Reported, not folded in.
                "other": cell["total"] - parts,
            }
    doc = {"note": ("Total ballots and the mode split from the EAC's Election "
                    "Administration and Voting Survey. 'early_total' is mail plus "
                    "early in person; 'other' is what the named modes leave over, "
                    "mostly provisional."),
           "sources": [s["url"] for s in SOURCES],
           "states": states}
    OUT.write_text(json.dumps(doc, indent=1) + "\n")
    # County file keyed on the last completed MIDTERM, which is the comparison a
    # midterm wants; 2024 is kept alongside it.
    (DATA / "eavs-counties.json").write_text(json.dumps(
        {"note": "Early vote (mail + early in person) per county, from the EAC survey.",
         "basis_year": "2022",
         "states": all_cty.get("2022", {}),
         "by_year": all_cty}, indent=1) + "\n")
    yrs = sorted({y for v in states.values() for y in v})
    print(f"eavs: {len(states)} jurisdictions, years {yrs}")
    for st in ("GA", "OH", "MI", "KS", "NE"):
        if st in states:
            for y in sorted(states[st]):
                v = states[st][y]
                print(f"   {st} {y}: total {v['total_ballots']:>10,}  early "
                      f"{v['early_total']:>10,} ({100*v['early_total']/max(v['total_ballots'],1):4.1f}%)"
                      f"  election day {v['election_day']:>10,}")
    print(f"   -> {OUT.name}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv) or 0)
    except Exception as e:
        print(f"EAVS FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
