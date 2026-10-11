# Local Germany job search

Double-click **Start Job Search.cmd** on Windows. Enter a role and a German
city, then click **Search jobs**. Results open in your browser; HTML and CSV
copies are saved in `output/`. The **Open last results** button reopens the
previous report. The example software-engineer search is not a personal job
recommendation.

Requires Python 3.10+ with tkinter and internet access. The launcher installs
JobSpy into an isolated `.venv` on first run. It runs on your PC, with no paid
API, subscription, proxy or AI service. Searches go to the selected job board.
Closing the window cancels an active search. A search times out after two minutes.

Indeed is the initial source. LinkedIn and Glassdoor are optional sources and
may rate-limit or block requests. Zero results can mean either no matches or a
source problem: inspect `output/search.log` and try a broader search or another
source. Descriptions are not fetched separately for LinkedIn; open the listing
for full details. Dates and remote flags come from the job boards, and results
are not automatically matched against a CV. No applications are sent.

The source library is [speedyapply/JobSpy](https://github.com/speedyapply/JobSpy),
under its included MIT license. Generated reports, local environments and logs
are excluded from Git.
