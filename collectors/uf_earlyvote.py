#!/usr/bin/env python3
"""UF Election Lab early-vote CSVs -> data/early-<ST>.json, for states with no usable feed

Source: election.lab.ufl.edu/data-downloads/earlyvote/2026/<ST>_county.csv
Plain CSV, one row per county, refreshed daily. Found by watching what the Election Lab's
own state pages fetch; the pages render from JS, the CSVs underneath do not.

WHY A SECOND-HAND SOURCE AT ALL. Some states simply do not publish a daily early-vote file
on the web:
    Nebraska  the SOS produces one and hands it to the Election Lab, but does not post it
    Kansas    same arrangement
    Michigan  same arrangement
    Georgia   the state's own file is behind reCAPTCHA Enterprise
    Ohio      behind Cloudflare, no reachable file endpoint
    Minnesota behind Radware bot-management
This repo does not defeat CAPTCHAs or bot-management, so for these six the Election Lab is
the only route that does not involve circumventing a control. Each payload records both the
Election Lab and the upstream source it names, so the provenance is never hidden.

STATES WITH A DIRECT FEED ARE DELIBERATELY NOT TAKEN FROM HERE. Florida, North Carolina,
Maine, Iowa and Texas are pulled from the state itself, because the state gives strictly
more: Florida's per-county outstanding by party, Maine's 560 municipalities, Iowa's receipt
methods, Texas's registered-voter denominators. A secondhand aggregate is the fallback, not
the default.

Columns: request_* (mail requested), accept_* (mail returned), inperson_*, voted_*, each
with _all/_dem/_rep/_none. Outstanding is request_all - accept_all, which is mail requested
and not yet returned — derived, and labelled as derived.

A state whose party columns are all zero has no party registration (GA, MI, MN, OH). Those
are written as turnout-only rather than as "100% unaffiliated".

FAILS CLOSED: any fetch or parse problem for a state raises; other states still run.
"""
import json, csv, io, sys, pathlib, urllib.request, collections
from datetime import datetime, timezone

BASE = "https://election.lab.ufl.edu/data-downloads/earlyvote/2026/"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept-Encoding": "identity"}
# Only states with no usable direct feed. FL/NC/ME/IA/TX are pulled from the state itself.
STATES = {"NE": "Nebraska", "KS": "Kansas", "GA": "Georgia",
          "MI": "Michigan", "OH": "Ohio", "MN": "Minnesota"}

# IOWA joined the fallback set on 2026-10-22. sos.iowa.gov began returning 403 to every
# path on 10-20 — from the laptop AND the VM, so it is the site, not a rate limit on us —
# and the direct pull has failed every tick since. Unlike Maine, the Lab's Iowa carries
# party AND the mail/in-person split, so it is a clean substitute rather than a downgrade;
# it is still a fallback so the richer state parse (which also has receipt methods) resumes
# automatically if the block lifts.
#
# Maine is a FALLBACK ONLY, and deliberately so. maine.gov blocks the cron VM's datacenter
# IP, so Maine normally comes from laptop.sh. The Election Lab does carry Maine, but it
# lumps mail and in-person into one "accepted" figure, and those two streams break very
# differently there (mail D+37, in-person D+30). Overwriting the direct parse with that
# would quietly destroy the split.
#
# So the Lab's copy is written ONLY when the direct data has gone properly stale — more
# than STALE_DAYS behind what the Lab has. That bounds how out of date Maine can get if
# nobody runs the laptop command, without downgrading it the rest of the time.
# FLORIDA joined on 2026-10-23. Its own CDN serves whatever that edge node happens to
# hold, and it sat on 10/21 files while the Election Lab - reading the SAME Florida
# source - was two days ahead. The board showed 1,587,693 for Florida against the Lab's
# 2,127,629, half a million ballots behind, because a direct feed was trusted for being
# direct rather than for being current. The direct parse is still preferred: it carries
# party, outstanding mail and the county detail the Lab's state row does not, and it
# resumes the moment the CDN catches up.
# TEXAS joined on 2026-10-25. tx_earlyvote.py reads the Texas SOS directly and the SOS
# had still not posted a 2026 election, so it exited 2 - "not published yet" - on every
# tick and the board showed nothing for Texas. The Election Lab had 3,688,224 Texas
# ballots by 10/24, compiled from the counties rather than from the SOS. The largest
# state on the board was missing entirely because one publisher was quiet and nothing
# looked anywhere else. The direct parse still wins the moment the SOS does publish.
FALLBACK = {"ME": "Maine", "IA": "Iowa", "FL": "Florida", "TX": "Texas"}

