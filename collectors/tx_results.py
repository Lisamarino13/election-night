#!/usr/bin/env python3
"""Texas election-night results by county -> data/results-TX.json

Texas publishes election night as static JSON behind its results site, and the file
that matters is County.json: every one of the 254 counties, every race, every
candidate, with

    V   total votes
    EV  EARLY votes (Texas counts mail with early voting)

so election-day votes are V - EV exactly. That split is the one thing a projection
cannot do without, and Texas gives it per candidate per county without any inference.

Each county also carries a Summary:

    RV   registered voters          PRR / PRP  precincts reporting / total
    VC   votes cast                 P          percent reporting
    NPL / PLR  polling locations, which are FEWER than precincts - several precincts
               vote at one location. Reading NPL as the precinct total made the
               statewide figure "9,885 of 5,807 reporting". PLP sums to 25,400 across
               254 counties, i.e. 254 x 100, which is what fixed the reading: the PL*
               fields are a separate polling-location series with its own percent.

The discovery chain, because none of it is documented:

    /static/data/Version.json                      -> the constants version
    /static/data/ElectionConstants_<ver>.json      -> currentelectionInfo, with the
                                                      election ID and its year/type
    /static/data/election/<EID>/Version.json       -> that election's data version
    /static/data/election/<EID>/<ver>/County.json  -> the results

The site sits behind Cloudflare and gzips everything regardless of what is asked for,
so a plain read hands JSON a gzip header and gets an HTML error page instead.

Exit 2 means Texas has not staged the November 2026 election yet - which is still true
as of writing, and is an expected state rather than a failure. Any other problem raises
and writes nothing.
"""
import gzip, json, pathlib, re, sys, urllib.request, collections
from datetime import datetime, timezone
import election_day

