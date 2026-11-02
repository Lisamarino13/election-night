(function(){
"use strict";
/* Early-vote comparison for Georgia, South Carolina and North Carolina.
   Reads the same data/ files the board does, so the cron's hourly pull moves these
   charts too rather than freezing whatever the numbers were the day it was written.

   Colour encodes the CYCLE, not the party and not the year's rank: presidential
   years (2020, 2024) share one hue, midterms (2022) another, and 2026 — the one
   still in progress — a third, drawn open so a running total is never mistaken for
   a final. Party red/blue is deliberately absent; none of these three states
   registers by party, so a D/R split here would be a vendor's model, not a count. */

const PAL = {pres:"var(--y2024)", mid:"var(--y2022)", now:"var(--y2026)"};
const cycleOf = y => +y === 2026 ? "now" : (+y % 4 === 0 ? "pres" : "mid");
const n  = v => v == null ? "—" : v.toLocaleString("en-US");
const ab = v => v >= 1e6 ? (v/1e6).toFixed(v>=1e7?0:1)+"M" : v >= 1e3 ? Math.round(v/1e3)+"K" : String(v);
const esc = s => String(s).replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));

// Axis ceilings land on 1 / 2 / 2.5 / 5 x 10^n so the gridlines read as round
// numbers. Dividing a ceiling into quarters gave ticks like 2.3M and 3.4M.
function scale(max){
  const raw = max/4, mag = Math.pow(10, Math.floor(Math.log10(raw))), nrm = raw/mag;
  const step = (nrm<=1?1:nrm<=2?2:nrm<=2.5?2.5:nrm<=5?5:10)*mag;
  return {step, top: Math.ceil(max/step)*step};
}

const SRC = [];
const J = async p => { const r = await fetch(p + "?t=" + Date.now()); if(!r.ok) throw new Error(p+" "+r.status); return r.json(); };

// ---- tooltip ---------------------------------------------------------------
let tip = document.getElementById("tip");
if (!tip){ tip = document.createElement("div"); tip.className = "tip";
  tip.setAttribute("role","status"); document.body.appendChild(tip); }
function showTip(e, html){
  tip.innerHTML = html; tip.style.opacity = 1;
  const r = tip.getBoundingClientRect();
  let x = e.clientX + 14, y = e.clientY - r.height - 12;
  if (x + r.width > innerWidth - 8) x = e.clientX - r.width - 14;
  if (y < 8) y = e.clientY + 18;
  tip.style.left = x + "px"; tip.style.top = y + "px";
}
const hideTip = () => { tip.style.opacity = 0; };
addEventListener("scroll", hideTip, {passive:true});

const svgEl = (t, a) => { const e = document.createElementNS("http://www.w3.org/2000/svg", t);
  for (const k in a) e.setAttribute(k, a[k]); return e; };

// ---- bars: total early vote by cycle ---------------------------------------
// A rounded data-end anchored to the baseline: only the top corners are rounded,
// so the bar still reads as sitting on zero.
function barPath(x, y, w, h, r){
  r = Math.min(r, w/2, h);
  return `M${x},${y+h} L${x},${y+r} Q${x},${y} ${x+r},${y} L${x+w-r},${y} Q${x+w},${y} ${x+w},${y+r} L${x+w},${y+h} Z`;
}

