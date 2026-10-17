#!/usr/bin/env python3
"""Texas early voting by county -> data/early-TX.json  (and --history -> ev-history-TX.json)

Source: earlyvoting.texas-election.com, the SOS's own daily early-voting turnout system.
The public page is a JSP with no documented API; these are its real endpoints, found in
its own JS:
    GET  /Elections/getElectionDetails.do     -> <select id=idElection> every election
    GET  /Elections/getElectionEVDates.do     -> <select name=selectedDate> the EV days
    POST /Elections/getEVDetails.do           -> one row per county for a given day

A session cookie from the first GET is required; posting cold returns HTTP 500.

The county table carries, per county, for the selected day:
    Registered Voters | # In Person that day | Cumulative In-Person | Cumulative % In-Person
    Cumulative By Mail | Cumulative In-Person And Mail | Cumulative % Early Voting
All 254 counties are present, not only the large ones.

NO PARTY SPLIT. Texas has no party registration, so there is nothing to break out — the
payload sets party_available=false so the board cannot imply a split that does not exist.
Pace against 2022 and 2024 is what Texas data supports, and the registered-voter column
makes that a real denominator rather than a guess.

The 2026 general election is not in the dropdown until the SOS opens it (EV begins
2026-10-19). Until then this exits 2 with "not yet published" and writes nothing — a
distinct state from a broken scrape, so the cron can stay quiet instead of alarming.

FAILS CLOSED: any fetch or parse problem raises and writes nothing.
"""
import json, re, sys, pathlib, urllib.request, urllib.parse, http.cookiejar
from datetime import datetime, timezone

BASE = "https://earlyvoting.texas-election.com"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept-Encoding": "identity",
      "Referer": BASE + "/Elections/getElectionEVDates.do",
      "Content-Type": "application/x-www-form-urlencoded"}
LIVE_YEAR = 2026
HISTORY = {2020: "44144", 2022: "47009", 2024: "49664"}
# the columns this parser depends on, in order, as the page labels them
WANT = ["County", "Registered Voters", "In Person", "Cumulative In-Person Voters",
        "Cumulative % In-Person", "Cumulative By Mail Voters",
        "Cumulative In-Person And Mail Voters", "Cumulative Percent Early Voting"]


class Session:
    def __init__(self):
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.get("/Elections/getElectionDetails.do")          # seed the session cookie

    def get(self, path, **params):
        u = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
        with self.op.open(urllib.request.Request(u, headers=UA), timeout=60) as r:
            if r.status != 200:
                raise RuntimeError(f"HTTP {r.status} GET {path}")
            return r.read().decode("utf-8", "ignore")

    def post(self, path, **params):
        body = urllib.parse.urlencode(params).encode()
        with self.op.open(urllib.request.Request(BASE + path, data=body, headers=UA),
                          timeout=90) as r:
            if r.status != 200:
                raise RuntimeError(f"HTTP {r.status} POST {path}")
            return r.read().decode("utf-8", "ignore")


def options(html, name):
    m = re.search(r'<select[^>]+(?:id|name)="%s"(.*?)</select>' % re.escape(name),
                  html, re.S | re.I)
    if not m:
        raise RuntimeError(f"<select {name}> missing — page structure changed")
    out = []
    for v, label in re.findall(r'value="([^"]*)"[^>]*>(.*?)</option>', m.group(1), re.S):
        label = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", label)).strip()
        if v:
            out.append((v, label))
    return out


def num(s):
    s = re.sub(r"[>,\s]", "", s or "")
    if s in ("", "-", "N/A"):
        return None
    try:
        return int(s)
    except ValueError:
        return None


