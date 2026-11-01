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


# Total ballots counted, every state, every general since 2014. The Lab publishes one
# turnout file per cycle behind its turnout pages; the schema is identical across all
# six (STATE_ABV, TOTAL_BALLOTS_COUNTED), and the 2022 figures match the turn_2022
# column carried in the early-vote national file exactly, so the two agree.
#
# This is the denominator for every bar on every card. Without it only the handful of
# states whose results collector takes a year could show an election-day figure.
TURNOUT_BASE = ("https://election.lab.ufl.edu/data-downloads/turnoutdata/"
                "Turnout_{year}G_{ver}.csv")
TURNOUT_FILES = {"2024": "v0.4", "2022": "v1.0", "2020": "v1.0",
                 "2018": "v1.0", "2016": "v1.0", "2014": "v1.0"}
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}


def turnout_by_year():
    """{year -> {state -> total ballots counted}}."""
    import csv, io, urllib.request
    out = {}
    for year, ver in TURNOUT_FILES.items():
        url = TURNOUT_BASE.format(year=year, ver=ver)
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
            st = (row.get("STATE_ABV") or "").strip()
            raw = (row.get("TOTAL_BALLOTS_COUNTED") or "").replace(",", "").strip()
            try:
                v = int(float(raw))
            except ValueError:
                continue
            if st and st != "US" and v:
                got[st] = v
        if got:
            out[year] = got
    return out


# North Carolina publishes every contest split by mode AND by party, so a completed
# cycle there gives a COUNTED early share with a partisan breakdown - the only state
# where both are available for a past election. Its file layout changed after 2022, so
# only 2024 onward parses.
NC_PRIOR = {"2024": ("2024_11_05", "20241105", ("US PRESIDENT", "NC GOVERNOR"))}
NC_MODES = ["Election Day", "Early Voting", "Absentee by Mail", "Provisional"]


def nc_prior(year):
    import csv, io, zipfile, urllib.request, collections
    tag, stamp, contests = NC_PRIOR[year]
    url = f"https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/{tag}/results_pct_{stamp}.zip"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
        blob = r.read()
    z = zipfile.ZipFile(io.BytesIO(blob))
    rows = list(csv.DictReader(
        io.StringIO(z.read(z.namelist()[0]).decode("utf-8", "ignore")), delimiter="\t"))
    def num(v):
        try:
            return int(str(v).replace(",", "").strip() or 0)
        except ValueError:
            return 0
    out = {}
    for contest in contests:
        modes = collections.Counter()
        party = collections.defaultdict(collections.Counter)
        for row in rows:
            if row.get("Contest Name") != contest:
                continue
            pk = (row.get("Choice Party") or "").strip() or "OTH"
            for m in NC_MODES:
                v = num(row.get(m))
                modes[m] += v
                party[pk][m] += v
        tot = sum(modes.values())
        if not tot:
            continue
        eday = modes.get("Election Day", 0)
        out[contest] = {
            "total": tot, "election_day": eday, "early": tot - eday,
            "early_pct": (tot - eday) / tot,
            "by_mode": dict(modes),
            "by_party": {pk: {"total": sum(mm.values()),
                              "election_day": mm.get("Election Day", 0),
                              "early": sum(mm.values()) - mm.get("Election Day", 0),
                              "early_pct": (sum(mm.values()) - mm.get("Election Day", 0))
                                           / max(sum(mm.values()), 1)}
                         for pk, mm in party.items() if sum(mm.values())},
        }
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
    ep = DATA / "eavs.json"
    eavs = (json.loads(ep.read_text()).get("states") or {}) if ep.exists() else {}
    if not eavs:
        print("  (no eavs.json — run eavs.py; falling back to the turnout columns)",
              file=sys.stderr)
    states = {}
    for st in sorted(set(list(PRIOR) + [p.name[11:-5] for p in DATA.glob("ev-history-*.json")])):
        hist = ev_history(st)
        row = {"ev_history": hist}
        # Election day is what is left when the early vote is taken off the turnout. It
        # only exists for a year where BOTH are known, and is never inferred from a
        # neighbouring cycle.
        split = {}
        # EAVS first: the EAC's survey carries a MEASURED mode split for every state and
        # every cycle, where the cast-based figure is only ballots received. It is also
        # the only source that covers Georgia, Kansas, Michigan, Nebraska and Ohio before
        # 2024 at all.
        for yr, cell in (eavs.get(st) or {}).items():
            tv, ev = cell.get("total_ballots"), cell.get("early_total")
            if tv and ev is not None:
                split[yr] = {"total_vote": tv, "early": ev,
                             "election_day": cell.get("election_day"),
                             "mail": cell.get("mail"),
                             "early_in_person": cell.get("early_in_person"),
                             "other": cell.get("other"),
                             "early_pct": ev / tv, "basis": "EAVS"}
        # Then the turnout column, for any cycle EAVS does not cover (it starts at 2018,
        # and Minnesota's card goes back to 2014).
        for yr, totals in turn.items():
            if yr in split:
                continue
            tv, ev = totals.get(st), (hist.get(yr) or {}).get("cast")
            if tv and ev is not None:
                split[yr] = {"total_vote": tv, "early": ev, "election_day": tv - ev,
                             "early_pct": ev / tv, "basis": "cast"}
        if split:
            row["by_year"] = split
        if st == "NC":
            for yr in NC_PRIOR:
                try:
                    got = nc_prior(yr)
                except Exception as e:
                    row.setdefault("notes", {})[yr] = f"{type(e).__name__}: {e}"
                    continue
                if not got:
                    continue
                row.setdefault("counted_by_contest", {})[yr] = got
                first = list(got.values())[0]
                # A counted figure replaces a cast one for the same year: it is the
                # measured early vote rather than ballots received.
                row.setdefault("by_year", {})[yr] = {
                    "total_vote": first["total"], "early": first["early"],
                    "election_day": first["election_day"],
                    "early_pct": first["early_pct"], "basis": "counted"}
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
