#!/usr/bin/env python3
"""Early vote as a share of the TOTAL vote, for prior cycles -> data/ev-share.json

Two numbers are needed and they come from different places.

The denominator - total votes cast - is not in the early-vote files at all. Those carry
`registered`, never turnout. It has to come from a prior year's ELECTION-NIGHT feed,
which is why only the states whose results collector can be pointed at an old election
can be measured directly.

The numerator depends on whether the state's results feed labels the mode:

  labelled   TX publishes EV alongside V per candidate per county; North Carolina and
             the Clarity states (GA, IA, SC) carry a VoteType per choice. For these the
             early vote is a measured figure at every report, and the share is exact.
  unlabelled FL and OH report one total per contest. Their share has to use the
             early-vote file's "cast" figure as the numerator, which is a DIFFERENT
             quantity: ballots received, not ballots counted as early. Texas shows how
             far apart those can be - 7,699,516 cast against 9,075,933 counted early in
             2024 - so the two are reported separately and never silently mixed.

Party and race splits come from the early-vote side (ev-history-<ST>.json and
demographics-<ST>.json), because no results feed breaks a contest down that way. Only
six states carry a party split historically and only four carry race, so the breakdown
is reported where it exists and left out where it does not.
"""
import json, pathlib, sys

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"

# Prior elections each results collector can actually be pointed at. KS, ME, MN and NE
# take no year argument, so they cannot be measured until they run live.
PRIOR = {
    "TX": [("2024", "49664")],
    "FL": [("2024", "20241105")],
}
MAIL = ("by_mail", "mail_returned", "returned")
INPERSON = ("in_person", "early_in_person")


def _n(block, key):
    v = (block or {}).get(key)
    if isinstance(v, dict):
        v = v.get("total")
    return v if isinstance(v, (int, float)) else None


def _one(block, names):
    for k in names:
        v = _n(block, k)
        if v is not None:
            return v
    return None


def ev_history(st):
    """{year -> {total, mail, in_person, party:{...}}} from the early-vote side."""
    p = DATA / f"ev-history-{st}.json"
    if not p.exists():
        return {}
    out = {}
    for yr, blk in (json.loads(p.read_text()).get("years") or {}).items():
        s = blk.get("state_totals") or {}
        mail, ip = _one(s, MAIL), _one(s, INPERSON)
        if mail is None and ip is None:
            continue
        row = {"cast": (mail or 0) + (ip or 0), "mail": mail, "in_person": ip,
               "registered": s.get("registered")}
        # Party, only where the source carries it.
        party = {}
        for key in MAIL + INPERSON:
            cell = s.get(key)
            if isinstance(cell, dict):
                for pk in ("D", "R", "NPA", "O"):
                    if isinstance(cell.get(pk), (int, float)):
                        party[pk] = party.get(pk, 0) + cell[pk]
        if party:
            row["party"] = party
        out[yr] = row
    return out


def demographics(st):
    """{year -> {race counts}} where the state records race at registration."""
    p = DATA / f"demographics-{st}.json"
    if not p.exists():
        return {}
    out = {}
    for yr, blk in (json.loads(p.read_text()).get("years") or {}).items():
        race = (((blk.get("streams") or {}).get("voted") or {}).get("race") or {})
        if race.get("counts"):
            out[yr] = {"counts": race["counts"], "described": race.get("total")}
    return out


# The Lab keeps a turnout column in each cycle's own national file: the 2026 file
# carries turn_2022, the 2024 file carries turn_2020. Those two are the only turnout
# denominators that exist for every state - there is no 2020 or 2022 archive to pull an
# early-vote total from, so a year is only usable where BOTH numbers exist.
TURNOUT = [("2022", "https://election.lab.ufl.edu/data-downloads/earlyvote/2026/US.csv",
            "turn_2022"),
           ("2020", "https://election.lab.ufl.edu/data-downloads/earlyvote/2024/US.csv",
            "turn_2020")]
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}


def turnout_by_year():
    """{year -> {state -> total votes cast}} from the Lab's own turnout columns."""
    import csv, io, urllib.request
    out = {}
    for year, url, col in TURNOUT:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                        timeout=90) as r:
                text = r.read().decode("utf-8-sig", "ignore")
            if text.lstrip()[:1] == "<":
                continue
            rows = list(csv.DictReader(io.StringIO(text)))
        except Exception:
            continue
        got = {}
        for row in rows:
            st = (row.get("state_abbv") or "").strip()
            try:
                v = int(float(row.get(col) or 0))
            except ValueError:
                v = 0
            if st and v:
                got[st] = v
        if got:
            out[year] = got
    return out


