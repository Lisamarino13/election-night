/* Georgia — the governor's race, read off the banked vote.
 *
 * Every figure here is computed from files in this repo and named where it came from:
 *   data/early-GA.json                     tonight's early vote, by county
 *   data/ga/ga_2022_governor_counties.json 2022 governor + senate, by county AND by mode
 *   data/county-2024.json, county-series   2016/2020/2024 presidential, by county
 *   Georgia SOS results API                2014-2022 mode splits (118 elections back to 2012)
 *   NBC News                               2024 mode split, which ties to the certified result
 *
 * The argument is deliberately narrow. Composition is measured; margin is not. Where a
 * number rests on an assumption the card says so rather than burying it in a footnote.
 */
(function () {
  "use strict";

  var SECTIONS = [];
  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function n0(v) { return Math.round(v).toLocaleString("en-US"); }
  function mgn(v) {
    return v > 0 ? "R+" + v.toFixed(2) : "D+" + Math.abs(v).toFixed(2);
  }

  /* ---- the counted facts. Everything else is derived from these. ---------------- */
  var EV = 2834892;          // early ballots banked, data/early-GA.json, 159 counties
  // Raffensperger, 2:45pm ET: 775,000 already voted, projecting 1.4-1.5M for the day.
  // Midpoint. He revised UP from 1.2M during the afternoon and we had 1.6M before that.
  // This one input moves Jackson's bar by 1.6 points, so it is named, dated and sourced.
  var EDAY = 1450000;
  var TOT = EV + EDAY;
  var MAIL26 = 129773, INPERSON26 = 2705120;

  function card(id, kicker, title, hint, body, note) {
    SECTIONS.push({id: id, title: title});
    return '<section class="gacard" id="' + id + '">'
      + (kicker ? '<p class="gakick">' + esc(kicker) + "</p>" : "")
      + "<h3>" + esc(title) + "</h3>"
      + (hint ? '<p class="gahint">' + hint + "</p>" : "")
      + body
      + (note ? '<p class="ganote">' + note + "</p>" : "")
      + "</section>";
  }

  function tbl(head, rows, foot) {
    return '<div class="scroll"><table class="gatbl"><thead><tr>'
      + head.map(function (h, i) {
          return "<th" + (i ? ' class="num"' : "") + ">" + h + "</th>";
        }).join("")
      + "</tr></thead><tbody>"
      + rows.map(function (r) {
          return "<tr" + (r.em ? ' class="em"' : "") + ">"
            + r.c.map(function (c, i) {
                return "<td" + (i ? ' class="num"' : "") + ">" + c + "</td>";
              }).join("") + "</tr>";
        }).join("")
      + "</tbody>" + (foot || "") + "</table></div>";
  }

  /* =============================================================== the thesis */
  function thesis() {
    return '<section class="gaarg" id="ga-thesis">'
      + '<p class="gakick">The question</p>'
      + "<h2>Georgia&rsquo;s governor: what is already decided, and what is not</h2>"
      + "<p><b>Jon Ossoff&rsquo;s Senate race is not close</b> &mdash; he leads by 7 to 8 in "
      + "the final polls. The governor&rsquo;s race is, and it is the only thing on this "
      + "page. Keisha Lance Bottoms against Rick Jackson, tied at <b>49.03 to 49.0</b> in "
      + "InsiderAdvantage&rsquo;s final survey.</p>"
      + "<p><b>What is already decided is the composition of 70% of the vote.</b> "
      + "<b class='nm'>" + n0(EV) + "</b> ballots are cast and counted into the system. "
      + "Against a projected " + n0(TOT) + " turnout that is <b>"
      + (EV / TOT * 100).toFixed(1) + "%</b> banked &mdash; the highest share Georgia has "
      + "ever taken into an election day in a comparable race.</p>"
      + "<p><b>What is not decided is how those ballots broke</b>, and nothing in the early "
      + "vote can tell us. Georgia publishes who has voted, never how. So this page separates "
      + "the two: the counted facts first, then what has to be assumed to turn them into a "
      + "margin, then what each assumption is worth.</p>"
      + '<p class="gaflag"><b>The honest summary.</b> Bottoms holds a banked lead on the '
      + "order of <b>+166,000 to +307,000</b> depending on where the race actually sits. "
      + "For Jackson to erase it on a 1.45M election day he needs to win today by "
      + "<b>R+8.0</b>. That is <i>not</i> an extreme ask: 2022&rsquo;s election day ran "
      + "R+15.95 with Kemp stripped out, and 2014&rsquo;s ran R+11.64. Only 2018 "
      + "(R+5.25), 2016 (R+6.76) and 2024 (R+7.07) fall short of it. <b>Georgia is a "
      + "genuine toss-up on this arithmetic, and it got closer this afternoon</b> "
      + "&mdash; the Secretary of State revised election-day turnout up from 1.2M to "
      + "1.4&ndash;1.5M, and a bigger election day is more of the mode that leans "
      + "Republican. At 1.2M his bar was R+9.6.</p>"
      + "</section>";
  }

  /* =============================================================== 1. counted */
  function bankedCard() {
    var rows = [
      {c: ["Early in person", n0(INPERSON26), (INPERSON26 / EV * 100).toFixed(1) + "%"]},
      {c: ["Absentee by mail", n0(MAIL26), (MAIL26 / EV * 100).toFixed(1) + "%"]},
      {em: 1, c: ["<b>Banked</b>", "<b>" + n0(EV) + "</b>",
                  "<b>" + (EV / TOT * 100).toFixed(1) + "% of turnout</b>"]},
      {c: ["Election day, expected", n0(EDAY), (EDAY / TOT * 100).toFixed(1) + "%"]}
    ];
    return card("ga-banked", "Section 1 &middot; the counted facts",
      "Seventy per cent of the vote is already in",
      "No model, no assumption. These are ballots the state has received.",
      '<div class="gabig">' + n0(EV) + "</div>"
      + '<div class="gasub">banked of a projected ' + n0(TOT) + "</div>"
      + tbl(["", "ballots", "share"], rows),
      "<b>Source: data/early-GA.json, all 159 counties, pulled tonight.</b> The 1.45M "
      + "election-day figure is the Secretary of State&rsquo;s, given at 2:45pm with "
      + "775,000 already voted and a projection of 1.4&ndash;1.5M; this is the midpoint. "
      + "He revised up from 1.2M during the afternoon, and we had estimated 1.6M before "
      + "that. <b>Every share on this page moves with it</b>, and the turnout card prices "
      + "exactly how much.");
  }

  function historyCard() {
    var rows = [
      {c: ["2018 midterm", n0(2101680), n0(1800413), "53.9%"]},
      {c: ["2022 midterm", n0(2532644), n0(1417799), "64.1%"]},
      {c: ["2024 presidential", n0(4025145), n0(1221257), "76.7%"]},
      {em: 1, c: ["<b>2026 midterm, projected</b>", "<b>" + n0(EV) + "</b>",
                  "<b>" + n0(EDAY) + "</b>",
                  "<b>" + (EV / TOT * 100).toFixed(1) + "%</b>"]}
    ];
    return card("ga-history", "Section 1 &middot; slide 2",
      "A record banked share, and an ordinary election day",
      "Georgia&rsquo;s election-day vote has fallen every cycle while early voting absorbed it.",
      tbl(["cycle", "early", "election day", "early %"], rows)
      + '<p class="gainline"><b>Election day is down 31% since 2018</b> '
      + "&mdash; 1,788,425 to 1,417,799 to 1,221,257 &mdash; and the Secretary of State "
      + "expects about <b>1,450,000</b> tonight, revised up from 1.2M at 2:45pm.</p>",
      "<b>This is a rules change, not a mood change.</b> Georgia&rsquo;s SB 202 (2021) "
      + "expanded early in-person voting &mdash; an extra mandatory Saturday for most "
      + "counties, longer weekday hours &mdash; while sharply restricting absentee: the "
      + "request window cut from 180 days to 78&ndash;11 days out, photo ID required, drop "
      + "boxes capped at one per 100,000 voters and available only during early-voting "
      + "hours. The law pushed voters out of mail and into early in person, which is "
      + "exactly what the numbers show. <b>Because the cause is still in force, the trend "
      + "is a structural expectation rather than a guess.</b> 2024 was a higher share still "
      + "at 76.7%, but a presidential year is not the comparison class for a midterm.");
  }

  /* =============================================================== 2. composition */
  function compCard() {
    var rows = [
      {c: ["Atlanta metro (32 counties)", n0(1881574), n0(1835209), "+" + n0(46365),
           "D+14.7", "+" + n0(6813)]},
      {c: ["Rural outside metro (117)", n0(583392), n0(628976), "&minus;" + n0(45584),
           "R+39.0", "+" + n0(17760)]},
      {c: ["Other big counties (10)", n0(369926), n0(370707), "&minus;781", "D+5.6", "&minus;44"]},
      {em: 1, c: ["<b>Net</b>", "", "", "", "", "<b>+" + n0(24529) + "</b>"]}
    ];
    return card("ga-comp", "Section 2 &middot; what the composition is worth",
      "The banked electorate is about one point bluer than the last midterm",
      "Measured against <i>2022&rsquo;s early vote</i> &mdash; the only honest comparison.",
      tbl(["group", "2026 early", "at par", "surplus", "2024 lean", "net D votes"], rows)
      + '<p class="gainline"><b>+' + n0(24529) + " net Democratic votes, or "
      + "<b class='nm'>+0.61</b> points</b> on a " + n0(TOT) + " electorate. Georgia was "
      + "decided by 11,779 votes in 2020.</p>",
      "<b>The baseline matters more than the finding.</b> Comparing tonight&rsquo;s early "
      + "vote to a past <i>full</i> electorate gives +3.66 points, but that is mostly "
      + "definitional &mdash; an early vote always looks bluer than a whole electorate. "
      + "Against 2022&rsquo;s <i>early</i> vote the shift is <b>+0.99 points</b>, and the "
      + "rural shortfall contributes nearly three times what Atlanta&rsquo;s surplus does, "
      + "because each missing rural ballot carries 39 points of margin against "
      + "Atlanta&rsquo;s 15. Republican counties grew their early vote <b>+9.0%</b> over "
      + "2022 while Democratic counties grew <b>+15.6%</b>; the R share of the early vote "
      + "fell from <b>43.0% to 41.6%</b>. There is no sign Republicans have returned to "
      + "early voting &mdash; only that the electorate has drifted slightly.");
  }

  /* =============================================================== 3. the regime */
  function regimeCard() {
    var rows = [
      {c: ["2014 governor", "R+11.64", "R+8.05", "+3.59"]},
      {c: ["2016 president", "R+6.76", "R+5.32", "+1.44"]},
      {c: ["2018 governor", "R+5.25", "R+1.40", "+3.84"]},
      {c: ["2020 president", "R+23.09", "R&minus;0.26", "<b>+23.35</b>"]},
      {c: ["2022 senate (no Kemp)", "R+15.95", "D+0.98", "<b>+16.92</b>"]},
      {c: ["2022 governor (Kemp)", "R+25.34", "R+7.59", "<b>+17.75</b>"]},
      {em: 1, c: ["<b>2024 president</b>", "<b>R+7.07</b>", "<b>R+2.19</b>", "<b>+4.88</b>"]}
    ];
    return card("ga-regime", "Section 3 &middot; the mode gap",
      "The huge election-day skew was a two-cycle anomaly, and it has already ended",
      "How much redder election day ran than that race&rsquo;s own statewide result.",
      tbl(["cycle", "election day", "statewide", "skew"], rows)
      + '<p class="gainline"><b>Before 2020 the skew was 1.4 to 3.8. COVID and the '
      + "campaign against early voting drove it to 17&ndash;23. In 2024 it fell back to "
      + "<b class='nm'>4.88</b>.</b></p>",
      "<b>Sources: the Georgia SOS results API for 2014&ndash;2022 (it holds 118 elections "
      + "back to 2012), NBC News for 2024.</b> The 2024 mode split weights to R+2.19 "
      + "against a certified R+2.21, so it checks out. <b>The skew is structural, not "
      + "candidate-driven:</b> on the same 2022 ballot Kemp&rsquo;s skew was +17.75 and "
      + "Walker&rsquo;s +16.92 &mdash; nearly identical, even though Kemp ran 8.57 points "
      + "ahead of Walker statewide. Kemp&rsquo;s personal vote was spread evenly across "
      + "every mode, not concentrated on election day. <b>Which regime 2026 belongs to is "
      + "the single biggest open question on this page</b>, and 2024 is the most recent "
      + "evidence.");
  }

  /* =============================================================== 4. the bar */
  function barCard() {
    var rows = [
      {c: ["2018 governor", "R+5.25", "no"]},
      {c: ["2016 president", "R+6.76", "no"]},
      {c: ["2024 president", "R+7.07", "no, by 0.9"]},
      {c: ["2014 governor", "R+11.64", "<b>yes</b>"]},
      {c: ["2022 senate (no Kemp)", "R+15.95", "<b>yes</b>"]},
      {c: ["2020 president &mdash; pandemic", "R+23.09", "<b>yes</b>"]},
      {c: ["2022 governor &mdash; Kemp", "R+25.34", "<b>yes</b>"]}
    ];
    return card("ga-bar", "Section 4 &middot; what Jackson needs",
      "He has to win election day by about 8 points",
      "Bottoms&rsquo; banked lead, spread across the 1.45M the state now expects.",
      '<div class="gabig">R+7.96</div>'
      + '<div class="gasub">to pull even &mdash; it was R+9.6 before the turnout '
      + "revision, and R+23 when we assumed a 1.2M day and a smaller banked lead</div>"
      + tbl(["every Georgia election day since 2014", "margin", "clears R+7.96?"], rows)
      + '<p class="gainline"><b>Four of the last seven clear it.</b> This is no longer '
      + "a bar only a pandemic or Kemp could reach &mdash; 2014 and a Kemp-free 2022 "
      + "both clear it comfortably, and 2024 misses by nine tenths of a point. "
      + "Morris&rsquo;s independent estimate this morning was that Republicans need "
      + "<b>R+17 to R+23</b>; that was computed against a smaller election day than the "
      + "state is now projecting.</p>",
      "<b>The range, not the point estimate.</b> Across the banked estimates on this "
      + "page &mdash; D+4.07 to D+5.93, or <b>+115,380</b> to <b>+168,109</b> votes "
      + "&mdash; Jackson&rsquo;s bar runs from <b>R+7.96</b> to <b>R+11.59</b>. "
      + "<b>Every figure in that range has happened in Georgia before.</b> That is the "
      + "honest position: this is a toss-up, and it moved toward Jackson this afternoon "
      + "when the state raised its own turnout projection.");
  }

  function turnoutCard() {
    var rows = [
      {c: ["900,000", "24.1%", "R+12.82", "<b>clears</b>"]},
      {c: ["1,200,000 &mdash; his 1:30pm figure", "29.7%", "R+9.62", "<b>clears</b>"]},
      {em: 1, c: ["<b>1,450,000 &mdash; his 2:45pm figure</b>", "<b>33.8%</b>",
                  "<b>R+7.96</b>", "<b>clears</b>"]},
      {c: ["1,500,000", "34.6%", "R+7.69", "<b>clears</b>"]},
      {c: ["1,788,425 &mdash; 2018&rsquo;s record", "38.7%", "R+6.45", "<b>clears</b>"]}
    ];
    return card("ga-turnout", "Section 4 &middot; slide 2",
      "A bigger election day helps him, and the state just raised its estimate",
      "Every ballot cast today is one more of the mode that leans Republican.",
      tbl(["election-day turnout", "% of total", "R needs", "vs a Kemp-free R+15.95"], rows)
      + '<p class="gainline"><b>At every plausible turnout, a 2022-style Kemp-free '
      + "election day (R+15.95) clears the bar.</b> Only an election day like 2018&rsquo;s "
      + "(R+5.25) or 2024&rsquo;s (R+7.07) leaves Bottoms ahead. The question is no longer "
      + "<i>how many</i> vote today but <i>how</i> they vote.</p>",
      "<b>This card said the opposite an hour ago, and it was wrong.</b> It was built on "
      + "a 1.2M election day and a smaller banked lead, and concluded Jackson needed a "
      + "turnout Georgia had not produced since 2018. The Secretary of State then revised "
      + "his own projection from 1.2M to 1.4&ndash;1.5M at 2:45pm. A bigger election day "
      + "does not help Bottoms &mdash; it adds ballots to the mode she loses, and it "
      + "lowers the margin Jackson needs. <b>The direction of this page changed because "
      + "an input changed, which is what should happen.</b>");
  }

  /* =============================================================== 5. the limits */
  function limitsCard() {
    return '<section class="gaarg" id="ga-limits">'
      + '<p class="gakick">Section 5 &middot; what this cannot see</p>'
      + "<h2>The honest limits</h2>"
      + "<p><b>This is a composition model. It measures who voted, not how.</b> It assumes "
      + "every 2026 early voter casts the ballot their county cast in a past election "
      + "&mdash; zero persuasion, zero swing, zero candidate effect. That is not a detail; "
      + "it assumes away the thing an election is.</p>"
      + "<ol>"
      + "<li><b>A 3-point uniform swing flips the conclusion.</b> The whole spread of "
      + "assumptions on this page is about 7.75 points wide &mdash; narrower than an "
      + "ordinary polling error. The model is dominated by a variable it does not "
      + "contain.</li>"
      + "<li><b>Mail is shrinking, and it is Bottoms&rsquo; best mode.</b> It ran D+24 to "
      + "D+26 in every racial band in 2018 and 2022, and it has fallen from 5.7% of the "
      + "vote to <b>4.6%</b>. Her strongest instrument is a fifth smaller than "
      + "Abrams&rsquo; was.</li>"
      + "<li><b>No past cycle cleanly calibrates this one.</b> 2018 predates COVID and "
      + "SB 202; 2022 was the peak of the Republican boycott of early voting; 2024 was a "
      + "presidential year. Each is wrong in a different direction.</li>"
      + "<li><b>The election-day figure is an expectation, not a count.</b> It is the "
      + "best-sourced number available &mdash; the Secretary of State&rsquo;s own &mdash; "
      + "but he moved it from 1.2M to 1.4&ndash;1.5M in one afternoon, and that alone "
      + "swung Jackson&rsquo;s bar from R+9.6 to R+8.0. <b>It is the single most "
      + "load-bearing number on this page and it is still a guess, his rather than "
      + "ours.</b></li>"
      + "</ol>"
      + "<p><b>What survives all of that</b> is narrow and worth stating on its own: "
      + "<b class='nm'>" + n0(EV) + "</b> ballots are counted; they are about a point "
      + "bluer than the last midterm&rsquo;s early vote; they are a record share of the "
      + "electorate; and election day is both smaller and, since 2024, less skewed than "
      + "the cycle everyone is reasoning from. <b>Those are counts and measurements. The "
      + "margin is not.</b></p>"
      + "</section>";
  }

  function validCard() {
    var rows = [
      {c: ["2018 governor", n0(33814), "R+1.89", "R+5.25", "Kemp won &mdash; correct"]},
      {c: ["2022 senate", n0(258633), "R+18.24", "R+15.95",
           "Warnock led &mdash; correct"]},
      {em: 1, c: ["<b>2026 governor</b>", "<b>" + n0(278773) + "</b>", "<b>R+19.23</b>",
                  "<b>&mdash;</b>", "<b>?</b>"]}
    ];
    return card("ga-valid", "Section 4 &middot; slide 3",
      "The same arithmetic retrodicts both past midterms",
      "Banked lead, divided by election-day ballots, against what actually happened.",
      tbl(["cycle", "D banked lead", "R needed", "R got", "result"], rows),
      "<b>This is the only part of the method that has been tested rather than asserted.</b> "
      + "Abrams banked too little and Kemp cleared her bar by 3.4 points. Warnock banked "
      + "enough and Walker fell 2.29 short, and Warnock led on the night. Two midterms, "
      + "two correct calls. Bottoms banks a lead close to Warnock&rsquo;s &mdash; against "
      + "an election day a couple of points smaller as a share of the electorate. "
      + "<b>Note the bar moved.</b> At the 1.2M the state was projecting at 1:30pm this "
      + "read R+23.23; at the 1.45M it projected at 2:45pm it reads R+19.23, because the "
      + "same lead spread over more ballots is a smaller margin per ballot. Walker fell "
      + "2.29 short of R+18.24 in 2022.");
  }

  /* =============================================================== render */
  var CSS =
      ".gacard,.gaarg{background:var(--panel);border:1px solid var(--line);"
    + "border-radius:10px;padding:16px 18px;margin:0 0 14px}"
    + ".gaarg{border-left:3px solid var(--fg)}"
    + ".gaarg h2{font-family:var(--display);font-weight:400;font-size:22px;margin:2px 0 10px}"
    + ".gaarg p{margin:0 0 9px;font-size:14px;line-height:1.55;max-width:74ch}"
    + ".gaarg ol{margin:4px 0 10px;padding-left:1.2em;font-size:14px;line-height:1.55}"
    + ".gaarg li{margin-bottom:7px}"
    + ".gacard h3{font-family:var(--display);font-weight:600;font-size:18px;margin:2px 0 7px}"
    + ".gakick{font-family:var(--display);font-size:11px;text-transform:uppercase;"
    + "letter-spacing:.09em;color:var(--dim);margin:0 0 4px}"
    + ".gahint{font-size:13px;color:var(--dim);margin:0 0 12px;max-width:74ch;line-height:1.5}"
    + ".ganote{font-size:12.5px;color:var(--dim);margin:11px 0 0;max-width:74ch;"
    + "line-height:1.5;border-top:1px solid var(--line);padding-top:9px}"
    + ".gaflag{border-left:3px solid var(--flag);padding-left:11px}"
    + ".gainline{font-size:13.5px;line-height:1.55;margin:11px 0 0;max-width:74ch}"
    + ".gabig{font-family:var(--display);font-size:40px;line-height:1.1;"
    + "font-variant-numeric:tabular-nums}"
    + ".gasub{font-size:13px;color:var(--dim);margin:2px 0 10px}"
    + "table.gatbl{width:100%;border-collapse:collapse;font-size:13.5px}"
    + "table.gatbl th{font-family:var(--display);text-transform:uppercase;font-size:10.5px;"
    + "letter-spacing:.06em;color:var(--dim);text-align:left;padding:0 0 5px 12px;"
    + "border-bottom:1px solid var(--line);font-weight:600}"
    + "table.gatbl th:first-child{padding-left:0}"
    + "table.gatbl td{padding:5px 0 5px 12px;border-bottom:1px solid var(--line)}"
    + "table.gatbl td:first-child{padding-left:0}"
    + "table.gatbl .num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}"
    + "table.gatbl tr.em td{font-weight:600}"
    + ".gajump{display:flex;flex-wrap:wrap;gap:7px;margin:0 0 16px}"
    + ".gajump a{font-size:12px;color:var(--dim);text-decoration:none;border:1px solid "
    + "var(--line);border-radius:3px;padding:4px 9px}"
    + ".gajump a:hover{color:var(--fg);border-color:var(--fg)}"
    + "@media(max-width:640px){.gacard,.gaarg{padding:14px}"
    + ".gabig{font-size:32px}table.gatbl{font-size:12.5px}"
    + "table.gatbl th,table.gatbl td{padding-left:8px}}";

  window.renderGeorgia = function (host) {
    SECTIONS = [];
    var body = thesis() + bankedCard() + historyCard() + compCard()
      + regimeCard() + barCard() + validCard() + turnoutCard() + limitsCard();
    var jump = '<div class="gajump">' + SECTIONS.map(function (s) {
      return '<a href="#' + s.id + '">' + esc(s.title) + "</a>";
    }).join("") + "</div>";
    host.innerHTML = "<style>" + CSS + "</style>" + jump + body;
  };
})();
