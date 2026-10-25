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
# The in-person file is "EarlyVoted". It was guessed as "EvVoted" before early voting
# opened, and the 404 was swallowed, so in-person read 0 for the first days of Florida EV
# while 171,025 votes sat in a file we were not asking for. Candidates are tried in order
# and a total miss is REPORTED, never silent.
OPTIONAL = {"in_person": ("EarlyVoted", "EvVoted", "EvEarlyVoted")}


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


def _sortable(day):
    """mm/dd/yyyy -> yyyymmdd for comparison."""
    import re
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", day or "")
    return f"{m.group(3)}{int(m.group(1)):02d}{int(m.group(2)):02d}" if m else ""


def _day(stamp):
    """Date part of a compile stamp, so 8:04AM and 2:01PM on the same day compare equal."""
    import re
    m = re.search(r"\d{1,2}/\d{1,2}/\d{4}", stamp or "")
    return m.group(0) if m else (stamp or "")


def fetch_consistent(attempts=4, pause=3):
    """All required files from the SAME compile date, or raise.

    The cache is the reason for the loop: a retry often lands on an edge node that has
    the full set. Taking whatever came back and publishing it would mean an outstanding
    count from one day sitting beside a returned count from another.
    """
    last, best, best_day = None, None, None
    for i in range(1, attempts + 1):
        data = {"compiled": {}}
        for key, stat in FILES.items():
            data[key], data["compiled"][key] = fetch(stat)
        # Compare the DAY, not the exact stamp. _day exists for precisely this - the
        # docstring says so - but the check used the raw timestamps, so Florida posting
        # its two files at 11:01AM and 5:02PM on the SAME DAY read as "the CDN is
        # serving mixed days" and the collector refused on every run for days. What
        # must not be combined is two different days; two times on one day is just
        # Florida updating one file after the other.
        stamps = set(data["compiled"].values())
        days = {_day(v) for v in data["compiled"].values()}
        if len(days) == 1 and None not in stamps and not any(d in ("", None) for d in days):
            day = next(iter(days))
            # Keep looking for a NEWER consistent set. The cache holds more than one day at
            # once, so the first agreeing pair is not necessarily the latest one — taking it
            # made the published figure jump backwards between runs.
            if best_day is None or _sortable(day) > _sortable(best_day):
                best, best_day = data, day
            if i >= 2:
                return best
        else:
            last = dict(data["compiled"])
            print(f"   FL compile DAYS disagree {last} — refetching ({i}/{attempts})",
                  file=sys.stderr)
        if i < attempts:
            time.sleep(pause)
    if best:
        return best
    raise RuntimeError(f"required files never agreed on a compile DAY after {attempts} "
                       f"tries (last: {last}); the CDN is serving different days — "
                       f"refusing to combine them")


def main():
    data = fetch_consistent()
    day = next(iter(set(data["compiled"].values())))
    for key, names in OPTIONAL.items():
        errs = []
        for stat in names:
            try:
                got, c = fetch(stat)
            except Exception as e:
                errs.append(f"{stat}: {e}")
                continue
            # DO NOT require the same day. In-person is an INDEPENDENT quantity published
            # on its own schedule — it does not have to agree with the mail files the way
            # outstanding and returned do, because no arithmetic combines them. Requiring a
            # match made in-person appear and vanish between runs as the three files drifted
            # in and out of alignment. Its own compile date is recorded instead.
            if _day(c) != _day(day):
                print(f"   FL note: in-person compiled {c}, mail is {day} — kept, dated "
                      f"separately", file=sys.stderr)
            data[key] = got
            data["compiled"][key] = c
            break
        else:
            print(f"   FL: no in-person file yet ({'; '.join(errs)})", file=sys.stderr)
    counties = sorted(set(data["outstanding"]) & set(data["returned"]) - {"State Totals"})
    if len(counties) < 60:
        raise RuntimeError(f"only {len(counties)} counties in both files — refusing")
    payload = {"state": "FL", "unit": "county", "election": "2026 General",
               "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "compiled": data["compiled"], "counties": {}}
    for c in counties:
        rec = {"outstanding": data["outstanding"][c], "returned": data["returned"][c]}
        if "in_person" in data and c in data["in_person"]:
            rec["early_in_person"] = data["in_person"][c]
            rec["in_person"] = data["in_person"][c]
        payload["counties"][c] = rec
    payload["in_person"] = "in_person" in data
    # Florida publishes "Vote-by-Mail Provided (Not Yet Returned)", so outstanding is a
    # reported count, not derived. Say so in the payload: NC sets this false because it
    # genuinely does not publish one, and the two cases must stay distinguishable.
    payload["outstanding_available"] = True
    # The streams can be a day apart, and the board adds them together into a total
    # early vote. The comment above says no arithmetic combines them; that stopped being
    # true when the total was added, so when they disagree the card has to say the total
    # spans two publication days rather than present it as one moment.
    days = {k: _day(v) for k, v in data["compiled"].items() if v}
    if len(set(days.values())) > 1:
        payload.setdefault("notes", {})["mixed_days"] = (
            "Florida publishes these files on separate schedules and they are a day "
            "apart right now, so the total early vote spans two: "
            + ", ".join(f"{k} compiled {v}" for k, v in sorted(days.items()))
            + ". The figure is dated by the OLDEST of them, which is the day every part "
              "of it is good through.")
        payload["mixed_days"] = True
    payload["state_totals"] = {"outstanding": data["outstanding"]["State Totals"],
                               "returned": data["returned"]["State Totals"]}
    if "in_person" in data:
        # early_in_person is the key every other collector uses and the board reads. It was
        # written as "in_person" here, so Florida's in-person never rendered even once it
        # was being collected. Both are emitted: the canonical name, and the old one so
        # nothing that already reads it breaks.
        payload["state_totals"]["early_in_person"] = data["in_person"]["State Totals"]
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
