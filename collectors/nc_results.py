#!/usr/bin/env python3
"""North Carolina election-night results, by county -> data/results-NC.json

Source: s3.amazonaws.com/dl.ncsbe.gov/ENRS/2026_11_03/results_pct_20261103.zip
        s3.amazonaws.com/dl.ncsbe.gov/ENRS/2026_11_03/absentee_spoiled_outstanding_20261103.zip

North Carolina is the best-instrumented state on this board, and the reason is that it
reports each precinct's votes SPLIT BY MODE:

    Election Day | Early Voting | Absentee by Mail | Provisional

That split is what makes an honest projection possible. Everywhere else, a county at
"60% of precincts reporting" tells you nothing about WHICH ballots are missing, and the
early vote and the election-day vote break in opposite directions - so the same 60% can
mean a lead that will grow or one that will vanish.

Here the remaining ballots are not guessed at. They are measured, from two directions:

  early + mail still to count
      = what the absentee file says was CAST early and by mail in that county
        (data/early-NC.json, which we have been collecting daily since Oct 16)
        minus what the results file says has been COUNTED in those two modes.
      Both sides come from the same state, keyed on the same county.

  mail still outstanding
      = abs_outstanding, published per county in the state's own daily file - ballots
        sent to a voter and not yet returned. These are not the same thing as uncounted
        returned ballots and are reported separately for that reason.

  election-day vote still to come
      = NOT derivable. There is no denominator for it: nobody knows how many people will
        show up until they do. It is reported as precincts-not-yet-reporting and never
        as a ballot count, because a number here would be a forecast wearing the costume
        of a measurement.

FAILS CLOSED: any fetch or parse problem raises and writes nothing, so the board keeps
showing the previous good count with its own timestamp rather than a partial one.
"""
import csv, io, json, pathlib, sys, zipfile, urllib.request, collections
from datetime import datetime, timezone

ELECTION = ("2026_11_03", "20261103")
BASE = "https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/{}/{}"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}

# The contests this board tracks for NC. Anything else in the file is ignored rather
# than aggregated: the file carries every judicial seat and amendment in the state.
CONTESTS = {"US SENATE": "senate"}
PARTY = {"DEM": "D", "REP": "R", "LIB": "O", "GRE": "O", "CST": "O", "UNA": "O"}
MODES = ["Election Day", "Early Voting", "Absentee by Mail", "Provisional"]


def fetch(filename, timeout=180):
    url = BASE.format(ELECTION[0], filename)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError(f"{url}: HTTP {r.status}")
        body = r.read()
    if len(body) < 500:
        raise RuntimeError(f"{filename}: {len(body)} bytes - refusing a truncated download")
    return body


def num(v):
    v = (v or "").strip().replace(",", "")
    return int(v) if v.lstrip("-").isdigit() else 0


def parse_results(body):
    """county -> race -> {choices, modes, precincts}."""
    z = zipfile.ZipFile(io.BytesIO(body))
    names = [n for n in z.namelist() if n.lower().endswith(".txt")]
    if not names:
        raise RuntimeError("results zip: no .txt inside")
    out = collections.defaultdict(lambda: collections.defaultdict(lambda: {
        "choices": collections.defaultdict(lambda: {"party": "O", "votes": 0,
                                                    "by_mode": dict.fromkeys(MODES, 0)}),
        "modes": dict.fromkeys(MODES, 0),
        "precincts": set(), "precincts_in": set(),
    }))
    rows = 0
    with z.open(names[0]) as f:
        rd = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="ignore"),
                            delimiter="\t")
        need = ["County", "Precinct", "Contest Name", "Choice", "Choice Party",
                "Total Votes", "Real Precinct"] + MODES
        for c in need:
            if c not in (rd.fieldnames or []):
                raise RuntimeError(f"results: column {c!r} missing - layout changed")
        for row in rd:
            rows += 1
            name = (row.get("Contest Name") or "").strip().upper()
            race = CONTESTS.get(name)
            if race is None:
                continue
            if (row.get("Real Precinct") or "").strip().upper() == "N":
                # a holding bucket the state uses for ballots not yet assigned to a
                # precinct; its votes are real and must be counted, but it is not a
                # precinct and must not inflate the reporting denominator
                pct = None
            else:
                pct = (row.get("Precinct") or "").strip()
            cty = (row.get("County") or "").strip().title()
            if not cty:
                continue
            rec = out[cty][race]
            choice = (row.get("Choice") or "").strip()
            if not choice:
                continue
            party = PARTY.get((row.get("Choice Party") or "").strip().upper(), "O")
            tot = num(row.get("Total Votes"))
            ch = rec["choices"][choice]
            ch["party"] = party
            ch["votes"] += tot
            for m in MODES:
                v = num(row.get(m))
                ch["by_mode"][m] += v
                rec["modes"][m] += v
            if pct:
                rec["precincts"].add(pct)
                if tot:
                    rec["precincts_in"].add(pct)
    if rows < 1000:
        raise RuntimeError(f"results: only {rows} rows - refusing a partial file")
    if not out:
        raise RuntimeError(f"results: none of {sorted(CONTESTS)} found in {rows:,} rows")
    return out, rows


def parse_outstanding(body):
    z = zipfile.ZipFile(io.BytesIO(body))
    names = [n for n in z.namelist() if n.lower().endswith(".csv")]
    if not names:
        raise RuntimeError("outstanding zip: no .csv inside")
    out = {}
    with z.open(names[0]) as f:
        rd = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="ignore"))
        if "abs_outstanding" not in (rd.fieldnames or []):
            raise RuntimeError("outstanding: abs_outstanding column missing")
        for row in rd:
            cty = (row.get("county_name") or "").strip().title()
            if cty:
                out[cty] = {"sent": num(row.get("abs_sent")),
                            "accepted": num(row.get("abs_accepted")),
                            "received_not_counted": num(row.get("abs_received_not_counted")),
                            "outstanding": num(row.get("abs_outstanding"))}
    if len(out) < 90:
        raise RuntimeError(f"outstanding: only {len(out)} counties - NC has 100; refusing")
    return out


