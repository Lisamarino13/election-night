# Manual drop folder

Three states publish the data we want but put it behind bot-management or a CAPTCHA:

| State | Why it cannot be automated |
|---|---|
| Georgia | reCAPTCHA Enterprise on the file download |
| Minnesota | Radware bot-manager on the absentee data page |
| Ohio | Cloudflare plus a dashboard app, no file endpoint |

Defeating those controls is not something this repo does. So the file is fetched by hand
and parsed here instead. Drop downloads in this folder using the names below; the importer
picks up whatever is present and ignores the rest.

    data/manual/GA-<YYYY-MM-DD>.csv      Georgia absentee file (statewide)
    data/manual/MN-<YYYY-MM-DD>.html     Minnesota absentee data page, saved from the browser
    data/manual/OH-<YYYY-MM-DD>.xlsx     Ohio absentee export

The date in the filename is the date the STATE reports the data for, not the day you
downloaded it. If you are unsure, use the date shown on the page — same rule the automated
collectors follow, so a re-download of the same day replaces rather than duplicates.
