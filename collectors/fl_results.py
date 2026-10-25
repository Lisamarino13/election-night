#!/usr/bin/env python3
"""Florida election-night results by county -> data/results-FL.json

Source: flelectionfiles.floridados.gov/enightfilespublic/<YYYYMMDD>_ElecResultsFL.txt

A tab-delimited file, one row per county per candidate:

    CountyName  RaceName  PartyCode  CanNameLast/First  CanVotes
    Precincts   PrecinctsReporting

Florida does NOT split a contest's votes by mode in this file - there is no early or
election-day column. But Florida counts vote-by-mail and early voting FIRST and posts
them at poll close, before any election-day precinct reports. So while
PrecinctsReporting is zero and votes are already on the board, what is on the board IS
the early and mail vote. Banked once at that moment, every later election-day figure is
exact subtraction, the same way Ohio is handled.

That subtraction is what makes the precinct scaling safe. Dividing a county's whole
total by its reporting fraction would scale the early vote too - which is already
complete - and in Florida the early vote is most of the ballots, so that mistake would
be enormous.

FAILS CLOSED: any fetch or parse problem raises and writes nothing.
"""
import csv, io, json, pathlib, re, sys, urllib.request, collections
from datetime import datetime, timezone

BASE = "https://flelectionfiles.floridados.gov/enightfilespublic"
ELECTION_DATE = "20261103"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept-Encoding": "gzip"}
WANT = {"senate": r"United States Senator", "governor": r"^Governor"}
PARTY = {"REP": "R", "DEM": "D"}


def get(url, timeout=180):
    import gzip
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError(f"{url}: HTTP {r.status}")
        body = r.read()
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    text = body.decode("utf-8", "ignore")
    if text.lstrip().startswith("<"):
        raise RuntimeError(f"{url}: served HTML, not the results file")
    return text


def num(v):
    v = (v or "").strip().replace(",", "")
    return int(v) if v.lstrip("-").isdigit() else 0


def candidate_name(row):
    last = (row.get("CanNameLast") or "").strip()
    first = (row.get("CanNameFirst") or "").strip()
    mid = (row.get("CanNameMiddle") or "").strip()
    # Florida writes a running mate as First="Trump" Middle=" / " Last="Vance"
    if mid.strip() == "/":
        return f"{first} / {last}".strip()
    return " ".join(x for x in (first, mid, last) if x and x != "/").strip() or last


def parse(text):
    rows = list(csv.DictReader(io.StringIO(text), delimiter="\t"))
    if not rows:
        raise RuntimeError("results file: no rows")
    need = ["CountyName", "RaceName", "CanVotes", "Precincts", "PrecinctsReporting"]
    for c in need:
        if c not in rows[0]:
            raise RuntimeError(f"results file: column {c!r} missing - layout changed")
    counties = collections.defaultdict(lambda: {"precincts_total": 0,
                                                "precincts_reporting": 0, "races": {}})
    found, party_of = {}, {}
    for r in rows:
        name = (r.get("RaceName") or "").strip()
        race = next((k for k, pat in WANT.items() if re.search(pat, name, re.I)), None)
        if race is None:
            continue
        if race in found and found[race] != name:
            raise RuntimeError(f"{race!r} matched two contests: {found[race]!r} and {name!r}")
        found[race] = name
        cty = (r.get("CountyName") or "").strip().title()
        if not cty:
            continue
        c = counties[cty]
        c["precincts_total"] = max(c["precincts_total"], num(r.get("Precincts")))
        c["precincts_reporting"] = max(c["precincts_reporting"],
                                       num(r.get("PrecinctsReporting")))
        cn = candidate_name(r)
        party_of[cn] = PARTY.get((r.get("PartyCode") or "").strip().upper(), "O")
        c["races"].setdefault(race, {})[cn] = \
            c["races"].setdefault(race, {}).get(cn, 0) + num(r.get("CanVotes"))
    if not found:
        raise RuntimeError(f"none of {sorted(WANT)} found in the file")
    if len(counties) < 60:
        raise RuntimeError(f"only {len(counties)} counties - Florida has 67; refusing")
    return counties, found, party_of


def baseline(counties, stamp):
    """Bank the early and mail vote, once, while no precinct has reported."""
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "baseline-FL.json"
    if p.exists():
        try:
            prev = json.loads(p.read_text())
            if prev.get("counties"):
                return prev
        except Exception:
            pass
    reporting = sum(c["precincts_reporting"] for c in counties.values())
    votes = sum(v for c in counties.values() for r in c["races"].values() for v in r.values())
    if reporting or votes <= 0:
        return None                     # too late, or nothing banked yet
    doc = {"state": "FL", "captured": stamp, "precincts_reporting": 0,
           "note": ("Each county's vote per contest while Florida had posted its "
                    "vote-by-mail and early voting and no election-day precinct had "
                    "reported. Used to separate election-day votes from early ones, "
                    "which this file does not do itself."),
           "counties": {c: {r: dict(v) for r, v in d["races"].items()}
                        for c, d in counties.items()}}
    p.write_text(json.dumps(doc, indent=1) + "\n")
    print(f"   banked the early-vote baseline ({votes:,} votes, 0 precincts in)")
    return doc


