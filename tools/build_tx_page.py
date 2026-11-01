#!/usr/bin/env python3
"""Render the Texas two-tier model as charts -> tx-model.html

Reads data/tx-twotier.json and data/model.json; writes a self-contained page.
Re-run it whenever the collectors run; it holds no numbers of its own.
"""
import json, os, math, html, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "tx-model.html")

D = json.load(open(os.path.join(ROOT, "data", "tx-twotier.json")))
M = json.load(open(os.path.join(ROOT, "data", "model.json")))
TX = M["states"]["TX"]
BE = TX["break_even"].get("eday_set") or TX["break_even"].get("eday_high")
ROWS = D["counties"]

SIZE_BANDS = [("metro 250k+", 250000, 10**9), ("mid 50-250k", 50000, 250000),
              ("small <50k", 0, 50000)]


def band_of(r):
    for i, (lbl, lo, hi) in enumerate(SIZE_BANDS):
        if lo <= r["votes_2024"] < hi:
            return i, lbl
    return 2, SIZE_BANDS[2][0]


def esc(s):
    return html.escape(str(s))


# ---------------------------------------------------------------- scatter
def scatter(xf, yf, xlab, ylab, title, note, xdom, ydom, logx=False, xfmt="{:.0f}%"):
    W, H = 760, 400
    L, R, T, B = 62, 18, 14, 46
    pw, ph = W - L - R, H - T - B
    x0, x1 = xdom
    y0, y1 = ydom
    tx = (lambda v: L + pw * (math.log10(v) - math.log10(x0)) / (math.log10(x1) - math.log10(x0))) \
        if logx else (lambda v: L + pw * (v - x0) / (x1 - x0))
    ty = lambda v: T + ph * (1 - (v - y0) / (y1 - y0))
    rmax = max(r["ev_2026"] for r in ROWS)
    out = []
    # grid
    yt = [t for t in range(int(y0), int(y1) + 1, 5) if y0 <= t <= y1]
    for t in yt:
        out.append(f'<line class="grid" x1="{L}" x2="{L+pw}" y1="{ty(t):.1f}" y2="{ty(t):.1f}"/>')
        out.append(f'<text class="tick" x="{L-8}" y="{ty(t)+4:.1f}" text-anchor="end">{t:+d}</text>')
    if logx:
        xt = [1000, 10000, 100000, 1000000]
    else:
        step = 20 if (x1 - x0) > 60 else 10
        xt = [t for t in range(int(x0), int(x1) + 1, step)]
    for t in xt:
        if not (x0 <= t <= x1):
            continue
        out.append(f'<line class="grid" x1="{tx(t):.1f}" x2="{tx(t):.1f}" y1="{T}" y2="{T+ph}"/>')
        lab = f"{t:,}" if logx else xfmt.format(t)
        out.append(f'<text class="tick" x="{tx(t):.1f}" y="{T+ph+18}" text-anchor="middle">{lab}</text>')
    if y0 < 0 < y1:
        out.append(f'<line class="zero" x1="{L}" x2="{L+pw}" y1="{ty(0):.1f}" y2="{ty(0):.1f}"/>')
    for r in sorted(ROWS, key=lambda r: -r["ev_2026"]):
        i, lbl = band_of(r)
        xv, yv = xf(r), yf(r)
        if xv is None or yv is None:
            continue
        rad = 3.2 + 13 * math.sqrt(r["ev_2026"] / rmax)
        out.append(
            f'<circle class="dot s{i+1}" cx="{tx(min(max(xv,x0),x1)):.1f}" '
            f'cy="{ty(min(max(yv,y0),y1)):.1f}" r="{rad:.1f}" '
            f'data-t="{esc(r["county"])} &#183; {esc(xlab)} {xv:.1f} &#183; {esc(ylab)} {yv:+.1f} '
            f'&#183; {r["ev_2026"]:,} banked &#183; pace {r["pace"]:.2f}"/>')
    out.append(f'<text class="axis" x="{L+pw/2:.0f}" y="{H-6}" text-anchor="middle">{esc(xlab)}</text>')
    out.append(f'<text class="axis" transform="translate(14,{T+ph/2:.0f}) rotate(-90)" '
               f'text-anchor="middle">{esc(ylab)}</text>')
    leg = " ".join(
        f'<span class="key"><i class="s{i+1}"></i>{esc(l)}</span>'
        for i, (l, _, _) in enumerate(SIZE_BANDS))
    return (f'<figure class="card"><h3>{esc(title)}</h3><p class="note">{note}</p>'
            f'<div class="legend">{leg}<span class="key muted">bubble = ballots banked</span></div>'
            f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(title)}">'
            + "".join(out) + "</svg></figure>")


