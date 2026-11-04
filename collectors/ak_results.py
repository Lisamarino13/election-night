#!/usr/bin/env python3
"""Alaska election-night results by House district -> data/results-AK.json

Alaska's Division of Elections publishes a single precinct-level CSV for the
live count, linked from the election-results page as "Summary (csv)":

    /enr/<eid>/results/GA_ENR_Precinct_State_of_Alaska.csv

where <eid> is 26GENR for tonight. It is the best feed on this board: one row
per precinct per candidate, 444 precincts, with the vote split five ways -
Election Day, Absentee, Early Voting, Question and Remote - so no mode has to
be inferred. Reg_voters and Reporting_flag come per precinct, so the reporting
denominator is the state's own.

Three things about Alaska that a collector has to get right:

  * THERE ARE TWO SULLIVANS ON THE SENATE BALLOT. "Sullivan, Dan S." (REP) is
    the incumbent; "Sullivan, Daniel J. Jr." has no party and is a different
    person. In the 2026 primary they drew 68,726 and 4,107 votes. Any match on
    the substring "Sullivan" silently inflates the incumbent by about 6%, so
    candidates are keyed on the FULL candidate_name and never on a fragment.

  * Alaska counts by ranked choice. This file is Round 1 first choices only -
    it is what the state itself publishes on the night, and it is not the
    final result in any race where nobody clears 50%. The payload says so.

  * Precincts are reported, districts are what people read. Pct_Id is
    "01-600", so the first two characters are the House district; the board
    renders 40 districts and keeps the precinct counts underneath.

Proof: --proof 26PRIM runs the whole path against the 2026 primary, where the
votes are real. Proving it against tonight's feed proves only that the file
parses - every total is zero until polls close, so the vote-reading path would
be untested at the moment it matters. The division does not keep the earlier
generals at this path (24GENR and 22GENR are 404), so the primary is the most
recent election with real counts behind it.
"""
import collections, csv, io, pathlib, re, sys, urllib.request
from datetime import datetime, timezone

import early_cast as early_cast_shared
import election_day

BASE = "https://www.elections.alaska.gov/enr"
EID = "26GENR"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}

# Contest_title is exact in this file, so these are equality matches rather than
# patterns - a loose pattern would pull in "Supreme Court" retention questions.
# Alaska also elects a governor in 2026; this board does not track it.
WANT = {"senate": "U.S. Senator"}
PARTY = {"REP": "R", "DEM": "D", "UNA": "I", "NON": "I", "AIP": "O", "LIB": "O", "GRN": "O"}

# The five columns the file splits the vote into, folded into what the board reasons
# about. Every one is listed: a mode left out is votes that vanish, so the build
# asserts the three it produces add back to total_votes.
EARLY_MODES = ("Absentee", "Early Voting", "Remote")
EDAY_MODES = ("Election Day",)
PROV_MODES = ("Question",)


def get(url, timeout=180):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def load(eid):
    raw = get(f"{BASE}/{eid}/results/GA_ENR_Precinct_State_of_Alaska.csv")
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    if len(rows) < 1000:
        raise RuntimeError(f"{eid}: only {len(rows)} rows — refusing, the file is short")
    return rows


def early_cast():
    return early_cast_shared.by_unit("AK", key=early_cast_shared.ckey)


def num(v):
    return int(v or 0)


def district_of(r):
    """(district code, precinct id or None). Raises rather than dropping a row.

    Most rows carry Pct_Id "01-600", where the first two characters are the House
    district. Early-voting and questioned ballots do NOT: they are reported per
    district with an empty Pct_Id and the district in the name, as
    "District 7 - Early Voting". In the 2026 primary those rows held 27,508 early
    and 5,021 questioned votes - 20% of the Senate total - so a collector that
    skips them reports four fifths of Alaska and an early vote of zero.
    """
    pct = (r.get("Pct_Id") or "").strip()
    if pct:
        return pct.split("-")[0], pct
    m = re.match(r"\s*District\s+(\d+)\s*-", r.get("Precinct_name") or "")
    if m:
        return "%02d" % int(m.group(1)), None
    raise RuntimeError(f"row has no precinct and no district in its name: "
                       f"{(r.get('Precinct_name') or '')!r}")


