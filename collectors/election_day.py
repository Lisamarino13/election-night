#!/usr/bin/env python3
"""The one rule every results collector needs: results do not exist before polls close.

Minnesota taught this the hard way. Its 2026 results file went live eight days early
and is *already populated* - not with zeroes, but with its public accuracy test:
WRITE-IN sitting second statewide with 12,012 votes, Lyon County (33 precincts)
outpolling Dakota (144 precincts), and counts landing on suspiciously round numbers.
A collector whose only guard is "exit if the feed carries no votes" publishes all of
that as real the moment a state starts testing.

So the guard is not "are there votes" but "could these possibly be votes": nothing
publishes until the last poll in that state has closed. Before then a populated feed
is a test by definition, however plausible it looks.

Times are the LAST closing in each state, in UTC, for 2026-11-03. Erring late costs a
few minutes on the night; erring early lets test data onto the board, so every state
with a second time zone waits for its western edge. DST ends 2026-11-01, so these are
standard-time offsets (EST -5, CST -6, MST -7, AKST -9).

Set RESULTS_IGNORE_POLL_CLOSE=1 to parse a live feed before the gate opens. It is for
checking a parser against real structure; it never writes a results file.
"""
import os
from datetime import datetime, timezone

# state -> (hour, minute) UTC on 2026-11-04, when the state's LAST poll closes
_CLOSE = {
    "GA": (0, 0),    # 7:00pm EST
    "SC": (0, 0),    # 7:00pm EST
    "NC": (0, 30),   # 7:30pm EST
    "OH": (0, 30),   # 7:30pm EST
    "ME": (1, 0),    # 8:00pm EST
    "FL": (1, 0),    # panhandle counties close 7:00pm CST
    "MI": (2, 0),    # four western UP counties close 8:00pm CST
    "TX": (2, 0),    # El Paso / Hudspeth close 7:00pm MST
    "KS": (2, 0),    # four western counties close 7:00pm MST
    "IA": (2, 0),    # 8:00pm CST
    "MN": (2, 0),    # 8:00pm CST
    "NE": (3, 0),    # panhandle counties close 8:00pm MST
    "AK": (5, 0),    # 8:00pm AKST
}
OVERRIDE = "RESULTS_IGNORE_POLL_CLOSE"


def polls_close(state):
    if state not in _CLOSE:
        raise RuntimeError(f"no poll-closing time recorded for {state!r} — add one "
                           f"before that state may publish results")
    h, m = _CLOSE[state]
    return datetime(2026, 11, 4, h, m, tzinfo=timezone.utc)


def overridden():
    return os.environ.get(OVERRIDE) == "1"


def before_close(state, now=None):
    """None once the state may publish; otherwise why it may not, for the caller to print."""
    now = now or datetime.now(timezone.utc)
    close = polls_close(state)
    if now >= close:
        return None
    left = close - now
    hrs = left.days * 24 + left.seconds // 3600
    return (f"{state}: polls have not closed — anything in the feed now is the state's "
            f"accuracy test, not results ({hrs}h until {close:%Y-%m-%d %H:%MZ}). "
            f"Nothing written. Set {OVERRIDE}=1 to parse it without publishing.")


def writing_allowed(state, now=None):
    """True if a results file may be written for this state right now."""
    return before_close(state, now) is None


def test_data_signature(totals):
    """Signatures that say 'accuracy test' even after polls close. Flags, never blocks."""
    flags = []
    for race, t in (totals or {}).items():
        ch = t.get("choices") or {}
        if not ch:
            continue
        ranked = sorted(ch.items(), key=lambda x: -(x[1] or 0))
        wi = [(n, v) for n, v in ranked if "WRITE" in str(n).upper()]
        if wi:
            major = [v for n, v in ranked
                     if (t.get("parties") or {}).get(n) in ("D", "R")]
            if major and wi[0][1] > min(major):
                flags.append(f"{race}: write-in ({wi[0][1]:,}) outpolls a major-party "
                             f"candidate ({min(major):,})")
    return flags


def write_or_hold(state, path, payload, totals=None):
    """Write a results file, or refuse to and say why. Returns the collector's exit code.

    Two refusals: the gate is shut (no results exist yet), or the gate is shut and the
    override is on (parse it, publish nothing). Test-data signatures are printed as
    warnings once the gate is open, because a real write-in landslide is possible even
    if it never happens.
    """
    import json
    shut = before_close(state)
    if shut:
        if overridden():
            print(f"{state}: parsed the live feed but wrote nothing — {OVERRIDE} is set "
                  f"and polls have not closed.")
            # The override exists to check a parser against real structure, so say what
            # the parse found; it is just never allowed to become a published figure.
            for race, t in (totals or {}).items():
                rep, tot = t.get("precincts_reporting"), t.get("precincts_total")
                pct = f"{rep:,}/{tot:,} precincts" if rep is not None and tot else "precincts ?"
                print(f"   parsed {race}: {(t.get('total') or 0):,} votes, {pct}")
            for flag in test_data_signature(totals):
                print(f"   and it is test data: {flag}")
        else:
            print(shut)
        return 2
    for flag in test_data_signature(totals):
        print(f"{state} WARNING — looks like test data: {flag}", flush=True)
    path.write_text(json.dumps(payload, indent=1) + "\n")
    return 0
