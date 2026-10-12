# Germany job search — no AI

Double-click **Start Job Search.cmd**. Choose role, industry/skills, seniority,
location and posting age. Combined searches Indeed, LinkedIn and Arbeitsagentur,
and includes saved company-career jobs;
you can also select one source (including optional Glassdoor).

Related English/German titles are expanded from a visible, editable catalogue.
Project management includes Projektmanager, Projektleiter, Projektkoordinator,
Projektassistenz and project coordinator. Solar expands to solar/Photovoltaik;
it does not silently broaden into unrelated renewable sectors. For unrecognised
roles, add title alternatives separated by semicolons (maximum six).

Matching is deterministic: a related title gets 50 points, or a role mentioned
only in the description gets 20. An industry/skill term adds 30; explicit junior
or senior title agreement adds 15. Detected experience conflicts subtract 40,
or are hidden when that option is selected. Newest listings break ties. Scores
are sorting rules, not probabilities; the report shows supporting terms/excerpts.

Known old listings are excluded. Unknown dates and seniority remain visible and
labelled. Seniority rules recognise explicit titles and minimum-years phrases,
not every wording of a requirement. Industry/skills are preferences, not mandatory
filters. Remote-only requires the source's remote flag; it excludes unknown BA
remote statuses because home-office-possible may mean hybrid. Check each advert.
For job boards, location is filtered by the source, with approximately 50 km around a city;
Germany/Deutschland searches nationwide. No language or visa eligibility is inferred.

Matching URLs (ignoring tracking parameters), or identical normalised title,
company AND location, are consolidated. Different locations remain separate.
Missing identity fields are never sufficient to merge. Sources are retained and
alternative listing URLs are included in CSV. Similar but differently worded
cross-board duplicates may remain.

The coverage section lists every source/query outcome, including empty, failed
and timed-out requests. Empty means no returned records, not guaranteed absence
of vacancies. Source work has a 45-second limit per query, with three concurrent
workers; the GUI allows six minutes overall. Up to 30 candidates per query/source
are collected. A failed source does not discard other results. Cancel stops the
search process tree on Windows. Source descriptions may be unavailable.

HTML/CSV reports and logs stay in output/ and are excluded from Git. No paid
services, model downloads, AI inference, CV upload or automatic applications.
Python 3.10+ with tkinter and internet access is required; setup creates .venv.

## Direct company careers

Click **Refresh companies**, then search with **Company careers** or **Combined**.
**Company status** shows each feed's count, last successful check and problems.
**Add company** accepts a public `https://company.jobs.personio.de` careers URL
and a display name. The feed must pass validation before it is saved. This first
version supports Personio only; Greenhouse, Lever and custom sites are not yet supported.

Ten initial feeds were checked on 2026-10-12: MaxSolar, WIRSOL Roof Solutions,
Kronos Solar, heimWatt, 1KOMMA5°, Trina Solar, hep solar, Sungrow Europe,
einhundert Energie and Solar Materials. Live verification returned 526 jobs
across all countries and roles; one job link per company returned HTTP 200 and
contained the expected title. This count is a dated observation, not a guarantee.

Company jobs are stored in `output/careers.sqlite3`. Stable company/job IDs prevent
duplicates. Refresh commits each validated feed independently. Failed, malformed,
oversized or timed-out feeds preserve previous jobs and are labelled failed. Network
timeouts get one retry. Successful feeds have a six-hour cooldown; failures can be
retried after five minutes. There is no background schedule: use Refresh companies.
Search reads the saved database, so company results remain available offline.

Missing jobs remain labelled after the first successful scan that omits them.
After two successful scans at least six hours apart they are hidden, never deleted.
Reappearing jobs are restored with the original first-seen time. A valid but incorrect
empty feed can still eventually hide jobs, so inspect the company-status warnings.
First-seen and last-seen times are separate from posting dates: Personio's creation
date is not treated as a verified publication date. Unknown dates stay visible even
with a posting-age filter, with an explicit warning. Remote eligibility is unknown,
so these jobs are excluded when the remote-required option is selected.

Career candidates require a related role in their title. Germany filtering requires
an explicit Germany label or a recognised German place name in the feed's location.
Unknown/foreign locations are withheld and counted in coverage notes. City searches
use city names and a few bilingual aliases, without a radius. The place-name catalogue
is deliberately limited and may omit valid German roles. No visa or language
eligibility is inferred. Application links go directly to the employer's ATS page.

Tests: .venv\Scripts\python.exe -m unittest test_matching test_careers -v
Personio feed documentation: https://developer.personio.de/v1.0/reference/get_xml
Upstream JobSpy: https://github.com/speedyapply/JobSpy (MIT).
Arbeitsagentur interface reference: https://github.com/bundesAPI/jobsuche-api
This is an unofficially documented interface and may change.
