#!/usr/bin/env python3
"""Louisiana election-night results by parish -> data/results-LA.json

Louisiana's results site is an Angular shell over a single endpoint that serves
named JSON blobs:

    /ElectionResults/ElectionResults/Data?blob=<path>

It answers GET with a `blob` query parameter. A GET without one returns
"501 - Header values specify a method that is not implemented", and POST returns
the same 501, which is what makes the endpoint look dead until you find the
parameter. The blob paths were read out of the page's own bundle
(/bundles/graphicalresults), which builds them as:

    ElectionDates.htm                            the available elections
    <date>/RacesCandidates_Multiparish.htm       races and candidates
    <date>/ParishesInElection.htm                precinct counts per parish
    <date>/VotesRaceByParish/Votes_<race>.htm    TOTAL votes per parish
    <date>/VotesEarly/Votes_<race>.htm           EARLY votes per parish

The date folder is yyyymmdd with no separators: 20261103.

Two things that make Louisiana unusually good to collect:

  * the early blob is per parish AND per candidate, so election-day votes are
    total minus early exactly - the same mode split Texas publishes, which no
    other state on this board gives at parish level.
  * every parish carries PrecinctsExpected and VoterCountQualified, so the
    reporting denominator is the state's own rather than one we assume.

Parishes arrive as ParishValue "01".."64" with no names. Louisiana numbers its
parishes alphabetically, which the geodata file confirms: 01 Acadia, 17 East
Baton Rouge, 36 Orleans, 64 Winn. The names are taken from
/Areas/ElectionResults/Scripts/GeoData/laParish.js rather than hardcoded, so a
boundary change upstream cannot silently misname a parish - if the list stops
being 64 long the run fails instead of publishing a wrong map.

Candidate party is not a field. It is inside the display string, as
'"Jamie" Davis (DEM)', so it is parsed out of the trailing parenthesis and the
name is what remains.

Exit 2 means Louisiana has not staged the election yet, which is an expected
state rather than a failure. Any other problem raises and writes nothing.
"""
import json, pathlib, re, sys, urllib.request
from datetime import datetime, timezone
import early_cast as early_cast_shared
import election_day

