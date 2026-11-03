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
 *     line of D+5.54 is replaced by a band, because a tie in the Senate race can land anywhere in it
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
  // Phone layout. The charts here are hand-placed SVG with no layout engine, so a
  // label gutter sized for 760px does not survive a 375px screen - it just shrinks the
  // type to six pixels. Charts that keep labels in a gutter read this and switch
  // geometry instead of scaling. Set once per render, re-read on a resize that crosses
  // the breakpoint.
  var BREAK = 640;
  var NARROW = false;
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
      + '<p class="txkick">The question</p>'
      + "<h2>Will we win Texas?</h2>"
      + "<p><b>The Senate seat: yes, and with more confidence than the margin suggests."
      + "</b> Not because the polls are generous \u2014 they are not, and this tab prices "
      + "them at three to four points too Democratic \u2014 but because of what is left "
      + "after that is taken off. The same four polls asked about the governor&rsquo;s "
      + 'race too, and Talarico runs <b class="nm">4.92</b> points ahead of Hinojosa on '
      + "the same questionnaires. A polling error hits both races equally and subtracts "
      + "out of the difference, so <b>the Paxton effect is larger than the polling miss "
      + "and cannot be erased by it</b>. Take the full haircut and the Senate race is "
      + 'still <b class="nm">D+0.98</b> \u2014 and in fact there is no haircut that '
      + "beats him: he only loses once the correction exceeds 5.03 points, which is "
      + "larger than any polling miss ever measured in Texas.</p>"
      + "<p><b>And that haircut is itself conservative.</b> All four of the big Texas "
      + "polling misses are presidential years with Trump <i>on the ballot</i>; the two "
      + "midterms without him average <b>\u22121.87</b>, meaning the polls understated "
      + "Democrats. 2026 is a midterm with no Trump on the ballot, so the better-reasoned "
      + "prior is the friendly one \u2014 on which Talarico wins by 6.90 and Hinojosa by "
      + "1.98. This tab quotes the unfriendly figure anyway, because four observations "
      + "that agree beat two that contradict each other. Section 1 slide 3 prices "
      + "exactly what that costs.</p>"
      + "<p><b>Which generalises into the number to hold tonight.</b> Talarico is the "
      + "generic Texas Democrat plus 4.92, so he is level only when that generic "
      + 'Democrat loses by <b class="nm">4.92</b>. <b>We think he wins an R+4 night</b> '
      + "\u2014 a night where the rest of the Texas ticket loses by four, which would "
      + "read as a bad evening for Democrats everywhere else on the ballot, still "
      + 'leaves him <b class="nm">D+0.92</b>. R+3 leaves him D+1.92. It is only at '
      + "about R+5 for the ticket that the lag stops covering him.</p>"
      + "<p><b>The governor&rsquo;s race is a different question with a different "
      + "answer.</b> There is no Paxton in it. At the same haircut Abbott against "
      + 'Hinojosa is <b class="nm">R+3.94</b>, and she has to find 402,353 votes '
      + "somewhere. Only two things on this ballot are big enough: the Hispanic vote "
      + "running better than the polls assume, and rural turnout coming in under. She "
      + "needs both at once. <b>Except on one reading, where she needs neither.</b>"
      + "</p>"
      + "<p><b>The finding that decides her race, and the strongest thing on this "
      + "tab.</b> Tarrant County is the one place in Texas that publishes who is "
      + "voting, and it shows an unaffiliated bloc \u2014 no primary ballot since 2022 "
      + "\u2014 that is now <b>43%</b> of its early vote and <i>mirrors the county "
      + "itself</i> within a point and a half on age, race, sex and registration. "
      + "Harris, measured a completely different way, finds the Democratic turnout edge "
      + "widest among exactly those voters: <b>13.2 points</b> among people who skipped "
      + "the 2022 midterm against 5.0 among the most reliable. Two counties, two "
      + "instruments that cannot produce each other\u2019s number, one direction."
      + "<br><br>Project that across the six large counties where the measurement "
      + "licenses it and the bloc does not break 50/50 \u2014 it breaks like each "
      + "county it sits in. Dallas 69.4%, Harris 60.8%, Tarrant 54.5%; weighted, "
      + '<b class="nm">61.1%</b>. That is worth <b>447,576</b> net votes against an '
      + "even split, and she needs 402,353. <b>On the flat assumption her lever falls "
      + "eleven points short; on the mirror it clears on its own.</b> One unmeasurable "
      + "choice, worth four points of statewide margin \u2014 more than the Hispanic "
      + "and rural levers combined. Section 4 slide 1."
      + "</p>"
      + "<p><b>We have looked at fourteen different paths to a number, and our "
      + "conclusions are these.</b></p>"
      + "<ol>"
      + "<li><b>The race is close at all because the methods agree.</b> Fourteen routes, "
      + 'from four sources that share no inputs, have a median of <b class="nm">D+0.65</b> '
      + "in a state whose last three statewide cycles averaged R+10.09. A poll can be "
      + "wrong about who turns out and a model can be wrong about how a group shifts, but "
      + "they are not wrong in the same direction for the same reason.</li>"
      + "<li><b>Talarico wins, and the candidate is why.</b> The 4.92 he runs ahead of "
      + "his own ticket is larger than the three-to-four point polling miss and cancels "
      + "in the difference, so it survives the worst the polls can do. He holds an R+4 "
      + "night for the rest of the ticket.</li>"
      + "<li><b>The unaffiliated bloc is the strongest evidence here, and it is "
      + "double-edged.</b> Tarrant and Harris agree on it from two instruments that "
      + "share no inputs, and projecting it properly \u2014 letting it mirror each "
      + "county rather than carrying one county\u2019s number flat \u2014 moves the "
      + "governor\u2019s race by four points. It settles nothing for Talarico, who "
      + "clears every version of it, and settles everything for Hinojosa.</li>"
      + "<li><b>Hinojosa is a genuine coin flip, and the same candidate is why.</b> "
      + "There is no Paxton in her race, so the identical night that elects Talarico by "
      + "a point loses her by four. She needs the Hispanic vote at D+36.15 <i>and</i> "
      + "rural turnout down, together.</li>"
      + "<li><b>The one number that settles it reports first.</b> Texas dumps the early "
      + 'vote at 7pm Central, and a tie in the Senate race lands between <b class="nm">D+2.27</b> and '
      + '<b class="nm">R+0.18</b>.</li>'
      + "</ol>"
      + "<p><b>And why.</b> Four things changed, and each one is counted rather than "
      + "assumed:</p>"
      + "<ol>"
      + '<li><b>The primary.</b> Democrats took <b class="nm">51.70%</b> of 4,486,097 '
      + "March ballots &mdash; the first midterm majority on record &mdash; on "
      + '<b class="nm">+115.6%</b> growth over 2022. Fitted against seven cycles of '
      + "Texas Novembers, that implies a race between D+1.57 and R+1.66.</li>"
      + '<li><b>The early vote.</b> <b class="nm">' + n0(PROJ.banked) + "</b> ballots are "
      + "already banked, about 76% of the projected total. In Tarrant County 48.8% of "
      + "early voters did not vote in the 2022 midterm, and Morris&rsquo;s Harris County "
      + "work found the turnout gap widening as voters get less regular: 90.7% of the "
      + "most reliable Democrats had already voted against 85.7% of the equivalent "
      + "Republicans, but among voters who skipped the 2022 midterm it is 70.3% against "
      + "57.1%. Those are turnout rates, not margins."
      + "<br><br>Three things follow. <b>One:</b> the Republican coalition is the "
      + "high-engagement coalition \u2014 it holds its own among people who always "
      + "vote and loses badly among people who sometimes do. <b>Two:</b> an electorate "
      + "larger than 2022&rsquo;s has to be drawn from the pool where that gap is 13.2 "
      + "points, not 5.0, so every extra voter is on average more Democratic than the "
      + "last one. <b>Three:</b> election day cannot fix it for Republicans, because "
      + "their remaining base is the reliable half that has already turned out "
      + "\u2014 in Tarrant, 86% of active Democratic primary voters had voted early "
      + "against 79% of Republicans, leaving about 29,000 Democrats and 42,000 "
      + "Republicans. That 13,000 edge is roughly the Democratic early-vote lead, which "
      + "is why the county is close rather than decided.</li>"
      + "<li><b>The polls.</b> All four non-partisan final polls have Talarico ahead, "
      + 'averaging <b class="nm">D+5.03</b> across 5,934 interviews. The famous Texas polling misses '
      + "are a presidential-year pattern \u2014 four for four, mean 4.05, every one "
      + "with Trump on the ballot. <b>There are two midterms to check, not one, and "
      + "they disagree.</b> 2022 was accurate to half a point. 2018 missed by "
      + "<b>4.23 in the opposite direction</b> \u2014 the final average had Cruz by 6.8 "
      + "and he won by 2.57. So the midterm evidence is two observations pointing "
      + "opposite ways, and 2018 is the one that resembles 2026.</li>"
      + "<li><b>The composition model.</b> Rebuilding the state county by county from "
      + "citizen voting-age population and a per-group shift gives "
      + '<b class="nm">D+0.65</b> &mdash; arrived at without looking at a primary ballot '
      + "or a poll.</li>"
      + "</ol>"
      + "<p><b>What would make it wrong.</b> The sign turns on one number nothing above "
      + 'measures: how far Hispanic voters move. Break-even is <b class="nm">+17.6</b>. '
      + "AtlasIntel&rsquo;s crosstab implies +16.5 and Paxton wins by a hair; "
      + "Morris&rsquo;s engagement finding implies +27 and Talarico wins by three. The "
      + "county model also clears even by only "
      + '<b class="nm">24,657</b> net votes, and it gets there having moved Black voters '
      + "+12 off a base already 91.1% Democratic, which is not defensible; capping that "
      + "alone turns D+0.65 into R+0.97.</p>"
      + '<p class="txnote" style="border-top:none;padding-top:0">None of this is the test. '
      + "The early vote reports first tonight, and because it is ~76% of the ballots a tie "
      + 'lands in a narrow band: an early margin between <b class="nm">'
      + mgn(THR_SAFE_D) + '</b> and <b class="nm">' + mgn(THR_SAFE_R) + "</b>. Better than that and this answer is "
      + "right; worse and it is wrong, in one reading, with nothing left to argue about.</p>"
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
        + '<div class="scroll"><table class="txtbl"><tbody>'
        + '<tr><td>Early and mail</td><td class="num">' + mgn(L.earlyMargin) + "</td></tr>"
        + (L.edayMargin != null ? '<tr><td>Election day</td><td class="num">' + mgn(L.edayMargin) + "</td></tr>" : "")
        + (L.totalMargin != null ? '<tr class="em"><td>Everything counted</td><td class="num">' + mgn(L.totalMargin) + "</td></tr>" : "")
        + '<tr><td>Precincts</td><td class="num">' + n0(L.precReporting || 0) + " / " + n0(L.precTotal || 0) + "</td></tr>"
        + "</tbody></table></div>",
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
  /* Texas votes differently for Senate than it votes for everything else on the same
     ballot. Three of the last four Senate races show it, and the one that does not is
     2020. This matters twice over: it is a reason to read a Senate poll against the
     Senate record rather than against "how Republican Texas is", and it is a caution on
     the tie band in the next card, whose 2022 leg is built from Governor, Lieutenant
     Governor and Attorney General because 2022 had no Senate race at all.

     Unopposed races are excluded: 2018's Court of Criminal Appeals Place 8 had no
     Democrat and came in at R+74.68, which would drag any average it touched. */
  function senateCharts() {
    var R = (D.svt || []).map(function (r) {
      return {y: r.year, kind: r.kind, c: r.contest, s: num(r.senate_margin_R),
              t: num(r.ticket_median_R), a: num(r.ahead_of_ticket), n: num(r.n_other)};
    }).filter(function (r) { return r.s != null; });
    if (!R.length) return "";
    var wide = !NARROW;
    var W = wide ? 760 : 360, L = wide ? 190 : 8, RM = wide ? 96 : 8;
    var ROW = wide ? 46 : 62, T = wide ? 46 : 42;
    var H = T + R.length * ROW + 16;
    var lo = -6, hi = 18;
    var xs = function (v) { return L + (v - lo) / (hi - lo) * (W - L - RM); };
    var g = svg(W, H, "Texas Senate results against the rest of the statewide ticket in "
                    + "the same election");
    [-5, 0, 5, 10, 15].forEach(function (t) {
      g += line(xs(t), T - 16, xs(t), H - 14, t === 0 ? "zl" : "gl")
         + txt(xs(t), H - 3, t === 0 ? "even" : mgn(t, 0), "tk", "middle");
    });
    g += txt(wide ? L : 8, 14, "hollow dot: the rest of the statewide ticket, median",
             "lgd")
       + txt(W - RM, 14, "solid dot: the Senate race", "lgd", wide ? "end" : "end");
    R.forEach(function (r, i) {
      var y = T + (wide ? 12 : 26) + i * ROW;
      var head = r.y + "  " + r.c;
      if (wide) {
        g += txt(L - 14, y + 4, head, "lbb", "end")
           + txt(L - 14, y + 17, r.kind + (r.n ? ", vs " + r.n + " other races" : ""),
                 "sub", "end");
      } else {
        g += txt(8, y - 14, head, "lbb")
           + txt(W - 8, y - 14, r.kind, "sub", "end");
      }
      if (r.t != null) {
        g += '<circle cx="' + xs(r.t) + '" cy="' + y + '" r="4.5" fill="var(--card,#fff)" '
           + 'stroke="currentColor" stroke-width="1.5" opacity="0.7"/>';
      }
      g += '<circle cx="' + xs(r.s) + '" cy="' + y + '" r="5" fill="' + sideCol(r.s) + '"/>';
      g += txt(xs(r.s) + (r.s < (r.t == null ? 99 : r.t) ? -10 : 10), y + 4, mgn(r.s, 2),
               "vl", r.s < (r.t == null ? 99 : r.t) ? "end" : "start");
      if (r.t != null) {
        g += txt(xs(r.t) + (r.s < r.t ? 10 : -10), y + 4, mgn(r.t, 2), "tk",
                 r.s < r.t ? "start" : "end");
        if (wide) {
          g += '<text x="' + (W - RM + 12) + '" y="' + (y + 4) + '" class="vl" fill="'
             + sideCol(-r.a) + '">' + (r.a > 0 ? "+" : "") + r.a.toFixed(2) + "</text>";
        }
      }
    });
    g += "</svg>";

    /* The 2026 row deserves its own picture, because it is a better test than the three
       above it: the same respondents answered both questions, so house effects, turnout
       models and sampling all cancel. Whatever is left is ticket-splitting. */
    var SG = (D.sg || []).map(function (r) {
      return {n: r.pollster, nn: num(r.n), sc: r.screen, sen: num(r.senate_d_margin),
              gov: num(r.governor_d_margin), gap: num(r.talarico_runs_ahead)};
    }).filter(function (r) { return r.sen != null; });
    var g2 = "";
    if (SG.length) {
      var W2 = wide ? 760 : 360, L2 = wide ? 186 : 8, R2 = wide ? 104 : 8;
      var ROW2 = wide ? 42 : 58, T2 = 40;
      var H3 = T2 + SG.length * ROW2 + 18;
      var lo2 = -9, hi2 = 5;
      var x2 = function (v) { return L2 + (v - lo2) / (hi2 - lo2) * (W2 - L2 - R2); };
      g2 = svg(W2, H3, "The same four polls on both Texas races: Senate against Governor");
      [-8, -6, -4, -2, 0, 2, 4].forEach(function (t) {
        g2 += line(x2(t), T2 - 14, x2(t), H3 - 14, t === 0 ? "zl" : "gl")
           + txt(x2(t), H3 - 3, t === 0 ? "even" : mgn(t, 0), "tk", "middle");
      });
      g2 += txt(wide ? L2 : 8, 14, "\u25cb Abbott / Hinojosa", "lgd")
         + txt((wide ? L2 : 8) + 128, 14, "\u25cf Paxton / Talarico", "lgd");
      SG.forEach(function (r, i) {
        var y = T2 + (wide ? 12 : 24) + i * ROW2;
        var sm = -r.sen, gm = -r.gov;              // to margin_R, as the rest of the tab
        if (wide) {
          g2 += txt(L2 - 14, y + 4, r.n, "lbb", "end")
             + txt(L2 - 14, y + 17, n0(r.nn) + " " + r.sc, "sub", "end");
        } else {
          g2 += txt(8, y - 13, r.n, "lbb") + txt(W2 - 8, y - 13, n0(r.nn), "sub", "end");
        }
        g2 += '<circle cx="' + x2(gm) + '" cy="' + y + '" r="4.5" fill="var(--card,#fff)" '
           + 'stroke="currentColor" stroke-width="1.5"/>'
           + '<circle cx="' + x2(sm) + '" cy="' + y + '" r="5.5" fill="' + sideCol(sm) + '"/>';
        if (wide) {
          g2 += '<text x="' + (W2 - R2 + 12) + '" y="' + (y + 4) + '" class="vl" fill="'
             + DC + '">+' + r.gap.toFixed(1) + "</text>";
        } else {
          g2 += txt(W2 - 8, y + 16, "Talarico +" + r.gap.toFixed(1), "tk", "end");
        }
      });
      if (wide) g2 += txt(W2 - R2 + 12, 14, "Talarico ahead", "lgd");
      g2 += "</svg>";
    }
    var hit = R.filter(function (r) { return r.a != null && r.a > 0; }).length;
    var meas = R.filter(function (r) { return r.a != null; });
    return {ticket: g, sengov: g2, rows: R, sg: SG};
  }

  /* The extrapolation argument, as paired figures rather than a table of sentences.
     Each row is one claim; each side is the number that county's own instrument gives
     for it. The units differ by design - Morris measures turnout rates by engagement
     tier, Tackett measures composition by primary camp - and the point is that two
     instruments that cannot produce each other's number agree on the direction anyway. */
  function twoCountiesCard() {
    var R = (D.twoc || []).map(function (r) {
      return {c: r.claim, hm: r.harris_metric, hv: num(r.harris_value), hu: r.harris_unit,
              tm: r.tarrant_metric, tv: num(r.tarrant_value), tu: r.tarrant_unit};
    }).filter(function (r) { return r.hv != null; });
    if (!R.length) return "";
    var fmt = function (v, u) {
      return u === "pct" ? v + "%" : (u === "ratio" ? v + " to 1" : "+" + v.toFixed(1));
    };
    var wide = !NARROW;
    var W = wide ? 760 : 360, MID = wide ? 300 : 180, HALF = wide ? 210 : 86;
    var ROW = wide ? 54 : 74, T = 56, H = T + R.length * ROW + 12;
    var mx = 55;
    var s2 = svg(W, H, "Harris and Tarrant on the same claims, each by its own instrument");
    s2 += txt(MID - HALF - 8, 18, "HARRIS — Morris, turnout by engagement tier",
              "lgd", "end")
       + txt(MID + HALF + 8, 18, "TARRANT — Tackett, composition by primary camp",
             "lgd");
    s2 += line(MID, T - 14, MID, H - 8, "gl");
    var y = T;
    R.forEach(function (r) {
      s2 += txt(MID, y + 4, r.c, "lbb", "middle");
      var hw = Math.min(HALF, r.hv / mx * HALF * 1.6);
      var tw = Math.min(HALF, r.tv / mx * HALF * 1.6);
      var by = y + 14;
      s2 += rect(MID - HALF - 8 - hw, by, hw, 13, DC, ' rx="2" opacity="0.7"')
         + txt(MID - HALF - 14 - hw, by + 11, fmt(r.hv, r.hu), "vl", "end")
         + rect(MID + HALF + 8, by, tw, 13, DC, ' rx="2" opacity="0.7"')
         + txt(MID + HALF + 14 + tw, by + 11, fmt(r.tv, r.tu), "vl");
      if (wide) {
        s2 += txt(MID - 10, by + 11, r.hm, "sub", "end")
           + txt(MID + 10, by + 11, r.tm, "sub");
      }
      y += ROW;
    });
    s2 += "</svg>";
    return card("tx-twocounties", "Section 2 · slide 6 · what the two counties share",
      "Two counties, two incompatible instruments, one direction",
      "<b>Harris and Tarrant are the only Texas counties that publish individual voting "
      + "histories.</b> Everything else on this tab about <i>who</i> is voting is an "
      + "inference; these two are counts. Together they are <b>2,182,391</b> projected "
      + "votes, 21.4% of the state. The bars are not comparable to each other and are not "
      + "meant to be — Morris measures turnout rates by how reliably a voter has "
      + "turned out before, Tackett measures composition by which primary a voter last "
      + "chose. Neither method can produce the other&rsquo;s number. Each row is one "
      + "claim with each county&rsquo;s own evidence for it beside it.",
      s2,
      "<b>Six claims, two instruments, same direction on all six.</b> The movement sits "
      + "with irregular voters (Harris: a 13.2-point Democratic turnout lead among those "
      + "who skipped 2022; Tarrant: 48.8% of early voters skipped 2022) and not with "
      + "regular ones (Harris: the lead collapses to 5.0 among all-three-generals voters). "
      + "The Republican coalition is the reliable one and is not replenishing (Harris: "
      + "new primary voters break 5 to 1 Democratic; Tarrant: half of Republican primary "
      + "voters are 65 or over and 6% registered after 2022). And the two counties grew "
      + "their early vote by almost exactly the same amount, 44% and 47% — the one "
      + "row where the units genuinely match."
      + "<br><br><b>Why that licenses an extrapolation at all.</b> Two independent "
      + "analysts, two counties, two methods that share no inputs, one answer. And the "
      + "counties are not the same kind of place — Harris was D+12.89 in the 2024 "
      + "Senate race and Tarrant D+1.83, a stronghold and the swing county. A finding "
      + "that holds in both is stronger than the same finding twice in one kind of county."
      + "<br><br><b>Where it stops, which the next section enforces.</b> It does not "
      + "license extrapolating to <i>any</i> county. Harris is 63.2% non-white and "
      + "Tarrant 47.0%, so the measured band is roughly 47% to 63% non-white. The "
      + "majority-white large counties — Collin, Denton, Williamson, Montgomery, "
      + "Galveston, Hays, Travis — sit outside it and nothing here measures the bloc "
      + "in places like those. The two border counties, El Paso at 85.8% and Hidalgo at "
      + "90.1%, sit outside it the other way and are close to 90% Mexican-American, which "
      + "is a different electorate again. Section 4 applies the finding only inside the "
      + "band."
      + "<br><br><b>And the one claim that does not transfer.</b> Hispanic turnout. Harris "
      + "has Hispanic early voters up 100% and their share of the early vote going 18% to "
      + "25%; Tarrant has Hispanic voters turning out <i>behind</i> the county, 39% "
      + "against 47%. Harris is 31.7% Hispanic and Tarrant 21.6%. So the engagement "
      + "finding travels and the Hispanic finding does not, which is the split this whole "
      + "tab keeps arriving at.");
  }

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
    var wide = !NARROW;
    var W = wide ? 720 : 360, L = wide ? YR + 150 : 8, R = wide ? 78 : 10;
    var ROW = wide ? 30 : 44, T = wide ? 38 : 46;
    var H = T + rows.length * ROW + 34;
    var lo = -8, hi = 26;
    var xs = function (v) { return L + (v - lo) / (hi - lo) * (W - L - R); };
    var s2 = svg(W, H, "Where the banked vote lands and where election day drags it");
    (wide ? [-5, 0, 5, 10, 15, 20, 25] : [-5, 0, 10, 20]).forEach(function (t) {
      s2 += line(xs(t), T - 10, xs(t), H - 22, t === 0 ? "zl" : "gl")
         + txt(xs(t), T - 16, t === 0 ? "even" : (t > 0 ? "R+" : "D+") + Math.abs(t),
               "tk", "middle");
    });
    s2 += '<defs><marker id="txar" viewBox="0 0 8 8" refX="7" refY="4" '
       + 'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
       + '<path d="M0,0 L8,4 L0,8 z" fill="context-stroke"/></marker></defs>';
    s2 += txt(wide ? YR : 8, H - 10,
              "\u25cf banked    \u25cb where it finished", "lgd")
       + txt(wide ? YR + 190 : 8, H - (wide ? 10 : 0),
             wide ? "arrow shows where election day took it \u2014 red toward "
                    + "Republicans, blue toward Democrats"
                  : "arrow: where election day took it", "lgd");
    var i = 0;
    years.forEach(function (y) {
      rows.filter(function (r) { return r.y === y; }).forEach(function (r, j) {
        var yy = T + 8 + i * ROW; i++;
        var cname = r.c.replace("President/Vice-President", "President")
                       .replace("U. S. Senator", "U.S. Senate");
        if (wide) {
          if (j === 0) {
            s2 += txt(8, yy + 4, String(y), "lbb")
               + txt(8, yy + 16, y === 2022 ? "midterm" : "presidential", "sub");
          }
          s2 += txt(L - 12, yy + 4, cname, "lb", "end");
        } else {
          s2 += txt(8, yy - 14, y + "  " + cname, "lbb");
        }
        // The arrow carries the direction, so red and blue keep meaning Republican and
        // Democratic. Colouring the DOTS by mode made the 2024 Senate row read as a
        // contradiction: a blue "banked" dot sitting at the most Republican point.
        var toR = r.d > r.e;
        var ax0 = xs(r.e) + (toR ? 7 : -7), ax1 = xs(r.d) + (toR ? -3 : 3);
        s2 += '<line x1="' + ax0 + '" y1="' + yy + '" x2="' + ax1 + '" y2="' + yy
           + '" stroke="' + (toR ? RC : DC) + '" stroke-width="2.5" opacity="0.85" '
           + 'marker-end="url(#txar)"/>';
        s2 += '<circle cx="' + xs(r.f) + '" cy="' + yy + '" r="4.5" fill="none" '
           + 'stroke="currentColor" stroke-width="1.5"/>';
        s2 += '<circle cx="' + xs(r.e) + '" cy="' + yy + '" r="5.5" fill="currentColor"/>';
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

    return card("tx-modes", "Section 2 · slide 7 · what election day does to it",
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
    return card("tx-banked", "Section 5 · slide 3 · the banked lead",
      "What election day would have to do",
      "Read down to the banked lead Texas reports, then across to the election-day margin "
      + "you find plausible. Election day is only " + ((1 - SHARE) * 100).toFixed(1)
      + "% of the vote, so the banked lead carries " + (SHARE / (1 - SHARE)).toFixed(1)
      + " times its weight.",
      '<div class="scroll"><table class="txtbl"><thead>' + head + "</thead><tbody>" + body
      + "</tbody></table></div>"
      + '<div class="scroll"><table class="txtbl" style="margin-top:12px"><thead><tr><th>If election day runs</th>'
      + "<th>the model implies an early margin of</th><th>i.e. a banked lead of</th></tr>"
      + "</thead><tbody>"
      + [["2024-like, R+5.17", 5.17], ["midpoint, R+10", 10], ["2022-like, R+16.00", 16]]
        .map(function (p) {
          var early = (-0.65 - (1 - SHARE) * p[1]) / SHARE;
          return "<tr><td>" + p[0] + '</td><td class="num dem">' + mgn(early)
            + '</td><td class="num dem">D+' + n0(-early / 100 * PROJ.banked) + "</td></tr>";
        }).join("") + "</tbody></table></div>",
      "The whole R+5 to R+22 range is worth about 4.1 points of final margin, which is why "
      + "the 7pm number decides this. <b>Do not read 140,000 as a prediction.</b> It is "
      + "roughly the break-even banked lead against a 2024-style election day — the "
      + "line the model has to beat, not where the model lands. The model itself is asking "
      + "for about 194,000 banked on that same assumption, and 463,000 if election day "
      + "looks like the 2022 midterm.");
  }

  /* ================================================= 4. where every estimate lands */
  /* ================================ 0b. every method, and where each one lands */
  /* The summary that opens the tab. These are not fifteen opinions, they are four
     families of method that share no inputs. The primaries read ballots cast in March
     against November margins over seven cycles - no interviews, no demographics. The
     polls read interviews taken this week. The model reads citizen voting-age population
     and a per-group shift - no primary vote, no poll. They arrive at the same place
     anyway, and arriving at the same place from unshared inputs is the whole reason to
     believe any of it.

     The early vote gets a block with no dot in it, on purpose. Every number here is a
     FINAL margin; the early vote produces a tie BAND on tonight's early margin, which is
     a different axis. Plotting it here would be the same unit error as reading net votes
     as points of margin. It is the test, and it is the one route that settles rather
     than estimates - so it is named in its place in the order and left empty. */
  function methodsCard() {
    var rows = (D.meth || []).map(function (r) {
      return {fam: r.family, reads: r.reads, label: r.label,
              kind: (r.kind || "estimate"), m: num(r.margin_R)};
    }).filter(function (r) { return r.kind === "test" || r.m != null; });
    if (!rows.length) return "";
    var fams = [];
    rows.forEach(function (r) {
      var f = fams.filter(function (x) { return x.name === r.fam; })[0];
      if (!f) { f = {name: r.fam, reads: r.reads, rows: []}; fams.push(f); }
      f.rows.push(r);
    });
    function med(a) {
      var q = a.slice().sort(function (x, y) { return x - y; }), n = q.length;
      return n % 2 ? q[(n - 1) / 2] : (q[n / 2 - 1] + q[n / 2]) / 2;
    }
    fams.forEach(function (f) {
      var v = f.rows.filter(function (r) { return r.m != null; })
                    .map(function (r) { return r.m; });
      f.n = v.length;
      if (!v.length) return;
      f.lo = Math.min.apply(null, v); f.hi = Math.max.apply(null, v); f.mid = med(v);
    });
    var pts = rows.filter(function (r) { return r.m != null; }).map(function (r) { return r.m; });
    var allMed = med(pts);
    var famMed = med(fams.filter(function (f) { return f.n; })
                          .map(function (f) { return f.mid; }));

    var lo = -8, hi = 3;
    var s;
    if (NARROW) {
      /* Phone geometry: nothing lives in a left gutter, because a 345px gutter inside a
         375px screen shrinks every label to about six pixels. Each route gets its own
         line with the label above the axis and the dot on it. */
      var W = 360, R0 = 8, R1 = 352, top = 26;
      var ROW = 27, HDR = 34, GAP = 12;
      var H = top + fams.reduce(function (a, f) {
        return a + HDR + f.rows.length * ROW + GAP;
      }, 0) + 8;
      var xs = function (v) { return R0 + (v - lo) / (hi - lo) * (R1 - R0); };
      s = svg(W, H, "Four families of method for pricing the Texas Senate race, and "
                  + "where each one lands");
      [-8, -6, -4, -2, 0, 2].forEach(function (t) {
        s += line(xs(t), 16, xs(t), H - 6, t === 0 ? "zl" : "gl")
           + txt(xs(t), 11, t === 0 ? "even" : mgn(t, 0), "tk", "middle");
      });
      s += '<line x1="' + xs(allMed) + '" y1="16" x2="' + xs(allMed) + '" y2="' + (H - 6)
         + '" stroke="' + sideCol(allMed) + '" stroke-width="2.5" opacity="0.28"/>';
      var y = top;
      fams.forEach(function (f) {
        s += txt(R0, y + 10, f.name, "lbb");
        if (f.n) {
          if (f.hi > f.lo) {
            s += '<line x1="' + xs(f.lo) + '" y1="' + (y + 22) + '" x2="' + xs(f.hi)
               + '" y2="' + (y + 22) + '" class="cn"/>';
          }
          s += '<circle cx="' + xs(f.mid) + '" cy="' + (y + 22) + '" r="5" fill="'
             + sideCol(f.mid) + '"/>'
             + txt(R0, y + 26, "median " + mgn(f.mid), "sub");
        } else {
          s += txt(R0, y + 24, "no estimate — it is the test", "sub");
        }
        y += HDR;
        f.rows.forEach(function (r) {
          if (r.m == null) {
            s += txt(R0, y + 11, "settles tonight, see the banked-vote card", "sub");
            y += ROW; return;
          }
          s += txt(R0, y + 10, r.label, "lb")
             + '<circle cx="' + xs(r.m) + '" cy="' + (y + 20) + '" r="3.4" fill="'
             + sideCol(r.m) + '" opacity="0.8"/>'
             + txt(xs(r.m) + (r.m < 0 ? 7 : -7), y + 24, mgn(r.m), "tk",
                   r.m < 0 ? "start" : "end");
          y += ROW;
        });
        y += GAP;
      });
      s += "</svg>";
    } else {
      var HDR2 = 25, ROW2 = 19, GAP2 = 10, W2 = 760, L = 345, RM = 62, top2 = 30;
      var H2 = top2 + fams.reduce(function (a, f) {
        return a + HDR2 + f.rows.length * ROW2 + GAP2;
      }, 0) + 14;
      var xs2 = function (v) { return L + (v - lo) / (hi - lo) * (W2 - L - RM); };
      s = svg(W2, H2, "Four families of method for pricing the Texas Senate race, and "
                    + "where each one lands");
      [-8, -6, -4, -2, 0, 2].forEach(function (t) {
        s += line(xs2(t), 18, xs2(t), H2 - 11, t === 0 ? "zl" : "gl")
           + txt(xs2(t), 13, t === 0 ? "even" : mgn(t, 0), "tk", "middle");
      });
      s += '<line x1="' + xs2(allMed) + '" y1="18" x2="' + xs2(allMed) + '" y2="'
         + (H2 - 11) + '" stroke="' + sideCol(allMed) + '" stroke-width="2.5" opacity="0.28"/>';
      var y2 = top2;
      fams.forEach(function (f) {
        s += txt(0, y2 + 9, f.name, "lbb") + txt(0, y2 + 20, "reads: " + f.reads, "sub");
        if (f.n) {
          if (f.hi > f.lo) {
            s += '<line x1="' + xs2(f.lo) + '" y1="' + (y2 + 8) + '" x2="' + xs2(f.hi)
               + '" y2="' + (y2 + 8) + '" class="cn"/>';
          }
          s += '<circle cx="' + xs2(f.mid) + '" cy="' + (y2 + 8) + '" r="4.5" fill="'
             + sideCol(f.mid) + '"/>'
             + txt(xs2(f.hi) + 10, y2 + 12, mgn(f.mid), "vl", "start");
        }
        y2 += HDR2;
        f.rows.forEach(function (r) {
          if (r.m == null) {
            s += txt(L - 12, y2 + 12, r.label, "lb", "end")
               + txt(L + 10, y2 + 12, "settles tonight — see the banked-vote card",
                     "sub", "start");
            y2 += ROW2; return;
          }
          s += txt(L - 12, y2 + 12, r.label, "lb", "end")
             + '<circle cx="' + xs2(r.m) + '" cy="' + (y2 + 8) + '" r="3.2" fill="'
             + sideCol(r.m) + '" opacity="0.75"/>'
             + txt(xs2(r.m) + (r.m < 0 ? -8 : 8), y2 + 12, mgn(r.m), "tk",
                   r.m < 0 ? "end" : "start");
          y2 += ROW2;
        });
        y2 += GAP2;
      });
      s += "</svg>";
    }

    return card("tx-methods", "The summary · every source at once",
      "Four ways of pricing this race, and where each one lands",
      "Fourteen routes to a number, grouped into the four sources that actually differ, in "
      + "the order the evidence arrived. <b>The sources share no inputs.</b> The primaries "
      + "read ballots cast in March against November margins over seven cycles — no "
      + "interviews, no demographics. The polls read interviews taken this week. The model "
      + "reads citizen voting-age population and a per-group shift — no primary vote, "
      + "no poll. <b>They land on top of each other anyway.</b> Large dot is the "
      + "source’s median, small dots its individual routes, the bar its spread; the "
      + "vertical rule is the median of all fourteen.",
      s,
      "<b>The median of all fourteen routes is " + mgn(allMed) + ", and the median of the "
      + "three source medians is " + mgn(famMed) + ".</b> Agreement from unshared inputs is "
      + "the only reason to believe any single one of them. A poll can be wrong about who "
      + "turns out; a regression can be wrong about whether the past still applies; a "
      + "composition model can be wrong about how a group shifts. What they cannot easily "
      + "be is wrong in the same direction for the same reason. Where they spread, the "
      + "spread has one name: how far Hispanic voters move."
      + "<br><br><b>Where the picture is weakest.</b> The poll family is the one place the "
      + "routes are not independent of each other — the average is built from those "
      + "same five polls and Morris’s forecast is built on the average, so four of its "
      + "five dots are one reading wearing four hats. And the model family contains a known "
      + "bias in both directions: its published figure moved Black voters +12 off a 91.1% "
      + "base, which is not defensible, and capping that is the R+0.97 dot."
      + "<br><br><b>The early vote has no dot, on purpose.</b> Every number here is a final "
      + "margin. The early vote produces a tie <i>band</i> on tonight’s early margin "
      + "— a different axis — and a tie in the Senate race lands between <b>"
      + mgn(THR_SAFE_D) + "</b> and <b>" + mgn(THR_SAFE_R)
      + "</b>. Putting that on this chart would be the same unit error as reading net votes "
      + "as points of margin. It is also the only route that settles rather than estimates, "
      + "which is why it is named here and left empty.");
  }

  function estimatesCard() {
    var rows = (D.est || []).map(function (r) {
      return {label: r.label, kind: r.kind, m: num(r.margin_R), note: r.note, n: num(r.n)};
    }).filter(function (r) { return r.m != null; });
    rows.sort(function (a, b) { return a.m - b.m; });
    var wide = !NARROW;
    var W = wide ? 720 : 360, L = wide ? 300 : 8, R = wide ? 56 : 16;
    var ROW = wide ? 23 : 34, T = wide ? 26 : 32;
    var H = T + rows.length * ROW + 12;
    var lo = -8, hi = 3;
    var xs = function (v) { return L + (v - lo) / (hi - lo) * (W - L - R); };
    var s = svg(W, H, "Every estimate of the Texas Senate margin");
    (wide ? [-8, -6, -4, -2, 0, 2] : [-8, -4, 0, 2]).forEach(function (t) {
      s += line(xs(t), 16, xs(t), H - 14, t === 0 ? "zl" : "gl")
         + txt(xs(t), 12, t === 0 ? "even" : mgn(t, 0), "tk", "middle");
    });
    rows.forEach(function (r, i) {
      var y = T + i * ROW;
      // on a phone the label goes on its own line: a 300px gutter inside 375px of
      // screen shrinks every label to about six pixels
      var by = wide ? y - 6 : y + 2;
      if (wide) {
        s += txt(L - 10, y + 4, r.label, "lb", "end")
           + rect(Math.min(xs(0), xs(r.m)), by, Math.abs(xs(r.m) - xs(0)), 12,
                  sideCol(r.m), ' rx="2" opacity="0.85"')
           + txt(xs(r.m) + (r.m < 0 ? -8 : 8), by + 10, mgn(r.m), "vl",
                 r.m < 0 ? "end" : "start");
      } else {
        // the value shares the label's line: at the left end of the axis a value drawn
        // beside the bar runs off the edge of the screen
        s += txt(8, y - 6, r.label, "lb")
           + txt(W - 6, y - 6, mgn(r.m), "vl", "end")
           + rect(Math.min(xs(0), xs(r.m)), by, Math.abs(xs(r.m) - xs(0)), 12,
                  sideCol(r.m), ' rx="2" opacity="0.85"');
      }
    });
    s += "</svg>";
    return card("tx-est", "Section 1 · slide 1 · where every poll lands",
      "Where every poll lands",
      "Every non-partisan public poll of this race, their sample-weighted average, and the "
      + "one outside forecast built on them. Nothing of ours is in here \u2014 the regression, the uniform "
      + "swings and the county model each have their own section, and all of them appear "
      + "together in the summary chart at the top. Trafalgar is not here: it is an R-aligned "
      + "house, and a partisan poll does not belong in a dataset and then get argued "
      + "around in a footnote.",
      s,
      "<b>What the spread is and is not.</b> Four houses across four points is an "
      + "ordinary amount of poll disagreement, not a sign that one of them is broken. The "
      + "sample-weighted average is <b>D+5.03</b> across 5,934 interviews, and the next "
      + "card is about whether Texas polls have earned that benefit of the doubt."
      + "<br><br><b>Where our own numbers went.</b> They are not here on purpose: this is "
      + "the section about what people say they will do. The county model is section 4, "
      + "the primary regression is section 2 slide 2, and the summary chart at the top "
      + "puts all four sources on one axis."
      + "<br><br><b>The model&rsquo;s known bias, for when you reach it.</b> The county model moved the whole non-white "
      + "bloc +12, Black voters included. They were already 91.1% Democratic in 2024, so "
      + "+12 there is not a claim anyone can defend; capping it costs Democrats 1.62 "
      + "points and turns D+0.65 into R+0.97. Only the published figure is plotted here, "
      + "so read it as the optimistic end of its own range rather than the centre.");
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
    var W = NARROW ? 360 : 720, H = NARROW ? 260 : 320,
        L = NARROW ? 40 : 54, R = NARROW ? 20 : 46,
        T = NARROW ? 20 : 26, Bm = NARROW ? 50 : 58;
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
    return card("tx-primary", "Section 2 · slide 1 · what actually changed",
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

    var W = NARROW ? 360 : 720, H = NARROW ? 280 : 330,
        L = NARROW ? 46 : 88, R = NARROW ? 24 : 92,
        T = NARROW ? 30 : 40, Bm = NARROW ? 48 : 54;
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
      var W2 = NARROW ? 360 : 720, H3 = NARROW ? 250 : 280,
          L2 = NARROW ? 46 : 88, R2 = NARROW ? 24 : 92,
          T2 = NARROW ? 26 : 34, B2 = NARROW ? 48 : 54;
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
    var cmpTbl = CMP.length ? ('<div class="scroll"><table class="txtbl" style="margin:12px 0"><thead><tr>'
      + "<th>What the primary showed</th><th>2018</th><th>2026</th><th></th>"
      + "</tr></thead><tbody>"
      + CMP.map(function (r) {
          var last = /Senate result/.test(r.input);
          return "<tr" + (last ? ' class="em"' : "") + "><td>" + esc(r.input)
            + '</td><td class="num dim">' + esc(r.y2018) + '</td><td class="num">'
            + esc(r.y2026) + '</td><td class="num dem">'
            + (r.stronger === "2026" ? "2026 higher" : r.stronger === "tie" ? "same" : "")
            + "</td></tr>";
        }).join("") + "</tbody></table></div>") : "";
    return card("tx-primfit", "Section 2 · slide 2 · what the primary implies",
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
      + "better than R+2.57 \u2014 a comparison, which needs no extrapolation at all.</p>"
      + '<p class="txnote" style="border-top:none;padding-top:0">'
      + "<b>The regressions are a check on that, not the argument.</b> Fitted three ways "
      + "against every past cycle, they give:</p>"
      + '<div class="scroll"><table class="txtbl" style="margin:10px 0"><thead><tr><th>What you regress on</th>'
      + "<th>Cycles</th><th>Explains</th><th>2026</th></tr></thead><tbody>"
      + fits.map(function (q) {
          return "<tr" + (q === gro ? ' class="em"' : "") + "><td>" + esc(q.basis)
            + '</td><td class="num">' + q.n + '</td><td class="num">'
            + (q.r2 * 100).toFixed(0) + '%</td><td class="num '
            + (q.pred < 0 ? "dem" : "rep") + '">' + mgn(q.pred, 2) + "</td></tr>";
        }).join("") + "</tbody></table></div>",
      "<b>All three straddle even, against a state whose last three cycles average "
      + "R+10.09 and whose last four midterms average R+11.66.</b> They disagree by three "
      + "points, which is the honest uncertainty, and they agree on the thing that matters: "
      + "nothing in this primary looks like a normal Texas midterm."
      + "<br><br><b>What would break the comparison.</b> 2018 had Beto O’Rourke; 2026 "
      + "has a different opponent, and the candidates do not transfer. The primary inputs "
      + "match and improve; the people do not."
      + "<br><br><b>The real counterexample is 2020, and it is already priced in.</b> "
      + "Democrats won that primary too — 2,094,428 to 2,017,167, a share of "
      + "<b>50.94%</b>, only 0.76 points below 2026’s 51.70% — and then lost that "
      + "November by 5.58. That is the strongest argument against this card. It is also "
      + "one of the five cycles inside the all-cycles fit above, which is why that fit "
      + "lands at R+0.10 and not somewhere friendlier, and it is the reason the "
      + "midterm-only fit is a separate row: <b>2020 was a presidential year with Trump on "
      + "the ballot</b>, not a midterm reacting to him."
      + "<br><br><b>And 2020 carried none of what 2026 carries</b> — no ICE shooting "
      + "in Houston, no most-expensive-October-on-record at the pump, no Venezuela, and "
      + "Trump himself on the ballot rather than being the thing voters are answering. "
      + "None of those can be priced into a regression, which cuts both ways: these fits "
      + "are built on primary turnout alone and cannot see them. If they are worth "
      + "anything, they are worth it on top of a number that already straddles even."
      + "<br><br><b>One correction.</b> This card used to call Paxton “a Republican "
      + "nominee under indictment”. He is not, and has not been since June 2025, when "
      + "the securities-fraud charges that hung over him from 2015 were dismissed after he "
      + "completed a pretrial-diversion agreement — no plea, no admission of guilt. "
      + "What is true is the impeachment: the Texas House impeached him in 2023 and the "
      + "Senate acquitted him. The measured version of the candidate problem is two cards "
      + "down, where he runs 9.15 points behind his own ticket in the primary.");
  }

  function baselineCard() {
    /* The old version drew a hollow dot and a filled dot and explained which was which
       only in the prose below, labelled the value of one of them and not the other, and
       never showed the swing it had applied - so the reader could see the answer but not
       the arithmetic that produced it. Every quantity is now on the chart: the result
       then, the swing added, and where that lands in 2026. */
    var rows = (D.base || []).map(function (r) {
      return {label: r.baseline, year: r.year, then: num(r.margin_then_R),
              nat: num(r.national_then_R), swing: num(r.swing_to_2026),
              now: num(r.implied_2026_R)};
    }).filter(function (r) { return r.then != null && r.now != null; })
      .sort(function (a, b) { return a.now - b.now; });
    if (!rows.length) return "";
    var wide = !NARROW;
    var W = wide ? 760 : 360, L = wide ? 244 : 8, R = wide ? 118 : 8;
    var ROW = wide ? 34 : 56, T = 54;
    var H = T + rows.length * ROW + 18;
    var lo = -12, hi = 16;
    var xs = function (v) { return L + (v - lo) / (hi - lo) * (W - L - R); };
    var s = svg(W, H, "Seven past Texas results, each carried to 2026 by the national "
                    + "swing from its own year");
    [-10, -5, 0, 5, 10, 15].forEach(function (t) {
      s += line(xs(t), T - 16, xs(t), H - 15, t === 0 ? "zl" : "gl")
         + txt(xs(t), H - 4, t === 0 ? "even" : mgn(t, 0), "tk", "middle");
    });
    // an on-chart legend, in words, instead of a sentence underneath
    var lx = wide ? L : 8;
    s += '<circle cx="' + (lx + 5) + '" cy="14" r="4.5" fill="var(--card,#fff)" '
       + 'stroke="currentColor" stroke-width="1.5"/>'
       + txt(lx + 15, 18, "what Texas actually did that year", "lgd");
    s += '<circle cx="' + (lx + 213) + '" cy="14" r="5" fill="currentColor"/>'
       + txt(lx + 223, 18, "what it implies for 2026", "lgd");
    s += txt(lx, 34, "→ the arrow is the national swing from that year to this one",
             "lgd");
    if (wide) s += txt(W - R + 12, 18, "swing added", "lgd");
    s += '<defs><marker id="baseArr" viewBox="0 0 10 10" refX="9" refY="5" '
       + 'markerWidth="5" markerHeight="5" orient="auto-start-reverse">'
       + '<path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" opacity="0.45"/>'
       + "</marker></defs>";
    rows.forEach(function (r, i) {
      var y = T + (wide ? 12 : 26) + i * ROW;
      if (wide) s += txt(L - 14, y + 4, r.label, "lb", "end");
      else s += txt(8, y - 14, r.label, "lb");
      s += '<line x1="' + xs(r.then) + '" y1="' + y + '" x2="' + xs(r.now) + '" y2="' + y
         + '" stroke="currentColor" stroke-width="1.5" opacity="0.45" '
         + 'marker-end="url(#baseArr)"/>';
      s += '<circle cx="' + xs(r.then) + '" cy="' + y + '" r="4.5" fill="var(--card,#fff)" '
         + 'stroke="currentColor" stroke-width="1.5"/>';
      s += '<circle cx="' + xs(r.now) + '" cy="' + y + '" r="5.5" fill="'
         + sideCol(r.now) + '"/>';
      // BOTH ends carry their number now, not just the filled one
      s += txt(xs(r.then) + (r.then > r.now ? 10 : -10), y - 8, mgn(r.then, 2), "tk",
               r.then > r.now ? "start" : "end");
      s += '<text x="' + (xs(r.now) + (r.now < r.then ? -10 : 10)) + '" y="' + (y + 4)
         + '" text-anchor="' + (r.now < r.then ? "end" : "start") + '" class="vl" fill="'
         + sideCol(r.now) + '">' + mgn(r.now, 2) + "</text>";
      if (wide && r.swing != null) {
        s += txt(W - R + 12, y + 4, (r.swing > 0 ? "D+" : "R+")
                 + Math.abs(r.swing).toFixed(1), "tk");
      } else if (r.swing != null) {
        s += txt(W - 8, y - 14, "swing " + (r.swing > 0 ? "D+" : "R+")
                 + Math.abs(r.swing).toFixed(1), "sub", "end");
      }
    });
    s += "</svg>";
    return card("tx-base", "Section 1 · slide 6 · why the methods disagree",
      "Where Texas lands depends on which past race you start from",
      "<b>How to read each row.</b> The hollow dot is what Texas actually did in that "
      + "race. The arrow adds the national swing between <i>that</i> year and this one. "
      + "The filled dot is where that lands in 2026, and it is the only number here that "
      + "is a prediction \u2014 the other two are arithmetic."
      + "<br><br>This year\u2019s generic ballot is <b>D+8.5</b>, the median of seven "
      + "aggregators the night before, spanning D+7.0 to D+10.8; every point of it moves "
      + "every row one for one. The swings differ by row because each year had its own "
      + "national environment to swing <i>from</i>: 2018 was already a strong Democratic "
      + "year nationally, so it barely moves, while 2024 was a Republican one and moves "
      + "ten points.",
      s,
      "Which year you start from moves the answer by more than any demographic lever on "
      + "this tab. Starting from the 2024 Senate is the harshest available choice, and it "
      + "is the one the county model makes.");
  }

  /* ================================================== 7. the Paxton drag */
  /* The Paxton-Trump effect. Two things are inside Talarico's lead and they come from
     opposite places, which is why the card exists: the ENVIRONMENT, which is national and
     is Trump, and the CANDIDATE, which is local and is Paxton. The governor's race
     separates them. Abbott against Hinojosa is a generic Texas Republican against a
     generic Texas Democrat on the same questionnaires - and it is D+0.11, dead even. Of
     Talarico's 5.03 points, 4.92 is the gap to his own ticket.

     It also carries the haircut table, because this is the only part of the poll evidence
     the three-to-four point miss cannot reach. */
  /* Sensitising the one assumption doing the most work. Every figure on the polls
     cards applies a three-to-four point haircut taken from races with TRUMP ON THE
     BALLOT to a race where he is not on it. All four of the big misses are
     presidential years; both of the Trump-off-ballot races are in the other set, and
     they average -1.87. Conditioning on the thing that is actually true of 2026 is worth
     5.92 points, and it runs the friendly way - which is why the rest of the tab is
     conservative rather than neutral. */
  function haircutCard() {
    var R = (D.hair || []).map(function (r) {
      return {s: r.scenario, h: num(r.haircut), on: r.trump_on_ballot,
              t: num(r.talarico_margin_R), g: num(r.hinojosa_margin_R)};
    }).filter(function (r) { return r.h != null; });
    if (!R.length) return "";
    R.sort(function (a, b) { return a.h - b.h; });
    var wide = !NARROW;
    var W = wide ? 760 : 360, L = wide ? 46 : 38, RM = wide ? 104 : 14;
    var T = wide ? 106 : 130, Bm = 50, H = wide ? 400 : 380;
    var lo = -5, hi = 5.2, vlo = -10, vhi = 6;
    var xs = function (v) { return L + (v - lo) / (hi - lo) * (W - L - RM); };
    var ys = function (v) { return T + (v - vlo) / (vhi - vlo) * (H - T - Bm); };
    var TAL = "var(--tal,#6b4fbb)", HIN = "var(--hin,#0f8f8f)";
    var s2 = svg(W, H, "Both Texas races across every polling haircut ever measured");
    [-10, -5, 0, 5].forEach(function (v) {
      s2 += line(L, ys(v), W - RM, ys(v), v === 0 ? "zl" : "gl")
         + txt(L - 6, ys(v) + 4, v === 0 ? "even" : mgn(v, 0), "tk", "end");
    });
    for (var t = -4; t <= 5; t += 2) {
      s2 += line(xs(t), T, xs(t), H - Bm, "gl")
         + txt(xs(t), H - Bm + 18, (t > 0 ? "+" : "") + t, "tk", "middle");
    }
    s2 += txt(L, H - 12, "the polling haircut applied to BOTH races → "
              + "more generous to Republicans", "lgd");
    s2 += txt(0, T - 14, "statewide margin", "lgd");
    // the six measured misses, marked and split by whether Trump was on the ballot
    var seen = {};
    R.filter(function (r) { return r.on; }).forEach(function (r, i) {
      if (seen[r.h]) return; seen[r.h] = 1;
      var y = 22 + i * 14;
      var on = r.on === "yes";
      s2 += line(xs(r.h), y + 4, xs(r.h), T - 4, "gl")
         + '<circle cx="' + xs(r.h) + '" cy="' + y + '" r="3.5" fill="'
         + (on ? RC : DC) + '"/>'
         + txt(xs(r.h) + (xs(r.h) > W / 2 ? -7 : 7), y + 4,
               r.s.split(" — ")[0] + (on ? "  Trump ON" : "  Trump off"), "sub",
               xs(r.h) > W / 2 ? "end" : "start");
    });
    var path = function (key, col) {
      return '<polyline points="' + R.map(function (r) {
        return xs(r.h) + "," + ys(r[key]); }).join(" ")
        + '" fill="none" stroke="' + col + '" stroke-width="2.5" opacity="0.9"/>';
    };
    s2 += path("g", HIN) + path("t", TAL);
    [[5.03, TAL, "Talarico"], [0.11, HIN, "Hinojosa"]].forEach(function (b) {
      if (b[0] > hi) return;
      s2 += '<line x1="' + xs(b[0]) + '" y1="' + T + '" x2="' + xs(b[0]) + '" y2="'
         + ys(0) + '" stroke="' + b[1] + '" stroke-width="1" stroke-dasharray="3 3" '
         + 'opacity="0.75"/>'
         + '<circle cx="' + xs(b[0]) + '" cy="' + ys(0) + '" r="4.5" fill="' + b[1] + '"/>'
         + '<text x="' + xs(b[0]) + '" y="' + (T - 8) + '" text-anchor="middle" '
         + 'class="vl" fill="' + b[1] + '">' + b[2] + " loses past +" + b[0] + "</text>";
    });
    if (wide) {
      s2 += '<text x="' + (W - RM + 10) + '" y="' + (ys(R[R.length - 1].t) + 4)
         + '" class="lbb" fill="' + TAL + '">Talarico</text>'
         + '<text x="' + (W - RM + 10) + '" y="' + (ys(R[R.length - 1].g) + 4)
         + '" class="lbb" fill="' + HIN + '">Hinojosa</text>';
    }
    s2 += "</svg>";
    var tbl = '<div class="scroll"><table class="txtbl" style="margin-top:12px"><thead>'
      + "<tr><th>Haircut</th><th>Trump on the ballot?</th><th>Talarico</th>"
      + "<th>Hinojosa</th><th>Carries</th></tr></thead><tbody>"
      + R.map(function (r) {
          return "<tr" + (/mean/.test(r.s) ? ' class="em"' : "") + "><td>" + esc(r.s)
            + '</td><td class="dim">' + (r.on === "yes" ? "yes" : (r.on === "no" ? "no" : "—"))
            + '</td><td class="num ' + (r.t < 0 ? "dem" : "rep") + '">' + mgn(r.t)
            + '</td><td class="num ' + (r.g < 0 ? "dem" : "rep") + '">' + mgn(r.g)
            + '</td><td class="' + (r.carries === "both" ? "dem" : "dim") + '">'
            + esc(r.carries || (r.t < 0 && r.g < 0 ? "both" : "Talarico only"))
            + "</td></tr>";
        }).join("") + "</tbody></table></div>";

    return card("tx-haircut", "Section 1 · slide 3 · how much the haircut is assuming",
      "The haircut comes from races with Trump on the ballot. This one does not have him",
      "<b>This is the single assumption doing the most work anywhere on this tab, so it "
      + "gets its own slide.</b> Every figure on the previous card applies a three-to-four "
      + "point correction to the polls. That correction is measured almost entirely from "
      + "races where Trump was <i>on the ballot</i>. 2026 is not one of those. Each line "
      + "is one race&rsquo;s margin across every haircut; the marks above the plot are the "
      + "six measured misses, red where Trump was on the ballot and blue where he was not.",
      s2 + tbl,
      "<b>The conditioning is worth 5.92 points.</b> The four presidential-year misses "
      + "average <b>+4.05</b> and every one of them had Trump on the ballot. The two "
      + "midterm misses average <b>−1.87</b> and neither did. 2026 is a midterm with "
      + "no Trump on the ballot, so the defensible prior is the second number, not the "
      + "first. The rest of this tab uses the first anyway, which is a choice to be "
      + "conservative rather than a reading of the evidence."
      + "<br><br><b>What that does to the Senate race: nothing, at any value.</b> "
      + "Talarico only loses once the haircut exceeds <b>5.03</b> — larger than any "
      + "of the six misses ever measured in Texas, including the worst, 2024&rsquo;s "
      + "presidential +4.68. There is no haircut on this chart that beats him. That is a "
      + "stronger claim than “he survives the full haircut”, which is what the "
      + "rest of the tab says."
      + "<br><br><b>And what it does to the governor&rsquo;s race: everything.</b> "
      + "Hinojosa loses once the haircut exceeds <b>0.11</b> — smaller than five of "
      + "the six. On the Trump-off-ballot prior of −1.87 she wins by 1.98. On 2018, "
      + "the closest analogue there is, she wins by 4.34. On the Trump-on-ballot prior "
      + "she loses by 3.94. <b>Her race is not close to a coin flip in any underlying "
      + "sense — it is a straight bet on which column 2026 belongs in</b>, and every "
      + "lever in Section 4 exists only because the tab assumes the Republican-friendly "
      + "column."
      + "<br><br><b>Why the tab stays conservative anyway.</b> Two observations are not a "
      + "pattern, they are two observations, and they point opposite ways — 2022 at "
      + "+0.50 and 2018 at −4.23. Conditioning on Trump-off-ballot is the better "
      + "theory but it rests on a sample of two, while the Trump-on-ballot figure rests "
      + "on four that agree to within 1.5 points of each other. The honest position is "
      + "that the friendly reading is better reasoned and worse evidenced, so the tab "
      + "quotes the unfriendly one and this slide says what that costs."
      + "<br><br><b>Read tonight against this.</b> If Texas comes in materially better "
      + "than the modelled figures, the explanation is most likely here — not in the "
      + "Hispanic vote, not in rural turnout, but in a four-point correction borrowed "
      + "from elections Trump was standing in.");
  }

  function paxtonCard() {
    var SC = senateCharts();
    // the Trump half: four conditions 2018 did not carry, sourced and dated. This used
    // to be a slide of its own in section 2, which put the environment half of this
    // argument three slides away from the candidate half.
    var CO = (D.only || []).map(function (r) {
      return {c: r.condition, w: r.what_2026_has, src: r.source};
    }).filter(function (r) { return r.w; });
    var coTbl = CO.length ? ('<div class="scroll"><table class="txtbl" '
      + 'style="margin-top:14px"><thead><tr><th>What 2018 did not have</th><th>2026</th>'
      + "<th>Source</th></tr></thead><tbody>"
      + CO.map(function (r) {
          return "<tr><td><b>" + esc(r.c) + "</b></td><td>" + esc(r.w)
            + '</td><td class="dim">' + esc(r.src) + "</td></tr>";
        }).join("") + "</tbody></table></div>") : "";
    var SEN = -5.03, GOV = -0.11;
    var CUTS = [["No haircut — the polls as published", 0],
                ["2022-like, the friendliest midterm miss", 0.50],
                ["All six races, mean", 2.08],
                ["The five that missed toward Democrats, mean", 3.34],
                ["Presidential years, 4-for-4 mean", 4.05]];
    var hairTbl = '<div class="scroll"><table class="txtbl" style="margin-top:14px">'
      + "<thead><tr><th>Haircut applied to BOTH races</th><th>Paxton / Talarico</th>"
      + "<th>Abbott / Hinojosa</th><th>Talarico runs ahead by</th></tr></thead><tbody>"
      + CUTS.map(function (c) {
          var sv = SEN + c[1], gv = GOV + c[1];
          return "<tr" + (c[1] === 4.05 ? ' class="em"' : "") + "><td>" + esc(c[0])
            + '</td><td class="num ' + (sv < 0 ? "dem" : "rep") + '">' + mgn(sv)
            + '</td><td class="num ' + (gv < 0 ? "dem" : "rep") + '">' + mgn(gv)
            + '</td><td class="num"><b>' + (GOV - SEN).toFixed(2) + "</b></td></tr>";
        }).join("")
      + "</tbody></table></div>";

    return card("tx-paxton", "Section 1 · slide 4 · the Paxton–Trump effect",
      "Almost all of Talarico’s lead is Paxton",
      "<b>The same four polls asked about the governor’s race too</b> — same "
      + "questionnaires, same 5,934 respondents, same field period. Abbott against "
      + "Hinojosa is a generic Texas Republican against a generic Texas Democrat, so it "
      + "measures the national environment landing in Texas. Paxton against Talarico "
      + "measures that plus the two candidates. The difference between them is the part "
      + "that is about the people on the ballot and nothing else.",
      SC.sengov + hairTbl + SC.ticket + coTbl,
      "<b>The decomposition.</b> Abbott against Hinojosa is <b>D+0.11</b> — dead "
      + "even. Paxton against Talarico is <b>D+5.03</b>. So of Talarico’s five "
      + "points, <b>4.92 of them are the gap to his own ticket</b>, and the Trump "
      + "environment in Texas, measured by the race that has no Paxton in it, is a tie. "
      + "Talarico runs ahead of Hinojosa in all four polls — YouGov +5.0, Kreate "
      + "+5.0, NYT/Siena +6.0, AtlasIntel +4.0 — and in two of them Abbott leads "
      + "while Talarico leads, the same respondents splitting their ticket on the same "
      + "page."
      + "<br><br><b>The polling miss cancels in that difference.</b> A systematic error "
      + "is a property of who answers a poll, not of which race they are asked about, so "
      + "it hits both questions by the same amount and subtracts out. The table above is "
      + "the proof: apply the full presidential-year haircut and the Senate race falls "
      + "from D+5.03 to D+0.98 and the Governor’s from D+0.11 to R+3.94 — but the "
      + "gap between them is <b>4.92 on every single row</b>. It is the one number on "
      + "this tab that a polling error cannot touch."
      + "<br><br><b>And it is bigger than either thing that could undo it.</b> The "
      + "candidate effect is 4.92. The polling miss is 3.34 to 4.05. The entire "
      + "election-day tie band — everything the un-banked quarter of the vote can do "
      + "to the result — is 2.27."
      + "<br><br><b>Texas has done this before, which is the fourth figure.</b> In 2018 "
      + "Cruz beat O’Rourke by 2.57 while the rest of the statewide ticket ran R+7.42 "
      + "— the Senate race was <b>4.85</b> points friendlier to Democrats than the "
      + "same voters’ other choices that day. In 2024 Cruz beat Allred by 8.50 against "
      + "a ticket median of R+16.37, a gap of <b>7.87</b>. 2020 is the exception, 0.32 "
      + "the other way. Three of four — and 2026’s 4.92 lands within a tenth of a "
      + "point of 2018’s 4.85."
      + "<br><br><b>What none of this says.</b> The gap fixes where Talarico sits "
      + "relative to his ticket, not where the ticket sits. He can run 4.92 ahead of "
      + "Hinojosa and both lose — roughly what the full haircut describes, D+0.98 and "
      + "R+3.94. <b>The gap is the robust number and the level is the fragile one</b>, "
      + "which is the opposite of how this race is usually discussed."
      + '<span class="txrule"></span>'
      + "<b>And where the Trump half shows up.</b> The environment is not "
      + "nothing — it is what moved Texas from R+8.50 in the 2024 Senate race to a "
      + "tied governor’s race, which is a swing of about eight points. It is simply "
      + "not <i>extra</i>: it is already inside the D+0.11, and Paxton is what sits on "
      + "top of it. The four conditions it rests on are the last table above. None can "
      + "be priced into a margin on its own, which is why they are listed rather than "
      + "modelled \u2014 but every one of them runs the same direction, which is why "
      + "2018\u2019s R+2.57 is read here as a floor rather than a match."
      + "<br><br><b>One thing that row does not say, because it is not true.</b> Paxton "
      + "is not under indictment and has not been since June 2025, when the "
      + "securities-fraud charges that hung over him from 2015 were dismissed after he "
      + "completed a pretrial-diversion agreement \u2014 no plea, no admission of guilt. "
      + "The impeachment is the part that is true, and the 9.15 points he ran behind his "
      + "own ticket in March is the part that is measured."
      + "<br><br><b>The rule it gives you for tonight.</b> Talarico is the generic Texas "
      + "Democrat plus 4.92, so he is level when the generic Democrat loses by 4.92. "
      + "That means <b>Talarico wins any night where a generic Texas Democrat loses by "
      + "less than about five points</b>:"
      + "<br>&nbsp;&nbsp;\u2022 a night at R+3 for the ticket \u2192 Talarico <b>D+1.92</b>"
      + "<br>&nbsp;&nbsp;\u2022 a night at R+4 \u2192 Talarico <b>D+0.92</b>"
      + "<br>&nbsp;&nbsp;\u2022 a night at R+4.92 \u2192 Talarico exactly even"
      + "<br>&nbsp;&nbsp;\u2022 a night at R+6 \u2192 Talarico R+1.08, and it is gone"
      + "<br><br>So an R+3 or R+4 night in Texas \u2014 which would read as a bad night "
      + "for Democrats everywhere else on the ballot, and would beat the 2024 Senate "
      + "result by four to five points \u2014 still elects Talarico, on the lag alone. "
      + "That is the single most useful number to hold while the returns come in."
      + "<br><br><b>What this costs the rest of the ballot.</b> None of the 4.92 "
      + "transfers. Hinojosa does not get it, and neither does anyone down-ballot. On "
      + "these polls the governor’s race is a coin flip and the Senate race is not, "
      + "for reasons that have nothing to do with the electorate.");
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
    var AX = NARROW ? 16 : 22;
    var cw = NARROW ? 46 : 58, ch = NARROW ? 30 : 34,
        L = (NARROW ? 66 : 92) + AX, T = NARROW ? 38 : 44,
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
    var wide = !NARROW;
    var W = wide ? 720 : 360, L = wide ? 110 : 8, R = wide ? 62 : 8;
    var ROW = wide ? 34 : 50, T = wide ? 34 : 44;
    var H = T + rows.length * ROW + 12;
    var lo = -95, hi = 72;
    var xs = function (v) { return L + (v - lo) / (hi - lo) * (W - L - R); };
    var s = svg(W, H, "Each group's 2024 measured margin and its 2026 estimate");
    s += line(xs(0), T - 18, xs(0), H - 14, "zl")
       + txt(xs(0), T - 24, "even", "tk", "middle");
    s += txt(wide ? L : 8, 14, "\u2190 more Democratic", "lgd")
       + txt(W - R, 14, "more Republican \u2192", "lgd", "end");
    rows.forEach(function (r, i) {
      var y = T + i * ROW, capped = r.g === "Black";
      var sub = capped ? "at the ceiling"
              : (Math.abs(r.sh) < 0.005 ? "nothing measures 2026"
                 : r.d24.toFixed(0) + "% → " + r.d26.toFixed(0) + "% D");
      if (wide) {
        s += txt(L - 10, y, r.g, "lb", "end") + txt(L - 10, y + 12, sub, "sub", "end");
      } else {
        s += txt(8, y - 20, r.g, "lb") + txt(W - 8, y - 20, sub, "sub", "end");
      }
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
    return card("tx-eth", "Section 3 · slide 1 · where each demographic sits",
      "Where each demographic is, and where the model needs it",
      "Hollow dot is 2024 measured — counted ballots in precincts overwhelmingly one "
      + "demographic by voting-age population, not a poll. Filled dot is the 2026 "
      + "estimate, blue where the demographic moves toward Democrats and red where it "
      + "moves away.",
      s,
      "<b>Asian voters are held where they were last measured, and that row is the "
      + "weakest number on this tab.</b> It sits at D+15.31. Two other measurements of "
      + "Texas Asian voters appear elsewhere in this deck and <i>both say Republican</i>: "
      + "the 2024 Texas exit poll has them <b>R+13</b> (Trump 55, Harris 42, 4% of the "
      + "electorate), and AtlasIntel\u2019s 2026 crosstab has them <b>R+32</b>. That is a "
      + "47-point spread, and the first two both claim to be 2024."
      + "<br><br><b>Why they disagree, and which to believe.</b> The D+15.31 here is "
      + "precinct inference \u2014 counted ballots in precincts that are overwhelmingly "
      + "one group by voting-age population. Texas has very few heavily Asian precincts, "
      + "so this is the thinnest cell in a table built that way. The exit poll is "
      + "self-identified respondents, a different population and a much larger sample. "
      + "AtlasIntel\u2019s R+32 rests on roughly 84 respondents, which is "
      + "<b>\u00b121 points</b> on a margin at 95% \u2014 the direction is probably real, "
      + "the number is not usable. On the balance of evidence Texas Asian voters went "
      + "Republican in 2024, and this row does not reflect that."
      + "<br><br><b>What it is worth.</b> At roughly 5% of the electorate, moving this row "
      + "from D+15.31 to the exit poll\u2019s R+13 is about <b>1.4 points</b> of statewide "
      + "margin toward Republicans. It is left at the published figure rather than "
      + "rewritten here, but it is a known bias in the model\u2019s favour and it belongs "
      + "next to the Black-voter one below, not buried."
      + "<br><br>The historical trend points the same way: this group moved 8.95 points "
      + "toward Republicans between 2018 and 2024. An earlier version anchored them to the "
      + "October generic ballot, which was wrong \u2014 that is a national all-voter "
      + "number sitting well right of where Asian voters vote, so it imported a claim "
      + "rather than removing one."
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
  /* How much the polls on this tab are worth: what they have been worth in Texas
     before, and whether they are moving. Both questions belong together because both
     are about weighting the poll evidence rather than adding to it. */
  function pollTrustCard() {
    var E = (D.perr || []).map(function (r) {
      return {c: r.cycle, k: r.kind, race: r.race, p: r.poll, pm: num(r.poll_margin_R),
              am: num(r.actual_margin_R), err: num(r.error)};
    }).filter(function (r) { return r.err != null; });
    var P = (D.pdate || []).map(function (r) {
      return {n: r.pollster, s: r.start, e: r.end, nn: num(r.n), sc: r.screen,
              m: num(r.margin_R), part: r.partisan === "1", d: num(r.days_to_election)};
    }).filter(function (r) { return r.m != null; }).sort(function (a, b) { return b.d - a.d; });
    if (!E.length && !P.length) return "";
    var errTbl = E.length ? ('<div class="scroll"><table class="txtbl"><thead><tr>'
      + "<th>Texas race</th><th>Type</th><th>Final poll</th><th>Actual</th>"
      + "<th>The poll was</th></tr></thead><tbody>"
      + E.map(function (r) {
          // positive error = the poll was friendlier to Democrats than the result.
          // 2018 is negative and the old table would have printed it as "too D".
          var tooD = r.err > 0;
          return "<tr" + (r.k === "midterm" ? ' class="em"' : "") + "><td>" + esc(r.c)
            + '<br><span class="dim">' + esc(r.race || "") + "</span>"
            + '</td><td class="dim">' + esc(r.k) + '</td><td class="num">' + mgn(r.pm, 1)
            + '</td><td class="num">' + mgn(r.am, 1) + '</td><td class="num '
            + (tooD ? "rep" : "dem") + '">' + Math.abs(r.err).toFixed(2)
            + (tooD ? " too D" : " too R") + "</td></tr>";
        }).join("") + "</tbody></table></div>") : "";
    var dateTbl = P.length ? ('<div class="scroll"><table class="txtbl" style="margin-top:14px"><thead><tr>'
      + "<th>Pollster</th><th>Field dates</th><th>Sample</th><th>Margin</th>"
      + "</tr></thead><tbody>"
      + P.map(function (r) {
          return "<tr><td>" + esc(r.n) + (r.part ? ' <span class="dim">partisan house</span>' : "")
            + '</td><td class="num dim">' + esc(r.s.slice(5)) + " to " + esc(r.e.slice(5))
            + '</td><td class="num">' + n0(r.nn) + " " + esc(r.sc)
            + '</td><td class="num ' + (r.m < 0 ? "dem" : "rep") + '">' + mgn(r.m, 0)
            + "</td></tr>";
        }).join("") + "</tbody></table></div>") : "";
    var SC = senateCharts();

    /* The join between the two halves of this card. A systematic poll error is a
       property of who answers a poll, not of which race they are asked about, so on a
       questionnaire carrying BOTH races it hits each by the same amount and subtracts
       out of the difference. The gap column is the point: it is 4.92 on every row. */
    var SEN = -5.03, GOV = -0.11;
    var CUTS = [["No haircut — the polls as published", 0],
                ["2022-like, the friendliest midterm miss", 0.50],
                ["All six races, mean", 2.08],
                ["The five that missed toward Democrats, mean", 3.34],
                ["Presidential years, 4-for-4 mean", 4.05]];
    var hairTbl = '<div class="scroll"><table class="txtbl" style="margin-top:14px">'
      + "<thead><tr><th>Haircut applied to BOTH races</th><th>Paxton / Talarico</th>"
      + "<th>Abbott / Hinojosa</th><th>Talarico runs ahead by</th></tr></thead><tbody>"
      + CUTS.map(function (c) {
          var sv = SEN + c[1], gv = GOV + c[1];
          return "<tr" + (c[1] === 4.05 ? ' class="em"' : "") + "><td>" + esc(c[0])
            + '</td><td class="num ' + (sv < 0 ? "dem" : "rep") + '">' + mgn(sv)
            + '</td><td class="num ' + (gv < 0 ? "dem" : "rep") + '">' + mgn(gv)
            + '</td><td class="num"><b>' + (GOV - SEN).toFixed(2) + "</b></td></tr>";
        }).join("")
      + "</tbody></table></div>";

    return card("tx-polltrust", "Section 1 · slide 2 · how much the polls are worth",
      "The polls are wrong by three to four points",
      "<b>Two questions about how much to trust the polls above.</b> How wrong final Texas polls have been "
      + "before \u2014 six races, one basis, and a miss that is large and "
      + "one-directional \u2014 and whether these four are drifting. What that miss does NOT "
      + "touch is the next slide.",
      errTbl + dateTbl,
      "<b>THE TAKEAWAY: Texas polls overstate Democrats, and by three to four points.</b> "
      + "Five of these six races missed in the same direction, and the mean of those five "
      + "is <b>3.34 points too Democratic</b>. Narrow it to the four presidential years "
      + "and it is tighter still: 3.14, 4.10, 4.28 and 4.68 — four for four, mean "
      + "<b>4.05</b>, not one of them under three points. This is the most consistent "
      + "finding on the tab and it runs against the argument the rest of it makes."
      + "<br><br><b>Applied to today.</b> The four-poll average is D+5.03. Take the "
      + "three-to-four-point haircut the record says to take and the race lands between "
      + "<b>D+1.0 and D+1.7</b> — still Talarico, with nothing to spare. Take the "
      + "all-six mean of 2.08 instead and it is D+2.95."
      + "<br><br><b>2022 is the weak one inside that group</b>, at half a point, and it is "
      + "the only midterm on the list that fits the pattern at all."
      + "<br><br><b>But the real outlier is 2018, and it is the race most like this "
      + "one.</b> The final RCP average had Cruz by 6.8 and he won by 2.57 — the poll "
      + "was <b>4.23 points too REPUBLICAN</b>, the opposite sign to every other row. "
      + "Measured properly it is 2.01 standard deviations from the mean of the six, "
      + "against 0.50 for 2022, so it is four times the outlier 2022 is. It is also the "
      + "only prior race that matches 2026 on the two things that matter: a midterm, and "
      + "a Democrat running a serious statewide Senate campaign. Apply 2018’s error "
      + "to today and D+5.03 becomes D+9.26."
      + "<br><br><b>So the haircut rule is real, large, and four for four in "
      + "presidential years</b> — every one of them with Trump on the ballot. In "
      + "midterms it has two observations pointing opposite ways, 0.50 one direction and "
      + "4.23 the other. 2026 is a midterm with no Trump on the ballot. The rule says "
      + "D+1; the one comparable race says D+9; there is no third midterm to break it."
      + "<br><br><b>What the four non-partisan polls show over time.</b> They run about "
      + "1.0 points per day toward Talarico, r = \u22120.71 \u2014 NYT/Siena and "
      + "AtlasIntel, the two that finished last, are also the two best for him. Four polls "
      + "cannot prove late movement, and the houses differ in method as well as in date, "
      + "so read it as consistent with a late drift rather than as evidence of one."
      + "<br><br><b>And they are not four independent readings either.</b> The average is "
      + "built from these same four polls and Morris\u2019s forecast is a poll-of-polls "
      + "built on them again, so the polls card\u2019s six rows are four readings. "
      + "NYT/Siena carries more weight than its single row suggests, being the "
      + "largest-sample live-caller in the set.");
  }


  function crosstabCard() {
    /* Eighteen rows in one undifferentiated stack was unreadable, and the right-hand
       column packed both polls into one string. Now grouped - race, age, sex, how they
       voted in 2024, party, where they live - with each poll's number in its own column
       and a phone layout that puts the label on its own line instead of in a gutter. */
    var R = (D.xtab || []).map(function (r) {
      return {grp: r.group || "", g: r.bloc, sh: num(r.share_pct),
              ym: r.yougov_margin_R === "" ? null : num(r.yougov_margin_R),
              am: num(r.atlas_margin_R), ad: num(r.atlas_d), ar: num(r.atlas_r)};
    }).filter(function (r) { return r.am != null; });
    if (!R.length) return "";
    var groups = [];
    R.forEach(function (r) {
      var f = groups.filter(function (x) { return x.name === r.grp; })[0];
      if (!f) { f = {name: r.grp, rows: []}; groups.push(f); }
      f.rows.push(r);
    });

    var wide = !NARROW;
    var W = wide ? 760 : 360, L = wide ? 236 : 8, RM = wide ? 128 : 74, T = 58;
    var ROW = wide ? 25 : 34, HDR = wide ? 26 : 24, GAP = wide ? 8 : 10;
    var H2 = T + groups.reduce(function (a2, f) {
      return a2 + (f.name ? HDR : 4) + f.rows.length * ROW + GAP;
    }, 0) + 20;
    var lo = -100, hi = 100;
    var xs = function (v) { return L + (v - lo) / (hi - lo) * (W - L - RM); };
    var s2 = svg(W, H2, "Texas Senate crosstabs from the two final polls, group by group");
    [-100, -50, 0, 50, 100].forEach(function (t) {
      s2 += line(xs(t), T - 14, xs(t), H2 - 16, t === 0 ? "zl" : "gl")
         + txt(xs(t), H2 - 4, t === 0 ? "even" : mgn(t, 0), "tk", "middle");
    });
    s2 += txt(L, T - 20, "← Talarico", "lgd")
       + txt(W - RM, T - 20, "Paxton →", "lgd", "end");
    // legend
    s2 += '<circle cx="' + ((wide ? L : 8) + 5) + '" cy="12" r="4.5" fill="none" '
       + 'stroke="currentColor" stroke-width="1.5"/>'
       + txt((wide ? L : 8) + 14, 16, "YouGov · 2,141 LV · 26–29 Oct", "lgd")
       + '<circle cx="' + ((wide ? L : 8) + 212) + '" cy="12" r="5" fill="currentColor"/>'
       + txt((wide ? L : 8) + 221, 16,
             "AtlasIntel · 1,678 · 28 Oct–1 Nov", "lgd");
    if (wide) {
      s2 += txt(L - 12, 16, "% of voters", "lgd", "end")
         + txt(W - RM + 10, 16, "YouGov", "lgd") + txt(W - 6, 16, "Atlas", "lgd", "end");
    }
    var y = T;
    groups.forEach(function (f) {
      if (f.name) {
        s2 += txt(wide ? 0 : 8, y + 12, f.name.toUpperCase(), "lgd");
        y += HDR;
      } else { y += 4; }
      f.rows.forEach(function (r) {
        var cy = y + (wide ? 10 : 20);
        // a margin with no idea how many people it covers says nothing: D+88 among a
        // group that is 2% of voters and D+88 among a group that is 20% are different
        // facts. The share goes next to the label, and is blank where none is published.
        var shTxt = r.sh != null ? r.sh + "%" : "\u2014";
        if (wide) {
          s2 += txt(L - 56, cy + 4, r.g, r.g === "Total" ? "lbb" : "lb", "end")
             + '<text x="' + (L - 12) + '" y="' + (cy + 4) + '" text-anchor="end" '
             + 'class="' + (r.sh != null ? "vl" : "sub") + '">' + shTxt + "</text>";
        } else {
          s2 += txt(8, y + 9, r.g + (r.sh != null ? "  \u00b7  " + r.sh + "% of voters" : ""),
                    r.g === "Total" ? "lbb" : "lb");
        }
        if (r.ym != null) {
          s2 += line(xs(r.ym), cy, xs(r.am), cy, "cn")
             + '<circle cx="' + xs(r.ym) + '" cy="' + cy + '" r="4.5" fill="var(--card,#fff)" '
             + 'stroke="currentColor" stroke-width="1.5"/>';
        }
        s2 += '<circle cx="' + xs(r.am) + '" cy="' + cy + '" r="5.5" fill="'
           + sideCol(r.am) + '"/>';
        if (wide) {
          s2 += txt(W - RM + 10, cy + 4, r.ym != null ? mgn(r.ym, 0) : "—", "tk")
             + '<text x="' + (W - 6) + '" y="' + (cy + 4) + '" text-anchor="end" '
             + 'class="vl" fill="' + sideCol(r.am) + '">' + mgn(r.am, 0) + "</text>";
        } else {
          s2 += '<text x="' + (W - 6) + '" y="' + (y + 9) + '" text-anchor="end" '
             + 'class="vl" fill="' + sideCol(r.am) + '">' + mgn(r.am, 0)
             + (r.ym != null ? " / " + mgn(r.ym, 0) : "") + "</text>";
        }
        y += ROW;
      });
      y += GAP;
    });
    s2 += "</svg>";
    var ind = R.filter(function (r) { return r.g === "Independents"; })[0];
    var nv = R.filter(function (r) { return /not vote/i.test(r.g); })[0];
    var hisp = R.filter(function (r) { return r.g === "Hispanic"; })[0];
    var twoWay = ind ? (ind.ad / (ind.ad + ind.ar) * 100) : null;
    return card("tx-xtab", "Section 1 · slide 5 · what the crosstabs say",
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
      + "(D+22 and D+22.1) and on 45\u201364 (D+2 and D+2.0)."
      + "<br><br><b>Where they are far apart, they are far apart on size, not side.</b> "
      + "They differ by 30 points on 18\u201329 \u2014 and both are solidly Democratic, "
      + "D+46 against D+16. Same on women, 17 apart and both Democratic; same on "
      + "Hispanic voters, 11.5 apart and both Democratic. There is exactly one group "
      + "where the two polls disagree about which way it votes, and it is men: YouGov has "
      + "them R+1, AtlasIntel R+15 \u2014 still the same side, just barely. Across all "
      + "eighteen rows the polls never put a group on opposite sides of even. That is a "
      + "much weaker disagreement than the spread suggests: they are arguing about "
      + "margins, not about who is winning which bloc."
      + "<br><br><b>The Asian row is the one number here not to lean on.</b> AtlasIntel "
      + "has Texas Asian voters R+32 and YouGov did not publish the crosstab at all. At "
      + "about 5% of a 1,678 sample that is roughly 84 respondents \u2014 "
      + "<b>\u00b121 points</b> on a margin at 95% confidence. It agrees in direction with "
      + "the 2024 Texas exit poll, which had them R+13, so Republican is probably right "
      + "and R+32 is not a usable figure. The model assumes this group is D+15.31, which "
      + "neither measurement supports; that is taken up on the demographics card."
      + "<br><br><b>The one gap that moves the model.</b> Hispanic voters, <b>D+28 "
      + "against D+16.5</b>. The county model assumes they land at D+29.85, which YouGov "
      + "supports and AtlasIntel does not \u2014 and break-even sits between the two.");
  }

  /* The two charts the Tarrant file actually publishes, drawn the way it draws them
     rather than flattened into tables of mine. The paired bars put each group's share of
     all registered voters against its share of the people who have voted; the stacked
     bars put the primary each voter last chose, D / neither / R, across a full 100%. */
  function pairedBars(rows, label, regLab, votLab) {
    var wide = !NARROW;
    var W = wide ? 760 : 360, L = wide ? 232 : 8, R = wide ? 64 : 56;
    var ROW = wide ? 40 : 54, T = wide ? 30 : 26;
    var H = T + rows.length * ROW + 10;
    var mx = Math.max.apply(null, rows.map(function (r) {
      return Math.max(r.reg, r.vot);
    })) * 1.12;
    var xs = function (v) { return (v / mx) * (W - L - R); };
    var s = svg(W, H, label);
    var y = T;
    s += txt(L, 12, regLab, "lgd") + txt(L + (wide ? 190 : 150), 12, votLab, "lgd");
    s += rect(L, 5, 9, 9, "currentColor", ' opacity="0.22" rx="1"')
       + rect(L + (wide ? 176 : 136), 5, 9, 9, "currentColor", ' opacity="0.6" rx="1"');
    rows.forEach(function (r) {
      if (wide) s += txt(L - 12, y + 13, r.g, "lb", "end");
      else s += txt(8, y + 2, r.g, "lb");
      var top = wide ? y : y + 10;
      s += rect(L, top, xs(r.reg), 9, "currentColor", ' opacity="0.22" rx="1.5"')
         + txt(L + xs(r.reg) + 7, top + 8, r.reg.toFixed(1) + "%", "tk", "start")
         + rect(L, top + 11, xs(r.vot), 9, "currentColor", ' opacity="0.6" rx="1.5"')
         + txt(L + xs(r.vot) + 7, top + 19, r.vot.toFixed(1) + "%", "vl", "start");
      y += ROW;
    });
    s += "</svg>";
    return s;
  }

  function stackedPrimary(rows, label) {
    var wide = !NARROW;
    var W = wide ? 760 : 360, L = wide ? 190 : 8, R = wide ? 78 : 8;
    var ROW = wide ? 36 : 54, T = wide ? 34 : 30;
    var H = T + rows.length * ROW + 12;
    var BW = W - L - R;
    var s = svg(W, H, label);
    s += txt(L, 13, "Democratic primary", "lgd")
       + txt(L + BW / 2, 13, "neither", "lgd", "middle")
       + txt(L + BW, 13, "Republican primary", "lgd", "end");
    var y = T;
    rows.forEach(function (r) {
      var top = wide ? y : y + 16;
      if (wide) {
        s += txt(L - 12, y + 10, r.g, "lb", "end")
           + txt(L - 12, y + 22, n0(r.n) + " voters", "sub", "end");
      } else {
        s += txt(8, y + 4, r.g, "lb")
           + txt(W - 8, y + 4, n0(r.n) + " · " + mgn(r.lean, 1), "vl", "end");
      }
      var x = L;
      [[r.d, DC, 0.85], [r.nei, "currentColor", 0.18], [r.rr, RC, 0.85]].forEach(function (p) {
        var w = p[0] / 100 * BW;
        s += rect(x, top, w, 17, p[1], ' opacity="' + p[2] + '"');
        if (w > 26) {
          s += '<text x="' + (x + w / 2) + '" y="' + (top + 12) + '" text-anchor="middle" '
             + 'class="' + (p[1] === "currentColor" ? "cell" : "cellw") + '">'
             + p[0] + "%</text>";
        }
        x += w;
      });
      if (wide) {
        s += '<text x="' + (L + BW + 10) + '" y="' + (top + 12) + '" class="vl" '
           + 'fill="' + sideCol(r.lean) + '">' + mgn(r.lean, 1) + "</text>";
      }
      y += ROW;
    });
    s += "</svg>";
    return s;
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

    /* This was three different quantities stacked in one column - a gap in points, a
       voter count, and a turnout rate - across fifteen rows mixing voting history with
       age with race, and it rounded the gap to whole numbers so several rows read
       "0 pts ahead". One quantity now: turnout rate. Who is ahead of the county and who
       is behind is then simply which side of the county line a bar ends on, which needs
       no second unit and no label to explain it. The voting-history rows are not in it
       because the file publishes no turnout rate for them - they are the paired bars
       above, which is where they belong. */
    var TURN = AG.map(function (r) {
      return {lab: r.a.replace("-", "–"), t: r.t, n: r.n, kind: "Age"};
    }).concat(G.map(function (r) {
      return {lab: r.g.replace("Asian or Pacific Islander", "Asian / Pacific Islander")
                    .replace("Other or multiracial", "Other or multiracial"),
              t: r.t, n: r.n, kind: "Race and ethnicity"};
    })).filter(function (r) { return r.t != null; });
    var OVERALL = 47.1;
    var wide2 = !NARROW;
    var W = wide2 ? 760 : 360, L = wide2 ? 188 : 8, R = wide2 ? 92 : 8;
    var ROW = wide2 ? 27 : 38, HDR = 26, T = 54;
    var blocks = [];
    TURN.forEach(function (r) {
      var f = blocks.filter(function (x) { return x.name === r.kind; })[0];
      if (!f) { f = {name: r.kind, rows: []}; blocks.push(f); }
      f.rows.push(r);
    });
    var H2 = T + blocks.reduce(function (a2, f) {
      return a2 + HDR + f.rows.length * ROW + 10;
    }, 0) + 16;
    var xs = function (v) { return L + v / 80 * (W - L - R); };
    var s2 = svg(W, H2, "Tarrant County early turnout rate by age and by race, against "
                      + "the county's own rate");
    [0, 20, 40, 60, 80].forEach(function (t) {
      s2 += line(xs(t), T - 16, xs(t), H2 - 14, "gl")
         + txt(xs(t), H2 - 3, t + "%", "tk", "middle");
    });
    // the county's own rate, which is what "ahead" and "behind" were trying to say
    s2 += '<line x1="' + xs(OVERALL) + '" y1="' + (T - 20) + '" x2="' + xs(OVERALL)
       + '" y2="' + (H2 - 14) + '" class="zl"/>'
       + txt(xs(OVERALL), T - 26, "the county: " + OVERALL + "%", "lgd", "middle");
    s2 += txt(wide2 ? 0 : 8, 16, "Share of each group's active registered voters who had "
              + "voted by 30 October", "lgd");
    var y = T;
    blocks.forEach(function (f) {
      s2 += txt(wide2 ? 0 : 8, y + 12, f.name.toUpperCase(), "lgd");
      y += HDR;
      f.rows.forEach(function (r) {
        var top = y + (wide2 ? 4 : 12);
        if (wide2) s2 += txt(L - 12, top + 10, r.lab, "lb", "end");
        else s2 += txt(8, y + 9, r.lab, "lb");
        var ahead = r.t >= OVERALL;
        s2 += rect(xs(0), top, xs(r.t) - xs(0), 13, "currentColor",
                   ' rx="2" opacity="' + (ahead ? "0.52" : "0.22") + '"')
           + txt(xs(r.t) + 8, top + 11, r.t + "%", "vl");
        if (wide2) s2 += txt(W - R + 44, top + 11, n0(r.n), "tk", "end");
        y += ROW;
      });
      y += 10;
    });
    if (wide2) s2 += txt(W - R + 44, T - 26, "voters", "lgd", "end");
    s2 += "</svg>";


    var H = (D.tarrh || []).map(function (r) {
      return {g: r.group, n: num(r.voters), lean: num(r.lean_R), d: num(r.pct_d_primary),
              nei: num(r.pct_neither), rr: num(r.pct_r_primary)};
    }).filter(function (r) { return r.lean != null; });
    var camps = H.length ? stackedPrimary(H, "Tarrant County by the most recent party "
      + "primary each voter chose since 2022: Democratic, neither, Republican") : "";

    return card("tx-tarrant", "Section 2 · slide 3 · the one county we can see",
      "Tarrant County, the only place we can see the 2026 electorate",
      "<b>Source: Chris Tackett, See It. Name It. Fight It., 31 October, on the Tarrant "
      + "County early-vote file.</b> <i>\u201cOver twelve days, 571,950 Tarrant County "
      + "voters cast a ballot in person, and 21,122 more have voted by mail. That\u2019s "
      + "593,072 ballots. In the entire 2022 midterm, early voting and Election Day "
      + "together, 593,172 people voted. We are 100 votes short of all of 2022, and "
      + "Election Day hasn\u2019t happened yet.\u201d</i> The early vote beat 2018 by 32% "
      + "and 2022 by 47%, and reached 90% of a presidential early vote. No other Texas "
      + "county publishes who is voting, so every composition figure elsewhere on this tab "
      + "is an inference and this one is a count.",
      // csTbl and histTbl both went: the stacked bars already carry every share and
      // margin csTbl showed, and the paired bars already carry the three groups
      // histTbl listed. Three figures now, each measuring something different.
      camps
      + pairedBars(HD.map(function (r) {
        return {g: r.g.replace("Sat out the 2022 midterm, then voted in 2024",
                               "Sat out 2022, then voted in 2024"),
                reg: r.reg, vot: r.vot};
      }), "Tarrant County: each group's share of all registered voters against its share "
         + "of the people who have already voted",
         "share of all registered", "share of the voters who have voted")
      + s2,
      "<b>An eight-point swing, in the part of the electorate that leans most "
      + "Republican.</b> In his words: <i>\u201cThat\u2019s a swing of nearly 8 points "
      + "toward Democrats since 2022, in the most Republican-leaning part of the "
      + "electorate, the people who vote early.\u201d</i> The Republican camp fell from "
      + "37.8% of the early vote to 27.2%."
      + "<br><br><b>But that margin is D% minus R%, and it matters how.</b> It is "
      + "simply <b>D% minus R%</b>. The Neither column is not allocated, not split, not "
      + "estimated — it is left out. So <i>D+2.6</i> describes 57% of this "
      + "electorate and is silent on the other 43%."
      + "<br><br><b>Which means the chart understates the shift.</b> Neither grew from "
      + "29.5% of the 2022 early vote to 43.0% of this one, so the pool that D and R are "
      + "drawn from shrank from 70.5% to 57.0%. Both shares fall, so the gap between them "
      + "falls too, <i>with nobody changing their mind</i>. Measure the same thing among "
      + "voters who actually have a primary history and the move is half again as large: "
      + "<b>R+7.23 to D+4.56, a swing of 11.8 points</b>, against the 7.7 the headline "
      + "margin shows."
      + "<br><br><b>And the 43% is the whole ball game.</b> It is 253,121 ballots already "
      + "cast that this measure says nothing whatever about. Every number on this chart "
      + "is a fact about the minority of the electorate that has picked a primary since "
      + "2022. The next card is about the other group, because it is bigger than either "
      + "party and it decides the county."
      + "<br><br><b>Nearly half of this electorate did not vote in the 2022 midterm.</b> The file "
      + "opens with it: <i>\u201c13.1% sat out the 2022 midterm, then voted in 2024, and "
      + "17.9% registered since 2022\u201d</i>, and a further 17.8% were on the rolls in "
      + "2022 and did not vote. Together that is 48.8% \u2014 about 287,000 people in one "
      + "county who sat out the last midterm and have already voted in this one.");
  }

  /* The two Tarrant findings that were sitting in data/tx unused: the precinct swing and
     the primary-history shift. tx_tarrant_precincts.csv and tx_tarrant_history.csv were
     both being fetched on every load and neither was ever drawn, so the strongest thing
     in the file - all four commissioner precincts moving the same direction - was not on
     the page at all.

     The card also answers "they are such a large share they will decide how the county
     goes" with arithmetic rather than adjective. The file groups every voter by the most
     recent party primary they chose since 2022, and publishes a calculator: at 95% party
     loyalty among Democratic primary voters, 91% among Republican ones, and 37% of the
     neither-primary group voting Democratic, it prints Tarrant at D 46.7 / R 53.3.
     Holding its two loyalty figures and solving for the third gives the break-even, and
     feeding 37% back in reproduces its published output to a tenth of a point, which is
     what says the arithmetic is the file's and not mine. */
  /* Tackett's second chart - "Who is in each camp" - and the words around it. This is
     the chart the card was missing: his first chart shows the three camps SIZES, this one
     shows who is IN them, and his finding lives entirely in the second. The Neither
     column sits on the county column line by line; the Republican column does not.

     His slider arithmetic replaces mine. An earlier version of this card computed a
     break-even of 44.3% using 95% Democratic and 91% Republican loyalty, which were not
     his assumptions. His defaults are 95/95 and he publishes the answer himself. Running
     his camp counts at 95/95 reproduces every figure he prints - 13,985 against "about
     14,000", 47.2/52.8 against "about 53 to 47", +28,036 and D+4.8, +24,102, +38,153 -
     which is what says the model here is his and not a lookalike. */
  function tarrantSwingCard() {
    var C = (D.camps || []).map(function (r) {
      return {m: r.metric, u: r.unit, c: num(r.county), d: num(r.dem),
              n: num(r.neither), r: num(r.rep)};
    }).filter(function (r) { return r.c != null; });
    var SL = (D.tsl || []).map(function (r) {
      return {s: r.scenario, lead: num(r.d_lead_votes), m: r.margin, pub: r.published};
    }).filter(function (r) { return r.lead != null; });
    var P = (D.tarr || []).map(function (r) {
      return {p: r.precinct, n: num(r.voted_2026), now: num(r.lean_2026_R),
              then: num(r.lean_2022_R)};
    }).filter(function (r) { return r.now != null && r.then != null; });
    if (!C.length) return "";

    /* --- his table, as he prints it */
    var fmt = function (v, u) {
      return u === "count" ? n0(v) : (u === "years" ? v + "" : v + "%");
    };
    var tbl = '<div class="scroll"><table class="txtbl"><thead><tr><th>&nbsp;</th>'
      + "<th>Tarrant County<br>(active voters)</th><th>Democratic<br>primary voters</th>"
      + "<th>Neither</th><th>Republican<br>primary voters</th></tr></thead><tbody>"
      + C.map(function (r) {
          return "<tr><td>" + esc(r.m) + '</td><td class="num dim">' + fmt(r.c, r.u)
            + (r.m === "Early voters" ? " registered" : "")
            + '</td><td class="num">' + fmt(r.d, r.u)
            + '</td><td class="num"><b>' + fmt(r.n, r.u) + "</b></td>"
            + '<td class="num">' + fmt(r.r, r.u) + "</td></tr>";
        }).join("")
      + "</tbody></table></div>";

    var RW = C.filter(function (r) { return r.u === "pct"; });
    /* The headline claim, on its own, before the three-camp version: the Neither bucket
       IS Tarrant County. Paired bars rather than deviation dots, because "these two bars
       are the same length on every line" is the whole point and a dot at zero does not
       say it as loudly. Largest gap on any line is 3 points; the mean is 1.5. */
    var mirror = "";
    if (RW.length) {
      var wideM = !NARROW;
      var WM = wideM ? 760 : 360, LM = wideM ? 212 : 8, RMM = wideM ? 92 : 64;
      var ROWM = wideM ? 42 : 52, TM = 44;
      var HM = TM + RW.length * ROWM + 14;
      var mxM = Math.max.apply(null, RW.map(function (r) {
        return Math.max(r.c, r.n); })) * 1.1;
      var xm = function (v) { return (v / mxM) * (WM - LM - RMM); };
      mirror = svg(WM, HM, "Tarrant County's active voters against the Neither bucket, "
                         + "line by line");
      mirror += '<rect x="' + (wideM ? LM : 8) + '" y="8" width="11" height="11" '
             + 'fill="currentColor" opacity="0.22" rx="2"/>'
             + txt((wideM ? LM : 8) + 17, 18, "Tarrant County, all active voters", "lgd")
             + '<rect x="' + ((wideM ? LM : 8) + 196) + '" y="8" width="11" height="11" '
             + 'fill="currentColor" opacity="0.62" rx="2"/>'
             + txt((wideM ? LM : 8) + 213, 18, "the Neither bucket", "lgd");
      if (wideM) mirror += txt(WM - RMM + 14, 18, "difference", "lgd");
      var ym = TM;
      RW.forEach(function (r) {
        if (wideM) mirror += txt(LM - 14, ym + 16, r.m, "lb", "end");
        else mirror += txt(8, ym - 2, r.m, "lb");
        var top = wideM ? ym : ym + 6;
        mirror += rect(LM, top, xm(r.c), 12, "currentColor", ' opacity="0.22" rx="2"')
               + txt(LM + xm(r.c) + 7, top + 10, r.c.toFixed(0) + "%", "tk")
               + rect(LM, top + 14, xm(r.n), 12, "currentColor", ' opacity="0.62" rx="2"')
               + txt(LM + xm(r.n) + 7, top + 24, r.n.toFixed(0) + "%", "vl");
        var d = r.n - r.c;
        mirror += txt(wideM ? WM - RMM + 14 : WM - 8, top + 17,
                      (d === 0 ? "same" : (d > 0 ? "+" : "−") + Math.abs(d).toFixed(0)),
                      "vl", wideM ? "start" : "end");
        ym += ROWM;
      });
      mirror += "</svg>";
    }

    /* --- his sliders, his published answers */
    var slTbl = SL.length ? ('<div class="scroll"><table class="txtbl"><thead><tr>'
      + "<th>What you assume</th><th>Democratic lead in the early vote</th>"
      + "<th>Margin</th><th>He prints</th></tr></thead><tbody>"
      + SL.map(function (r) {
          var em = /Break-even/.test(r.s);
          return '<tr' + (em ? ' class="em"' : "") + "><td>" + esc(r.s)
            + '</td><td class="num">' + (r.lead ? n0(r.lead) + " votes" : "—")
            + '</td><td class="num ' + (/^D/.test(r.m) ? "dem" : "") + '">' + esc(r.m)
            + '</td><td class="dim">' + esc(r.pub) + "</td></tr>";
        }).join("")
      + "</tbody></table></div>") : "";

    return card("tx-tarrant-swing", "Section 2 · slide 4 · who is in each camp",
      "The Neither voters look like Tarrant County",
      "<b>Source: Chris Tackett, See It. Name It. Fight It., 31 October — his table.</b> "
      + "The previous card showed how big the three camps are. This one shows who is "
      + "in them. Below the table, his headline claim on its own — the county’s "
      + "active voters against the Neither bucket, line by line — because it is "
      + "the claim the rest of the card rests on: <i>“on age, gender and race, "
      + "they’re within a point or two of the county’s active voters on almost "
      + "every line.”</i>",
      tbl + mirror + slTbl,
      "<b>Neither mirrors the county; the Republican camp does not come close.</b> "
      + "Averaged across the eight lines in the table, the Neither bucket sits "
      + "<b>1.5 points</b> from Tarrant’s own active voters and the Republican "
      + "primary camp sits <b>14.4</b> — nearly ten times further. The two lines "
      + "that carry most of that: 50% of Republican primary voters are 65 or older "
      + "against 22% of the county, and only <b>6% of them registered after November "
      + "2022 against 26% of the county</b>. That second one is the whole story of this "
      + "table in one number: the Republican early electorate is almost entirely "
      + "long-registered voters, with virtually no new ones in it."
      + "<br><br><b>His reading of the three columns, in his words.</b> <i>“The Neither voters "
      + "look like Tarrant County. On age, gender and race, they’re within a point or "
      + "two of the county’s active voters on almost every line. They aren’t a "
      + "fringe group or a niche. More than a quarter of them registered after the last "
      + "midterm. They’re the county as it is now.”</i>"
      + "<br><br><i>“Democratic primary voters look like the county with a few "
      + "differences. They’re about as Hispanic as the county and close to it on age. "
      + "They’re more female (61%) and more Black (26%) than the county, which "
      + "reflects the party’s most loyal voters.”</i>"
      + "<br><br><i>“Republican primary voters don’t look like the county. Half "
      + "of them are 65 or older, in a county where about one in five voters is. Only 3% "
      + "are under 30. Three in four are white, in a county where barely half of voters "
      + "are. Only 6% have registered since 2022.”</i>"
      + "<br><br><b>And his conclusion:</b> <i>“That’s the electorate in one "
      + "table. One camp is the county’s past, one is a big part of its present, and "
      + "the largest one, Neither, looks like the county itself. They will decide its "
      + "future.”</i> Earlier in the same piece: <i>“The Neither voters are the "
      + "election. 253,000 of them have already voted. They’re younger than the rest "
      + "of the early vote, more diverse, and newer to voting. On Friday, half of the "
      + "day’s voters were under 45.”</i>"
      + "<br><br><b>What that is worth, by his own calculator.</b> At his defaults — "
      + "95% of each party’s primary voters sticking with their party, Neither "
      + "splitting evenly — the early vote is already Democratic by about 14,000. "
      + "<i>“For Republicans to erase it, the Neither voters would have to break "
      + "about 53 to 47 their way.”</i> Running his camp counts at those assumptions "
      + "reproduces all five of his published figures, which is what says this is his "
      + "arithmetic and not a lookalike."
      + "<br><br><b>Both bases are nearly spent, and the remainder leans Republican.</b> "
      + "<i>“86% of active Democratic primary voters in Tarrant County voted early, "
      + "and 79% of Republican primary voters did. About 29,000 Democratic base voters are "
      + "left for Election Day, compared with about 42,000 Republican ones.”</i> That "
      + "13,000-vote edge is almost exactly the Democratic early-vote lead, which is why "
      + "he says the race is not won. But the people actually left are mostly in neither "
      + "camp: <i>“78% of the 2024 voters who haven’t voted yet have never "
      + "picked a primary.”</i>"
      + (P.length ? "<br><br><b>Every race moved the same way.</b> <i>“Every one of "
         + "these races moved 6 to 10 points toward Democrats compared with the 2022 early "
         + "vote … In every race, the Neither share of the early vote grew by 11 to 17 "
         + "points from 2022. How the Neithers break will dictate outcomes.”</i> On "
         + "the commissioner precincts: Precinct 2 went R+6.1 to D+1.9, Precinct 3 R+20.6 "
         + "to R+11.8, Precinct 4 R+12.6 to R+2.7. Precinct 1 was already D+37.5 and is "
         + "D+32.5." : ""));
  }


  /* The Morris gradient is the single biggest external input to this model: it is what
     reweights precincts inside every county. It has never been shown on its own, and the
     one public test of it is in here too. */
  /* Morris's own chart, not my reconstruction of it: turnout by how reliable a voter
     is, split by party, in the one Texas county that publishes individual voting
     histories. The gradient scatter that used to be here was my paraphrase. */
  function morrisCard() {
    /* Morris's chart, as he draws it: seven turnout-history tiers, least engaged at the
       top, one dot per party plus a grey dot for voters with no recent primary. An
       earlier version of this card had only two of the seven tiers, because those were
       the two he quoted in prose - and the two he quoted are the extremes, which is
       exactly the shape the middle five are needed to show is monotonic. */
    var E = (D.meng || []).map(function (r) {
      return {no: num(r.tier_no), tier: r.plain || r.tier, d: num(r.dem),
              r: num(r.rep), np: num(r.no_primary), gap: num(r.gap)};
    }).filter(function (r) { return r.d != null || r.np != null; });
    var PL = (D.mpoll || []).map(function (r) {
      return {tier: r.tier, d: num(r.dem), r: num(r.rep), gap: num(r.gap)};
    }).filter(function (r) { return r.d != null; });
    var HC = (D.mhar || []).map(function (r) {
      return {m: r.metric, a: r.y2022 === "" ? null : num(r.y2022), b: num(r.y2026)};
    }).filter(function (r) { return r.b != null; });
    if (!E.length) return "";

    var wide = !NARROW;
    var W = wide ? 760 : 360, L = wide ? 268 : 8, R = wide ? 66 : 52, T = 46;
    var ROW = wide ? 40 : 56;
    // Rows are not a fixed height: a party tier carries two dots and two labels, a
    // no-primary tier one. A single ROW big enough for both left the party sub-labels
    // sitting on top of the next tier's heading.
    var RP = 50, RG = 36;
    var H2 = T + E.reduce(function (a2, r) { return a2 + (r.np != null ? RG : RP); }, 0) + 20;
    var xs = function (v) { return L + v / 100 * (W - L - R); };
    var s2 = svg(W, H2, "Share of 2024 early in-person voters in Harris County who have "
                      + "voted early or by mail in 2026, by turnout history");
    [0, 25, 50, 75, 100].forEach(function (v) {
      s2 += line(xs(v), T - 14, xs(v), H2 - 16, "gl")
         + txt(xs(v), H2 - 4, v + "%", "tk", "middle");
    });
    var lg = [[DC, "Democrats"], [RC, "Republicans"], ["currentColor", "No recent primary"]];
    var lx = wide ? L : 8;
    lg.forEach(function (pr) {
      s2 += '<circle cx="' + (lx + 4) + '" cy="12" r="4" fill="' + pr[0] + '"'
         + (pr[0] === "currentColor" ? ' opacity="0.55"' : "") + "/>"
         + txt(lx + 13, 16, pr[1], "lgd");
      lx += pr[1].length * 5.9 + 28;
    });
    // A ladder, least engaged at the top, labelled in plain words rather than his
    // shorthand: "Presidential only" means they skipped the 2022 midterm, which no
    // reader can be expected to decode from the phrase.
    if (wide) s2 += txt(W - R + 8, 16, "turnout", "lgd")
                 + txt(W - 8, 16, "D lead", "lgd", "end");
    var y = T;
    E.forEach(function (r) {
      var grey = r.np != null;
      s2 += txt(wide ? 0 : 8, y + 4, r.tier, grey ? "lb" : "lbb");
      var dot = function (v, col, cy, nm) {
        return '<circle cx="' + xs(v) + '" cy="' + cy + '" r="5" fill="' + col + '"'
             + (col === "currentColor" ? ' opacity="0.55"' : "") + "/>"
             + (wide ? txt(L - 14, cy + 4, nm, "sub", "end") : "")
             + txt(W - R + 8, cy + 4, v.toFixed(1) + "%", "vl");
      };
      if (grey) {
        s2 += dot(r.np, "currentColor", y + 19, "no party \u2014 no recent primary");
        y += RG;
      } else {
        // no connector: two different groups, not one group moving
        s2 += dot(r.d, DC, y + 19, "Democrats") + dot(r.r, RC, y + 36, "Republicans");
        // the gap is the finding, so it is a number rather than a line
        if (r.gap != null) {
          s2 += '<text x="' + (W - 8) + '" y="' + (y + 32) + '" text-anchor="end" '
             + 'class="lbb" fill="' + DC + '">+' + r.gap.toFixed(1) + "</text>";
        }
        y += RP;
      }
    });
    s2 += "</svg>";

    // his second chart: the same question asked of people rather than of the voter file
    var s3 = "";
    if (PL.length) {
      var W3 = wide ? 760 : 360, L3 = wide ? 208 : 8, R3 = wide ? 66 : 52;
      var H3 = 34 + PL.length * 46;
      var x3 = function (v) { return L3 + v / 100 * (W3 - L3 - R3); };
      s3 = svg(W3, H3, "Share who say they will definitely vote, by how regularly they voted");
      [0, 25, 50, 75, 100].forEach(function (v) {
        s3 += line(x3(v), 20, x3(v), H3 - 14, "gl") + txt(x3(v), H3 - 3, v + "%", "tk", "middle");
      });
      PL.forEach(function (r, i) {
        var y = 32 + i * 46;
        if (wide) s3 += txt(L3 - 14, y + 8, r.tier, "lbb", "end");
        else s3 += txt(8, y - 10, r.tier, "lbb");
        s3 += '<circle cx="' + x3(r.d) + '" cy="' + (y - 4) + '" r="5" fill="' + DC + '"/>'
           + '<circle cx="' + x3(r.r) + '" cy="' + (y + 11) + '" r="5" fill="' + RC + '"/>'
           + txt(W3 - R3 + 8, y, r.d + "%", "vl") + txt(W3 - R3 + 8, y + 15, r.r + "%", "vl");
      });
      s3 += "</svg>";
    }

    var hc = HC.length ? ('<div class="scroll"><table class="txtbl" style="margin-top:14px"><thead><tr>'
      + "<th>Harris County early vote</th><th>2022</th><th>2026</th></tr></thead><tbody>"
      + HC.map(function (r) {
          return "<tr><td>" + esc(r.m) + '</td><td class="num dim">'
            + (r.a == null ? "\u2014" : r.a + "%") + '</td><td class="num">' + r.b
            + "%</td></tr>";
        }).join("") + "</tbody></table></div>") : "";

    return card("tx-morris", "Section 2 · slide 5 · the engagement gap",
      "What Morris found in Harris County",
      "<b>Source: G.&nbsp;Elliott Morris, Strength In Numbers \u2014 his chart, his "
      + "tiers.</b> <i>\u201cShare of 2024 early in-person voters who have voted early or "
      + "by mail in 2026, by turnout history.\u201d</i> Everyone in it voted early in "
      + "person in Harris County in the 2024 general. The tiers come from their history "
      + "<i>before</i> this cycle: how many of the last three generals they voted in "
      + "(2020, 2022, 2024), whether one of them was the 2022 midterm, and how many of the "
      + "two previous March primaries they voted in (2022, 2024). <i>\u201cPresidential "
      + "only\u201d</i> means they skipped the 2022 midterm. Texas has no party "
      + "registration, so party is the primary ballot they chose in 2022 or 2024; voters "
      + "with no recent primary ballot have no party and are shown in grey. The March 2026 "
      + "primary is deliberately left out of the tiers. The dot is the share who had voted "
      + "early or by mail by the end of early voting on 30 October. Harris is the only "
      + "large Texas county that publishes individual voting histories, so this is the one "
      + "place anyone can measure <i>which kind</i> of voter is turning out rather than "
      + "just how many.",
      s2 + s3 + hc,
      "<b>His conclusion, in his headline:</b> <i>\u201cEarly voting data suggests blue "
      + "wave, Dems could exceed 2018 turnout advantage \u2014 final early voting records "
      + "from Texas, Georgia, and now North Carolina show Democrats benefiting from an "
      + "\u2018engagement gap\u2019 that exceeds the party\u2019s advantage in "
      + "2018.\u201d</i> And at the end: <i>\u201cIf these patterns hold, Democrats may "
      + "even have a better turnout environment than 2018.\u201d</i> 2018 is the "
      + "comparison that matters for Texas: it is the year Beto held Cruz to R+2.57."
      + "<br><br><b>These are turnout rates, not vote shares.</b> Every number in the top "
      + "chart is the share of a group that has already voted \u2014 not how it voted. In "
      + "Morris&rsquo;s words: <i>\u201cAmong Houstonians who regularly turn out for "
      + "elections, Democrats (91% turnout) are out-voting Republicans (86%) by a modest "
      + "but still sizable 5 points. But among irregular voters \u2014 those who skipped "
      + "the 2022 midterm but voted early in 2024 \u2014 Republicans (57%) have fallen 13 "
      + "points behind Democrats (70%).\u201d</i> Those are his bottom and second rows "
      + "(90.7 against 85.7, and 70.3 against 57.1)."
      + "<br><br><b>The five tiers in between are why it is a finding and not an "
      + "anecdote.</b> The gap closes monotonically as voters get more reliable: 13.2 "
      + "points among presidential-only voters, 8.6 among those who made the last midterm "
      + "but not all three generals, 8.7 among all-three-generals voters with one primary, "
      + "and 5.0 among the most engaged of all. Every tier runs the same direction, so "
      + "this is a gradient rather than one loose group. The three grey dots \u2014 voters "
      + "with no recent primary at all, and so no party \u2014 run 44.0%, 59.3% and 70.6% "
      + "up the same ladder, which says the tiers are measuring engagement and not just "
      + "partisanship."
      + "<br><br><b>Asking people instead of the file gives the same answer.</b> A 6-point "
      + "gap among regular 2024 voters, 17 among irregular ones. "
      + "<i>\u201cIrregular Trump voters are the least sure of any 2024 voters that "
      + "they\u2019ll turn out.\u201d</i> He puts the whole-electorate version at ten "
      + "points: <i>\u201cFor months, Republicans have been telling pollsters they\u2019re "
      + "less likely to vote this year than Democrats \u2014 by about 10 percentage points "
      + "across firms. But that gap is concentrated among the least reliable Trump "
      + "voters.\u201d</i>"
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
      // Say what the block IS, in the header, in words a reader does not have to
      // reconstruct. "Hispanic 90%+" and "Non-white 90%+" look like variations on one
      // thing and are not: the second CONTAINS the first.
      var isH = dfn.indexOf("Hispanic") === 0;
      var head = '<tr class="grp"><td colspan="4">' + esc(dfn) + " \u2014 "
        + (isH ? "precincts where at least 90% of voting-age people are HISPANIC"
               : "precincts where at least 90% are NON-WHITE OF ANY KIND \u2014 Hispanic, "
                 + "Black, Asian and other together. This block CONTAINS the one above, "
                 + "plus everything else")
        + "</td></tr>";
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
    // The difference between the two blocks, as rows. This was explained in prose
    // underneath and the question still came back twice, which means it belongs in the
    // table: subtract the Hispanic block from the non-white block and what is left is
    // every precinct that is 90% non-white but NOT 90% Hispanic.
    var hs = {}, ns = {};
    rows.forEach(function (r) {
      if (r.race !== "2024 Senate") return;
      (r.group.indexOf("Hispanic") === 0 ? hs : ns)[r.where] =
        {b: num(r.ballots), m: num(r.margin_R)};
    });
    var diff = Object.keys(ns).filter(function (w) { return hs[w]; }).map(function (w) {
      var b = ns[w].b - hs[w].b;
      var m = b ? (ns[w].b * ns[w].m - hs[w].b * hs[w].m) / b : null;
      return {w: w, b: b, m: m};
    });
    if (diff.length) {
      body += '<tr class="grp"><td colspan="4">The difference between the two blocks '
        + "\u2014 precincts that are 90% non-white but NOT 90% Hispanic, so "
        + "overwhelmingly Black. Subtracted, not separately published</td></tr>"
        + diff.map(function (d) {
            return "<tr><td>" + esc(d.w) + "</td><td>2024 Senate</td>"
              + '<td class="num">' + n0(d.b) + '</td><td class="num '
              + (d.m < 0 ? "dem" : "rep") + '">' + mgn(d.m) + "</td></tr>";
          }).join("");
    }
    // the spread that makes the point, computed rather than asserted
    var h = rows.filter(function (r) { return r.group.indexOf("Hispanic") === 0
                                       && r.race === "2024 Senate"; });
    var spread = "";
    if (h.length > 1) {
      var ms = h.map(function (r) { return num(r.margin_R); });
      spread = Math.abs(Math.max.apply(null, ms) - Math.min.apply(null, ms)).toFixed(1);
    }
    return card("tx-prec", "Section 3 · slide 2 · two different electorates",
      "The same group, two different electorates",
      "Precincts that are overwhelmingly one group in 2024, split by where they are. "
      + "The first block is the one that matters for this model: Hispanic precincts on "
      + "the border run "
      + (spread ? "<b>" + spread + " points</b> " : "")
      + "away from Hispanic precincts in the big metros, in the same race on the same "
      + "day."
      + "<br><br><b>The two blocks are not the same measurement.</b> The first is precincts that are at least 90% <i>Hispanic</i>. The second is precincts that are at least 90% <i>non-white of any kind</i> \u2014 Hispanic, Black, Asian and other together \u2014 so it contains the first block plus everything else. Subtract one from the other and what is left is the part that is non-white but not Hispanic.",
      '<div class="scroll"><table class="txtbl"><thead><tr><th>Where</th><th>Race</th>'
      + "<th>Ballots</th><th>Margin</th></tr></thead><tbody>" + body + "</tbody></table></div>",
      "<b>What the difference between the two blocks actually is.</b> Subtracting the "
      + "Hispanic block from the non-white block leaves, in the 2024 Senate race:"
      + "<br>&nbsp;&nbsp;\u2022 Border / South Texas: <b>53,233</b> ballots at D+8.28 "
      + "\u2014 tiny, and it votes like its Hispanic neighbours."
      + "<br>&nbsp;&nbsp;\u2022 El Paso: <b>47,335</b> ballots at D+22.39."
      + "<br>&nbsp;&nbsp;\u2022 Big metro: <b>454,064</b> ballots at <b>D+57.83</b> "
      + "\u2014 seven times the size of the Hispanic-only group in the same place."
      + "<br><br><b>So in the metros, \u201cnon-white\u201d is almost entirely not "
      + "Hispanic.</b> Of the 519,792 ballots in 90% non-white metro precincts, 87% are "
      + "in the remainder, and that remainder is overwhelmingly Black. This is the "
      + "Black-ceiling problem seen geographically rather than in a table: the model "
      + "moves the whole non-white bloc +12, and in the metros that +12 lands almost "
      + "entirely on precincts already voting D+57.8. There is no room there, and it is "
      + "why the Hispanic figure has to carry the swing alone."
      + "<br><br><b>And the blocks are not even parallel.</b> The Hispanic block has both "
      + "2024 races; the non-white block has only the Senate. They cannot be read "
      + "row-against-row."
      + "<br><br>There is no single Hispanic number to measure, which is why break-even is a range "
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
    var wide = !NARROW;
    var W = wide ? 700 : 360, L = wide ? 190 : 8, R = wide ? 70 : 52;
    var ROW = wide ? 44 : 52;
    var H = 24 + rows.length * ROW;
    var mx = Math.max.apply(null, rows.map(function (r) { return r.mv; })) * 1.12;
    var s = svg(W, H, "Average county margin movement per cycle by group");
    rows.forEach(function (r, i) {
      var y = 12 + i * ROW;
      var w = r.mv / mx * (W - L - R);
      var sub = r.pct.toFixed(1) + "% of the vote, " + r.n + " counties";
      if (wide) {
        s += txt(L - 10, y + 16, r.g, "lb", "end")
           + txt(L - 10, y + 29, sub, "sub", "end");
      } else {
        s += txt(8, y + 6, r.g, "lb") + txt(8, y + 18, sub, "sub");
      }
      var by = wide ? y + 8 : y + 24;
      s += rect(L, by, w, 16, i === 0 ? DC : "var(--dim,#999)", ' rx="3"')
         + txt(L + w + 8, by + 12, r.mv.toFixed(2), "vl");
    });
    s += "</svg>";
    return card("tx-vol", "Section 3 · slide 3 · what moves, and what it weighs",
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
        + '<div class="scroll"><table class="txtbl" style="margin-bottom:12px"><thead><tr><th>&nbsp;</th>'
        + "<th>as a margin</th><th>in votes</th></tr></thead><tbody>"
        + "<tr><td>Ground the early vote was drawn from, at 2024 margins</td>"
        + '<td class="num">' + mgn(ground) + '</td>'
        + '<td class="num rep">' + sideV(vGround) + "</td></tr>"
        + "<tr><td>Shift the model assumes on top, weighted by early vote</td>"
        + '<td class="num dem">\u2212' + shift.toFixed(2) + '</td>'
        + '<td class="num dem">' + n0(Math.abs(vShift)) + " moved</td></tr>"
        + '<tr class="em"><td>Estimated banked margin</td>'
        + '<td class="num">' + mgn(est) + '</td>'
        + '<td class="num">' + sideV(vEst) + "</td></tr></tbody></table></div>"
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
    var wide = !NARROW;
    var W = wide ? 700 : 360, L = wide ? 130 : 8, R = wide ? 74 : 8;
    var ROW = wide ? 24 : 30;
    var H = 20 + top.length * ROW;
    var mx = top[0].gain * 1.1;
    var s = svg(W, H, "Net Democratic gain by county, top 14");
    top.forEach(function (r, i) {
      var y = 12 + i * ROW;
      var w = r.gain / mx * (W - L - R);
      if (wide) {
        s += txt(L - 10, y + 10, r.c, "lb", "end")
           + rect(L, y + 2, w, 14, DC, ' rx="2" opacity="0.85"')
           + txt(L + w + 8, y + 13, n0(r.gain), "vl");
      } else {
        // county name and figure share one line above the bar
        s += txt(8, y + 6, r.c, "lb") + txt(W - 8, y + 6, n0(r.gain), "vl", "end")
           + rect(L, y + 11, w, 11, DC, ' rx="2" opacity="0.85"');
      }
    });
    s += "</svg>";
    return card("tx-gain", "Section 5 · slide 2 · where the votes have to come from",
      "Net Democratic gain by county, needed to overcome the rural Republican bias",
      "What the model adds to each county versus its 2024 Senate result. The total needed "
      + "to erase R+5.98 is " + n0(305279) + "; the model produces " + n0(tot) + ". The "
      + "reason it has to be this large is the shape of the state: Republicans win 225 of "
      + "the 254 counties, and those 225 produce <b>1,377,318</b> net Republican votes "
      + "that have to be cleared before a single statewide vote of margin exists.",
      s,
      "<b>The rural bias, measured.</b> The 15 largest counties produce <b>1,265,790</b> "
      + "net Democratic votes on 6.9 million ballots. The other 239 produce "
      + "<b>1,199,649</b> net Republican votes on 3.3 million. Those two nearly cancel, "
      + "and what is left over is the entire statewide margin: <b>66,141</b> votes, or "
      + "<b>0.65 points</b> \u2014 which is where the model\u2019s D+0.65 comes from. "
      + "Rural Texas is only a third of the ballots and it very nearly erases the metros "
      + "entirely."
      + "<br><br><b>And this is Hinojosa\u2019s second lever, the one the Hispanic "
      + "card cannot supply.</b> After the full polling haircut the governor\u2019s race "
      + "is R+3.94 and she is short <b>402,353 votes</b>. The Hispanic slide shows that "
      + "lever alone needs Hispanic voters at D+36.15, which no measurement on this tab "
      + "reaches except the big-metro precincts. The other place 402,353 votes can come "
      + "from is here \u2014 and it is the same 1,199,649 net Republican votes:"
      + "<br>&nbsp;&nbsp;\u2022 rural turnout <b>down 34%</b>, which has no precedent, or"
      + "<br>&nbsp;&nbsp;\u2022 the rural margin <b>down 12.0 points</b> from R+35.9, on "
      + "the same ballots, or"
      + "<br>&nbsp;&nbsp;\u2022 the realistic version: rural turnout <b>down 15%</b> "
      + "<i>and</i> the Hispanic margin <b>7.3 points</b> better than the polls assume, "
      + "together."
      + "<br><br>Neither lever is plausible at full size. Both have to move, and they "
      + "have to move together. That is the whole difference between her race and "
      + "Talarico\u2019s, where the candidate effect does the work instead."
      + "<br><br><b>Concentration risk.</b> Five counties supply " + (top5 / tot * 100).toFixed(1)
      + "% of the net gain and ten supply " + (top10 / tot * 100).toFixed(1) + "%. A miss "
      + "in Harris or Dallas cannot be made up in rural Texas, and the whole cushion is "
      + n0(tot - 305279) + " votes out of 10.2 million.");
  }

  /* ================================================================ 12. the conclusion */
  /* The same question as the Tarrant sensitivity, asked of the one group that decides
     the state. Hold everything else at what the polls say, apply the full polling
     haircut to both races, and move only the Hispanic margin. Hispanic voters are 29.76%
     of the projected electorate, so each point of their margin is 0.2976 statewide -
     which means the 4.92 Paxton effect converts to exactly 16.53 points of Hispanic
     margin, and that is the entire distance between the two break-evens. */
  function hispanicSensCard() {
    var R = (D.hsens || []).map(function (r) {
      return {x: num(r.hispanic_margin_R), s: num(r.talarico_margin_R),
              g: num(r.hinojosa_margin_R)};
    }).filter(function (r) { return r.s != null; });
    var MK = (D.hmark || []).map(function (r) {
      return {l: r.label, v: num(r.margin_R)};
    }).filter(function (r) { return r.v != null; });
    if (!R.length) return "";
    var wide = !NARROW;
    var W = wide ? 760 : 360, L = wide ? 54 : 40, RM = wide ? 112 : 16;
    var T = wide ? 160 : 190, Bm = 50, H = wide ? 450 : 430;
    var lo = -4, hi = -46, vlo = -8, vhi = 10;
    var xs = function (v) { return L + (v - lo) / (hi - lo) * (W - L - RM); };
    var ys = function (v) { return T + (v - vlo) / (vhi - vlo) * (H - T - Bm); };
    var TAL = "var(--tal,#6b4fbb)", HIN = "var(--hin,#0f8f8f)";
    var s2 = svg(W, H, "What the Hispanic margin has to be to carry each race");
    [-5, 0, 5, 10].forEach(function (v) {
      s2 += line(L, ys(v), W - RM, ys(v), v === 0 ? "zl" : "gl")
         + txt(L - 6, ys(v) + 4, v === 0 ? "even" : mgn(v, 0), "tk", "end");
    });
    for (var t = -5; t >= -45; t -= 10) {
      s2 += line(xs(t), T, xs(t), H - Bm, "gl")
         + txt(xs(t), H - Bm + 18, mgn(t, 0), "tk", "middle");
    }
    s2 += txt(L, H - 12, "← less Democratic        the Hispanic margin        more Democratic →", "lgd");
    s2 += txt(0, T - 14, "statewide margin", "lgd");
    // every measured Hispanic figure, stacked above the plot on the same axis
    MK.sort(function (a, b) { return a.v - b.v; });
    MK.forEach(function (k, i) {
      if (k.v > lo || k.v < hi) return;          // axis runs lo (least D) to hi (most D)
      var y = 22 + i * 15;
      var right = xs(k.v) > (L + W - RM) / 2;
      s2 += line(xs(k.v), y + 4, xs(k.v), T - 4, "gl")
         + '<circle cx="' + xs(k.v) + '" cy="' + y + '" r="3" fill="currentColor" '
         + 'opacity="0.5"/>'
         + txt(xs(k.v) + (right ? -7 : 7), y + 4, k.l + "  " + mgn(k.v, 1), "sub",
               right ? "end" : "start");
    });
    var path = function (key, col) {
      return '<polyline points="' + R.map(function (r) {
        return xs(r.x) + "," + ys(r[key]); }).join(" ")
        + '" fill="none" stroke="' + col + '" stroke-width="2.5" opacity="0.9"/>';
    };
    s2 += path("g", HIN) + path("s", TAL);
    [[-19.66, TAL, "Talarico"], [-36.19, HIN, "Hinojosa"]].forEach(function (b) {
      s2 += '<line x1="' + xs(b[0]) + '" y1="' + T + '" x2="' + xs(b[0]) + '" y2="'
         + ys(0) + '" stroke="' + b[1] + '" stroke-width="1" stroke-dasharray="3 3" '
         + 'opacity="0.75"/>'
         + '<circle cx="' + xs(b[0]) + '" cy="' + ys(0) + '" r="4.5" fill="' + b[1] + '"/>'
         + '<text x="' + xs(b[0]) + '" y="' + (T - 8) + '" text-anchor="middle" '
         + 'class="vl" fill="' + b[1] + '">' + b[2] + " " + mgn(b[0], 2) + "</text>";
    });
    if (wide) {
      s2 += '<text x="' + (W - RM + 10) + '" y="' + (ys(R[R.length - 1].s) + 4)
         + '" class="lbb" fill="' + TAL + '">Talarico</text>'
         + '<text x="' + (W - RM + 10) + '" y="' + (ys(R[R.length - 1].g) + 4)
         + '" class="lbb" fill="' + HIN + '">Hinojosa</text>';
    }
    s2 += "</svg>";
    var tbl = '<div class="scroll"><table class="txtbl" style="margin-top:12px"><thead>'
      + "<tr><th>If Hispanic voters land at</th><th>Talarico</th><th>Hinojosa</th>"
      + "<th>Carries</th></tr></thead><tbody>"
      + R.filter(function (r) { return r.x % 6 === 0; }).map(function (r) {
          var who = (r.s < 0 && r.g < 0) ? "both"
                  : (r.s < 0 ? "Talarico only" : "neither");
          return "<tr" + (who === "both" ? ' class="em"' : "") + "><td>" + mgn(r.x, 0)
            + '</td><td class="num ' + (r.s < 0 ? "dem" : "rep") + '">' + mgn(r.s)
            + '</td><td class="num ' + (r.g < 0 ? "dem" : "rep") + '">' + mgn(r.g)
            + '</td><td class="' + (who === "both" ? "dem" : "dim") + '">' + who
            + "</td></tr>";
        }).join("") + "</tbody></table></div>";

    return card("tx-hispsens", "Section 4 · slide 2 · what the Hispanic vote has to do",
      "What the Hispanic vote has to do to carry each race",
      "<b>The same question the Tarrant card asks of its Neither bloc, asked of the one "
      + "group that decides the state.</b> Everything else is held at what the polls say, "
      + "the full three-to-four point polling haircut is applied to both races, and the "
      + "only moving part is the Hispanic margin. Hispanic voters are <b>29.76%</b> of the "
      + "projected electorate, so each point of their margin is 0.2976 points statewide. "
      + "The marks above the plot are every Hispanic figure measured anywhere on this tab.",
      s2 + tbl,
      "<b>The two break-evens.</b> Talarico is level when Hispanic voters land at "
      + "<b>D+19.66</b>. Hinojosa is level at <b>D+36.19</b>. The distance between them "
      + "is 16.53 points of Hispanic margin — which is the 4.92 Paxton effect "
      + "divided by 0.2976, exactly. As in Tarrant, everything separating these two "
      + "lines is the candidate."
      + "<br><br><b>Where the measured figures fall.</b> Talarico&rsquo;s line is already "
      + "cleared by almost everything: the two final polls weight to D+22.95, YouGov has "
      + "D+28, El Paso precincts D+28.67, the county model assumes D+29.85. Only two "
      + "measurements sit below his break-even — AtlasIntel&rsquo;s D+16.5 and the "
      + "90%-Hispanic border precincts at D+10.09 — and the 2024 exit poll, at "
      + "R+10, is off this chart entirely."
      + "<br><br><b>Hinojosa&rsquo;s line is cleared by nothing.</b> D+36.19 is above "
      + "every Hispanic figure on this tab except one: the 90%-Hispanic precincts in the "
      + "big metros, at D+41.15. She needs the <i>entire state&rsquo;s</i> Hispanic vote "
      + "to vote like Hispanic Houston and Dallas — which means the border too, and "
      + "the border was <b>Republican</b> at the top of the 2024 ticket."
      + "<br><br><b>So the Hispanic vote alone does not save her, and that is the "
      + "finding.</b> It is the largest single lever in Texas and it is not large enough "
      + "on its own; she needs it to run well <i>and</i> rural turnout to come in under. "
      + "For Talarico the same lever is already past its threshold on most of the "
      + "evidence, which is why his race is the confident one."
      + "<br><br><b>The caveat this card cannot escape.</b> There is no single Hispanic "
      + "number in Texas — that is the previous two slides. The border and the "
      + "metros sit 31 points apart and have been moving in opposite directions, so a "
      + "statewide Hispanic margin is an average over two electorates that do not behave "
      + "alike. Read the break-evens as thresholds on that average, not as a claim that "
      + "any actual Hispanic voter sits at D+36.");
  }


  /* ====================== Section 4: the turnout levers, grouped =================== */

  /* The Neither bloc extrapolated from Tarrant to the fifteen largest counties. The
     licence for doing it is the previous section: Harris and Tarrant agree on the
     mechanism from two incompatible methods, and they are 21.4% of the electorate
     between them. What is extrapolated is the SHARE and the BREAK, not the margin. */
  function neitherBigCard() {
    var H = (D.nhist || []).map(function (r) {
      return {c: r.cycle, d: num(r.d_camp), n: num(r.neither_camp), r: num(r.r_camp),
              res: num(r.county_result_R), broke: num(r.neither_broke_D), note: r.note};
    }).filter(function (r) { return r.n != null; });
    if (!H.length) return "";
    var wide = !NARROW;
    var W = wide ? 700 : 360, L = wide ? 176 : 8, R = wide ? 150 : 8;
    var ROW = wide ? 46 : 62, T = 44, Hh = T + H.length * ROW + 14;
    var xs = function (v) { return L + (v - 40) / 20 * (W - L - R); };
    var s2 = svg(W, Hh, "How Tarrant's Neither bloc has broken, solved from past results");
    [40, 45, 50, 55, 60].forEach(function (t) {
      s2 += line(xs(t), T - 14, xs(t), Hh - 12, t === 50 ? "zl" : "gl")
         + txt(xs(t), Hh - 2, t + "%", "tk", "middle");
    });
    s2 += txt(xs(50), T - 20, "an even split", "lgd", "middle");
    // No candidate threshold lines here. They were Tarrant COUNTY thresholds - 47.2%
    // and 41.5% - and on a card about the big fifteen they read as the statewide ones,
    // where 47.2% means something completely different (Talarico's floor, not
    // Hinojosa's). This chart is only the measured history.
    [].forEach(function (b) {
        s2 += '<line x1="' + xs(b[0]) + '" y1="' + (T - 8) + '" x2="' + xs(b[0]) + '" y2="'
           + (Hh - 12) + '" stroke="' + b[1] + '" stroke-width="1.5" '
           + 'stroke-dasharray="4 3" opacity="0.8"/>'
           + '<text x="' + xs(b[0]) + '" y="' + (T - 20) + '" text-anchor="middle" '
           + 'class="vl" fill="' + b[1] + '">' + b[2] + " " + b[0] + "%</text>";
      });
    var y = T;
    H.forEach(function (r) {
      if (wide) {
        s2 += txt(L - 14, y + 16, r.c, "lbb", "end")
           + txt(L - 14, y + 29, "D " + r.d + " / N " + r.n + " / R " + r.r, "sub", "end");
      } else {
        s2 += txt(8, y + 10, r.c, "lbb")
           + txt(8, y + 23, "D " + r.d + " / N " + r.n + " / R " + r.r, "sub");
      }
      var cy = y + (wide ? 16 : 36);
      if (r.broke != null) {
        s2 += '<circle cx="' + xs(r.broke) + '" cy="' + cy + '" r="6" '
           + 'fill="currentColor"/>'
           + txt(xs(r.broke) + 11, cy + 4, r.broke.toFixed(1) + "%", "vl");
        if (wide) s2 += txt(W - R + 14, cy + 4, "county finished R+" + r.res.toFixed(1), "sub");
      } else {
        s2 += txt(xs(50), cy + 4, "not yet resolvable", "sub", "middle");
      }
      y += ROW;
    });
    s2 += "</svg>";

    /* The lead figure has to be the per-county breaks, not Tarrant's. An earlier version
       opened with the Tarrant history - 49.9% and 50.1% - which reads as THE number, and
       the whole finding of this card is that it is not: these counties differ in their
       make-up, so the bloc that mirrors each of them breaks differently in each. */
    var MRC = (D.nmirror || []).map(function (r) {
      return {c: r.county, t: num(r.proj_turnout), m: num(r.margin_2026_R),
              nb: num(r.neither_ballots), mir: num(r.mirror_break_D),
              adj: num(r.mirror_plus_bias_D), net: num(r.net_d_votes)};
    }).filter(function (r) { return r.mir != null; })
      .sort(function (a, b) { return b.mir - a.mir; });
    var perCounty = "";
    if (MRC.length) {
      var wq = !NARROW;
      var W4 = wq ? 760 : 360, L4 = wq ? 118 : 8, R4 = wq ? 120 : 10;
      var RW4 = wq ? 34 : 46, T4 = 62, H4 = T4 + MRC.length * RW4 + 22;
      var lo4 = 40, hi4 = 74;
      var x4 = function (v) { return L4 + (v - lo4) / (hi4 - lo4) * (W4 - L4 - R4); };
      perCounty = svg(W4, H4, "What the unaffiliated bloc breaks in each in-scope county "
                            + "if it mirrors that county");
      [40, 45, 50, 55, 60, 65, 70].forEach(function (t) {
        perCounty += line(x4(t), T4 - 16, x4(t), H4 - 16, t === 50 ? "zl" : "gl")
                   + txt(x4(t), H4 - 4, t + "%", "tk", "middle");
      });
      perCounty += txt(x4(50), T4 - 22, "an even split", "lgd", "middle");
      [[47.2, "var(--tal,#6b4fbb)", "Talarico needs"],
       [61.2, "var(--hin,#0f8f8f)", "Hinojosa needs"]].forEach(function (b) {
        perCounty += '<line x1="' + x4(b[0]) + '" y1="' + (T4 - 10) + '" x2="' + x4(b[0])
          + '" y2="' + (H4 - 16) + '" stroke="' + b[1] + '" stroke-width="1.5" '
          + 'stroke-dasharray="4 3" opacity="0.85"/>'
          + '<text x="' + x4(b[0]) + '" y="' + (T4 - 24) + '" text-anchor="middle" '
          + 'class="vl" fill="' + b[1] + '">' + b[2] + " " + b[0] + "%</text>";
      });
      perCounty += txt(wq ? 0 : 8, 18, "each county's bloc, if it mirrors that county "
                       + "— bar width is how many ballots", "lgd");
      MRC.forEach(function (r, i) {
        var y = T4 + 6 + i * RW4;
        var f = (r.m < 0 ? "D+" : "R+") + Math.abs(r.m).toFixed(1);
        if (wq) {
          perCounty += txt(L4 - 12, y + 8, r.c, "lbb", "end")
                     + txt(L4 - 12, y + 20, "county " + f, "sub", "end");
        } else {
          perCounty += txt(8, y - 8, r.c + "  ·  county " + f, "lb");
        }
        var h = Math.max(6, Math.min(18, r.nb / 611623 * 18));
        perCounty += '<circle cx="' + x4(r.mir) + '" cy="' + (y + 8) + '" r="'
          + (h / 2 + 2) + '" fill="' + sideCol(-1) + '" opacity="0.8"/>'
          + txt(x4(r.mir) + h / 2 + 8, y + 12, r.mir.toFixed(1) + "%", "vl");
        if (wq) {
          perCounty += txt(W4 - R4 + 12, y + 7, n0(r.nb) + " ballots", "sub")
            + '<text x="' + (W4 - R4 + 12) + '" y="' + (y + 19) + '" class="vl" fill="'
            + sideCol(-r.net) + '">' + (r.net > 0 ? "+" : "\u2212")
            + n0(Math.abs(r.net)) + " net</text>";
        }
      });
      perCounty += "</svg>";
    }
    /* The scope, drawn: which of the fifteen are in and why. And then the share
       sensitivity, because applying Tarrant's 43% to five other counties is one
       assumption, not six measurements, and an earlier version of this card printed it
       as a per-county figure as though it had been measured in each. */
    var SC = (D.nscope || []).map(function (r) {
      return {c: r.county, t: num(r.proj_turnout), nw: num(r.pct_nonwhite),
              sc: r.scope, meas: r.measured === "yes"};
    }).filter(function (r) { return r.t != null; });
    var scopeFig = "";
    if (SC.length) {
      var wd = !NARROW;
      var W3 = wd ? 760 : 360, L3 = wd ? 112 : 8, R3 = wd ? 150 : 56;
      var RW = wd ? 24 : 30, T3 = 46, H3 = T3 + SC.length * RW + 16;
      var mxv = Math.max.apply(null, SC.map(function (r) { return r.t; })) * 1.06;
      var COL = {"in": DC, "cusp": DC, "border": RC, "white": "currentColor"};
      var OP = {"in": "0.75", "cusp": "0.45", "border": "0.4", "white": "0.18"};
      scopeFig = svg(W3, H3, "Which of the fifteen largest counties the finding travels to");
      scopeFig += txt(wd ? 0 : 8, 16, "projected turnout \u2014 solid in scope, pale out "
                      + "of scope", "lgd");
      if (wd) scopeFig += txt(W3 - R3 + 12, 16, "non-white", "lgd");
      SC.forEach(function (r, i) {
        var y = T3 + i * RW;
        var w = r.t / mxv * (W3 - L3 - R3);
        if (wd) scopeFig += txt(L3 - 10, y + 12, r.c + (r.meas ? " \u25cf" : ""),
                                r.meas ? "lbb" : "lb", "end");
        else scopeFig += txt(8, y + 4, r.c + (r.meas ? " \u25cf" : ""), "lb");
        scopeFig += rect(L3, y + (wd ? 2 : 7), w, 13, COL[r.sc],
                         ' rx="2" opacity="' + OP[r.sc] + '"');
        if (wd) {
          scopeFig += txt(L3 + w + 7, y + 12, n0(r.t), "tk")
                   + txt(W3 - R3 + 12, y + 12, r.nw.toFixed(1) + "%  " + r.sc, "sub");
        }
      });
      scopeFig += "</svg>";
    }

    /* the share assumption, sensitised */
    var SH = (D.nshare || []).map(function (r) {
      return {s: num(r.assumed_neither_share), nb: num(r.neither_ballots),
              pp: num(r.statewide_points_per_point), h: num(r.hinojosa_needs_pct),
              t: num(r.talarico_floor_pct)};
    }).filter(function (r) { return r.s != null; });
    var shTbl = SH.length ? ('<div class="scroll"><table class="txtbl" '
      + 'style="margin-top:14px"><thead><tr><th>If the Neither share is</th>'
      + "<th>Ballots in scope</th><th>Worth per point</th><th>Hinojosa needs</th>"
      + "<th>Talarico covered above</th></tr></thead><tbody>"
      + SH.map(function (r) {
          return "<tr" + (r.s === 43 ? ' class="em"' : "") + "><td>" + r.s + "%"
            + (r.s === 43 ? " \u2014 Tarrant\u2019s measured share" : "")
            + '</td><td class="num">' + n0(r.nb) + '</td><td class="num">'
            + r.pp.toFixed(3) + ' pts</td><td class="num rep">' + r.h
            + '%</td><td class="num dem">' + r.t + "%</td></tr>";
        }).join("") + "</tbody></table></div>") : "";
    /* The flat 50% was Tarrant's number, and Tarrant is the least Democratic county in
       the in-scope set. If the bloc mirrors its OWN county - which is the property
       Tackett measures and which these two cycles let us test - the break is different
       in every county and the whole thing moves. */
    var MR = (D.nmirror || []).map(function (r) {
      return {c: r.county, t: num(r.proj_turnout), m: num(r.margin_2026_R),
              nb: num(r.neither_ballots), mir: num(r.mirror_break_D),
              adj: num(r.mirror_plus_bias_D)};
    }).filter(function (r) { return r.mir != null; });
    var mirTbl = MR.length ? ('<div class="scroll"><table class="txtbl" '
      + 'style="margin-top:14px"><thead><tr><th>County</th><th>2026 margin</th>'
      + "<th>Neither ballots</th><th>Mirror implies</th><th>Plus the measured bias</th>"
      + "</tr></thead><tbody>"
      + MR.map(function (r) {
          return "<tr" + (r.c === "Tarrant" ? ' class="em"' : "") + "><td>" + esc(r.c)
            + (r.c === "Tarrant" ? " \u2014 where the 50% came from" : "")
            + '</td><td class="num ' + (r.m < 0 ? "dem" : "rep") + '">' + mgn(r.m, 1)
            + '</td><td class="num">' + n0(r.nb) + '</td><td class="num">'
            + r.mir.toFixed(1) + '%</td><td class="num dem">' + r.adj.toFixed(1)
            + "%</td></tr>";
        }).join("")
      + '<tr class="em"><td>Turnout-weighted</td><td class="num">\u2014</td>'
      + '<td class="num">1,794,952</td><td class="num">61.1%</td>'
      + '<td class="num dem">62.5%</td></tr>'
      + "</tbody></table></div>") : "";
    /* The third leg. Tarrant is a voter file and Harris is a voter file; AtlasIntel's
       independents crosstab is a POLL, measuring essentially the same population from a
       completely different instrument. Poll "independents" and "no recent primary
       ballot" are not the same definition - that caveat stands - but as a directional
       check it is the only one available, and it lands ABOVE the mirror rather than
       below it. */
    var TRI = (D.tri || []).map(function (r) {
      return {e: r.estimate, i: r.instrument, b: num(r.break_D)};
    }).filter(function (r) { return r.b != null; });
    var triTbl = TRI.length ? ('<div class="scroll"><table class="txtbl" '
      + 'style="margin-top:14px"><thead><tr><th>How the unaffiliated bloc breaks</th>'
      + "<th>Instrument</th><th>Break</th><th>Against Hinojosa\u2019s 61.2%</th>"
      + "</tr></thead><tbody>"
      + TRI.map(function (r) {
          var clears = r.b >= 61.2;
          return "<tr><td>" + esc(r.e) + '</td><td class="dim">' + esc(r.i)
            + '</td><td class="num"><b>' + r.b.toFixed(1) + '%</b></td><td class="'
            + (clears ? "dem" : "dim") + '">' + (clears ? "clears it" : "short")
            + "</td></tr>";
        }).join("") + "</tbody></table></div>") : "";
    return card("tx-neither-big", "Section 4 · slide 1 · the Neither bloc across the big fifteen",
      "The \u201cNeither\u201d bloc from Tarrant County, across the big fifteen, and what it is worth",
      "<b>The break is not one number \u2014 it is a different number in every "
      + "county, because these counties are not alike.</b> The property Tackett measures "
      + "in Tarrant is that the unaffiliated bloc mirrors <i>its own county</i> on age, "
      + "sex, race and registration. Tarrant is close to even, so its bloc splitting "
      + "50/50 is that property working, not a constant. Harris is D+21.5 and Dallas "
      + "D+38.9. The first chart is what the mirror implies in each of the six in-scope "
      + "counties, sized by how many ballots each contributes, against what each "
      + "candidate needs."
      + "<br><br><b>The licence for projecting it at all is the previous section.</b> Harris and "
      + "Tarrant agree on the mechanism — the movement sits with irregular and new "
      + "voters, the Republican coalition is the reliable one and is not replenishing "
      + "— and they agree on it from two instruments that cannot produce each "
      + "other&rsquo;s number. Morris measures turnout rates by engagement tier from the "
      + "Harris voter file; Tackett measures composition by primary camp from the Tarrant "
      + "one. Two analysts, two counties that are not the same kind of place, one "
      + "direction. <b>That agreement is what makes this a projection rather than a "
      + "guess</b>, and it is what sets how far it travels: Section 4 carries it only "
      + "across the band those two counties bracket."
      + "<br><br>Tarrant is the one county that publishes the camps, so the break itself "
      + "is solved for rather than read off. Hold both parties at 95% loyalty, take the "
      + "camp split the file gives for each past cycle, and ask what the Neither bloc must "
      + "have done to produce the result Tarrant actually got. The two dashed lines are "
      + "what each 2026 candidate needs from the same bloc.",
      perCounty + scopeFig + s2 + mirTbl + triTbl + shTbl,
      "<b>The break is different in every county, and that is the finding.</b> Dallas "
      + "69.4%, Bexar 63.5%, Harris 60.8%, Fort Bend 58.5%, Tarrant 54.5%, Brazoria "
      + "46.2% — turnout-weighted, <b>61.1%</b>. Each is simply that county’s "
      + "own margin reflected back, because that is the property the Tarrant file "
      + "measures: the bloc looks like the county it lives in."
      + "<br><br><b>What it is worth in votes</b>, against a flat 50/50 break, which "
      + "produces none: Dallas <b>+138,719</b>, Harris <b>+131,499</b>, Bexar "
      + "<b>+79,234</b>, Tarrant <b>+29,543</b>, Fort Bend <b>+24,763</b>, Brazoria "
      + "<b>−4,711</b>. Total <b>+399,047</b>, or <b>+447,576</b> with the measured "
      + "bias. Hinojosa needs 402,353."
      + "<br><br><b>The mirror is tested, once, where both sides are known.</b> Tarrant "
      + "finished R+1.0 and R+4.4 in its last two cycles, so a bloc mirroring it should "
      + "have broken 49.5% and 47.8%. It broke 49.9% and 50.1% — the mirror holds, "
      + "running 1.35 points more Democratic than the county. Harris corroborates the "
      + "mechanism from a different instrument entirely: the Democratic turnout edge is "
      + "13.2 points among voters who skipped the 2022 midterm against 5.0 among the most "
      + "reliable."
      + "<br><br><b>Three instruments, and they do not agree on how much.</b> Tarrant’s "
      + "break carried flat says <b>50%</b>. The same file mirrored and bias-corrected "
      + "says <b>62.5%</b>. AtlasIntel, asking Texas independents directly, says "
      + "<b>69.7%</b> two-way — against 49.5% for the same group in the 2024 exit "
      + "poll. Two of the three clear Hinojosa’s 61.2%; the one that does not is the "
      + "flat carry, which has the least information in it."
      + "<br><br><b>Scope and assumptions, both of which cut against her.</b> The finding "
      + "travels only across the band the two measured counties bracket — 47.0% to "
      + "63.2% non-white — so seven majority-white large counties are out and El "
      + "Paso and Hidalgo are out the other way, being close to 90% Mexican-American. "
      + "That leaves six counties and 4,174,308 votes, 40.9% of Texas, not the 67.3% an "
      + "earlier version used. The <b>1,794,952</b> figure is unaffiliated <i>ballots</i> "
      + "in those six, 43% of their projected vote — and that 43% is Tarrant’s "
      + "share applied uniformly, one assumption rather than six measurements. Across "
      + "every share from 30% to 55% Hinojosa still needs between 57.6% and 66.1%, so the "
      + "answer does not turn on it."
      + "<br><br><b>Why the tab does not simply take the friendly reading.</b> The mirror "
      + "is validated at R+1.0 and R+4.4. Applying it to Dallas at D+38.9 extrapolates "
      + "forty points past anything it has been checked against, and the 69.4% it implies "
      + "there is not a number anyone has observed. Harris and Dallas are also 54% of the "
      + "bloc, so they carry 54% of the weight — correct arithmetic, but it means two "
      + "counties set the answer."
      + "<br><br><b>So the prediction.</b> For Talarico none of this matters: his floor is "
      + "<b>47.2%</b> and every version clears it, at every share, on every instrument. "
      + "For Hinojosa it is the entire race — flat-50 leaves her eleven points short, "
      + "the mirror puts her already there, and nothing measurable resolves it before the "
      + "count. <b>Her race is not close because the evidence is balanced; it is close "
      + "because one unmeasurable choice is worth four points.</b>");
  }

  /* The rural lever on its own. It lived inside the county-gain card, three sections
     away from the other two, which made it impossible to read the three together. */
  function ruralCard() {
    var R = (D.rur || []).map(function (r) {
      return {cut: num(r.turnout_cut_pct), v: num(r.votes_found),
              sh: num(r.share_of_need), pts: num(r.statewide_points)};
    }).filter(function (r) { return r.v != null; });
    if (!R.length) return "";
    var wide = !NARROW;
    var W = wide ? 720 : 360, L = wide ? 120 : 8, RM = wide ? 128 : 56;
    var ROW = wide ? 30 : 40, T = 46, H = T + R.length * ROW + 14;
    var mx = 110;
    var xs = function (v) { return L + v / mx * (W - L - RM); };
    var s2 = svg(W, H, "What a fall in rural turnout is worth to the governor's race");
    [0, 25, 50, 75, 100].forEach(function (t) {
      s2 += line(xs(t), T - 14, xs(t), H - 12, t === 100 ? "zl" : "gl")
         + txt(xs(t), T - 20, t + "%", "tk", "middle");
    });
    s2 += txt(wide ? 0 : 8, 16, "share of the 402,353 votes Hinojosa needs →", "lgd");
    if (wide) s2 += txt(W - RM + 12, T - 20, "statewide", "lgd");
    var y = T;
    R.forEach(function (r) {
      var lab = r.cut === 0 ? "unchanged" : "down " + r.cut + "%";
      if (wide) s2 += txt(L - 12, y + 15, lab, "lb", "end");
      else s2 += txt(8, y + 6, lab, "lb");
      var by = wide ? y + 4 : y + 12;
      s2 += rect(L, by, xs(r.sh) - L, 14,
                 r.sh >= 100 ? DC : "currentColor",
                 ' rx="2" opacity="' + (r.sh >= 100 ? "0.8" : "0.3") + '"')
         + txt(xs(r.sh) + 7, by + 12, r.sh.toFixed(0) + "%", "vl");
      if (wide) s2 += txt(W - RM + 12, by + 12, "+" + r.pts.toFixed(2), "tk");
      y += ROW;
    });
    s2 += "</svg>";
    return card("tx-rural", "Section 4 · slide 3 · the rural lever",
      "What rural turnout would have to do",
      "<b>The 239 counties outside the largest fifteen cast 3,343,577 ballots at R+35.9, "
      + "a net of 1,199,649 Republican votes.</b> That net is what the metros have to "
      + "clear before the first statewide vote of margin exists. Each bar is the share of "
      + "the 402,353 votes Hinojosa needs that a given fall in rural turnout would supply, "
      + "with everything else held where the polls put it.",
      s2,
      "<b>Rural turnout would have to fall by a third.</b> A 34% collapse supplies exactly "
      + "the 402,353 votes. Down 15% — already a large miss by any historical "
      + "standard — supplies 44.7% of it, worth 1.76 statewide points. Down 25% "
      + "supplies three quarters."
      + "<br><br><b>For scale on how unlikely the full version is.</b> Texas total midterm "
      + "turnout moved 2.3% between 2018 and 2022. Nothing in the modern record resembles "
      + "a third of the rural electorate staying home, and the 2026 early vote is running "
      + "<i>ahead</i> of 2022 statewide, not behind. A partial version is plausible; the "
      + "full version is not, which is why this lever cannot carry her alone."
      + "<br><br><b>What would actually produce it.</b> Not persuasion — these "
      + "counties are R+35.9 and nothing on this tab suggests that margin moves. It would "
      + "have to be differential turnout: the rural Republican electorate is the "
      + "high-engagement electorate, and Section 2 slide 6 is the one place anyone has "
      + "measured whether it is showing up. In Harris the Republican turnout deficit is "
      + "5.0 points even among the most reliable voters, which is the mechanism by which "
      + "this lever would move at all."
      + "<br><br><b>And it does nothing for the Senate race</b>, which is already clear by "
      + "0.98 at the full polling haircut. Every figure on this card is about her race.");
  }

  /* The two levers that do NOT overlap, and the combination of them. Rural is the 239
     counties; the Neither bloc lives in the big fifteen; they are disjoint by
     construction. The Hispanic lever is NOT a third independent one - Hispanic voters
     sit inside both - so adding all three at face value double-counts. */
  function leversCard() {
    var R = (D.lev || []).map(function (r) {
      return {cut: num(r.rural_turnout_cut), n: num(r.neither_break_D),
              v: num(r.votes_found), m: num(r.hinojosa_margin_R)};
    }).filter(function (r) { return r.m != null; });
    if (!R.length) return "";
    var cuts = [], brks = [];
    R.forEach(function (r) {
      if (cuts.indexOf(r.cut) < 0) cuts.push(r.cut);
      if (brks.indexOf(r.n) < 0) brks.push(r.n);
    });
    cuts.sort(function (a, b) { return a - b; });
    brks.sort(function (a, b) { return a - b; });
    var cw = NARROW ? 54 : 104, ch = NARROW ? 32 : 38;
    var L = NARROW ? 76 : 150, T = 52;
    var W = L + brks.length * cw + 12, H = T + cuts.length * ch + 26;
    var s = svg(W, H, "What rural turnout and the Neither bloc have to do together");
    s += txt(L, 16, "the Neither bloc in the big fifteen breaks →", "lgd");
    brks.forEach(function (b, i) {
      s += txt(L + i * cw + cw / 2, T - 10, b + "%", "tk", "middle");
    });
    s += txt(0, 34, NARROW ? "rural" : "rural turnout", "lgd");
    cuts.forEach(function (c, j) {
      var y = T + j * ch;
      s += txt(L - 10, y + ch / 2 + 4, c === 0 ? "unchanged" : "down " + c + "%", "lb", "end");
      brks.forEach(function (b, i) {
        var cell = R.filter(function (r) { return r.cut === c && r.n === b; })[0];
        if (!cell) return;
        var win = cell.m < 0;
        s += rect(L + i * cw + 1, y + 1, cw - 2, ch - 2,
                  win ? DC : RC, ' opacity="' + (Math.min(0.72, 0.1 + Math.abs(cell.m) / 6) ) + '"')
           + '<text x="' + (L + i * cw + cw / 2) + '" y="' + (y + ch / 2 + 4)
           + '" text-anchor="middle" class="cellw">' + mgn(cell.m) + "</text>";
      });
    });
    s += "</svg>";
    /* Three vectors, each tested on its own before the combination. The grid below is
       the two that are disjoint; this table is all three, because "can this one carry
       her alone?" is a different question from "do they add up?" and only the second
       has the overlap problem. */
    var V = (D.vec || []).map(function (r) {
      return {v: r.vector, n: r.needs_alone, o: r.observed_range, verdict: r.verdict,
              why: r.why};
    }).filter(function (r) { return r.n; });
    var vecTbl = V.length ? ('<div class="scroll"><table class="txtbl"><thead><tr>'
      + "<th>Vector</th><th>What it needs on its own</th><th>What has been observed</th>"
      + "<th>Can it carry her alone?</th></tr></thead><tbody>"
      + V.map(function (r) {
          var ok = r.verdict === "yes";
          return "<tr><td><b>" + esc(r.v) + '</b><br><span class="dim">' + esc(r.why)
            + '</span></td><td class="num"><b>' + esc(r.n) + '</b></td><td class="dim">'
            + esc(r.o) + '</td><td class="' + (ok ? "dem" : "rep") + '"><b>'
            + esc(r.verdict) + "</b></td></tr>";
        }).join("") + "</tbody></table></div>") : "";
    return card("tx-levers", "Section 4 · slide 4 · all three together",
      "Three vectors, one of which can carry her alone",
      "<b>Each cell is the governor&rsquo;s race after the full polling haircut</b>, with "
      + "rural turnout down the amount on the left and the Neither bloc in the big fifteen "
      + "breaking the amount along the top. Blue cells are Hinojosa winning. These two "
      + "levers are <b>disjoint</b>: rural is the 239 smallest counties, the Neither bloc "
      + "is inside the largest fifteen, and nothing is counted twice.",
      vecTbl + '<div class="scroll">' + s + "</div>",
      "<b>Three vectors, and the answer differs for each.</b> The table above tests each "
      + "one on its own, which is a fair question even though they cannot be added. "
      + "<b>Rural cannot carry her</b> \u2014 it needs a 34% collapse and nothing in the "
      + "modern record is close. <b>The unaffiliated bloc can</b> \u2014 it needs 61.2% "
      + "and the county-mirror estimate is 62.5% with AtlasIntel\u2019s independents at "
      + "69.7%. <b>The Hispanic vote can, but only at its ceiling</b> \u2014 it needs "
      + "D+36.15, which is above every measurement on this tab except the 90%-Hispanic "
      + "metro precincts at D+41.15."
      + "<br><br><b>So one of the three does carry her alone, on its most defensible "
      + "reading.</b> That is a materially different position from the one the rest of "
      + "this tab describes, and it comes entirely from scoping the extrapolation to the "
      + "counties where it is licensed and letting the bloc mirror each of them."
      + "<br><br><b>Alone on the conservative readings, neither of the two in the grid works.</b> Rural turnout would have to collapse <b>34%</b> with "
      + "the Neither bloc at its historical even split — no Texas midterm has come "
      + "close. The Neither bloc would have to break <b>61.2%</b> with rural turnout "
      + "unchanged — eleven points beyond anything it has done in two measured "
      + "cycles. Both are the edges of this grid and both are red."
      + "<br><br><b>Together they are reachable, but not comfortably.</b> Rural down 15% "
      + "and the bloc at 56.2% does it. Rural down 25% and 52.9% does it — and 52.9% "
      + "is only three points above the historical break, which is the single most "
      + "plausible cell on this grid. Below that the two have to trade off against each "
      + "other point for point."
      + "<br><br><b>These numbers are on the SCOPED extrapolation, which is why they are "
      + "harder than they were.</b> An earlier version of this grid spread the Neither "
      + "finding across all fifteen large counties and had her needing 56.8%. Restricting "
      + "it to the six counties inside the measured non-white band — 4,174,308 votes "
      + "rather than 6,868,411 — cuts each point of break from 0.58 statewide points "
      + "to 0.352, and moves her requirement to 61.2%. The correction is the right one "
      + "and it runs against her."
      + "<br><br><b>And the Hispanic vote is not a third lever, which is the thing most "
      + "likely to be got wrong.</b> Hispanic voters sit <i>inside</i> the Neither bloc "
      + "and <i>inside</i> those six counties. Adding Section 4 slide 1&rsquo;s "
      + "requirement on top of this grid counts the same ballots twice. The honest "
      + "reading: rural and Neither are the two independent levers, and the Hispanic "
      + "margin is the main <i>mechanism</i> by which the Neither bloc breaks above even. "
      + "The exchange rate between the two ways of saying it: one point of Hispanic "
      + "margin is worth about <b>0.85 points</b> of Neither break, because 0.2976 "
      + "divided by 0.352 is 0.845. They are two descriptions of one movement."
      + "<br><br><b>And none of this touches the Senate race.</b> Talarico clears his "
      + "threshold on the unchanged row at the historical break, and there is no cell on "
      + "this grid where he loses. It is a map of her race only.");
  }

  function conclusionCard() {
    return '<section class="txarg" id="tx-read-committed">'
      + '<p class="txkick">Written down before the polls close · 2 November 2026</p>'
      + "<h2>What I will read into tomorrow night, decided now</h2>"
      + "<p><b>Why the Senate seat is the confident call, stated as floors.</b> Not "
      + "because the polls are generous \u2014 this tab prices them at three to four "
      + "points too Democratic \u2014 but because <b>every path to beating Talarico "
      + "requires something no Texas election has produced</b>:</p>"
      + "<ul>"
      + "<li>He loses only if the polling haircut exceeds <b>5.03</b>. The worst miss "
      + "ever measured in Texas is <b>4.68</b>, and that was a presidential year with "
      + "Trump on the ballot.</li>"
      + "<li>He loses only if the generic Texas Democrat loses by more than <b>4.92</b>. "
      + "An R+4 night \u2014 a bad evening for Democrats everywhere else on the ballot "
      + "\u2014 still elects him.</li>"
      + "<li>His unaffiliated-bloc floor is <b>47.2%</b>. That bloc has broken 49.9% and "
      + "50.1% in its two measured cycles, and all three triangulated estimates "
      + "\u2014 61.1%, 62.5% and AtlasIntel\u2019s 69.7% \u2014 sit above it.</li>"
      + "<li>His Hispanic floor is <b>D+19.66</b>, cleared by the four-poll average, by "
      + "YouGov, by the El Paso precincts and by the county model.</li>"
      + "</ul>"
      + "<p><b>No single lever on this tab, at any value it has ever taken, beats him.</b> "
      + "That is a different claim from \u201che is ahead by five\u201d, and it is the "
      + "reason the Senate call is made with confidence while the governor&rsquo;s race "
      + "is not. Two qualifiers kept: the 4.92 is one week of polling from four houses "
      + "\u2014 measured well but measured once \u2014 and Texas has historically broken "
      + "Democratic hearts by beating its polls, with 2018 the counter-case where that ran "
      + "the other way.</p>"
      + "<p>What follows was committed in advance so it cannot be rationalised afterward. "
      + "All three branches turn on the early-vote margin Texas reports when polls close, "
      + "against the band set by what election day has actually done in Texas.</p>"
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
    + ".txarg ol,.txarg ul{margin:4px 0 10px;padding-left:1.2em;font-size:14px;line-height:1.55}"
    + ".txarg li{margin-bottom:6px}"
    + ".txarg .nm{font-variant-numeric:tabular-nums}"
    + ".txcard h3{font-family:var(--display);text-transform:uppercase;letter-spacing:.06em;"
    + "font-size:13px;margin:0 0 7px}"
    + ".txkick{font-size:10.5px;text-transform:uppercase;letter-spacing:.09em;"
    + "color:var(--dim);margin:0 0 3px}"
    + ".txhint{font-size:13px;color:var(--dim);margin:0 0 12px;max-width:74ch;line-height:1.5}"
    + ".txrule{display:block;border-top:1px solid var(--line);margin:14px 0}"
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
    + ".txnav{font-size:12px;margin:0 0 14px;line-height:1.9;display:flex;flex-wrap:wrap;gap:0 14px;max-width:100%}"
    + ".txnav a{white-space:nowrap}"
    + "@media (max-width:640px){"
    + ".txcard,.txarg{padding:13px 13px;border-radius:8px;margin:0 0 11px}"
    + ".txarg h2{font-size:19px}.txframe h2{font-size:18px}"
    + ".txarg p,.txframe p{font-size:13.5px}"
    + ".txhint{font-size:12.5px}.txnote{font-size:12px}"
    + ".txbig{font-size:31px}"
    + ".txnav{line-height:2.1;font-size:11.5px}"
    + ".txnav{gap:0 9px}"
    + "table.txtbl{font-size:12px}"
    + "table.txtbl th{font-size:9.5px;padding-left:8px}"
    + "table.txtbl td{padding-left:8px}"
    + ".bandrow{font-size:12px;padding:6px 8px}"
    + ".txcard .scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}"
    + "}"
    + ":root{--tal:#6b4fbb;--hin:#0f8f8f}"
    + "@media (prefers-color-scheme:dark){:root:not([data-theme=\"light\"])"
    + "{--tal:#a78bfa;--hin:#2dd4bf}}"
    + ":root[data-theme=\"dark\"]{--tal:#a78bfa;--hin:#2dd4bf}"
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

  /* A resize that crosses the phone breakpoint has to redraw, because the charts choose
     their geometry rather than scaling it. Redraw from the data already in memory - never
     refetch the twenty-seven files - and debounce, because iOS fires resize on every
     address-bar nudge. */
  var LAST_HOST = null, LAST_LIVE = null, RZ = null;
  window.addEventListener("resize", function () {
    var now = window.innerWidth < BREAK;
    if (now === NARROW || !LAST_HOST) return;
    clearTimeout(RZ);
    RZ = setTimeout(function () {
      if ((window.innerWidth < BREAK) === NARROW || !LAST_HOST) return;
      NARROW = window.innerWidth < BREAK;
      draw(LAST_HOST, LAST_LIVE);
    }, 180);
  });

  window.renderTexas = function (host) {
    NARROW = window.innerWidth < BREAK;
    host.innerHTML = '<div class="txwrap-inner"><p class="txhint">Loading the Texas '
      + "analysis…</p></div>";
    var want = [["meth", "tx_methods.csv"], ["modes", "tx_modes_statewide.csv"], ["order", "tx_reporting_order.csv"], ["est", "tx_estimates.csv"], ["prim", "tx_primary_series.csv"], ["fit", "tx_primary_fit.csv"], ["cmp", "tx_2018_compare.csv"],
                ["base", "tx_baseline.csv"], ["pax", "tx_paxton.csv"],
                ["sens", "tx_sensitivity.csv"], ["blocs", "tx_blocs.csv"],
                ["eth", "tx_ethnicity.csv"], ["prec", "tx_precincts.csv"], ["tarr", "tx_tarrant_precincts.csv"], ["tarrh", "tx_tarrant_history.csv"], ["tgrp", "tx_tarrant_groups.csv"], ["tarrhd", "tx_tarrant_history_detail.csv"], ["tage", "tx_tarrant_age.csv"], ["hair", "tx_haircut.csv"], ["hsens", "tx_hispanic_sensitivity.csv"], ["hmark", "tx_hispanic_markers.csv"], ["vec", "tx_three_vectors.csv"], ["tri", "tx_triangulate.csv"], ["nmirror", "tx_neither_mirror.csv"], ["nscope", "tx_neither_scope.csv"], ["nshare", "tx_neither_share.csv"], ["rur", "tx_rural.csv"], ["nhist", "tx_neither_history.csv"], ["lev", "tx_levers.csv"], ["twoc", "tx_two_counties.csv"], ["svt", "tx_senate_vs_ticket.csv"], ["sg", "tx_sen_gov_2026.csv"], ["only", "tx_2026_only.csv"], ["camps", "tx_tarrant_camps.csv"], ["tsl", "tx_tarrant_sliders.csv"], ["cshare", "tx_tarrant_camp_shares.csv"], ["meng", "tx_morris_engagement.csv"], ["mpoll", "tx_morris_polls.csv"], ["mhar", "tx_morris_harris.csv"], ["xtab", "tx_crosstabs.csv"], ["exit", "tx_exit_2024.csv"], ["perr", "tx_poll_error.csv"], ["pdate", "tx_polls_dated.csv"], ["pace", "tx_pace_gradient.csv"],
                ["vol", "tx_volatility.csv"], ["cty", "tx_counties.csv"],
                ["watch", "tx_watch.json"]];
    Promise.all(want.map(function (p) {
      return load(p[1]).then(function (v) { D[p[0]] = v; })
        .catch(function (e) { D[p[0]] = []; console.warn("texas:", e.message); });
    })).then(function () {
      draw(host, live());
    });
  };

  function draw(host, L) {
      LAST_HOST = host; LAST_LIVE = L;
      SECTIONS = [];
      // Narrative order. The tab is an argument, not a dashboard, so it runs:
      // what changed (the primary), how that reaches the result (early vote against
      // election day), where it lands (the estimates and why they disagree), the group
      // doing the moving (the Hispanic cards), and finally the three ways of asking
      // what it would take. The live read sits second because on the night it is the
      // only card anyone needs first.
      // Five sections, in the order the evidence arrives: what March showed, what the
      // banked vote shows, what the polls say and what they are worth, the one group it
      // all turns on, and finally what would have to be true.
      // Open with the polls, because that is the best available guess right now - then
      // turn and ask what the counted data says, which is the primary and the early vote.
      var html = thesis()
        + readCard(L)
        + methodsCard()

        + framing("tx-frame-polls", "Section 1 \u00b7 what the polls tell us",
            "The best guess anyone has today",
            ["All four non-partisan final polls put Talarico ahead, by between three points and seven, averaging <b>D+5.03</b> across 5,934 interviews. That is where the public conversation sits, so it is where this starts. Trafalgar, an R-aligned house and the only poll showing Paxton ahead, is not in this dataset at all.",
             "But they are not four independent readings, and Texas polls have a record worth knowing before leaning on them: the famous misses are a presidential-year pattern, and the two midterms available to check missed by half a point and by four in the OTHER direction."])
        + estimatesCard()
        + pollTrustCard()
        + haircutCard()
        + paxtonCard()
        + crosstabCard()
        + baselineCard()

        + framing("tx-frame-primary", "Section 2 \u00b7 what the 2026 data says",
            "But what do the votes already cast say?",
            ["Everything above is people telling a stranger what they intend to do. The rest of this section is what they have already done \u2014 4.5 million primary ballots in March and 7.7 million early votes since, all of them counted rather than estimated.",
             "<b>The primary first.</b> Texas runs an open primary, so it is the one measure where a voter declares a side with no pollster in the room. It went Democratic <b>51.70%</b>, the first midterm majority of the modern era, on turnout up 48.1% from 2022 with the Democratic half more than doubling. Fitted against seven cycles of Texas Novembers that implies a race between D+1.57 and R+1.66, in a state whose last three statewide cycles averaged R+10.09.",
             "<b>Then the early vote</b>, from slide 4. Texas records no party, so nobody can count the banked vote by side \u2014 but Tarrant publishes who is in its electorate, Harris publishes which kind of voter is turning out, and North Carolina registers by party and can check whether the pattern survives outside Texas."])
        + primaryCard()
        + primaryFitCard()

        + tarrantCard()
        + tarrantSwingCard()
        + morrisCard()
        + twoCountiesCard()
        + historyCard()

        + framing("tx-frame-hisp", "Section 3 \u00b7 the Hispanic vote",
            "The one question nobody has measured",
            ["Strip out the candidate and the baseline choice and a single question is left, and the whole race turns on it: <b>how far Hispanic voters move.</b>",
             "Three facts make it harder than it sounds. The group is 29.76% of the projected electorate. It is not one electorate but two \u2014 the border and the metros sit tens of points apart and have been moving in opposite directions. And the border is the most volatile ground in Texas, swinging three times as hard per cycle as anywhere else on a twelfth of the ballots.",
             "So there is no single Hispanic number to put in a model, which is why break-even is a range rather than a point."])
        + ethCard()
        + precinctCard()
        + volCard()

        + framing("tx-frame-levers", "Section 4 \u00b7 the turnout levers",
            "What would have to happen, and whether it can",
            ["Section 3 ended on thresholds rather than a number: the Hispanic margin has "
             + "to reach D+19.66 for Talarico and D+36.19 for Hinojosa. This section asks "
             + "the same question of the two levers that are <i>independent of each "
             + "other</i> \u2014 how the unaffiliated bloc in the big metros breaks, and "
             + "whether rural turnout comes in under.",
             "They do not overlap: rural is the 239 smallest counties and the unaffiliated "
             + "bloc lives inside the largest fifteen. The Hispanic margin is not a third "
             + "lever on top of them \u2014 it is the mechanism by which the second one "
             + "moves, which is why reading all three additively double-counts the same "
             + "ballots.",
             "Where it arrives: alone, neither lever reaches far enough. Together, two "
             + "moderate moves do it \u2014 and none of it is needed for the Senate seat."])
        + neitherBigCard()
        + hispanicSensCard()
        + ruralCard()
        + leversCard()

        + framing("tx-frame-outcomes", "Section 5 \u00b7 our model",
            "And last, our own model",
            ["Our own model goes last, after every outside source, because it is the one thing here nobody else can check. Everything above is evidence and none of it is an answer, since every piece "
             + "stops in the same place: the electorate changed, the banked vote is most "
             + "of the result, the candidate is worth about five points, and the movement "
             + "is Hispanic voters \u2014 but nobody has measured how far they move.",
             "So rather than produce one number, these ask what would have to be true "
             + "from four directions: what this model already has banked and where those "
             + "votes physically come from, then the same question in votes, in "
             + "demographics, and in party blocs with no demographics in it at all.",
             "They are built from different data and they land in the same place, which "
             + "is the strongest thing this tab can say. A coin flip that four independent "
             + "routes agree on is still a coin flip \u2014 but it is a well-measured one."])
        + watchCard(L)
        + countyGainCard()
        + bankedCard()
        + gridCard("tx-sens", "Section 5 · slide 4 · the demographic levers",
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
        + gridCard("tx-blocs", "Section 5 · slide 5 · the same question by bloc",
            "What it takes, by voting bloc",
            "Independents against the Republican bloc-size edge, with Democrats holding "
            + "98% and crossover fixed at 2%. <b>Independents are 36% of the electorate</b>, "
            + "the figure the 2024 Texas exit poll measured rather than one a poll "
            + "self-reported. Texas has no party registration, so there is no other place a "
            + "bloc size can come from. The Republican edge runs from even to R+12 in "
            + "two-point steps \u2014 the old grid ran from D+4 in fours, and a Democratic "
            + "bloc advantage in Texas is not a state anyone claims it is in.",
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
        + '<div class="txwrap-inner">' + nav + thesis()
        + html.slice(html.indexOf("</section>") + 10) + "</div>";
  }
})();
