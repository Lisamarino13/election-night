#!/usr/bin/env python3
"""Fold every data/results-<ST>.json into the board's data/results.json.

The board's projection takes, per race, a list of counties as

    {"name": .., "votes": [per candidate], "outstanding": N or null}

and applies each county's own counted vote share to that county's own outstanding
ballots. The whole value of the method is in WHERE the remaining vote sits, so the
outstanding figure has to mean something precise.

What goes into `outstanding` is only what is MEASURED:

    early and mail ballots cast in that county but not yet counted
      + mail ballots the state reports as still outstanding
      + provisionals / UOCAVA the state reports as outstanding

Election-day ballots still to come are NOT in it. Nobody knows how many people will
turn out until they do, and multiplying precincts-not-yet-reporting by an average
would be a forecast wearing the costume of a measurement. So `outstanding` is a FLOOR,
not the whole remainder, and every race carries precincts reporting alongside it so the
board can say plainly that election-day votes from N precincts are still to come on top.

A state with no result feed keeps whatever was already on the board rather than being
blanked, and a county with nothing measurable gets null - never 0, because 0 reads as
"nothing left" and would make a projection look certain.
"""
import json, pathlib, sys, glob, os, collections
from datetime import datetime, timezone

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
# how a candidate's party is spelled across the feeds
PARTY_OK = {"D", "R", "O"}


def party_of(name, hint):
    p = (hint or "O").strip().upper()
    return p if p in PARTY_OK else "O"


EARLY_KEYS = ("Early Voting", "Absentee by Mail", "early", "mail")
EDAY_KEYS = ("Election Day", "Provisional", "election_day", "provisional")


def split_modes(choices, candidates, by_mode_race=None):
    """(early+mail per candidate, election-day per candidate) where the split is known.

    Two shapes arrive here. North Carolina and Clarity put a by_mode dict on each
    choice. Ohio cannot - its feed has no per-contest mode split - so its collector
    reconstructs one by subtracting a banked early-vote baseline, and hands it over as
    by_mode_race. Either way the election-day figure that leaves this function contains
    no early ballots, which is the only thing the precinct scaling requires.
    """
    idx = {c["name"]: i for i, c in enumerate(candidates)}
    k = len(candidates)
    early, eday = [0] * k, [0] * k
    seen = False
    if isinstance(by_mode_race, dict) and by_mode_race:
        for name, v in by_mode_race.items():
            i = idx.get(name)
            if i is None or not isinstance(v, dict):
                continue
            seen = True
            early[i] += v.get("early") or 0
            eday[i] += v.get("election_day") or 0
        if seen:
            return early, eday
    for name, v in (choices or {}).items():
        i = idx.get(name)
        if i is None or not isinstance(v, dict):
            continue
        bm = v.get("by_mode")
        if not isinstance(bm, dict):
            continue
        seen = True
        for m, n in bm.items():
            if m in EARLY_KEYS:
                early[i] += n or 0
            elif m in EDAY_KEYS:
                eday[i] += n or 0
    return (early, eday) if seen else (None, None)


