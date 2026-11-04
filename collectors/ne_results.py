#!/usr/bin/env python3
"""Nebraska election-night results by county -> data/results-NE.json

Nebraska's results site renders its totals server-side into a 3.9MB page with no table
markup and no data file, which is why this looked unreachable at first. The county
numbers come from a separate web service that the page's own map script calls:

    https://neresultswebservice.azurewebsites.us/ResultsAjax.svc/
        GetCandidates?ElectionType=General&ElectionID=0
        GetMapData?type=SW&category=CTY&raceID=<id>&osn=<n>&county=0&party=0

Neither is documented. The signature came out of Scripts/BuildCounties.js, which the
results page loads to draw its county map - the map IS the county data, and asking the
service directly skips the map.

The contest id is the one the page uses for its "Follow This Contest" checkbox
(id="chk-148" for the Senate race). GetMapData answers {"d":[]} before any votes exist
and the same shape with rows afterwards, so an empty answer means "no results yet"
rather than a broken call - which is why this can be built and checked now, nine days
early, rather than first thing on the night.

Exit 2 means Nebraska has not published results yet. Any other problem raises and
writes nothing.
"""
import gzip, json, pathlib, re, sys, urllib.request, collections
from datetime import datetime, timezone
import early_cast as early_cast_shared
import election_day

SVC = "https://neresultswebservice.azurewebsites.us/ResultsAjax.svc"
PAGE = "https://electionresults.nebraska.gov/resultsSW.aspx?type=SW&map=CTY"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept": "application/json,*/*", "Accept-Encoding": "gzip"}
WANT = {"senate": r"United States Senator"}
PARTY = {"REPUBLICAN": "R", "DEMOCRAT": "D", "DEMOCRATIC": "D",
         # GetMapData sends PartyCode, the three-letter form
         "REP": "R", "DEM": "D", "LIB": "O", "GRN": "O", "NON": "I"}


def get(url, timeout=90, as_json=True):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError(f"{url}: HTTP {r.status}")
        body = r.read()
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    text = body.decode("utf-8", "ignore")
    if not as_json:
        return text
    if text.lstrip().startswith("<"):
        raise RuntimeError(f"{url}: served HTML, not JSON")
    return json.loads(text)


def contests(eid=None):
    """Contest name -> the ids the service wants, read off the results page itself.

    `eid` names a PAST election, the way the site's own scripts take one: ?eid=<n> on
    the page URL (utils.js setCountyURL, BuildCounties.js getUrlVars()["eid"]). Left
    out, this is tonight's live page exactly as before.
    """
    html = get(PAGE + (f"&eid={eid}" if eid else ""), timeout=120, as_json=False)
    out = {}
    # Each contest is a heading followed by its "Follow This Contest" checkbox, whose id
    # carries the race id. Pairing them is how a contest name maps to an id without any
    # documented listing.
    # The "chk-<n>" id names the contest but is NOT what GetMapData wants: called with
    # it and osn=0 the service answers {"d":[]} however many votes are in, so the
    # collector would report "no results yet" all night without ever erroring. The pair
    # it does want is in the page's own BuildCounty('SW', '<raceID>', '<osn>', '')
    # calls, which appear once per contest in the same order as the checkboxes.
    pairs = re.findall(r"BuildCounty\(\s*'[^']*'\s*,\s*'(\d+)'\s*,\s*'(\d+)'", html)
    names = []
    for m in re.finditer(r"<h1>(.*?)</h1>(.*?)(?=<h1>|$)", html, re.S):
        name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1))).strip()
        if name and re.search(r'id="chk-\d+"', m.group(2)):
            names.append(name)
    if len(names) != len(pairs):
        raise RuntimeError(f"{len(names)} contests but {len(pairs)} BuildCounty calls — "
                           f"the page layout changed; the pairing is no longer safe")
    for name, (rid, osn) in zip(names, pairs):
        out[name] = (int(rid), int(osn))
    if not out:
        raise RuntimeError("results page carried no contest headings — layout changed")
    # The display markup is the wrong thing to read. All three of these regexes were
    # scraping rendered spans and all three returned nothing on 11-02 while the page
    # plainly carried the figures: "Results last updated:" is followed immediately by
    # </span>, so [^<] could never match; "Registered Voters" is separated from its
    # number by exactly 41 characters of markup against a 40-character allowance; and
    # the "Total" the third one found was an unrelated form value. Because each was
    # guarded by `if`, the failures were silent and meta came back {}.
    #
    # ASP.NET puts the same figures in hidden inputs, which are machine-facing and do
    # not move when the layout does. Read those instead.
    def hid(name):
        m = re.search(rf'id="hid{name}"[^>]*\bvalue="([^"]*)"', html)
        return m.group(1).strip() if m else None

    def hidint(name):
        v = hid(name)
        if v is None:
            return None
        v = v.replace(",", "")
        return int(v) if re.fullmatch(r"-?\d+", v) else None

    meta = {}
    t = re.search(r"Results last updated:\s*(?:</span>\s*<span[^>]*>)?\s*([^<]{5,40})", html)
    if t:
        meta["updated"] = re.sub(r"\s+", " ", t.group(1)).strip()
    reg = re.search(r'class="header-voter-number"[^>]*>\s*([\d,]+)', html) \
        or re.search(r"Registered Voters(?:(?!\d)[\s\S]){0,80}?([\d,]{4,})", html)
    if reg:
        meta["registered"] = int(reg.group(1).replace(",", ""))
    # precincts: reported + partial + not-reported is the total, and each part is
    # useful on its own once counting starts.
    rep, part, notrep = (hidint("PrecinctsReported"), hidint("PrecinctsPartial"),
                         hidint("PrecinctsNotReported"))
    if None not in (rep, part, notrep):
        meta["precincts_reporting"] = rep
        meta["precincts_partial"] = part
        meta["precincts_total"] = rep + part + notrep
    else:
        pr = re.search(r'class="header-totalprecincts-text"[^>]*>\s*([\d,]+)', html) \
            or re.search(r"Precincts Fully:\s*[\d,]+\s*/\s*([\d,]+)", html)
        if pr:
            meta["precincts_total"] = int(pr.group(1).replace(",", ""))
    if hid("ElectionDate"):
        meta["election_date"] = hid("ElectionDate")
    if hid("ElectionType"):
        meta["election_type"] = hid("ElectionType")
    # A layout change that takes out every field at once is what hid the old bug for
    # days. One missing field is tolerable; all of them is not.
    if not meta:
        raise RuntimeError("results page carried none of the expected header figures - "
                           "layout changed")
    return out, meta


