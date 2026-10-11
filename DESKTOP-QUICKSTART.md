# Smart Germany job search

Double-click **Start Job Search.cmd**, fill in the role, industry or skills,
seniority, location and posting age, then click **Search jobs**. The editable
search-title preview shows the queries sent to the selected board.

For example, **Project manager / Solar / Junior** searches project management,
project coordination and German photovoltaic titles. Seniority is assessed
after collection so jobs that omit junior are not automatically lost.
Common role families use an English/German title catalogue. Unknown roles
keep their original title; add alternatives separated by semicolons if useful.

A free multilingual Sentence Transformers model runs on your CPU and ranks
job titles and description excerpts by meaning, with seniority adjustments.
It is not a chatbot, an unrestricted natural-language parser or LinkedIn's AI.
Seniority checks use explicit title cues and stated minimum years; missing
information stays unknown. Hide clear experience mismatches excludes detected
conflicts, not all unsuitable jobs. Mid-level checks junior and explicit
leadership titles, but cannot infer exact experience requirements.

Each result shows a relevant excerpt and experience check. Verify language,
location, eligibility and availability on the listing. No CV is needed and no
application is sent. Broader renewable-energy queries can return jobs outside
solar; semantic ranking is not a strict industry filter.

HTML reports, CSV exports and logs stay in output/. Open last results reopens
the latest report. Queries go to the selected board; ranking happens locally.
Results, logs, local environments and model downloads are excluded from Git.

## Setup

Windows needs Python 3.10+ with tkinter and internet access. The launcher sets
up an isolated .venv, installs dependencies and downloads the model once.
Allow several minutes and roughly 1-2 GB disk space including dependencies.
There is no paid API, subscription, proxy or AI service. Models stay in .models/.

Sources can block or rate-limit requests. Empty responses do not prove there
are no jobs. Empty and failed subsearches appear as warnings. A GUI search
stops after five minutes; try fewer titles or another source if it times out.
Cancel or closing the app stops the search. Posting dates and remote flags
come from job boards. Up to four queries and 50 candidates per query are
collected; duplicate URLs are removed. Long descriptions use representative
chunks. This is not an exhaustive search or a hiring probability score.

Upstream: https://github.com/speedyapply/JobSpy (MIT).
Model: https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
Tests: .venv\Scripts\python.exe -m unittest test_smart_search -v
