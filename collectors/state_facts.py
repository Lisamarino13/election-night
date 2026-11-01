#!/usr/bin/env python3
"""Per-state facts the board needs on the night -> data/state-facts.json

Three things that are not in any feed.

WHEN in-person early voting ends. Not derivable from our own data: every state's
in-person figure was still rising at its last observation even where voting had closed,
because the final day's returns post afterwards. Texas closed on the 30th and its
reported in-person was still climbing on the 1st. So the window is recorded from
Ballotpedia's 2026 table and CHECKED against our series - an observation after the
stated close is reporting lag and is expected; an observation before it would mean the
date is wrong.

WHETHER the state's results feed lets early votes be told apart. This decides whether
the precinct scaling can run at all, and it is read off what each collector had to do
rather than from lore:

  labelled    the feed carries a mode per choice, so early votes are identifiable at
              every report and the order they arrive in does not matter.
  early first the feed carries ONE total per contest, and the collector banks a
              baseline while no election-day precinct has yet reported. That only works
              because the state posts early votes first, and it was built against the
              real feed.
  no split    neither. The early share cannot be separated from the feed at all.

WHO is on the ballot. Written by election_day.record_candidates as a side effect of the
collectors refusing to publish results: the ballot is known days early even though the
figures are withheld.
"""
import json, pathlib, sys
from datetime import date

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"

# In-person early voting window for the 2026 general.
# Source: ballotpedia.org/Early_voting_dates,_2026 (read 2026-11-01).
EV_WINDOW = {
    "AK": ("2026-10-19", "2026-11-03"),   # runs through election day itself
    "FL": ("2026-10-24", "2026-10-31"),
    "GA": ("2026-10-13", "2026-10-30"),
    "IA": ("2026-10-14", "2026-11-02"),
    "KS": ("2026-10-14", "2026-11-02"),
    "ME": ("2026-10-05", "2026-10-29"),
    "MI": ("2026-10-24", "2026-11-01"),
    "MN": ("2026-09-18", "2026-11-02"),
    "NC": ("2026-10-15", "2026-10-31"),   # closes 3pm
    "NE": ("2026-10-05", "2026-11-02"),
    "OH": ("2026-10-06", "2026-11-01"),
    "SC": ("2026-10-19", "2026-10-31"),
    "TX": ("2026-10-19", "2026-10-30"),
}

# How the results feed treats modes, from what each collector had to do against it.
COUNT_ORDER = {
    "TX": ("labelled", "publishes EV beside V per candidate per county"),
    "NC": ("labelled", "every contest split by mode in results_pct"),
    "GA": ("labelled", "Clarity VoteType per choice"),
    "IA": ("labelled", "Clarity VoteType per choice"),
    "SC": ("labelled", "Clarity VoteType per choice"),
    "FL": ("early first", "one total per contest; the collector banks a baseline while "
                          "no election-day precinct has reported"),
    "OH": ("early first", "one total per county; the collector banks a baseline while "
                          "no election-day precinct has reported"),
    "KS": ("no split", "county pages carry no early/election-day split"),
    "ME": ("no split", "result files carry no early/election-day split"),
    "MN": ("no split", "absentee ballots are folded into each precinct's own result"),
    "NE": ("no split", "the county map service carries no mode"),
    "AK": ("no split", "no election-night collector built"),
    "MI": ("no split", "no statewide election-night feed exists"),
}


def observed_last_day(st):
    """(last day in-person grew, last day we have at all) from our own series."""
    p = DATA / "trend-ev.json"
    if not p.exists():
        return None, None
    days = ((json.loads(p.read_text()).get("states") or {}).get(st) or {}).get("days") or []
    if not days:
        return None, None
    tot = lambda x: sum(v for v in (x or {}).values() if isinstance(v, (int, float)))
    grew = [days[i]["as_of"] for i in range(1, len(days))
            if tot(days[i].get("in_person_returned")) > tot(days[i-1].get("in_person_returned"))]
    return (grew[-1] if grew else None), days[-1]["as_of"]


def candidates(st):
    p = DATA / f"candidates-{st}.json"
    if not p.exists():
        return None
    return (json.loads(p.read_text()).get("races")) or None


def main():
    out, problems = {}, []
    for st, (first, last) in sorted(EV_WINDOW.items()):
        order, why = COUNT_ORDER.get(st, ("unknown", ""))
        seen, have_through = observed_last_day(st)
        row = {"early_in_person": {"first_day": first, "last_day": last,
                                   "last_day_we_saw_growth": seen,
                                   "our_series_runs_through": have_through},
               "counting": {"mode": order, "evidence": why},
               "candidates": candidates(st)}
        # Only a contradiction when we actually HAVE data through the stated close and
        # still saw no growth up to it. Comparing against today instead flagged seven
        # states purely because our series had not reached their close yet - Michigan
        # votes through the 1st and our last observation was the 30th.
        if seen and have_through and have_through >= last and seen < last:
            row["early_in_person"]["note"] = (
                f"our series stopped growing on {seen}, before the stated close {last}")
            problems.append(f"{st}: growth stopped {seen}, window says {last}")
        out[st] = row

    doc = {"note": ("Early-voting window, how the results feed treats modes, and who is "
                    "on the ballot. The window is a scheduled fact and cannot be derived "
                    "from our data - every state was still reporting in-person growth "
                    "after its close because the last day's returns post afterwards."),
           "ev_window_source": "ballotpedia.org/Early_voting_dates,_2026 (read 2026-11-01)",
           "states": out}
    (DATA / "state-facts.json").write_text(json.dumps(doc, indent=1) + "\n")

    print(f"{'st':4s} {'in-person early voting':26s} {'counting':12s} candidates")
    for st, row in sorted(out.items()):
        w = row["early_in_person"]
        c = row["candidates"]
        n = sum(len(r["candidates"]) for r in c.values()) if c else 0
        print(f"{st:4s} {w['first_day']} to {w['last_day']}   "
              f"{row['counting']['mode']:12s} "
              f"{(str(n) + ' names in ' + str(len(c)) + ' race(s)') if c else '—'}")
    for p in problems:
        print(f"   CHECK {p}")
    print(f"   -> state-facts.json")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as e:
        print(f"STATE FACTS FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
