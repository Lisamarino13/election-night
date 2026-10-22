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
const tip = document.getElementById("tip");
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
  const max = Math.max(...rows.filter(r=>r.total!=null).map(r=>r.total), 1);
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
    const sub = svgEl("text", {class:"axlab", x:x+bw/2, y:H-PAD.b+37, "text-anchor":"middle",
      style:"font-size:11.5px;letter-spacing:.05em;text-transform:uppercase"});
    sub.textContent = r.note || (cycleOf(r.year)==="pres" ? "presidential" : cycleOf(r.year)==="now" ? "still voting" : "midterm");
    svg.appendChild(sub);

    if (r.total == null){                       // a gap we cannot fill is shown as a gap
      const m = svgEl("text", {x:x+bw/2, y:yOf(0)-12, "text-anchor":"middle",
        style:"font-size:12.5px;fill:var(--flag);font-style:italic"});
      m.textContent = "not published"; svg.appendChild(m);
      svg.appendChild(svgEl("line", {x1:x, x2:x+bw, y1:yOf(0), y2:yOf(0),
        stroke:"var(--flag)", "stroke-width":2, "stroke-dasharray":"3 3"}));
      return;
    }
    const y = yOf(r.total), h = plotH - (y - PAD.t);
    const cyc = cycleOf(r.year), fill = PAL[cyc];
    const p = svgEl("path", {d:barPath(x, y, bw, h, 4), fill: cyc==="now" ? "none" : fill,
      stroke: fill, "stroke-width": cyc==="now" ? 2 : 0,
      "stroke-dasharray": cyc==="now" ? "5 3" : "none"});
    p.style.cursor = "default";
    svg.appendChild(p);
    const vl = svgEl("text", {class:"dlab fig", x:x+bw/2, y:y-9, "text-anchor":"middle", fill:"var(--fg)"});
    vl.textContent = ab(r.total); svg.appendChild(vl);
    // hit target larger than the mark
    const hit = svgEl("rect", {x:x-7, y:PAD.t, width:bw+14, height:plotH, fill:"transparent"});
    hit.addEventListener("pointerenter", e => showTip(e,
      `<div class="k"><i style="background:${fill}"></i><b>${r.year}</b></div>
       <div class="fig">${n(r.total)} early + mail</div>
       ${r.mail!=null?`<div class="dim fig" style="color:var(--dim)">mail ${n(r.mail)} &middot; in person ${n(r.ip)}</div>`:""}
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

// ---- load ------------------------------------------------------------------
(async function(){
  const panels = document.getElementById("panels");
  const sections = [];
  const fail = m => { const d=document.createElement("div"); d.className="note";
    d.innerHTML = `<b>Could not draw this.</b> ${esc(m)}`; panels.appendChild(d); };

  // ---------- Georgia ----------
  try{
    const [h, cur] = await Promise.all([J("data/ev-history-GA.json"), J("data/early-GA.json")]);
    const y = h.years || {}, t26 = cur.state_totals || {};
    SRC.push("Georgia: " + (cur.source||""));
    const rows = [
      {year:2020, total:null},
      {year:2022, total:null},
      {year:2024, total:(y["2024"]||{}).state_totals ? y["2024"].state_totals.total : null,
        mail:((y["2024"]||{}).state_totals||{}).by_mail, ip:((y["2024"]||{}).state_totals||{}).in_person,
        tip:"completed cycle"},
      {year:2026, total:t26.total, mail:t26.by_mail, ip:t26.in_person,
        tip:"as of "+(cur.as_of||"")+" — still voting"},
    ];
    const pres = rows.find(r=>r.year===2024).total, now = rows.find(r=>r.year===2026).total;
    sections.push(panel({
      title:"Georgia", races:"Governor \u00b7 Senate",
      lede:`<b class="fig">${n(now)}</b> early and mail ballots so far, against
        <b class="fig">${n(pres)}</b> for all of 2024 — <b>${Math.round(now/pres*100)}%</b> of a
        presidential cycle's entire early vote, with voting still open. Georgia has no
        midterm here to measure against: our source carries only 2024 at county level.`,
      legend:LEGEND,
      caption:`Total early and mail ballots. 2020 and 2022 are not published in the file
        this board reads, so they are shown as gaps rather than guessed at. Georgia does
        not register voters by party, so no D/R split exists in the official data.`,
      table:`<table><thead><tr><th>Cycle</th><th>Mail</th><th>In person</th><th>Total</th></tr></thead>
        <tbody>${rows.map(r=>`<tr><td>${r.year}${r.year%4===0?' <span class="dim">presidential</span>':""}</td>
          ${r.total==null?'<td colspan="3" class="miss">not published in our source</td>'
          :`<td class="fig">${n(r.mail)}</td><td class="fig">${n(r.ip)}</td><td class="fig b">${n(r.total)}</td>`}</tr>`).join("")}
        </tbody></table>`,
      draw: host => drawBars(host, rows, {aria:`Georgia early and mail ballots: 2024 ${n(pres)}, 2026 so far ${n(now)}; 2020 and 2022 not published.`}),
    }));
  }catch(e){ fail("Georgia — " + e.message); }

  // ---------- South Carolina ----------
  try{
    const [h, cur] = await Promise.all([J("data/ev-history-SC.json"), J("data/early-SC.json")]);
    const y = h.years || {};
    SRC.push("South Carolina: " + (cur.source||""));
    const ser = [];
    for (const yr of ["2022","2024"]){
      const d = y[yr]; if(!d || !d.days) continue;
      ser.push({year:+yr, vals:d.days.map(k=>d.running[k])});
    }
    // 2026's own day columns are per-day counts; accumulate them the same way.
    const daily = cur.daily || {}; let run = 0;
    const v26 = Object.keys(daily).sort((a,b)=>new Date(a)-new Date(b)).map(k => run += daily[k]);
    if (v26.length) ser.push({year:2026, vals:v26});
    ser.sort((a,b)=>a.year-b.year);
    const mid = ser.find(s=>s.year===2022), now = ser.find(s=>s.year===2026);
    const i = (now?now.vals.length:0) - 1;
    const ratio = (mid && now && i>=0) ? Math.round(now.vals[i]/mid.vals[i]*100) : null;
    const nDays = Math.max(...ser.map(s=>s.vals.length));
    sections.push(panel({
      title:"South Carolina", races:"Governor \u00b7 Senate",
      lede: ratio ? `Through <b>day ${i+1}</b> of early voting, <b class="fig">${n(now.vals[i])}</b>
        ballots — against <b class="fig">${n(mid.vals[i])}</b> on the same day of 2022.
        That is <b>${ratio}%</b> of the last midterm's pace, and ahead of where the 2024
        presidential cycle sat on day ${i+1}.`
        : "South Carolina publishes a figure per early-voting day, so 2026 can be set against the same day of earlier cycles.",
      legend:LEGEND,
      caption:`Running total after each early-voting day. This is the one state of the three
        where the comparison is genuinely like-for-like: the same day of each cycle, not a
        share of a finished one. 2022 and 2024 ran ${nDays} days.`,
      table:`<table><thead><tr><th>Day</th>${ser.map(s=>`<th>${s.year}</th>`).join("")}
        ${mid&&now?`<th>vs 2022</th>`:""}</tr></thead><tbody>
        ${Array.from({length:nDays},(_,k)=>`<tr><td>Day ${k+1}</td>
          ${ser.map(s=>`<td class="fig${s.year===2026?" b":""}">${s.vals[k]==null?'<span class="dim">—</span>':n(s.vals[k])}</td>`).join("")}
          ${mid&&now?`<td class="fig">${(now.vals[k]!=null&&mid.vals[k])?Math.round(now.vals[k]/mid.vals[k]*100)+"%":""}</td>`:""}</tr>`).join("")}
        </tbody></table>`,
      draw: host => drawLines(host, ser, {aria:`South Carolina cumulative early vote by day: 2026 is at ${ratio}% of 2022's same-day pace.`}),
    }));
  }catch(e){ fail("South Carolina — " + e.message); }

  // ---------- North Carolina ----------
  try{
    const [h, cur] = await Promise.all([J("data/ev-history-NC.json"), J("data/early-NC.json")]);
    const y = h.years || {}, st = cur.state_totals || {};
    SRC.push("North Carolina: " + (cur.source||""));
    const tot = o => ((o||{}).mail_returned||{}).total!=null || ((o||{}).early_in_person||{}).total!=null
      ? (((o||{}).mail_returned||{}).total||0) + (((o||{}).early_in_person||{}).total||0) : null;
    const rows = ["2020","2022","2024"].map(yr=>{
      const s=(y[yr]||{}).state_totals;
      return {year:+yr, total:tot(s), mail:((s||{}).mail_returned||{}).total,
        ip:((s||{}).early_in_person||{}).total, tip:"completed cycle"};
    }).filter(r=>r.total!=null);
    rows.push({year:2026, total:tot(st), mail:(st.mail_returned||{}).total,
      ip:(st.early_in_person||{}).total, tip:"as of "+(cur.as_of||"")+" — still voting"});
    const mid = rows.find(r=>r.year===2022), now = rows[rows.length-1];
    sections.push(panel({
      title:"North Carolina", races:"Senate",
      lede:`<b class="fig">${n(now.total)}</b> early and mail ballots so far — already
        <b>${Math.round(now.total/mid.total*100)}%</b> of everything 2022 cast early, with
        voting still open. North Carolina does register by party, so the board's own card
        carries the D/R/unaffiliated split; this chart is turnout only.`,
      legend:LEGEND,
      caption:`Total early and mail ballots. Every year but 2026 is a completed cycle;
        2026 is a running total and is drawn open for that reason.`,
      table:`<table><thead><tr><th>Cycle</th><th>Mail</th><th>In person</th><th>Total</th>
        <th>vs 2022</th></tr></thead><tbody>
        ${rows.map(r=>`<tr><td>${r.year}${r.year%4===0?' <span class="dim">presidential</span>':""}</td>
          <td class="fig">${n(r.mail)}</td><td class="fig">${n(r.ip)}</td>
          <td class="fig b">${n(r.total)}</td>
          <td class="fig">${r.year===2022?"—":Math.round(r.total/mid.total*100)+"%"}</td></tr>`).join("")}
        </tbody></table>`,
      draw: host => drawBars(host, rows, {aria:`North Carolina early and mail ballots by cycle; 2026 so far ${n(now.total)}, ${Math.round(now.total/mid.total*100)} percent of the 2022 total.`}),
    }));
  }catch(e){ fail("North Carolina — " + e.message); }

  sections.forEach(s => panels.appendChild(s));
  const redraw = () => sections.forEach(s => s._draw());
  redraw();
  let t; addEventListener("resize", () => { clearTimeout(t); t = setTimeout(redraw, 120); });

  // trend-ev.json carries no run stamp, so date this page off the freshest
  // "fetched" among the three files it actually drew from.
  const stamps = [];
  for (const st of ["GA","SC","NC"]){
    try{ const d = await J("data/early-"+st+".json"); if(d.fetched) stamps.push(d.fetched); }catch(e){}
  }
  if (stamps.length){
    const d = new Date(stamps.sort().pop());
    document.getElementById("asof").textContent = "Last pull " +
      d.toLocaleString("en-US",{month:"short",day:"numeric",hour:"numeric",minute:"2-digit"}) + ".";
  }
  document.getElementById("srcs").textContent = "Sources — " + SRC.join("  •  ");
})();
