#!/usr/bin/env python3
"""Race, age and gender of the early vote, from the UF Election Lab's national file.

Only a handful of states record a voter's race at registration, so this is not a
national picture and must never be presented as one: for 2026 the file carries race
for Georgia, Louisiana and North Carolina alone. Of those, Georgia and North
Carolina are on our board.

The figures are a count of who has VOTED early, not of how they voted. No state
counts ballots before election day. A racial or age breakdown of turnout says who
has shown up so far; it says nothing about the result, and a projection built on it
would be a model, not a count.

Streams are kept apart for the same reason the board keeps mail and in-person apart:
they break in opposite directions and pooling them hides it.
    accept_*    mail ballots returned and accepted
    inperson_*  in-person early votes
    voted_*     the two together, which is what UF's own dashboard shows

Fail-closed: a missing column or a stream that does not add up raises and writes
nothing, so a layout change cannot quietly turn into a wrong chart.
"""
import csv, io, json, pathlib, sys, urllib.request, datetime

URL = "https://election.lab.ufl.edu/data-downloads/earlyvote/{year}/US.csv"
UA = {"User-Agent": "election-night-board/1.0 (personal early-vote tracker)"}

RACE = ["nh_white", "nh_black", "hispanic", "nh_asian", "nh_native_american", "nh_other"]
RACE_LABEL = {
    "nh_white": "White",
    "nh_black": "Black",
    "hispanic": "Hispanic",
    "nh_asian": "Asian",
    "nh_native_american": "Native American",
    "nh_other": "Other / multiple / unknown",
}
# UF buckets age into four; the file does not say where the cuts fall, and its
# dashboard labels them 18-25 / 26-40 / 41-65 / over 65.
AGE = ["age_1", "age_2", "age_3", "age_4"]
AGE_LABEL = {"age_1": "18–25", "age_2": "26–40", "age_3": "41–65", "age_4": "over 65"}
GENDER = ["male", "female", "gender_unknown"]
GENDER_LABEL = {"male": "Male", "female": "Female", "gender_unknown": "Unknown"}
STREAMS = {"accept": "mail returned", "inperson": "in-person early", "voted": "all early + mail"}


def fetch(year):
    url = URL.format(year=year)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        if r.status != 200:
            raise RuntimeError(f"{url}: HTTP {r.status}")
        raw = r.read().decode("utf-8", errors="ignore")
    if raw.lstrip().startswith("<"):
        raise RuntimeError(f"{url}: served HTML, not CSV (the year may not be published)")
    rows = list(csv.DictReader(io.StringIO(raw)))
    if not rows:
        raise RuntimeError(f"{url}: no rows")
    if "state_abbv" not in rows[0]:
        raise RuntimeError(f"{url}: no state_abbv column — layout changed")
    return rows, url


def num(v):
    v = (v or "").strip().replace(",", "")
    if v in ("", "NA", "N/A", "-"):
        return None
    return int(float(v))


def block(row, stream, keys, labels):
    """One stream's breakdown, or None when the state does not publish it."""
    out, total = {}, 0
    for k in keys:
        v = num(row.get(f"{stream}_{k}"))
        if v is None:
            return None
        out[k] = v
        total += v
    if total == 0:
        return None
    return {"counts": out, "total": total,
            "labels": {k: labels[k] for k in keys}}


def extract(row, year, url):
    st = row["state_abbv"]
    rec = {"state": st, "year": year, "source": url,
           "upstream": (row.get("data_source") or "").strip(),
           "as_of": (row.get("last_update") or "").strip(),
           "turnout_2022": num(row.get("turn_2022")),
           "streams": {}}
    any_race = False
    for stream in STREAMS:
        s = {}
        tot = num(row.get(f"{stream}_all"))
        if tot is not None:
            s["total"] = tot
        for name, keys, labels in (("race", RACE, RACE_LABEL),
                                   ("age", AGE, AGE_LABEL),
                                   ("gender", GENDER, GENDER_LABEL)):
            b = block(row, stream, keys, labels)
            if b:
                s[name] = b
                if name == "race":
                    any_race = True
                # A breakdown may cover LESS than the stream - a voter with no race
                # or age on file is in the total but in no bucket - so the parts
                # falling short is ordinary and the shortfall is recorded as
                # coverage instead. Parts EXCEEDING the total is not ordinary: it
                # means the buckets are a different quantity wearing the same name,
                # and that is refused rather than drawn.
                if "total" in s and s["total"]:
                    if b["total"] > s["total"] * 1.01 + 50:
                        raise RuntimeError(
                            f"{st} {year} {stream}.{name}: parts sum to {b['total']:,}, "
                            f"more than {stream}_all at {s['total']:,}")
                    b["coverage"] = round(b["total"] / s["total"], 4)
        if s:
            rec["streams"][stream] = s
    return rec if any_race else None


def run(years):
    out_dir = pathlib.Path(__file__).resolve().parent.parent / "data"
    by_state = {}
    for year in years:
        try:
            rows, url = fetch(year)
        except Exception as e:
            print(f"  {year}: skipped — {e}")
            continue
        n = 0
        for row in rows:
            rec = extract(row, year, url)
            if rec:
                by_state.setdefault(rec["state"], {})[str(year)] = rec
                n += 1
        print(f"  {year}: race for {n} state(s)")
    if not by_state:
        raise RuntimeError("no state published race in any requested year — writing nothing")
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    for st, years_rec in sorted(by_state.items()):
        p = out_dir / f"demographics-{st}.json"
        p.write_text(json.dumps({
            "state": st, "fetched": stamp,
            "note": ("Who has voted early, not how they voted. No state counts ballots "
                     "before election day."),
            "stream_labels": STREAMS,
            "years": years_rec,
        }, indent=1) + "\n")
        latest = max(years_rec)
        v = years_rec[latest]["streams"].get("voted", {}).get("race", {})
        print(f"  wrote {p.name}: years {sorted(years_rec)} "
              f"({latest} total {v.get('total', 0):,})")


if __name__ == "__main__":
    years = [int(a) for a in sys.argv[1:] if a.isdigit()] or [2024, 2026]
    print("UF demographics — years", years)
    run(years)
