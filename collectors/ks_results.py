#!/usr/bin/env python3
"""Kansas election-night results by county -> data/results-KS.json

Kansas publishes one static HTML page per county at ent.sos.ks.gov, which would be the
easiest feed of the lot except that the whole host sits behind a Cloudflare browser
challenge. Plain requests get an identical 703KB "Just a moment..." page every time,
with or without full browser headers, and headless Chrome gets the same thing even
with JavaScript running and a 45-second wait - headless is what the challenge objects
to. A normal windowed Chrome clears it in a couple of seconds, so that is what this
uses (see browser_fetch.py). The cost is that Kansas runs from the laptop, not the
cron VM, like Maine.

Two page layouts, both parsed here:

    county pages    "County Precincts Reporting: 587 of 587"
                    rows of name | county votes | county % | state votes | state %
    statewide.html  "Precincts Reporting: 4150 of 4150"
    national.html   rows of name | votes | %

The parse is checked against the page's own percentages on every run: each candidate's
votes over the race total must land within a point of the percentage Kansas printed.
That caught nothing on the 2026 primary (22 races, zero mismatches), which is the
point - it is the check that would catch a layout change.

PARTY IS NOT IN THE FEED. Kansas labels no candidate with a party anywhere in the DOM;
its "By Party" menu only filters which primary's races you see. In a primary the party
is in the race name - "United States Senate (R)" - but in the general those suffixes
are gone and the candidates are unlabelled. Her board splits by party, so the party has
to come from somewhere, and the honest source is Kansas's own primary: whoever won
"United States Senate (D)" is the D nominee. Run

    ks_results.py --nominees

while the primary is still the staged election to bank that roster into
data/ks-nominees.json. It is read back on election night and anyone not on it is "O".

Exit 2 means Kansas has not published general-election results yet. Any other problem
raises and writes nothing.
"""
import collections, json, pathlib, re, sys, time
from datetime import datetime, timezone
import early_cast as early_cast_shared
import browser_fetch
import election_day

BASE = "https://ent.sos.ks.gov"
INDEX = f"{BASE}/kssos_ent.html"
# Where the PREVIOUS elections' sites are still served, unlinked, in the same layout:
# https://kssos.org/ent/<Year><Primary|General>/kssos_ent.html, 2012General onward.
# Read by --proof only; see proof() for how this was found and why it is needed.
ARCHIVE = "https://kssos.org/ent"
# pages on the index that are views, not counties
# Views, not counties. Compared lower-cased because Kansas mixes the casing
# ("Uncontested.html" next to "allen.html").
NOT_COUNTIES = {"kssos_ent", "statewide", "national", "constitutional", "judicial",
                "democratic", "republican", "daysafterelection", "uncontested"}
EXPECT_COUNTIES = 105
# the general drops the (D)/(R) suffix the primary carries
# Kansas also elects a governor in 2026; this board does not track it.
WANT = {"senate": r"^United States Senate$"}
# in a primary the suffix IS the party, which is how the roster gets built
PRIMARY_WANT = {"senate": r"^United States Senate \((D|R)\)$"}
DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
ROSTER = DATA / "ks-nominees.json"


# On the GENERAL ballot Kansas prefixes the party onto the name - "D-Adam Hamilton",
# "R-Roger Marshall", "L-David C Graham" - which is not how the primary listed them.
# Left alone, the roster lookup misses every name and the whole ballot reads party "O".
PARTY_PREFIX = re.compile(r"^\s*([DRLIG])\s*-\s*(.+)$")
PREFIX_PARTY = {"D": "D", "R": "R", "L": "O", "I": "O", "G": "O"}


def split_party(name):
    """('Adam Hamilton', 'D') from 'D-Adam Hamilton'; (name, None) when unprefixed."""
    m = PARTY_PREFIX.match(name or "")
    if not m:
        return (name or "").strip(), None
    return m.group(2).strip(), PREFIX_PARTY.get(m.group(1))


def strip(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).replace(" ", " ") \
             .replace("&nbsp;", " ").strip()


def as_int(s):
    t = strip(s).replace(",", "")
    return int(t) if re.fullmatch(r"-?\d+", t) else None


