#!/usr/bin/env python3
"""Florida final early/mail figures for prior cycles -> data/ev-history-FL.json

Source: the Division's archived "status counts" PDFs, same three rows as the live
2026 file, so 2026 can be paced against a like-for-like denominator:
    Vote-by-Mail Provided (Not Yet Returned)
    Voted Vote-by-Mail
    Voted Early                      <- in-person, absent from the live file until EV opens

One-shot: these numbers are final and never change. Run once, commit the output.
"""
import json, re, sys, pathlib, urllib.request
import pdfplumber

SRC = {
    # 2020 lives on the Division's blob host, not dos.fl.gov — the archive index links it
    # absolutely while later years are site-relative.
    "2020": ("https://fldoswebumbracoprod.blob.core.windows.net/media/703948/gen-2020.pdf",
             "2020 General"),
    "2022": ("https://dos.fl.gov/media/706191/2022-ge-rptstatuscountsarchive-ev-vbm.pdf", "2022 General"),
    "2024": ("https://dos.fl.gov/media/708648/2024gen_vbm-ev_statuscounts.pdf",            "2024 General"),
}
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
ROWS = {"Vote-by-Mail Provided (Not Yet Returned)": "outstanding",
        "Voted Vote-by-Mail": "mail_returned",
        "Voted Early": "early_in_person"}
# the four party columns, in the order the PDFs print them
NUMS = re.compile(r"([\d,]{1,12})")


# The 2020 archive prints Unicode hyphens (U+2010/U+2011) where 2022 and 2024 use ASCII,
# so "Vote-by-Mail" never matched and the whole file parsed to nothing. Normalise every
# dash variant before matching rather than carrying two sets of labels.
DASHES = {0x2010: "-", 0x2011: "-", 0x2012: "-", 0x2013: "-", 0x2014: "-", 0x2212: "-",
          0x00a0: " "}


def parse(path):
    out, county = {}, None
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").splitlines():
                line = line.translate(DASHES).strip()
                m = re.match(r"^(.+?)\s+(?:As Of\s+)?Republican\s+Democrat\s+Other\s+Affiliation\s+TOTAL$", line)
                if m:
                    county = m.group(1).strip()
                    out.setdefault(county, {})
                    continue
                for label, key in ROWS.items():
                    if county and line.startswith(label):
                        tail = line[len(label):]
                        tail = re.sub(r"^\s*\d{1,2}/\d{1,2}/\d{2,4}", "", tail)   # drop "As Of" date
                        got = [int(x.replace(",", "")) for x in NUMS.findall(tail)]
                        if len(got) >= 5:
                            r, d, o, npa, tot = got[:5]
                            out[county][key] = {"R": r, "D": d, "O": o, "NPA": npa, "total": tot}
                        break
    if "STATE TOTAL" not in out:
        raise RuntimeError(f"{path}: no STATE TOTAL block — layout changed")
    return out


def main():
    years = {}
    for yr, (url, name) in SRC.items():
        p = pathlib.Path(f"/tmp/fl_{yr}.pdf")
        if not p.exists():
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                p.write_bytes(r.read())
        data = parse(p)
        st = data.pop("STATE TOTAL")
        if len(data) < 60:
            raise RuntimeError(f"{yr}: only {len(data)} counties parsed — refusing")
        ev_total = sum(st.get(k, {}).get("total", 0) for k in ("mail_returned", "early_in_person"))
        years[yr] = {"name": name, "state_totals": st, "counties": data,
                     "ev_combined_total": ev_total, "source": url}
        print(f"  {yr}: {len(data)} counties  mail {st['mail_returned']['total']:,}  "
              f"early {st['early_in_person']['total']:,}  combined {ev_total:,}")
    out = pathlib.Path(__file__).resolve().parent.parent / "data" / "ev-history-FL.json"
    out.write_text(json.dumps({"state": "FL", "years": years}, indent=1))
    print(f"  -> {out.name}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FAILED (nothing written): {e}", file=sys.stderr)
        sys.exit(1)
