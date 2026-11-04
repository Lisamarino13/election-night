#!/usr/bin/env python3
"""How many early + mail ballots a unit has CAST — the baseline every results
collector needs to say how many are still to count.

Each of the nine results collectors carried its own copy of this, and every copy
added up EVERY stream name it knew:

    g("by_mail") + g("mail_returned") + g("returned") + g("in_person") + g("early_in_person")

Those are aliases, not separate quantities. A payload that carries two names for the
same stream gets it counted twice, and three of them do: Florida writes both
`early_in_person` and `in_person` from the same file, so its in-person vote was counted
twice and early_cast returned 7,607,402 against a true 4,726,493 — the whole in-person
total again. Maine and North Carolina carry two names for mail and were over by 129,525
and 92,396.

That figure is the denominator for "early and mail ballots still to count", so an
inflated baseline makes the board believe millions of ballots are outstanding that were
never cast, and the projection spends them.

So: ONE stream per mode, first name present wins. Mail and in-person are kept separate
because they break in opposite directions and the caller may want them apart.
"""
import json, pathlib

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
MAIL = ("by_mail", "mail_returned", "returned")
INPERSON = ("in_person", "early_in_person")


def _n(block, key):
    v = (block or {}).get(key)
    if isinstance(v, dict):
        v = v.get("total")
    return v if isinstance(v, (int, float)) else None


def _one(block, names):
    """The first of these stream names the block actually carries."""
    for k in names:
        v = _n(block, k)
        if v is not None:
            return v
    return None


def split(block):
    """(mail, in_person) for one unit — either may be None if not published."""
    return _one(block, MAIL), _one(block, INPERSON)


def total(block):
    """Early + mail ballots cast by this unit, counting each mode once."""
    mail, ip = split(block)
    if mail is None and ip is None:
        return None
    return (mail or 0) + (ip or 0)


def ckey(s):
    """Letters and digits only, upper-cased - a county key that survives spelling.

    Early-vote files and results feeds rarely agree on how a county is written.
    Georgia's early file says DEKALB, BENHILL, MCDUFFIE; its results API says
    "DeKalb County", "Ben Hill County", "McDuffie County". Normalising with .title()
    produced "Dekalb", which matches neither, and five Georgia counties silently got
    cast=None on election night - DeKalb among them, holding 240,254 ballots - so the
    per-county outstanding summed 249,868 short and the board projected a state total
    below its own early vote. Case and punctuation are not information here.
    """
    return "".join(ch for ch in str(s).upper() if ch.isalnum())


def by_unit(state, key=None):
    """{unit -> ballots cast}, plus the file's as_of.

    `key` normalises the unit name to whatever the caller's results feed uses; the
    default leaves it as the early-vote file spells it.
    """
    p = DATA / f"early-{state}.json"
    if not p.exists():
        return {}, None
    d = json.loads(p.read_text())
    units = d.get("counties") or d.get("units") or {}
    norm = key or (lambda s: s)
    out = {}
    for name, block in units.items():
        if name.strip().upper() in ("STATEWIDE", "STATE", "TOTAL", "TOTALS", "ALL"):
            continue
        v = total(block)
        if v is None:
            continue
        k = norm(name)
        # Normalising a name can make two source rows collide, and assigning would make
        # the second silently replace the first. Maine's own file spells the same
        # unorganized township both "T10 SD" and "T10 Sd", so .title() merged five pairs
        # and dropped five ballots. Two rows for one unit are two parts of its total.
        out[k] = out.get(k, 0) + v
    return out, d.get("as_of")
