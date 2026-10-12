# Germany job search — no AI

Double-click **Start Job Search.cmd**. Choose role, industry/skills, seniority,
location and posting age. Combined searches Indeed, LinkedIn and Arbeitsagentur;
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
Location is filtered by the source, with approximately 50 km around a city;
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

Tests: .venv\Scripts\python.exe -m unittest test_matching -v
Upstream JobSpy: https://github.com/speedyapply/JobSpy (MIT).
Arbeitsagentur interface reference: https://github.com/bundesAPI/jobsuche-api
This is an unofficially documented interface and may change.
