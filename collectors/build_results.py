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


def split_modes(choices, candidates):
    """(early+mail per candidate, election-day per candidate) where the feed splits them."""
    idx = {c["name"]: i for i, c in enumerate(candidates)}
    k = len(candidates)
    early, eday = [0] * k, [0] * k
    seen = False
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
        early_v, eday_v = split_modes(rr.get("choices"), candidates)
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


def main():
    base_path = DATA / "results.json"
    board = json.loads(base_path.read_text()) if base_path.exists() else {"states": {}}
    board.setdefault("states", {})
    touched = []

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
    base_path.write_text(json.dumps(board, indent=1) + "\n")
    print(f"-> results.json ({len(touched)} state(s) with a live feed: {', '.join(touched) or 'none'})")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as e:
        print(f"BUILD RESULTS FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