def total_vote(st, eid):
    """Total votes and, where the feed labels it, the early vote counted."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    if st == "TX":
        import tx_results as M
        _p, tot, _c = M.build(eid, f"prior {eid}")
    elif st == "FL":
        import fl_results as M
        _p, tot, _c = M.build(eid)
    else:
        raise RuntimeError(f"no prior-year reader for {st}")
    out = {}
    for race, t in tot.items():
        out[race] = {"total": t.get("total"),
                     "early_counted": t.get("early_and_mail_counted"),
                     "early_cast_at_the_time": t.get("early_and_mail_cast"),
                     "precincts": [t.get("precincts_reporting"), t.get("precincts_total")]}
    return out


def main():
    turn = turnout_by_year()
    states = {}
    for st in sorted(set(list(PRIOR) + [p.name[11:-5] for p in DATA.glob("ev-history-*.json")])):
        hist = ev_history(st)
        row = {"ev_history": hist}
        # Election day is what is left when the early vote is taken off the turnout. It
        # only exists for a year where BOTH are known, and is never inferred from a
        # neighbouring cycle.
        split = {}
        for yr, totals in turn.items():
            tv, ev = totals.get(st), (hist.get(yr) or {}).get("cast")
            if tv and ev is not None:
                split[yr] = {"total_vote": tv, "early": ev, "election_day": tv - ev,
                             "early_pct": ev / tv, "basis": "cast"}
        if split:
            row["by_year"] = split
        demo = demographics(st)
        if demo:
            row["race"] = demo
        measured = {}
        for yr, eid in PRIOR.get(st, []):
            try:
                measured[yr] = total_vote(st, eid)
            except Exception as e:
                measured[yr] = {"error": f"{type(e).__name__}: {e}"}
        if measured:
            row["measured_total_vote"] = measured
            for yr, races in measured.items():
                if "error" in races:
                    continue
                first = list(races.values())[0]
                tv = first.get("total")
                ev = first.get("early_counted")
                basis = "counted"
                if ev is None:
                    # NOT early_cast_at_the_time. That field is produced by reading the
                    # CURRENT early-vote file, so on a prior-year run it carries today's
                    # numbers: Florida's 2024 row came out at 5,254,007, which is its 2026
                    # early vote, and Texas's at 7,699,516, also 2026. The early vote for
                    # that year is the one in the archive.
                    ev = (hist.get(yr) or {}).get("cast")
                    basis = "cast"
                if tv and ev is not None:
                    row.setdefault("by_year", {})[yr] = {
                        "total_vote": tv, "early": ev, "election_day": tv - ev,
                        "early_pct": ev / tv, "basis": basis}
        states[st] = row

    out = {"note": ("Early vote as a share of the total vote. The denominator comes "
                    "from a prior election-night feed, so only states whose results "
                    "collector takes a year can be measured; the rest carry their "
                    "early-vote history alone until they run live. Where a feed labels "
                    "the mode the early vote is COUNTED and exact; where it does not, "
                    "only ballots CAST are known, and the two are not the same figure."),
           "states": states}
    (DATA / "ev-share.json").write_text(json.dumps(out, indent=1) + "\n")

    print("EV share of total vote, where both numbers exist:")
    for st, row in sorted(states.items()):
        for yr, races in (row.get("measured_total_vote") or {}).items():
            if "error" in races:
                print(f"  {st} {yr}: {races['error']}")
                continue
            for race, r in races.items():
                tot = r["total"] or 0
                cnt, cast = r["early_counted"], r["early_cast_at_the_time"]
                if cnt:
                    print(f"  {st} {yr} {race}: total {tot:,} · early COUNTED {cnt:,} "
                          f"= {100*cnt/tot:.1f}%")
                if cast:
                    print(f"  {st} {yr} {race}: total {tot:,} · early CAST {cast:,} "
                          f"= {100*cast/tot:.1f}%"
                          + ("  (cast and counted differ — see note)" if cnt else ""))
    print(f"   -> ev-share.json")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as e:
        print(f"EV SHARE FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
