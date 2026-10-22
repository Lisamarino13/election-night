#!/usr/bin/env python3
"""Ohio election-night results by county -> data/results-OH.json

Two feeds from the Secretary of State's own election-night service:

  /Api/v1/download?filename=VSSC1622XmlFileBlob
      IEEE-1622 election results XML. Each county is a <GpUnit Type="County"> carrying
      registered voters, ballots cast, absentee ballots cast, precincts reported out of
      total, and a count status; each contest carries a per-county vote count.

  /Api/v1/Contest/GetElectionSummaryCsv
      Per county: registered, ballots counted, turnout, OUTSTANDING UOCAVA ABSENTEES and
      OUTSTANDING PROVISIONALS, precincts reporting.

Ohio is unusual in publishing outstanding ballots itself, so two of the three kinds of
remaining ballot are reported rather than derived:

    outstanding UOCAVA + outstanding provisionals  - from Ohio
    early and mail still to count                  - measured here, as what this board
        recorded cast early in that county minus the county's absentee ballots counted
    election-day ballots still to come             - not estimated, only precincts out

A caution the payload carries too: Ohio's contest votes are a single Total per county,
not split by mode. The absentee/provisional split lives on the county, not on the
contest, so a per-contest mode breakdown is not available here the way it is in North
Carolina. Treating the county absentee count as if it were the contest's absentee count
is an approximation, and it is labelled as one.

FAILS CLOSED: any fetch or parse problem raises and writes nothing.
"""
import csv, io, json, pathlib, re, sys, urllib.request, collections
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