def build(eid=EID):
    rows = load(eid)
    found = {}
    for race, title in WANT.items():
        if any(r["Contest_title"] == title for r in rows):
            found[race] = title
    if not found:
        raise RuntimeError(f"none of {sorted(WANT)} found among this file's contests")

    cast, cast_as_of = early_cast()
    districts = {}
    state = collections.defaultdict(
        lambda: {"choices": collections.Counter(), "early": collections.Counter(),
                 "eday": collections.Counter(), "prov": collections.Counter(),
                 "parties": {}})
    # precinct -> (district, reporting, registered); one precinct appears on many rows
    seen_pct = {}

    for r in rows:
        race = next((k for k, t in found.items() if r["Contest_title"] == t), None)
        if race is None:
            continue
        dist, pct = district_of(r)
        if pct is not None and pct not in seen_pct:
            seen_pct[pct] = (dist, r.get("Reporting_flag") == "1", num(r.get("Reg_voters")))
        # The full name, never a fragment: two different Sullivans are on this ballot.
        who = (r.get("candidate_name") or "").strip()
        if not who:
            continue
        e = sum(num(r.get(f"{m}_votes")) for m in EARLY_MODES)
        d = sum(num(r.get(f"{m}_votes")) for m in EDAY_MODES)
        p = sum(num(r.get(f"{m}_votes")) for m in PROV_MODES)
        tv = num(r.get("total_votes"))
        if e + d + p != tv:
            raise RuntimeError(f"{pct} {who}: modes {e}+{d}+{p} != total_votes {tv} — "
                               f"this file has a mode column we are not reading")
        rec = districts.setdefault(dist, {
            "name": ("Federal overseas absentee" if dist == "99"
                     else f"House District {int(dist)}"), "district": dist,
            "registered": 0, "precincts_reporting": 0, "precincts_total": 0, "races": {}})
        rr = rec["races"].setdefault(race, {
            "choices": collections.Counter(), "early": collections.Counter(),
            "eday": collections.Counter(), "prov": collections.Counter()})
        rr["choices"][who] += tv
        rr["early"][who] += e
        rr["eday"][who] += d
        rr["prov"][who] += p
        s = state[race]
        s["choices"][who] += tv
        s["early"][who] += e
        s["eday"][who] += d
        s["prov"][who] += p
        s["parties"].setdefault(who, PARTY.get((r.get("Party_Code") or "").strip().upper(), "O"))

    for pct, (dist, reporting, reg) in seen_pct.items():
        rec = districts.get(dist)
        if rec is None:
            continue
        rec["precincts_total"] += 1
        rec["precincts_reporting"] += 1 if reporting else 0
        rec["registered"] += reg

    counties, pr_in, pr_all = {}, 0, 0
    for dist, rec in sorted(districts.items()):
        pr_in += rec["precincts_reporting"]
        pr_all += rec["precincts_total"]
        out = {"district": rec["district"], "registered": rec["registered"],
               "precincts_reporting": rec["precincts_reporting"],
               "precincts_total": rec["precincts_total"], "races": {}}
        for race, rr in rec["races"].items():
            counted = sum(rr["choices"].values())
            ce = sum(rr["early"].values())
            out["races"][race] = {
                "counted": counted,
                "choices": dict(rr["choices"].most_common()),
                "choices_by_mode": {
                    who: {"early": rr["early"].get(who, 0),
                          "election_day": rr["eday"].get(who, 0),
                          "provisional": rr["prov"].get(who, 0)}
                    for who in rr["choices"]},
                "early_and_mail_counted": ce,
                "precincts_reporting": rec["precincts_reporting"],
                "precincts_total": rec["precincts_total"],
            }
        counties[rec["name"]] = out

    cast_tot = sum(cast.values()) if cast else None
    totals = {}
    for race, s in state.items():
        total = sum(s["choices"].values())
        ce = sum(s["early"].values())
        totals[race] = {
            "contest_name": found.get(race),
            "choices": dict(s["choices"].most_common()),
            "parties": dict(s["parties"]),
            "total": total,
            "modes": {"early": ce,
                      "election_day": sum(s["eday"].values()),
                      "provisional": sum(s["prov"].values())},
            "choices_by_mode": {
                who: {"early": s["early"].get(who, 0),
                      "election_day": s["eday"].get(who, 0),
                      "provisional": s["prov"].get(who, 0)}
                for who in s["choices"]},
            "precincts_reporting": pr_in, "precincts_total": pr_all,
            "early_and_mail_cast": cast_tot, "early_and_mail_counted": ce,
            "early_and_mail_left": (max(0, cast_tot - ce) if cast_tot is not None else None),
        }
        if sum(totals[race]["modes"].values()) != total:
            raise RuntimeError(f"{race}: modes do not sum to the total")

    payload = {
        "state": "AK", "unit": "district", "source_kind": "alaska-enr",
        "election": f"Alaska {eid}", "election_date": eid,
        "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "early_cast_as_of": cast_as_of,
        "counties": counties, "state_totals": totals,
        "source": f"{BASE}/{eid}/results/GA_ENR_Precinct_State_of_Alaska.csv",
        "notes": {
            "rcv": "Alaska counts by ranked choice. These are Round 1 first choices, "
                   "which is what the state publishes on the night; in any race where "
                   "nobody clears 50% they are not the final result.",
            "modes": "Alaska splits every precinct five ways. Absentee, early voting and "
                     "remote are folded into 'early', election day stands alone, and "
                     "questioned ballots are carried as 'provisional' — no mode is "
                     "dropped and the three are checked against the state's own total.",
            "names": "Candidates are keyed on the full name. Two different Sullivans are "
                     "on the Senate ballot and a substring match would merge them.",
            "units": "Rows are precincts; they are summed into the 40 House districts, "
                     "with the precinct counts kept underneath.",
        },
    }
    return payload, totals, counties


def main():
    if "--proof" in sys.argv:
        i = sys.argv.index("--proof")
        eid = sys.argv[i + 1] if len(sys.argv) > i + 1 else "26PRIM"
        payload, totals, counties = build(eid)
        print(f"AK proof via {eid}: {len(counties)} House districts, "
              f"{list(totals.values())[0]['precincts_total']} precincts")
        for race, t in totals.items():
            m = t["modes"]
            print(f"   {race} ({t['contest_name']}): {t['total']:,} votes  "
                  f"early {m['early']:,}  election-day {m['election_day']:,}  "
                  f"provisional {m['provisional']:,}  "
                  f"[sums to {sum(m.values()):,}]")
            for c, v in list(t["choices"].items())[:5]:
                print(f"      {c[:34]:36} {t['parties'].get(c, '?'):2} {v:>9,}")
        return 0

    payload, totals, counties = build()
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "results-AK.json"
    rc = election_day.write_or_hold("AK", p, payload, totals)
    if rc == 0:
        for race, t in totals.items():
            print(f"AK {race}: {t['total']:,} votes, "
                  f"{t['precincts_reporting']}/{t['precincts_total']} precincts")
    return rc


if __name__ == "__main__":
    sys.exit(main())
