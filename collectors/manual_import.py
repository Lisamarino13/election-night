#!/usr/bin/env python3
"""Parse hand-downloaded files from data/manual/ -> data/early-<ST>.json

Three states publish what we need but gate it behind bot-management or a CAPTCHA, which
this repo does not try to defeat. They are fetched by hand instead and parsed here.

    data/manual/MN-<YYYY-MM-DD>.html   Minnesota absentee page, saved from the browser
    data/manual/GA-<YYYY-MM-DD>.csv    Georgia absentee file (statewide)
    data/manual/OH-<YYYY-MM-DD>.txt    Ohio Absentee_Request_Report.txt

Run it with no arguments; it takes the NEWEST file per state and ignores the rest, so you
can keep every day's download in the folder as an archive.

MINNESOTA is implemented: its county table is server-rendered in the page HTML, columns
County / Applications / Accepted ballots - by mail / Accepted ballots - in person, 87 rows.
There is no party registration in Minnesota, so this is turnout only — party_available is
false and the board shows a turnout card rather than inventing a split.

Outstanding is derived: applications minus accepted. That is ballots applied for and not
yet accepted, which is the closest thing Minnesota publishes to an outstanding count, and
it is labelled as derived rather than presented as a reported figure.

GEORGIA and OHIO are not implemented yet — their formats are unseen. They are listed as
TODO rather than guessed at, because a parser written against an imagined layout is how
you get numbers that look right and are not.

FAILS CLOSED: any parse problem raises and writes nothing.
"""
import json, re, sys, pathlib, html.parser, collections
from datetime import datetime, timezone

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
MANUAL = DATA / "manual"


class TableGrab(html.parser.HTMLParser):
    """Collect every table as a list of rows of cell text."""
    def __init__(self):
        super().__init__()
        self.tables, self._t, self._r, self._c, self._in = [], None, None, None, False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._t = []
        elif tag == "tr" and self._t is not None:
            self._r = []
        elif tag in ("td", "th") and self._r is not None:
            self._c, self._in = [], True

    def handle_endtag(self, tag):
        if tag == "table" and self._t is not None:
            self.tables.append(self._t); self._t = None
        elif tag == "tr" and self._r is not None and self._t is not None:
            if any(x.strip() for x in self._r):
                self._t.append(self._r)
            self._r = None
        elif tag in ("td", "th") and self._c is not None:
            self._r.append(re.sub(r"\s+", " ", "".join(self._c)).strip())
            self._c, self._in = None, False

    def handle_data(self, d):
        if self._in and self._c is not None:
            self._c.append(d)