BASE = "https://results.texas-election.com/static/data"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept": "application/json,*/*", "Accept-Encoding": "gzip"}
WANT = {"senate": r"U\.?\s*S\.?\s+SENATOR", "governor": r"^GOVERNOR"}
PARTY = {"REP": "R", "DEM": "D"}


def get(url, timeout=120):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError(f"{url}: HTTP {r.status}")
        body = r.read()
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    text = body.decode("utf-8", "ignore")
    if text.lstrip().startswith("<"):
        raise RuntimeError(f"{url}: served HTML, not JSON")
    return json.loads(text)


def find_election(year=2026):
    """The November general for `year`, or None when Texas has not staged it."""
    ver = get(f"{BASE}/Version.json").get("___versionNo")
    if ver is None:
        raise RuntimeError("Version.json carried no ___versionNo")
    const = get(f"{BASE}/ElectionConstants_{ver}.json")
    cur = const.get("currentelectionInfo") or {}
    if str(cur.get("Y")) == str(year) and (cur.get("ET") or "").upper() == "G":
        return cur.get("ID"), cur.get("N")
    # not current yet - look for it by year anyway, in case a later one is current
    by_year = (const.get("electionInfo") or {}).get(str(year)) or {}
    for kind, entries in by_year.items():
        if (kind or "").upper() != "G":
            continue
        for eid, e in (entries or {}).items():
            if re.search(r"NOVEMBER", (e.get("N") or ""), re.I):
                return eid, e.get("N")
    return None, (cur.get("N") or "unknown")


def load_counties(eid):
    v = get(f"{BASE}/election/{eid}/Version.json")
    ver, elec_date = v.get("___versionNo"), v.get("elecDate")
    if ver is None:
        raise RuntimeError(f"election {eid}: no data version")
    counties = get(f"{BASE}/election/{eid}/{ver}/County.json", timeout=240)
    if len(counties) < 200:
        raise RuntimeError(f"only {len(counties)} counties — Texas has 254; refusing")
    return ver, elec_date, counties


def early_cast():
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "early-TX.json"
    if not p.exists():
        return {}, None
    d = json.loads(p.read_text())
    out = {}
    for cty, b in (d.get("counties") or {}).items():
        num = lambda k: (b[k].get("total") if isinstance(b.get(k), dict) else b.get(k)) or 0
        out[cty.upper()] = num("by_mail") + num("in_person") + num("early_in_person")
    return out, d.get("as_of")


def build(eid, name, label=""):
    ver, elec_date, raw = load_counties(eid)
    cast, cast_as_of = early_cast()
    counties, state = {}, collections.defaultdict(
        lambda: {"choices": collections.Counter(), "early": collections.Counter(),
                 "parties": {}})
    found, pr_in, pr_all = {}, 0, 0

    for fips, c in sorted(raw.items()):
        cname = (c.get("N") or "").strip().title()
        summ = c.get("Summary") or {}
        rec = {"fips": fips, "registered": summ.get("RV"), "ballots_cast": summ.get("VC"),
               "precincts_reporting": summ.get("PRR"),
               "precincts_total": summ.get("PRP") or summ.get("PRR"),
               "polling_locations": summ.get("NPL"),
               "percent_reporting": summ.get("P"), "races": {}}
        pr_in += summ.get("PRR") or 0
        pr_all += (summ.get("PRP") or summ.get("PRR") or 0)
        for rid, r in (c.get("Races") or {}).items():
            on = (r.get("ON") or "").strip()
            race = next((k for k, pat in WANT.items() if re.search(pat, on, re.I)), None)
            if race is None:
                continue
            if race in found and found[race] != on:
                raise RuntimeError(f"{race!r} matched two contests: {found[race]!r} and {on!r}")
            found[race] = on
            choices = {}
            for ch in (r.get("C") or {}).values():
                nm = (ch.get("N") or "").strip()
                v, ev = ch.get("V") or 0, ch.get("EV") or 0
                # Texas counts mail ballots with early voting, so EV is the whole
                # early-and-mail figure and the remainder is election day.
                choices[nm] = {"party": PARTY.get((ch.get("P") or "").upper(), "O"),
                               "votes": v,
                               "by_mode": {"early": ev, "election_day": max(0, v - ev)}}
                state[race]["choices"][nm] += v
                state[race]["early"][nm] += ev
                state[race]["parties"][nm] = choices[nm]["party"]
            counted_early = sum(x["by_mode"]["early"] for x in choices.values())
            was = cast.get((c.get("N") or "").strip().upper())
            rec["races"][race] = {
                "choices": dict(sorted(choices.items(), key=lambda x: -x[1]["votes"])),
                "counted": sum(x["votes"] for x in choices.values()),
                "early_and_mail_counted": counted_early,
                "early_and_mail_cast": was,
                "early_and_mail_left": (max(0, was - counted_early) if was is not None else None),
                "precincts_reporting": summ.get("PRR"),
                "precincts_total": summ.get("PRP") or summ.get("PRR"),
            }
        counties[cname] = rec

    if not found:
        raise RuntimeError(f"none of {sorted(WANT)} found among the Texas contests")
    totals = {}
    cast_tot = sum(cast.values()) if cast else None
    for race, s in state.items():
        ce = sum(s["early"].values())
        totals[race] = {
            "contest_name": found.get(race),
            "choices": dict(s["choices"].most_common()),
            "parties": dict(s["parties"]),
            "total": sum(s["choices"].values()),
            "modes": {"early": ce,
                      "election_day": sum(s["choices"].values()) - ce},
            "precincts_reporting": pr_in, "precincts_total": pr_all,
            "early_and_mail_cast": cast_tot, "early_and_mail_counted": ce,
            "early_and_mail_left": (max(0, cast_tot - ce) if cast_tot is not None else None),
        }
    payload = {
        "state": "TX", "unit": "county", "source_kind": "texas-enr",
        "election": name, "election_date": elec_date, "version": ver,
        "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "early_cast_as_of": cast_as_of,
        "counties": counties, "state_totals": totals,
        "source": f"{BASE}/election/{eid}/{ver}/County.json",
        "notes": {
            "modes": "Texas publishes EV (early) alongside V (total) per candidate per "
                     "county, so election-day votes are V minus EV exactly - no inference. "
                     "Texas counts mail ballots with early voting, so 'early' here is "
                     "early in person plus mail.",
            "left": "early_and_mail_left is measured: ballots this board recorded cast "
                    "early in that county, minus the early votes counted here.",
            "election_day": "Ballots still to come on election day are not estimated; "
                            "only precincts not yet reporting are shown.",
        },
    }
    return payload, totals, counties


def main():
    if "--proof" in sys.argv:
        i = sys.argv.index("--proof")
        eid = sys.argv[i + 1]
        payload, totals, counties = build(eid, f"proof {eid}")
        print(f"TX proof via election {eid} ({payload['election_date']}, ver {payload['version']})")
        print(f"   {len(counties)} counties  precincts "
              f"{list(totals.values())[0]['precincts_reporting']:,}/"
              f"{list(totals.values())[0]['precincts_total']:,}")
        for race, t in totals.items():
            print(f"   {race}: {t['total']:,} votes  "
                  f"early {t['modes']['early']:,}  election-day {t['modes']['election_day']:,}")
            for c, v in list(t["choices"].items())[:3]:
                print(f"      {c[:38]:40} {v:>10,}")
        return 0

    eid, name = find_election(2026)
    if not eid:
        print(f"TX: November 2026 general not staged yet (current: {name})")
        return 2
    payload, totals, counties = build(eid, name)
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "results-TX.json"
    rc = election_day.write_or_hold("TX", p, payload, totals)
    if rc:
        return rc
    for race, t in totals.items():
        print(f"TX {race}: {t['total']:,} counted  precincts "
              f"{t['precincts_reporting']:,}/{t['precincts_total']:,}  "
              f"early+mail left {t['early_and_mail_left']}")
    print(f"   -> {p.name} ({len(counties)} counties)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as e:
        print(f"TX RESULTS FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
