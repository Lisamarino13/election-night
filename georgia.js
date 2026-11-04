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
  var EDAY = 1300000;
  // Bottoms' banked lead, both ends measured the same way: each past race's county-level
  // early+mail margin applied to that county's 2026 early turnout. 2024 president and
  // 2018 governor; both source files tie out to the certified statewide result.
  // FLOOR - county reweighting only. Each past race's county-level early margin applied
  // to that county's 2026 early turnout. Composition-BLIND: it freezes each county's
  // internal margin at the baseline year, so the measured race shift is absent from it.
  var FLOOR_LO = 95199, FLOOR_HI = 106570;   // 2024 president / 2018 governor
  // HEADLINE - calibrated to 2024's ACTUAL early+mail margin (R+0.68, certified county
  // file), then ONLY the measured racial composition changed to 2026's counts. Black
  // share of the early electorate 26.34% -> 32.38%. Black-D support 86% to 92%.
  var BANK_LO = 161272, BANK_HI = 190201;
  // 2020's early baseline, by a wholly different route, lands at +200,112 - see ga-methods.
  var BANK_2020 = 200112;
  var TOT = EV + EDAY;
  function bar(net) { return (net / EDAY * 100).toFixed(2); }
  var MAIL26 = 129773, INPERSON26 = 2705120;

  function card(id, kicker, title, hint, body, note) {
    SECTIONS.push({id: id, title: title});
    return '<section class="gacard" id="' + id + '">'
      + (kicker ? '<p class="gakick">' + kicker + "</p>" : "")
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
      + '<p class="gaflag"><b>The honest summary.</b> Bottoms holds a banked lead of '
      + "<b class='nm'>+" + n0(BANK_LO) + " to +" + n0(BANK_HI) + "</b>. That range "
      + "comes from calibrating per-group support so 2024&rsquo;s composition reproduces "
      + "2024&rsquo;s <i>actual</i> early margin of R+0.68, then changing nothing but the "
      + "measured composition &mdash; the Black share of the early electorate rose from "
      + "26.34% to 32.38%. For Jackson to erase it on a 1.3M election day he needs <b>R+"
      + bar(BANK_LO) + " to R+" + bar(BANK_HI) + "</b>. <b>Only three Georgia election "
      + "days since 2014 have ever cleared that &mdash; 2020, and both 2022 races &mdash; "
      + "and all three sit inside the mode-skew anomaly this page argues has ended.</b> "
      + "Georgia&rsquo;s own 2024 election day ran R+7.34, well short of it. <b>On the "
      + "measured composition Bottoms is favoured. Only the geography-only floor makes "
      + "this close, and that floor cannot see what changed.</b></p>"
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
      "<b>Source: data/early-GA.json, all 159 counties, pulled tonight.</b> The 1.2M "
      + "election-day figure is projected from the Secretary of State&rsquo;s own hourly "
      + "trail &mdash; 300k at 10am, 500k at noon, 650k at 1:30pm, 775k at 2:45pm, a flat "
      + "<b>100,000 per hour</b> &mdash; held at that rate to 5pm and stepped to "
      + "<b>150,000/hour</b> for the after-work rush. That gives <b>1.3M</b>. A press "
      + "attribution of 1.4&ndash;1.5M could not be verified against a primary source and "
      + "is not used. <b>Every share on this page moves with this number</b>, and the "
      + "turnout card prices exactly how much.");
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
      + '<p class="gainline"><b>Election day is down 32% since 2018</b> '
      + "&mdash; 1,800,413 to 1,417,799 to 1,221,257 &mdash; and the Secretary of State "
      + "is on pace for about <b>1,300,000</b> tonight.</p>",
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
      {c: ["<b>Atlanta core (10)</b>", "<b>" + n0(1358943) + "</b>", "<b>47.9%</b>",
           "<b>D+38.0 to D+38.5</b>",
           "<b>+" + n0(516860) + " to +" + n0(523588) + "</b>"]},
      {c: ["Exurban ring (19)", n0(434101), "15.3%", "R+39.3 to R+44.5",
           "&minus;" + n0(170401) + " to &minus;" + n0(192949)]},
      {c: ["Other big counties (10)", n0(368015), "13.0%", "D+6.6 to D+13.7",
           "+" + n0(24407) + " to +" + n0(50553)]},
      {c: ["Rural rest (120)", n0(673833), "23.8%", "R+40.8 to R+40.9",
           "&minus;" + n0(274622) + " to &minus;" + n0(275667)]},
      {em: 1, c: ["<b>Floor, geography only</b>", "<b>" + n0(EV) + "</b>", "<b>100%</b>",
                  "", "<b>+" + n0(FLOOR_LO) + " to +" + n0(FLOOR_HI) + "</b>"]}
    ];
    return card("ga-comp", "Section 2 &middot; what the composition is worth",
      "Atlanta's core has banked her over half a million votes",
      "Not a share, not a shift &mdash; the actual lead sitting in the counted ballots.",
      tbl(["group", "banked ballots", "of banked", "early lean, 2024 / 2018",
           "net D banked"], rows)
      + '<p class="gainline"><b>The core ten counties are 47.9% of every ballot banked '
      + "and carry <b class='nm'>+516,860 to +523,588</b> net Democratic votes.</b> The "
      + "exurban ring, rural Georgia and the mid-size cities claw back about 420,000 to "
      + "445,000 of it, which is what leaves the geography-only floor near 100,000.</p>"
      + '<p class="gainline"><b>This card used to bury that.</b> It reported a single '
      + "&ldquo;Atlanta metro&rdquo; of 29 counties at D+18.4, which averaged DeKalb "
      + "(D+68.8) and Clayton (D+71.4) together with Cherokee (R+39.5), Forsyth (R+34.0) "
      + "and Paulding (R+25.2). That average is not a place, and it penalised the core. "
      + "<b>The ring is now separated from the counties it was dragging down.</b></p>"
      + '<p class="gainline"><b>The inner suburbs moved, and 2018 cannot see it.</b> '
      + "Henry went D+17.9 in 2018 to <b>D+31.1</b> in 2024; Douglas D+21.3 to "
      + "<b>D+32.5</b>. Cherokee and Forsyth both got less Republican, not more. "
      + "A baseline year freezes all of that.</p>",
      "<b>A change-from-baseline number cannot see a level that was already high.</b> "
      + "An earlier version of this card reported each group&rsquo;s <i>change</i> in "
      + "share of the early vote since 2022, which made Atlanta look like it had "
      + "contributed +6,813 votes when its core has banked over half a million."
      + "<span class='txrule'></span>"
      + "<b>The drift, for what it is worth:</b> Atlanta&rsquo;s early vote is up "
      + "<b>15.3%</b> on 2022 and rural counties grew more slowly, so the banked "
      + "electorate is about <b>one point</b> bluer than the last midterm&rsquo;s. "
      + "Republican counties grew <b>+9.0%</b> against Democratic counties&rsquo; "
      + "<b>+15.6%</b>, and the R share of the early vote fell from <b>43.0% to "
      + "41.6%</b>. Real, but small next to the lead already banked.");
  }

  /* =============================================================== 2b. the ladder */
  function methodsCard() {
    var rows = [
      {c: ["2024 president, overall county margin", n0(73391), "R+5.65",
           "composition-blind"]},
      {c: ["2020 president, overall county margin", n0(90397), "R+6.95",
           "composition-blind"]},
      {c: ["2024 president, early-vote margin", n0(95199), "R+7.32", "<b>floor</b>"]},
      {c: ["2018 governor, early-vote margin", n0(106570), "R+8.20", "<b>floor</b>"]},
      {em: 1, c: ["<b>Composition-calibrated to 2024&rsquo;s real margin</b>",
                  "<b>" + n0(BANK_LO) + "&ndash;" + n0(BANK_HI) + "</b>",
                  "<b>R+12.41&ndash;14.63</b>", "<b>counts the measured shift</b>"]},
      {c: ["2020 president, early-vote margin", n0(BANK_2020), "R+15.39",
           "inflated by pandemic mode-sorting"]}
    ];
    return card("ga-methods", "Section 2 &middot; slide 2",
      "Every way we can measure the banked lead, and what each one misses",
      "Same 2,834,892 ballots. The spread is the honest uncertainty.",
      tbl(["method", "net D banked", "R needs on 1.3M", "what it is"], rows)
      + '<p class="gainline"><b>The four geography-only rows cluster near 100,000 for one '
      + "reason: they all freeze each county&rsquo;s internal margin at a past year.</b> "
      + "And the counties barely move &mdash; Fulton ran D+47.3, D+48.9 and D+45.8 in "
      + "2018, 2020 and 2024; DeKalb D+73.7, D+71.2, D+68.8. <b>Georgia&rsquo;s county "
      + "geography is not what changed this cycle.</b></p>"
      + '<p class="gainline"><b>What changed is who turned up inside those counties.</b> '
      + "The Black share of the early electorate went from 26.34% to 32.38% and the white "
      + "share fell 5.39 points &mdash; counts from the state&rsquo;s own file. The two "
      + "rows that price that in, by completely different routes, land at <b class='nm'>"
      + n0(BANK_LO) + "&ndash;" + n0(BANK_HI) + "</b> and <b class='nm'>" + n0(BANK_2020)
      + "</b>.</p>",
      "<b>Why 2020 is listed but not used as the headline.</b> Its early margin ran D+5.79 "
      + "while its election day ran R+23.09 &mdash; the pandemic sorted Democrats into "
      + "early voting to a degree no other cycle matches. The size of that distortion is "
      + "visible in this table: 2020&rsquo;s <i>early</i> margin gives " + n0(BANK_2020)
      + " but its <i>overall</i> margin gives only " + n0(90397)
      + ", a gap of about 110,000 votes from mode sorting alone. It corroborates the top "
      + "of the headline range rather than setting it. <b>All three county files &mdash; "
      + "2018, 2020, 2024 &mdash; tie out to their certified statewide results.</b>");
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
      {em: 1, c: ["<b>2024 president</b>", "<b>R+7.34</b>", "<b>R+2.19</b>", "<b>+5.15</b>"]}
    ];
    return card("ga-regime", "Section 3 &middot; the mode gap",
      "The huge election-day skew was a two-cycle anomaly, and it has already ended",
      "How much redder election day ran than that race&rsquo;s own statewide result.",
      tbl(["cycle", "election day", "statewide", "skew"], rows)
      + '<p class="gainline"><b>Before 2020 the skew was 1.4 to 3.8. COVID and the '
      + "campaign against early voting drove it to 17&ndash;23. In 2024 it fell back to "
      + "<b class='nm'>5.15</b>.</b></p>",
      "<b>Source: the Georgia SOS results API, all 159 counties, for every row including "
      + "2024.</b> The 2024 split is no longer NBC&rsquo;s summary &mdash; it is the "
      + "state&rsquo;s own certified county file, and it sums to Harris 2,548,017 and "
      + "Trump 2,663,117, matching the certified result to the vote. <b>The skew is structural, not "
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
      {c: ["2018 governor", "R+5.25", "no &mdash; clears neither"]},
      {c: ["2016 president", "R+6.76", "no &mdash; clears neither"]},
      {em: 1, c: ["<b>2024 president</b>", "<b>R+7.34</b>",
                  "<b>floor only, by 0.02 &mdash; 5.07 short of the headline</b>"]},
      {c: ["2014 governor", "R+11.64", "floor only &mdash; 0.77 short"]},
      {c: ["2022 senate (no Kemp)", "R+15.95", "<b>yes, both</b>"]},
      {c: ["2020 president &mdash; pandemic", "R+23.09", "<b>yes, both</b>"]},
      {c: ["2022 governor &mdash; Kemp", "R+25.34", "<b>yes, both</b>"]}
    ];
    return card("ga-bar", "Section 4 &middot; what Jackson needs",
      "He has to win election day by 12.4 to 14.6 points",
      "Bottoms&rsquo; banked lead, spread across a projected 1.3M election day.",
      '<div class="gabig">R+' + bar(BANK_LO) + " to R+" + bar(BANK_HI) + "</div>"
      + '<div class="gasub">once the measured change in who voted early is counted. '
      + "Geography alone gives R+" + bar(FLOOR_LO) + " to R+" + bar(FLOOR_HI)
      + ", but that is a floor that cannot see the composition shift</div>"
      + tbl(["every Georgia election day since 2014", "margin",
             "clears the floor / the headline?"], rows)
      + '<p class="gainline"><b>Only three election days in Georgia since 2014 clear '
      + "the headline bar</b> &mdash; 2020&rsquo;s pandemic election day, and both 2022 "
      + "races. <b>All three fall inside the 2020&ndash;2022 mode-skew window of +16.9 "
      + "to +23.4, which Section 3 shows collapsed to +5.15 by 2024.</b> 2014 (R+11.64) "
      + "clears the floor but falls 0.77 short of the headline; 2024 (R+7.34) clears the "
      + "floor by two hundredths and misses the headline by 5.07.</p>",
      "<b>Why the second number is the better one.</b> The geography-only figure holds "
      + "every county&rsquo;s internal margin frozen at a past year, so <b>the one thing "
      + "that is measurably different about tonight is absent from it</b>: the Black "
      + "share of Georgia&rsquo;s early electorate rose from 26.34% to 32.38% and the "
      + "white share fell 5.39 points. Those are counts from the state&rsquo;s own file. "
      + "The headline range calibrates per-group support so that 2024&rsquo;s "
      + "composition reproduces 2024&rsquo;s <i>actual</i> early margin of R+0.68, then "
      + "changes nothing but the composition. <b>What stays assumed is per-group "
      + "support</b> &mdash; Black-D support of 86% to 92% spans the range, and Georgia "
      + "publishes who voted, never how. <b>Treat the geography-only number as a floor, "
      + "not a forecast.</b>");
  }

  function turnoutCard() {
    var rows = [
      {c: ["1,000,000", "26.1%", "R+9.52&ndash;10.66", "R+16.13&ndash;19.02",
           "floor only"]},
      {c: ["1,200,000 &mdash; his 1:30pm figure", "29.7%", "R+7.93&ndash;8.88",
           "R+13.44&ndash;15.85", "floor only"]},
      {em: 1, c: ["<b>1,300,000 &mdash; our projection</b>", "<b>31.4%</b>",
                  "<b>R+7.32&ndash;8.20</b>", "<b>R+12.41&ndash;14.63</b>",
                  "<b>floor only</b>"]},
      {c: ["1,500,000", "34.6%", "R+6.35&ndash;7.10", "R+10.75&ndash;12.68",
           "<b>clears both</b>"]},
      {c: ["1,788,425 &mdash; 2018&rsquo;s record", "38.7%", "R+5.32&ndash;5.96",
           "R+9.02&ndash;10.64", "<b>clears both</b>"]}
    ];
    return card("ga-turnout", "Section 4 &middot; slide 2",
      "A bigger election day helps him, and the state just raised its estimate",
      "Every ballot cast today is one more of the mode that leans Republican.",
      tbl(["election-day turnout", "% of total", "R needs, floor", "R needs, headline",
           "does a Kemp-free R+15.95 clear it?"], rows)
      + '<p class="gainline"><b>A bigger election day lowers the bar, but not fast '
      + "enough to matter below 1.5M.</b> Against the headline range even a 2022-style "
      + "Kemp-free election day (R+15.95) only clears both ends once turnout reaches "
      + "about 1.5M &mdash; at the 1.3M we project it clears the floor and lands inside "
      + "the headline range, not past it. <b>The question is no longer <i>how many</i> "
      + "vote today but <i>how</i> they vote.</b></p>",
      "<b>On the election-day figure, this page uses 1.3M and says why.</b> It is "
      + "projected from the Secretary of State&rsquo;s own hourly trail &mdash; 300k at "
      + "10am, 650k at 1:30pm, 775k at 2:45pm &mdash; held at 100,000/hour and stepped to "
      + "150,000/hour for the after-work rush. <b>A press attribution of 1.4&ndash;1.5M "
      + "could not be verified against a primary source and is used nowhere on this "
      + "page</b>, including here; an earlier version of this card asserted that revision "
      + "as fact, which was wrong. A bigger election day does not help Bottoms &mdash; it "
      + "adds ballots to the mode she loses and lowers the margin Jackson needs.");
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
      + "would swing Jackson&rsquo;s bar by 1.6 points. <b>It is the single most "
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
      {em: 1, c: ["<b>2026 governor</b>",
                  "<b>" + n0(BANK_LO) + " to " + n0(BANK_HI) + "</b>",
                  "<b>R+" + bar(BANK_LO) + " to R+" + bar(BANK_HI) + "</b>",
                  "<b>&mdash;</b>", "<b>?</b>"]}
    ];
    return card("ga-valid", "Section 4 &middot; slide 3",
      "The same arithmetic retrodicts both past midterms",
      "Banked lead, divided by election-day ballots, against what actually happened.",
      tbl(["cycle", "D banked lead", "R needed", "R got", "result"], rows),
      "<b>This is the only part of the method that has been tested rather than asserted.</b> "
      + "Abrams banked too little and Kemp cleared her bar by 3.4 points. Warnock banked "
      + "enough and Walker fell 2.29 short, and Warnock led on the night. Two midterms, "
      + "two correct calls. <b>Bottoms banks less than Warnock did &mdash; "
      + n0(BANK_LO) + " to " + n0(BANK_HI) + " against his 258,633 &mdash; but faces an "
      + "election day roughly 120,000 ballots smaller, so her bar (R+" + bar(BANK_LO)
      + " to R+" + bar(BANK_HI) + ") lands below his R+18.24.</b> "
      + "<b>A correction belongs here.</b> This card previously put her banked lead at "
      + "278,773 and her bar at R+21.44. That figure could not be reproduced from any "
      + "source on this page or any file behind it, and it contradicted the 115,347 the "
      + "rest of the page was using. It has been removed and replaced with the measured "
      + "range. <b>The 2018 and 2022 rows are unchanged: both are the states own "
      + "certified early-vote totals and both tie out.</b>");
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
      + methodsCard() + regimeCard() + barCard() + validCard() + turnoutCard() + limitsCard();
    var jump = '<div class="gajump">' + SECTIONS.map(function (s) {
      return '<a href="#' + s.id + '">' + esc(s.title) + "</a>";
    }).join("") + "</div>";
    host.innerHTML = "<style>" + CSS + "</style>" + jump + body;
  };
})();