def county_rows(race_id, osn, eid=None):
    # BuildCounties.js swaps GetMapData for GetMapDataArchive and adds &electionID=<eid>
    # when the page URL carries one; everything else about the call is the same. With no
    # eid this is the live call, unchanged.
    call = ("GetMapDataArchive" if eid else "GetMapData")
    d = get(f"{SVC}/{call}?type=SW&category=CTY&raceID={race_id}"
            f"&osn={osn}&county=0&party=0"
            + (f"&electionID={eid}" if eid else "")).get("d")
    if d is None:
        raise RuntimeError(f"GetMapData returned null for race {race_id} — "
                           f"the service rejected the call rather than finding nothing")
    return d


def early_cast():
    """Early + mail ballots cast per unit, from the shared reader.

    This was a local copy that added up every stream name it knew. Those names
    are aliases, so a payload carrying two for one stream had it counted twice -
    Florida writes both early_in_person and in_person and was over by 2,880,909,
    the whole in-person vote again. early_cast.by_unit takes one stream per mode.
    """
    return early_cast_shared.by_unit("NE", key=early_cast_shared.ckey)


def build(eid=None):
    """Read the feed and tally it. The live path and --proof both come through here.

    Lifted out of main() unchanged so a proof run against a past election goes through
    exactly the same contest lookup, service call and row reader the night uses — a
    second copy of this would only prove the copy. `eid` is passed straight down.
    """
    found, meta = contests(eid)
    picked = {}
    for name, (rid, osn) in found.items():
        race = next((k for k, pat in WANT.items() if re.search(pat, name, re.I)), None)
        if race is None:
            continue
        if race in picked and picked[race][0] != name:
            raise RuntimeError(f"{race!r} matched two contests: {picked[race][0]!r} and {name!r}")
        picked[race] = (name, rid, osn)
    if not picked:
        raise RuntimeError(f"none of {sorted(WANT)} among {len(found)} contests on the page")

    cast, cast_as_of = early_cast()
    counties, totals, any_votes = {}, {}, False
    for race, (name, rid, osn) in picked.items():
        rows = county_rows(rid, osn, eid)
        tally = collections.Counter()
        parties = {}
        # One row per candidate per county. The previous reader summed every numeric
        # field on a row, which counted TotalPrecincts and BallotOrder as candidates
        # and collapsed the real ones together.
        per = {}
        for r in rows:
            cty = str(r.get("CountyName") or "").strip().title()
            who = re.sub(r"\s+", " ", str(r.get("calcCandidate") or "")).strip()
            if not cty or not who:
                continue
            v = int(r.get("calcCandidateVotes") or 0)
            parties.setdefault(who, PARTY.get(str(r.get("PartyCode") or "").upper(), "O"))
            rec = per.setdefault(cty, {"ch": collections.Counter(), "pr": None, "pt": None})
            rec["ch"][who] += v
            tally[who] += v
            if r.get("PrecinctsReporting") is not None:
                rec["pr"] = int(r["PrecinctsReporting"])
            if r.get("TotalPrecincts") is not None:
                rec["pt"] = int(r["TotalPrecincts"])
        for cty, rec0 in per.items():
            rec = counties.setdefault(cty, {"races": {}})
            rec["races"][race] = {
                "choices": {c: {"party": parties.get(c, "O"), "votes": v}
                            for c, v in rec0["ch"].most_common()},
                "counted": sum(rec0["ch"].values()),
                "precincts_reporting": rec0["pr"],
                "precincts_total": rec0["pt"],
                "early_and_mail_cast": cast.get(early_cast_shared.ckey(cty)),
            }
            if sum(rec0["ch"].values()):
                any_votes = True
        totals[race] = {
            "contest_name": name, "race_id": rid,
            "choices": dict(tally.most_common()),
            "parties": parties,
            "total": sum(tally.values()),
            "precincts_total": meta.get("precincts_total"),
            "early_and_mail_cast": sum(cast.values()) if cast else None,
        }
    return counties, totals, any_votes, picked, meta, cast_as_of


