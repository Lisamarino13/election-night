#!/usr/bin/env python3
"""A correct minimal xlsx reader: zipped XML, stdlib only.

The reader this replaces appended each cell in document order and ignored the cell's
own reference. xlsx omits empty cells, so a sparse row silently shifts every value
after the gap one column to the left. Maine's files are dense and it never showed
there; the EAC's survey is sparse, and reading it that way put Georgia's 2022 turnout
at 369 against a true 3,964,926.

A cell says where it belongs - r="AB12" - and that is used here rather than its
position in the stream.
"""
import io, re, zipfile


def _col(ref):
    """'AB12' -> 27 (zero-based column index)."""
    m = re.match(r"([A-Z]+)", ref or "")
    if not m:
        return None
    n = 0
    for ch in m.group(1):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def rows(data, sheet=0):
    xz = zipfile.ZipFile(io.BytesIO(data))
    shared = []
    if "xl/sharedStrings.xml" in xz.namelist():
        sst = xz.read("xl/sharedStrings.xml").decode("utf-8", "ignore")
        shared = [re.sub(r"<[^>]+>", "", s)
                  for s in re.findall(r"<si>(.*?)</si>", sst, re.S)]
    names = sorted(n for n in xz.namelist()
                   if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
    if not names:
        raise RuntimeError("xlsx: no worksheet")
    ws = xz.read(names[sheet]).decode("utf-8", "ignore")
    out = []
    for row in re.findall(r"<row[^>]*>(.*?)</row>", ws, re.S):
        cells = {}
        for c in re.finditer(r'<c([^>]*)>(?:<v>([^<]*)</v>|<is>(.*?)</is>)?</c>',
                             row, re.S):
            attrs, v, inline = c.group(1), c.group(2), c.group(3)
            ref = re.search(r'r="([A-Z]+\d+)"', attrs)
            idx = _col(ref.group(1)) if ref else None
            if inline is not None:
                val = re.sub(r"<[^>]+>", "", inline)
            elif v is None:
                val = ""
            elif 't="s"' in attrs:
                i = int(v)
                val = shared[i] if 0 <= i < len(shared) else ""
            else:
                val = v
            if idx is None:
                idx = max(cells) + 1 if cells else 0
            cells[idx] = val
        width = (max(cells) + 1) if cells else 0
        out.append([cells.get(i, "") for i in range(width)])
    if out:
        w = max(len(r) for r in out)
        out = [r + [""] * (w - len(r)) for r in out]
    return out
