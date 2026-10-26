#!/usr/bin/env python3
"""Election-night results by county from Clarity Elections -> data/results-<ST>.json

Clarity runs election night for a large share of the country, each state on its own
branded host but all behind the same three-step read:

    /{path}/elections.json              -> the elections on file, each with an EID
    /{path}/{EID}/current_ver.txt       -> the version counter, which moves on each update
    /{path}/{EID}/{ver}/reports/detailxml.zip  -> every county, every choice, by mode

The detail XML carries exactly what a county-level projection needs:

    <County name=".." totalVoters=".." ballotsCast=".." precinctsParticipating=".."
            precinctsReported=".." />
    <Choice text=".." party=".." totalVotes="..">
      <VoteType name="Election Day"> <County name=".." votes=".." /> ...

so votes are split by MODE per county, the same way North Carolina reports them. That
split is the whole game: early and election-day ballots break in opposite directions,
so a county "60% reported" means nothing until you know which modes are in.

Remaining early and mail ballots are measured, not modelled - what this board recorded
as cast early in that county, minus what the feed reports counted in the early and mail
modes. Election-day ballots still to come are deliberately not estimated; there is no
denominator for turnout that has not happened, so only precincts-not-yet-reporting is
reported.

Exit 2 means the state has not staged its November election yet, which is an expected
state in October and not a failure. Any other problem raises and writes nothing.
"""
import io, json, pathlib, re, sys, urllib.request, zipfile, collections
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import election_day

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept": "*/*", "Accept-Encoding": "gzip, deflate"}

# Several states keep a legacy clarityelections.com entry alongside a branded host and
# only one of them answers, so each state carries its candidates in preference order.
HOSTS = {
    "GA": [("results.sos.ga.gov", "GA"),
           ("results.enr.clarityelections.com", "GA")],
    "IA": [("electionresults.iowa.gov", "IA")],
    "SC": [("www.enr-scvotes.org", "SC")],
}
# The contests this board tracks, matched case-insensitively on the contest text.
WANT = {
    "GA": {"senate": r"\bUS SENATE\b|UNITED STATES SENAT", "governor": r"\bGOVERNOR\b"},
    "IA": {"senate": r"\bUS SENAT|UNITED STATES SENAT"},
    "SC": {"senate": r"\bUS SENAT|UNITED STATES SENAT"},
}
PARTY = {"DEM": "D", "D": "D", "REP": "R", "R": "R"}
# Clarity names its modes differently state to state; these are folded into the three
# the board reasons about. An unseen name raises rather than being dropped, because a
# silently ignored mode is votes that vanish.
MODE_MAP = {
    "election day": "election_day", "election day votes": "election_day",
    "absentee by mail": "mail", "mail": "mail", "absentee": "mail",
    "mail-in": "mail", "absentee mail": "mail", "mail ballots": "mail",
    "early voting": "early", "advance voting": "early", "advanced voting": "early",
    "in person early": "early", "early in person": "early", "one stop": "early",
    "provisional": "provisional", "provisional votes": "provisional",
    "absentee by mail - uocava": "mail", "uocava": "mail", "overseas": "mail",
    "failsafe": "provisional", "curbside": "election_day",
}
EARLY_MODES = ("early", "mail")


def get(url, timeout=90):
    """These hosts gzip the response whatever Accept-Encoding asks for, and urllib does
    not decompress on its own, so a raw read hands JSON parsing a gzip header."""
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError(f"{url}: HTTP {r.status}")
        body = r.read()
        enc = (r.headers.get("Content-Encoding") or "").lower()
    if enc == "gzip" or body[:2] == b"\x1f\x8b":
        import gzip
        body = gzip.decompress(body)
    elif enc == "deflate":
        import zlib
        try:
            body = zlib.decompress(body)
        except zlib.error:
            body = zlib.decompress(body, -zlib.MAX_WBITS)
    return body


def find_election(host, path):
    """The November 2026 general, or None when the state has not staged it."""
    raw = get(f"https://{host}/{path}/elections.json", timeout=40).decode("utf-8", "ignore")
    if raw.lstrip().startswith("<"):
        raise RuntimeError(f"{host}: elections.json served HTML")
    for e in json.loads(raw):
        name = (e.get("ElectionName") or "")
        date = (e.get("Date") or "")
        if "11/3/2026" in date or ("2026" in date and "/3/2026" in date and date.startswith("11")):
            return e
        if re.search(r"2026", name) and re.search(r"general", name, re.I) \
           and not re.search(r"primary|runoff|special", name, re.I):
            return e
    return None


def detail(host, path, eid):
    ver = get(f"https://{host}/{path}/{eid}/current_ver.txt", timeout=40).decode().strip()
    if not ver.isdigit():
        raise RuntimeError(f"{host}/{path}/{eid}: current_ver.txt was not a version ({ver[:60]!r})")
    body = get(f"https://{host}/{path}/{eid}/{ver}/reports/detailxml.zip", timeout=180)
    z = zipfile.ZipFile(io.BytesIO(body))
    names = [n for n in z.namelist() if n.lower().endswith(".xml")]
    if not names:
        raise RuntimeError("detailxml.zip: no .xml inside")
    return ver, z.read(names[0])


def mode_of(name):
    key = re.sub(r"\s+", " ", (name or "").strip().lower())
    m = MODE_MAP.get(key)
    if m is None:
        raise RuntimeError(f"unrecognised vote type {name!r} - add it to MODE_MAP rather "
                           f"than letting its votes be dropped")
    return m


def parse(xml_bytes, st):
    root = ET.fromstring(xml_bytes)
    meta = {
        "election": (root.findtext("ElectionName") or "").strip(),
        "election_date": (root.findtext("ElectionDate") or "").strip(),
        "timestamp": (root.findtext("Timestamp") or "").strip(),
    }
    # county turnout block: registered, ballots cast, precincts reported
    cty_meta = {}
    for c in root.findall("./ElectionVoterTurnout/Counties/County"):
        a = c.attrib
        cty_meta[a.get("name", "").strip().title()] = {
            "registered": int(a.get("totalVoters") or 0),
            "ballots_cast": int(a.get("ballotsCast") or 0),
            "precincts_total": int(a.get("precinctsParticipating") or 0),
            "precincts_reporting": int(a.get("precinctsReported") or 0),
        }
    if not cty_meta:
        raise RuntimeError("detail.xml: no county turnout block")

    wanted = WANT.get(st, {})
    races = collections.defaultdict(lambda: collections.defaultdict(
        lambda: {"choices": collections.defaultdict(
            lambda: {"party": "O", "votes": 0, "by_mode": collections.Counter()})}))
    found = {}
    for contest in root.iter("Contest"):
        text = (contest.get("text") or "").strip()
        race = next((k for k, pat in wanted.items() if re.search(pat, text, re.I)), None)
        if race is None:
            continue
        # Two different contests matching one race key would be summed together under
        # it - which is exactly what happens in a primary, where the Democratic and
        # Republican "United States Senator" contests both match. In a general there is
        # one contest per race, so more than one here means the pattern is too loose and
        # the total would be nonsense.
        if race in found and found[race] != text:
            raise RuntimeError(
                f"{st}: {race!r} matched two contests - {found[race]!r} and {text!r}. "
                f"Their votes would be added together; tighten WANT[{st!r}][{race!r}].")
        found[race] = text
        for choice in contest.findall("Choice"):
            cname = (choice.get("text") or "").strip()
            party = PARTY.get((choice.get("party") or "").strip().upper(), "O")
            for vt in choice.findall("VoteType"):
                mode = mode_of(vt.get("name"))
                for c in vt.findall("County"):
                    cty = (c.get("name") or "").strip().title()
                    v = int(c.get("votes") or 0)
                    rec = races[cty][race]["choices"][cname]
                    rec["party"] = party
                    rec["votes"] += v
                    rec["by_mode"][mode] += v
    if not found:
        raise RuntimeError(f"{st}: none of {sorted(wanted)} found in the contest list")
    return meta, cty_meta, races, found


def early_cast(st):
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / f"early-{st}.json"
    if not p.exists():
        return {}, None
    d = json.loads(p.read_text())
    out = {}
    for cty, b in (d.get("counties") or {}).items():
        def tot(*keys):
            for k in keys:
                v = b.get(k)
                if isinstance(v, dict) and v.get("total") is not None:
                    return v["total"]
                if isinstance(v, (int, float)):
                    return int(v)
            return 0
        mail = tot("mail_returned", "by_mail", "returned")
        ip = tot("early_in_person", "in_person")
        out[cty.title()] = mail + ip
    return out, d.get("as_of")


def build(st):
    last = None
    for host, path in HOSTS.get(st, []):
        try:
            e = find_election(host, path)
        except Exception as exc:
            last = f"{host}: {exc}"
            continue
        if e is None:
            last = f"{host}: no November 2026 general staged yet"
            continue
        ver, xml = detail(host, path, e["EID"])
        meta, cty_meta, races, found = parse(xml, st)
        cast, cast_as_of = early_cast(st)

        counties, state_tot = {}, collections.defaultdict(
            lambda: {"choices": collections.Counter(), "modes": collections.Counter()})
        for cty, per_race in sorted(races.items()):
            cm = cty_meta.get(cty, {})
            out = {}
            for race, r in per_race.items():
                modes = collections.Counter()
                for ch in r["choices"].values():
                    modes.update(ch["by_mode"])
                counted_early = sum(modes[m] for m in EARLY_MODES)
                was = cast.get(cty)
                out[race] = {
                    "choices": {c: {"party": v["party"], "votes": v["votes"],
                                    "by_mode": dict(v["by_mode"])}
                                for c, v in sorted(r["choices"].items(),
                                                   key=lambda x: -x[1]["votes"])},
                    "modes": dict(modes),
                    "counted": sum(modes.values()),
                    "precincts_total": cm.get("precincts_total"),
                    "precincts_reporting": cm.get("precincts_reporting"),
                    "registered": cm.get("registered"),
                    "ballots_cast": cm.get("ballots_cast"),
                    "early_and_mail_cast": was,
                    "early_and_mail_counted": counted_early,
                    "early_and_mail_left": (max(0, was - counted_early)
                                            if was is not None else None),
                }
                for c, v in r["choices"].items():
                    state_tot[race]["choices"][c] += v["votes"]
                state_tot[race]["modes"].update(modes)
            counties[cty] = out

        party_of = {}
        for per in races.values():
            for r in per.values():
                for c, v in r["choices"].items():
                    party_of[c] = v["party"]
        state = {}
        for race, s in state_tot.items():
            cast_tot = sum(cast.values()) if cast else None
            counted_early = sum(s["modes"][m] for m in EARLY_MODES)
            state[race] = {
                "contest_name": found.get(race),
                "choices": dict(s["choices"].most_common()),
                "parties": {c: party_of.get(c, "O") for c in s["choices"]},
                "total": sum(s["choices"].values()),
                "modes": dict(s["modes"]),
                "precincts_reporting": sum(v.get("precincts_reporting") or 0
                                           for v in cty_meta.values()),
                "precincts_total": sum(v.get("precincts_total") or 0
                                       for v in cty_meta.values()),
                "early_and_mail_cast": cast_tot,
                "early_and_mail_counted": counted_early,
                "early_and_mail_left": (max(0, cast_tot - counted_early)
                                        if cast_tot is not None else None),
            }

        payload = {
            "state": st, "unit": "county", "source_kind": "clarity",
            "election": meta["election"], "election_date": meta["election_date"],
            "feed_timestamp": meta["timestamp"], "version": ver,
            "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "early_cast_as_of": cast_as_of,
            "counties": counties, "state_totals": state,
            "source": f"https://{host}/{path}/{e['EID']}/{ver}/reports/detailxml.zip",
            "notes": {
                "modes": "Votes split by mode; early and mail are never pooled with "
                         "election day, because they break in opposite directions.",
                "left": "early_and_mail_left is measured - ballots recorded cast early or "
                        "by mail in that county, minus those modes as counted here.",
                "election_day": "Ballots still to come on election day are not estimated; "
                                "only precincts not yet reporting are shown.",
            },
        }
        p = pathlib.Path(__file__).resolve().parent.parent / "data" / f"results-{st}.json"
        rc = election_day.write_or_hold(st, p, payload, state)
        if rc:
            return rc
        for race, s in state.items():
            print(f"{st} {race}: {s['total']:,} counted  "
                  f"precincts {s['precincts_reporting']:,}/{s['precincts_total']:,}  "
                  f"early+mail left "
                  f"{s['early_and_mail_left'] if s['early_and_mail_left'] is not None else '?'}")
        print(f"   -> {p.name} ({len(counties)} counties, feed {meta['timestamp']})")
        return 0
    print(f"{st}: not available yet - {last}")
    return 2


def proof(st, eid):
    """Run the whole parse against a named past election and print what it found.

    An empty November feed proves only that the fetch works. This exercises the parser
    on an election that actually has votes in it, which is the part that has to be right
    on the night - and it writes nothing, so it can be run any time.
    """
    for host, path in HOSTS.get(st, []):
        try:
            ver, xml = detail(host, path, eid)
        except Exception as e:
            print(f"  {host}: {e}")
            continue
        try:
            meta, cty_meta, races, found = parse(xml, st)
        except RuntimeError as e:
            if "matched two contests" not in str(e):
                raise
            # a primary legitimately carries one contest per party; say so and go on
            print(f"{st} proof: {e}")
            print("   (expected for a primary - the general carries one contest per race)")
            return 0
        print(f"{st} proof via {host} (EID {eid}, ver {ver})")
        print(f"   {meta['election']}  {meta['election_date']}  feed {meta['timestamp']}")
        print(f"   counties {len(cty_meta)}  contests matched {found}")
        reg = sum(v['registered'] for v in cty_meta.values())
        cast = sum(v['ballots_cast'] for v in cty_meta.values())
        pin = sum(v['precincts_reporting'] for v in cty_meta.values())
        pall = sum(v['precincts_total'] for v in cty_meta.values())
        print(f"   registered {reg:,}  ballots cast {cast:,}  precincts {pin:,}/{pall:,}")
        tot = collections.Counter(); modes = collections.Counter()
        for per in races.values():
            for r in per.values():
                for c, v in r["choices"].items():
                    tot[c] += v["votes"]; modes.update(v["by_mode"])
        print(f"   modes seen: {dict(modes)}")
        for c, v in tot.most_common(6):
            print(f"      {c:34} {v:>9,}")
        big = sorted(races.items(),
                     key=lambda kv: -sum(ch['votes'] for r in kv[1].values()
                                         for ch in r['choices'].values()))[:3]
        for cty, per in big:
            for race, r in per.items():
                m = collections.Counter()
                for ch in r["choices"].values(): m.update(ch["by_mode"])
                print(f"      {cty:16} {race:9} {sum(m.values()):>8,}  by mode {dict(m)}")
        return 0
    return 1


if __name__ == "__main__":
    if "--proof" in sys.argv:
        i = sys.argv.index("--proof")
        sys.exit(proof(sys.argv[i+1].upper(), sys.argv[i+2]))
    states = [a.upper() for a in sys.argv[1:] if a.isalpha()] or sorted(HOSTS)
    rc = 0
    for st in states:
        try:
            r = build(st)
        except Exception as e:
            print(f"{st} FAILED (nothing written): {e}", file=sys.stderr)
            r = 1
        rc = max(rc, r if r != 2 else (rc or 2))
    sys.exit(rc)