# ---------------------------------------------------------------- diverging bars
def diverge(groups, title, note, unit="pts"):
    rowh, W = 26, 760
    L, R = 230, 70
    pw = W - L - R
    mx = max(abs(g[1]) for g in groups) * 1.15 or 1
    H = rowh * len(groups) + 34
    cx = L + pw / 2
    out = [f'<line class="zero" x1="{cx:.1f}" x2="{cx:.1f}" y1="8" y2="{rowh*len(groups)+8}"/>']
    for i, (lbl, v, sub) in enumerate(groups):
        y = 8 + i * rowh
        w = abs(v) / mx * (pw / 2)
        x = cx if v >= 0 else cx - w
        cls = "pos" if v >= 0 else "neg"
        out.append(f'<rect class="bar {cls}" x="{x:.1f}" y="{y+4}" width="{max(w,1.5):.1f}" '
                   f'height="{rowh-12}" rx="3" data-t="{esc(lbl)} &#183; {v:+.2f} {unit} &#183; {esc(sub)}"/>')
        out.append(f'<text class="rowlab" x="{L-12}" y="{y+rowh/2+1}" text-anchor="end">{esc(lbl)}</text>')
        tx_ = (x + w + 8) if v >= 0 else (x - 8)
        anc = "start" if v >= 0 else "end"
        out.append(f'<text class="val" x="{tx_:.1f}" y="{y+rowh/2+1}" text-anchor="{anc}">{v:+.2f}</text>')
    out.append(f'<text class="tick" x="{cx:.1f}" y="{H-6}" text-anchor="middle">0</text>')
    return (f'<figure class="card"><h3>{esc(title)}</h3><p class="note">{note}</p>'
            f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(title)}">'
            + "".join(out) + "</svg></figure>")


# ---------------------------------------------------------------- grouped bars
def grouped(series, cats, title, note):
    W, H = 760, 310
    L, R, T, B = 62, 18, 10, 56
    pw, ph = W - L - R, H - T - B
    n, m = len(cats), len(series)
    gw = pw / n
    bw = min(gw * 0.78 / m, 46)
    mx = max(max(s[1]) for s in series) * 1.12
    out = []
    for t in range(0, int(mx) + 1, 10):
        yy = T + ph * (1 - t / mx)
        out.append(f'<line class="grid" x1="{L}" x2="{L+pw}" y1="{yy:.1f}" y2="{yy:.1f}"/>')
        out.append(f'<text class="tick" x="{L-8}" y="{yy+4:.1f}" text-anchor="end">{t}%</text>')
    for ci, c in enumerate(cats):
        gx = L + gw * ci + (gw - bw * m - 2 * (m - 1)) / 2
        for si, (slab, vals) in enumerate(series):
            v = vals[ci]
            bh = ph * v / mx
            x = gx + si * (bw + 2)
            out.append(f'<rect class="bar s{si+1}" x="{x:.1f}" y="{T+ph-bh:.1f}" width="{bw:.1f}" '
                       f'height="{bh:.1f}" rx="3" data-t="{esc(slab)} &#183; {esc(c)} &#183; {v:.2f}%"/>')
            out.append(f'<text class="val sm" x="{x+bw/2:.1f}" y="{T+ph-bh-5:.1f}" '
                       f'text-anchor="middle">{v:.1f}</text>')
        out.append(f'<text class="rowlab" x="{L+gw*ci+gw/2:.1f}" y="{T+ph+20}" '
                   f'text-anchor="middle">{esc(c)}</text>')
    out.append(f'<line class="base" x1="{L}" x2="{L+pw}" y1="{T+ph}" y2="{T+ph}"/>')
    leg = " ".join(f'<span class="key"><i class="s{i+1}"></i>{esc(s[0])}</span>'
                   for i, s in enumerate(series))
    return (f'<figure class="card"><h3>{esc(title)}</h3><p class="note">{note}</p>'
            f'<div class="legend">{leg}</div>'
            f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(title)}">'
            + "".join(out) + "</svg></figure>")


