#!/usr/bin/env python3
"""UF Election Lab 2024 statewide finals -> data/ev-history-<ST>.json, for states with none

Source: election.lab.ufl.edu/data-downloads/earlyvote/2024/US.csv — one row per state,
the 2024 general's final early-vote figures, with party where the state registers by party.

WHAT THIS IS AND IS NOT. It is statewide only: the Lab keeps county files for the current
cycle, not past ones (every <ST>_county.csv 404s for 2024 and earlier). And 2024 was a
PRESIDENTIAL year, so it is a ceiling, not a like-for-like midterm comparator — a state
sitting at 40% of its 2024 early vote is not behind, it is in a different kind of election.
Each year is tagged so the board can label it rather than letting three cycles sit side by
side as equivalents.

States that already have a real history from their own archives are skipped: Florida,
North Carolina and Texas have 2020/2022/2024, Iowa has 2022. A secondhand single year
would be a downgrade, not an addition.

The Lab's older archive does carry 2022 and earlier, but it is the paid one, so it is not
used here. For a true midterm baseline in the remaining states the route is the state's
own archive, state by state.

FAILS CLOSED: a state that cannot be parsed is skipped with a reason; nothing is written.
"""
import json, csv, io, sys, pathlib, urllib.request
from datetime import datetime, timezone

URL = "https://election.lab.ufl.edu/data-downloads/earlyvote/2024/US.csv"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept-Encoding": "identity"}
# Maine is deliberately absent: the Lab lumps its mail and in-person into one accepted
# figure, so its 2024 row would render as "in-person 0" — a false zero for a state that
# very much had in-person early voting. Maine's history comes from its own archive.
WANT = {"NE", "KS", "GA", "MI", "OH", "MN"}
DATA = pathlib.Path(__file__).resolve().parent.parent / "data"


def num(r, k):
    v = (r.get(k) or "").strip().replace(",", "")
    try:
        return int(v)
    except ValueError:
        return 0


def main():
    with urllib.request.urlopen(urllib.request.Request(URL, headers=UA), timeout=60) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}")
        rows = list(csv.DictReader(io.StringIO(r.read().decode("utf-8", "ignore"))))
    if len(rows) < 40:
        raise RuntimeError(f"only {len(rows)} states in US.csv — refusing")

    wrote = skipped = 0
    for row in rows:
        st = (row.get("state_abbv") or "").strip().upper()
        if st not in WANT:
            continue
        out = DATA / f"ev-history-{st}.json"
        if out.exists():
            print(f"{st}: already has a history from its own archive — leaving it")
            skipped += 1
            continue
        mail, ip = num(row, "accept_all"), num(row, "inperson_all")
        if mail + ip == 0:
            print(f"{st}: no 2024 figures in the file — skipped", file=sys.stderr)
            skipped += 1
            continue
        party = num(row, "accept_dem") + num(row, "accept_rep") > 0
        rec = lambda pre, tot: ({"D": num(row, pre + "_dem"), "R": num(row, pre + "_rep"),
                                 "NPA": num(row, pre + "_none"), "O": 0, "total": tot}
                                if party else {"total": tot})
        payload = {"state": st, "unit": "state", "party_available": party,
                   "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "years": {"2024": {
                       "election": "2024 General", "cycle": "presidential",
                       "statewide_only": True,
                       "as_of": (row.get("last_update") or "").strip(),
                       # Both shapes: the party card reads mail_returned/early_in_person,
                       # the turnout card reads by_mail/in_person/total. Emitting one of
                       # them leaves the other card's pace table blank.
                       "state_totals": {"mail_returned": rec("accept", mail),
                                        "early_in_person": rec("inperson", ip),
                                        "by_mail": mail, "in_person": ip,
                                        "total": mail + ip, "registered": 0,
                                        "in_person_reported": ip > 0},
                       "source": URL,
                       "upstream": (row.get("data_source") or "").strip()}},
                   "attribution": {"aggregator": "UF Election Lab (election.lab.ufl.edu)"},
                   "notes": {"scope": "statewide only — the Lab keeps county files for the "
                                      "current cycle only",
                             "cycle": "2024 is presidential; it is a ceiling, not a midterm "
                                      "comparator"}}
        out.write_text(json.dumps(payload, indent=1))
        print(f"{st} 2024: mail {mail:>9,}  in-person {ip:>9,}"
              f"{'  [party]' if party else '  [turnout only]'}  -> {out.name}")
        wrote += 1
    print(f"\n{wrote} written, {skipped} skipped")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"UF HISTORY FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
