#!/usr/bin/env python3
"""Minnesota early/absentee history from the state's own file -> data/ev-history-MN.json

Source: sos.mn.gov "Statewide Absentee Voting Statistics 2014 to 2026" (.xlsx)

Minnesota had this on its site the whole time and the board showed 2024 only, taken from
the Election Lab's national file because that was the easy path. The state publishes every
statewide election back to 2014 — transmitted, returned, accepted, and the rejection
reasons.

Note the bot-management asymmetry: scvotes-style challenges block the sos.mn.gov PAGE to a
plain client, but the media file itself serves fine. The page is why Minnesota looked like
a manual-download state; it never needed to be one for history.

SCOPE: statewide only, and Minnesota's "absentee" covers both mail and in-person absentee
(early voting there is absentee by another name), so Accepted is the total early vote for
that cycle. There is no mail/in-person split and no county breakdown in this file.

FAILS CLOSED: any fetch or parse problem raises and writes nothing.
"""
import json, re, sys, pathlib, urllib.request
from datetime import datetime, timezone

URL = ("https://www.sos.mn.gov/media/fmkbeaok/"
       "statewide-absentee-voting-statistics-2014-to-2026.xlsx")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept-Encoding": "identity"}
WANT_ROWS = {"Total Transmitted": "transmitted", "Returned by Voter": "returned",
             "Accepted": "accepted", "Rejected (Total)": "rejected"}


def main():
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from sc_earlyvote import xlsx_rows          # stdlib xlsx reader, no dependency

    with urllib.request.urlopen(urllib.request.Request(URL, headers=UA), timeout=90) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}")
        rows = xlsx_rows(r.read())

    hdr_i = next((i for i, rr in enumerate(rows[:8])
                  if (rr.get("A") or "").strip() == "Statistical Categories"), None)
    if hdr_i is None:
        raise RuntimeError("no 'Statistical Categories' header — layout changed")
    hdr = rows[hdr_i]
    # only the GENERAL elections; primaries are a different animal
    cols = {c: v.strip() for c, v in hdr.items()
            if c != "A" and re.fullmatch(r"\d{4} General", (v or "").strip())}
    if not cols:
        raise RuntimeError(f"no '<year> General' columns in {hdr}")

    vals = {}
    for rr in rows[hdr_i + 1:]:
        label = (rr.get("A") or "").strip()
        if label in WANT_ROWS:
            for c, name in cols.items():
                vals.setdefault(name, {})[WANT_ROWS[label]] = int(
                    re.sub(r"[^\d]", "", rr.get(c, "0") or "0") or 0)

    years = {}
    for name, v in vals.items():
        y = name.split()[0]
        acc = v.get("accepted", 0)
        if not acc:
            continue
        years[y] = {
            "election": f"{y} General",
            "cycle": "presidential" if int(y) % 4 == 0 else "midterm",
            "statewide_only": True, "streams_split": False,
            "state_totals": {
                # Minnesota's absentee covers mail AND in-person absentee, so accepted is
                # the whole early vote. No split is available, so none is invented.
                "returned_combined": {"total": acc},
                "by_mail": acc, "in_person": 0, "total": acc, "registered": 0,
                "in_person_reported": False},
            "detail": v, "source": URL}

    if not years:
        raise RuntimeError("no general elections parsed — refusing")
    out = {"state": "MN", "unit": "state", "party_available": False, "years": years,
           "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "notes": {"scope": "statewide only; Minnesota's absentee covers mail and "
                              "in-person absentee together, so accepted is the total early "
                              "vote and no mail/in-person split exists in this file"}}
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "ev-history-MN.json"
    p.write_text(json.dumps(out, indent=1))
    for y in sorted(years):
        d = years[y]["detail"]
        print(f"MN {y}: transmitted {d.get('transmitted',0):>9,}  returned "
              f"{d.get('returned',0):>9,}  accepted {d.get('accepted',0):>9,}")
    print(f"   -> {p.name}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"MN HISTORY FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
