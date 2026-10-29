#!/usr/bin/env python3
"""Keep index.html's ?v= stamps equal to the real content hash of each asset.

index.html loads charts.css and compare.js with a cache-busting query built from the
file's own sha1. GitHub Pages serves everything with cache-control: max-age=600 and an
ETag, so an asset whose URL has not changed can be revalidated and kept - which is
fine until the file changes and the stamp does not. Then a browser takes the fresh
index.html and keeps the stale script, and the board renders its cards with new code
and its charts with old. That is exactly what happened: compare.js changed and
?v=e4acb495 did not, so the charts kept disagreeing with the cards on a screen that
had the fix.

    python3 tools/stamp-assets.py            # rewrite the stamps
    python3 tools/stamp-assets.py --check    # exit 1 if any stamp is stale

Run --check before committing any board change.
"""
import hashlib, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "index.html"
ASSETS = ["charts.css", "compare.js"]


def digest(name):
    return hashlib.sha1((ROOT / name).read_bytes()).hexdigest()[:8]


def main(argv):
    check = "--check" in argv
    html = PAGE.read_text()
    stale, out = [], html
    for name in ASSETS:
        path = ROOT / name
        if not path.exists():
            print(f"{name}: missing", file=sys.stderr)
            return 1
        want = digest(name)
        pat = re.compile(re.escape(name) + r"\?v=([0-9a-f]{6,40})")
        found = pat.findall(out)
        if not found:
            print(f"{name}: index.html does not reference it with a ?v= stamp",
                  file=sys.stderr)
            return 1
        for got in set(found):
            if got != want:
                stale.append((name, got, want))
        out = pat.sub(f"{name}?v={want}", out)

    if not stale:
        print("stamps already current: " + ", ".join(f"{n}={digest(n)}" for n in ASSETS))
        return 0
    for name, got, want in stale:
        print(f"{'STALE' if check else 'fixed'}  {name}: {got} -> {want}")
    if check:
        print("\nindex.html would serve a cached copy of the changed file. "
              "Run tools/stamp-assets.py before committing.", file=sys.stderr)
        return 1
    PAGE.write_text(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