function drawBars(host, rows, opts){
  const W = Math.max(280, host.clientWidth), PAD = {t:22, r:10, b:52, l:46};
  const H = Math.min(360, Math.max(240, Math.round(W * 0.62)));
  const plotW = W - PAD.l - PAD.r, plotH = H - PAD.t - PAD.b;
  // A bar that carries election day is as tall as the TOTAL vote, so the scale has to
  // see that or the stacked part runs off the top.
  const max = Math.max(...rows.filter(r=>r.total!=null)
    .map(r => r.totalVote != null ? r.totalVote : r.total), 1);
  const {step, top} = scale(max);
  const yOf = v => PAD.t + plotH - (v/top) * plotH;

  const svg = svgEl("svg", {viewBox:`0 0 ${W} ${H}`, width:W, height:H, role:"img",
    "aria-label":opts.aria});
  // gridlines + y labels
  const ticks = Math.round(top/step);
  for (let i=0;i<=ticks;i++){
    const v = step*i, y = yOf(v);
    svg.appendChild(svgEl("line", {class:"gridline", x1:PAD.l, x2:W-PAD.r, y1:y, y2:y}));
    const t = svgEl("text", {class:"axlab", x:PAD.l-8, y:y+4, "text-anchor":"end"});
    t.textContent = i ? ab(v) : "0"; svg.appendChild(t);
  }
  const GAP = 2; // surface gap between adjacent fills
  const slot = plotW / rows.length;
  const bw = Math.min(84, slot - 14 - GAP);
  rows.forEach((r, i) => {
    const x = PAD.l + slot*i + (slot - bw)/2;
    const lab = svgEl("text", {class:"axlab", x:x+bw/2, y:H-PAD.b+20, "text-anchor":"middle",
      style:"font-family:var(--display);font-size:15px;font-weight:600;fill:var(--fg)"});
    lab.textContent = r.year; svg.appendChild(lab);
    // On a phone four slots are ~70px and these run together into
    // "PRESIDENTIALMIDTERMPRESIDENTIAL". The legend already carries the cycle,
    // so below that width the per-bar sublabel is dropped rather than overlapped.
    if (slot >= 76){
      const sub = svgEl("text", {class:"axlab", x:x+bw/2, y:H-PAD.b+37, "text-anchor":"middle",
        style:"font-size:11.5px;letter-spacing:.05em;text-transform:uppercase"});
      sub.textContent = r.note || (cycleOf(r.year)==="pres" ? "presidential" : cycleOf(r.year)==="now" ? "still voting" : "midterm");
      svg.appendChild(sub);
    }

    const y = yOf(r.total), h = plotH - (y - PAD.t);
    const cyc = cycleOf(r.year), fill = PAL[cyc];
    // Election day sits ON TOP of the early vote, so the bar is the whole turnout and
    // the solid part is the share that had already voted. Drawn first so the early
    // block's rounded cap stays on top of it.
    const hasEday = r.eday != null && r.totalVote != null;
    if (hasEday){
      const yTop = yOf(r.totalVote);
      svg.appendChild(svgEl("path", {
        d: barPath(x, yTop, bw, y - yTop, 4), fill: fill, "fill-opacity": 0.26,
        stroke: fill, "stroke-width": 1, "stroke-opacity": 0.5}));
    }
    const p = svgEl("path", {d:barPath(x, y, bw, h, 4), fill: cyc==="now" ? "none" : fill,
      stroke: fill, "stroke-width": cyc==="now" ? 2 : 0,
      "stroke-dasharray": cyc==="now" ? "5 3" : "none"});
    p.style.cursor = "default";
    svg.appendChild(p);
    const vl = svgEl("text", {class:"dlab fig",
      x:x+bw/2, y:(hasEday?yOf(r.totalVote):y)-9, "text-anchor":"middle", fill:"var(--fg)"});
    vl.textContent = ab(hasEday ? r.totalVote : r.total); svg.appendChild(vl);
    // A figure per box, not just the total on top: the stack is two quantities and the
    // reader should not have to subtract. Each label sits in its own segment, and is
    // dropped when that segment is too short to hold it rather than overflowing into
    // the one next to it.
    if (hasEday){
      const seg = [
        {v: r.eday,  y0: yOf(r.totalVote), y1: y,          dark: false},
        {v: r.total, y0: y,                y1: yOf(0),     dark: true},
      ];
      for (const g of seg){
        const h2 = g.y1 - g.y0;
        if (h2 < 16) continue;
        const t = svgEl("text", {class:"fig", x:x+bw/2, y:g.y0 + h2/2 + 4,
          "text-anchor":"middle",
          style:`font-size:11.5px;font-weight:600;fill:${g.dark?"#fff":"var(--fg)"}`});
        t.textContent = ab(g.v);
        svg.appendChild(t);
      }
    }
    // hit target larger than the mark
    const hit = svgEl("rect", {x:x-7, y:PAD.t, width:bw+14, height:plotH, fill:"transparent"});
    hit.addEventListener("pointerenter", e => showTip(e,
      `<div class="k"><i style="background:${fill}"></i><b>${r.year}</b></div>
       <div class="fig">${n(r.total)} early + mail</div>
       ${r.mail!=null?`<div class="dim fig" style="color:var(--dim)">mail ${n(r.mail)} &middot; in person ${n(r.ip)}</div>`:""}
       ${r.eday!=null?`<div class="fig">${n(r.eday)} election day</div>
         <div class="fig"><b>${n(r.totalVote)} total vote</b> &middot;
           early ${Math.round(100*r.total/r.totalVote)}% <span class="dim">${esc(r.basis||"")}</span></div>`:""}
       <div style="color:var(--dim)">${esc(r.tip||"")}</div>`));
    hit.addEventListener("pointermove", e => showTip(e, tip.innerHTML));
    hit.addEventListener("pointerleave", hideTip);
    svg.appendChild(hit);
  });
  svg.appendChild(svgEl("line", {class:"axis", x1:PAD.l, x2:W-PAD.r, y1:yOf(0), y2:yOf(0)}));
  host.replaceChildren(svg);
}

// ---- lines: cumulative by early-voting day ---------------------------------
function drawLines(host, series, opts){
  const W = Math.max(280, host.clientWidth), PAD = {t:22, r:40, b:46, l:48};
  const H = Math.min(380, Math.max(250, Math.round(W * 0.66)));
  const plotW = W - PAD.l - PAD.r, plotH = H - PAD.t - PAD.b;
  const nDays = Math.max(...series.map(s => s.vals.length));
  const max = Math.max(...series.flatMap(s => s.vals), 1);
  const {step, top} = scale(max);
  const xOf = i => PAD.l + (nDays===1?0:(i/(nDays-1))*plotW);
  const yOf = v => PAD.t + plotH - (v/top)*plotH;

  const svg = svgEl("svg", {viewBox:`0 0 ${W} ${H}`, width:W, height:H, role:"img",
    "aria-label":opts.aria});
  for (let i=0, nt=Math.round(top/step); i<=nt; i++){
    const v = step*i, y = yOf(v);
    svg.appendChild(svgEl("line", {class:"gridline", x1:PAD.l, x2:W-PAD.r, y1:y, y2:y}));
    const t = svgEl("text", {class:"axlab", x:PAD.l-8, y:y+4, "text-anchor":"end"});
    t.textContent = i ? ab(v) : "0"; svg.appendChild(t);
  }
  const everyOther = nDays > 8;
  for (let i=0;i<nDays;i++){
    if (everyOther && i%2 && i!==nDays-1) continue;
    const t = svgEl("text", {class:"axlab", x:xOf(i), y:H-PAD.b+20, "text-anchor":"middle"});
    t.textContent = i+1; svg.appendChild(t);
  }
  const xt = svgEl("text", {class:"axlab", x:PAD.l+plotW/2, y:H-PAD.b+39, "text-anchor":"middle",
    style:"font-size:11.5px;letter-spacing:.05em;text-transform:uppercase"});
  xt.textContent = "day of early voting"; svg.appendChild(xt);

  series.forEach(s => {
    const col = PAL[cycleOf(s.year)];
    const d = s.vals.map((v,i)=>`${i?"L":"M"}${xOf(i)},${yOf(v)}`).join(" ");
    svg.appendChild(svgEl("path", {d, fill:"none", stroke:col, "stroke-width":2,
      "stroke-linejoin":"round", "stroke-linecap":"round",
      "stroke-dasharray": cycleOf(s.year)==="now" ? "none" : "none"}));
    s.vals.forEach((v,i)=>{
      // a 2px surface ring keeps overlapping markers legible
      svg.appendChild(svgEl("circle", {cx:xOf(i), cy:yOf(v), r:4.5, fill:col,
        stroke:"var(--panel)", "stroke-width":2}));
    });
    const li = s.vals.length-1, lx = xOf(li), ly = yOf(s.vals[li]);
    const room = (W - PAD.r + 34) - lx;          // does "2026" fit to the right?
    const lab = svgEl("text", {class:"dlab", fill:col,
      x: room >= 36 ? lx+9 : lx-9, y: ly+5,
      "text-anchor": room >= 36 ? "start" : "end"});
    lab.textContent = s.year; svg.appendChild(lab);
  });
  // one crosshair hit column per day
  for (let i=0;i<nDays;i++){
    const hit = svgEl("rect", {x:xOf(i)-plotW/(nDays*2)-2, y:PAD.t,
      width:plotW/nDays+4, height:plotH, fill:"transparent"});
    const html = `<b>Day ${i+1}</b>` + series.map(s=>{
      const v = s.vals[i];
      return `<div class="k"><i style="background:${PAL[cycleOf(s.year)]}"></i>
        <span>${s.year}</span> <span class="fig">${v==null?"—":n(v)}</span></div>`;
    }).join("");
    const show = e => { svg.querySelectorAll(".cross").forEach(x=>x.remove());
      svg.appendChild(svgEl("line", {class:"cross", x1:xOf(i), x2:xOf(i), y1:PAD.t,
        y2:PAD.t+plotH, stroke:"var(--dim)", "stroke-width":1, "stroke-dasharray":"3 3",
        "pointer-events":"none"}));
      showTip(e, html); };
    hit.addEventListener("pointerenter", show);
    hit.addEventListener("pointermove", show);
    hit.addEventListener("pointerleave", ()=>{ svg.querySelectorAll(".cross").forEach(x=>x.remove()); hideTip(); });
    svg.appendChild(hit);
  }
  svg.appendChild(svgEl("line", {class:"axis", x1:PAD.l, x2:W-PAD.r, y1:yOf(0), y2:yOf(0)}));
  host.replaceChildren(svg);
}