# ALASKA has no county file at the Lab - only its row in the national one - so it cannot
# be pulled the way every other state here is, and it was the one state on the board with
# NO early-vote figure at all. A state-level number is worth having and is better than a
# blank card, but it carries no per-county detail, so the per-county projection cannot
# run there and the payload says so rather than implying otherwise.
STATE_ONLY = {"AK": "Alaska"}
# How far behind a direct parse may fall before the Lab's copy replaces it. This is a
# judgement about how much VOTE is at stake, not just how many days, so it is per state.
# Maine added about 2,000 ballots a day at this point and a two-day tolerance costs
# almost nothing against the mail/in-person split its direct parse carries. Florida adds
# 200,000-400,000 a day, so the same two days hid 539,936 ballots: Florida may not be
# behind at all.
STALE_DAYS = 2
STALE_DAYS_BY_STATE = {"FL": 0}
# Only these three are universal. The rest vary by what the state collects: party columns
# exist only where there is party registration (NE, KS), in-person is absent entirely for
# Michigan, and Georgia carries age and race instead. Demanding the full set rejected four
# states whose files were perfectly fine.
EXPECT = {"county", "request_all", "accept_all"}
EMPTY = {"R": 0, "D": 0, "NPA": 0, "O": 0, "total": 0}


def get(url, timeout=60):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status} for {url}")
        return r.read().decode("utf-8", "ignore")


def n(row, key):
    v = (row.get(key) or "").strip().replace(",", "")
    try:
        return int(v)
    except ValueError:
        return 0


def national():
    """US.csv -> {ST: {...}} for provenance AND as a cross-check on the county files.

    The Lab publishes a per-state national file and per-state county files, and they can
    disagree: on 2026-10-22 Kansas's county file summed to 55,481 while US.csv said 91,185,
    both stamped 10/21. Every other state matched exactly. We use the county file because
    the projection needs county-level data, so when the two disagree we are faithfully
    reproducing the lower one while their own headline shows the higher — which is exactly
    the kind of gap someone cross-checking will hit. Capture the national figure so the
    discrepancy can be stated on the card instead of looking like our error.
    """
    out = {}
    for r in csv.DictReader(io.StringIO(get(BASE + "US.csv"))):
        st = (r.get("state_abbv") or "").strip().upper()
        if not st:
            continue
        num = lambda k: int((r.get(k) or "0").replace(",", "") or 0)
        out[st] = {"last_update": (r.get("last_update") or "").strip(),
                   "data_source": (r.get("data_source") or "").strip(),
                   "notes": (r.get("notes") or "").strip(),
                   "nat_mail": num("accept_all"), "nat_ip": num("inperson_all"),
                   "nat_voted": num("voted_all"), "nat_requested": num("request_all")}
    return out


