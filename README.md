# Midterm Night Board

County-by-county early vote and election-night tracking for the competitive 2026 Senate
and Governor races, pulled straight from secretary-of-state sources.

**Live board:** https://lisamarino13.github.io/election-night/

## The projection

The number that matters on election night is not "who's ahead" — it's **who's ahead once
the ballots that haven't been counted yet are counted.** Those two answers differ whenever
the outstanding vote is concentrated somewhere that votes differently from the state as a
whole, which is most of the time.

So the projection is per county, never statewide:

```
for each county:
    share[candidate] = votes[candidate] / votes_counted_in_that_county
    projected[candidate] += votes[candidate] + share[candidate] * outstanding_in_that_county
```

Applying each county's *own* rate to its *own* outstanding ballots, then summing. The
statewide shortcut — one average rate applied to one pile of outstanding votes — gets a
different answer, and in a close race the difference decides it.

A worked example from Michigan test data: the per-county sum gives D +68,770 / R +40,820
from the outstanding vote, while the statewide ratio gives D +61,739 / R +47,846. A
**7,031-vote** gap, entirely because the outstanding ballots sit in Wayne County (69.7% D)
rather than at the statewide 55.6%.

This is the method behind calling Georgia for Biden two days before the decision desks did.

## What the data actually supports

Being honest about the sources is most of the value here.

**Mail and in-person early voting are never pooled.** They break in opposite directions.
Florida's 2026 mail vote is running D+7; Florida's in-person early vote finished R+21 in
2022. Averaging them hides a 28-point gap.

**"Outstanding" is never shown as zero.** Maine and Florida publish ballots issued but not
yet returned, so their outstanding is a real count. North Carolina does not publish it at
all — that card shows a dash. A zero would read as "nothing left to count" and make a
projection look certain when the quantity is simply unknown.

**Party registration does not exist everywhere.** Florida, North Carolina, Maine, Iowa,
Nebraska, Kansas and Alaska register voters by party. Texas, Ohio, Michigan, Minnesota,
South Carolina and Georgia do not — so for those states this shows turnout only. Any D/R
early-vote split you see published for Texas or Georgia is a vendor model, not a count.

**Presidential and midterm cycles are not comparable.** Florida's 2020 mail vote was 4.86M
against 2.77M in 2022 — that gap is the calendar, not a trend. Pace is always measured
against the most recent midterm, and presidential years are labeled as context.

## Collectors

| State | Source | Streams | Party | Outstanding |
|---|---|---|---|---|
| Florida | `electionfiles.floridados.gov`, daily ~8am ET | mail (in-person when EV opens) | yes | yes |
| North Carolina | `dl.ncsbe.gov` ballot-level zip, daily | mail + in-person | yes | not published |
| Maine | `maine.gov` statewide absentee file, daily | mail + in-person | yes | yes |
| Texas | `earlyvoting.texas-election.com`, all 254 counties | mail + in-person | none in state | n/a |

Every collector **fails closed**: any fetch or parse problem raises and writes nothing, so
a bad run leaves yesterday's good data in place rather than blanking the board or
publishing a zero.

Two source hazards worth knowing, both found the hard way:

- **Florida's CDN serves mixed days.** Two fetches of the same URL seconds apart returned
  different dates, and outstanding and returned can come from different days. Every run now
  requires both files to carry the same compile date, and retries until they do.
- **North Carolina renamed a field value.** 2020 and 2022 say `ONE-STOP`; 2024 onward says
  `EARLY VOTING`. Matching only the new spelling turned 4.1 million in-person ballots into a
  silent zero. Unrecognized values now raise instead of being dropped.

## Running it

```bash
collectors/run_all.sh          # pull every state, archive, rebuild the store
```

`data/snapshots/early-<ST>-<date>.json` is the durable record, keyed on the **state's own**
as-of date, so re-running is idempotent. `data/ev.db` is derived and rebuildable:

```bash
python3 collectors/ingest.py --rebuild
```

Historical cycles are one-shot pulls, already committed:

```bash
python3 collectors/fl_history.py            # FL 2020 / 2022 / 2024
python3 collectors/nc_absentee.py --history # NC 2020 / 2022 / 2024
python3 collectors/tx_earlyvote.py --history
```

## Sources

All data is public and comes from state election authorities. Nothing here is modeled or
estimated except where a tile says so explicitly; the break-rate assumptions used in the
party-weighted view are labeled as assumptions, because that is what they are.