// ---- shares: a composition compared across two cycles -----------------------
// Horizontal bars, because the category labels are words rather than years and
// a phone has far more room across than a rotated axis label gives.
function drawShares(host, groups, series, opts){
  const W = Math.max(280, host.clientWidth);
  const labW = Math.min(150, Math.max(96, Math.round(W*0.30)));
  const PAD = {t:6, r:46, b:26, l:labW};
  const rowH = series.length * 15 + 16;
  const H = PAD.t + PAD.b + groups.length * rowH;
  const plotW = W - PAD.l - PAD.r;
  const max = Math.max(...groups.flatMap(g => series.map(s => g.vals[s.key] || 0)), 0.01);
  const {step, top} = scale(max*100);
  const xOf = p => PAD.l + (p*100/top) * plotW;

  const svg = svgEl("svg", {viewBox:`0 0 ${W} ${H}`, width:W, height:H, role:"img",
    "aria-label":opts.aria});
  for (let i=0, nt=Math.round(top/step); i<=nt; i++){
    const x = PAD.l + (i/nt)*plotW;
    svg.appendChild(svgEl("line", {class:"gridline", x1:x, x2:x, y1:PAD.t, y2:H-PAD.b}));
    const t = svgEl("text", {class:"axlab", x, y:H-PAD.b+15, "text-anchor":"middle"});
    t.textContent = Math.round(step*i) + "%"; svg.appendChild(t);
  }
  groups.forEach((g, gi) => {
    const y0 = PAD.t + gi*rowH + 7;
    // The label column is capped, and a long one ("Other / multiple / unknown") ran
    // off the left edge where the figure clips it. Trimmed to what actually fits,
    // with the full wording still in the tooltip and the table.
    const lab = svgEl("text", {class:"axlab", x:PAD.l-9, y:y0 + (series.length*15)/2 + 1,
      "text-anchor":"end", style:"fill:var(--fg);font-size:13px"});
    const room = Math.max(4, Math.floor((PAD.l - 14) / 6.4));
    lab.textContent = g.label.length > room ? g.label.slice(0, room - 1).trimEnd() + "\u2026"
                                            : g.label;
    if (lab.textContent !== g.label){
      const t = svgEl("title"); t.textContent = g.label; lab.appendChild(t);
    }
    svg.appendChild(lab);
    series.forEach((s, si) => {
      const p = g.vals[s.key];
      if (p == null) return;
      const y = y0 + si*15, h = 11, col = PAL[s.cycle];
      svg.appendChild(svgEl("path", {d:barPath(PAD.l, y, Math.max(1, xOf(p)-PAD.l), h, 3),
        fill: col}));
      const v = svgEl("text", {class:"fig", x:xOf(p)+7, y:y+h-1,
        style:"font-size:12.5px;fill:var(--fg)"});
      v.textContent = (p*100).toFixed(1) + "%"; svg.appendChild(v);
      const hit = svgEl("rect", {x:PAD.l, y:y-2, width:plotW, height:h+4, fill:"transparent"});
      const html = `<b>${esc(g.label)}</b>` + series.map(s2 => {
        const q = g.vals[s2.key];
        return q==null ? "" : `<div class="k"><i style="background:${PAL[s2.cycle]}"></i>
          <span>${esc(s2.label)}</span> <span class="fig">${(q*100).toFixed(1)}% &middot;
          ${n(g.counts[s2.key])}</span></div>`;
      }).join("");
      hit.addEventListener("pointerenter", e => showTip(e, html));
      hit.addEventListener("pointermove", e => showTip(e, html));
      hit.addEventListener("pointerleave", hideTip);
      svg.appendChild(hit);
    });
  });
  host.replaceChildren(svg);
}

// ---- panels ----------------------------------------------------------------
function panel({title, races, lede, legend, caption, table, draw}){
  const sec = document.createElement("section");
  sec.className = "panel";
  sec.innerHTML = `
    <div class="phd"><h2>${esc(title)}</h2><div class="races">${races}</div></div>
    <p class="lede">${lede}</p>
    <div class="legend">${legend}</div>
    <figure><div class="plot"></div><figcaption>${caption}</figcaption></figure>
    <button class="tblbtn" aria-expanded="false">Show the numbers</button>
    <div class="scroll" hidden>${table}</div>`;
  const host = sec.querySelector(".plot");
  const btn = sec.querySelector(".tblbtn"), box = sec.querySelector(".scroll");
  btn.onclick = () => { const open = box.hidden; box.hidden = !open;
    btn.setAttribute("aria-expanded", String(open));
    btn.textContent = open ? "Hide the numbers" : "Show the numbers"; };
  sec._draw = () => draw(host);
  return sec;
}
const key = (c, label) => `<span><i style="background:${c==="now"?"none":PAL[c]};${
  c==="now"?`border:2px dashed ${PAL.now}`:""}"></i>${esc(label)}</span>`;