def parse(html, url):
    """One results page -> {title, last_updated, races:{name:{...}}}."""
    titles = [strip(m) for m in re.findall(r"<h1[^>]*>.*?</h1>", html, re.S)]
    title = next((re.sub(r"^Results\s*-\s*", "", t) for t in titles
                  if t.startswith("Results -")), None)
    stamps = re.findall(r'<span id="time-stamp">(.*?)</span>', html, re.S)
    races = {}
    for block in re.split(r'<div class="race">', html)[1:]:
        h3 = re.search(r"<h3>(.*?)</h3>", block, re.S)
        if not h3:
            continue
        name = strip(h3.group(1))
        pr = re.search(r"Precincts Reporting:\s*([\d,]+)\s*of\s*([\d,]+)", block)
        cl = re.search(r'<div class="race-candidate-list">(.*?)'
                       r'(?=<div class="race-details|<div class="race-legend|$)',
                       block, re.S)
        cands, stated_total = [], None
        if cl:
            for row in re.split(r'<div class="row">', cl.group(1))[1:]:
                cells = re.findall(r"<p>(.*?)</p>", row, re.S)
                if len(cells) < 3:
                    continue  # spacer rows
                who, votes = strip(cells[0]), as_int(cells[1])
                if not who or votes is None:
                    continue
                # Kansas ends each race with its own "Total Votes" line. Counting it as
                # a candidate doubles the race (it did, on the first run), so it is
                # pulled out and used as the check on our own sum instead.
                if who.lower().startswith("total vote"):
                    stated_total = votes
                    continue
                cands.append({"name": who, "votes": votes, "pct": strip(cells[2])})
        if not cands:
            continue
        total = sum(c["votes"] for c in cands)
        if stated_total is not None and stated_total != total:
            raise RuntimeError(f"{url}: {name}: candidates sum to {total:,} but Kansas "
                               f"prints Total Votes {stated_total:,}")
        # The page prints its own percentages too; if ours disagree, the layout moved
        # and the columns no longer mean what this parser thinks they mean.
        for c in cands:
            stated = re.match(r"([\d.]+)\s*%", c["pct"])
            if stated and total:
                calc = 100.0 * c["votes"] / total
                if abs(float(stated.group(1)) - calc) > 1.0:
                    raise RuntimeError(
                        f"{url}: {name} / {c['name']}: page says {c['pct']}, "
                        f"{c['votes']:,} of {total:,} is {calc:.1f}% — column layout "
                        f"changed")
        races[name] = {
            "precincts_reporting": int(pr.group(1).replace(",", "")) if pr else None,
            "precincts_total": int(pr.group(2).replace(",", "")) if pr else None,
            "candidates": cands, "counted": total,
            "stated_total": stated_total,
        }
    if not races:
        # Distinguish "this county has posted nothing yet" from "the page we are
        # parsing is not the page we think it is". A real Kansas results page carries
        # the title and the Last Updated stamp whether or not any race is on it;
        # Smith County served exactly that tonight, and treating it as a layout change
        # failed the whole state for one empty county.
        looks_right = bool(title)
        if looks_right:
            return {"title": title, "last_updated": strip(stamps[0]),
                    "county_last_reported": strip(stamps[1]) if len(stamps) > 1 else None,
                    "races": {}}
        raise RuntimeError(f"{url}: no race blocks found — page layout changed")
    return {"title": title, "last_updated": strip(stamps[0]) if stamps else None,
            "county_last_reported": strip(stamps[1]) if len(stamps) > 1 else None,
            "races": races}


def county_slugs(index_html):
    """Every county page the index offers, however the index chooses to offer it.

    Kansas moved its county links out of <a href="allen.html"> and into a dropdown,
    <select id="county-ddl"><option value="allen.html">Allen</option>. Reading only
    href= found 98 of the wrong things and none of the counties, and the count check
    below turned that into a hard failure on election night. Both attributes are read
    now, so the page can go back to links, stay a dropdown, or carry both.
    """
    found = (re.findall(r'href="([A-Za-z_]+)\.html', index_html)
             + re.findall(r'value="([A-Za-z_]+)\.html', index_html))
    slugs = sorted({m for m in found if m.lower() not in NOT_COUNTIES})
    if len(slugs) != EXPECT_COUNTIES:
        raise RuntimeError(f"index listed {len(slugs)} county pages, expected "
                           f"{EXPECT_COUNTIES} — Kansas has 105 counties")
    return slugs


def feed_date(page):
    """The date Kansas stamped on the page, as a date, or None."""
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", page.get("last_updated") or "")
    if not m:
        return None
    return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2))).date()


def match_races(names, patterns):
    out = {}
    for race, pat in patterns.items():
        for n in names:
            m = re.match(pat, n, re.I)
            if m:
                out.setdefault(race, []).append((n, m.groups()[0] if m.groups() else None))
    return out