def early_cast():
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "early-FL.json"
    if not p.exists():
        return {}, None
    d = json.loads(p.read_text())
    out = {}
    for cty, b in (d.get("counties") or {}).items():
        g = lambda k: (b[k].get("total") if isinstance(b.get(k), dict) else b.get(k)) or 0
        out[cty.title()] = g("returned") + g("mail_returned") + g("by_mail") \
                           + g("early_in_person") + g("in_person")
    return out, d.get("as_of")


def build(date=ELECTION_DATE):
    text = get(f"{BASE}/{date}_ElecResultsFL.txt")
    counties, found, party_of = parse(text)
    base = baseline(counties, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    bcty = (base or {}).get("counties") or {}
    cast, cast_as_of = early_cast()

    out_c, state = {}, collections.defaultdict(
        lambda: {"choices": collections.Counter(), "early": collections.Counter()})
    pr_in = pr_all = 0
    for cty, d in sorted(counties.items()):
        pr_in += d["precincts_reporting"]; pr_all += d["precincts_total"]
        rec = {"precincts_total": d["precincts_total"],
               "precincts_reporting": d["precincts_reporting"], "races": {}}
        for race, choices in d["races"].items():
            b = (bcty.get(cty) or {}).get(race) or {}
            by_mode = {c: {"early": b.get(c, 0), "election_day": max(0, v - b.get(c, 0))}
                       for c, v in choices.items()} if b else None
            counted_early = sum(m["early"] for m in by_mode.values()) if by_mode else None
            was = cast.get(cty)
            rec["races"][race] = {
                "choices": {c: {"party": party_of.get(c, "O"), "votes": v,
                                **({"by_mode": by_mode[c]} if by_mode else {})}
                            for c, v in sorted(choices.items(), key=lambda x: -x[1])},
                "counted": sum(choices.values()),
                "precincts_total": d["precincts_total"],
                "precincts_reporting": d["precincts_reporting"],
                "early_and_mail_counted": counted_early,
                "early_and_mail_cast": was,
                "early_and_mail_left": (max(0, was - counted_early)
                                        if (was is not None and counted_early is not None)
                                        else None),
            }
            for c, v in choices.items():
                state[race]["choices"][c] += v
                if by_mode:
                    state[race]["early"][c] += by_mode[c]["early"]
        out_c[cty] = rec

    cast_tot = sum(cast.values()) if cast else None
    totals = {}
    for race, s in state.items():
        ce = sum(s["early"].values()) or None
        totals[race] = {
            "contest_name": found.get(race),
            "choices": dict(s["choices"].most_common()),
            "parties": {c: party_of.get(c, "O") for c in s["choices"]},
            "total": sum(s["choices"].values()),
            "precincts_reporting": pr_in, "precincts_total": pr_all,
            "early_and_mail_cast": cast_tot, "early_and_mail_counted": ce,
            "early_and_mail_left": (max(0, cast_tot - ce)
                                    if (cast_tot is not None and ce is not None) else None),
        }
    payload = {
        "state": "FL", "unit": "county", "source_kind": "florida-enr",
        "election": "2026 General", "election_date": date,
        "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "early_cast_as_of": cast_as_of,
        "early_baseline": {"captured": (base or {}).get("captured"), "have": bool(bcty)},
        "counties": out_c, "state_totals": totals,
        "source": f"{BASE}/{date}_ElecResultsFL.txt",
        "notes": {
            "modes": "Florida's results file carries no early or election-day column. "
                     "Florida posts vote-by-mail and early voting at poll close, before "
                     "any election-day precinct reports, so the board at that moment IS "
                     "the early vote; it is banked once and everything after is exact "
                     "subtraction. Until it is banked there is no mode split and the "
                     "precinct scaling stays switched off, because dividing a Florida "
                     "county's whole total would scale an early vote that is already "
                     "complete and is most of the ballots.",
            "election_day": "Ballots still to come on election day are not estimated; "
                            "only precincts not yet reporting are shown.",
        },
    }
    return payload, totals, out_c


def main():
    if "--proof" in sys.argv:
        i = sys.argv.index("--proof")
        payload, totals, counties = build(sys.argv[i + 1])
        print(f"FL proof via {sys.argv[i+1]}: {len(counties)} counties, precincts "
              f"{list(totals.values())[0]['precincts_reporting']:,}/"
              f"{list(totals.values())[0]['precincts_total']:,}")
        for race, t in totals.items():
            print(f"   {race}: {t['total']:,} votes")
            for c, v in list(t["choices"].items())[:3]:
                print(f"      {c[:36]:38} {v:>10,}")
        return 0
    try:
        payload, totals, counties = build()
    except RuntimeError as e:
        if "HTTP 404" in str(e) or "not the results file" in str(e):
            print(f"FL: the 2026 results file is not published yet ({e})")
            return 2
        raise
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "results-FL.json"
    p.write_text(json.dumps(payload, indent=1) + "\n")
    for race, t in totals.items():
        print(f"FL {race}: {t['total']:,} counted  precincts "
              f"{t['precincts_reporting']:,}/{t['precincts_total']:,}")
    print(f"   -> {p.name} ({len(counties)} counties)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as e:
        print(f"FL RESULTS FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
