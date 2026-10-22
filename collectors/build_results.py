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


def county_rows(race_block, counties, candidates):
    """[{name, votes[], outstanding}] in the candidate order the board will draw."""
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
        # the measured remainder for this county, never 0-for-unknown
        parts = []
        for key in ("early_and_mail_left", "mail_outstanding",
                    "outstanding_provisional", "outstanding_uocava"):
            v = (r if isinstance(r, dict) else {}).get(key)
            if v is None:
                v = rec.get(key)
            if isinstance(v, int):
                parts.append(v)
        out = sum(parts) if parts else None
        rows.append({"name": cty, "votes": votes, "outstanding": out})
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
                                        "publishes. Election-day ballots still to come are "
                                        "NOT included.")
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