const LEGEND = key("mid","2022 midterm") + key("pres","presidential (2020 / 2024)") + key("now","2026 — still voting");


// ---- one state's chart, for embedding straight into that state's card --------
// The board opens on the vote tables, so a chart that lives only behind a tab is a
// chart nobody sees. This draws the same figure with no panel chrome so each card
// can carry its own.
// Early vote as a share of the TOTAL vote, for the cycles where both numbers exist.
// The early-vote files have no turnout denominator, so this comes from prior
// election-night feeds and is only populated for the states whose results collector
// takes a year.
let _share = null;
async function evShare(){
  if (_share) return _share;
  try { _share = await J("data/ev-share.json"); }
  catch(e){ _share = {states:{}}; }
  return _share;
}
// A COUNTED early vote is measured by the feed; a CAST one is ballots received, which is
// a different quantity. Texas 2024 was 80.4% counted against 68.2% cast - twelve points
// apart - so they are never shown as the same number.
function shareFor(share, code, year){
  // by_year is the assembled answer: every cycle where BOTH a turnout denominator and
  // an early-vote total exist, whether the denominator came from a prior election-night
  // feed or from the Lab's turnout column. Reading measured_total_vote instead meant
  // only the two states with a year-parameterised results collector ever stacked, and
  // only for 2024.
  const row = (((share.states||{})[code]||{}).by_year||{})[String(year)];
  if (!row || !row.total_vote || row.early == null) return null;
  return {total: row.total_vote, ev: row.early, pct: row.early_pct,
          kind: row.basis || "cast"};
}

// Both chart renderers need the same election-day stacking, and patching only one of
// them is how the Charts tab ended up showing it while the cards on the early-vote tab
// - the ones actually on screen - did not. One function, called by both.
async function addElectionDay(rows, code){
  const share = await evShare();
  // The bars are built from the early-vote archive, which for Georgia, Kansas,
  // Michigan, Nebraska and Ohio holds 2024 and nothing else. The EAC's survey covers
  // every state back to 2018, so any cycle it has and the archive does not is added
  // here rather than leaving the card with one historical bar.
  const by = ((share.states||{})[code]||{}).by_year || {};
  const have = new Set(rows.map(r => String(r.year)));
  for (const [yr, v] of Object.entries(by)){
    if (have.has(yr) || !v.total_vote || v.early == null) continue;
    rows.push({year:+yr, total:v.early, mail:v.mail ?? null, ip:v.early_in_person ?? null,
               tip:"completed cycle — mode split from the EAC survey"});
  }
  rows.sort((a,b) => a.year - b.year);
  let any = false;
  for (const r of rows){
    if (r.year === 2020){
      r.note = "covid cycle";
      r.tip = (r.tip ? r.tip + " — " : "") +
        "pandemic rules: expanded mail and early voting";
    }
    const sh = shareFor(share, code, r.year);
    if (!sh || sh.total <= r.total) continue;
    r.totalVote = sh.total;
    r.eday = sh.total - r.total;
    r.basis = sh.kind;
    any = true;
  }
  const legend = any
    ? LEGEND + `<span><i style="background:${PAL.mid};opacity:.26;
        border:1px solid ${PAL.mid}"></i>election day (stacked on top)</span>`
    : LEGEND;
  return {any, legend};
}

const _cache = {};
// Prefer the payloads the page already captured at load. Re-fetching here meant the
// charts could read a newer collector run than the cards above them, so one board
// showed two vintages at once.
let _gen = null;
async function stateData(code){
  // The page restamps __BOARD_RAW.gen on every early-vote refresh. Holding a cache
  // across that is what let the charts sit hours behind the cards.
  const g = (window.__BOARD_RAW || {}).gen;
  if (g !== _gen){ for (const k in _cache) delete _cache[k]; _gen = g; }
  if (_cache[code]) return _cache[code];
  const shared = window.__BOARD_RAW || {};
  let cur = (shared.early || {})[code] || null;
  let hist = (shared.hist || {})[code] || null;
  if (!cur){ try{ cur = await J("data/early-"+code+".json"); }catch(e){} }
  if (!hist){ try{ hist = (await J("data/ev-history-"+code+".json")).years || {}; }catch(e){ hist = {}; } }
  return (_cache[code] = {cur, hist: hist || {}});
}
async function renderStateChart(host, code){
  if (!host) return;
  const {cur, hist} = await stateData(code);
  if (!cur && !Object.keys(hist).length) return;

  if (code === "SC" && cur && cur.daily){
    const ser = [];
    for (const y of Object.keys(hist).sort()){
      const d = hist[y]; if (!d || !d.days) continue;
      ser.push({year:+y, vals:d.days.map(k => d.running[k])});
    }
    let run = 0;
    const v26 = Object.keys(cur.daily).sort((a,b)=>new Date(a)-new Date(b)).map(k => run += cur.daily[k]);
    if (v26.length) ser.push({year:2026, vals:v26});
    ser.sort((a,b)=>a.year-b.year);
    if (!ser.length) return;
    host.innerHTML = `<div class="legend">${LEGEND}</div><div class="plot"></div>`;
    const draw = () => drawLines(host.querySelector(".plot"), ser,
      {aria:"South Carolina cumulative early vote by day of early voting."});
    draw(); host._draw = draw;
    return;
  }

  const rows = [];
  for (const y of Object.keys(hist).sort()){
    const st = streams((hist[y]||{}).state_totals);
    if (st) rows.push({year:+y, ...st, tip:"completed cycle"});
  }
  const now = cur ? streams(cur.state_totals) : null;
  if (now){
    if (cur.in_person_reported === false) now.ip = null;
    rows.push({year:2026, ...now, tip:"as of " + (cur.as_of||"") + " — still voting"});
  }
  if (rows.length < 2) return;            // one bar is a number, not a chart
  const {legend: cardLegend} = await addElectionDay(rows, code);
  host.innerHTML = `<div class="legend">${cardLegend}</div><div class="plot"></div>`;
  const draw = () => drawBars(host.querySelector(".plot"), rows,
    {aria:`${code} early and mail ballots by cycle.`});
  draw(); host._draw = draw;
}
window.renderStateChart = renderStateChart;

