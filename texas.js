/* The Texas tab: the whole Texas analysis, thesis first.
 *
 * Texas is the one state on this board where the early vote is nearly the whole
 * election, so it gets a tab rather than a card. The argument runs: the 2024 result
 * carried onto 2026 turnout is R+5.98 and Democrats need ~305k net new votes to erase
 * it; three countable things say the electorate changed; three ways of pricing that
 * change land inside two points of even; and the sign is set by one number nobody has
 * measured - how far Hispanic voters move.
 *
 * Two corrections are baked in, both made on 2 November and both against earlier work:
 *
 *  1. The early-vote read used a within-county skew of 22.84 points borrowed from North
 *     Carolina, on the belief that Texas publishes no partisan results by mode. It
 *     does: County.json carries EV beside V per candidate per county, so every past
 *     cycle's early and election-day margins are exact. The real Texas skew is between
 *     -2.4 and +0.8 points, and in 2024 it pointed the OTHER way. The old single tie
 *     line of D+5.54 is replaced by a band, because a tie can land anywhere in it
 *     depending on what election day does.
 *  2. The county model moved the whole non-white bloc +12, Black voters included. They
 *     were already 91.1% Democratic in 2024, so +12 there is not defensible. Capping it
 *     costs Democrats 1.62 points and turns D+0.65 into R+0.97. Both are shown.
 *
 * Data lives in data/tx/*.csv so the numbers are inspectable rather than inlined.
 */
