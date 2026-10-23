#!/usr/bin/env python3
"""Catch a cumulative early-vote figure that went DOWN, and refuse to publish it as a count.

Ballots already cast and accepted do not un-cast. Within one election a returned /
accepted / in-person total can only rise, so a fall means the source changed its mind,
withdrew a figure, or broke - not that voters disappeared.

This happened on 2026-10-23. The UF Election Lab had been carrying 21,501 returned mail
ballots for South Carolina; it switched that field to 0, and the collector wrote the 0
through. South Carolina's board total silently dropped by 21,501 and nothing said so.
A zero there is a lie of a particular kind: it reads as "none were cast", when the truth
is "the source no longer publishes this".

So a stream that falls is set to NULL, not left at its new lower value and not quietly
restored to the old one. Null is what the board already knows how to draw - a dash, with
the reason beside it - and it keeps the state out of any sum it would otherwise distort.

Compares against the last committed copy, so it only ever fires on a real regression.
"""
import json, pathlib, subprocess, sys, glob, os

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
# cumulative streams only. "outstanding" and "requested" legitimately fall as ballots
# come back, and "registered" can be restated, so none of those are checked here.
CUMULATIVE = ("by_mail", "mail_returned", "returned", "in_person", "early_in_person",
              "total", "returned_combined")


def committed(path):
    r = subprocess.run(["git", "show", f"HEAD:{path}"], capture_output=True, text=True,
                       cwd=str(DATA.parent))
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


def val(block, key):
    v = (block or {}).get(key)
    if isinstance(v, dict):
        return v.get("total")
    return v if isinstance(v, (int, float)) else None


def main():
    hits = 0
    for f in sorted(glob.glob(str(DATA / "early-*.json"))):
        rel = os.path.relpath(f, DATA.parent)
        st = os.path.basename(f)[6:-5]
        old = committed(rel)
        if not old:
            continue
        new = json.loads(pathlib.Path(f).read_text())
        o, n = old.get("state_totals") or {}, new.get("state_totals") or {}
        fell = []
        for key in CUMULATIVE:
            ov, nv = val(o, key), val(n, key)
            if ov is None or nv is None:
                continue
            if nv < ov:
                fell.append((key, ov, nv))
        if not fell:
            continue
        hits += 1
        for key, ov, nv in fell:
            if isinstance(n.get(key), dict):
                n[key]["total"] = None
            else:
                n[key] = None
            print(f"  {st}: {key} fell {ov:,} -> {nv:,} — set to null, not {nv:,}")
        # The total is rebuilt from the streams that ARE still known rather than
        # nulled outright: South Carolina's 280,114 in-person votes are real and
        # unaffected, and a dash there would throw away more than it protects. What
        # the total no longer includes is named, so the board can say so on the card
        # instead of just showing a smaller number than last time.
        gone = [k for k, _, _ in fell
                if k in ("by_mail", "mail_returned", "returned", "in_person",
                         "early_in_person")]
        if gone:
            known = 0
            for key in ("by_mail", "mail_returned", "returned"):
                v = val(n, key)
                if v is not None:
                    known += v
                    break
            for key in ("in_person", "early_in_person"):
                v = val(n, key)
                if v is not None:
                    known += v
                    break
            n["total"] = known or None
            new["total_excludes"] = gone
        new.setdefault("notes", {})
        new["notes"]["withdrawn"] = (
            "A figure this board had already recorded was lower in the source's latest "
            "file. Ballots already cast do not un-cast, so the source has withdrawn or "
            "restated it; it is shown as unknown rather than as the smaller number, and "
            "the total covers only the streams still published. "
            + "; ".join(f"{k}: was {ov:,}, now {nv:,}" for k, ov, nv in fell))
        new["withdrawn_streams"] = [k for k, _, _ in fell]
        pathlib.Path(f).write_text(json.dumps(new, indent=1) + "\n")
    print(f"monotonic guard: {hits} state(s) with a withdrawn figure"
          if hits else "monotonic guard: no cumulative figure fell")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as e:
        print(f"MONOTONIC GUARD FAILED: {e}", file=sys.stderr)
        sys.exit(1)