# -- nominee roster -------------------------------------------------------------
def build_roster(b):
    """Bank each party's nominee from the staged primary into data/ks-nominees.json."""
    pages = {u: parse(b.fetch(f"{BASE}/{u}.html"), u) for u in ("national", "statewide")}
    roster, where = {}, {}
    for page_name, page in pages.items():
        found = match_races(page["races"], PRIMARY_WANT)
        for race, hits in found.items():
            for name, party in hits:
                cands = page["races"][name]["candidates"]
                win = max(cands, key=lambda c: c["votes"])
                if win["votes"] == 0:
                    continue
                roster.setdefault(race, {})
                if party in roster[race] and roster[race][party] != win["name"]:
                    raise RuntimeError(f"{race} {party}: two nominees "
                                       f"({roster[race][party]} and {win['name']})")
                roster[race][party] = win["name"]
                where[f"{race}/{party}"] = f"{name} on {page_name}.html"
    if not roster:
        raise RuntimeError("no party-primary races on national.html or statewide.html — "
                           "is the primary still the staged election?")
    stamp = feed_date(pages["national"])
    doc = {"state": "KS", "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "from_feed_dated": stamp.isoformat() if stamp else None,
           "nominees": roster, "derived_from": where,
           "why": "Kansas publishes no party per candidate. These are the primary "
                  "winners from Kansas's own pages, used to label the general."}
    ROSTER.write_text(json.dumps(doc, indent=1) + "\n")
    for race, parties in sorted(roster.items()):
        for p, who in sorted(parties.items()):
            print(f"KS {race} {p}: {who}")
    print(f"   -> {ROSTER.name} (from the primary dated {stamp})")
    return 0


def roster():
    if not ROSTER.exists():
        return {}, None
    d = json.loads(ROSTER.read_text())
    out = {}
    for race, parties in (d.get("nominees") or {}).items():
        for p, who in parties.items():
            out[(race, who.strip().lower())] = p
    return out, d.get("from_feed_dated")


# -- election night -------------------------------------------------------------
def early_cast():
    """Early + mail ballots cast per unit, from the shared reader.

    This was a local copy that added up every stream name it knew. Those names
    are aliases, so a payload carrying two for one stream had it counted twice -
    Florida writes both early_in_person and in_person and was over by 2,880,909,
    the whole in-person vote again. early_cast.by_unit takes one stream per mode.
    """
    return early_cast_shared.by_unit("KS", key=lambda s: s.strip().upper())


