#!/usr/bin/env python3
"""UF Election Lab early-vote tracker -> one row per state per day.

Dr. McDonald's tracker carries early/mail ballots cast broken out by party
registration, age, gender and race. One page per state, server-rendered.

Writes data/trend-earlyvote.json as an APPEND-ONLY series keyed (date, state),
so running this daily builds the trend the site itself doesn't offer.

FAILS CLOSED: a state that errors is skipped and logged; the existing series is
never truncated, and a run that resolves nothing exits non-zero without writing.
"""
import json, re, sys, html, pathlib, urllib.request
from datetime import datetime, timezone

BASE = "https://election.lab.ufl.edu/early-vote/2026-early-voting/2026-general-election-early-vote-{}/"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
STATES = {"FL":"florida","MI":"michigan","MN":"minnesota","ME":"maine","NE":"nebraska",
          "AK":"alaska","OH":"ohio","IA":"iowa","TX":"texas","KS":"kansas",
          "SC":"south-carolina","NC":"north-carolina","GA":"georgia"}
TAG = re.compile(r"<[^>]+>")
NUM = re.compile(r"^[\d,]+$")


def tables(doc):
    """Every <table> as a list of row-cell-lists, tags stripped."""
    out = []
    for tb in re.findall(r"<table[^>]*>(.*?)</table>", doc, re.S | re.I):
        rows = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tb, re.S | re.I):
            cells = [html.unescape(TAG.sub("", c)).strip()
                     for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S | re.I)]
            if cells:
                rows.append(cells)
        if rows:
            out.append(rows)
    return out


def fetch(slug):
    url = BASE.format(slug)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}")
        doc = r.read().decode("utf-8", "ignore")
    cuts = {}
    for rows in tables(doc):
        head = [h.lower() for h in rows[0]]
        if len(head) < 2 or "totalvoted" not in "".join(head).lower().replace(" ", ""):
            continue
        kind = head[0] or "unknown"
        vals = {}
        for r_ in rows[1:]:
            if len(r_) >= 2 and NUM.match(r_[1].strip()):
                vals[r_[0]] = int(r_[1].replace(",", ""))
        if vals:
            cuts[kind] = vals
    if "party" not in cuts:
        raise RuntimeError("no party table — layout changed or state not reporting")
    return url, cuts


def main():
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "trend-earlyvote.json"
    series = json.loads(p.read_text())["series"] if p.exists() else []
    today = datetime.now(timezone.utc).date().isoformat()
    got, failed = 0, []
    for ab, slug in STATES.items():
        try:
            url, cuts = fetch(slug)
        except Exception as e:
            failed.append(f"{ab}:{e}")
            continue
        series = [s for s in series if not (s["date"] == today and s["state"] == ab)]
        series.append({"date": today, "state": ab, "source": url, "cuts": cuts,
                       "party_total": sum(cuts["party"].values())})
        got += 1
    if not got:
        raise RuntimeError(f"no state resolved — writing nothing. {'; '.join(failed)}")
    series.sort(key=lambda s: (s["date"], s["state"]))
    p.write_text(json.dumps({"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                             "series": series}, indent=1))
    print(f"ok: {got}/{len(STATES)} states, {len(series)} rows in series -> {p.name}")
    for ab in sorted({s['state'] for s in series if s['date'] == today}):
        row = next(s for s in series if s["date"] == today and s["state"] == ab)
        pr = row["cuts"]["party"]
        bits = "  ".join(f"{k[:3]} {v:,}" for k, v in list(pr.items())[:4])
        print(f"   {ab}  {row['party_total']:>9,}   {bits}")
    if failed:
        print("   not reporting: " + ", ".join(f.split(':')[0] for f in failed), file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