def _iso(v):
    """Any of these sources' date stamps as ISO, so two of them can be compared."""
    import re
    from datetime import datetime
    v = str(v or "").strip()
    for pat, fmt in ((r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
                     (r"\d{1,2}/\d{1,2}/\d{4}", "%m/%d/%Y"),
                     (r"\d{1,2}-\d{1,2}-\d{4}", "%m-%d-%Y"),
                     (r"\d{1,2}-\d{1,2}-\d{2}(?!\d)", "%m-%d-%y")):
        m = re.search(pat, v)
        if m:
            try:
                return datetime.strptime(m.group(0), fmt).date().isoformat()
            except ValueError:
                continue
    return ""


def num(s):
    s = re.sub(r"[^\d-]", "", s or "")
    return int(s) if s else None


def parse_mn(path, as_of):
    p = TableGrab()
    p.feed(path.read_text(encoding="utf-8", errors="ignore"))
    want = ("county", "applications")
    table = None
    for t in p.tables:
        if len(t) >= 80 and len(t[0]) >= 4 and all(w in " ".join(t[0]).lower() for w in want):
            table = t
            break
    if table is None:
        raise RuntimeError(f"{path.name}: no county table found. Save the page with "
                           f"File > Save As > Page Source (.html), not a screenshot or PDF")
    hdr = [h.lower() for h in table[0]]
    try:
        i_cty = next(i for i, h in enumerate(hdr) if "county" in h)
        i_app = next(i for i, h in enumerate(hdr) if "application" in h)
        i_mail = next(i for i, h in enumerate(hdr) if "mail" in h)
        i_ip = next(i for i, h in enumerate(hdr) if "person" in h)
    except StopIteration:
        raise RuntimeError(f"{path.name}: unexpected columns {table[0]} — layout changed")

    counties, tot = {}, collections.Counter()
    for row in table[1:]:
        if len(row) <= max(i_cty, i_app, i_mail, i_ip):
            continue
        name = row[i_cty].strip()
        if not name or name.lower().startswith(("total", "statewide")):
            continue
        app, mail, ip = num(row[i_app]), num(row[i_mail]), num(row[i_ip])
        if app is None:
            continue
        accepted = (mail or 0) + (ip or 0)
        counties[name] = {"applications": app, "by_mail": mail or 0,
                          "in_person": ip or 0, "total": accepted,
                          # derived, not reported: applied for and not yet accepted
                          "outstanding_derived": max(app - accepted, 0)}
        tot["applications"] += app; tot["by_mail"] += mail or 0
        tot["in_person"] += ip or 0; tot["total"] += accepted
        tot["outstanding_derived"] += max(app - accepted, 0)
    if len(counties) < 80:
        raise RuntimeError(f"{path.name}: {len(counties)} counties, Minnesota has 87 — refusing")

    return {"state": "MN", "unit": "county", "election": "2026 General", "as_of": as_of,
            "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "party_available": False, "outstanding_available": False,
            "in_person": tot["in_person"] > 0,
            "counties": counties, "state_totals": dict(tot),
            "source": "https://www.sos.mn.gov/election-administration-campaigns/"
                      "data-maps/absentee-data/ (saved by hand)",
            "notes": {"outstanding": "derived as applications minus accepted; Minnesota "
                                     "does not publish an outstanding figure directly"}}


PARSERS = {"MN": parse_mn}
TODO = {"GA": "send one downloaded file and this gets written",
        "OH": "send one Absentee_Request_Report.txt and this gets written"}


def newest_per_state():
    out = {}
    if not MANUAL.exists():
        return out
    for f in MANUAL.iterdir():
        m = re.match(r"^([A-Z]{2})-(\d{4}-\d{2}-\d{2})\.", f.name)
        if m and f.is_file():
            st, day = m.group(1), m.group(2)
            if st not in out or day > out[st][1]:
                out[st] = (f, day)
    return out


def main():
    found = newest_per_state()
    if not found:
        print(f"nothing in {MANUAL.relative_to(DATA.parent)} — see its README for names")
        return 0
    wrote = 0
    for st, (path, day) in sorted(found.items()):
        if st in PARSERS:
            payload = PARSERS[st](path, day)
            out = DATA / f"early-{st}.json"
            # A hand-saved file beats an aggregate only while it is still the fresher
            # of the two. Minnesota's was saved on 2026-10-16 and kept overwriting the
            # UF Election Lab's copy every hour for a week: the board showed 202,252 for
            # Minnesota while the Lab had 419,189, because a primary source was allowed
            # to win on being primary alone rather than on being current.
            if out.exists():
                try:
                    have = json.loads(out.read_text())
                except Exception:
                    have = {}
                # Normalise before comparing. These sources stamp dates in whatever
                # format they like, and "10/23/2026" > "2026-10-16" is false as a string
                # comparison - "1" sorts before "2" - so a fresher file lost to a
                # week-old one on the first character.
                cur = _iso(have.get("as_of") or have.get("through"))
                if cur and cur > _iso(day):
                    print(f"{st}: holding — {out.name} is dated {cur}, the hand file is "
                          f"{day}. A saved file only wins while it is the fresher one.",
                          file=sys.stderr)
                    continue
            out.write_text(json.dumps(payload, indent=1))
            t = payload["state_totals"]
            print(f"{st} ok: {len(payload['counties'])} counties, as of {day}  <- {path.name}")
            print(f"   applications {t.get('applications',0):>9,}")
            print(f"   accepted mail{t.get('by_mail',0):>9,}   in person {t.get('in_person',0):>9,}")
            print(f"   -> {out.name}")
            wrote += 1
        elif st in TODO:
            print(f"{st}: parser not written yet — {TODO[st]} ({path.name})", file=sys.stderr)
        else:
            print(f"{st}: no parser and not a known manual state ({path.name})", file=sys.stderr)
    return 0 if wrote or not found else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"MANUAL IMPORT FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
