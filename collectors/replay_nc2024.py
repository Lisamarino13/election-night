#!/usr/bin/env python3
"""Replay North Carolina 2024 through the projection -> data/replay-NC-2024.json

The point of a replay is to test the METHOD against an election whose answer is already
known, on the hardest case there is.

North Carolina 2024 is that case. Early and mail voting ran 4.43M ballots against
1.17M on election day, and the two break in opposite directions - the early vote leans
Democratic, the election-day vote Republican. So for the first hours of the night the
Democrat leads every statewide race by a mile, and the question that decides whether a
projection is worth anything is whether it knows that lead is going to shrink, and by
how much. In 2024 it shrank enough to flip the presidential result and not enough to
flip governor:

    President          Trump +183,048    (Harris leads the early vote by ~450k)
    Attorney General   Jackson +159,549
    Governor           Stein +828,187

The replay builds the night as North Carolina actually reports it: the early and mail
vote lands first, in full, then election-day precincts arrive county by county. At each
step every county carries what it has counted and what it still owes, and the board's
own projection runs on that.

What this does and does not prove. It proves the arithmetic - that applying a county's
own counted share to that county's own remaining ballots lands on the right answer. It
does NOT prove we can know the remainder on the night: here the remainder is read off
the final result, which on a live election nobody has. For early and mail we can measure
it, because we count what was cast. For election day we cannot, and the board says so
rather than pretending otherwise.
"""
import csv, io, json, pathlib, sys, zipfile, urllib.request, collections, random
from datetime import datetime, timezone

URL = "https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/2024_11_05/results_pct_20241105.zip"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
CACHE = pathlib.Path("/tmp/nc_results_pct_20241105.zip")
RACES = {"US PRESIDENT": "president", "NC GOVERNOR": "governor",
         "NC ATTORNEY GENERAL": "attorney_general"}
PARTY = {"DEM": "D", "REP": "R"}
EARLY_MODES = ("Early Voting", "Absentee by Mail")
STEPS = 12


def fetch():
    if CACHE.exists() and CACHE.stat().st_size > 1_000_000:
        return CACHE.read_bytes()
    with urllib.request.urlopen(urllib.request.Request(URL, headers=UA), timeout=300) as r:
        body = r.read()
    if len(body) < 1_000_000:
        raise RuntimeError(f"{len(body)} bytes - refusing a truncated download")
    CACHE.write_bytes(body)
    return body


def num(v):
    v = (v or "").strip()
    return int(v) if v.lstrip("-").isdigit() else 0


def load():
    z = zipfile.ZipFile(io.BytesIO(fetch()))
    nm = [n for n in z.namelist() if n.lower().endswith(".txt")][0]
    # county -> race -> choice -> {"early":n, "eday":n}, plus precinct inventory
    data = collections.defaultdict(lambda: collections.defaultdict(
        lambda: collections.defaultdict(lambda: {"early": 0, "eday": 0})))
    party = {}
    precincts = collections.defaultdict(set)
    with z.open(nm) as f:
        rd = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="ignore"),
                            delimiter="\t")
        for row in rd:
            race = RACES.get((row.get("Contest Name") or "").strip().upper())
            if race is None:
                continue
            cty = (row.get("County") or "").strip().title()
            ch = (row.get("Choice") or "").strip()
            if not cty or not ch:
                continue
            party[ch] = PARTY.get((row.get("Choice Party") or "").strip().upper(), "O")
            early = sum(num(row.get(m)) for m in EARLY_MODES)
            eday = num(row.get("Election Day")) + num(row.get("Provisional"))
            d = data[cty][race][ch]
            d["early"] += early
            d["eday"] += eday
            if (row.get("Real Precinct") or "").strip().upper() != "N":
                p = (row.get("Precinct") or "").strip()
                if p:
                    precincts[cty].add(p)
    if len(data) < 90:
        raise RuntimeError(f"{len(data)} counties - NC has 100; refusing")
    return data, party, {c: len(p) for c, p in precincts.items()}


def build():
    data, party, pcts = load()
    races = sorted({r for per in data.values() for r in per})
    # Counties finish election-day counting at different times; a fixed shuffle keeps
    # the replay reproducible while still arriving in no meaningful order.
    counties = sorted(data)
    rnd = random.Random(20241105)
    order = counties[:]
    rnd.shuffle(order)

    out = {"state": "NC", "election": "2024 General", "built": datetime.now(
        timezone.utc).isoformat(timespec="seconds"), "source": URL,
        "races": {}, "steps": []}

    finals = {}
    for race in races:
        cand = sorted({c for per in data.values() for c in per.get(race, {})},
                      key=lambda c: -sum(d[race][c]["early"] + d[race][c]["eday"]
                                         for d in data.values() if race in d and c in d[race]))
        out["races"][race] = [{"name": c, "party": party.get(c, "O")} for c in cand]
        finals[race] = {c: sum(data[x][race][c]["early"] + data[x][race][c]["eday"]
                               for x in counties if race in data[x] and c in data[x][race])
                        for c in cand}
    out["finals"] = finals

    for step in range(STEPS + 1):
        # step 0 is the early and mail dump, before any election-day precinct is in
        done = set(order[:round(len(order) * step / STEPS)])
        snap = {"step": step,
                "label": ("Early and mail vote only" if step == 0 else
                          f"{len(done)} of {len(counties)} counties finished counting"),
                "counties_done": len(done), "races": {}}
        for race in races:
            rows = []
            for cty in counties:
                per = data[cty].get(race)
                if not per:
                    continue
                cand = [c["name"] for c in out["races"][race]]
                votes, left = [], 0
                for c in cand:
                    d = per.get(c, {"early": 0, "eday": 0})
                    got = d["early"] + (d["eday"] if cty in done else 0)
                    votes.append(got)
                    if cty not in done:
                        left += d["eday"]
                rows.append({"name": cty, "votes": votes,
                             "outstanding": left if left else None,
                             "precincts_total": pcts.get(cty, 0),
                             "precincts_reporting": pcts.get(cty, 0) if cty in done else 0})
            snap["races"][race] = rows
        out["steps"].append(snap)

    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "replay-NC-2024.json"
    p.write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print(f"NC 2024 replay: {len(counties)} counties, {len(races)} races, "
          f"{STEPS + 1} steps -> {p.name} ({p.stat().st_size // 1024} KB)")
    for race in races:
        f = finals[race]
        top = sorted(f.items(), key=lambda x: -x[1])[:2]
        print(f"   {race:17} final {top[0][0]} {top[0][1]:,} over {top[1][0]} {top[1][1]:,} "
              f"(+{top[0][1] - top[1][1]:,})")
    s0 = out["steps"][0]["races"][races[0]]
    tot = [sum(r["votes"][i] for r in s0) for i in range(len(out["races"][races[0]]))]
    nm = [c["name"] for c in out["races"][races[0]]]
    lead = sorted(zip(nm, tot), key=lambda x: -x[1])[:2]
    print(f"   at step 0 ({races[0]}): {lead[0][0]} leads {lead[1][0]} by "
          f"{lead[0][1] - lead[1][1]:,} on early and mail alone")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(build() or 0)
    except Exception as e:
        print(f"REPLAY FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