HOST = "https://liveresults.ohiosos.gov"
XML = HOST + "/Api/v1/download?filename=VSSC1622XmlFileBlob"
CSV = HOST + "/Api/v1/Contest/GetElectionSummaryCsv"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept": "*/*", "Accept-Encoding": "gzip, deflate"}
NS = {"e": "http://grouper.ieee.org/groups/1622/groups/2/V1/1622_2-election_results_reporting.xsd",
      "xsi": "http://www.w3.org/2001/XMLSchema-instance"}
WANT = {"senate": r"^U\.?S\.? SENATOR", "governor": r"^GOVERNOR"}
PARTY = {"DEMOCRAT": "D", "DEMOCRATIC": "D", "REPUBLICAN": "R"}


def get(url, timeout=120):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError(f"{url}: HTTP {r.status}")
        body, enc = r.read(), (r.headers.get("Content-Encoding") or "").lower()
    if enc == "gzip" or body[:2] == b"\x1f\x8b":
        import gzip; body = gzip.decompress(body)
    elif enc == "deflate":
        import zlib
        try: body = zlib.decompress(body)
        except zlib.error: body = zlib.decompress(body, -zlib.MAX_WBITS)
    return body


def n(v):
    v = re.sub(r'[",=]', "", (v or "").strip())
    try: return int(float(v))
    except ValueError: return None


def summary_csv():
    rows = list(csv.DictReader(io.StringIO(get(CSV, 60).decode("utf-8", "ignore"))))
    if not rows:
        raise RuntimeError("summary csv: no rows")
    key = {k.strip().lower(): k for k in rows[0]}
    need = ["county", "outstanding uocava absentees", "outstanding provisionals"]
    for c in need:
        if c not in key:
            raise RuntimeError(f"summary csv: column {c!r} missing - layout changed")
    out = {}
    for r in rows:
        name = (r[key["county"]] or "").strip()
        if not name or name.lower() == "totals":
            continue
        out[name.title()] = {
            "registered": n(r.get(key.get("registered voters", ""), "")),
            "ballots_counted": n(r.get(key.get("ballots counted", ""), "")),
            "outstanding_uocava": n(r[key["outstanding uocava absentees"]]) or 0,
            "outstanding_provisional": n(r[key["outstanding provisionals"]]) or 0,
        }
    if len(out) < 80:
        raise RuntimeError(f"summary csv: {len(out)} counties - Ohio has 88; refusing")
    return out


def tag(el):
    return el.tag.split("}")[-1]


def parse_xml(body):
    root = ET.fromstring(body)
    meta = {"generated": root.get("GeneratedDate"), "status": root.get("Status"),
            "is_test": (root.get("IsTest") or "").lower() == "true",
            "issuer": root.get("Issuer")}
    counties, by_id = {}, {}
    for gp in root.iter():
        if tag(gp) != "GpUnit" or gp.get("Type") != "County":
            continue
        # Ohio lists every county TWICE: the reporting unit ("Adams", carrying registered
        # voters and precinct counts) and a district shell ("Adams County", carrying
        # neither. Taking both gave 176 counties for an 88-county state and would have
        # halved every per-county rate. The reporting unit is the one with registration.
        if gp.get("VotersRegistered") is None:
            continue
        name = (gp.get("Name") or "").strip().title()
        if not name:
            continue
        rec = {"registered": n(gp.get("VotersRegistered")),
               "ballots_cast": n(gp.get("VotersParticipated")),
               "precincts_total": n(gp.get("TotalSubUnits")),
               "precincts_reporting": n(gp.get("SubUnitsReported")),
               "by_mode": {}, "status": None}
        for ch in gp:
            if tag(ch) == "SummaryCounts":
                rec["by_mode"][(ch.get("Type") or "").lower()] = n(ch.get("BallotsCast")) or 0
            elif tag(ch) == "CountStatus":
                rec["status"] = ch.get("Status")
        counties[name] = rec
        by_id[gp.get("ObjectId")] = name
    if len(counties) < 80:
        raise RuntimeError(f"xml: {len(counties)} counties - Ohio has 88; refusing")

    # CandidateId -> ballot name / party. A BallotSelection points at its candidate
    # rather than naming them, and a governor's selection points at two (the running
    # mate second), so the first id is the one that names the ticket.
    parties = {}
    for el in root.iter():
        if tag(el) == "Party":
            nm = next(("".join(c.itertext()).strip() for c in el.iter()
                       if tag(c) == "Name"), "")
            parties[el.get("ObjectId")] = nm.strip()
    cands = {}
    for el in root.iter():
        if tag(el) != "Candidate":
            continue
        nm = next(("".join(c.itertext()).strip() for c in el if tag(c) == "BallotName"), None)
        pid = next((("".join(c.itertext()).strip()) for c in el if tag(c) == "PartyId"), None)
        cands[el.get("ObjectId")] = (nm, parties.get(pid, ""))

    races = collections.defaultdict(lambda: collections.defaultdict(dict))
    choice_party = {}
    found = {}
    for contest in root.iter():
        if tag(contest) != "Contest":
            continue
        name = (contest.get("Name") or "").strip()
        race = next((k for k, p in WANT.items() if re.search(p, name, re.I)), None)
        if race is None:
            continue
        if race in found and found[race] != name:
            raise RuntimeError(f"{race!r} matched two contests: {found[race]!r} and {name!r}")
        found[race] = name
        for sel in contest.iter():
            if tag(sel) != "BallotSelection":
                continue
            cid = next((("".join(c.itertext()).strip()) for c in sel
                        if tag(c) == "CandidateId"), None)
            cname, pname = cands.get(cid, (None, ""))
            if cname is None:
                cname = "Write-in" if (sel.get("IsWriteIn") or "").lower() == "true" else None
            if cname is None:
                continue
            choice_party[cname] = PARTY.get(pname.strip().upper(), "O")
            for vc in sel.iter():
                if tag(vc) != "VoteCounts":
                    continue
                gid = next((("".join(g.itertext()).strip())
                            for g in vc if tag(g) == "GpUnitId"), None)
                cty = by_id.get(gid)
                if cty is None:
                    continue
                races[cty][race][cname] = races[cty][race].get(cname, 0) + (n(vc.get("Count")) or 0)
    if not found:
        raise RuntimeError(f"none of {sorted(WANT)} found among the contests")
    return meta, counties, races, found, choice_party


def baseline(counties_races, precincts_reporting_total, stamp):
    """Capture each county's EARLY vote per contest, once, before any precinct reports.

    Ohio publishes a contest's votes as a single Total per county - no mode split - so
    on its own the feed cannot say which part of a county's total is early and which is
    election-day. Dividing that total by the precinct fraction would scale the early
    vote too, which is already complete, and that is the one mistake that flips a race
    on the night.

    But Ohio counts absentee BEFORE election day, and reports election-day precincts in
    their own column. So while that column reads zero, whatever is on the board IS the
    early vote. Captured once at that moment, every later election-day figure is exact
    subtraction rather than an approximation - size and party share both.

    The file is written once and never overwritten while it holds votes: a later run
    must not mistake a half-counted board for the baseline.
    """
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "baseline-OH.json"
    if p.exists():
        try:
            prev = json.loads(p.read_text())
            if prev.get("counties"):
                return prev
        except Exception:
            pass                                   # a corrupt baseline is re-taken
    if precincts_reporting_total:
        return None                                # too late - election day is under way
    total = sum(v for per in counties_races.values()
                for ch in per.values() for v in ch.values())
    if total <= 0:
        return None                                # nothing counted yet; nothing to bank
    doc = {"state": "OH", "captured": stamp, "precincts_reporting": 0,
           "note": ("Each county's vote per contest at the moment Ohio had counted its "
                    "absentee ballots and no election-day precinct had reported. Used to "
                    "separate election-day votes from early ones, which this feed does "
                    "not do itself."),
           "counties": {c: {r: dict(ch) for r, ch in per.items()}
                        for c, per in counties_races.items()}}
    p.write_text(json.dumps(doc, indent=1) + "\n")
    print(f"   banked the early-vote baseline ({total:,} votes, 0 precincts in) -> {p.name}")
    return doc


def early_cast():
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "early-OH.json"
    if not p.exists():
        return {}, None
    d = json.loads(p.read_text())
    out = {}
    for cty, b in (d.get("counties") or {}).items():
        def num(*ks):
            for k in ks:
                v = b.get(k)
                if isinstance(v, dict) and v.get("total") is not None: return v["total"]
                if isinstance(v, (int, float)): return int(v)
            return 0
        out[cty.title()] = num("by_mail", "mail_returned", "returned") + \
                           num("in_person", "early_in_person")
    return out, d.get("as_of")


def main():
    meta, cty_xml, races, found, choice_party = parse_xml(get(XML))
    summary = summary_csv()
    cast, cast_as_of = early_cast()

    pr_total = sum((info.get("precincts_reporting") or 0) for info in cty_xml.values())
    base = baseline(races, pr_total, meta["generated"])
    bcty = (base or {}).get("counties") or {}

    counties, state = {}, collections.defaultdict(collections.Counter)
    for cty, info in sorted(cty_xml.items()):
        s = summary.get(cty, {})
        absentee = info["by_mode"].get("absentee") or 0
        was = cast.get(cty)
        rec = {
            "registered": info["registered"], "ballots_cast": info["ballots_cast"],
            "precincts_total": info["precincts_total"],
            "precincts_reporting": info["precincts_reporting"],
            "count_status": info["status"],
            "ballots_by_mode": info["by_mode"],
            "outstanding_uocava": s.get("outstanding_uocava"),
            "outstanding_provisional": s.get("outstanding_provisional"),
            "early_and_mail_cast": was,
            "early_and_mail_counted": absentee,
            "early_and_mail_left": (max(0, was - absentee) if was is not None else None),
            "races": {},
        }
        for race, choices in races.get(cty, {}).items():
            rec["races"][race] = dict(sorted(choices.items(), key=lambda x: -x[1]))
            # with the baseline banked, every contest's votes split exactly into the
            # early vote that was already in and the election-day vote since
            b = (bcty.get(cty) or {}).get(race) or {}
            if b:
                rec.setdefault("by_mode_races", {})[race] = {
                    ch: {"early": b.get(ch, 0), "election_day": v - b.get(ch, 0)}
                    for ch, v in choices.items()}
            state[race].update(choices)
        counties[cty] = rec

    cast_tot = sum(cast.values()) if cast else None
    abs_tot = sum((c["ballots_by_mode"].get("absentee") or 0) for c in counties.values())
    totals = {}
    for race, cnt in state.items():
        totals[race] = {
            "contest_name": found.get(race),
            "choices": dict(cnt.most_common()),
            "parties": {c: choice_party.get(c, "O") for c in cnt},
            "total": sum(cnt.values()),
            "precincts_reporting": sum(c["precincts_reporting"] or 0 for c in counties.values()),
            "precincts_total": sum(c["precincts_total"] or 0 for c in counties.values()),
            "early_and_mail_cast": cast_tot, "early_and_mail_counted": abs_tot,
            "early_and_mail_left": (max(0, cast_tot - abs_tot) if cast_tot is not None else None),
            "outstanding_uocava": sum(c["outstanding_uocava"] or 0 for c in counties.values()),
            "outstanding_provisional": sum(c["outstanding_provisional"] or 0
                                           for c in counties.values()),
        }

    payload = {
        "state": "OH", "unit": "county", "source_kind": "ohio-enr",
        "election": "2026 General", "feed_generated": meta["generated"],
        "feed_status": meta["status"], "is_test_data": meta["is_test"],
        "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "early_cast_as_of": cast_as_of,
        "counties": counties, "state_totals": totals,
        "source": XML, "summary_source": CSV,
        "early_baseline": {"captured": (base or {}).get("captured"),
                           "have": bool(bcty)},
        "notes": {
            "modes": "Ohio reports a contest's votes as one Total per county, with the "
                     "absentee split published on the COUNTY rather than the contest. To "
                     "separate a contest's election-day votes from its early ones, each "
                     "county's totals are banked once while Ohio's election-day precinct "
                     "count still reads zero - at which point the board IS the early vote. "
                     "Everything after that is exact subtraction, so the election-day "
                     "figure that gets scaled by precincts never contains early ballots.",
            "outstanding": "Outstanding UOCAVA absentees and provisionals are Ohio's own "
                           "figures, not derived here.",
            "election_day": "Ballots still to come on election day are not estimated; "
                            "only precincts not yet reporting are shown.",
            "test": "feed_status and is_test_data come from the feed. Ohio runs mock "
                    "elections before election day; a board must not show mock votes as "
                    "real, so this flag travels with the data.",
        },
    }
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "results-OH.json"
    p.write_text(json.dumps(payload, indent=1) + "\n")
    flag = "  [TEST DATA]" if meta["is_test"] else ""
    print(f"OH {meta['status']}{flag}  generated {meta['generated']}")
    for race, t in totals.items():
        print(f"  {race:9} {t['total']:>9,} counted  precincts "
              f"{t['precincts_reporting']:,}/{t['precincts_total']:,}  "
              f"early+mail left {t['early_and_mail_left']}")
        for c, v in list(t["choices"].items())[:4]:
            print(f"      {c:34} {v:>9,}")
    print(f"   -> {p.name} ({len(counties)} counties)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as e:
        print(f"OH RESULTS FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
