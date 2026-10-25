#!/usr/bin/env python3
"""Check every state against the UF Election Lab's own headline -> data/tie-out.json

This exists because the board was wrong for days at a time and the only thing that
caught it was someone comparing numbers by hand. Minnesota was 216,937 light for a
week, Florida 539,936, Texas was missing 3.7M ballots entirely, and in each case the
collectors reported success: a stale figure is still a figure, and nothing downstream
knew it was old.

So every run now asks the one question a human was asking: does this tie out? The Lab
publishes a national row per state, rebuilt more often than anything else it ships, and
it is independent of how this board gets its own numbers. Where we are BEHIND it, we
have a staleness problem. Where we are ahead, we have a fresher source than the Lab -
North Carolina usually is, because it comes from the state directly.

A gap is not automatically a fault. Georgia's comes from the Lab's own county file
lagging its national file by hours, and that is noted on the card rather than treated
as a break. What matters is that the gap is MEASURED on every run and visible, instead
of waiting for someone to notice the totals look small.

Never fails the pull: a check that can break the thing it checks is worse than no check.
"""
import csv, io, json, pathlib, sys, urllib.request, gzip, glob, os
from datetime import datetime, timezone

US = "https://election.lab.ufl.edu/data-downloads/earlyvote/2026/US.csv"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept-Encoding": "gzip"}
DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
# Below this a difference is rounding or a few minutes of drift, not a problem.
FLOOR, SHARE = 2000, 0.02


def fetch():
    with urllib.request.urlopen(urllib.request.Request(US, headers=UA), timeout=90) as r:
        body = r.read()
        lm = r.headers.get("Last-Modified")
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8", "ignore"))))
    if not rows or "state_abbv" not in rows[0]:
        raise RuntimeError("UF national file did not parse")
    return {r["state_abbv"]: r for r in rows}, lm


def num(v):
    v = (v or "").strip().replace(",", "")
    try:
        return int(float(v))
    except ValueError:
        return 0


def board_total(s):
    """What the card adds up, by whichever names this state's source uses."""
    g = lambda k: (s[k].get("total") if isinstance(s.get(k), dict) else s.get(k)) if k in s else None
    mail = next((g(k) for k in ("by_mail", "mail_returned", "returned") if g(k) is not None), 0)
    ip = next((g(k) for k in ("in_person", "early_in_person") if g(k) is not None), 0)
    return (mail or 0) + (ip or 0)


def main():
    uf, lm = fetch()
    states, behind_total, behind = {}, 0, []
    for f in sorted(glob.glob(str(DATA / "early-*.json"))):
        st = os.path.basename(f)[6:-5]
        try:
            d = json.loads(pathlib.Path(f).read_text())
        except Exception:
            continue
        ours = board_total(d.get("state_totals") or {})
        theirs = num((uf.get(st) or {}).get("voted_all"))
        gap = theirs - ours
        tol = max(FLOOR, theirs * SHARE)
        if not theirs:
            verdict = "no UF row"
        elif abs(gap) <= tol:
            verdict = "ties out"
        elif gap > 0:
            verdict = "behind"
            behind_total += gap
            behind.append(st)
        else:
            verdict = "ours is newer"
        states[st] = {"board": ours, "uf": theirs, "gap": gap, "verdict": verdict,
                      "as_of": d.get("as_of"),
                      "source": "UF" if "ufl.edu" in str(d.get("source") or "") else "direct"}
    out = {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "uf_file_modified": lm,
           "board_total": sum(v["board"] for v in states.values()),
           "uf_total": sum(v["uf"] for v in states.values()),
           "behind_states": behind, "behind_ballots": behind_total,
           "ties_out": sum(1 for v in states.values() if v["verdict"] == "ties out"),
           "checked": len(states),
           "note": ("Each state against the UF Election Lab's national row, which is "
                    "independent of how this board collects. BEHIND means this board is "
                    "stale, not that the sources disagree - a count cannot fall as time "
                    "passes."),
           "states": states}
    (DATA / "tie-out.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"tie-out: {out['ties_out']}/{out['checked']} tie out; "
          f"behind by {behind_total:,} ballots"
          + (f" ({', '.join(behind)})" if behind else ""))
    for st in behind:
        v = states[st]
        print(f"   {st} behind {v['gap']:,} — board {v['board']:,} vs UF {v['uf']:,}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as e:
        # Never fail the pull over the check itself.
        print(f"tie-out: could not check ({e})", file=sys.stderr)
        sys.exit(0)
