# Manual drop folder

Mostly unnecessary now. The UF Election Lab publishes plain CSVs for the states that do not
serve a usable file of their own, so Georgia, Ohio, Minnesota, Michigan, Nebraska and
Kansas are all collected automatically by `collectors/uf_earlyvote.py`.

This folder still exists for one reason: **a primary source beats an aggregate.** If you
download a file from the state itself, drop it here and it overrides the Election Lab's
figure for that state. `manual_import.py` runs after `uf_earlyvote.py` for exactly that
reason.

    data/manual/MN-<YYYY-MM-DD>.html     Minnesota absentee page, saved from the browser
    data/manual/GA-<YYYY-MM-DD>.csv      Georgia absentee file (parser not written yet)
    data/manual/OH-<YYYY-MM-DD>.txt      Ohio Absentee_Request_Report.txt (parser not written yet)

Use the date the STATE reports for, not the day you downloaded — same rule the automated
collectors follow, so re-downloading a day replaces it rather than inventing a second one.

Worth knowing: for Minnesota the two sources disagree on one figure. The state's page says
6,263 applications for Aitkin County; the Election Lab says 5,981 requested. Mail returned
and in-person match exactly (1,814 / 282), so the difference is in what counts as a
request, and it only affects the derived outstanding number.

## Pulling a state by hand

Some states publish on a dashboard with nothing to download — Michigan's is a Power BI
embed. For those, drop a small JSON with the numbers you read off the screen:

    data/manual/<ST>-<YYYY-MM-DD>.json

    {"state":"MI","as_of":"2026-11-02 07:04",
     "by_mail":1569715,"in_person":743450,"total":2313165,
     "registered":7420172,
     "source":"https://www.michigan.gov/sos/.../voter-participation-dashboard"}

Then `python3 collectors/manual_import.py`.

It replaces the STATE TOTAL only and leaves the county rows alone, because a dashboard
that gives no county split cannot be turned into one — scaling 83 counties to hit a new
statewide figure would invent 83 numbers nobody published. The card shows the current
state total over county detail that is openly older, and says so.

It refuses the file if `by_mail + in_person` does not equal `total`. That sum is the one
arithmetic check the dashboard itself offers, so it is worth making.

`uf_earlyvote.py` will not overwrite a hand-read file that is newer than the Election
Lab's copy, so the half-hourly cron cannot put a stale figure back. It holds only while
the hand file is the fresher of the two — an override cannot outlive its day.

### Where to read each one

| State | Where | Notes |
|---|---|---|
| MI | michigan.gov/sos → Voter Participation Dashboard | Power BI; read absentee returned, early voting cast, total. No county split. |
| SC | scvotes.gov → Voter Registration and Participation Statistics | Links the current `EV-Totals-*.csv`. **Watch the folder**: the 11/02 file is published under an *October* filename inside `/uploads/2026/11/`. Full county and poll-place detail. |
| MN | sos.mn.gov absentee data page | Server-rendered county table; save the page as HTML and `manual_import.py` parses it. |

### Known good cross-check

`onpointpolitics.us/maps/early-vote/<state>` carries the same state-office counts (via
civicAPI) and is a fast second opinion on a total. It agreed exactly with this board on
Iowa, Minnesota and Nebraska on 11-02.

It is NOT a source to copy from. On the same day it had Michigan at 1,459,825 — mail
only, no in-person at all, 853,340 ballots behind Michigan's own dashboard. A tracker
that is right about three states can still be carrying one state's frozen feed, which is
the same failure this board had until the figure was read by hand.
