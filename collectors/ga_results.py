#!/usr/bin/env python3
"""Georgia election-night results by county -> data/results-GA.json

Georgia used to publish through Clarity, and clarity_results.py still carries GA in its
HOSTS. That path is dead: results.enr.clarityelections.com/GA/elections.json still
answers, but its list stops at the June 2024 primary and every detail path under it now
returns 403, while results.sos.ga.gov has no Clarity path structure at all. The GA rows
in clarity_results.py can therefore never find a 2026 election, and because
find_election returning None is reported as "not staged yet", the failure was
indistinguishable from the expected pre-election state.

Georgia's replacement is an Angular front end over a JSON API, discovered by watching
what the page itself fetches:

    /results/public/api/jurisdictions/Georgia
        -> .elections[]  each {publicElectionId, electionDate, name}
           publicElectionId is a readable slug, e.g. "GeneralPrimary51926"
        -> .voterRegistration is NOT here; the county roster comes from the election
    /results/public/api/elections/Georgia/<publicElectionId>/data
        -> .ballotItems[]        every contest, statewide, with summaryResults
        -> .localityElections[]  one per county: ballotsCast, totalVoters,
                                 precinctsReporting
        -> .voterRegistration[]  one per county: localityName, total
    /results/public/api/elections/<county-slug>/<publicElectionId>/data
        -> the same shape for one county, where the slug is the county name
           lowercased with "-county-ga" appended: "appling-county-ga"

A contest's summaryResults.ballotOptions[] carries, per candidate, voteCount and
groupResults[] - the mode split, as {groupId, groupName, voteCount}. The four groups are
Election Day, Advance Voting, Absentee by Mail and Provisional. groupName is present at
both state and county level and the groupIds are identical between them, so modes are
read directly and never inferred from position.

Costs 160 requests per pull (one statewide, 159 counties). That is the price of
county-level Georgia: there is no single file that carries it.

Exit 2 means Georgia has not staged the November 2026 general yet - which is still true
as of writing: the newest election in the list is 25 August 2026. Any other problem
raises and writes nothing.
"""
import collections
import concurrent.futures
import json
import pathlib
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

import early_cast as early_cast_shared
import election_day