def proof(b, election=None):
    """Run the whole election-night read against a PAST Kansas election. Writes nothing.

    Pointed at the staged election (no argument) this proves only that the pages parse:
    every total is zero until polls close, so the VOTE-READING path - the Total Votes
    cross-check, the printed-percentage check and the county-sum-versus-statewide check,
    which are the three things that would catch a layout change - is never exercised at
    all. `--proof <election>` runs it where the votes are real.

    Finding the past election. ent.sos.ks.gov is a flat static site that is replaced
    each election: it carries only the staged one, with no archive link, no election id
    and no directory index (probed 2026-11-03), and sos.ks.gov/elections/election-
    results.html publishes only official-totals PDFs and precinct-level xlsx - a
    different format this parser cannot read - noting that unofficial results are
    "available upon request". The previous sites are still served, unlinked, at

        https://kssos.org/ent/<Year><Primary|General>/kssos_ent.html

    in the same layout and with the same county filenames, for 2012General through
    2026Primary. So `election` is that folder name - 2022General - or a full base URL.

    One archive difference, reported rather than papered over: the staged site has a
    Statewide tab (statewide.html) and the older ones do not, so statewide totals come
    from whichever of national.html / statewide.html the election serves plus the
    index's own All-Races block, which every one of them carries.

    early_cast() is deliberately not read here: it is this board's 2026 early-vote
    ledger and has nothing to say about a past election's counties.
    """
    base = election if (election or "").startswith("http") else (
        f"{ARCHIVE}/{election}" if election else BASE)
    # kssos.org sits behind a CloudFront WAF that blocks a burst: walking the county
    # pages back to back was cut off at the 27th with "Request blocked" and stayed
    # blocked for about ten minutes. So the archive is read at a crawl, and a block is
    # waited out rather than reported as a layout change or left as a partial proof.
    archive = not base.startswith(BASE)
    # A blocked page is not an empty election. CloudFront's "Request blocked" body and
    # Chrome's own error document for it both arrive as perfectly loadable HTML, so a
    # results page only counts as arrived once it carries a race block - otherwise a
    # block surfaced as "no race blocks found — page layout changed", which is the
    # message that would be believed on election night.
    has_races = lambda h: 'class="race"' in h
    key = lambda s: re.sub(r"[^a-z]", "", (s or "").lower().replace("county", ""))

    def page(url, tries=10, **kw):
        for attempt in range(tries):
            try:
                return b.fetch(url, **kw)
            except RuntimeError as e:
                if not archive or attempt == tries - 1:
                    raise
                print(f"   {url.rsplit('/', 1)[-1]}: blocked or empty "
                      f"({str(e)[-38:]}) — waiting 180s")
                time.sleep(180)

    print(f"KS proof: {base}")
    index = page(f"{base}/kssos_ent.html",
                 ready=lambda h: "allen.html" in h, timeout=120)
    slugs = county_slugs(index)

    # The statewide documents, read as the live run reads them. A missing one is named
    # and skipped rather than fatal, because the archived elections predate the
    # Statewide tab; the index's All-Races block is what they carry instead. tries=2,
    # since a long retry on a page that is simply absent would stall the proof.
    pages = {}
    for nm in ("national", "statewide"):
        try:
            pages[nm] = parse(page(f"{base}/{nm}.html", tries=2, timeout=30,
                                   ready=has_races), nm)
        except RuntimeError as e:
            print(f"   no {nm}.html for this election ({str(e)[:58]}…)")
    pages["kssos_ent"] = parse(index, "kssos_ent")
    names = [n for p in pages.values() for n in p["races"]]
    picked = match_races(names, WANT)
    if not picked:
        raise RuntimeError(f"none of {sorted(WANT)} is on this election's pages "
                           f"({len(set(names))} contests). Kansas elects a US Senator "
                           f"and a Governor in different years, so pick a general that "
                           f"carries them.")
    print(f"   {len(slugs)} county pages, feed dated {feed_date(pages['kssos_ent'])}, "
          f"contests matched: {sorted(picked)}")

    party_of, roster_from = roster()
    counties = {}
    empty = 0
    for i, slug in enumerate(slugs, 1):
        if archive and i > 1:
            time.sleep(3.5)
        for attempt in range(10):
            doc = parse(page(f"{base}/{slug}.html", timeout=30, ready=has_races), slug)
            cname = (doc["title"] or "").replace(" County", "").strip()
            if key(cname) == key(slug):
                break
            # A blocked or stale fetch can hand back a DIFFERENT document that also
            # carries race blocks - the index's own All-Races page did, twice, on the
            # first full walk - so a page is accepted only once it names the county
            # that was asked for. Counting another county's votes as this one's is the
            # one failure that would still tie out and still be wrong.
            print(f"   {slug}.html served {cname!r} — refetching")
            time.sleep(20)
        else:
            raise RuntimeError(f"{slug}.html never served its own page "
                               f"(last title {cname!r})")
        if cname in counties:
            raise RuntimeError(f"two pages both named {cname!r}")
        rec = counties.setdefault(cname, {"races": {}})
        for race, hits in match_races(doc["races"], WANT).items():
            r = doc["races"][hits[0][0]]
            choices = {}
            for c in r["candidates"]:
                nm, pk = split_party(c["name"])
                choices[nm] = {"party": pk or party_of.get((race, nm.strip().lower()), "O"),
                               "votes": c["votes"]}
            rec["races"][race] = {
                "choices": dict(sorted(choices.items(), key=lambda x: -x[1]["votes"])),
                "counted": r["counted"],
                "precincts_reporting": r["precincts_reporting"],
                "precincts_total": r["precincts_total"]}
        if not rec["races"]:
            # No tracked contest on this county's page. Before polls close that is every
            # county; after, it is a county that has not reported. Either way it is not
            # a reason to throw away the other 104.
            if not doc["races"]:
                counties.pop(cname, None)
                empty += 1
                continue
            raise RuntimeError(f"{slug}.html carried none of {sorted(WANT)} "
                               f"(it did carry {sorted(doc['races'])[:4]})")
        if i % 25 == 0 or i == len(slugs):
            print(f"   {i:3d}/{len(slugs)}  last: {cname} "
                  f"({len(doc['races'])} races, updated {doc['last_updated']})")

    totals = {}
    for race, hits in picked.items():
        name = hits[0][0]
        src = next(p["races"][name] for p in pages.values() if name in p["races"])
        totals[race] = {
            "contest_name": name,
            "choices": {split_party(c["name"])[0]: c["votes"] for c in src["candidates"]},
            "parties": {split_party(c["name"])[0]:
                        (split_party(c["name"])[1]
                         or party_of.get((race, split_party(c["name"])[0].lower()), "O"))
                        for c in src["candidates"]},
            "total": src["counted"], "stated_total": src["stated_total"],
            "precincts_reporting": src["precincts_reporting"],
            "precincts_total": src["precincts_total"]}

    # The same two cross-checks the live run makes before it will publish anything.
    for race, t in totals.items():
        for who, votes in t["choices"].items():
            summed = sum((c["races"].get(race, {}).get("choices", {}).get(who, {}) or {})
                         .get("votes", 0) for c in counties.values())
            if summed != votes:
                raise RuntimeError(f"KS {race}: counties sum to {summed:,} for {who} but "
                                   f"the statewide page says {votes:,}")
        rep = sum((c["races"].get(race) or {}).get("precincts_reporting") or 0
                  for c in counties.values())
        if t["precincts_reporting"] is not None and rep != t["precincts_reporting"]:
            raise RuntimeError(f"KS {race}: counties report {rep:,} precincts, statewide "
                               f"page says {t['precincts_reporting']:,}")

    print(f"KS proof: {len(counties)} counties named and read, roster from {roster_from}")
    for race, t in totals.items():
        ssum = sum(t["choices"].values())
        print(f"   {race}: {t['total']:,} votes  precincts "
              f"{t['precincts_reporting']:,}/{t['precincts_total']:,}  ({t['contest_name']})")
        for c, v in sorted(t["choices"].items(), key=lambda x: -x[1])[:5]:
            print(f"      {c[:38]:40} {v:>10,}  {t['parties'].get(c)}")
        print(f"      TIES: candidates sum {ssum:,} == race total {t['total']:,}: "
              f"{ssum == t['total']}; == Kansas's own Total Votes line "
              f"{t['stated_total']:,}: {ssum == t['stated_total']}; "
              f"105 counties sum to the statewide page: True (checked above)")
    print("   no mode split: Kansas publishes no early/election-day breakdown on these "
          "pages, so there is none to tie out")
    print("   nothing written — this is a parse proof, not a results pull")
    return 0