def pull(st, meta):
    rows = list(csv.DictReader(io.StringIO(get(f"{BASE}{st}_county.csv"))))
    if not rows:
        raise RuntimeError(f"{st}: empty CSV")
    missing = EXPECT - set(rows[0])
    if missing:
        raise RuntimeError(f"{st}: columns {sorted(missing)} missing — layout changed")

    cols = set(rows[0])
    has_party = {"accept_dem", "accept_rep"} <= cols
    has_ip = "inperson_all" in cols
    party = has_party and any(n(r, "accept_dem") or n(r, "accept_rep") for r in rows)
    counties, tot = {}, collections.Counter()
    for r in rows:
        name = (r.get("county") or "").strip()
        if not name:
            continue
        req, acc = n(r, "request_all"), n(r, "accept_all")
        ip = n(r, "inperson_all") if has_ip else 0
        out = max(req - acc, 0)
        if party:
            counties[name] = {
                "returned": {"D": n(r, "accept_dem"), "R": n(r, "accept_rep"),
                             "NPA": n(r, "accept_none"), "O": 0, "total": acc},
                "early_in_person": {"D": n(r, "inperson_dem"), "R": n(r, "inperson_rep"),
                                    "NPA": n(r, "inperson_none"), "O": 0, "total": ip},
                "outstanding": {"D": max(n(r, "request_dem") - n(r, "accept_dem"), 0),
                                "R": max(n(r, "request_rep") - n(r, "accept_rep"), 0),
                                "NPA": max(n(r, "request_none") - n(r, "accept_none"), 0),
                                "O": 0, "total": out}}
        else:
            counties[name] = {"by_mail": acc, "in_person": ip, "total": acc + ip,
                              "registered": None, "requested": req,
                              "outstanding_derived": out}
            if not has_ip:
                counties[name].pop("in_person")       # Michigan does not report it
        tot["requested"] += req; tot["by_mail"] += acc
        tot["in_person"] += ip; tot["total"] += acc + ip; tot["outstanding"] += out
        if has_party:
            for p, col in (("D", "dem"), ("R", "rep"), ("NPA", "none")):
                tot[f"ret_{p}"] += n(r, f"accept_{col}")
                tot[f"ip_{p}"] += n(r, f"inperson_{col}") if has_ip else 0
                tot[f"out_{p}"] += max(n(r, f"request_{col}") - n(r, f"accept_{col}"), 0)

    if len(counties) < 10:
        raise RuntimeError(f"{st}: only {len(counties)} counties — refusing")

    m = meta.get(st, {})
    # cross-check this county file against the Lab's own national figure.
    #
    # The two are not peers. The Lab rebuilds its national file more often than its
    # per-state county files, so a county file can be many hours behind it. Calling
    # that "the sources disagree" was wrong and it hid a real staleness: a cumulative
    # count cannot be LOWER with more time behind it, so when ours is the smaller
    # number we are simply the older one, and the card should say so.
    nat = (m.get("nat_mail", 0) or 0) + (m.get("nat_ip", 0) or 0)
    cty = tot["by_mail"] + tot["in_person"]
    mismatch = None
    if nat and abs(cty - nat) > 500:
        _cm = _last_modified(f"{BASE}{st}_county.csv")
        _nm = _last_modified(f"{BASE}US.csv")
        # ISO strings in the payload: a datetime is not JSON-serialisable, and writing
        # one silently killed the whole write, so the stale note stayed on the card.
        mismatch = {"county_file": cty, "national_file": nat, "diff": cty - nat,
                    "county_file_modified": _cm.isoformat() if _cm else None,
                    "national_file_modified": _nm.isoformat() if _nm else None}
        how = "behind" if cty < nat else "ahead of"
        print(f"   {st}: county file totals {cty:,}, {how} the Lab's national file at "
              f"{nat:,} ({cty-nat:+,}) — county file kept for its per-county detail",
              file=sys.stderr)
    payload = {"state": st, "unit": "county", "election": "2026 General",
               "as_of": m.get("last_update") or None,
               "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "party_available": party, "outstanding_available": False,
               "in_person": has_ip and tot["in_person"] > 0,
               "in_person_reported": has_ip,
               "counties": counties,
               "source": f"{BASE}{st}_county.csv",
               "attribution": {
                   "aggregator": "UF Election Lab (election.lab.ufl.edu)",
                   "upstream": m.get("data_source") or "unstated",
                   # the CSV writes "NA" for "no note"; rendering that literally put
                   # "How this is counted: NA" on cards that have nothing to caveat
                   "note": ("" if (m.get("notes") or "").strip().upper() in ("", "NA")
                            else m["notes"].strip())},
               "notes": {"outstanding": "derived as mail requested minus mail returned; "
                                        "not a figure the state publishes directly"}}
    if mismatch:
        payload["source_mismatch"] = mismatch
        cm, nm = _cm, _nm
        lag = ""
        if cm and nm:
            try:
                hrs = round((nm - cm).total_seconds() / 3600)
                if hrs > 0:
                    lag = (f" The county file was last written {hrs} hour"
                           f"{'s' if hrs != 1 else ''} before the national one.")
            except Exception:
                pass
        if mismatch["diff"] < 0:
            payload["notes"]["mismatch"] = (
                f"This figure is {abs(mismatch['diff']):,} BEHIND the Election Lab's own "
                f"headline for {st}: their county file totals "
                f"{mismatch['county_file']:,}, their national file {mismatch['national_file']:,}."
                f"{lag} A count cannot fall as time passes, so this is staleness and not "
                f"a disagreement. The county file is kept because a per-county projection "
                f"needs per-county numbers, and it catches up when the Lab rewrites it.")
        else:
            payload["notes"]["mismatch"] = (
                f"the Election Lab's county file totals {mismatch['county_file']:,} while "
                f"its own national file says {mismatch['national_file']:,}."
                f"{lag} The county file is used here, for its per-county detail")
    if party:
        payload["state_totals"] = {
            "returned": {"D": tot["ret_D"], "R": tot["ret_R"], "NPA": tot["ret_NPA"],
                         "O": 0, "total": tot["by_mail"]},
            "early_in_person": {"D": tot["ip_D"], "R": tot["ip_R"], "NPA": tot["ip_NPA"],
                                "O": 0, "total": tot["in_person"]},
            "outstanding": {"D": tot["out_D"], "R": tot["out_R"], "NPA": tot["out_NPA"],
                            "O": 0, "total": tot["outstanding"]}}
    else:
        payload["state_totals"] = {"registered": 0, "by_mail": tot["by_mail"],
                                   "in_person": tot["in_person"], "total": tot["total"],
                                   "requested": tot["requested"]}
    return payload, tot, party