(function () {
  "use strict";

  var PROJ = {total: 10211996, banked: 7734079};
  var SHARE = PROJ.banked / PROJ.total;
  var EDAY_VOTES = PROJ.total - PROJ.banked;
  // The band is set by the SKEW (election day minus early), not by the absolute
  // election-day margin. An earlier version used the absolute figure and that was wrong
  // twice over. First, 2022's election day was R+16 largely because the whole race was
  // R+10.90 - carrying that number into a race everyone expects to be close imports
  // 2022's partisan level as though it were a property of election day. Second, the two
  // races it used were each the most Democrat-friendly in their own cycle: Cruz-Allred's
  // -4.14 is the biggest outlier of nine statewide races in 2024, and Abbott's +7.48 the
  // lowest of twelve in 2022. The algebra that matters is
  //
  //     final = early + (1 - banked share) * skew
  //
  // so the tie line is simply early = -(1 - share) * skew. The basis is the major
  // statewide offices - President, Senate, Governor, Lt Governor, Attorney General.
  // An earlier version used judicial races on the grounds that nobody runs ahead of the
  // ticket in them, which is true but produced a near-identical band (D+2.07 to R+0.33
  // against D+2.27 to R+0.18) while filling the table with Supreme Court places nobody
  // recognises. The 0.2-point difference is not worth the noise.
  var SKEW_2024 = -0.75;    // median of President +2.64 and Senate -4.14
  var SKEW_2022 = 9.36;     // median of Governor, Lt Governor and AG; the only midterm
  var THR_SAFE_D = -(1 - SHARE) * SKEW_2022;   // D+2.07
  var THR_SAFE_R = -(1 - SHARE) * SKEW_2024;   // R+0.33

  var HIST = [
    {year: 2024, kind: "presidential", race: "U.S. Senate", total: 11291854,
     earlyShare: 80.4, early: 9.31, eday: 5.17, final: 8.50},
    {year: 2022, kind: "midterm", race: "Governor", total: 8102908,
     earlyShare: 68.2, early: 8.53, eday: 16.00, final: 10.90},
    {year: 2020, kind: "presidential", race: "U.S. Senate", total: 11144040,
     earlyShare: 86.8, early: 7.74, eday: 22.19, final: 9.64}
  ];

  /* ---------------------------------------------------------------- utilities */
  var D = {};                       // dataset cache, filled by load()
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c];
    });
  }
  function n0(v) { return Math.round(v).toLocaleString("en-US"); }
  function mgn(v, dp) {
    if (v == null || !isFinite(v)) return "—";
    return (v < 0 ? "D+" : "R+") + Math.abs(v).toFixed(dp == null ? 2 : dp);
  }
  function num(v) { var x = parseFloat(v); return isFinite(x) ? x : null; }

  /* A CSV parser that handles the quoted fields these files carry. */
  function parseCSV(text) {
    var rows = [], row = [], cur = "", q = false, i;
    for (i = 0; i < text.length; i++) {
      var c = text[i];
      if (q) {
        if (c === '"') { if (text[i + 1] === '"') { cur += '"'; i++; } else q = false; }
        else cur += c;
      } else if (c === '"') q = true;
      else if (c === ",") { row.push(cur); cur = ""; }
      else if (c === "\n") { row.push(cur); rows.push(row); row = []; cur = ""; }
      else if (c !== "\r") cur += c;
    }
    if (cur.length || row.length) { row.push(cur); rows.push(row); }
    var head = rows.shift() || [];
    return rows.filter(function (r) { return r.length && r.join("").trim(); })
      .map(function (r) {
        var o = {};
        head.forEach(function (h, j) { o[h.trim()] = (r[j] == null ? "" : r[j]).trim(); });
        return o;
      });
  }
  function load(name) {
    return fetch("data/tx/" + name + "?t=" + Date.now()).then(function (r) {
      if (!r.ok) throw new Error(name + ": HTTP " + r.status);
      return name.slice(-5) === ".json" ? r.json() : r.text().then(parseCSV);
    });
  }

  /* --------------------------------------------------------------- svg helpers */
  var NS = "http://www.w3.org/2000/svg";
  function svg(w, h, label) {
    return '<svg viewBox="0 0 ' + w + " " + h + '" width="100%" role="img" '
         + 'aria-label="' + esc(label) + '" style="max-width:100%;height:auto">';
  }
  function txt(x, y, s, cls, anchor) {
    return '<text x="' + x + '" y="' + y + '"'
         + (anchor ? ' text-anchor="' + anchor + '"' : "")
         + ' class="' + (cls || "tk") + '">' + esc(s) + "</text>";
  }
  function line(x1, y1, x2, y2, cls) {
    return '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2
         + '" class="' + (cls || "gl") + '"/>';
  }
  function rect(x, y, w, h, fill, extra) {
    return '<rect x="' + x + '" y="' + y + '" width="' + Math.max(0, w)
         + '" height="' + Math.max(0, h) + '" fill="' + fill + '"'
         + (extra || "") + "/>";
  }
  var RC = "var(--rep,#b3443a)", DC = "var(--dem,#2a6ebb)";
  function sideCol(v) { return v < 0 ? DC : RC; }

  /* ------------------------------------------------------------------- the live read */
  function live() {
    var B = window.DATA || {};
    var tx = (B.states || {}).TX;
    var r = tx && tx.races && tx.races.senate;
    if (!r || !r.counted || r.roster_only) return null;
    var out = {counted: r.counted, isTest: !!r.is_test_data,
               precReporting: r.precincts_reporting, precTotal: r.precincts_total};
    var byMode = r.choices_by_mode;
    if (!byMode) return out;
    var party = {};
    (r.candidates || []).forEach(function (c) {
      party[c.name] = (c.party || "O").toUpperCase();
    });
    var e = {R: 0, D: 0, T: 0}, d = {R: 0, D: 0, T: 0};
    Object.keys(byMode).forEach(function (who) {
      var m = byMode[who] || {}, p = party[who] || "O";
      var ev = m.early || 0, dv = m.election_day || 0;
      e.T += ev; d.T += dv;
      if (p === "R" || p === "REP") { e.R += ev; d.R += dv; }
      else if (p === "D" || p === "DEM") { e.D += ev; d.D += dv; }
    });
    if (e.T) out.earlyMargin = (e.R - e.D) / e.T * 100;
    if (d.T) out.edayMargin = (d.R - d.D) / d.T * 100;
    if (e.T + d.T) out.totalMargin = ((e.R + d.R) - (e.D + d.D)) / (e.T + d.T) * 100;
    out.earlyVotes = e.T; out.edayVotes = d.T;
    return out;
  }

  /* ------------------------------------------------------------------ card chrome */
  var SECTIONS = [];
  function card(id, kicker, title, hint, body, note) {
    SECTIONS.push({id: id, title: title});
    return '<section class="txcard" id="' + id + '">'
      + (kicker ? '<p class="txkick">' + esc(kicker) + "</p>" : "")
      + "<h3>" + esc(title) + "</h3>"
      + (hint ? '<p class="txhint">' + hint + "</p>" : "")
      + body
      + (note ? '<p class="txnote">' + note + "</p>" : "")
      + "</section>";
  }

  /* =============================================================== 0. the thesis */
  function thesis() {
    return '<section class="txarg" id="tx-thesis">'
      + '<p class="txkick">The through line</p>'
      + "<h2>One unmeasured number decides this race</h2>"
      + "<p>The 2024 Senate result, carried onto 2026&rsquo;s projected turnout, is "
      + '<b class="nm">R+5.98</b>. Democrats need <b class="nm">' + n0(305279)
      + "</b> net new votes to erase it.</p>"
      + "<p>Three things we can count say the electorate did change: <b class=\"nm\">"
      + n0(PROJ.banked) + "</b> early votes already banked, a March primary that went "
      + 'Democratic <b class="nm">51.70%</b> &mdash; the first midterm majority on record '
      + "&mdash; and precinct returns putting Hispanic metro Texas 31 to 46 points left of "
      + "the border. Three ways of turning that into a margin &mdash; the county model, "
      + "seven historical baselines, a bloc grid &mdash; all land inside two points of even.</p>"
      + '<p>But the county model clears that bar by only <b class="nm">24,657</b> net '
      + "votes. Because flipping a vote closes the gap by two, that cushion is a final "
      + 'margin of <b class="nm">about half a point</b> &mdash; the model&rsquo;s D+0.65. '
      + "Half a point is not a projection, it is a coin flip. And the sign is set by one "
      + "number nothing here "
      + 'measures: how far Hispanic voters actually move. Break-even is <b class="nm">+17.6</b>. '
      + "AtlasIntel&rsquo;s crosstab implies +16.5 and Paxton wins by a hair; Morris&rsquo;s "
      + "engagement finding implies +27 and Talarico wins by three.</p>"
      + '<p class="txnote" style="border-top:none;padding-top:0">Every card below is either '
      + "a way of narrowing that one number, or a reason it cannot be narrowed before the "
      + "polls close.</p>"
      + "</section>";
  }

  /* A framing block. Chapters 1 and 2 are mechanics; Chapter 3 is where the argument
     turns into a number, and the reader needs telling that the disagreement ahead is
     one disagreement wearing eleven hats rather than eleven separate opinions. */
  function framing(id, kicker, title, paras) {
    SECTIONS.push({id: id, title: title});
    return '<section class="txframe" id="' + id + '">'
      + '<p class="txkick">' + esc(kicker) + "</p>"
      + "<h2>" + esc(title) + "</h2>"
      + paras.map(function (t) { return "<p>" + t + "</p>"; }).join("")
      + "</section>";
  }

  /* ======================================================== 1. the read, live or not */
  function readCard(L) {
    var band = '<div class="txband">'
      + '<div class="bandrow"><span class="bl dem">Talarico under every election day Texas has produced</span>'
      + '<span class="bv">better than ' + mgn(THR_SAFE_D) + "</span></div>"
      + '<div class="bandrow mid"><span class="bl">Election day genuinely decides it</span>'
      + '<span class="bv">' + mgn(THR_SAFE_D) + " to " + mgn(THR_SAFE_R) + "</span></div>"
      + '<div class="bandrow"><span class="bl rep">Paxton under every election day Texas has produced</span>'
      + '<span class="bv">worse than ' + mgn(THR_SAFE_R) + "</span></div></div>";

    if (L && L.earlyMargin != null) {
      var verdict, vcls;
      if (L.earlyMargin < THR_SAFE_D) { verdict = "Talarico under every election day Texas has produced"; vcls = "dem"; }
      else if (L.earlyMargin > THR_SAFE_R) { verdict = "Paxton under every election day Texas has produced"; vcls = "rep"; }
      else { verdict = "Inside the band — election day decides it"; vcls = "mid"; }
      return card("tx-read", "Start here · the early vote settles it",
        "The early vote, as reported",
        "Texas publishes its early and mail vote almost all at once when polls close. This "
        + "is that margin, computed from EV beside V per candidate — measured, not assumed."
        + (L.isTest ? ' <b class="amber">This feed is flagged as test data.</b>' : ""),
        '<div class="txbig" style="color:' + sideCol(L.earlyMargin) + '">'
        + mgn(L.earlyMargin) + "</div>"
        + '<div class="txsub">on ' + n0(L.earlyVotes) + " early and mail ballots"
        + (L.edayVotes ? ", election day " + mgn(L.edayMargin) + " on " + n0(L.edayVotes) : "")
        + "</div>"
        + '<p class="txverdict ' + vcls + '">' + esc(verdict) + "</p>"
        + band
        + '<table class="txtbl"><tbody>'
        + '<tr><td>Early and mail</td><td class="num">' + mgn(L.earlyMargin) + "</td></tr>"
        + (L.edayMargin != null ? '<tr><td>Election day</td><td class="num">' + mgn(L.edayMargin) + "</td></tr>" : "")
        + (L.totalMargin != null ? '<tr class="em"><td>Everything counted</td><td class="num">' + mgn(L.totalMargin) + "</td></tr>" : "")
        + '<tr><td>Precincts</td><td class="num">' + n0(L.precReporting || 0) + " / " + n0(L.precTotal || 0) + "</td></tr>"
        + "</tbody></table>",
        "The band, rather than a single line, because the answer depends on what election "
        + "day does and Texas has produced both a +9.4 move and a \u22120.8 one in the last "
        + "two cycles. Source: Texas\u2019s own County.json, which carries EV beside V per "
        + "candidate per county, so every past cycle\u2019s split is exact.");
    }
    return card("tx-read", "Start here · the early vote settles it",
      "What to read when polls close",
      "Nothing published yet. Texas dumps the early and mail vote in one go at 7pm Central, "
      + "and it is about " + (SHARE * 100).toFixed(1) + "% of the projected electorate "
      + "— so that first number is very nearly the result.",
      '<div class="txbig">' + n0(PROJ.banked) + "</div>"
      + '<div class="txsub">banked of a projected ' + n0(PROJ.total) + " ("
      + (SHARE * 100).toFixed(1) + "%), leaving " + n0(EDAY_VOTES) + " for election day</div>"
      + band,
      "The banked lead is <b>not</b> a measured quantity. Texas has no party registration "
      + "— you declare at the poll — so nobody, this board included, knows how the "
      + "banked vote breaks until it is counted. Every banked figure here is a hypothesis.");
  }

  /* ======================================================= 2. measured mode history */
  function historyCard() {
    var all = (D.modes || []).map(function (r) {
      return {y: +r.year, kind: r.kind, c: r.contest, b: r.bucket,
              es: num(r.early_share), e: num(r.early_margin_R),
              d: num(r.eday_margin_R), f: num(r.final_margin_R),
              k: num(r.skew_eday_minus_early), major: r.major === "1"};
    }).filter(function (r) { return r.k != null; });
    // Judicial seats are dropped: seven Supreme Court places and four CCA seats filled
    // the table with contests nobody recognises, and using them as the band's basis
    // moved the answer by 0.2 points against the major offices.
    var rows = all.filter(function (r) { return r.major; });
    if (!rows.length) return "";
    var years = [2024, 2022, 2020];

    // The chart is the point of this card: where the banked vote lands, and where
    // election day drags it. One row per race, early dot to election-day dot.
    // Two collisions to avoid. The year sits in its own left column, so a long
    // contest name like "Lieutenant Governor" cannot run back into "2022 midterm";
    // and the legend gets a bottom gutter rather than sitting two pixels under the
    // axis ticks.
    var YR = 78;
    var W = 720, H = 72 + rows.length * 30, L = YR + 150, R = 78, T = 38;
    var lo = -8, hi = 26;
    var xs = function (v) { return L + (v - lo) / (hi - lo) * (W - L - R); };
    var s2 = svg(W, H, "Where the banked vote lands and where election day drags it");
    [-5, 0, 5, 10, 15, 20, 25].forEach(function (t) {
      s2 += line(xs(t), T - 10, xs(t), H - 22, t === 0 ? "zl" : "gl")
         + txt(xs(t), T - 16, t === 0 ? "even" : (t > 0 ? "R+" : "D+") + Math.abs(t),
               "tk", "middle");
    });
    s2 += txt(YR, H - 10, "\u25cf banked (early + mail)", "lgd")
       + txt(YR + 150, H - 10, "\u25cf election day", "lgd")
       + txt(YR + 272, H - 10, "\u25cb where it finished", "lgd");
    var i = 0;
    years.forEach(function (y) {
      rows.filter(function (r) { return r.y === y; }).forEach(function (r, j) {
        var yy = T + 8 + i * 30; i++;
        if (j === 0) {
          s2 += txt(8, yy + 4, String(y), "lbb");
          s2 += txt(8, yy + 16, y === 2022 ? "midterm" : "presidential", "sub");
        }
        s2 += txt(L - 12, yy + 4, r.c.replace("President/Vice-President", "President")
                  .replace("U. S. Senator", "U.S. Senate"), "lb", "end");
        s2 += line(xs(r.e), yy, xs(r.d), yy, "cn");
        s2 += '<circle cx="' + xs(r.f) + '" cy="' + yy + '" r="4.5" fill="none" '
           + 'stroke="currentColor" stroke-width="1.5"/>';
        s2 += '<circle cx="' + xs(r.e) + '" cy="' + yy + '" r="5.5" fill="' + DC + '"/>';
        s2 += '<circle cx="' + xs(r.d) + '" cy="' + yy + '" r="5.5" fill="' + RC + '"/>';
        s2 += txt(W - R + 8, yy + 4, (r.k > 0 ? "+" : "\u2212")
                  + Math.abs(r.k).toFixed(2), "vl");
      });
    });
    s2 += txt(W - R + 8, T - 16, "move", "tk");
    s2 += "</svg>";

    var body = years.map(function (y) {
      var band = rows.filter(function (r) { return r.y === y; });
      if (!band.length) return "";
      var kindLab = band[0].kind === "midterm" ? "midterm" : "pres.";
      return band.map(function (r) {
        return "<tr" + (r.b === "us senate" ? ' class="em"' : "") + "><td>" + r.y
          + ' <span class="dim">' + kindLab + "</span></td><td>"
          + esc(r.c.replace("President/Vice-President", "President")
                 .replace("U. S. Senator", "U.S. Senate"))
          + '</td><td class="num">' + r.es.toFixed(1) + '%</td><td class="num">' + mgn(r.e)
          + '</td><td class="num">' + mgn(r.d) + '</td><td class="num">' + mgn(r.f)
          + '</td><td class="num ' + (r.k < 0 ? "dem" : "rep") + '">'
          + (r.k > 0 ? "+" : "\u2212") + Math.abs(r.k).toFixed(2) + "</td></tr>";
      }).join("");
    }).join("");

    return card("tx-modes", "Chapter 2 \u00b7 how a banked vote becomes a result",
      "What election day does to the banked vote",
      "Texas banks three quarters of its vote before election day, so the question is "
      + "simply how far the last quarter moves the first three. Blue dot is the banked "
      + "margin, red dot is election day, hollow ring is where the race finished \u2014 "
      + "always close to the blue dot, because the banked vote is most of the electorate. "
      + "The last column is the <b>move</b>: election day minus banked.",
      s2 + '<div class="scroll"><table class="txtbl"><thead><tr><th>Cycle</th><th>Contest</th>'
      + "<th>Banked share</th><th>Banked</th><th>Election day</th><th>Finished</th>"
      + "<th>Move</th></tr></thead><tbody>" + body + "</tbody></table></div>",
      "<b>Election day used to rescue Republicans and has mostly stopped.</b> The move ran "
      + "about +15.8 in 2020, +9.4 in 2022 and \u22120.8 in 2024. <b>The reason is not that "
      + "Texans are voting early more \u2014 they are voting early less.</b> The early share "
      + "went 86.8% \u2192 68.3% \u2192 80.3%, and 2020 had the highest early share of the "
      + "three alongside the largest Republican election-day rescue, which is backwards for "
      + "that story. What changed is WHO votes early. As COVID-era early voting receded, "
      + "Republican counties gave it up far less than Democratic ones: early share fell 8.9 "
      + "points in counties that went D+20 or better and only 3.7 points in counties that "
      + "went R+20 or worse, a correlation of +0.51 between a county\u2019s Republican margin "
      + "and its change in early share. Election day lost its Republican skew because "
      + "Republicans were relatively more likely to have already voted."
      + "<br><br><b>Three cautions.</b> That is an ecological result \u2014 county-level, not "
      + "voter-level \u2014 and Texas has no party registration, so a voter-level version of "
      + "it cannot be computed by anyone. The only <i>midterm</i> here is 2022, which still "
      + "moved +9.36. And Cruz\u2013Allred\u2019s \u22124.14 is the largest move of any race "
      + "in its cycle against Trump\u2019s +2.64 on the same ballot, so a Senate candidate can "
      + "run several points clear of the party on election day in either direction.");
  }

  /* ================================================ 3. what election day would have to do */
  function bankedCard() {
    // A clean 25k ladder. An earlier version spliced the model's own 194,486 into a 20k
    // sequence, which made the steps read as arbitrary. The model's figure belongs in the
    // implied-lead table below, where it is derived rather than asserted.
    var leads = [100000, 125000, 150000, 175000, 200000, 225000, 250000];
    var cols = [5, 10, 16, 22];
    var head = "<tr><th>Banked D lead</th><th>Ties at</th><th>R share needed</th>"
      + cols.map(function (c) { return "<th>eday R+" + c + "</th>"; }).join("") + "</tr>";
    var body = leads.map(function (lead) {
      var tie = lead / EDAY_VOTES * 100;
      var cells = cols.map(function (c) {
        var fin = (-lead + EDAY_VOTES * c / 100) / PROJ.total * 100;
        return '<td class="num ' + (fin < 0 ? "dem" : "rep") + '">' + mgn(fin) + "</td>";
      }).join("");
      return "<tr><td>D+" + n0(lead) + '</td><td class="num">' + mgn(tie)
        + '</td><td class="num">' + (50 + tie / 2).toFixed(2) + "%</td>" + cells + "</tr>";
    }).join("");
    return card("tx-banked", "Section 5 · slide 4 · the banked lead",
      "What election day would have to do",
      "Read down to the banked lead Texas reports, then across to the election-day margin "
      + "you find plausible. Election day is only " + ((1 - SHARE) * 100).toFixed(1)
      + "% of the vote, so the banked lead carries " + (SHARE / (1 - SHARE)).toFixed(1)
      + " times its weight.",
      '<div class="scroll"><table class="txtbl"><thead>' + head + "</thead><tbody>" + body
      + "</tbody></table></div>"
      + '<table class="txtbl" style="margin-top:12px"><thead><tr><th>If election day runs</th>'
      + "<th>the model implies an early margin of</th><th>i.e. a banked lead of</th></tr>"
      + "</thead><tbody>"
      + [["2024-like, R+5.17", 5.17], ["midpoint, R+10", 10], ["2022-like, R+16.00", 16]]
        .map(function (p) {
          var early = (-0.65 - (1 - SHARE) * p[1]) / SHARE;
          return "<tr><td>" + p[0] + '</td><td class="num dem">' + mgn(early)
            + '</td><td class="num dem">D+' + n0(-early / 100 * PROJ.banked) + "</td></tr>";
        }).join("") + "</tbody></table>",
      "The whole R+5 to R+22 range is worth about 4.1 points of final margin, which is why "
      + "the 7pm number decides this. <b>Do not read 140,000 as a prediction.</b> It is "
      + "roughly the break-even banked lead against a 2024-style election day — the "
      + "line the model has to beat, not where the model lands. The model itself is asking "
      + "for about 194,000 banked on that same assumption, and 463,000 if election day "
      + "looks like the 2022 midterm.");
  }

  /* ================================================= 4. where every estimate lands */
  function estimatesCard() {
    var rows = (D.est || []).map(function (r) {
      return {label: r.label, kind: r.kind, m: num(r.margin_R), note: r.note, n: num(r.n)};
    }).filter(function (r) { return r.m != null; });
    // the Black-ceiling correction is a result of today's work, not in the csv
    rows.push({label: "County model, Black shift at its ceiling", kind: "model", m: 0.97,
               note: "the same model with Black voters capped at +2 instead of +12"});
    rows.sort(function (a, b) { return a.m - b.m; });
    var W = 720, H = 36 + rows.length * 23, L = 300, R = 56;
    var lo = -8, hi = 3;
    var xs = function (v) { return L + (v - lo) / (hi - lo) * (W - L - R); };
    var s = svg(W, H, "Every estimate of the Texas Senate margin");
    [-8, -6, -4, -2, 0, 2].forEach(function (t) {
      s += line(xs(t), 16, xs(t), H - 14, t === 0 ? "zl" : "gl")
         + txt(xs(t), 12, t === 0 ? "even" : mgn(t, 0), "tk", "middle");
    });
    rows.forEach(function (r, i) {
      var y = 26 + i * 23;
      s += txt(L - 10, y + 4, r.label, "lb", "end");
      s += rect(Math.min(xs(0), xs(r.m)), y - 6, Math.abs(xs(r.m) - xs(0)), 12,
                sideCol(r.m), ' rx="2" opacity="0.85"');
      s += txt(xs(r.m) + (r.m < 0 ? -8 : 8), y + 4, mgn(r.m), "vl", r.m < 0 ? "end" : "start");
    });
    s += "</svg>";
    return card("tx-est", "Chapter 3 · slide 1 · where every estimate lands",
      "Where every estimate lands",
      "Fifteen estimates spanning eleven points and straddling zero. They do not "
      + "disagree randomly: nearly every one is the same arithmetic with a different "
      + "assumption about how far Hispanic voters move. Ten of the fifteen are on the "
      + "Democratic side, the median is D+1.29, and the two built from counted "
      + "ballots rather than assumptions \u2014 the primary regression and the "
      + "uniform swing off the 2024 Senate \u2014 sit on opposite sides of even.",
      s,
      "<b>The model&rsquo;s known bias.</b> The county model moved the whole non-white "
      + "bloc +12, Black voters included. They were already 91.1% Democratic in 2024, so "
      + "+12 there is not a claim anyone can defend; capping it costs Democrats 1.62 points "
      + "and turns D+0.65 into R+0.97. Both are plotted. Treat the friendlier one as the "
      + "optimistic end of its own range, not the centre.");
  }

  /* ===================================================== 5. the primary flipped */
  function primaryCard() {
    var rows = (D.prim || []).map(function (r) {
      return {y: +r.year, kind: r.kind, rp: num(r.r_primary), dp: num(r.d_primary),
              sh: num(r.d_share_primary), nov: num(r.november_margin_R)};
    }).filter(function (r) { return r.rp != null && r.dp != null; })
      .sort(function (a2, b2) { return a2.y - b2.y; });
    if (!rows.length) return "";
    rows.forEach(function (r) { r.tot = r.rp + r.dp; r.rsh = 100 - r.sh; });
    var W = 720, H = 320, L = 54, R = 46, T = 26, Bm = 58;
    var maxT = Math.max.apply(null, rows.map(function (r) { return r.tot; })) * 1.14;
    var ys = function (v) { return H - Bm - v / maxT * (H - Bm - T); };
    var step = (W - L - R) / rows.length, bw = step * 0.64;
    var s2 = svg(W, H, "Democratic and Republican share of the Texas primary by year");
    [0, 1, 2, 3, 4].forEach(function (m) {
      s2 += line(L, ys(m * 1e6), W - R, ys(m * 1e6), "gl")
         + txt(L - 8, ys(m * 1e6) + 4, m + "M", "tk", "end");
    });
    // the 50% line, drawn against each bar's own total so it reads against the stack
    rows.forEach(function (r, i) {
      var x = L + i * step + (step - bw) / 2;
      s2 += rect(x, ys(r.dp), bw, ys(0) - ys(r.dp), DC, ' rx="2"');
      s2 += rect(x, ys(r.tot), bw, ys(r.dp) - ys(r.tot), RC, ' rx="2"');
      var dh = ys(0) - ys(r.dp), rh = ys(r.dp) - ys(r.tot);
      if (dh > 15) s2 += txt(x + bw / 2, ys(0) - dh / 2 + 4, r.sh.toFixed(1) + "%",
                             "inb", "middle");
      if (rh > 15) s2 += txt(x + bw / 2, ys(r.dp) - rh / 2 + 4, r.rsh.toFixed(1) + "%",
                             "inb", "middle");
      s2 += txt(x + bw / 2, ys(r.tot) - 6, (r.tot / 1e6).toFixed(2) + "M", "tk", "middle");
      s2 += txt(x + bw / 2, H - Bm + 15, String(r.y),
                r.kind === "Midterm" ? "lbb" : "tk", "middle");
      s2 += txt(x + bw / 2, H - Bm + 28, r.kind === "Midterm" ? "mid" : "pres", "sub", "middle");
      if (r.nov != null)
        s2 += txt(x + bw / 2, H - Bm + 42, mgn(r.nov, 1), "tk", "middle");
    });
    s2 += txt(L, H - 6, "Blue = Democratic ballots, red = Republican; the two shares sum to "
              + "100. Bottom row is the November margin that followed.", "lgd");
    s2 += "</svg>";
    return card("tx-primary", "Chapter 1 \u00b7 what actually changed",
      "Democratic share of the Texas primary",
      "Texas runs an open primary \u2014 you declare at the poll and nothing binds you "
      + "before or after. In March 2026 Democratic turnout more than doubled from 2022, to "
      + "2,319,187, and the Democratic share crossed 50% in a midterm for the first time "
      + "in the modern era. Republicans had the contested Senate race and still lost the "
      + "share by 3.4 points.",
      s2,
      "This is the strongest single piece of evidence that the electorate changed, and the "
      + "one piece the demographic model does not use. It is also a certified count rather "
      + "than an inference, unlike almost everything else on this tab.");
  }

  /* The primary is the only certified count on this tab, so it is the only thing that
     can be regressed rather than assumed. This card does that and shows what the fit is
     worth, including the version of it that goes wrong. */
  function primaryFitCard() {
    var pts = (D.prim || []).map(function (r) {
      return {y: +r.year, kind: r.kind, x: num(r.d_share_primary), d: num(r.d_primary),
              m: r.november_margin_R === "" ? null : num(r.november_margin_R)};
    }).filter(function (r) { return r.x != null; }).sort(function (a, b) { return a.y - b.y; });
    // growth against the previous election OF THE SAME TYPE, which is the comparison the
    // midterm/presidential cycle makes meaningful
    var seen = {};
    pts.forEach(function (r) {
      if (seen[r.kind] != null && seen[r.kind] > 0) r.g = (r.d / seen[r.kind] - 1) * 100;
      seen[r.kind] = r.d;
    });
    var done = pts.filter(function (r) { return r.m != null; });
    var open2 = pts.filter(function (r) { return r.m == null; });
    var fits = (D.fit || []).map(function (r) {
      return {basis: r.basis, n: +r.n, a: num(r.a), b: num(r.b),
              r2: num(r.r_squared), sd: num(r.residual_sd),
              x0: num(r.x_min), x1: num(r.x_max), pred: num(r.pred), x26: num(r.x_2026)};
    });
    if (!done.length || !fits.length) return "";
    var all = fits.filter(function (q) { return q.basis === "D share of the primary"; })[0];
    var mid = fits.filter(function (q) { return /growth, midterms/.test(q.basis); })[0];
    var gro = fits.filter(function (q) { return /growth, all/.test(q.basis); })[0];
    var now = open2.length ? open2[0] : null;
    if (!now) return "";

    var W = 720, H = 330, L = 88, R = 92, T = 40, Bm = 54;
    var xlo = 26, xhi = 56, ylo = -8, yhi = 24;
    var xs = function (v) { return L + (v - xlo) / (xhi - xlo) * (W - L - R); };
    var ys = function (v) { return T + (v - ylo) / (yhi - ylo) * (H - Bm - T); };
    var s2 = svg(W, H, "Democratic share of the Texas primary against the November margin that followed");
    // axes, spelled out
    [-5, 0, 5, 10, 15, 20].forEach(function (v) {
      s2 += line(L, ys(v), W - R, ys(v), v === 0 ? "zl" : "gl")
         + txt(L - 10, ys(v) + 4, v === 0 ? "tied" : (v > 0 ? "R+" : "D+") + Math.abs(v),
               "tk", "end");
    });
    [30, 35, 40, 45, 50, 55].forEach(function (v) {
      s2 += txt(xs(v), H - Bm + 16, v + "%", "tk", "middle");
    });
    s2 += txt((L + W - R) / 2, H - 30,
              "how Democratic the PRIMARY was \u2192", "lgd", "middle");
    s2 += txt(14, T - 16, "how the NOVEMBER", "lgd")
       + txt(14, T - 4, "race finished \u2193", "lgd");
    // the fitted relationship, with its uncertainty
    var top = [], bot = [];
    for (var v = xlo; v <= xhi; v += 2) {
      top.push(xs(v) + "," + ys(all.a + all.b * v - all.sd));
      bot.unshift(xs(v) + "," + ys(all.a + all.b * v + all.sd));
    }
    s2 += '<polygon points="' + top.concat(bot).join(" ")
       + '" fill="currentColor" opacity="0.07"/>';
    s2 += '<line x1="' + xs(xlo) + '" y1="' + ys(all.a + all.b * xlo) + '" x2="' + xs(xhi)
       + '" y2="' + ys(all.a + all.b * xhi) + '" stroke="currentColor" stroke-width="2"/>';
    // every past cycle
    done.forEach(function (r) {
      var midt = r.kind === "Midterm";
      s2 += '<circle cx="' + xs(r.x) + '" cy="' + ys(r.m) + '" r="' + (midt ? 6 : 5)
         + '" fill="' + (midt ? "currentColor" : "none")
         + '" stroke="currentColor" stroke-width="1.6"/>';
      s2 += txt(xs(r.x), ys(r.m) - 12, String(r.y), "tk", "middle");
    });
    // 2026
    var pv = all.a + all.b * now.x;
    s2 += '<line x1="' + xs(now.x) + '" y1="' + T + '" x2="' + xs(now.x) + '" y2="'
       + (H - Bm) + '" stroke="' + RC + '" stroke-width="1.2" stroke-dasharray="3 3"/>';
    s2 += txt(xs(now.x), T - 8, "2026 primary: " + now.x.toFixed(1) + "%", "lbb", "middle");
    s2 += '<circle cx="' + xs(now.x) + '" cy="' + ys(pv) + '" r="7" fill="' + RC + '"/>';
    s2 += txt(W - R + 10, ys(pv) - 4, "so November", "tk");
    s2 += txt(W - R + 10, ys(pv) + 10, "lands near " + mgn(pv, 1), "lbb");
    s2 += txt(L, H - 8, "\u25cf midterm    \u25cb presidential", "lgd");
    s2 += "</svg>";

    // Second panel: the same question asked of GROWTH rather than share, because share
    // cannot see that Democratic primary votes more than doubled. This is the better
    // predictor of the two and it is the one that moves the answer, so it gets drawn
    // rather than left in a table.
    var gpts = pts.filter(function (r) { return r.g != null; });
    var gdone = gpts.filter(function (r) { return r.m != null; });
    var s3 = "";
    if (gro && gdone.length) {
      var W2 = 720, H3 = 280, L2 = 88, R2 = 92, T2 = 34, B2 = 54;
      var gxlo = -60, gxhi = 130, gylo = -8, gyhi = 24;
      var gx = function (v) { return L2 + (v - gxlo) / (gxhi - gxlo) * (W2 - L2 - R2); };
      var gy = function (v) { return T2 + (v - gylo) / (gyhi - gylo) * (H3 - B2 - T2); };
      s3 = svg(W2, H3, "Democratic primary growth against the November margin that followed");
      [-5, 0, 5, 10, 15, 20].forEach(function (v) {
        s3 += line(L2, gy(v), W2 - R2, gy(v), v === 0 ? "zl" : "gl")
           + txt(L2 - 10, gy(v) + 4, v === 0 ? "tied" : (v > 0 ? "R+" : "D+") + Math.abs(v),
                 "tk", "end");
      });
      [-50, 0, 50, 100].forEach(function (v) {
        s3 += line(gx(v), T2 - 6, gx(v), H3 - B2, "gl")
           + txt(gx(v), H3 - B2 + 16, (v > 0 ? "+" : "") + v + "%", "tk", "middle");
      });
      s3 += txt((L2 + W2 - R2) / 2, H3 - 30,
                "change in DEMOCRATIC primary votes since the last like election \u2192",
                "lgd", "middle");
      s3 += '<line x1="' + gx(gxlo) + '" y1="' + gy(gro.a + gro.b * gxlo) + '" x2="'
         + gx(gxhi) + '" y2="' + gy(gro.a + gro.b * gxhi)
         + '" stroke="currentColor" stroke-width="2"/>';
      if (mid) {
        s3 += '<line x1="' + gx(gxlo) + '" y1="' + gy(mid.a + mid.b * gxlo) + '" x2="'
           + gx(gxhi) + '" y2="' + gy(mid.a + mid.b * gxhi) + '" stroke="' + DC
           + '" stroke-width="1.6" stroke-dasharray="5 4" opacity="0.8"/>';
      }
      gdone.forEach(function (r) {
        var midt = r.kind === "Midterm";
        s3 += '<circle cx="' + gx(r.g) + '" cy="' + gy(r.m) + '" r="' + (midt ? 6 : 5)
           + '" fill="' + (midt ? "currentColor" : "none")
           + '" stroke="currentColor" stroke-width="1.6"/>';
        s3 += txt(gx(r.g), gy(r.m) - 12, String(r.y), "tk", "middle");
      });
      s3 += '<line x1="' + gx(now.g) + '" y1="' + T2 + '" x2="' + gx(now.g) + '" y2="'
         + (H3 - B2) + '" stroke="' + RC + '" stroke-width="1.2" stroke-dasharray="3 3"/>';
      s3 += txt(gx(now.g), T2 - 8, "2026: +" + now.g.toFixed(0) + "%", "lbb", "middle");
      [[gro, "currentColor", "all cycles"], [mid, DC, "midterms only"]].forEach(function (q) {
        if (!q[0]) return;
        var pv2 = q[0].a + q[0].b * now.g;
        s3 += '<circle cx="' + gx(now.g) + '" cy="' + gy(pv2) + '" r="6" fill="' + q[1] + '"/>';
        // the two predictions are 1.7 points apart, which is ~12px here, so stack their
        // labels rather than letting them print over each other
        s3 += txt(W2 - R2 + 10, gy(pv2) + (q[1] === DC ? -5 : 11),
                  mgn(pv2, 1) + "  " + q[2], "tk");
      });
      s3 += "</svg>";
    }

    var CMP = (D.cmp || []);
    var cmpTbl = CMP.length ? ('<table class="txtbl" style="margin:12px 0"><thead><tr>'
      + "<th>What the primary showed</th><th>2018</th><th>2026</th><th></th>"
      + "</tr></thead><tbody>"
      + CMP.map(function (r) {
          var last = /Senate result/.test(r.input);
          return "<tr" + (last ? ' class="em"' : "") + "><td>" + esc(r.input)
            + '</td><td class="num dim">' + esc(r.y2018) + '</td><td class="num">'
            + esc(r.y2026) + '</td><td class="num dem">'
            + (r.stronger === "2026" ? "2026 higher" : r.stronger === "tie" ? "same" : "")
            + "</td></tr>";
        }).join("") + "</tbody></table>") : "";
    return card("tx-primfit", "Chapter 1 \u00b7 what the primary implies",
      "2026 is an outlier, and that is the finding",
      "<b>Do not read this as a line with a dot at the end.</b> 2026 sits outside the "
      + "range of every prior cycle on every primary measure there is \u2014 that is not a "
      + "problem for the analysis, it is the analysis. The useful question is not what a "
      + "line extrapolates to, but which past cycle 2026 most resembles and whether it "
      + "beats it. <b>The answer is 2018, and 2026 is stronger on every input.</b>",
      cmpTbl
      + "<p class=\"txnote\" style=\"border-top:none;padding-top:0\">"
      + "<b>2018 and 2026 sit in near-identical national environments</b> \u2014 the 2018 "
      + "result was D+8.6 and the 2026 generic ballot is D+8.5, a tenth of a point apart. "
      + "On every Texas primary input that can be measured, 2026 is ahead: more than twice "
      + "the Democratic primary votes, faster growth, a share 10.9 points higher. "
      + "<b>2018 produced R+2.57, the closest Texas had come since 1994.</b> So the "
      + "question is whether a matching national year with better primary indicators lands "
      + "better than R+2.57 \u2014 a comparison, which needs no extrapolation at all.</p>",
      "<b>The regressions are a check on that, not the argument.</b> Each dot below is a "
      + "past cycle; 2026 is the dashed line far to the right of all of them. Fitted three "
      + "ways they give:"
      + '<table class="txtbl" style="margin:10px 0"><thead><tr><th>What you regress on</th>'
      + "<th>Cycles</th><th>Explains</th><th>2026</th></tr></thead><tbody>"
      + fits.map(function (q) {
          return "<tr" + (q === gro ? ' class="em"' : "") + "><td>" + esc(q.basis)
            + '</td><td class="num">' + q.n + '</td><td class="num">'
            + (q.r2 * 100).toFixed(0) + '%</td><td class="num '
            + (q.pred < 0 ? "dem" : "rep") + '">' + mgn(q.pred, 2) + "</td></tr>";
        }).join("") + "</tbody></table>"
      + s3 + s2
      + "<b>All three straddle even, against a state whose last three cycles average "
      + "R+10.09 and whose last four midterms average R+11.66.</b> They disagree by three "
      + "points, which is the honest uncertainty, and they agree on the thing that matters: "
      + "nothing in this primary looks like a normal Texas midterm."
      + "<br><br><b>What would break the comparison.</b> 2018 had Beto O\u2019Rourke and a "
      + "first-term backlash; 2026 has a Republican nominee under indictment and a "
      + "different opponent. The primary inputs match and improve, the candidates do not "
      + "transfer, and Democrats won the 2020 primary too \u2014 2,094,428 to 2,017,167 "
      + "\u2014 then lost that November by 5.58.");
  }

  function baselineCard() {
    var rows = (D.base || []).map(function (r) {
      return {label: r.baseline, year: r.year, then: num(r.margin_then_R),
              swing: num(r.swing_to_2026), now: num(r.implied_2026_R)};
    }).filter(function (r) { return r.then != null && r.now != null; })
      .sort(function (a, b) { return a.now - b.now; });
    if (!rows.length) return "";
    var W = 720, H = 36 + rows.length * 26, L = 250, R = 54;
    var lo = -12, hi = 16;
    var xs = function (v) { return L + (v - lo) / (hi - lo) * (W - L - R); };
    var s = svg(W, H, "Seven Texas baselines carried to 2026 by each year's own national swing");
    [-10, -5, 0, 5, 10, 15].forEach(function (t) {
      s += line(xs(t), 16, xs(t), H - 14, t === 0 ? "zl" : "gl")
         + txt(xs(t), 12, t === 0 ? "even" : mgn(t, 0), "tk", "middle");
    });
    rows.forEach(function (r, i) {
      var y = 28 + i * 26;
      s += txt(L - 10, y + 4, r.label, "lb", "end");
      s += line(xs(r.then), y, xs(r.now), y, "cn");
      s += '<circle cx="' + xs(r.then) + '" cy="' + y + '" r="4.5" fill="none" '
         + 'stroke="currentColor" stroke-width="1.5"/>';
      s += '<circle cx="' + xs(r.now) + '" cy="' + y + '" r="5" fill="' + sideCol(r.now) + '"/>';
      s += txt(xs(r.now) + (r.now < 0 ? -9 : 9), y + 4, mgn(r.now, 1), "vl",
               r.now < 0 ? "end" : "start");
    });
    s += "</svg>";
    return card("tx-base", "Chapter 3 · slide 3 · why the methods disagree",
      "Seven starting points, each with its own swing",
      "Take any past Texas result, add the national swing from <i>that</i> year to this "
      + "year&rsquo;s generic ballot of <b>D+8.5</b>, and see where Texas lands. The "
      + "generic ballot is the median of seven aggregators the night before, spanning "
      + "D+7.0 to D+10.8, and every point of it moves every baseline here one for one. "
      + "2018 was already a strong "
      + "Democratic national year, so it cannot borrow the 2024 swing. Hollow dot is the "
      + "result then, filled dot is where it implies 2026 lands.",
      s,
      "Which year you start from moves the answer by more than any demographic lever on "
      + "this tab. Starting from the 2024 Senate is the harshest available choice, and it "
      + "is the one the county model makes.");
  }

  /* ================================================== 7. the Paxton drag */
  function paxtonCard() {
    var rows = (D.pax || []).map(function (r) {
      return {p: r.pollster, n: num(r.n), sen: num(r.senate_d_margin),
              gov: num(r.governor_d_margin), drag: num(r.paxton_drag)};
    }).filter(function (r) { return r.drag != null; });
    if (!rows.length) return "";
    var mean = rows.reduce(function (a, r) { return a + r.drag; }, 0) / rows.length;
    var body = rows.map(function (r) {
      return "<tr><td>" + esc(r.p) + (r.n ? ' <span class="dim">n=' + n0(r.n) + "</span>" : "")
        + '</td><td class="num">' + (r.sen > 0 ? "D+" : "R+") + Math.abs(r.sen).toFixed(1)
        + '</td><td class="num">' + (r.gov > 0 ? "D+" : "R+") + Math.abs(r.gov).toFixed(1)
        + '</td><td class="num dem">+' + r.drag.toFixed(2) + "</td></tr>";
    }).join("");
    return card("tx-paxton", "Chapter 3 · slide 2 · the part that is not the electorate",
      "Senate against governor, same pollster",
      "Four pollsters asked about both races in the same field period with the same "
      + "sample, so house effects cancel in the difference. What is left is the candidate.",
      '<table class="txtbl"><thead><tr><th>Pollster</th><th>Senate</th><th>Governor</th>'
      + "<th>Paxton drag</th></tr></thead><tbody>" + body
      + '<tr class="em"><td>Mean</td><td class="num">—</td><td class="num">—</td>'
      + '<td class="num dem">+' + mean.toFixed(2) + "</td></tr></tbody></table>",
      "This is the part of the Democratic case that is not about the electorate at all, "
      + "which also means none of it transfers to the governor&rsquo;s race or down-ballot.");
  }

  /* ========================================== 8. the two sensitivity grids */
  function gridCard(id, kicker, title, hint, rows, xKey, yKey, vKey, xLab, yLab, note, yFmt) {
    if (!rows || !rows.length) return "";
    var xs = [], ys = [];
    rows.forEach(function (r) {
      var x = num(r[xKey]), y = num(r[yKey]);
      if (xs.indexOf(x) < 0) xs.push(x);
      if (ys.indexOf(y) < 0) ys.push(y);
    });
    xs.sort(function (a, b) { return a - b; });
    ys.sort(function (a, b) { return b - a; });
    var mx = Math.max.apply(null, rows.map(function (r) { return Math.abs(num(r[vKey])); })) || 1;
    // AX is the gutter the rotated y-axis label sits in, to the left of the row
    // labels. Without it the label was parked at the bottom-left corner, reading as
    // a footnote rather than as the axis it names.
    var AX = 22;
    var cw = 58, ch = 34, L = 92 + AX, T = 44,
        W = L + xs.length * cw + 12, H = T + ys.length * ch + 22;
    var s = svg(W, H, title);
    s += txt(L, 16, xLab, "lgd");
    xs.forEach(function (x, i) {
      s += txt(L + i * cw + cw / 2, T - 9, (x > 0 && xKey !== "ind_break_D" ? "+" : "") + x
               + (xKey === "ind_break_D" ? "%" : ""), "tk", "middle");
    });
    ys.forEach(function (y, j) {
      var lab = yFmt ? yFmt(y) : ((y > 0 ? "+" : "") + y);
      s += txt(L - 8, T + j * ch + ch / 2 + 4, lab, "lb", "end");
    });
    rows.forEach(function (r) {
      var x = xs.indexOf(num(r[xKey])), y = ys.indexOf(num(r[yKey])), v = num(r[vKey]);
      if (x < 0 || y < 0 || v == null) return;
      var t = Math.min(1, Math.abs(v) / mx * 1.5);
      var fill = v < 0 ? DC : RC;
      s += rect(L + x * cw, T + y * ch, cw - 2, ch - 2, fill,
                ' rx="3" opacity="' + (0.12 + t * 0.78).toFixed(3) + '"');
      s += txt(L + x * cw + (cw - 2) / 2, T + y * ch + ch / 2 + 4, mgn(v, 1),
               t > 0.55 ? "cellw" : "cell", "middle");
    });
    // centred on the grid itself, not on the whole svg, so it lines up with the rows
    var ymid = T + (ys.length * ch) / 2;
    s += '<text x="' + (AX - 8) + '" y="' + ymid + '" text-anchor="middle" '
       + 'class="lgd" transform="rotate(-90 ' + (AX - 8) + ' ' + ymid + ')">'
       + esc(yLab) + "</text>";
    s += "</svg>";
    return card(id, kicker, title, hint, '<div class="scroll">' + s + "</div>", note);
  }

  /* ================================================= 9. how far each group moved */
  function ethCard() {
    var rows = (D.eth || []).map(function (r) {
      return {g: r.group, a: num(r.margin_2024_R), b: num(r.margin_2026_est_R),
              sh: num(r.shift_2026_est), d24: num(r.d_share_2024),
              d26: num(r.d_share_2026_est), why: r.basis};
    }).filter(function (r) { return r.a != null && r.b != null; });
    if (!rows.length) return "";
    var order = ["Hispanic", "Asian", "Black", "White"];
    rows.sort(function (p, q) { return order.indexOf(p.g) - order.indexOf(q.g); });
    var W = 720, H = 40 + rows.length * 34, L = 110, R = 62;
    var lo = -95, hi = 72;
    var xs = function (v) { return L + (v - lo) / (hi - lo) * (W - L - R); };
    var s = svg(W, H, "Each group's 2024 measured margin and its 2026 estimate");
    s += line(xs(0), 20, xs(0), H - 20, "zl") + txt(xs(0), 14, "even", "tk", "middle");
    s += txt(L, 14, "more Democratic", "lgd")
       + txt(W - R, 14, "more Republican", "lgd", "end");
    rows.forEach(function (r, i) {
      var y = 34 + i * 34, capped = r.g === "Black";
      s += txt(L - 10, y, r.g, "lb", "end");
      s += txt(L - 10, y + 12, capped ? "at the ceiling"
               : (Math.abs(r.sh) < 0.005 ? "nothing measures 2026"
                  : r.d24.toFixed(0) + "% → " + r.d26.toFixed(0) + "% D"), "sub", "end");
      // Direction is no longer always Democratic: anchoring Asian voters at the generic
      // ballot moves them TOWARD Republicans, because D+8.5 sits below the D+15.31 they
      // already gave in 2024. Colour the end dot by which way the row actually travels
      // and sign the label, instead of hardcoding a blue dot and a "+".
      var toD = r.sh > 0, none = Math.abs(r.sh) < 0.005;
      if (!none) s += line(xs(r.a), y, xs(r.b), y, "cn");
      s += '<circle cx="' + xs(r.a) + '" cy="' + y + '" r="4.5" fill="none" '
         + 'stroke="currentColor" stroke-width="1.5"/>';
      // A row with no 2026 estimate keeps only its measured dot. A filled dot drawn on
      // top of the hollow one would assert a 2026 position that nothing supports.
      if (!none) {
        s += '<circle cx="' + xs(r.b) + '" cy="' + y + '" r="5" fill="' + (toD ? DC : RC) + '"'
           + (capped ? ' opacity="0.55"' : "") + "/>";
      }
      s += txt(Math.min(xs(r.a), xs(r.b)) - 9, y + 4,
               none ? "no estimate" : (toD ? "+" : "−") + Math.abs(r.sh).toFixed(1),
               (capped || none) ? "sub" : "vl", "end");
    });
    s += "</svg>";
    return card("tx-eth", "Section 5 · slide 2 · the demographic doing the moving",
      "Where each demographic is, and where the model needs it",
      "Hollow dot is 2024 measured — counted ballots in precincts overwhelmingly one "
      + "demographic by voting-age population, not a poll. Filled dot is the 2026 "
      + "estimate, blue where the demographic moves toward Democrats and red where it "
      + "moves away.",
      s,
      "<b>Asian voters are held where they were last measured.</b> An earlier version anchored them to the October generic ballot, which was wrong: the generic ballot is a national all-voter number and sits well to the right of where Asian voters actually vote, so anchoring to it imported a claim rather than removing one. Nothing in 2026 measures this group in Texas, so the row stops at its 2024 position and says so. The historical trend is real and does point right — they moved 8.95 points toward Republicans between 2018 and 2024 — but whether that continued is unknown, and at 4.57% of the electorate the whole plausible range is under nine tenths of a point statewide."
      + "<br><br>" + "<b>The row that does not work is Black voters.</b> 2024 already sits at 91.1% "
      + "Democratic, so the model&rsquo;s +12 for the whole non-white bloc cannot come from "
      + "there — it has to be carried by Hispanic voters almost alone. That is the "
      + "weakest joint in the model, and this is the chart where it shows.");
  }

  /* ============================== 10. why one Hispanic number is not enough + volatility */
  /* Tarrant is the only Texas county that publishes its early electorate in enough
     detail to see 2026 rather than infer it: precinct lean against 2022, and every
     voter's most recent primary. It is also the state's bellwether. */
  /* Tarrant publishes who is voting, which no other Texas county does. The precinct
     leans were the weakest thing in it - a primary-history proxy, not a vote - so the
     card is built on the composition tables instead. */
  /* The two final polls' own crosstabs, read off the released PDFs. This is the only
     place on the tab where two independent instruments measure the SAME groups, so the
     places they agree and disagree are worth more than either topline. */
  /* The 2024 Texas exit poll. It is the only measurement on this tab of the SAME
     groups the model reasons about, in the SAME state, in a race whose answer is known -
     which makes it the right baseline to test the model's starting points against. */
  function exitCard() {
    var E = (D.exit || []).map(function (r) {
      return {c: r.category, g: r.group, t: num(r.trump), h: num(r.harris),
              s: num(r.share_of_electorate), m: num(r.margin_R)};
    }).filter(function (r) { return r.m != null; });
    if (!E.length) return "";
    var W = 720, H2 = 44 + E.length * 23, L = 150, R2 = 104, T = 32;
    var lo = -95, hi = 95;
    var xs = function (v) { return L + (v - lo) / (hi - lo) * (W - L - R2); };
    var s2 = svg(W, H2, "2024 Texas exit poll by group");
    s2 += line(xs(0), T - 10, xs(0), H2 - 14, "zl");
    s2 += txt(xs(0), T - 16, "even", "tk", "middle");
    s2 += txt(L, T - 16, "Harris", "lgd") + txt(W - R2, T - 16, "Trump", "lgd", "end");
    var cur = null;
    E.forEach(function (r, i) {
      var y = T + 6 + i * 23;
      if (r.c !== cur) { cur = r.c; s2 += line(8, y - 12, W - 8, y - 12, "gl"); }
      s2 += txt(L - 10, y + 4, r.g, "lb", "end");
      s2 += rect(Math.min(xs(0), xs(r.m)), y - 5, Math.abs(xs(r.m) - xs(0)), 11,
                 sideCol(r.m), ' rx="2" opacity="0.85"');
      s2 += txt(W - R2 + 8, y + 4, mgn(r.m, 0) + "   " + r.s + "% of voters", "tk");
    });
    s2 += "</svg>";
    var lat = E.filter(function (r) { return r.g === "Latino"; })[0];
    var ind = E.filter(function (r) { return r.g === "Independents"; })[0];
    var lm = E.filter(function (r) { return r.g === "Latino men"; })[0];
    var lw = E.filter(function (r) { return r.g === "Latina women"; })[0];
    return card("tx-exit", "Chapter 3 \u00b7 slide 6 \u00b7 the 2024 baseline, measured",
      "What the 2024 Texas exit poll actually found",
      "<b>Source: the 2024 Texas presidential exit poll.</b> Every assumption on this tab "
      + "is a claim about how some group moves from 2024. This is the only measurement of "
      + "where those same groups actually <i>were</i> in 2024, in this state, in a race "
      + "whose answer is known. Bars are the margin; the figure beside each is that "
      + "group&rsquo;s share of the electorate.",
      s2,
      "<b>It contradicts the model\u2019s Hispanic starting point.</b> The exit poll has "
      + "Latinos going Trump " + lat.t + "\u2013" + lat.h + ", <b>" + mgn(lat.m, 0)
      + "</b>, at " + lat.s + "% of the electorate. The county model\u2019s displayed 2024 "
      + "Hispanic baseline is D+17.85, read off precincts that are 90%+ Hispanic. Those "
      + "two cannot both describe the same voters, and they are nearly 28 points apart. "
      + "Neither is authoritative: 90%-Hispanic precincts capture only about a sixth of "
      + "Texas Hispanics and skew to the border and El Paso, while exit polls are the "
      + "least reliable instrument there is for Latino subsamples. But if the exit poll is "
      + "nearer the truth, the model is starting the largest swing group almost 28 points "
      + "too far left."
      + "<br><br><b>And the gender split inside it is larger than the group gap.</b> Latino "
      + "men went " + mgn(lm.m, 0) + " while Latina women went " + mgn(lw.m, 0)
      + " \u2014 47 points apart, in the same ethnicity, in the same election. Any single "
      + "Hispanic number on this tab is averaging across that."
      + "<br><br><b>It also repairs the bloc grid.</b> Independents were <b>" + ind.s
      + "% of the Texas electorate</b> and split " + ind.t + "\u2013" + ind.h + ", "
      + mgn(ind.m, 0) + ". The grid in Section 5 had been built on 30% from a poll\u2019s "
      + "self-identification; it now uses this measured 36%, which lengthens the lever "
      + "again \u2014 a ten-point move among independents is worth 3.6 points of statewide "
      + "margin, not 3.0.");
  }

  function crosstabCard() {
    var R = (D.xtab || []).map(function (r) {
      return {g: r.group, ym: r.yougov_margin_R === "" ? null : num(r.yougov_margin_R),
              am: num(r.atlas_margin_R), ad: num(r.atlas_d), ar: num(r.atlas_r)};
    }).filter(function (r) { return r.am != null; });
    if (!R.length) return "";
    var W = 720, H2 = 48 + R.length * 25, L = 162, R2 = 96, T = 34;
    var lo = -95, hi = 95;
    var xs = function (v) { return L + (v - lo) / (hi - lo) * (W - L - R2); };
    var s2 = svg(W, H2, "Texas Senate crosstabs from the two final polls");
    s2 += line(xs(0), T - 12, xs(0), H2 - 14, "zl");
    s2 += txt(xs(0), T - 18, "even", "tk", "middle");
    s2 += txt(L, T - 18, "Talarico", "lgd") + txt(W - R2, T - 18, "Paxton", "lgd", "end");
    R.forEach(function (r, i) {
      var y = T + 6 + i * 25;
      s2 += txt(L - 10, y + 4, r.g, r.g === "Total" ? "lbb" : "lb", "end");
      if (r.ym != null) {
        s2 += line(xs(r.ym), y, xs(r.am), y, "cn");
        s2 += '<circle cx="' + xs(r.ym) + '" cy="' + y + '" r="4" fill="none" '
           + 'stroke="currentColor" stroke-width="1.5"/>';
      }
      s2 += '<circle cx="' + xs(r.am) + '" cy="' + y + '" r="5" fill="'
         + sideCol(r.am) + '"/>';
      s2 += txt(W - R2 + 8, y + 4,
                (r.ym != null ? mgn(r.ym, 0) + " / " : "") + mgn(r.am, 0), "tk");
    });
    s2 += txt(L, 16, "\u25cb YouGov, 2,141 likely voters, 26\u201329 Oct", "lgd")
       + txt(L + 250, 16, "\u25cf AtlasIntel, 1,678, 28 Oct\u20131 Nov", "lgd");
    s2 += "</svg>";
    var ind = R.filter(function (r) { return r.g === "Independents"; })[0];
    var nv = R.filter(function (r) { return /NOT vote/.test(r.g); })[0];
    var hisp = R.filter(function (r) { return r.g === "Hispanic"; })[0];
    var twoWay = ind ? (ind.ad / (ind.ad + ind.ar) * 100) : null;
    return card("tx-xtab", "Chapter 3 \u00b7 slide 5 \u00b7 what the crosstabs say",
      "The two final polls, group by group",
      "<b>Sources: the released YouGov and AtlasIntel toppers.</b> Hollow dot is YouGov "
      + "(2,141 likely voters, 26\u201329 October), filled dot is AtlasIntel (1,678, "
      + "28 October\u20131 November). Where a group has only a filled dot, only AtlasIntel "
      + "published it. This is the one place on this tab where two independent instruments "
      + "measure the same groups.",
      s2,
      "<b>The two numbers that answer open questions on this tab.</b> First, "
      + "<b>independents: AtlasIntel has them " + ind.ad.toFixed(1) + "\u2013"
      + ind.ar.toFixed(1) + " for Talarico</b>, which is "
      + twoWay.toFixed(1) + "% two-way. The bloc grid later in this deck asks what "
      + "independents would have to do at AtlasIntel\u2019s own bloc sizes, and the answer "
      + "is 69.2%. Its own crosstab lands within half a point of its own requirement."
      + "<br><br>Second, <b>people who did not vote in 2024 break "
      + nv.ad.toFixed(1) + "\u2013" + nv.ar.toFixed(1) + " for Talarico.</b> That is the "
      + "new-voter question measured directly rather than inferred from primary ballots, "
      + "and it is more lopsided than Morris\u2019s five-to-one finding in Harris County."
      + "<br><br><b>Where they agree and where they do not is the useful part.</b> The two "
      + "polls land within a tenth of a point on Black voters (D+69 and D+68.6), on 30\u201344 "
      + "(D+22 and D+22.1) and on 45\u201364 (D+2 and D+2.0). They are 30 points apart on "
      + "18\u201329, 17 on women, 14 on men, and <b>11.5 apart on Hispanic voters "
      + "\u2014 D+28 against D+16.5</b>. That last one is the number this whole model turns "
      + "on: the county model assumes Hispanic voters land at D+29.85, which YouGov "
      + "supports and AtlasIntel does not."
      + "<br><br><b>One caution on the poll \u201cwhite\u201d and \u201cHispanic\u201d "
      + "rows.</b> They are self-identified respondents statewide. The precinct figures "
      + "elsewhere on this tab are counted ballots in precincts that are 90% one group, "
      + "which is a different and more geographically concentrated population. The two are "
      + "not interchangeable and the gap between them is composition, not disagreement.");
  }

  function tarrantCard() {
    var HD = (D.tarrhd || []).map(function (r) {
      return {g: r.group, reg: num(r.share_of_registered), vot: num(r.share_of_voters),
              n: num(r.voters), gap: num(r.gap)};
    }).filter(function (r) { return r.vot != null; });
    var AG = (D.tage || []).map(function (r) {
      return {a: r.age, n: num(r.voted), sv: num(r.share_of_voters),
              sa: num(r.share_of_active), t: num(r.turnout_so_far), gap: num(r.gap)};
    }).filter(function (r) { return r.sv != null; });
    var G = (D.tgrp || []).map(function (r) {
      return {g: r.group, n: num(r.voted), sv: num(r.share_of_voters),
              sa: num(r.share_of_active), t: num(r.turnout_so_far)};
    }).filter(function (r) { return r.sv != null; });
    if (!AG.length && !HD.length) return "";

    // One chart: who is turning out ahead of their registration, and who behind.
    var rows = AG.map(function (r) { return {lab: r.a + "", gap: r.gap, t: r.t, kind: "age"}; })
      .concat(G.map(function (r) {
        return {lab: r.g.replace("Asian or Pacific Islander", "Asian / PI")
                      .replace("Other or multiracial", "Other"),
                gap: r.sv - r.sa, t: r.t, kind: "race"};
      }));
    var W = 720, H2 = 44 + rows.length * 26, L = 132, R = 118, T = 32;
    var mx = 7;
    var xs = function (v) { return L + (v + mx) / (2 * mx) * (W - L - R); };
    var s2 = svg(W, H2, "Tarrant County: which groups are turning out ahead of their registration");
    s2 += line(xs(0), T - 10, xs(0), H2 - 14, "zl");
    s2 += txt(xs(0), T - 16, "at their share", "tk", "middle");
    s2 += txt(L, T - 16, "turning out behind", "lgd");
    s2 += txt(W - R, T - 16, "ahead", "lgd", "end");
    rows.forEach(function (r, i) {
      var y = T + 6 + i * 26;
      if (i > 0 && rows[i - 1].kind !== r.kind) {
        s2 += line(8, y - 13, W - 8, y - 13, "gl");
      }
      s2 += txt(L - 12, y + 4, r.lab, "lb", "end");
      s2 += rect(Math.min(xs(0), xs(r.gap)), y - 6, Math.abs(xs(r.gap) - xs(0)), 13,
                 r.gap >= 0 ? RC : DC, ' rx="2" opacity="0.8"');
      s2 += txt(xs(r.gap) + (r.gap >= 0 ? 7 : -7), y + 4,
                (r.gap > 0 ? "+" : "") + r.gap.toFixed(0), "vl",
                r.gap >= 0 ? "start" : "end");
      s2 += txt(W - R + 44, y + 4, r.t + "% turnout", "tk");
    });
    s2 += "</svg>";

    var tbl = function (head, body) {
      return '<div class="scroll"><table class="txtbl"><thead><tr>' + head
        + "</tr></thead><tbody>" + body + "</tbody></table></div>";
    };
    var histTbl = HD.length ? tbl(
      "<th>Who these voters are</th><th>Voters</th><th>Share of voters</th>"
      + "<th>Share of all registered</th>",
      HD.map(function (r) {
        return "<tr><td>" + esc(r.g) + '</td><td class="num">' + n0(r.n)
          + '</td><td class="num">' + r.vot + '%</td><td class="num dim">' + r.reg
          + "%</td></tr>";
      }).join("")
      + '<tr class="em"><td>Did not vote in the 2022 midterm</td><td class="num">'
      + n0(HD.reduce(function (a2, r) { return a2 + r.n; }, 0)) + '</td><td class="num">'
      + HD.reduce(function (a2, r) { return a2 + r.vot; }, 0).toFixed(1)
      + '%</td><td class="num dim">'
      + HD.reduce(function (a2, r) { return a2 + r.reg; }, 0).toFixed(1) + "%</td></tr>") : "";

    return card("tx-tarrant", "Chapter 3 \u00b7 slide 4 \u00b7 who is actually voting",
      "Tarrant County, the only place we can see the 2026 electorate",
      "<b>Source: the Tarrant County early-vote file, through Friday 30 October.</b> "
      + "588,653 early and mail voters matched to the voter file by state voter ID. No "
      + "other Texas county publishes who is voting, so every composition assumption "
      + "elsewhere on this tab is an inference and this one is a count.",
      histTbl + s2,
      "<b>Nearly half of this electorate did not vote in the 2022 midterm.</b> The file "
      + "opens with it: <i>\u201c13.1% sat out the 2022 midterm, then voted in 2024, and "
      + "17.9% registered since 2022\u201d</i>, and a further 17.8% were on the rolls in "
      + "2022 and did not vote. Together that is 48.8% \u2014 about 287,000 people in one "
      + "county who sat out the last midterm and have already voted in this one."
      + "<br><br><b>But the composition cuts the other way, on two measures.</b> The file "
      + "compares each group\u2019s share of voters with its share of active voters, on "
      + "the rule that <i>\u201ca group whose share of voters is bigger is turning out "
      + "ahead of the rest\u201d</i>. By age the electorate is older, not younger: under "
      + "35s are 19% of voters against 30% of active voters, 18\u201324 turnout is 29% "
      + "against 67% for 65\u201374, and over-65s outnumber under-35s 1.53 to one. By "
      + "race it is whiter: white voters 58% of voters against 53% of active, Hispanic "
      + "voters 18% against 21%, at 39% turnout against 52%."
      + "<br><br><b>That is the honest shape of it.</b> A large infusion of people who "
      + "skipped 2022, arriving inside an electorate that is skewing older and whiter "
      + "than its own registration base. Which of those two facts matters more is exactly "
      + "the disagreement this chapter is about, and one county cannot settle it."
      + "<br><br><b>The file declines to forecast, twice.</b> <i>\u201cA primary ballot is "
      + "not a November vote, and the large 2026 Democratic primary makes every 2026 group "
      + "look more Democratic on this measure.\u201d</i> And: <i>\u201cIt is not a "
      + "forecast, and it is not how anyone actually voted: ballots are secret.\u201d</i>");
  }

  /* The Morris gradient is the single biggest external input to this model: it is what
     reweights precincts inside every county. It has never been shown on its own, and the
     one public test of it is in here too. */
  /* Morris's own chart, not my reconstruction of it: turnout by how reliable a voter
     is, split by party, in the one Texas county that publishes individual voting
     histories. The gradient scatter that used to be here was my paraphrase. */
  function morrisCard() {
    var E = (D.meng || []).map(function (r) {
      return {src: r.source, meas: r.measure, tier: r.tier,
              d: num(r.dem), r: num(r.rep), gap: num(r.gap)};
    }).filter(function (r) { return r.d != null; });
    var HC = (D.mhar || []).map(function (r) {
      return {m: r.metric, a: r.y2022 === "" ? null : num(r.y2022), b: num(r.y2026)};
    }).filter(function (r) { return r.b != null; });
    if (!E.length) return "";

    var W = 720, H2 = 58 + E.length * 54, L = 196, R = 70, T = 40;
    var xs = function (v) { return L + v / 100 * (W - L - R); };
    var s2 = svg(W, H2, "Turnout by level of past engagement, Democrats against Republicans");
    [0, 25, 50, 75, 100].forEach(function (v) {
      s2 += line(xs(v), T - 12, xs(v), H2 - 24, "gl")
         + txt(xs(v), T - 18, v + "%", "tk", "middle");
    });
    E.forEach(function (r, i) {
      var y = T + 4 + i * 54;
      if (i > 0 && E[i - 1].src !== r.src) s2 += line(8, y - 16, W - 8, y - 16, "gl");
      var words = r.tier.split(" ");
      var l1 = [], l2 = [];
      words.forEach(function (w) { (l1.join(" ").length < 26 ? l1 : l2).push(w); });
      s2 += txt(L - 12, y + 6, l1.join(" "), "lb", "end");
      if (l2.length) s2 += txt(L - 12, y + 19, l2.join(" "), "sub", "end");
      s2 += rect(xs(0), y - 2, xs(r.d) - xs(0), 11, DC, ' rx="2"');
      s2 += rect(xs(0), y + 12, xs(r.r) - xs(0), 11, RC, ' rx="2"');
      s2 += txt(xs(r.d) + 7, y + 7, r.d + "%", "vl");
      s2 += txt(xs(r.r) + 7, y + 21, r.r + "%", "vl");
      s2 += txt(W - R + 8, y + 14, "D+" + r.gap, "lbb");
    });
    s2 += txt(L, 16, "\u25a0 Democrats", "lgd") + txt(L + 86, 16, "\u25a0 Republicans", "lgd");
    s2 += txt(W - R + 8, 16, "gap", "lgd");
    s2 += txt(L, H2 - 8, E[0].meas + "  (top pair)   \u00b7   " + E[E.length - 1].meas
              + "  (bottom pair)", "lgd");
    s2 += "</svg>";

    var hc = HC.length ? ('<table class="txtbl" style="margin-top:14px"><thead><tr>'
      + "<th>Harris County early vote</th><th>2022</th><th>2026</th></tr></thead><tbody>"
      + HC.map(function (r) {
          return "<tr><td>" + esc(r.m) + '</td><td class="num dim">'
            + (r.a == null ? "\u2014" : r.a + "%") + '</td><td class="num">' + r.b
            + "%</td></tr>";
        }).join("") + "</tbody></table>") : "";

    return card("tx-morris", "Chapter 4 \u00b7 slide 1 \u00b7 the engagement gap",
      "What Morris found in Harris County",
      "<b>Source: G.&nbsp;Elliott Morris, Strength In Numbers.</b> Harris County publishes "
      + "individual voting histories, which no other large Texas county does, so this is "
      + "the only place anyone can measure <i>which kind</i> of voter is turning out "
      + "rather than just how many. The top pair is the share of 2024 early voters who "
      + "have voted again this year, by how reliably they have voted before. The bottom "
      + "pair is two polls asking the same people whether they will definitely vote.",
      s2 + hc,
      "<b>The gap widens as the voters get less reliable, and that is the finding.</b> In "
      + "Morris&rsquo;s words: <i>\u201cAmong Houstonians who regularly turn out for "
      + "elections, Democrats (91% turnout) are out-voting Republicans (86%) by a modest "
      + "but still sizable 5 points. But among irregular voters \u2014 those who skipped "
      + "the 2022 midterm but voted early in 2024 \u2014 Republicans (57%) have fallen 13 "
      + "points behind Democrats (70%).\u201d</i> The polls say the same thing "
      + "independently: a 6-point gap among regular 2024 voters, 17 among irregular ones. "
      + "<i>\u201cIrregular Trump voters are the least sure of any 2024 voters that "
      + "they\u2019ll turn out.\u201d</i>"
      + "<br><br><b>New voters are the sharpest version of it.</b> <i>\u201cAmong those "
      + "who voted in the primary this March, Democrats outnumber Republicans more than 5 "
      + "to 1. In 2022, they were split about evenly.\u201d</i>"
      + "<br><br><b>And the composition moved with it.</b> Hispanic early voters in Harris "
      + "doubled since 2022, from 18% of the early vote to 25%, against 43% growth for "
      + "Black voters and 24% for white. The precinct gradient is the same fact seen "
      + "geographically: <i>\u201cIn precincts where at least three-quarters of registered "
      + "voters have Spanish surnames, early ballots nearly doubled (+97%), while in "
      + "precincts where fewer than 1 in 10 do, they rose just 27%\u201d</i> \u2014 "
      + "against a county average of 44%. It is partly a bounce-back: in 2022 only 36% of "
      + "Harris\u2019s 2020 Hispanic early voters voted early again against 51% of white "
      + "ones, and this year it is 62% against 66%."
      + "<br><br><b>Two limits.</b> Texas voter records carry no race, so Morris estimates "
      + "it from surname and precinct. And this is one county \u2014 the model applies its "
      + "gradient to all 254.");
  }

  function precinctCard() {
    var rows = (D.prec || []).filter(function (r) { return num(r.margin_R) != null; });
    if (!rows.length) return "";
    // The file carries TWO precinct definitions - 90%+ Hispanic and 90%+ non-white -
    // and an earlier version of this table printed only `where` and `race`, so
    // "Border / South Texas, 2024 Senate" appeared twice with nothing to tell the two
    // apart. Group by definition first, and say what each one is.
    var defs = [];
    rows.forEach(function (r) { if (defs.indexOf(r.group) < 0) defs.push(r.group); });
    var body = defs.map(function (dfn) {
      var band = rows.filter(function (r) { return r.group === dfn; });
      var head = '<tr class="grp"><td colspan="4">' + esc(dfn)
        + " \u2014 precincts that are " + esc(dfn.replace(/ 90%\+$/, ""))
        + " by at least 90% of voting-age population</td></tr>";
      var byWhere = {};
      band.forEach(function (r) { (byWhere[r.where] = byWhere[r.where] || []).push(r); });
      return head + Object.keys(byWhere).map(function (w) {
        return byWhere[w].map(function (r, i) {
          var m = num(r.margin_R);
          return "<tr>"
            + (i === 0 ? '<td rowspan="' + byWhere[w].length + '">' + esc(w) + "</td>" : "")
            + "<td>" + esc(r.race) + '</td><td class="num">' + n0(num(r.ballots))
            + '</td><td class="num ' + (m < 0 ? "dem" : "rep") + '">' + mgn(m)
            + "</td></tr>";
        }).join("");
      }).join("");
    }).join("");
    // the spread that makes the point, computed rather than asserted
    var h = rows.filter(function (r) { return r.group.indexOf("Hispanic") === 0
                                       && r.race === "2024 Senate"; });
    var spread = "";
    if (h.length > 1) {
      var ms = h.map(function (r) { return num(r.margin_R); });
      spread = Math.abs(Math.max.apply(null, ms) - Math.min.apply(null, ms)).toFixed(1);
    }
    return card("tx-prec", "Chapter 4 \u00b7 slide 2 \u00b7 impact of the Hispanic vote",
      "The same group, two different electorates",
      "Precincts that are overwhelmingly one group in 2024, split by where they are. "
      + "The first block is the one that matters for this model: Hispanic precincts on "
      + "the border run "
      + (spread ? "<b>" + spread + " points</b> " : "")
      + "away from Hispanic precincts in the big metros, in the same race on the same "
      + "day. The second block widens the definition to any 90% non-white precinct, "
      + "which is a different and more Democratic set.",
      '<div class="scroll"><table class="txtbl"><thead><tr><th>Where</th><th>Race</th>'
      + "<th>Ballots</th><th>Margin</th></tr></thead><tbody>" + body + "</tbody></table></div>",
      "There is no single Hispanic number to measure, which is why break-even is a range "
      + "rather than a point: the same group runs tens of points apart depending on where "
      + "it lives, and the two halves have been moving in opposite directions. Note also "
      + "that the border's 2024 <i>presidential</i> margin is Republican while its Senate "
      + "margin is Democratic \u2014 the same voters, the same ballot, a 12-point split "
      + "between the top of the ticket and the Senate race.");
  }

  function volCard() {
    var rows = (D.vol || []).map(function (r) {
      return {g: r.group, n: num(r.counties), pct: num(r.pct_of_vote),
              mv: num(r.mean_move_per_cycle)};
    }).filter(function (r) { return r.mv != null; }).sort(function (a, b) { return b.mv - a.mv; });
    if (!rows.length) return "";
    var W = 700, H = 24 + rows.length * 44, L = 190, R = 70;
    var mx = Math.max.apply(null, rows.map(function (r) { return r.mv; })) * 1.12;
    var s = svg(W, H, "Average county margin movement per cycle by group");
    rows.forEach(function (r, i) {
      var y = 12 + i * 44;
      s += txt(L - 10, y + 16, r.g, "lb", "end");
      s += txt(L - 10, y + 29, r.pct.toFixed(1) + "% of the vote, " + r.n + " counties", "sub", "end");
      var w = r.mv / mx * (W - L - R);
      s += rect(L, y + 8, w, 16, i === 0 ? DC : "var(--dim,#999)", ' rx="3"');
      s += txt(L + w + 8, y + 20, r.mv.toFixed(2), "vl");
    });
    s += "</svg>";
    return card("tx-vol", "Chapter 4 · slide 3 · what moves, and what it weighs",
      "Why South Texas matters",
      "Average absolute change in county margin across 2018 to 2020 to 2022 to 2024, "
      + "weighted by projected 2026 turnout, with each group&rsquo;s share of the vote.",
      s,
      "The border swings three times as hard as anywhere else while carrying a twelfth of "
      + "the ballots: the highest-uncertainty, lowest-weight part of the map. Watch it "
      + "first for direction, not for votes.");
  }

  /* ================================= 11. the county watchlist, live, + net D gain */
  function watchCard(L) {
    var w = D.watch || [];
    if (!w.length) return "";
    var liveBy = {};
    var B = window.DATA || {};
    var r = ((B.states || {}).TX || {}).races && B.states.TX.races.senate;
    if (r && r.counties && r.candidates) {
      var ri = -1, di = -1;
      r.candidates.forEach(function (c, i) {
        var p = (c.party || "").toUpperCase();
        if (p === "R" || p === "REP") ri = i;
        if (p === "D" || p === "DEM") di = i;
      });
      if (ri >= 0 && di >= 0) {
        r.counties.forEach(function (row) {
          var v = row.votes || [], t = v.reduce(function (a, x) { return a + (x || 0); }, 0);
          if (t > 0) liveBy[row.name] = {m: ((v[ri] || 0) - (v[di] || 0)) / t * 100, t: t,
                                         pr: row.precincts_reporting, pt: row.precincts_total};
        });
      }
    }
    var groups = [];
    w.forEach(function (o) { if (groups.indexOf(o.group) < 0) groups.push(o.group); });
    var body = groups.map(function (g) {
      var rows = w.filter(function (o) { return o.group === g; });
      return '<tr class="grp"><td colspan="6">' + esc(g) + "</td></tr>"
        + rows.map(function (o) {
          var lv = liveBy[o.county];
          var swing = lv ? (lv.m - o.m24) : null;
          return "<tr><td>" + esc(o.county) + '</td><td class="num">' + n0(o.turnout)
            + '</td><td class="num">' + mgn(o.m24) + '</td><td class="num dim">'
            + mgn(o.m26) + "</td>"
            + '<td class="num ' + (lv ? (lv.m < 0 ? "dem" : "rep") : "") + '">'
            + (lv ? mgn(lv.m) : "—") + "</td>"
            + '<td class="num ' + (swing == null ? "" : (swing < 0 ? "dem" : "rep")) + '">'
            + (swing == null ? "—" : (swing < 0 ? "← " : "→ ")
               + Math.abs(swing).toFixed(1)) + "</td></tr>";
        }).join("");
    }).join("");
    // The headline: what this model thinks is already in the box. Derived from the
    // county file rather than asserted - every county's 2026 early vote weighted by its
    // own 2024 Senate margin gives the ground the banked vote was drawn from, and the
    // same weighting of the model's per-county shift gives what it assumes happened on
    // top. Texas has no party registration, so this is an inference, never a count.
    var ev = 0, evGround = 0, evShift = 0;
    (D.cty || []).forEach(function (r) {
      var e = num(r.ev_2026), m = num(r.margin_2024_sen), sh = num(r.shift);
      if (e == null || m == null || sh == null) return;
      ev += e; evGround += e * m; evShift += e * sh;
    });
    var head = "";
    if (ev > 0) {
      var ground = evGround / ev, shift = evShift / ev, est = ground - shift;
      var lead = -est / 100 * PROJ.banked;
      // Margins are the unit the rest of the tab uses, but the thing being counted
      // tomorrow is votes, so give both. A margin of X points on N ballots is X% of N
      // votes of margin, which is half that many voters changing sides.
      var vGround = ground / 100 * PROJ.banked;
      var vShift = shift / 100 * PROJ.banked;
      var vEst = est / 100 * PROJ.banked;
      var sideV = function (v) {
        return (v < 0 ? "D+" : "R+") + n0(Math.abs(v));
      };
      head = '<div class="txbig" style="color:' + sideCol(est) + '">' + mgn(est) + "</div>"
        + '<div class="txsub">what this model has banked: a lead of about <b>'
        + sideV(vEst) + "</b> votes on " + n0(PROJ.banked)
        + " early and mail ballots</div>"
        + '<table class="txtbl" style="margin-bottom:12px"><thead><tr><th>&nbsp;</th>'
        + "<th>as a margin</th><th>in votes</th></tr></thead><tbody>"
        + "<tr><td>Ground the early vote was drawn from, at 2024 margins</td>"
        + '<td class="num">' + mgn(ground) + '</td>'
        + '<td class="num rep">' + sideV(vGround) + "</td></tr>"
        + "<tr><td>Shift the model assumes on top, weighted by early vote</td>"
        + '<td class="num dem">\u2212' + shift.toFixed(2) + '</td>'
        + '<td class="num dem">' + n0(Math.abs(vShift)) + " moved</td></tr>"
        + '<tr class="em"><td>Estimated banked margin</td>'
        + '<td class="num">' + mgn(est) + '</td>'
        + '<td class="num">' + sideV(vEst) + "</td></tr></tbody></table>"
        + '<p class="txsub" style="margin:-4px 0 12px">That '
        + n0(Math.abs(vShift)) + " votes of margin is about "
        + n0(Math.abs(vShift) / 2) + " voters changing sides, out of "
        + n0(PROJ.banked) + " who have already voted. For scale, the whole race needs "
        + n0(305279) + " net new Democratic votes to erase 2024.</p>";
    }
    return card("tx-watch", "Section 5 · slide 1 · what is already banked",
      "What we think is already banked, and where it came from",
      "Texas has no party registration, so nobody can count the banked lead \u2014 this "
      + "is an inference. It is built from the one thing that <i>is</i> known: which "
      + "counties the 7.73M early ballots came from. Weight each county&rsquo;s 2024 "
      + "Senate margin by its own 2026 early vote and you get the ground the banked vote "
      + "was drawn from; the model&rsquo;s shift is then applied on top.",
      head
      + '<div class="scroll"><table class="txtbl"><thead><tr><th>County</th><th>Proj turnout</th>'
      + "<th>2024</th><th>Model 2026</th><th>Live</th><th>Swing</th></tr></thead><tbody>"
      + body + "</tbody></table></div>",
      "Nineteen counties carry 67.5% of the projected vote, so the outcomes that follow "
      + "are decided here. The live and swing columns fill in as Texas reports.");
  }

  function countyGainCard() {
    var rows = (D.cty || []).map(function (r) {
      return {c: r.county, gain: num(r.net_d_gain), t: num(r.proj_turnout),
              m24: num(r.margin_2024_sen), m26: num(r.margin_2026)};
    }).filter(function (r) { return r.gain != null; }).sort(function (a, b) { return b.gain - a.gain; });
    if (!rows.length) return "";
    var top = rows.slice(0, 14);
    var tot = rows.reduce(function (a, r) { return a + r.gain; }, 0);
    var top5 = rows.slice(0, 5).reduce(function (a, r) { return a + r.gain; }, 0);
    var top10 = rows.slice(0, 10).reduce(function (a, r) { return a + r.gain; }, 0);
    var W = 700, H = 20 + top.length * 24, L = 130, R = 74;
    var mx = top[0].gain * 1.1;
    var s = svg(W, H, "Net Democratic gain by county, top 14");
    top.forEach(function (r, i) {
      var y = 12 + i * 24;
      s += txt(L - 10, y + 10, r.c, "lb", "end");
      var w = r.gain / mx * (W - L - R);
      s += rect(L, y + 2, w, 14, DC, ' rx="2" opacity="0.85"');
      s += txt(L + w + 8, y + 13, n0(r.gain), "vl");
    });
    s += "</svg>";
    return card("tx-gain", "Section 5 · slide 3 · where the votes have to come from",
      "Net Democratic gain by county",
      "What the model adds to each county versus its 2024 Senate result. The total needed "
      + "to erase R+5.98 is " + n0(305279) + "; the model produces " + n0(tot) + ".",
      s,
      "<b>Concentration risk.</b> Five counties supply " + (top5 / tot * 100).toFixed(1)
      + "% of the net gain and ten supply " + (top10 / tot * 100).toFixed(1) + "%. A miss "
      + "in Harris or Dallas cannot be made up in rural Texas, and the whole cushion is "
      + n0(tot - 305279) + " votes out of 10.2 million.");
  }

  /* ================================================================ 12. the conclusion */
  function conclusionCard() {
    return '<section class="txarg" id="tx-read-committed">'
      + '<p class="txkick">Written down before the polls close · 2 November 2026</p>'
      + "<h2>What I will read into tomorrow night, decided now</h2>"
      + "<p>Committed in advance so it cannot be rationalised afterward. All three branches "
      + "turn on the early-vote margin Texas reports when polls close, against the band "
      + "set by what election day has actually done in Texas.</p>"
      + "<ol>"
      + "<li><b>Early vote better than " + mgn(THR_SAFE_D) + ".</b> Talarico wins even if "
      + "election day looks like 2022, the harshest midterm on record. The Hispanic shift "
      + "beat break-even and the polls were right.</li>"
      + "<li><b>Early vote " + mgn(THR_SAFE_D) + " to " + mgn(THR_SAFE_R) + ".</b> "
      + "Genuinely undecided, and election day decides it. Do not call it until election-day "
      + "precincts are in.</li>"
      + "<li><b>Early vote worse than " + mgn(THR_SAFE_R) + ".</b> Paxton wins even if "
      + "election day is as weak for Republicans as 2024. The polls missed in the familiar "
      + "Texas direction and the primary signal did not convert.</li>"
      + "</ol>"
      + '<p class="txnote"><b>Read nothing before about 90% of the early vote is in.</b> '
      + "Texas reports early and mail first, but not all at once and not in a published "
      + "order, and its metros hold a large Democratic early margin against a large rural "
      + "Republican one. Measured across 2020, 2022 and 2024, a partial count can sit 65 "
      + "points from the true early margin at 10% counted and 42 at half; the orderings "
      + "converge to about 5 points only at 90% \u2014 the same 5 in all three cycles. "
      + "Every threshold above refers to the FULL early vote, never to a partial one.</p>"
      + '<p class="txnote"><b>What would discredit the method rather than the result:</b> if '
      + "Hidalgo, Cameron and Webb come in right of 2024 while Harris and Dallas come in "
      + "left of it, the electorate is sorting by education rather than ethnicity and every "
      + "Hispanic number here is measuring the wrong thing. The watchlist above shows this "
      + "live.</p>"
      + '<p class="txnote"><b>Least sure of, in order:</b> the Hispanic shift, which sets '
      + "the sign and is unmeasured; turnout above 10.2 million, which the whole model scales "
      + "with; and the Black ceiling, corrected today at a cost of 1.62 points, which the "
      + "county map has still not been re-cut for.</p>"
      + "</section>";
  }

  /* ===================================================================== assembly */
  var CSS = ""
    + ".txwrap-inner{max-width:860px}"
    + ".txcard,.txarg{background:var(--card,#fff);border:1px solid var(--line);"
    + "border-radius:10px;padding:16px 18px;margin:0 0 14px}"
    + ".txarg{border-left:3px solid var(--fg)}"
    + ".txframe{padding:4px 0 10px;margin:22px 0 14px;border-top:2px solid var(--fg)}"
    + ".txframe h2{font-family:var(--display);font-weight:400;font-size:21px;margin:3px 0 9px}"
    + ".txframe p{margin:0 0 8px;font-size:14px;line-height:1.55;max-width:74ch;color:var(--dim)}"
    + ".txframe p:first-of-type{color:var(--fg)}"
    + ".txarg h2{font-family:var(--display);font-weight:400;font-size:22px;margin:2px 0 10px}"
    + ".txarg p{margin:0 0 9px;font-size:14px;line-height:1.55;max-width:74ch}"
    + ".txarg ol{margin:4px 0 0;padding-left:1.2em;font-size:14px;line-height:1.55}"
    + ".txarg li{margin-bottom:6px}"
    + ".txarg .nm{font-variant-numeric:tabular-nums}"
    + ".txcard h3{font-family:var(--display);text-transform:uppercase;letter-spacing:.06em;"
    + "font-size:13px;margin:0 0 7px}"
    + ".txkick{font-size:10.5px;text-transform:uppercase;letter-spacing:.09em;"
    + "color:var(--dim);margin:0 0 3px}"
    + ".txhint{font-size:13px;color:var(--dim);margin:0 0 12px;max-width:74ch;line-height:1.5}"
    + ".txnote{font-size:12.5px;color:var(--dim);margin:11px 0 0;max-width:74ch;"
    + "line-height:1.5;border-top:1px solid var(--line);padding-top:9px}"
    + ".txbig{font-family:var(--display);font-size:40px;line-height:1.1;"
    + "font-variant-numeric:tabular-nums}"
    + ".txsub{font-size:13px;color:var(--dim);margin:2px 0 10px}"
    + ".txverdict{font-size:14px;font-weight:600;margin:0 0 10px;padding:7px 10px;"
    + "border-radius:6px;background:var(--bg,#f6f6f4)}"
    + ".txverdict.dem{color:var(--dem,#2a6ebb)}.txverdict.rep{color:var(--rep,#b3443a)}"
    + ".txband{margin:0 0 12px;border:1px solid var(--line);border-radius:7px;overflow:hidden}"
    + ".bandrow{display:flex;justify-content:space-between;gap:12px;padding:7px 10px;"
    + "font-size:12.5px;border-bottom:1px solid var(--line)}"
    + ".bandrow:last-child{border-bottom:none}.bandrow.mid{background:var(--bg,#f6f6f4)}"
    + ".bandrow .bl.dem{color:var(--dem,#2a6ebb)}.bandrow .bl.rep{color:var(--rep,#b3443a)}"
    + ".bandrow .bv{font-variant-numeric:tabular-nums;white-space:nowrap;font-weight:600}"
    + "table.txtbl{width:100%;border-collapse:collapse;font-size:13px}"
    + "table.txtbl th{font-family:var(--display);text-transform:uppercase;letter-spacing:.05em;"
    + "font-size:10px;color:var(--dim);text-align:right;padding:0 0 5px 11px;white-space:nowrap}"
    + "table.txtbl th:first-child,table.txtbl td:first-child{text-align:left;padding-left:0}"
    + "table.txtbl td{padding:4px 0 4px 11px;border-top:1px solid var(--line)}"
    + "table.txtbl td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}"
    + "table.txtbl tr.em td{font-weight:600}"
    + "table.txtbl tr.grp td{font-family:var(--display);text-transform:uppercase;"
    + "letter-spacing:.05em;font-size:10px;color:var(--dim);padding-top:11px}"
    + "table.txtbl .dem,.txcard .dem{color:var(--dem,#2a6ebb)}"
    + "table.txtbl .rep,.txcard .rep{color:var(--rep,#b3443a)}"
    + ".txcard .dim,table.txtbl .dim{color:var(--dim)}"
    + ".txcard .scroll{overflow-x:auto}"
    + ".txnav{font-size:12px;margin:0 0 14px;line-height:1.9}"
    + ".txnav a{margin-right:12px;white-space:nowrap}"
    + "#txwrap svg{color:var(--fg)}"
    + "#txwrap .gl{stroke:var(--line);stroke-width:1}"
    + "#txwrap .zl{stroke:currentColor;stroke-width:1;stroke-dasharray:3 3;opacity:.55}"
    + "#txwrap .cn{stroke:currentColor;stroke-width:2.5;opacity:.3;stroke-linecap:round}"
    + "#txwrap text{font-size:11px;fill:var(--fg)}"
    + "#txwrap .tk{font-size:10px;fill:var(--dim)}"
    + "#txwrap .lb{font-size:11.5px;fill:var(--fg)}"
    + "#txwrap .lbb{font-size:11.5px;fill:var(--fg);font-weight:600}"
    + "#txwrap .sub{font-size:9.5px;fill:var(--dim)}"
    + "#txwrap .lgd{font-size:10px;fill:var(--dim)}"
    + "#txwrap .vl{font-size:11px;fill:var(--fg);font-variant-numeric:tabular-nums}"
    + "#txwrap .inb{font-size:10px;fill:#fff;font-variant-numeric:tabular-nums}"
    + "#txwrap .cell{font-size:10.5px;fill:var(--fg);font-variant-numeric:tabular-nums}"
    + "#txwrap .cellw{font-size:10.5px;fill:#fff;font-variant-numeric:tabular-nums}";

  window.renderTexas = function (host) {
    host.innerHTML = '<div class="txwrap-inner"><p class="txhint">Loading the Texas '
      + "analysis…</p></div>";
    var want = [["modes", "tx_modes_statewide.csv"], ["order", "tx_reporting_order.csv"], ["est", "tx_estimates.csv"], ["prim", "tx_primary_series.csv"], ["fit", "tx_primary_fit.csv"], ["cmp", "tx_2018_compare.csv"],
                ["base", "tx_baseline.csv"], ["pax", "tx_paxton.csv"],
                ["sens", "tx_sensitivity.csv"], ["blocs", "tx_blocs.csv"],
                ["eth", "tx_ethnicity.csv"], ["prec", "tx_precincts.csv"], ["tarr", "tx_tarrant_precincts.csv"], ["tarrh", "tx_tarrant_history.csv"], ["tgrp", "tx_tarrant_groups.csv"], ["tarrhd", "tx_tarrant_history_detail.csv"], ["tage", "tx_tarrant_age.csv"], ["meng", "tx_morris_engagement.csv"], ["mhar", "tx_morris_harris.csv"], ["xtab", "tx_crosstabs.csv"], ["exit", "tx_exit_2024.csv"], ["pace", "tx_pace_gradient.csv"],
                ["vol", "tx_volatility.csv"], ["cty", "tx_counties.csv"],
                ["watch", "tx_watch.json"]];
    Promise.all(want.map(function (p) {
      return load(p[1]).then(function (v) { D[p[0]] = v; })
        .catch(function (e) { D[p[0]] = []; console.warn("texas:", e.message); });
    })).then(function () {
      SECTIONS = [];
      var L = live();
      // Narrative order. The tab is an argument, not a dashboard, so it runs:
      // what changed (the primary), how that reaches the result (early vote against
      // election day), where it lands (the estimates and why they disagree), the group
      // doing the moving (the Hispanic cards), and finally the three ways of asking
      // what it would take. The live read sits second because on the night it is the
      // only card anyone needs first.
      var html = thesis()
        + readCard(L)
        // 1. what actually changed
        + primaryCard()
        + primaryFitCard()
        // 2. how a banked vote reaches a result
        + historyCard()
        // 3. where every method lands, and why they disagree
        + framing("tx-frame-lands", "Chapter 3",
            "So where does it land, and why can nobody agree?",
            ["Chapter 2 is mechanics: three quarters of the vote is already cast, and "
             + "election day moves it by a point or by nine depending on the cycle. None "
             + "of that tells you who wins.",
             "The first slide below is every attempt at an answer \u2014 eleven of them, "
             + "spanning six points and straddling zero. A spread that wide usually means "
             + "the methods are measuring different things. They are not.",
             "Two choices account for most of it, and neither is demographic. The "
             + "candidate is worth about five points, measured within-poll so house "
             + "effects cancel. And which past result you carry forward moves the answer "
             + "more than any assumption about who turns out. Strip both out and what is "
             + "left is a single question: <b>how far Hispanic voters move.</b>"])
        + estimatesCard()
        + paxtonCard()
        + baselineCard()
        + tarrantCard()
        + crosstabCard()
        + exitCard()
        // 4. the group doing the moving
        + framing("tx-frame-hisp", "Chapter 4",
            "The one question nobody has measured",
            ["Chapter 3 strips out the two things that are not about the electorate \u2014 "
             + "the candidate, worth about five points, and the choice of which past "
             + "result to carry forward. What is left is a single question, and the whole "
             + "race turns on it: <b>how far Hispanic voters move.</b>",
             "Three facts make that harder than it sounds. The group is 29.76% of the "
             + "projected electorate, so it carries real weight. It is not one electorate "
             + "but two \u2014 the border and the metros sit tens of points apart and "
             + "have been moving in opposite directions. And the border is the most "
             + "volatile ground in Texas, swinging three times as hard per cycle as "
             + "anywhere else while carrying a twelfth of the ballots.",
             "So there is no single Hispanic number to put in a model, which is why "
             + "break-even is a range rather than a point. The two slides here show "
             + "why one number cannot describe this group, and which parts of the map "
             + "actually move."])
        + morrisCard()
        + precinctCard()
        + volCard()
        // 5. three ways of asking what it would take
        + framing("tx-frame-outcomes", "The outcomes",
            "Four ways of asking the same question",
            ["Everything above is evidence. None of it is an answer, because every piece "
             + "stops at the same place: the electorate changed, the banked vote is most "
             + "of the result, the candidate is worth about five points, and the movement "
             + "is Hispanic voters \u2014 but nobody has measured how far they move.",
             "So the honest thing is not to produce one number. It is to ask what would "
             + "have to be true, from four directions, and see whether the answers agree. "
             + "The first two establish the starting position: what this model already has "
             + "in the box, and where each demographic sits against where it needs to "
             + "be. The next two ask it in votes \u2014 how big a banked lead, against "
             + "how hard an election day, and where those votes physically have to come "
             + "from county by county. The last two ask it in demographics and then in "
             + "party blocs, with no demographics in it at all.",
             "They are built from different data and they land in the same place, which is "
             + "the strongest thing this tab can say. A coin flip that four independent "
             + "routes agree on is still a coin flip \u2014 but it is a well-measured one."])
        + watchCard(L)
        + ethCard()
        + countyGainCard()
        + bankedCard()
        + gridCard("tx-sens", "Section 5 \u00b7 slide 5 \u00b7 the demographic levers",
            "What it takes to flip Texas",
            "Statewide margin for each pair of assumed shifts. White applies in the "
            + "fifteen largest counties only. Across the whole white axis the answer "
            + "barely moves; across the Hispanic axis it swings the race \u2014 which is "
            + "why one unmeasured number carries the sign.",
            D.sens, "hispanic_shift", "white_shift", "tx_margin_R",
            "Hispanic shift toward Democrats \u2192", "\u2193 White shift",
            "Black and Asian are held at the values the published model used. The +8 for "
            + "Black voters is not defensible as a group-level claim and was corrected to "
            + "+2, so read every cell as about 1.6 points friendlier to Democrats than "
            + "the corrected model gives.")
        + gridCard("tx-blocs", "Section 5 \u00b7 slide 6 \u00b7 the same question by bloc",
            "What it takes, by voting bloc",
            "Independents against the Republican bloc-size edge, with Democrats holding "
            + "98% and crossover fixed at 2%. <b>Independents are 30% of the electorate, "
            + "from AtlasIntel</b> \u2014 solving its published bloc breaks to return its "
            + "own D+6 topline gives 29% Democrat, 30% independent, 41% Republican. Texas "
            + "has no party registration, so a poll is the only place a bloc size can come "
            + "from.",
            D.blocs, "ind_break_D", "r_bloc_edge", "tx_margin_R",
            "Independents breaking Democratic \u2192", "\u2193 Republican size edge",
            "<b>The independent share is a lever-length assumption, not a level one.</b> "
            + "At even blocs a 50/50 split ties the race at <i>any</i> share \u2014 the "
            + "share only sets how fast the margin moves. A ten-point move among "
            + "independents is worth 2.0 points of margin if they are 20% of the electorate "
            + "and 3.0 if they are 30%, so how big the bloc is matters as much as how it "
            + "breaks. On AtlasIntel&rsquo;s own R+12 bloc sizes the race needs 69.2% of "
            + "independents."
            + "<br><br><b>Where history sits on that axis.</b> Nationally, independents went D+2 in the 2022 midterm and D+4 in 2024 \u2014 51% and 52% voting Democratic. 2026 polling has them near D+20, or 60%. AtlasIntel\u2019s own Texas crosstab has them at 64.5\u201328.0, which is 68.2%. Read the grid against those: at even blocs the 2024 figure is a coin flip, D+20 is a six-point Democratic win, and at AtlasIntel\u2019s R+12 bloc sizes even D+20 still loses by five and a half. The Democratic case in Texas needs independents roughly twice as far from 2024 as the national swing already is."
            + "<br><br>The March primary \u2014 Democrats 51.70% of 4,479,000 "
            + "ballots \u2014 argues the blocs are nearer even, where the race turns on "
            + "independents splitting 50/50.",
            function (y) { return y === 0 ? "even" : (y > 0 ? "R+" : "D+") + Math.abs(y); })
        + conclusionCard();
      var nav = '<p class="txnav">' + SECTIONS.map(function (s) {
        return '<a href="#' + s.id + '">' + esc(s.title) + "</a>";
      }).join("") + "</p>";
      host.innerHTML = "<style>" + CSS + "</style>"
        + '<div class="txwrap-inner">' + thesis() + nav
        + html.slice(html.indexOf("</section>") + 10) + "</div>";
    });
  };
})();
