#!/usr/bin/env python3
"""Minnesota election-night results by county -> data/results-MN.json

Minnesota's results *web app* (electionresults.sos.mn.gov) sits behind Radware bot
management: plain requests are bounced to validate.perfdrive.com, and the challenge
URL echoes the client it fingerprinted back at you ("sst=curl/8.4.0"). That wall is
what made this state look unreachable.

The wall is only on the app. The app's own "Media Files" page links to a *separate*
host that is not protected at all:

    https://electionresultsfiles.sos.mn.gov/<YYYYMMDD>/allracesbycounty.txt

A browser was needed exactly once, to read that index and learn the paths. Fetching
the files afterwards is ordinary HTTP, so this collector needs no browser and runs on
the cron VM like the rest.

Layout of allracesbycounty.txt, 16 semicolon-separated fields, verified against
Cntytbl.txt on the 2020 file (1,044 statewide rows, zero precinct-total mismatches;
822 county/office/party groups, zero vote-sum mismatches):

    [1] county id      [3] office id   [4] office name    [6] candidate id
    [7] candidate      [10] party      [11] precincts reporting
    [12] precincts total  [13] votes   [14] pct           [15] office total in county

District contests ([4] contains "District") carry the precinct count of the part of
the county inside the district, not the whole county, so only statewide contests are
cross-checked against Cntytbl.

The 2026 directory is already live and carries the real 2026 field with zeroes, so a
reporting=0 answer means "not published yet", not a broken call.

Exit 2 means Minnesota has not published results yet. Any other problem raises and
writes nothing.
"""
import collections, itertools, json, pathlib, sys, urllib.request
from datetime import datetime, timezone
import early_cast as early_cast_shared
import election_day