def county_rows(race_block, counties, candidates):
    """[{name, votes[], outstanding, remainder[]}] in the order the board will draw.

    `remainder` is the part that matters. Testing the method against North Carolina
    2024 showed the SIZE of the remainder matters far less than the vote share you
    spend it at: spending it at a county's blended share (early plus election day
    together) was off by 70,000 votes at the halfway mark, while spending the
    election-day part at the county's ELECTION-DAY share was within 3,000. So the
    remainder is carried as components, each with the share vector it should be spent
    at, rather than as one number.
    """
    idx = {c["name"]: i for i, c in enumerate(candidates)}
    rows = []
    for cty, rec in sorted(counties.items()):
        r = (rec.get("races") or {}).get(race_block) if "races" in rec else rec.get(race_block)
        if r is None:
            continue
        votes = [0] * len(candidates)
        choices = r.get("choices") if isinstance(r, dict) and "choices" in r else r
        if isinstance(choices, dict):
            for name, v in choices.items():
                i = idx.get(name)
                if i is not None:
                    votes[i] += (v if isinstance(v, int) else (v or {}).get("votes", 0)) or 0
        rr = r if isinstance(r, dict) else {}
        early_v, eday_v = split_modes(rr.get("choices"), candidates,
                                      (rec.get("by_mode_races") or {}).get(race_block))
        norm = lambda a: (sum(a) and [x / sum(a) for x in a]) or None

        remainder = []
        # 1. ballots already cast early or by mail and not yet counted, plus any
        #    outstanding mail / provisional / UOCAVA the state publishes. Measured.
        measured = 0
        for key in ("early_and_mail_left", "mail_outstanding",
                    "outstanding_provisional", "outstanding_uocava"):
            v = rr.get(key)
            if v is None:
                v = rec.get(key)
            if isinstance(v, int):
                measured += v
        if measured:
            remainder.append({"n": measured, "basis": "measured",
                              "share": norm(early_v) if early_v else None})
        # 2. election-day ballots from precincts not yet reporting, scaled from what
        #    the reporting precincts have already produced. An estimate, and labelled
        #    one - it cannot be made at all until some precinct has reported.
        pr = rr.get("precincts_reporting") or rec.get("precincts_reporting") or 0
        pt = rr.get("precincts_total") or rec.get("precincts_total") or 0
        if pr and pt and pt > pr and eday_v and sum(eday_v):
            est = round(sum(eday_v) * (pt - pr) / pr)
            if est:
                remainder.append({"n": est, "basis": "scaled from precincts reporting",
                                  "share": norm(eday_v)})
        out = sum(c["n"] for c in remainder) if remainder else None
        rows.append({"name": cty, "votes": votes, "outstanding": out,
                     "remainder": remainder or None,
                     "precincts_reporting": pr or None, "precincts_total": pt or None})
    return rows


def candidates_for(state_totals_race):
    names = list((state_totals_race.get("choices") or {}).keys())
    parties = state_totals_race.get("parties") or {}
    out = []
    for nm in names:
        out.append({"name": nm, "party": party_of(nm, parties.get(nm))})
    return out


# Races this board does not follow. Alaska, Minnesota and Kansas all elect a governor
# in 2026 and all three publish one, so every source offers it - and this build only
# ever ADDS to the board it starts from, which made deleting them from results.json
# useless: the next run put them straight back. Dropping them by name at the end is
# the only thing that sticks.
NOT_TRACKED = {("AK", "governor"), ("MN", "governor"), ("KS", "governor")}


def refresh_eday_caps(data_dir):
    """Keep eday-caps.json's early-vote figure in step with the early-vote files.

    `ev` was written once by hand and never updated, while data/early-<ST>.json is
    refreshed every cycle. By 01:25Z on election night six states had drifted - Michigan
    by 454,434 ballots, South Carolina by 99,878, Ohio by 75,687 - and every figure the
    board derives from `ev` was wrong with them: percent outstanding, left-to-count, and
    the Election Day pool the need-to-win margin is divided by. Ohio's own outstanding
    count had grown LARGER than the remaining ceiling computed off its stale `ev`, which
    zeroed its Election Day pool entirely.

    The early-vote file is the count; the cap file should follow it, not lead it.
    """
    caps_path = data_dir / "eday-caps.json"
    if not caps_path.exists():
        return
    caps = json.loads(caps_path.read_text())
    moved = []
    for st, rec in caps.items():
        ev_path = data_dir / f"early-{st}.json"
        if not ev_path.exists():
            continue
        try:
            actual = (json.loads(ev_path.read_text()).get("state_totals") or {}).get("total")
        except Exception:
            continue
        if not isinstance(actual, int) or actual <= 0:
            continue
        if abs(actual - (rec.get("ev") or 0)) < 1:
            continue
        moved.append(f"{st} {rec.get('ev', 0):,}->{actual:,}")
        rec["ev"] = actual
        cap = rec.get("eday_cap") or 0
        rec["turnout"] = actual + cap
        rec["banked_pct"] = round(actual / (actual + cap) * 100, 1) if (actual + cap) else None
    if moved:
        caps_path.write_text(json.dumps(caps, indent=1) + "\n")
        print("  eday-caps refreshed from the early-vote files: " + "; ".join(moved))