// ---- one state's race composition, same deal --------------------------------
async function renderRaceChart(host, code){
  if (!host) return;
  let d = null;
  try{ d = await J("data/demographics-"+code+".json"); }catch(e){ return; }
  const yrs = Object.keys(d.years||{}).sort();
  if (!yrs.length) return;
  const latest = yrs[yrs.length-1];
  const vt = (y,st) => ((((d.years[y]||{}).streams||{})[st]||{}).race) || null;
  const nowR = vt(latest,"voted");
  if (!nowR) return;
  const series = yrs.filter(y=>vt(y,"voted")).map(y=>({
    key:y, label:y + (+y%4===0 ? " final" : (+y===2026 ? " so far" : "")), cycle:cycleOf(y)}));
  const groups = Object.keys(nowR.counts).map(k => ({
    label:nowR.labels[k], k,
    vals:Object.fromEntries(series.map(sr=>{const r=vt(sr.key,"voted");
      return [sr.key, r ? r.counts[k]/r.total : null];})),
    counts:Object.fromEntries(series.map(sr=>{const r=vt(sr.key,"voted");
      return [sr.key, r ? r.counts[k] : null];})),
  })).sort((a,b)=>(b.vals[latest]||0)-(a.vals[latest]||0));
  // Two different things can be wrong with a race card, and the old guard only caught
  // one of them. It warned when a state had published NO figure for this cycle - which
  // meant that the moment South Carolina published a thin one, the warning disappeared
  // and the card silently drew SC's composition from 28,614 mail ballots against a
  // 530,558 early vote, with nothing on screen to say so. Presence of a 2026 series is
  // not the question. COVERAGE is: what share of the state's early vote does this
  // breakdown actually describe, and which modes are missing from it.
  let gap = "";
  if (!series.some(sr => +sr.key === 2026)){
    gap = `<div class="streamline">No 2026 race breakdown published for this state yet &mdash;
       showing ${latest} alone. ${code === "SC"
         ? "South Carolina's race figures cover mail ballots only; its in-person early report carries no breakdown."
         : "The source has not posted one for this cycle."}</div>`;
  } else {
    let evTotal = null;
    try{ evTotal = (await stateData(code)).cur.state_totals.total; }catch(e){}
    const covered = (nowR && nowR.total) || 0;
    if (evTotal && covered && covered < 0.95 * evTotal){
      const pct = covered / evTotal;
      // Name the modes that carry ballots but no breakdown, so the shortfall is
      // attributable rather than just a number.
      const streams = (d.years[latest]||{}).streams || {};
      const blind = ["inperson","accept"].filter(k => {
        const r = (streams[k]||{}).race;
        return !r || !r.total;
      }).map(k => k === "inperson" ? "in-person early" : "mail");
      gap = `<div class="streamline">This breakdown covers
        ${n(covered)} of ${n(evTotal)} early ballots
        (${pct < 0.1 ? (100*pct).toFixed(1) : Math.round(100*pct)}%)${
          blind.length ? " &mdash; " + blind.join(" and ") + " ballots carry no race breakdown" : ""
        }, so the shares describe that subset, not everyone who has voted.</div>`;
    }
  }
  host.innerHTML = `<div class="legend">${series.map(sr=>key(sr.cycle,sr.label)).join("")}</div>
    <div class="plot"></div>${gap}`;
  const draw = () => drawShares(host.querySelector(".plot"), groups, series,
    {aria:`${code} early vote composition by race.`});
  draw(); host._draw = draw;
}
window.renderRaceChart = renderRaceChart;

// ---- which contests each state carries, taken from the board's own race list ----
const STATES = {
  AK:{name:"Alaska"},
  GA:{name:"Georgia",        races:"Governor · Senate"},
  SC:{name:"South Carolina", races:"Senate"},
  NC:{name:"North Carolina", races:"Senate"},
  FL:{name:"Florida",        races:"Governor · Senate"},
  IA:{name:"Iowa",           races:"Senate"},
  MI:{name:"Michigan",       races:"Senate"},
  MN:{name:"Minnesota",      races:"Senate"},
  OH:{name:"Ohio",           races:"Governor · Senate"},
  ME:{name:"Maine",          races:"Senate"},
  KS:{name:"Kansas",         races:"Senate"},
  NE:{name:"Nebraska",       races:"Senate"},
  TX:{name:"Texas",          races:"Governor · Senate"},
};
const ORDER = ["GA","SC","NC","FL","IA","MI","MN","OH","ME","KS","NE","TX"];

// Every state names its streams differently — by_mail / mail_returned / returned for
// mail, in_person / early_in_person for the rest, and Iowa's older files and
// Minnesota's carry only a combined figure. One reader, so a state cannot quietly
// contribute a different quantity to the same chart.
const num = x => x == null ? null : (typeof x === "object" ? (x.total ?? null) : x);
function streams(s){
  if (!s) return null;
  const comb = num(s.returned_combined);
  let mail = num(s.by_mail); if (mail == null) mail = num(s.mail_returned);
  if (mail == null) mail = num(s.returned);
  let ip = num(s.in_person); if (ip == null) ip = num(s.early_in_person);
  let total = num(s.total);
  if (total == null) total = comb;
  if (total == null && (mail != null || ip != null)) total = (mail||0) + (ip||0);
  if (total == null) return null;
  return {total, mail, ip};
}


