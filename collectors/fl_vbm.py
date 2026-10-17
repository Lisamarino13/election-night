#!/usr/bin/env python3
"""Florida vote-by-mail: outstanding and returned ballots per county, by party.

Source: electionfiles.floridados.gov, tab-separated, refreshed daily ~8am ET
(the Division posts by 9am with noon/3pm/6pm catch-ups for late counties).
Published Sept 4 -> Nov 18 2026, so it keeps running past election day.

Writes data/early-FL.json:
  outstanding[county][party]  <- "Vote-by-Mail Provided (Not Yet Returned)"
  returned[county][party]     <- "Voted Vote-by-Mail"

FAILS CLOSED. Any fetch or parse problem raises and writes nothing, so a bad
run can never blank an existing file or feed zeroes into a projection.

CDN HAZARD (observed 2026-10-17): these files sit behind a cache whose edge nodes do not
hold the same day. Two fetches of the SAME url seconds apart returned 10/16 and then
10/17, and on one pass VbmProvided was 10/17 while VbmVoted was still 10/16. Outstanding
comes from one file and returned from the other, so a mismatch silently combines two
different days into one row. Every required file's CompileDate is therefore compared, and
a disagreement is retried and then refused rather than published.
"""
import json, sys, time, urllib.request, pathlib
from datetime import datetime, timezone

BASE = "https://electionfiles.floridados.gov/countyballotreportfiles"
ELECTION = "49894"                      # 2026 General
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
FILES = {"outstanding": "VbmProvided", "returned": "VbmVoted"}
# In-person early voting opens later (~Oct 24 for the 2026 general). The Division has not
# published these yet; the collector looks each run and folds them in the day they appear,
# so no code change is needed mid-cycle.
OPTIONAL = {"in_person": "EvVoted"}


def fetch(stat):
    url = f"{BASE}/Stats_{ELECTION}_{stat}.txt"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status != 200:
            raise RuntimeError(f"{url} -> HTTP {r.status}")
        body = r.read().decode("utf-8", "ignore")
    rows = [l.split("\t") for l in body.splitlines() if l.strip()]
    if len(rows) < 10:
        raise RuntimeError(f"{url}: only {len(rows)} rows — refusing a partial file")
    head = rows[0]
    for col in ("CountyName", "TotalRep", "TotalDem", "TotalNpa", "TotalOth",
                "GrandTotal", "CompileDate"):
        if col not in head:
            raise RuntimeError(f"{url}: column {col!r} missing — layout changed")
    ix = {c: head.index(c) for c in head}
    num = lambda s: int(s.replace(",", "").strip() or 0)
    out, compiled = {}, None
    for r in rows[1:]:
        if len(r) < len(head):
            continue
        county = r[ix["CountyName"]].strip()
        compiled = compiled or r[ix["CompileDate"]].strip()
        out[county] = {"R": num(r[ix["TotalRep"]]), "D": num(r[ix["TotalDem"]]),
                       "NPA": num(r[ix["TotalNpa"]]), "O": num(r[ix["TotalOth"]]),
                       "total": num(r[ix["GrandTotal"]])}
    if "State Totals" not in out:
        raise RuntimeError(f"{url}: no State Totals row — refusing an incomplete file")
    return out, compiled


def fetch_consistent(attempts=4, pause=3):
    """All required files from the SAME compile date, or raise.

    The cache is the reason for the loop: a retry often lands on an edge node that has
    the full set. Taking whatever came back and publishing it would mean an outstanding
    count from one day sitting beside a returned count from another.
    """
    last = None
    for i in range(1, attempts + 1):
        data = {"compiled": {}}
        for key, stat in FILES.items():
            data[key], data["compiled"][key] = fetch(stat)
        stamps = set(data["compiled"].values())
        if len(stamps) == 1 and None not in stamps:
            return data
        last = dict(data["compiled"])
        print(f"   FL compile dates disagree {last} — refetching ({i}/{attempts})",
              file=sys.stderr)
        if i < attempts:
            time.sleep(pause)
    raise RuntimeError(f"required files never agreed on a compile date after {attempts} "
                       f"tries (last: {last}); the CDN is serving mixed days — refusing "
                       f"to combine them")


def main():
    data = fetch_consistent()
    day = next(iter(set(data["compiled"].values())))
    for key, stat in OPTIONAL.items():
        try:
            got, c = fetch(stat)
            if c != day:
                # in-person from a different day cannot sit beside today's mail numbers
                print(f"   FL skipping {stat}: compiled {c}, mail is {day}", file=sys.stderr)
                continue
            data[key] = got
            data["compiled"][key] = c
        except Exception:
            pass                      # not published yet — expected before EV opens
    counties = sorted(set(data["outstanding"]) & set(data["returned"]) - {"State Totals"})
    if len(counties) < 60:
        raise RuntimeError(f"only {len(counties)} counties in both files — refusing")
    payload = {"state": "FL", "unit": "county", "election": "2026 General",
               "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "compiled": data["compiled"], "counties": {}}
    for c in counties:
        rec = {"outstanding": data["outstanding"][c], "returned": data["returned"][c]}
        if "in_person" in data and c in data["in_person"]:
            rec["in_person"] = data["in_person"][c]
        payload["counties"][c] = rec
    payload["in_person"] = "in_person" in data
    payload["state_totals"] = {"outstanding": data["outstanding"]["State Totals"],
                               "returned": data["returned"]["State Totals"]}
    if "in_person" in data:
        payload["state_totals"]["in_person"] = data["in_person"]["State Totals"]
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "early-FL.json"
    p.write_text(json.dumps(payload, indent=1))
    t = payload["state_totals"]
    print(f"FL ok: {len(counties)} counties  "
          f"outstanding {t['outstanding']['total']:,}  returned {t['returned']['total']:,}  -> {p.name}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FL FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