def _date(v):
    """A loose date -> date, or None."""
    from datetime import date as _d
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%y", "%m/%d/%y"):
        try:
            return datetime.strptime(str(v).strip(), fmt).date()
        except (ValueError, TypeError):
            pass
    import re as _re
    m = _re.search(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", str(v or ""))
    return _date(m.group(0)) if m else None


def direct_is_fresh(path, uf_as_of, st=None):
    """True when the existing (direct) file is recent enough to keep."""
    if not path.exists():
        return False
    try:
        existing = json.loads(path.read_text())
    except Exception:
        return False
    if existing.get("fallback"):
        # Already the Lab's own copy from a previous run. Comparing its date against the
        # Lab's would say "fresh" and hold, freezing the state until it aged past the
        # threshold — update once — freeze again. A fallback file is always replaced.
        return False
    # Florida carries no as_of at all - it stamps each file separately in `compiled` -
    # so this returned True for it on every run since the fallback was added, and
    # Florida was held no matter how far behind it fell. Where there is no as_of, the
    # oldest compile stamp is the date, the same rule the store uses: a payload built
    # from several files is only current to the oldest of them.
    stamp = existing.get("as_of") or existing.get("through")
    if not stamp:
        comp = existing.get("compiled")
        if isinstance(comp, dict) and comp:
            dates = [d for d in (_date(v) for v in comp.values()) if d]
            stamp = min(dates).isoformat() if dates else None
    if not stamp:
        return True                       # genuinely undatable; do not clobber on a guess
    mine, theirs = _date(stamp), _date(uf_as_of)
    if not mine or not theirs:
        return True
    return (theirs - mine).days <= STALE_DAYS_BY_STATE.get(st, STALE_DAYS)


def _last_modified(url):
    """The server's Last-Modified for a file, so two of the Lab's files can be ordered."""
    import email.utils
    try:
        req = urllib.request.Request(url, method="HEAD", headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            lm = r.headers.get("Last-Modified")
        return email.utils.parsedate_to_datetime(lm) if lm else None
    except Exception:
        return None


def pull_state_row(st, meta):
    """A payload from the Lab's NATIONAL row alone, for a state with no county file."""
    m = meta.get(st) or {}
    if not m:
        raise RuntimeError(f"{st}: no row in the Lab's national file")
    # national() keeps its own names for these, not the CSV's.
    mail, ip = m.get("nat_mail") or 0, m.get("nat_ip") or 0
    total = m.get("nat_voted") or (mail + ip)
    return {
        "state": st, "unit": "state", "election": "2026 General",
        "as_of": m.get("last_update") or None,
        "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "party_available": False, "outstanding_available": False,
        "in_person": ip > 0, "in_person_reported": ip > 0,
        "counties": {},
        "county_detail": False,
        "state_totals": {"registered": 0, "by_mail": mail, "in_person": ip,
                         "total": total, "requested": m.get("nat_requested") or 0},
        "source": f"{BASE}US.csv",
        "fallback": True,
        "attribution": {"aggregator": "UF Election Lab (election.lab.ufl.edu)",
                        "upstream": (m.get("data_source") or "unstated"),
                        "note": ("" if (m.get("notes") or "").strip().upper() in ("", "NA")
                                 else m["notes"].strip())},
        "notes": {"scope": ("The Election Lab publishes no county file for this state, so "
                            "this is its statewide row only. There is no per-county "
                            "breakdown, which means the county-by-county projection "
                            "cannot be run here - only the statewide totals."),
                  "party": "No party registration figures are published for this state."},
    }, {"total": total, "by_mail": mail, "in_person": ip, "outstanding": 0,
        "mail_outstanding": 0, "ret_D": 0, "ret_R": 0, "ret_NPA": 0,
        "requested": m.get("nat_requested") or 0}


def main(argv):
    only = [a.upper() for a in argv
            if a.upper() in STATES or a.upper() in FALLBACK or a.upper() in STATE_ONLY]
    meta = national()
    data = pathlib.Path(__file__).resolve().parent.parent / "data"
    ok = failed = skipped = held = 0
    for st in sorted(only or (list(STATES) + list(FALLBACK) + list(STATE_ONLY))):
        try:
            if st in STATE_ONLY:
                payload, tot = pull_state_row(st, meta)
                party = False
            else:
                payload, tot, party = pull(st, meta)
        except Exception as e:
            print(f"UF {st} FAILED (nothing written): {e}", file=sys.stderr)
            failed += 1
            continue
        if tot["total"] == 0:
            print(f"UF {st}: no early votes reported yet "
                  f"(upstream last updated {meta.get(st,{}).get('last_update','?')})",
                  file=sys.stderr)
            skipped += 1
            continue
        target = data / f"early-{st}.json"
        if st in FALLBACK:
            if direct_is_fresh(target, payload["as_of"], st):
                print(f"UF {st}: holding — the direct pull is current, and the Lab's copy "
                      f"has no mail/in-person split")
                held += 1
                continue
            payload["fallback"] = True
            lost = ("It does NOT separate mail from in-person" if not payload["in_person"]
                    else "It lacks the receipt-method detail the state file carries")
            payload["notes"]["fallback"] = (
                f"the direct state parse went stale or is unreachable, so this is the UF "
                f"Election Lab's copy. {lost}; the direct parse resumes automatically when "
                f"the state is reachable again")
            print(f"UF {st}: direct data is >{STALE_DAYS}d stale — using the Lab's copy "
                  f"({'no mail/in-person split' if not payload['in_person'] else 'no receipt-method detail'})",
                  file=sys.stderr)
        target.write_text(json.dumps(payload, indent=1))
        tag = "party" if party else "turnout only (no party registration)"
        print(f"UF {st} ok: {len(payload['counties'])} counties, as of "
              f"{payload['as_of']}  [{tag}]")
        print(f"   mail returned {tot['by_mail']:>9,}   in-person {tot['in_person']:>9,}"
              f"   mail outstanding {tot['outstanding']:>9,}")
        ok += 1
    print(f"UF: {ok} written, {held} held (direct is fresher), "
          f"{skipped} with no data yet, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
