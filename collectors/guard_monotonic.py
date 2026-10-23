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


def stream_day(payload, key):
    """The date the source gave for THIS stream, where it gives one per stream."""
    comp = payload.get("compiled")
    if isinstance(comp, dict):
        for k in (key, "returned", "outstanding"):
            if k in comp:
                return _day(comp[k])
    return _day(payload.get("as_of") or payload.get("through"))


def _day(s):
    import re
    from datetime import datetime
    s = str(s or "").strip()
    for pat, fmt in ((r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
                     (r"\d{1,2}/\d{1,2}/\d{4}", "%m/%d/%Y"),
                     (r"\d{1,2}-\d{1,2}-\d{4}", "%m-%d-%Y"),
                     (r"\d{1,2}-\d{1,2}-\d{2}(?!\d)", "%m-%d-%y")):
        m = re.search(pat, s)
        if m:
            try:
                return datetime.strptime(m.group(0), fmt).date().isoformat()
            except ValueError:
                continue
    return None


def val(block, key):
    v = (block or {}).get(key)
    if isinstance(v, dict):
        return v.get("total")
    return v if isinstance(v, (int, float)) else None


def repair_snapshots(st, streams, live_totals):
    """Null the same withdrawn stream in the archive, where it was recorded as 0.

    data/snapshots/ is the durable record - the SQLite store is rebuilt from it - so a
    withdrawn figure left in there as 0 comes back on the next rebuild and goes into
    every trend line. South Carolina's mail was recorded as 0 on 2026-10-20, briefly
    appeared as 21,501 on the 21st, and was withdrawn again; UF's South Carolina county
    file currently sums to 0 across all 46 counties, which is to say it publishes no
    South Carolina mail at all.

    Only a 0 is rewritten, and only for a stream the live file now shows as unknown. A
    genuine 0 early in a cycle - before any mail is back - stays a 0 everywhere the
    source is still publishing the field.
    """
    fixed = 0
    for sf in sorted((DATA / "snapshots").glob(f"early-{st}-*.json")):
        try:
            snap = json.loads(sf.read_text())
        except Exception:
            continue
        s = snap.get("state_totals") or {}
        changed = []
        for key in streams:
            if live_totals.get(key) is not None:
                continue                       # still published; leave the archive alone
            if val(s, key) == 0:
                if isinstance(s.get(key), dict):
                    s[key]["total"] = None
                else:
                    s[key] = None
                changed.append(key)
        if not changed:
            continue
        known = 0
        for group in (("by_mail", "mail_returned", "returned"),
                      ("in_person", "early_in_person")):
            for key in group:
                v = val(s, key)
                if v is not None:
                    known += v
                    break
        if "total" in s:
            s["total"] = known or None
        snap["total_excludes"] = changed
        snap.setdefault("notes", {})["withdrawn"] = (
            "The source does not publish this stream; it was recorded as 0 before that "
            "was understood and is shown as unknown.")
        sf.write_text(json.dumps(snap, indent=1) + "\n")
        fixed += 1
        print(f"     repaired archive {sf.name}: {', '.join(changed)} 0 -> null")
    return fixed


def repair_misdated_snapshots():
    """Null a stream in a snapshot whose own compile date is not that snapshot's day.

    A snapshot is one day's state. Where a source stamps each stream separately -
    Florida does - a stream carrying a different date was never a figure for this day,
    and leaving it there makes the day-over-day change wrong in both days: the one it
    was filed under and the one it was taken from.

    Florida's CDN serves no history, so a misfiled figure cannot be replaced with the
    right one. It becomes unknown, which the board already draws as a dash.
    """
    fixed = 0
    for sf in sorted((DATA / "snapshots").glob("early-*.json")):
        try:
            snap = json.loads(sf.read_text())
        except Exception:
            continue
        comp = snap.get("compiled")
        if not isinstance(comp, dict) or len(set(map(_day, comp.values()))) < 2:
            continue
        day = sf.stem.rsplit("-", 3)[-3:]
        day = "-".join(day)
        st = snap.get("state_totals") or {}
        changed = []
        for stream, stamp in comp.items():
            if _day(stamp) == day:
                continue
            for key in ({"returned": ("returned", "mail_returned", "by_mail"),
                         "outstanding": ("outstanding",),
                         "in_person": ("in_person", "early_in_person")}.get(stream, ())):
                if key in st and val(st, key) is not None:
                    if isinstance(st[key], dict):
                        st[key]["total"] = None
                    else:
                        st[key] = None
                    changed.append(f"{key} (compiled {_day(stamp)})")
        if not changed:
            continue
        snap.setdefault("notes", {})["misdated"] = (
            f"Filed as {day}, but these streams were compiled on another day and were "
            f"never figures for it: " + "; ".join(changed) + ". The source serves no "
            f"history, so they are shown as unknown rather than as another day's count.")
        sf.write_text(json.dumps(snap, indent=1) + "\n")
        print(f"     {sf.name}: nulled {', '.join(changed)}")
        fixed += 1
    return fixed


def main():
    hits = 0
    repair_misdated_snapshots()
    # Standing reconciliation, run every time rather than only when something falls.
    # A withdrawal is caught once, but the archive it poisoned stays wrong until it is
    # repaired, and the fall never happens again to trigger that repair. So on every
    # run, any stream the live file reports as unknown is nulled in the archive wherever
    # it sits there as a 0.
    for f in sorted(glob.glob(str(DATA / "early-*.json"))):
        st = os.path.basename(f)[6:-5]
        try:
            live = json.loads(pathlib.Path(f).read_text())
        except Exception:
            continue
        lt = live.get("state_totals") or {}
        unknown = [k for k in CUMULATIVE if k in lt and val(lt, k) is None]
        if unknown:
            repair_snapshots(st, unknown, lt)
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
        # A withdrawn field and a STALE FETCH both look like a number that fell, and
        # they need opposite answers. Florida serves its mail and in-person files from a
        # CDN that can hand back yesterday's copy of one of them; that is not a state
        # un-counting ballots, it is us holding an older file, and the right response is
        # to keep the newer figure already recorded rather than erase it.
        #
        # The source's own date for the stream decides which it is. Older date -> stale
        # fetch, keep what we had. Same or newer date with a smaller number -> the source
        # really did restate or withdraw it, and that becomes unknown.
        od, nd = stream_day(old, fell[0][0]), stream_day(new, fell[0][0])
        if od and nd and nd < od:
            for key, ov, nv in fell:
                if isinstance(n.get(key), dict):
                    n[key]["total"] = ov
                else:
                    n[key] = ov
            # The dates have to travel with the figures. Holding 10/22's numbers while
            # leaving 10/21 in `compiled` made _as_of file them under 10-21, which
            # overwrote the real 10-21 snapshot with the next day's values - the exact
            # misfiling the oldest-date rule was meant to end.
            for field in ("compiled", "as_of", "through"):
                if field in old:
                    new[field] = old[field]
                elif field in new:
                    new.pop(field)
            new.setdefault("notes", {})["stale_fetch"] = (
                f"The source served an older file this run ({nd} against the {od} already "
                f"recorded), so the figures it carried were lower. The newer figures are "
                f"kept: " + "; ".join(f"{k} held at {ov:,}" for k, ov, _ in fell))
            pathlib.Path(f).write_text(json.dumps(new, indent=1) + "\n")
            for key, ov, nv in fell:
                print(f"  {st}: {key} came back {nv:,} from an older file ({nd}); "
                      f"holding the {od} figure {ov:,}")
            continue
        hits += 1
        # NARROW ON PURPOSE. This guard was written for one thing: a source that stops
        # publishing a field and sends 0 in its place, which reads as "none were cast"
        # when it means "no longer published". That is the only case where rewriting a
        # figure is right.
        #
        # It was doing much more than that, and it twice damaged Florida. Holding a
        # value against a stale fetch and carrying the old date with it filed the next
        # day's numbers under the previous day. Then, on the following run, the held
        # date made a genuinely older file look like a withdrawal, and Florida's mail
        # was nulled outright - 1.1M ballots gone from the board.
        #
        # So: a fall to exactly ZERO becomes null. Any other fall is reported and left
        # alone, because a collector's own output is more trustworthy than this guard's
        # guess about why it moved. Dates are never touched.
        zeroed = [(k, ov, nv) for k, ov, nv in fell if nv == 0]
        other = [(k, ov, nv) for k, ov, nv in fell if nv != 0]
        for key, ov, nv in other:
            print(f"  {st}: {key} fell {ov:,} -> {nv:,} — FLAGGED, value left as the "
                  f"collector wrote it")
        if other:
            new.setdefault("notes", {})["fell"] = (
                "A figure is lower than this board last recorded: "
                + "; ".join(f"{k} was {ov:,}, now {nv:,}" for k, ov, nv in other)
                + ". Ballots already cast do not un-cast, so the source has restated "
                  "something or served an older file. The number shown is the one the "
                  "source gave.")
        for key, ov, nv in zeroed:
            if isinstance(n.get(key), dict):
                n[key]["total"] = None
            else:
                n[key] = None
            print(f"  {st}: {key} fell {ov:,} -> 0 — set to null, not 0")
        if zeroed:
            known = 0
            for group in (("by_mail", "mail_returned", "returned"),
                          ("in_person", "early_in_person")):
                for key in group:
                    v = val(n, key)
                    if v is not None:
                        known += v
                        break
            if "total" in n:
                n["total"] = known or None
            new["total_excludes"] = [k for k, _, _ in zeroed]
            new.setdefault("notes", {})["withdrawn"] = (
                "The source sent 0 for a figure it had been publishing, which means it "
                "is no longer published rather than that none were cast. It is shown as "
                "unknown, and the total covers only the streams still published: "
                + "; ".join(f"{k} was {ov:,}" for k, ov, _ in zeroed))
        pathlib.Path(f).write_text(json.dumps(new, indent=1) + "\n")
        if zeroed:
            repair_snapshots(st, [k for k, _, _ in zeroed], n)
    print(f"monotonic guard: {hits} state(s) with a withdrawn figure"
          if hits else "monotonic guard: no cumulative figure fell")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as e:
        print(f"MONOTONIC GUARD FAILED: {e}", file=sys.stderr)
        sys.exit(1)