// ---- What is left to decide: banked early vote against the election-day pool ----
// Election-day VOLUME is close to mode-independent. Texas counted 2.32M of them in
// 2018, 1.71M in 2020, 2.59M in 2022 and 2.33M in 2024 while its early vote swung
// between 5.5M and 9.6M. Twelve of fourteen states we track saw election day SHRINK
// from 2018 to 2022 as early voting ate into it; Texas and Iowa are the two where it
// grew. So each state's election-day pool is set as a CAP from its own history, and
// what is already banked is measured against that rather than against a turnout
// forecast the early vote cannot support.
async function capsPanel(){
  let caps = null;
  try{
    const r = await fetch("data/eday-caps.json?t=" + Date.now());
    if (r.ok) caps = await r.json();
  }catch(e){ return null; }
  if (!caps) return null;
  const rows = Object.entries(caps)
    .map(([code, v]) => ({code, name:(STATES[code]||{}).name || code, ...v}))
    .filter(r => r.ev && r.eday_cap)
    .sort((a,b) => b.banked_pct - a.banked_pct);
  if (!rows.length) return null;

  const draw = host => {
    const W = host.clientWidth || 720, rowH = 26, padL = 112, padR = 54;
    const H = rows.length * rowH + 34;
    const max = Math.max(...rows.map(r => r.turnout));
    const x = v => padL + (W - padL - padR) * v / max;
    const parts = rows.map((r, i) => {
      const y = i * rowH + 6, h = rowH - 12;
      const evW = Math.max(x(r.ev) - padL, 1);
      const edW = Math.max(x(r.turnout) - x(r.ev), 1);
      return `<text x="${padL - 8}" y="${y + h/2 + 4}" text-anchor="end" class="rlab">${esc(r.name)}</text>
        <rect x="${padL}" y="${y}" width="${evW}" height="${h}" rx="2" fill="${PAL.now}">
          <title>${esc(r.name)}: ${n(r.ev)} already cast</title></rect>
        <rect x="${padL + evW + 2}" y="${y}" width="${Math.max(edW - 2, 1)}" height="${h}" rx="2"
          fill="none" stroke="${PAL.mid}" stroke-width="1.5" stroke-dasharray="3 2">
          <title>${esc(r.name)}: up to ${n(r.eday_cap)} still to come on election day</title></rect>
        <text x="${x(r.turnout) + 6}" y="${y + h/2 + 4}" class="vlab">${r.banked_pct}%</text>`;
    }).join("");
    host.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img"
      aria-label="Share of each state's vote already cast, against the election-day pool still to come">
      ${parts}</svg>`;
  };

  const tot = rows.reduce((a, r) => (a.ev += r.ev, a.cap += r.eday_cap, a), {ev:0, cap:0});
  const most = rows[0], least = rows[rows.length - 1];
  return panel({
    title: "What is left to decide",
    races: "",
    lede: `<b class="fig">${n(tot.ev)}</b> ballots are already cast across these states,
      against an election-day pool of about <b class="fig">${n(tot.cap)}</b>. In
      <b>${esc(most.name)}</b> that is <b>${most.banked_pct}%</b> of the vote already in;
      in <b>${esc(least.name)}</b> only <b>${least.banked_pct}%</b>. The same early-vote
      lead means very different things in those two states.`,
    legend: key("now", "already cast") +
      `<span><i style="background:none;border:1.5px dashed ${PAL.mid}"></i>election-day pool</span>`,
    caption: `The election-day pool is a CAP taken from each state's own 2018 and 2022
      counts, not a turnout forecast. Election-day volume barely moves with the mode mix:
      Texas counted 2.32M in 2018 and 2.59M in 2022 while its early vote went from 5.5M to
      7.7M. Twelve of the fourteen states here saw election day shrink between those two
      midterms, so the cap is a ceiling rather than an expectation. Percentages are the
      share of the projected vote already in hand.`,
    table: `<table><thead><tr><th>State</th><th>Already cast</th><th>Election-day cap</th>
      <th>Projected turnout</th><th>Share already in</th>
      <th>Net lead a side can carry, if it wins election day by 15</th></tr></thead><tbody>
      ${rows.map(r => `<tr><td>${esc(r.name)}</td><td>${n(r.ev)}</td>
        <td>${n(r.eday_cap)}</td><td>${n(r.turnout)}</td><td>${r.banked_pct}%</td>
        <td>${n(Math.round(r.eday_cap * 0.15))}</td></tr>`).join("")}
      </tbody></table>`,
    draw
  });
}

async function renderCharts(panels){
  if (!panels) return;
  panels.replaceChildren();
  const sections = [], jump = [];
  const note = (m) => { const d = document.createElement("div"); d.className = "note";
    d.innerHTML = m; panels.appendChild(d); };

  // the whole-board view first: how much of each state is already decided
  const caps = await capsPanel();
  if (caps){ sections.push(caps);
    jump.push(`<a href="#p-caps">What is left</a>`); caps.id = "p-caps"; }

  for (const code of ORDER){
    const meta = STATES[code];
    // same shared payloads as the cards, so the two panels cannot disagree
    const sd = await stateData(code);
    const cur = sd.cur, hist = sd.hist || {};
    if (!cur && !Object.keys(hist).length) continue;
    if (cur && cur.source) SRC.push(meta.name + ": " + cur.source);

    // ---- rows: one per cycle that actually has a figure ----
    const rows = [];
    for (const y of Object.keys(hist).sort()){
      const st = streams((hist[y]||{}).state_totals);
      if (!st) continue;                       // a cycle with nothing published is dropped
      rows.push({year:+y, ...st, tip:"completed cycle"});
    }
    const now = cur ? streams(cur.state_totals) : null;
    if (now){
      // a state that does not report in person must not contribute a zero
      if (cur.in_person_reported === false) now.ip = null;
      rows.push({year:2026, ...now, tip:"as of " + (cur.as_of||"") + " — still voting"});
    }
    if (!rows.length) continue;

    const mid = rows.filter(r => r.year % 4 === 2 && r.year !== 2026).pop();
    const pct = (mid && now) ? Math.round(now.total/mid.total*100) : null;

    // ---- South Carolina is the one state with a figure per early-voting day ----
    let draw, caption, legend = LEGEND, lede, table;
    const scDaily = code === "SC" && cur && cur.daily;
    if (scDaily){
      const ser = [];
      for (const y of Object.keys(hist).sort()){
        const d = hist[y]; if (!d || !d.days) continue;
        ser.push({year:+y, vals:d.days.map(k => d.running[k])});
      }
      let run = 0;
      const v26 = Object.keys(cur.daily).sort((a,b)=>new Date(a)-new Date(b)).map(k => run += cur.daily[k]);
      if (v26.length) ser.push({year:2026, vals:v26});
      ser.sort((a,b)=>a.year-b.year);
      const m2 = ser.find(s=>s.year===2022), n2 = ser.find(s=>s.year===2026);
      const i = (n2 ? n2.vals.length : 0) - 1;
      const same = (m2 && n2 && i>=0) ? Math.round(n2.vals[i]/m2.vals[i]*100) : null;
      const nDays = Math.max(...ser.map(s=>s.vals.length));
      // The daily series is IN-PERSON only: South Carolina's daily report counts people
      // through the door, and its absentee workbook publishes requested and issued but
      // not returned, so mail has no per-day figure. Calling these "ballots" made this
      // card read as the state total and contradict the 789,240 on the card above, which
      // includes mail. Say which quantity this is.
      const scMail = (cur.state_totals || {}).by_mail;
      lede = same
        ? `Through <b>day ${i+1}</b> of early voting, <b class="fig">${n(n2.vals[i])}</b>
           <b>in-person</b> ballots — against <b class="fig">${n(m2.vals[i])}</b> on the
           same day of 2022. That is <b>${same}%</b> of the last midterm's pace.`
        : `South Carolina publishes a figure per early-voting day, so 2026 can be set
           against the same day of earlier cycles.`;
      caption = `Running total of <b>in-person</b> ballots after each early-voting day —
        the same day of each cycle, not a share of a finished one. 2022 and 2024 ran
        ${nDays} days.${scMail ? ` Mail is not in this series: South Carolina's daily
        report counts in-person voters only, so the ${n(scMail)} mail ballots returned
        are excluded here and included in the card above.` : ""}`;
      table = `<table><thead><tr><th>Day</th>${ser.map(s=>`<th>${s.year}</th>`).join("")}
        ${m2&&n2?"<th>vs 2022</th>":""}</tr></thead><tbody>
        ${Array.from({length:nDays},(_,k)=>`<tr><td>Day ${k+1}</td>
          ${ser.map(s=>`<td class="fig${s.year===2026?" b":""}">${s.vals[k]==null?'<span class="dim">—</span>':n(s.vals[k])}</td>`).join("")}
          ${m2&&n2?`<td class="fig">${(n2.vals[k]!=null&&m2.vals[k])?Math.round(n2.vals[k]/m2.vals[k]*100)+"%":""}</td>`:""}</tr>`).join("")}
        </tbody></table>`;
      draw = host => drawLines(host, ser, {aria:`South Carolina cumulative in-person early vote by day of early voting.`});
    } else {
      const pres = rows.filter(r => r.year % 4 === 0).pop();
      // Declared before the lede and caption, which both read it. Putting it next to the
      // table left it in the temporal dead zone and the charts tab died on
      // "Cannot access 'share' before initialization".
      const share = await evShare();
      const anyShare = rows.some(r => shareFor(share, code, r.year));
      // Hang the election-day figure on each row the bars can show it for. A year with
      // no turnout denominator keeps its early-only bar rather than being given a
      // guessed one.
      legend = (await addElectionDay(rows, code)).legend;
      lede = !now
        ? `No 2026 early-vote file is published yet, so this is the record of earlier
           cycles only.`
        : pct != null
          ? `<b class="fig">${n(now.total)}</b> early and mail ballots so far — already
             <b>${pct}%</b> of everything ${mid.year} cast early, with voting still open.`
          : `<b class="fig">${n(now.total)}</b> early and mail ballots so far.
             There is no midterm in our archive to set that against${pres?` — only
             ${pres.year}, a presidential cycle, which is not comparable`:""}.`;
      caption = `Total early and mail ballots. Every cycle but 2026 is a completed one;
        2026 is a running total and is drawn open for that reason.
        ${rows.some(r=>r.ip==null)?"A stream this state does not report is left out rather than shown as zero.":""}
        ${rows.some(r=>shareFor(share, code, r.year))
          ? `Total vote and early share come from that year's election-night feed, the only
             place a turnout denominator exists. <b>counted</b> means the feed labelled the
             mode and the share is exact; <b>cast</b> means it did not, so the numerator is
             ballots received rather than ballots counted early - a different quantity, and
             in Texas 2024 twelve points apart.`
          : "No early share is shown: this state's results collector cannot be pointed at a past election, so there is no turnout denominator for it yet."}`;
      table = `<table><thead><tr><th>Cycle</th><th>Mail</th><th>In person</th><th>Total early</th>
        ${anyShare?"<th>Total vote</th><th>Early share</th>":""}
        ${mid?"<th>vs "+mid.year+"</th>":""}</tr></thead><tbody>
        ${rows.map(r=>{ const sh = shareFor(share, code, r.year); return `<tr><td>${r.year}${r.year%4===0?' <span class="dim">presidential</span>':""}</td>
          <td class="fig">${r.mail==null?'<span class="dim">not reported</span>':n(r.mail)}</td>
          <td class="fig">${r.ip==null?'<span class="dim">not reported</span>':n(r.ip)}</td>
          <td class="fig b">${n(r.total)}</td>
          ${anyShare?`<td class="fig">${sh?n(sh.total):'<span class="dim">—</span>'}</td>
            <td class="fig">${sh?`${Math.round(100*sh.pct)}% <span class="dim">${sh.kind}</span>`:'<span class="dim">—</span>'}</td>`:""}
          ${mid?`<td class="fig">${r.year===mid.year?"—":Math.round(r.total/mid.total*100)+"%"}</td>`:""}</tr>`;}).join("")}
        </tbody></table>`;
      draw = host => drawBars(host, rows, {aria:`${meta.name} early and mail ballots by cycle.`});
    }

    const sec = panel({title:meta.name, races:meta.races, lede, legend, caption, table, draw});
    sec.id = "st-" + code;
    sections.push(sec);
    jump.push(`<a href="#st-${code}">${code}</a>`);
  }


  // ---------- who has voted early, where a state records it ----------
  // Only a few states record race at registration. This is turnout composition,
  // not a result: no state counts ballots before election day, so a share here
  // says who has shown up, never how they voted.
  const demoPanels = [];
  for (const code of ORDER){
    let d = null;
    try{ d = await J("data/demographics-"+code+".json"); }catch(e){ continue; }
    const yrs = Object.keys(d.years||{}).sort();
    if (!yrs.length) continue;
    const latest = yrs[yrs.length-1];
    const vt = (y, stream) => ((((d.years[y]||{}).streams||{})[stream]||{}).race) || null;
    const nowR = vt(latest, "voted");
    if (!nowR) continue;

    const series = yrs.filter(y => vt(y,"voted")).map(y => ({
      key:y, label:y + (+y%4===0 ? " final" : (+y===2026 ? " so far" : "")),
      cycle: cycleOf(y)
    }));
    const keys = Object.keys(nowR.counts);
    const groups = keys
      .map(k => ({
        label: nowR.labels[k], k,
        vals: Object.fromEntries(series.map(sr => {
          const r = vt(sr.key,"voted");
          return [sr.key, r ? r.counts[k]/r.total : null];
        })),
        counts: Object.fromEntries(series.map(sr => {
          const r = vt(sr.key,"voted");
          return [sr.key, r ? r.counts[k] : null];
        })),
      }))
      .sort((a,b) => (b.vals[latest]||0) - (a.vals[latest]||0));

    const prev = series.length > 1 ? series[series.length-2].key : null;
    const blk = groups.find(g => g.k === "nh_black");
    const shift = (blk && prev && blk.vals[prev] != null)
      ? (blk.vals[latest] - blk.vals[prev]) * 100 : null;

    // mail against in person: the two streams differ sharply and pooling hides it
    const mail = vt(latest,"accept"), ip = vt(latest,"inperson");
    const streamLine = (mail && ip && blk) ? `
      <p class="lede" style="margin-top:9px">By stream: mail returned is
        <b>${(mail.counts.nh_black/mail.total*100).toFixed(1)}%</b> Black
        (${n(mail.total)} ballots), in-person early
        <b>${(ip.counts.nh_black/ip.total*100).toFixed(1)}%</b> (${n(ip.total)}).</p>` : "";

    const legend = series.map(sr => key(sr.cycle, sr.label)).join("");
    const lede = shift != null
      ? `Black voters are <b>${(blk.vals[latest]*100).toFixed(1)}%</b> of ${latest}'s early
         vote so far, against <b>${(blk.vals[prev]*100).toFixed(1)}%</b> in ${prev} —
         <b>${shift>0?"+":"−"}${Math.abs(shift).toFixed(1)}</b> points.
         ${prev && +prev%4===0 ? `${prev} is a completed presidential cycle and ${latest} is
           days old, so expect this gap to move as the window runs.` : ""}`
      : `Who has voted early so far, by race.`;

    const sec = panel({
      title: STATES[code] ? STATES[code].name : code,
      races: (STATES[code] ? STATES[code].races : "") + " · by race",
      lede: lede + streamLine,
      legend,
      caption: `Share of each cycle's early vote. This is who has voted, not how they
        voted — no state counts ballots before election day, so nothing here is a result
        or a projection. Only Georgia, North Carolina and Louisiana record race at
        registration for 2026; the rest of the board cannot show this at all.
        ${prev ? `${prev} is a completed cycle and ${latest} is still running.` : ""}`,
      table: `<table><thead><tr><th>Group</th>
        ${series.map(sr=>`<th>${sr.label}</th>`).join("")}
        ${prev?"<th>change</th>":""}</tr></thead><tbody>
        ${groups.map(g=>`<tr><td>${esc(g.label)}</td>
          ${series.map(sr=>`<td class="fig">${g.vals[sr.key]==null?'<span class="dim">—</span>'
            :`${(g.vals[sr.key]*100).toFixed(1)}% <span class="dim">${n(g.counts[sr.key])}</span>`}</td>`).join("")}
          ${prev?`<td class="fig">${(g.vals[prev]!=null&&g.vals[latest]!=null)
            ?`<b style="color:${g.vals[latest]>=g.vals[prev]?"var(--d)":"var(--r)"}">${
              g.vals[latest]>=g.vals[prev]?"+":"−"}${Math.abs((g.vals[latest]-g.vals[prev])*100).toFixed(1)}</b>`
            :""}</td>`:""}</tr>`).join("")}
        </tbody></table>`,
      draw: host => drawShares(host, groups, series,
        {aria:`${code} early vote composition by race, ${series.map(x=>x.key).join(" and ")}.`}),
    });
    sec.id = "race-" + code;
    demoPanels.push(sec);
    jump.push(`<a href="#race-${code}">${code} race</a>`);
  }
  sections.push(...demoPanels);

  if (!sections.length){ note("<b>No early-vote data loaded.</b>"); return; }

  const nav = document.createElement("nav");
  nav.className = "jumprow";
  nav.innerHTML = `<span class="jlab">Jump to</span>` + jump.join("");
  panels.appendChild(nav);
  sections.forEach(s => panels.appendChild(s));

  const redraw = () => sections.forEach(s => s._draw());
  redraw();
  let t; addEventListener("resize", () => { clearTimeout(t); t = setTimeout(redraw, 120); });

  const asof = document.getElementById("asof");
  if (asof){
    const stamps = [];
    for (const code of ORDER){
      try{ const d = (await stateData(code)).cur; if (d && d.fetched) stamps.push(d.fetched); }catch(e){}
    }
    if (stamps.length){
      const d = new Date(stamps.sort().pop());
      asof.textContent = "Last pull " +
        d.toLocaleString("en-US",{month:"short",day:"numeric",hour:"numeric",minute:"2-digit"}) + ".";
    }
  }
  const srcs = document.getElementById("srcs");
  if (srcs) srcs.textContent = "Sources \u2014 " + SRC.join("  \u2022  ");
}
window.renderCharts = renderCharts;
// compare.html renders at once; the board calls renderCharts() the first time its
// charts tab is opened, so these fetches do not run on every board load.
if (document.getElementById("panels")) renderCharts(document.getElementById("panels"));
})();