BASE = "https://voterportal.sos.la.gov"
DATA = BASE + "/ElectionResults/ElectionResults/Data?blob="
GEO = BASE + "/Areas/ElectionResults/Scripts/GeoData/laParish.js"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept": "application/json,text/plain,*/*"}
WANT = {"senate": r"U\.?\s*S\.?\s+SENATOR"}
PARTY = {"REP": "R", "DEM": "D"}


def get(path, raw=False, timeout=90):
    url = path if path.startswith("http") else DATA + path
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError(f"{url}: HTTP {r.status}")
        body = r.read().decode("utf-8", "ignore")
    if raw:
        return body
    if body.lstrip().startswith("<"):
        raise RuntimeError(f"{url}: served HTML, not JSON — the blob name is probably wrong")
    return json.loads(body)


def parish_names():
    """The 64 parish names in code order, from the state's own geodata.

    Hardcoding this list would let a rename upstream put the wrong name on a
    parish without anything noticing. Reading it and refusing to proceed on a
    short list makes that a failure rather than a quiet error.
    """
    js = get(GEO, raw=True)
    names = re.findall(r'"(?:NAME|name|PARISH|Parish)"\s*:\s*"([^"]+)"', js)
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    if len(out) != 64:
        raise RuntimeError(f"laParish.js gave {len(out)} parish names — Louisiana has 64")
    return {f"{i + 1:02d}": n for i, n in enumerate(out)}


def find_election(year=2026):
    """The November general for `year` as a yyyymmdd folder, or None.

    The blob is {"Dates": {"DefaultElectionDate": "11/03/2026", "Date": [...]}} and
    the dates are MM/DD/YYYY, not ISO - reading them as ISO silently finds nothing
    and the collector reports "not staged yet" for an election that is staged.
    """
    d = get("ElectionDates.htm")
    block = d.get("Dates") or {}
    rows = block.get("Date") or []
    if isinstance(rows, dict):
        rows = [rows]
    cand = [str(r.get("ElectionDate") or "") for r in rows]
    cand.insert(0, str(block.get("DefaultElectionDate") or ""))
    for raw in cand:
        m = re.match(r"\s*(\d{2})/(\d{2})/(\d{4})\s*$", raw)
        if m and m.group(3) == str(year) and m.group(1) == "11":
            return f"{m.group(3)}{m.group(1)}{m.group(2)}"
    return None


def split_name(desc):
    """'"Jamie" Davis (DEM)' -> ('Jamie Davis', 'D'). Party is not its own field."""
    m = re.search(r"\(([A-Z]{3,4})\)\s*$", desc or "")
    party = PARTY.get(m.group(1).upper(), "O") if m else "O"
    name = re.sub(r"\s*\([A-Z]{3,4}\)\s*$", "", desc or "").strip()
    return name.replace('"', "").strip(), party


def build(folder):
    names = parish_names()
    races = get(f"{folder}/RacesCandidates_Multiparish.htm")
    rlist = (races.get("Races") or {}).get("Race") or []
    found = {}
    for r in rlist:
        title = (r.get("SpecificTitle") or "").strip()
        for key, pat in WANT.items():
            if re.search(pat, title, re.I):
                if key in found:
                    raise RuntimeError(f"{key!r} matched twice: "
                                       f"{found[key]['title']!r} and {title!r}")
                ch = r.get("Choice") or []
                if isinstance(ch, dict):
                    ch = [ch]
                found[key] = {"id": str(r.get("ID")), "title": title,
                              "choices": {str(c.get("ID")): split_name(c.get("Desc"))
                                          for c in ch}}
    if not found:
        raise RuntimeError(f"none of {sorted(WANT)} found among {len(rlist)} Louisiana races")

    cast, cast_as_of = early_cast_shared.by_unit("LA", key=lambda s: s.upper())
    counties, totals = {}, {}
    for key, race in found.items():
        by_parish = get(f"{folder}/VotesRaceByParish/Votes_{race['id']}.htm")
        early = get(f"{folder}/VotesEarly/Votes_{race['id']}.htm")
        P = (by_parish.get("Parishes") or {}).get("Parish") or []
        E = {str(p.get("ParishValue")): p
             for p in ((early.get("EarlyVoting") or {}).get("Parish") or [])}
        if len(P) != 64:
            raise RuntimeError(f"{key}: {len(P)} parishes in the feed — Louisiana has 64")

        st = {"choices": {}, "early": {}, "parties": {}}
        pr_in = pr_all = 0
        for p in P:
            code = str(p.get("ParishValue"))
            nm = names.get(code)
            if not nm:
                raise RuntimeError(f"parish code {code!r} has no name in the geodata")
            ev = E.get(code) or {}
            evc = {str(c.get("ID")): int(c.get("VoteTotal") or 0)
                   for c in (ev.get("Choice") or [])}
            choices = {}
            for c in (p.get("Choice") or []):
                cid = str(c.get("ID"))
                who, party = race["choices"].get(cid, (f"Choice {cid}", "O"))
                v = int(c.get("VoteTotal") or 0)
                e = evc.get(cid, 0)
                # Louisiana reports early and absentee together, so 'early' here is
                # early in person plus mail, and the remainder is election day.
                choices[who] = {"party": party, "votes": v,
                                "by_mode": {"early": e, "election_day": max(0, v - e)}}
                st["choices"][who] = st["choices"].get(who, 0) + v
                st["early"][who] = st["early"].get(who, 0) + e
                st["parties"][who] = party
            ri = int(p.get("PrecinctsReporting") or 0)
            ra = int(p.get("PrecinctsExpected") or 0) or ri
            pr_in += ri
            pr_all += ra
            counted_early = sum(x["by_mode"]["early"] for x in choices.values())
            was = cast.get(nm.upper())
            rec = counties.setdefault(nm, {
                "fips": code, "registered": int(p.get("VoterCountQualified") or 0),
                "ballots_cast": int(p.get("VoterCountVoted") or 0),
                "precincts_reporting": ri, "precincts_total": ra,
                "percent_reporting": round(ri / ra * 100, 1) if ra else 0,
                "races": {}})
            rec["races"][key] = {
                "choices": dict(sorted(choices.items(), key=lambda x: -x[1]["votes"])),
                "counted": sum(x["votes"] for x in choices.values()),
                "early_and_mail_counted": counted_early,
                "early_and_mail_cast": was,
                "early_and_mail_left": (max(0, was - counted_early) if was is not None else None),
                "precincts_reporting": ri, "precincts_total": ra,
            }
        ce = sum(st["early"].values())
        cast_tot = sum(cast.values()) if cast else None
        totals[key] = {
            "contest_name": race["title"],
            "choices": dict(sorted(st["choices"].items(), key=lambda x: -x[1])),
            "parties": st["parties"],
            "total": sum(st["choices"].values()),
            "modes": {"early": ce, "election_day": sum(st["choices"].values()) - ce},
            "choices_by_mode": {who: {"early": st["early"].get(who, 0),
                                      "election_day": v - st["early"].get(who, 0)}
                                for who, v in st["choices"].items()},
            "precincts_reporting": pr_in, "precincts_total": pr_all,
            "early_and_mail_cast": cast_tot, "early_and_mail_counted": ce,
            "early_and_mail_left": (max(0, cast_tot - ce) if cast_tot is not None else None),
        }

    payload = {
        "state": "LA", "unit": "parish", "source_kind": "louisiana-enr",
        "election": f"November {folder[:4]} general", "election_date": folder,
        "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "early_cast_as_of": cast_as_of,
        "counties": counties, "state_totals": totals,
        "source": DATA + f"{folder}/VotesRaceByParish/Votes_<race>.htm",
        "notes": {
            "modes": "Louisiana publishes an early-and-absentee blob per race per parish "
                     "alongside the total, so election-day votes are total minus early "
                     "exactly — no inference.",
            "names": "Parishes arrive as codes 01-64 with no names; the names come from "
                     "the state's own laParish.js geodata in alphabetical order, which is "
                     "how Louisiana numbers parishes.",
            "left": "early_and_mail_left is measured: ballots this board recorded cast "
                    "early in that parish, minus the early votes counted here.",
        },
    }
    return payload, totals, counties


def main():
    folder = find_election(2026)
    if not folder:
        print("LA: November 2026 general not staged yet")
        return 2
    payload, totals, counties = build(folder)
    if "--proof" in sys.argv:
        print(f"LA proof via {folder}: {len(counties)} parishes")
        for race, t in totals.items():
            print(f"   {race}: {t['total']:,} votes  early {t['modes']['early']:,}  "
                  f"election-day {t['modes']['election_day']:,}  "
                  f"precincts {t['precincts_reporting']:,}/{t['precincts_total']:,}")
            for c, v in list(t["choices"].items())[:4]:
                print(f"      {c[:38]:40} {v:>10,}  {t['parties'].get(c)}")
        return 0
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "results-LA.json"
    rc = election_day.write_or_hold("LA", p, payload, totals)
    if rc:
        return rc
    for race, t in totals.items():
        print(f"LA {race}: {t['total']:,} counted  precincts "
              f"{t['precincts_reporting']:,}/{t['precincts_total']:,}")
    print(f"   -> {p.name} ({len(counties)} parishes)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as e:
        print(f"LA RESULTS FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