def early_cast():
    """What our own daily collection says was cast early and by mail, per county."""
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "early-NC.json"
    if not p.exists():
        return {}, None
    d = json.loads(p.read_text())
    out = {}
    for cty, b in (d.get("counties") or {}).items():
        mail = (b.get("mail_returned") or {}).get("total", 0)
        ip = (b.get("early_in_person") or {}).get("total", 0)
        out[cty.title()] = {"mail": mail, "in_person": ip, "total": mail + ip}
    return out, d.get("as_of")


def main():
    res_body = fetch(f"results_pct_{ELECTION[1]}.zip")
    out_body = fetch(f"absentee_spoiled_outstanding_{ELECTION[1]}.zip", timeout=60)
    results, rows = parse_results(res_body)
    outstanding = parse_outstanding(out_body)
    cast, cast_as_of = early_cast()

    counties, totals = {}, collections.defaultdict(lambda: collections.Counter())
    state_modes = collections.Counter()
    pct_in = pct_all = 0
    for cty, races in sorted(results.items()):
        rec = {}
        for race, r in races.items():
            counted_early = r["modes"]["Early Voting"] + r["modes"]["Absentee by Mail"]
            was_cast = (cast.get(cty) or {}).get("total")
            # Measured, not modelled - and only where both sides exist. A negative
            # remainder means more has been counted than we recorded as cast, which is
            # normal late in the night (cures, late-arriving mail) and is clamped to
            # zero rather than shown as a negative pile of ballots.
            early_left = max(0, was_cast - counted_early) if was_cast is not None else None
            rec[race] = {
                "choices": {c: {"party": v["party"], "votes": v["votes"],
                                "by_mode": v["by_mode"]}
                            for c, v in sorted(r["choices"].items(),
                                               key=lambda x: -x[1]["votes"])},
                "modes": dict(r["modes"]),
                "counted": sum(r["modes"].values()),
                "precincts_total": len(r["precincts"]),
                "precincts_reporting": len(r["precincts_in"]),
                "early_and_mail_cast": was_cast,
                "early_and_mail_counted": counted_early,
                "early_and_mail_left": early_left,
                "mail_outstanding": (outstanding.get(cty) or {}).get("outstanding"),
            }
            for c, v in r["choices"].items():
                totals[race][c] += v["votes"]
            for m, v in r["modes"].items():
                state_modes[m] += v
            pct_in += len(r["precincts_in"]); pct_all += len(r["precincts"])
        counties[cty] = rec

    # party travels with the choice in the per-county block but was lost on the way up,
    # so every candidate arrived at the board as "other" and nothing could be coloured.
    party_of = {}
    for races_ in results.values():
        for r in races_.values():
            for c, v in r["choices"].items():
                party_of[c] = v["party"]
    state = {}
    for race, cnt in totals.items():
        tot = sum(cnt.values())
        cast_tot = sum(v["total"] for v in cast.values()) if cast else None
        counted_early = state_modes["Early Voting"] + state_modes["Absentee by Mail"]
        state[race] = {
            "choices": dict(cnt.most_common()),
            "parties": {c: party_of.get(c, "O") for c in cnt},
            "total": tot,
            "modes": dict(state_modes),
            "precincts_reporting": pct_in, "precincts_total": pct_all,
            "early_and_mail_cast": cast_tot,
            "early_and_mail_counted": counted_early,
            "early_and_mail_left": (max(0, cast_tot - counted_early)
                                    if cast_tot is not None else None),
            "mail_outstanding": sum(v["outstanding"] for v in outstanding.values()),
        }

    payload = {
        "state": "NC", "unit": "county", "election": "2026 General",
        "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": rows,
        "early_cast_as_of": cast_as_of,
        "counties": counties, "state_totals": state,
        "source": BASE.format(ELECTION[0], f"results_pct_{ELECTION[1]}.zip"),
        "outstanding_source": BASE.format(ELECTION[0],
                                          f"absentee_spoiled_outstanding_{ELECTION[1]}.zip"),
        "notes": {
            "modes": "Votes are reported split by mode; early and mail are never pooled "
                     "with election day, because they break in opposite directions.",
            "left": "early_and_mail_left is measured: ballots this board recorded as cast "
                    "early or by mail in that county, minus those two modes as counted in "
                    "the results file. It is not an estimate.",
            "election_day": "Ballots still to come on election day are deliberately absent. "
                            "There is no denominator for turnout that has not happened, so "
                            "only precincts-not-yet-reporting is shown.",
        },
    }
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "results-NC.json"
    p.write_text(json.dumps(payload, indent=1) + "\n")
    for race, s in state.items():
        lead = list(s["choices"].items())[:2]
        print(f"NC {race}: {s['total']:,} counted  "
              f"precincts {s['precincts_reporting']:,}/{s['precincts_total']:,}")
        for c, v in lead:
            print(f"     {c:28} {v:>9,}")
        print(f"     early+mail cast {s['early_and_mail_cast'] or 0:>9,} "
              f"counted {s['early_and_mail_counted']:>9,} "
              f"LEFT {s['early_and_mail_left'] if s['early_and_mail_left'] is not None else '?':>9}")
        print(f"     mail still outstanding (sent, not returned) {s['mail_outstanding']:>9,}")
    print(f"   -> {p.name} ({len(counties)} counties)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as e:
        print(f"NC RESULTS FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