# ---------------------------------------------------------------- build
C = D["composition"]
GR = ("white", "black", "hispanic")
GRL = ("white", "Black", "Hispanic")

charts = []

charts.append(scatter(
    lambda r: r["hispanic"], lambda r: r["swing_20_24"],
    "Hispanic share of adults", "2020 → 2024 margin swing (R-positive)",
    "The 2024 swing tracks race",
    "Each county's own 2020→2024 move. Upward = swung Republican. "
    "The Hispanic-heavy counties moved furthest, in every size band — which is why "
    "a 2024-only baseline bakes in the peak of a one-cycle shift.",
    (0, 100), (-15, 35)))

charts.append(scatter(
    lambda r: r["black"], lambda r: r["swing_20_24"],
    "Black share of adults", "2020 → 2024 margin swing (R-positive)",
    "The same swing against Black share",
    "Flatter than the Hispanic view and concentrated at the left — no Texas county is "
    "more than 32.7% Black, so this axis cannot separate counties the way the Hispanic axis can.",
    (0, 35), (-15, 35), xfmt="{:.0f}%"))

charts.append(scatter(
    lambda r: r["votes_2024"], lambda r: 100 * (r["pace"] - 1),
    "2024 votes cast (log scale)", "2026 early vote vs 2022, % change",
    "Pace tracks county size — but only partly",
    "I first told you pace was size and not race. A weighted regression with both terms in "
    "at once says otherwise: size t=+3.6, Hispanic share t=+3.1, both significant, and the two "
    "together explain only 15% of the variation. Size is the stronger single term (R² 0.118 "
    "vs 0.107), not the only one.",
    (700, 2000000), (-30, 90), logx=True))

sz = {c["size"]: c for c in D["by_size"]}
hb = {c["race"]: c for c in D["by_hispanic"]}
bb = {c["race"]: c for c in D["by_black"]}
groups = []
for lbl, _, _ in SIZE_BANDS:
    c = sz[lbl]
    groups.append((lbl, c["share_change"],
                   f"pace {c['pace']:.2f} · 2024 margin R{c['margin_2024']:+.1f}"))
for k in ("Hispanic 50%+", "Hispanic 25-50%", "Hispanic <25%"):
    c = hb[k]
    groups.append((k, c["share_change"],
                   f"pace {c['pace']:.2f} · 2024 margin R{c['margin_2024']:+.1f}"))
for k in ("Black 20%+", "Black 10-20%", "Black <10%"):
    c = bb[k]
    groups.append((k, c["share_change"],
                   f"pace {c['pace']:.2f} · 2024 margin R{c['margin_2024']:+.1f}"))
charts.append(diverge(groups, "Who gained share of the early vote, 2022 → 2026",
    "Change in each group's share of all Texas early ballots. This is composition, not turnout: "
    "the three bands inside each cut sum to zero by construction. Black-20%+ counties gained the "
    "most of any group, and small counties — the R+55.9 group — lost the most."))

ed = C["election_day"].get("low") or {}
charts.append(grouped(
    [("2022 banked", [C["banked_2022"][g] for g in GR]),
     ("2026 banked", [C["banked_2026"][g] for g in GR]),
     ("left for election day", [(ed.get("mix") or {}).get(g, 0) for g in GR])],
    list(GRL), "Tier 2: the racial make-up of the ballots in the box",
    "County pace × county adult population × county race mix. The ballots already banked are "
    "0.62 pts less white than 2022's, and what is left for election day is 4.2 pts whiter than what "
    "is banked. <strong>These are the places the ballots came from, not the voters</strong> — turnout "
    "differs by race inside a county, so read the 2022→2026 change, not the levels."))

tiles = [
    ("ballots banked", f"{TX['ev_joined']:,}", f"{D['statewide']['pace']:.2f}× the 2022 early vote"),
    ("election day", f"{BE['eday_ballots']:,}",
     f"turnout {BE['turnout']:,} — under the {TX['turnout']['turnout_2024']:,} 2024 ceiling"),
    ("share already banked", f"{BE['banked_share']:.1f}%", "of the projected two-party vote"),
    ("banked ballots lean", f"R{BE['banked_margin']:+.2f}",
     f"mix {TX['mix_effect']:+.2f} + within-county skew {TX['ev_skew_within_county']:+.2f}"),
    ("R needs on election day", f"R{BE['ed_margin_R_needs']:+.2f}", "to reach a statewide tie"),
    ("projected final", f"R{BE['projected_final']:+.2f}",
     "at 2024 county behaviour; R+6.45 if the 2024 swing fully reverts"),
]
tilehtml = "".join(
    f'<div class="tile"><div class="tl">{esc(a)}</div><div class="tv">{esc(b)}</div>'
    f'<div class="ts">{c}</div></div>' for a, b, c in tiles)

