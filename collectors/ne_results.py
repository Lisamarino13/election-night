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

SVC = "https://neresultswebservice.azurewebsites.us/ResultsAjax.svc"
PAGE = "https://electionresults.nebraska.gov/resultsSW.aspx?type=SW&map=CTY"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept": "application/json,*/*", "Accept-Encoding": "gzip"}
WANT = {"senate": r"United States Senator"}
PARTY = {"REPUBLICAN": "R", "DEMOCRAT": "D", "DEMOCRATIC": "D"}


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


def contests():
    """Contest name -> the ids the service wants, read off the results page itself."""
    html = get(PAGE, timeout=120, as_json=False)
    out = {}
    # Each contest is a heading followed by its "Follow This Contest" checkbox, whose id
    # carries the race id. Pairing them is how a contest name maps to an id without any
    # documented listing.
    for m in re.finditer(r"<h1>(.*?)</h1>(.*?)(?=<h1>|$)", html, re.S):
        name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1))).strip()
        chk = re.search(r'id="chk-(\d+)"', m.group(2))
        if name and chk:
            out[name] = int(chk.group(1))
    if not out:
        raise RuntimeError("results page carried no contest headings — layout changed")
    meta = {}
    t = re.search(r"Results last updated:\s*([^<]{5,40})", html)
    if t:
        meta["updated"] = re.sub(r"\s+", " ", t.group(1)).strip()
    reg = re.search(r"Registered Voters[^0-9]{0,40}([\d,]+)", html)
    if reg:
        meta["registered"] = int(reg.group(1).replace(",", ""))
    pr = re.search(r"Total\s*([\d,]+)\s*</", html)
    if pr:
        meta["precincts_total"] = int(pr.group(1).replace(",", ""))
    return out, meta


def county_rows(race_id):
    d = get(f"{SVC}/GetMapData?type=SW&category=CTY&raceID={race_id}"
            f"&osn=0&county=0&party=0").get("d")
    if d is None:
        raise RuntimeError(f"GetMapData returned null for race {race_id} — "
                           f"the service rejected the call rather than finding nothing")
    return d


def early_cast():
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "early-NE.json"
    if not p.exists():
        return {}, None
    d = json.loads(p.read_text())
    out = {}
    for cty, b in (d.get("counties") or {}).items():
        g = lambda k: (b[k].get("total") if isinstance(b.get(k), dict) else b.get(k)) or 0
        out[cty.title()] = g("by_mail") + g("mail_returned") + g("returned") \
                           + g("in_person") + g("early_in_person")
    return out, d.get("as_of")


def main():
    found, meta = contests()
    picked = {}
    for name, rid in found.items():
        race = next((k for k, pat in WANT.items() if re.search(pat, name, re.I)), None)
        if race is None:
            continue
        if race in picked and picked[race][0] != name:
            raise RuntimeError(f"{race!r} matched two contests: {picked[race][0]!r} and {name!r}")
        picked[race] = (name, rid)
    if not picked:
        raise RuntimeError(f"none of {sorted(WANT)} among {len(found)} contests on the page")

    cast, cast_as_of = early_cast()
    counties, totals, any_votes = {}, {}, False
    for race, (name, rid) in picked.items():
        rows = county_rows(rid)
        tally = collections.Counter()
        parties = {}
        for r in rows:
            cty = str(r.get("County") or r.get("Name") or "").strip().title()
            if not cty:
                continue
            rec = counties.setdefault(cty, {"races": {}})
            ch = {}
            for k, v in r.items():
                if isinstance(v, (int, float)) and k.lower() not in (
                        "id", "countyid", "raceid", "precinctsreporting",
                        "precinctstotal", "registered", "ballotscast"):
                    ch[k] = int(v)
                    tally[k] += int(v)
            rec["races"][race] = {
                "choices": {c: {"party": parties.get(c, "O"), "votes": v}
                            for c, v in sorted(ch.items(), key=lambda x: -x[1])},
                "counted": sum(ch.values()),
                "precincts_reporting": r.get("PrecinctsReporting"),
                "precincts_total": r.get("PrecinctsTotal"),
                "early_and_mail_cast": cast.get(cty),
            }
            if sum(ch.values()):
                any_votes = True
        totals[race] = {
            "contest_name": name, "race_id": rid,
            "choices": dict(tally.most_common()),
            "parties": parties,
            "total": sum(tally.values()),
            "precincts_total": meta.get("precincts_total"),
            "early_and_mail_cast": sum(cast.values()) if cast else None,
        }

    if not any_votes:
        print(f"NE: results not published yet — the service answers for "
              f"{', '.join(n for n, _ in picked.values())} but carries no votes "
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
    p.write_text(json.dumps(payload, indent=1) + "\n")
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
