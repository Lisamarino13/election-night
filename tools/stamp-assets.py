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
# texas.js was added with a hardcoded "?v=1" and left out of this list, so every
# browser that had once loaded it kept that copy forever - the exact failure this
# script exists to prevent, repeated on a new file. Anything index.html loads with a
# ?v= stamp belongs here.
ASSETS = ["charts.css", "compare.js", "texas.js"]


def digest(name):
    return hashlib.sha1((ROOT / name).read_bytes()).hexdigest()[:8]


def committed_stamps():
    """What the COMMITTED index.html asks for, which is what gets served."""
    import subprocess
    r = subprocess.run(["git", "-C", str(ROOT), "show", "HEAD:index.html"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return {name: set(re.findall(re.escape(name) + r"\?v=([0-9a-f]{6,40})", r.stdout))
            for name in ASSETS}


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
        # The working tree agreeing with itself is not enough. index.html is what the
        # browser asks for, and it is possible to commit a changed compare.js while
        # leaving index.html's stamp bump unstaged - which happened, and shipped a file
        # at a URL nobody requests. Check what is actually committed.
        bad = []
        com = committed_stamps()
        if com is not None:
            for name in ASSETS:
                want = digest(name)
                got = com.get(name) or set()
                if got and want not in got:
                    bad.append((name, ", ".join(sorted(got)), want))
        if bad:
            for name, got, want in bad:
                print(f"UNCOMMITTED STAMP  {name}: HEAD asks for {got}, the file is {want}",
                      file=sys.stderr)
            print("\nindex.html's stamp bump is not committed, so the browser will keep "
                  "the old file. Stage index.html with it.", file=sys.stderr)
            return 1
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