def main():
    base_path = DATA / "results.json"
    board = json.loads(base_path.read_text()) if base_path.exists() else {"states": {}}
    board.setdefault("states", {})
    touched = []

    # Who is on the ballot, before anyone has a result. Every collector already writes
    # data/candidates-<ST>.json via election_day.record_candidates when it refuses to
    # publish figures, so the roster is known days early - but nothing read those files,
    # which is why the board showed "Candidate 1 / Candidate 2" for ten of thirteen
    # states. A real result below overwrites this, so it only ever fills a gap.
    rostered = []
    for f in sorted(glob.glob(str(DATA / "candidates-*.json"))):
        st = os.path.basename(f)[len("candidates-"):-len(".json")]
        entry = board["states"].get(st)
        if entry is None:
            continue
        doc = json.loads(pathlib.Path(f).read_text())
        entry.setdefault("races", {})
        for race, r in (doc.get("races") or {}).items():
            names = [c for c in (r.get("candidates") or []) if c.get("name")]
            if not names:
                continue
            blk = entry["races"].setdefault(race, {})
            if blk.get("counted"):
                continue        # real results already here; never overwrite them
            # Put the Republican first and the Democrat second, as the board's columns
            # assume, and keep everyone else in the order the state listed them.
            order = {"R": 0, "REP": 0, "D": 1, "DEM": 1}
            blk["candidates"] = sorted(
                [{"name": c["name"], "party": c.get("party") or "O"} for c in names],
                key=lambda c: order.get((c["party"] or "").upper(), 2))
            blk.setdefault("counties", [])
            blk["roster_only"] = True
            blk["roster_source"] = doc.get("source")
        rostered.append(st)
    if rostered:
        print(f"  ballot rosters folded in for {', '.join(rostered)}")

    for f in sorted(glob.glob(str(DATA / "results-*.json"))):
        st = os.path.basename(f)[len("results-"):-len(".json")]
        d = json.loads(pathlib.Path(f).read_text())
        entry = board["states"].get(st)
        if entry is None:
            print(f"  {st}: not a state this board tracks - skipped")
            continue
        counties = d.get("counties") or {}
        totals = d.get("state_totals") or {}
        if not totals:
            print(f"  {st}: feed carries no contest yet")
            continue
        entry.setdefault("races", {})
        for race, tot in totals.items():
            cands = candidates_for(tot)
            if not cands:
                continue
            rows = county_rows(race, counties, cands)
            blk = entry["races"].setdefault(race, {})
            blk["candidates"] = cands
            blk["counties"] = rows
            blk["updated"] = d.get("fetched")
            blk["precincts_reporting"] = tot.get("precincts_reporting")
            blk["precincts_total"] = tot.get("precincts_total")
            # what the outstanding figure does and does not include, carried with it
            blk["outstanding_basis"] = ("measured early and mail not yet counted, plus any "
                                        "outstanding mail, provisional and UOCAVA the state "
                                        "publishes, plus election-day ballots from precincts "
                                        "not yet reporting, scaled from what the reporting "
                                        "precincts produced. Each part is spent at the vote "
                                        "share of its OWN mode.")
            blk["is_test_data"] = bool(d.get("is_test_data"))
            blk["counted"] = tot.get("total")
            blk["modes"] = tot.get("modes")
            # Carried only where the state publishes it per candidate. Texas does (EV
            # beside V per candidate per county), which is what lets the Texas tab read
            # the early-vote MARGIN rather than just the early-vote share.
            if tot.get("choices_by_mode"):
                blk["choices_by_mode"] = tot["choices_by_mode"]
            blk.pop("roster_only", None)     # real figures supersede the ballot roster
            blk.pop("roster_source", None)
        entry["source"] = d.get("source")
        entry["updated"] = d.get("fetched")
        touched.append(st)
        measured = sum(1 for race in totals
                       for r in county_rows(race, counties, candidates_for(totals[race]))
                       if r["outstanding"] is not None)
        print(f"  {st}: {len(counties)} counties, races {sorted(totals)}, "
              f"{measured} county rows with a measured remainder"
              f"{'  [TEST DATA]' if d.get('is_test_data') else ''}")

    board["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    board["note"] = ("Projections apply each county's own counted vote share to that "
                     "county's own outstanding ballots. Outstanding counts only ballots "
                     "already cast and not yet counted - election-day turnout that has "
                     "not happened is not in it, so it is a floor.")
    for st, race in NOT_TRACKED:
        ent = board["states"].get(st) or {}
        if (ent.get("races") or {}).pop(race, None) is not None:
            print(f"  {st}: dropped {race} - not a race this board follows")
    refresh_eday_caps(base_path.parent)
    base_path.write_text(json.dumps(board, indent=1) + "\n")
    print(f"-> results.json ({len(touched)} state(s) with a live feed: {', '.join(touched) or 'none'})")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as e:
        print(f"BUILD RESULTS FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