HOST = "https://results.sos.ga.gov"
API = f"{HOST}/results/public/api"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept": "application/json,*/*", "Accept-Encoding": "gzip"}
# Matched case-insensitively against the contest name. The general drops the party
# suffix the primary carries ("US Senate - Rep"), so anchor on the office and refuse a
# primary's party-split contests rather than silently summing one party's votes.
WANT = {"senate": r"^US Senate\b|^United States Senat",
        "governor": r"^Governor\b"}
PARTY = {"DEM": "D", "REP": "R", "D": "D", "R": "R"}
MODE_MAP = {"election day": "election_day", "advance voting": "early",
            "absentee by mail": "mail", "provisional": "provisional",
            "advanced voting": "early", "early voting": "early",
            "absentee by mail - uocava": "mail", "uocava": "mail"}
EARLY_MODES = ("early", "mail")


def get(url, timeout=90):
    """Cloudflare fronts this host and gzips regardless of what is asked for."""
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError(f"{url}: HTTP {r.status}")
        body = r.read()
        enc = (r.headers.get("Content-Encoding") or "").lower()
    if enc == "gzip" or body[:2] == b"\x1f\x8b":
        import gzip
        body = gzip.decompress(body)
    text = body.decode("utf-8", "ignore")
    if text.lstrip().startswith("<"):
        raise RuntimeError(f"{url}: served HTML, not JSON - Cloudflare challenge?")
    if not text.strip():
        raise RuntimeError(f"{url}: empty body")
    return json.loads(text)


def txt(field):
    """These name fields are lists of {languageId, text}; take the English one."""
    if isinstance(field, str):
        return field.strip()
    for e in field or []:
        if (e or {}).get("languageId") in (None, "en"):
            return (e.get("text") or "").strip()
    return ""


def find_election(year=2026):
    """The November general for `year`, or None when Georgia has not staged it."""
    j = get(f"{API}/jurisdictions/Georgia")
    els = j.get("elections") or []
    if not els:
        raise RuntimeError("jurisdictions/Georgia carried no elections list")
    for e in els:
        if (e.get("electionDate") or "") == f"{year}-11-03":
            return e.get("publicElectionId"), txt(e.get("name"))
    # Date is authoritative, but a date typo should not hide a staged election.
    for e in els:
        d, n = (e.get("electionDate") or ""), txt(e.get("name"))
        if d.startswith(f"{year}-11") and re.search(r"general", n, re.I) \
           and not re.search(r"primary|runoff|special|recount", n, re.I):
            return e.get("publicElectionId"), n
    newest = max((e.get("electionDate") or "") for e in els)
    return None, f"newest staged election is {newest}"


def county_slug(name):
    """'Appling County' -> 'appling-county-ga', the slug the API wants."""
    base = re.sub(r"\s+county\s*$", "", name.strip(), flags=re.I)
    return re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-") + "-county-ga"


def contests_of(data, where):
    """{race -> ballotItem} for the races this board tracks.

    A primary carries one contest per party ("US Senate - Rep" and "US Senate - Dem").
    Those must not both match, or one party's votes would be reported as the whole
    contest, so a double match raises instead.
    """
    out, seen = {}, {}
    for b in data.get("ballotItems") or []:
        name = txt(b.get("name"))
        race = next((k for k, pat in WANT.items() if re.search(pat, name, re.I)), None)
        if race is None:
            continue
        if race in seen and seen[race] != name:
            raise RuntimeError(f"{where}: {race!r} matched two contests: "
                               f"{seen[race]!r} and {name!r}")
        seen[race] = name
        out[race] = b
    return out, seen


def options_of(item):
    """{candidate -> {party, votes, by_mode}} for one contest."""
    out = {}
    for o in ((item.get("summaryResults") or {}).get("ballotOptions") or []):
        name = txt(o.get("name"))
        if not name:
            continue
        modes = collections.Counter()
        for g in o.get("groupResults") or []:
            gname = txt(g.get("groupName"))
            key = MODE_MAP.get(gname.lower())
            if key is None:
                raise RuntimeError(f"unrecognised vote group {gname!r} - add it to "
                                   f"MODE_MAP rather than letting its votes be dropped")
            modes[key] += g.get("voteCount") or 0
        out[name] = {"party": PARTY.get(txt((o.get("party") or {}).get("abbreviation")
                                            or "").upper(), "O"),
                     "votes": o.get("voteCount") or 0,
                     "by_mode": dict(modes)}
    return out


def reporting_of(item):
    rs = item.get("reportingStatus") or {}
    return rs.get("reportingUnits"), rs.get("totalUnits")


def county_roster(state_data):
    """County name -> {registered, ballots_cast} from the statewide payload."""
    reg = {}
    for v in state_data.get("voterRegistration") or []:
        n = txt(v.get("localityName"))
        if n:
            reg[n] = {"registered": v.get("total"), "ballots_cast": None}
    # localityElections is parallel per county but carries the election name, not the
    # county's, so ballotsCast is matched by position against voterRegistration only
    # when the two lists are the same length.
    les = state_data.get("localityElections") or []
    if len(les) == len(reg):
        for n, le in zip(list(reg), les):
            reg[n]["ballots_cast"] = le.get("ballotsCast")
            reg[n]["precincts_reporting"] = le.get("precinctsReporting")
    if not reg:
        raise RuntimeError("statewide payload carried no county roster")
    return reg


# Georgia's early-vote file spells counties uppercase with no spaces (DEKALB, BENHILL,
# MCDUFFIE), while the results API spells them "DeKalb County", "Ben Hill County",
# "McDuffie County". .title() turned DEKALB into "Dekalb", which matches neither, so five
# counties silently got cast=None - DeKalb among them, holding 240,254 early ballots. The
# per-county outstanding then summed 249,868 short and the board projected a Georgia
# total BELOW its own early vote. Match on letters only, case-folded.
def _ckey(s):
    return "".join(ch for ch in str(s).upper() if ch.isalnum())


def early_cast():
    return early_cast_shared.by_unit("GA", key=_ckey)


def build():
    eid, name = find_election()
    if eid is None:
        print(f"GA: November 2026 general not staged yet - {name}")
        return 2
    state_data = get(f"{API}/elections/Georgia/{eid}/data")
    state_items, found = contests_of(state_data, "Georgia")
    if not state_items:
        raise RuntimeError(f"none of {sorted(WANT)} found among Georgia's contests")
    roster = county_roster(state_data)
    cast, cast_as_of = early_cast()
    elec = state_data.get("election") or {}
    feed_ts = elec.get("asOf") or elec.get("lastUpdated") or ""

    # 159 counties fetched one after another took about 7 minutes - 75% of the whole
    # election-night run, and it set the cadence for every other state. The requests are
    # independent, so they go out together. Six at a time is deliberate: enough to turn
    # 7 minutes into about one, gentle enough not to look like an attack on the
    # Secretary of State's API on the night it matters most. Any single county failing
    # still raises exactly as before - a partial Georgia is never published.
    # One transient reset on one county used to kill the whole Georgia pull, because a
    # partial Georgia is never published. At six concurrent requests that happened about
    # one run in three, which on the night would mean Georgia going dark for a tick for
    # no reason. Three tries with a short backoff; still raises if a county is genuinely
    # unreachable, so the all-or-nothing guarantee is unchanged.
    def fetch(cname):
        last = None
        for attempt in range(3):
            try:
                return cname, get(f"{API}/elections/{county_slug(cname)}/{eid}/data",
                                  timeout=60)
            except Exception as exc:
                last = exc
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"{cname}: {last}") from last

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        fetched = dict(pool.map(fetch, sorted(roster)))

    counties = {}
    for cname in sorted(roster):
        cd = fetched[cname]
        items, _ = contests_of(cd, cname)
        meta = roster[cname]
        out = {}
        for race, item in items.items():
            choices = options_of(item)
            modes = collections.Counter()
            for ch in choices.values():
                modes.update(ch["by_mode"])
            counted_early = sum(modes[m] for m in EARLY_MODES)
            was = (cast.get(_ckey(cname))
                   or cast.get(_ckey(re.sub(r"\s+County$", "", cname))))
            pr_in, pr_all = reporting_of(item)
            out[race] = {
                "choices": {c: v for c, v in sorted(choices.items(),
                                                    key=lambda x: -x[1]["votes"])},
                "modes": dict(modes),
                "counted": sum(modes.values()),
                "precincts_total": pr_all,
                "precincts_reporting": pr_in,
                "registered": meta.get("registered"),
                "ballots_cast": meta.get("ballots_cast"),
                "early_and_mail_cast": was,
                "early_and_mail_counted": counted_early,
                "early_and_mail_left": (max(0, was - counted_early)
                                        if was is not None else None),
            }
        if out:
            counties[cname] = out

    state_tot = collections.defaultdict(
        lambda: {"choices": collections.Counter(), "modes": collections.Counter(),
                 "parties": {}})
    for race, item in state_items.items():
        for c, v in options_of(item).items():
            state_tot[race]["choices"][c] += v["votes"]
            state_tot[race]["modes"].update(v["by_mode"])
            state_tot[race]["parties"][c] = v["party"]

    cast_tot = sum(cast.values()) if cast else None
    state = {}
    for race, s in state_tot.items():
        counted_early = sum(s["modes"][m] for m in EARLY_MODES)
        pr_in, pr_all = reporting_of(state_items[race])
        state[race] = {
            "contest_name": found.get(race),
            "choices": dict(s["choices"].most_common()),
            "parties": s["parties"],
            "total": sum(s["choices"].values()),
            "modes": dict(s["modes"]),
            "precincts_reporting": pr_in,
            "precincts_total": pr_all,
            "early_and_mail_cast": cast_tot,
            "early_and_mail_counted": counted_early,
            "early_and_mail_left": (max(0, cast_tot - counted_early)
                                    if cast_tot is not None else None),
        }

    payload = {
        "state": "GA", "unit": "county", "source_kind": "ga-sos-api",
        "election": txt(elec.get("name")) or name,
        "election_date": elec.get("electionDate") or "",
        "feed_timestamp": feed_ts, "version": eid,
        "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "early_cast_as_of": cast_as_of,
        "counties": counties, "state_totals": state,
        "source": f"{API}/elections/Georgia/{eid}/data",
        "notes": {
            "modes": "Votes split by mode; early and mail are never pooled with "
                     "election day, because they break in opposite directions. "
                     "Georgia names them Advance Voting and Absentee by Mail.",
            "left": "early_and_mail_left is measured - ballots recorded cast early or "
                    "by mail in that county, minus those modes as counted here.",
            "election_day": "Ballots still to come on election day are not estimated; "
                            "only precincts not yet reporting are shown.",
            "source_change": "Georgia left Clarity: the legacy host 403s on every "
                             "detail path and its election list stops at June 2024. "
                             "This reads the SOS results API the live site itself uses.",
        },
    }
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "results-GA.json"
    rc = election_day.write_or_hold("GA", p, payload, state)
    if rc:
        return rc
    for race, s in state.items():
        print(f"GA {race}: {s['total']:,} counted  precincts "
              f"{s['precincts_reporting'] or 0:,}/{s['precincts_total'] or 0:,}  "
              f"early+mail left "
              f"{s['early_and_mail_left'] if s['early_and_mail_left'] is not None else '?'}")
    print(f"   -> {p.name} ({len(counties)} counties, feed {feed_ts})")
    return 0


def proof(eid):
    """Run the whole parse against a named past election and print what it found.

    An empty November feed proves only that the fetch works. This exercises the parser
    on an election that actually has votes in it, and writes nothing, so it can be run
    any time. A primary legitimately carries one contest per party, so the double-match
    guard firing is the expected answer there rather than a failure.
    """
    state_data = get(f"{API}/elections/Georgia/{eid}/data")
    elec = state_data.get("election") or {}
    print(f"GA proof via {HOST} (election {eid})")
    print(f"   {txt(elec.get('name'))}  {elec.get('electionDate')}  "
          f"as of {elec.get('asOf')}")
    try:
        items, found = contests_of(state_data, "Georgia")
    except RuntimeError as e:
        if "matched two contests" not in str(e):
            raise
        print(f"   {e}")
        print("   (expected for a primary - the general carries one contest per race)")
        items, found = {}, {}
        for b in state_data.get("ballotItems") or []:
            n = txt(b.get("name"))
            if re.search(r"^US Senate\b", n, re.I):
                items[n] = b
        found = {k: k for k in items}
    roster = county_roster(state_data)
    print(f"   counties {len(roster)}  contests matched "
          f"{ {k: txt(v.get('name')) for k, v in items.items()} }")
    reg = sum(v.get("registered") or 0 for v in roster.values())
    cast = sum(v.get("ballots_cast") or 0 for v in roster.values())
    print(f"   registered {reg:,}  ballots cast {cast:,}")
    for race, item in items.items():
        pr_in, pr_all = reporting_of(item)
        opts = options_of(item)
        modes = collections.Counter()
        for v in opts.values():
            modes.update(v["by_mode"])

        print(f"   {race}: {sum(v['votes'] for v in opts.values()):,} votes  "
              f"precincts {pr_in or 0:,}/{pr_all or 0:,}  modes {dict(modes)}")
        for c, v in sorted(opts.items(), key=lambda x: -x[1]["votes"])[:4]:
            print(f"      {c:<34}{v['party']}  {v['votes']:>9,}  {v['by_mode']}")
    # one county, end to end, to prove the per-county path and the slug
    cname = sorted(roster)[0]
    cd = get(f"{API}/elections/{county_slug(cname)}/{eid}/data", timeout=60)
    # Match the county's contests by the exact names the statewide pass settled on, so a
    # primary's party-split contests are reported separately here too instead of
    # tripping the double-match guard that is correct for build().
    citems = {n: b for b in (cd.get("ballotItems") or [])
              for n in [txt(b.get("name"))] if n in items}
    if not citems:
        citems, _ = contests_of(cd, cname)
    print(f"   {cname} via {county_slug(cname)}: "
          f"{len(cd.get('ballotItems') or [])} ballot items")
    for race, item in citems.items():
        opts = options_of(item)
        pr_in, pr_all = reporting_of(item)
        print(f"      {race}: {sum(v['votes'] for v in opts.values()):,} votes, "
              f"precincts {pr_in or 0}/{pr_all or 0}")
    return 0


if __name__ == "__main__":
    if "--proof" in sys.argv:
        i = sys.argv.index("--proof")
        if len(sys.argv) <= i + 1:
            sys.exit("--proof needs an election id, e.g. --proof 2024NovGen   (--list shows every staged election)")
        sys.exit(proof(sys.argv[i + 1]))
    if "--list" in sys.argv:
        j = get(f"{API}/jurisdictions/Georgia")
        els = sorted(j.get("elections") or [],
                     key=lambda e: e.get("electionDate") or "", reverse=True)
        for e in els[:20]:
            print(f"{e.get('electionDate')}  {e.get('publicElectionId'):<40}"
                  f"{txt(e.get('name'))}")
        sys.exit(0)
    sys.exit(build())