def main(argv):
    # On the cron VM there is no browser, and Kansas without one is not a failure, it
    # is the wrong host - the same answer Maine gives there. Saying so with exit 2
    # keeps election night's every-three-minutes log honest instead of red.
    try:
        browser_fetch.chrome_path()
    except RuntimeError as e:
        print(f"KS: {e} — run this from the laptop, as Maine is")
        return 2

    with browser_fetch.Browser() as b:
        if "--nominees" in argv:
            return build_roster(b)
        if "--proof" in argv:
            # --proof <election> runs the whole read against a PAST election, where the
            # votes are real; bare --proof still parses whatever is staged.
            i = argv.index("--proof")
            return proof(b, argv[i + 1] if len(argv) > i + 1 else None)

        # Wait for the RESULTS page, not for a substring a half-rendered or challenge
        # page can also carry. The run on 11-01 timed out on 1,715,321 bytes that
        # contained neither the title nor a candidate list, while a clean fetch of the
        # same URL was 568,816 bytes with both.
        index = b.fetch(INDEX, ready=lambda h: "Unofficial Kansas Election Results" in h
                                               and "allen.html" in h, timeout=90)
        slugs = county_slugs(index)
        state_page = parse(b.fetch(f"{BASE}/national.html"), "national")
        sw_page = parse(b.fetch(f"{BASE}/statewide.html"), "statewide")
        names = list(state_page["races"]) + list(sw_page["races"])

        picked = match_races(names, WANT)
        if not picked:
            primaries = match_races(names, PRIMARY_WANT)
            stamp = feed_date(state_page)
            if primaries:
                print(f"KS: the staged election is still a primary — races are "
                      f"party-split ({sorted(n for v in primaries.values() for n, _ in v)[:2]}), "
                      f"feed dated {stamp}. Run --nominees to bank the roster.")
            else:
                print(f"KS: neither {sorted(WANT)} is staged yet (feed dated {stamp}); "
                      f"{len(names)} contests on the statewide and national pages")
            return 2

        party_of, roster_from = roster()
        cast, cast_as_of = early_cast()

        counties, any_votes = {}, False
        for slug in slugs:
            page = parse(b.fetch(f"{BASE}/{slug}.html"), slug)
            cname = (page["title"] or slug.title()).replace(" County", "").strip()
            rec = counties.setdefault(cname, {"races": {}})
            for race, hits in match_races(page["races"], WANT).items():
                name = hits[0][0]
                r = page["races"][name]
                choices = {}
                for c in r["candidates"]:
                    nm, pk = split_party(c["name"])
                    choices[nm] = {
                        "party": pk or party_of.get((race, nm.strip().lower()), "O"),
                        "votes": c["votes"]}
                if r["counted"]:
                    any_votes = True
                rec["races"][race] = {
                    "choices": dict(sorted(choices.items(), key=lambda x: -x[1]["votes"])),
                    "counted": r["counted"],
                    "precincts_reporting": r["precincts_reporting"],
                    "precincts_total": r["precincts_total"],
                    "early_and_mail_cast": cast.get(cname.upper()),
                }
            if not rec["races"]:
                raise RuntimeError(f"{slug}.html carried none of {sorted(WANT)}")

        totals = {}
        for race, hits in picked.items():
            name = hits[0][0]
            src = state_page["races"].get(name) or sw_page["races"][name]
            totals[race] = {
                "contest_name": name,
                "choices": {split_party(c["name"])[0]: c["votes"]
                            for c in src["candidates"]},
                "parties": {split_party(c["name"])[0]:
                            (split_party(c["name"])[1]
                             or party_of.get((race, split_party(c["name"])[0].lower()), "O"))
                            for c in src["candidates"]},
                "total": src["counted"],
                "precincts_reporting": src["precincts_reporting"],
                "precincts_total": src["precincts_total"],
                "early_and_mail_cast": sum(cast.values()) if cast else None,
            }

        # The 105 county pages and the statewide page are separate documents that must
        # describe the same election. On the 2026 primary they agreed to the vote on
        # every candidate and to 4,150/4,150 precincts, so a disagreement here means a
        # county went missing, got counted twice, or one of the pages is stale.
        for race, t in totals.items():
            for who, votes in t["choices"].items():
                summed = sum((c["races"].get(race, {}).get("choices", {})
                               .get(who, {}) or {}).get("votes", 0)
                             for c in counties.values())
                if summed != votes:
                    raise RuntimeError(
                        f"KS {race}: counties sum to {summed:,} for {who} but the "
                        f"statewide page says {votes:,}")
            rep = sum((c["races"].get(race) or {}).get("precincts_reporting") or 0
                      for c in counties.values())
            if t["precincts_reporting"] is not None and rep != t["precincts_reporting"]:
                raise RuntimeError(
                    f"KS {race}: counties report {rep:,} precincts, statewide page "
                    f"says {t['precincts_reporting']:,}")

        if not any_votes:
            print(f"KS: {len(counties)} county pages parsed but no votes yet "
                  f"(feed dated {feed_date(state_page)})")
            return 2

        unlabelled = sorted({c for t in totals.values()
                             for c, p in t["parties"].items() if p == "O"})
        payload = {
            "state": "KS", "unit": "county", "source_kind": "ks-sos-enr-html",
            "election": "2026 General",
            "feed_updated": state_page["last_updated"],
            "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "early_cast_as_of": cast_as_of,
            "party_roster_from": roster_from,
            "counties": counties, "state_totals": totals,
            "source": f"{BASE}/<county>.html (+ national.html and statewide.html for "
                      f"state totals), read with a real browser",
            "notes": {
                "party": "Kansas publishes no party per candidate; parties here come "
                         "from data/ks-nominees.json, banked from Kansas's own primary."
                         + (f" Unlabelled, shown as O: {', '.join(unlabelled)}."
                            if unlabelled else ""),
                "modes": "Kansas's county pages carry no early/election-day split, so the "
                         "precinct scaling stays off here unless a split appears.",
                "checked": "Every race is checked against the percentages Kansas prints.",
            },
        }
        rc = election_day.write_or_hold("KS", DATA / "results-KS.json", payload, totals)
        if rc:
            return rc
        for race, t in totals.items():
            print(f"KS {race}: {t['total']:,} counted across {len(counties)} counties "
                  f"({t['precincts_reporting']:,}/{t['precincts_total']:,} precincts)")
        print(f"   -> results-KS.json")
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv) or 0)
    except Exception as e:
        print(f"KS RESULTS FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