def county_table(html, day):
    """The one table whose header matches the EV turnout layout -> list of county dicts."""
    for tm in re.finditer(r"<table(.*?)</table>", html, re.S | re.I):
        rows = []
        for r in re.findall(r"<tr(.*?)</tr>", tm.group(1), re.S | re.I):
            cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).strip().lstrip(">")
                     for c in re.findall(r"<t[dh](.*?)</t[dh]>", r, re.S | re.I)]
            if any(cells):
                rows.append(cells)
        if len(rows) < 20 or len(rows[0]) < 8:
            continue
        hdr = rows[0]
        for i, want in enumerate(WANT):
            if want.lower() not in (hdr[i] if i < len(hdr) else "").lower():
                raise RuntimeError(f"column {i} is {hdr[i] if i < len(hdr) else '<none>'!r}, "
                                   f"expected {want!r} — layout changed")
        counties = {}
        for row in rows[1:]:
            if len(row) < 8 or not row[0]:
                continue
            name = row[0].strip().title()
            if name.upper() == "STATEWIDE" or name.lower().startswith("total"):
                name = "STATEWIDE"
            counties[name] = {
                "registered": num(row[1]),
                "in_person_today": num(row[2]),
                "in_person": num(row[3]),
                "by_mail": num(row[5]),
                "total": num(row[6]),
            }
        if len(counties) < 200:
            raise RuntimeError(f"only {len(counties)} counties — Texas has 254; refusing")
        return counties
    raise RuntimeError(f"no county turnout table for {day} — page structure changed")


def pull(s, id_election, label):
    html = s.get("/Elections/getElectionEVDates.do", idElection=id_election)
    days = options(html, "selectedDate")
    if not days:
        raise RuntimeError(f"{label}: no early-voting days listed yet")
    day, day_label = days[-1]
    page = s.post("/Elections/getEVDetails.do", idElection=id_election,
                  idGroupedElection="", electionDate="", webPageSyncDate="true",
                  downloadElectionFileCSVFlag="false", pollPlaceIdtown="",
                  electionDayIdTown="", selectedDate=day)
    counties = county_table(page, day_label)
    return {"id_election": id_election, "election": label, "through": day_label,
            "days_reported": len(days), "counties": counties}


def rollup(counties):
    tot = {"registered": 0, "in_person": 0, "by_mail": 0, "total": 0}
    for name, c in counties.items():
        if name == "STATEWIDE":
            continue
        for k in tot:
            if c.get(k) is not None:
                tot[k] += c[k]
    return tot


def main(argv):
    s = Session()
    out_dir = pathlib.Path(__file__).resolve().parent.parent / "data"

    if "--history" in argv:
        payload = {"state": "TX", "unit": "county", "party_available": False,
                   "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "years": {}, "source": BASE + "/Elections/getEVDetails.do"}
        for year, eid in sorted(HISTORY.items()):
            got = pull(s, eid, f"{year} General")
            got["state_totals"] = rollup(got["counties"])
            payload["years"][str(year)] = got
            t = got["state_totals"]
            print(f"TX {year}: through {got['through']} · {got['days_reported']} EV days · "
                  f"in-person {t['in_person']:,} + mail {t['by_mail']:,} = {t['total']:,}"
                  f"  ({t['total']*100/t['registered']:.1f}% of {t['registered']:,} reg)")
        p = out_dir / "ev-history-TX.json"
        p.write_text(json.dumps(payload, indent=1))
        print(f"   -> {p.name}")
        return 0

    # live 2026
    details = s.get("/Elections/getElectionDetails.do")
    eid = next((v for v, label in options(details, "idElection")
                if re.search(rf"\b{LIVE_YEAR}\b.*GENERAL", label, re.I)), None)
    if not eid:
        print(f"TX: {LIVE_YEAR} general election not yet published by the SOS "
              f"(early voting begins 2026-10-19) — nothing written", file=sys.stderr)
        return 2
    got = pull(s, eid, f"{LIVE_YEAR} General")
    got.update({"state": "TX", "unit": "county", "party_available": False,
                "outstanding_available": False,
                "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "state_totals": rollup(got["counties"]),
                "source": BASE + "/Elections/getEVDetails.do"})
    p = out_dir / "early-TX.json"
    p.write_text(json.dumps(got, indent=1))
    t = got["state_totals"]
    print(f"TX ok: {len(got['counties'])} counties, through {got['through']} "
          f"({got['days_reported']} EV days)")
    print(f"   in-person {t['in_person']:>10,}")
    print(f"   by mail   {t['by_mail']:>10,}")
    print(f"   total     {t['total']:>10,}   {t['total']*100/max(t['registered'],1):.1f}% "
          f"of {t['registered']:,} registered")
    print(f"   no party split — Texas has no party registration")
    print(f"   -> {p.name}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:
        print(f"TX FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
