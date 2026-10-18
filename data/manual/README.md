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