trows = "".join(
    f"<tr><td>{esc(r['county'])}</td><td>{r['ev_2026']:,}</td><td>{r['ev_2022']:,}</td>"
    f"<td>{r['pace']:.2f}</td><td>{r['votes_2024']:,}</td><td>{r['margin_2020']:+.1f}</td>"
    f"<td>{r['margin_2024']:+.1f}</td><td>{r['swing_20_24']:+.1f}</td>"
    f"<td>{r['white']:.1f}</td><td>{r['black']:.1f}</td><td>{r['hispanic']:.1f}</td></tr>"
    for r in sorted(ROWS, key=lambda r: -r["ev_2026"]))

PAGE = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Texas Two-Tier Model</title>
<style>
:root{{color-scheme:light;--surface-1:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;
--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--base:#c3c2b7;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--pos:#2a78d6;--neg:#e34948;
--ring:rgba(11,11,11,.10)}}
@media (prefers-color-scheme:dark){{:root:where(:not([data-theme=light])){{color-scheme:dark;
--surface-1:#1a1a19;--plane:#0d0d0d;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;
--grid:#2c2c2a;--base:#383835;--s1:#3987e5;--s2:#d95926;--s3:#199e70;
--pos:#3987e5;--neg:#e66767;--ring:rgba(255,255,255,.10)}}}}
:root[data-theme=dark]{{color-scheme:dark;--surface-1:#1a1a19;--plane:#0d0d0d;--ink:#f0efec;
--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--base:#383835;--s1:#3987e5;--s2:#d95926;
--s3:#199e70;--pos:#3987e5;--neg:#e66767;--ring:rgba(255,255,255,.10)}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--plane);color:var(--ink);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;padding:24px 16px 64px}}
.wrap{{max-width:860px;margin:0 auto}}
h1{{font-size:26px;margin:0 0 4px;letter-spacing:-.01em}}
.sub{{color:var(--ink2);margin:0 0 24px;font-size:14px}}
.card{{background:var(--surface-1);border:1px solid var(--ring);border-radius:12px;
padding:18px 18px 10px;margin:0 0 18px}}
h3{{font-size:17px;margin:0 0 6px}}
.note{{color:var(--ink2);font-size:13.5px;margin:0 0 12px}}
svg{{width:100%;height:auto;display:block;overflow:visible}}
.grid{{stroke:var(--grid);stroke-width:1}}
.zero{{stroke:var(--base);stroke-width:1.5;stroke-dasharray:3 3}}
.base{{stroke:var(--base);stroke-width:1.5}}
.tick{{fill:var(--muted);font-size:11.5px;font-variant-numeric:tabular-nums}}
.axis{{fill:var(--ink2);font-size:12.5px}}
.rowlab{{fill:var(--ink2);font-size:12.5px}}
.val{{fill:var(--ink);font-size:12px;font-variant-numeric:tabular-nums}}
.val.sm{{font-size:11px;fill:var(--ink2)}}
.dot{{fill-opacity:.62;stroke:var(--surface-1);stroke-width:2}}
.dot:hover{{fill-opacity:.95}}
.s1{{fill:var(--s1)}} .s2{{fill:var(--s2)}} .s3{{fill:var(--s3)}}
.bar.pos{{fill:var(--pos)}} .bar.neg{{fill:var(--neg)}}
.legend{{display:flex;flex-wrap:wrap;gap:14px;margin:0 0 10px;font-size:12.5px;color:var(--ink2)}}
.key{{display:inline-flex;align-items:center;gap:6px}}
.key i{{width:10px;height:10px;border-radius:3px;display:inline-block}}
.key i.s1{{background:var(--s1)}} .key i.s2{{background:var(--s2)}} .key i.s3{{background:var(--s3)}}
.key.muted{{color:var(--muted)}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:0 0 18px}}
.tile{{background:var(--surface-1);border:1px solid var(--ring);border-radius:12px;padding:14px}}
.tl{{font-size:11.5px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}}
.tv{{font-size:25px;margin:4px 0 2px;letter-spacing:-.02em}}
.ts{{font-size:12px;color:var(--ink2)}}
#tip{{position:fixed;pointer-events:none;opacity:0;transition:opacity .1s;
background:var(--ink);color:var(--surface-1);padding:7px 10px;border-radius:7px;
font-size:12.5px;max-width:300px;z-index:9}}
details{{margin:0 0 18px}}
summary{{cursor:pointer;color:var(--ink2);font-size:13.5px;padding:8px 0}}
table{{width:100%;border-collapse:collapse;font-size:12.5px;
font-variant-numeric:tabular-nums}}
th,td{{text-align:right;padding:5px 7px;border-bottom:1px solid var(--grid)}}
th:first-child,td:first-child{{text-align:left}}
th{{color:var(--muted);font-weight:600;position:sticky;top:0;background:var(--surface-1)}}
.scroll{{max-height:460px;overflow:auto;border:1px solid var(--ring);border-radius:10px}}
.caveat{{background:var(--surface-1);border:1px solid var(--ring);border-left:3px solid var(--s2);
border-radius:12px;padding:14px 18px;margin:0 0 18px;font-size:13.5px;color:var(--ink2)}}
@media (max-width:640px){{body{{padding:16px 16px 48px}} .tv{{font-size:22px}}}}
</style></head><body><div class="wrap">
<h1>Texas: the two-tier model</h1>
<p class="sub">Tier 1 is county pace. Tier 2 overlays each county's adult population and racial
make-up on it. Early vote as of {esc(D['as_of'])} &#183; {D['counties_joined']} of 254 counties
joined, none dropped &#183; margins are R-positive throughout.</p>
<div class="tiles">{tilehtml}</div>
<div class="caveat"><strong>What this is not.</strong> Nothing here is a forecast. The projected
final is arithmetic on a stated baseline &mdash; that every county votes as it did in 2024 &mdash;
and the honest uncertainty is not a confidence interval. Resampling the counties is the wrong tool
(we observe all 254; they are not a sample), and an ecological regression of margin on race returns
impossible values here &mdash; an implied Black margin of &minus;131 points &mdash; so it is not
used. The real spread is the baseline choice: R+13.29 at 2024 behaviour, R+6.45 if the 2020&#8594;2024
swing fully reverts. The election-day ballot count barely matters by comparison: 1.7M to 3.3M moves
the projection about one point, while moving the banked share from 82% to 70%.</div>
{''.join(charts)}
<details><summary>All 254 counties &mdash; the table behind every chart</summary>
<div class="scroll"><table><thead><tr><th>county</th><th>EV 2026</th><th>EV 2022</th>
<th>pace</th><th>votes 2024</th><th>2020</th><th>2024</th><th>swing</th>
<th>white %</th><th>Black %</th><th>Hisp %</th></tr></thead><tbody>{trows}</tbody></table></div>
</details>
<p class="sub">Sources: county early vote from the Texas Secretary of State (2022 and 2026);
county results 2020 and 2024 tied out to certified statewide totals &mdash; Texas 2020 matches
exactly; race from the Census Vintage 2024 county estimates, age 20+; election-day ballot counts
from the EAC's Election Administration and Voting Survey; the within-county early-vote skew
measured off North Carolina's precinct file, the only state we track that splits the mode.
Built {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')}Z.</p>
</div><div id="tip"></div><script>
var tip=document.getElementById('tip');
document.addEventListener('mouseover',function(e){{
 var t=e.target.getAttribute&&e.target.getAttribute('data-t');
 if(!t){{tip.style.opacity=0;return}}
 tip.innerHTML=t;tip.style.opacity=1;
 var x=e.clientX+14,y=e.clientY+14;
 if(x+tip.offsetWidth>innerWidth-8)x=e.clientX-tip.offsetWidth-14;
 if(y+tip.offsetHeight>innerHeight-8)y=e.clientY-tip.offsetHeight-14;
 tip.style.left=x+'px';tip.style.top=y+'px';}});
document.addEventListener('mouseout',function(){{tip.style.opacity=0}});
</script></body></html>
"""
open(OUT, "w").write(PAGE)
print(f"wrote {OUT}  ({len(PAGE):,} bytes)")