def main():
    # --proof <eid> runs the whole build against a PAST Nebraska election, where the
    # votes are real. Proving it against tonight's feed proves only that the call is
    # answered: every total is zero until polls close, so the vote-reading path would be
    # untested at the moment it matters. It returns before write_or_hold, so a proof run
    # never writes a results file.
    #
    # The eid is the archive election id the site's own scripts take as ?eid=<n>; the
    # page itself is the listing (resultsSW.aspx?type=SW&map=CTY&eid=<n> answers 200 for
    # an archived election and 302s to ErrorPages/Error.aspx for one it does not hold).
    if "--proof" in sys.argv:
        i = sys.argv.index("--proof")
        if len(sys.argv) <= i + 1:
            raise RuntimeError("--proof needs an archive election id, e.g. --proof 25")
        eid = sys.argv[i + 1]
        counties, totals, any_votes, picked, meta, _ = build(eid)
        print(f"NE proof via archive election {eid} "
              f"({meta.get('election_date','?')} {meta.get('election_type','?')}): "
              f"{len(counties)} counties, read any votes: {any_votes}")
        for race, t in totals.items():
            print(f"   {race}: {t['total']:,} votes  no mode split (Nebraska's county "
                  f"map data carries none)  precincts "
                  f"{meta.get('precincts_reporting')}/{t['precincts_total']}")
            print(f"      contest {t['contest_name']!r}  race_id {t['race_id']}")
            for c, v in list(t["choices"].items())[:4]:
                print(f"      {str(c)[:38]:40} {v:>10,}  {t['parties'].get(c)}")
            tie = sum(t["choices"].values())
            print(f"      candidate sum {tie:,} vs race total {t['total']:,} — "
                  f"{'TIES' if tie == t['total'] else 'DOES NOT TIE'}")
        for nm, rec in list(counties.items())[:3]:
            r = list(rec["races"].values())[0]
            print(f"   {nm}: {r['counted']:,} counted, "
                  f"{r['precincts_reporting']}/{r['precincts_total']} precincts")
        return 0

    counties, totals, any_votes, picked, meta, cast_as_of = build()

    if not any_votes:
        print(f"NE: results not published yet — the service answers for "
              f"{', '.join(v[0] for v in picked.values())} but carries no votes "
              f"(page last updated {meta.get('updated','?')})")
        return 2

    payload = {
        "state": "NE", "unit": "county", "source_kind": "nebraska-enr",
        "election": "2026 General", "feed_updated": meta.get("updated"),
        "registered": meta.get("registered"),
        "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "early_cast_as_of": cast_as_of,
        "counties": counties, "state_totals": totals,
        "source": f"{SVC}/GetMapData (county map data behind the results page)",
        "notes": {
            "modes": "Nebraska's county map data carries no early/election-day split, so "
                     "the precinct scaling stays off here unless a split appears.",
            "election_day": "Ballots still to come on election day are not estimated.",
        },
    }
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "results-NE.json"
    rc = election_day.write_or_hold("NE", p, payload, totals)
    if rc:
        return rc
    for race, t in totals.items():
        print(f"NE {race}: {t['total']:,} counted across {len(counties)} counties")
    print(f"   -> {p.name}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as e:
        print(f"NE RESULTS FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
