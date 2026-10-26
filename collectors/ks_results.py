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
import collections, json, pathlib, re, sys
from datetime import datetime, timezone
import browser_fetch
import election_day

BASE = "https://ent.sos.ks.gov"
INDEX = f"{BASE}/kssos_ent.html"
# pages on the index that are views, not counties
# Views, not counties. Compared lower-cased because Kansas mixes the casing
# ("Uncontested.html" next to "allen.html").
NOT_COUNTIES = {"kssos_ent", "statewide", "national", "constitutional", "judicial",
                "democratic", "republican", "daysafterelection", "uncontested"}
EXPECT_COUNTIES = 105
# the general drops the (D)/(R) suffix the primary carries
WANT = {"senate": r"^United States Senate$",
        "governor": r"^Governor\s*/\s*Lt\.?\s*Governor$"}
# in a primary the suffix IS the party, which is how the roster gets built
PRIMARY_WANT = {"senate": r"^United States Senate \((D|R)\)$",
                "governor": r"^Governor\s*/\s*Lt\.?\s*Governor \((D|R)\)$"}
DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
ROSTER = DATA / "ks-nominees.json"


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
        raise RuntimeError(f"{url}: no race blocks found — page layout changed")
    return {"title": title, "last_updated": strip(stamps[0]) if stamps else None,
            "county_last_reported": strip(stamps[1]) if len(stamps) > 1 else None,
            "races": races}


def county_slugs(index_html):
    slugs = sorted({m for m in re.findall(r'href="([A-Za-z_]+)\.html', index_html)
                    if m.lower() not in NOT_COUNTIES})
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
    p = DATA / "early-KS.json"
    if not p.exists():
        return {}, None
    d = json.loads(p.read_text())
    out = {}
    for cty, b in (d.get("counties") or {}).items():
        g = lambda k: (b[k].get("total") if isinstance(b.get(k), dict) else b.get(k)) or 0
        out[cty.strip().upper()] = (g("by_mail") + g("mail_returned") + g("returned")
                                    + g("in_person") + g("early_in_person"))
    return out, d.get("as_of")


def proof(b):
    """Parse every county page against whatever election is staged. Writes nothing.

    An exit-2 from the real run only proves the general is not up yet. This walks all
    105 counties so the fetch, the Total Votes cross-check, the percentage check and
    the county naming are all exercised before election night, against real pages.
    """
    index = b.fetch(INDEX)
    slugs = county_slugs(index)
    print(f"KS proof: {len(slugs)} county pages")
    seen, votes, races = {}, 0, collections.Counter()
    for i, slug in enumerate(slugs, 1):
        page = parse(b.fetch(f"{BASE}/{slug}.html"), slug)
        if not page["title"]:
            raise RuntimeError(f"{slug}.html: no \"Results - <county>\" heading")
        cname = page["title"].replace(" County", "").strip()
        if cname in seen:
            raise RuntimeError(f"two pages both named {cname!r}: {seen[cname]}, {slug}")
        seen[cname] = slug
        for name, r in page["races"].items():
            races[name] += 1
            votes += r["counted"]
        if i % 25 == 0 or i == len(slugs):
            print(f"   {i:3d}/{len(slugs)}  last: {cname} "
                  f"({len(page['races'])} races, updated {page['last_updated']})")
    print(f"KS proof: {len(seen)} counties named, {votes:,} votes parsed, "
          f"{len(races)} distinct contests")
    top = [n for n, _ in races.most_common(4)]
    print(f"   contests on every county page: {top}")
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
            return proof(b)

        index = b.fetch(INDEX, ready=lambda h: "kssos_ent" in h or "allen.html" in h)
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
                    choices[c["name"]] = {
                        "party": party_of.get((race, c["name"].strip().lower()), "O"),
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
                "choices": {c["name"]: c["votes"] for c in src["candidates"]},
                "parties": {c["name"]: party_of.get((race, c["name"].strip().lower()), "O")
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