HOST = "https://electionresultsfiles.sos.mn.gov"
ELECTION_DIR = "20261103"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept": "text/plain,*/*"}
# Minnesota names the governor's line for the ticket, and its Democrats are the DFL.
# Minnesota also elects a governor in 2026; this board does not track it.
WANT = {"senate": "U.S. Senator"}
# --proof against a past election: Minnesota's governor is elected in the midterm and
# its senators in the presidential years, so no single past general carries both lines
# in WANT. The 2024 general carries Senator plus President, which is the widest pair of
# statewide contests with real votes, so the proof run asks for those.
PROOF_WANT = {"senate": "U.S. Senator",
              "president": "U.S. President & Vice President"}
PARTY = {"DFL": "D", "R": "R", "GOP": "R"}
NFIELDS = 16


def get(name, timeout=90):
    url = f"{HOST}/{ELECTION_DIR}/{name}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError(f"{url}: HTTP {r.status}")
        body = r.read()
    text = body.decode("utf-8", "replace")
    if text.lstrip()[:1] == "<":
        raise RuntimeError(f"{url}: served HTML, not the data file — "
                           f"the files host is answering like the bot-walled app")
    return text


def counties_table():
    """county id -> (name, precincts in the whole county)."""
    out = {}
    for line in get("Cntytbl.txt").splitlines():
        p = line.rstrip().split(";")
        if len(p) >= 3 and p[0].strip():
            out[p[0]] = (p[1].strip(), int(p[2]))
    if len(out) != 87:
        raise RuntimeError(f"Cntytbl.txt listed {len(out)} counties, expected 87")
    return out


def rows():
    out = []
    for n, line in enumerate(get("allracesbycounty.txt").splitlines(), 1):
        if not line.strip():
            continue
        p = line.rstrip("\n").split(";")
        if len(p) != NFIELDS:
            raise RuntimeError(f"allracesbycounty.txt line {n}: {len(p)} fields, "
                               f"expected {NFIELDS} — layout changed")
        out.append(p)
    if not out:
        raise RuntimeError("allracesbycounty.txt was empty")
    return out


def early_cast():
    """Early + mail ballots cast per unit, from the shared reader.

    This was a local copy that added up every stream name it knew. Those names
    are aliases, so a payload carrying two for one stream had it counted twice -
    Florida writes both early_in_person and in_person and was over by 2,880,909,
    the whole in-person vote again. early_cast.by_unit takes one stream per mode.
    """
    return early_cast_shared.by_unit("MN", key=early_cast_shared.ckey)


def payload_stub(totals):
    return {"election": "2026 General",
            "source": f"{HOST}/{ELECTION_DIR}/allracesbycounty.txt"}


def build(want=None):
    """Read ELECTION_DIR and tally it. The live path and --proof both come through here.

    Lifted out of main() unchanged so a proof run can point ELECTION_DIR at a past
    election and go through exactly the same reader, cross-checks and tally the night
    uses — a second copy of this would only prove the copy.
    """
    want = want or WANT
    cty = counties_table()
    allrows = rows()
    cast, cast_as_of = early_cast()

    picked = {race: name for race, name in want.items()
              if any(r[4] == name for r in allrows)}
    missing = sorted(set(want) - set(picked))
    if missing:
        names = sorted({r[4] for r in allrows if "District" not in r[4]})
        raise RuntimeError(f"contest(s) {missing} not in the file; statewide names "
                           f"present: {names[:8]}")

    counties, totals, any_votes = {}, {}, False
    for race, office in picked.items():
        sel = [r for r in allrows if r[4] == office]
        tally, parties = collections.Counter(), {}
        st_rep = st_tot = 0
        for cid, group in itertools.groupby(sorted(sel, key=lambda r: r[1]),
                                              key=lambda r: r[1]):
            group = list(group)
            if cid not in cty:
                raise RuntimeError(f"county id {cid!r} not in Cntytbl.txt")
            name, pct_total = cty[cid]
            rep = int(group[0][11])
            tot = int(group[0][12])
            # Statewide contests cover every precinct in the county; a disagreement here
            # means the file's precinct basis changed, which would silently skew every
            # projection, so refuse rather than publish it.
            if tot != pct_total:
                raise RuntimeError(f"{office} in {name}: file says {tot} precincts, "
                                   f"Cntytbl.txt says {pct_total}")
            if rep > tot:
                raise RuntimeError(f"{office} in {name}: {rep} precincts reporting "
                                   f"of {tot}")
            choices = {}
            for r in group:
                cand = r[7].strip() or f"candidate {r[6]}"
                party = PARTY.get(r[10].strip().upper(), "O")
                votes = int(r[13])
                if cand in choices:
                    raise RuntimeError(f"{office} in {name}: {cand!r} listed twice")
                choices[cand] = {"party": party, "votes": votes}
                parties[cand] = party
                tally[cand] += votes
            counted = sum(c["votes"] for c in choices.values())
            if counted != int(group[0][15]):
                raise RuntimeError(f"{office} in {name}: candidate votes sum to "
                                   f"{counted}, file's office total is {group[0][15]}")
            if counted:
                any_votes = True
            st_rep += rep
            st_tot += tot
            rec = counties.setdefault(name, {"races": {}})
            rec["races"][race] = {
                "choices": dict(sorted(choices.items(), key=lambda x: -x[1]["votes"])),
                "counted": counted,
                "precincts_reporting": rep,
                "precincts_total": tot,
                "early_and_mail_cast": cast.get(early_cast_shared.ckey(name)),
            }
        totals[race] = {
            "contest_name": office,
            "choices": dict(tally.most_common()),
            "parties": parties,
            "total": sum(tally.values()),
            "precincts_reporting": st_rep,
            "precincts_total": st_tot,
            "early_and_mail_cast": sum(cast.values()) if cast else None,
        }
    return counties, totals, any_votes, cast_as_of


def main():
    # --proof <YYYYMMDD> runs the whole build against a PAST Minnesota election, where
    # the votes are real. Proving it against tonight's directory proves only that the
    # structure parses: every total is zero until polls close, so the vote-reading path
    # would be untested at the moment it matters. It returns before write_or_hold, so a
    # proof run never writes a results file.
    if "--proof" in sys.argv:
        global ELECTION_DIR
        i = sys.argv.index("--proof")
        if len(sys.argv) <= i + 1:
            raise RuntimeError("--proof needs an election directory, e.g. --proof 20241105")
        ELECTION_DIR = sys.argv[i + 1]
        counties, totals, any_votes, _ = build(PROOF_WANT)
        print(f"MN proof via {ELECTION_DIR}: {len(counties)} counties")
        for race, t in totals.items():
            print(f"   {race}: {t['total']:,} votes  no mode split (Minnesota folds "
                  f"absentee into the precinct)  precincts "
                  f"{t['precincts_reporting']:,}/{t['precincts_total']:,}")
            print(f"      contest {t['contest_name']!r}")
            for c, v in list(t["choices"].items())[:4]:
                print(f"      {c[:38]:40} {v:>10,}  {t['parties'].get(c)}")
            tie = sum(t["choices"].values())
            print(f"      candidate sum {tie:,} vs race total {t['total']:,} — "
                  f"{'TIES' if tie == t['total'] else 'DOES NOT TIE'}")
        big = sorted(counties.items(),
                     key=lambda x: -max(r["counted"] for r in x[1]["races"].values()))[:3]
        for nm, rec in big:
            r = list(rec["races"].values())[0]
            print(f"   {nm}: {r['counted']:,} counted, "
                  f"{r['precincts_reporting']}/{r['precincts_total']} precincts")
        return 0

    counties, totals, any_votes, cast_as_of = build()

    if not any_votes:
        # The ballot is known even though the votes are all zero, and the gate never
        # gets a chance to record it because this returns first.
        try:
            election_day.record_candidates("MN", payload_stub(totals), totals)
        except Exception:
            pass
        shown = ", ".join(f"{t['contest_name']} ({t['precincts_reporting']}/"
                          f"{t['precincts_total']} precincts)" for t in totals.values())
        print(f"MN: results not published yet — {ELECTION_DIR} carries the 2026 field "
              f"with zeroes: {shown}")
        return 2

    payload = {
        "state": "MN", "unit": "county", "source_kind": "mn-sos-media-files",
        "election": "2026 General", "election_dir": ELECTION_DIR,
        "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "early_cast_as_of": cast_as_of,
        "counties": counties, "state_totals": totals,
        "source": f"{HOST}/{ELECTION_DIR}/allracesbycounty.txt "
                  f"(+ Cntytbl.txt for the precinct cross-check)",
        "notes": {
            "modes": "Minnesota folds accepted absentee ballots into each precinct's own "
                     "result and publishes no early/election-day split, so the precinct "
                     "scaling stays off here unless a split appears.",
            "precincts": "Statewide precinct totals are checked against Cntytbl.txt every "
                         "run; district contests are excluded because their precinct count "
                         "covers only the part of the county inside the district.",
        },
    }
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "results-MN.json"
    rc = election_day.write_or_hold("MN", p, payload, totals)
    if rc:
        return rc
    for race, t in totals.items():
        print(f"MN {race}: {t['total']:,} counted across {len(counties)} counties "
              f"({t['precincts_reporting']:,}/{t['precincts_total']:,} precincts)")
    print(f"   -> {p.name}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as e:
        print(f"MN RESULTS FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
