"""Free local desktop launcher for JobSpy. No accounts or paid APIs required."""
import argparse
import html
import json
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"


def search(args):
    import pandas as pd
    from jobspy import scrape_jobs
    from smart_search import expand_queries, rank_jobs

    OUTPUT.mkdir(exist_ok=True)
    queries = args.queries.split(";") if args.queries else expand_queries(args.role, args.industry)
    queries = list(dict.fromkeys(q.strip() for q in queries if q.strip()))[:4]
    frames, warnings = [], []
    for query in queries:
        print(f"Searching {args.site}: {query}", flush=True)
        try:
            frame = scrape_jobs(
                site_name=[args.site], search_term=query, location=args.location,
                country_indeed="Germany", results_wanted=max(20, min(50, args.count)),
                hours_old=args.days * 24, is_remote=args.remote, verbose=1,
                fetch_description=args.site == "linkedin",
            )
            frames.append(frame)
            if frame.empty:
                warnings.append(f'No listings returned for "{query}"; there may be no matches or the source may be blocking requests.')
        except Exception as exc:
            warnings.append(f'Search "{query}" failed: {type(exc).__name__}. See search.log.')
            print(repr(exc), flush=True)
    if not frames:
        raise RuntimeError("Every source search failed. Try later or another source.")
    jobs = pd.concat(frames, ignore_index=True)
    if not jobs.empty:
        jobs = jobs.drop_duplicates(subset=["job_url"])
    candidate_count = len(jobs)
    rows = json.loads(jobs.to_json(orient="records", date_format="iso"))
    print(f"Ranking {candidate_count} unique listings locally…", flush=True)
    rows, rejected = rank_jobs(rows, args.role, args.industry, args.seniority, args.hide_mismatch)
    rows = rows[:args.count]
    jobs = pd.DataFrame(rows)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    csv_path = OUTPUT / f"jobs-{stamp}.csv"
    # Protect spreadsheet users from formula-like values in scraped text.
    safe = jobs.map(lambda v: "'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v)
    safe.to_csv(csv_path, index=False, encoding="utf-8-sig")
    cards = []
    for row in rows:
        esc = lambda key: html.escape(str(row.get(key) or ""))
        url = str(row.get("job_url") or "")
        link = f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">Open job listing</a>' if url.startswith(("https://", "http://")) else ""
        cards.append(f'<article><h2>{len(cards)+1}. {esc("title")}</h2><p>{esc("company")} · {esc("location")}</p><p>{esc("site")} · Posted: {esc("date_posted") or "Not supplied"}</p><p><strong>{esc("seniority_check")}</strong><br>{esc("fit_note")}</p><p>Relevant excerpt from the listing:</p><blockquote>{esc("evidence")}</blockquote>{link}<details><summary>Full description</summary><pre>{esc("description") or "Open the listing for the full description."}</pre></details></article>')
    title = html.escape(f"{args.role} — {args.location}")
    report = OUTPUT / f"jobs-{stamp}.html"
    notes = " ".join(html.escape(w) for w in warnings)
    report.write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Smart job results</title><style>body{font:16px system-ui;background:#f2f5fa;color:#15233b;max-width:950px;margin:40px auto;padding:0 20px}article{background:white;border:1px solid #d9e1ed;border-radius:12px;padding:22px;margin:16px 0}h2{font-size:20px}a{color:#1255ad}details{margin-top:18px}pre{white-space:pre-wrap;font:14px system-ui;overflow-wrap:anywhere}blockquote{border-left:3px solid #1255ad;padding-left:15px;color:#465775}</style>' + f'<h1>{title}</h1><p>{len(rows)} ranked listings from {candidate_count} candidates · {html.escape(args.site)} · Last {args.days} days · Retrieved {datetime.now():%Y-%m-%d %H:%M}</p><p>Industry / skills: {html.escape(args.industry) or "Any"} · Seniority: {html.escape(args.seniority)} · {rejected} clear experience mismatches hidden.</p><p>Searches: {html.escape("; ".join(queries))}</p><p>Ordered by local English/German semantic similarity with seniority adjustments. This is not a hiring probability or proof of eligibility. Missing seniority remains unknown; check each listing.</p><p>{notes}</p>' + ("".join(cards) or '<p>No listings available. Broaden the role, industry or dates, or try another source.</p>') + '</html>', encoding="utf-8")
    result = {"count": len(rows), "candidates": candidate_count, "queries": queries, "warnings": warnings, "report": str(report), "csv": str(csv_path), "role": args.role, "location": args.location}
    (OUTPUT / "latest.json").write_text(json.dumps(result), encoding="utf-8")
    print(json.dumps(result), flush=True)


def desktop():
    import tkinter as tk
    from tkinter import messagebox, ttk

    app = tk.Tk()
    app.title("JobSpy — Smart Germany job search")
    app.geometry("780x700")
    app.minsize(720, 660)
    frame = ttk.Frame(app, padding=24)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Find jobs that fit", font=("Segoe UI", 20, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
    ttk.Label(frame, text="Related titles · English/German matching · Ranked by relevance").grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 20))
    role = tk.StringVar(value="Project manager")
    location = tk.StringVar(value="Germany")
    industry = tk.StringVar(value="Solar / photovoltaics")
    seniority = tk.StringVar(value="Junior / entry level")
    queries = tk.StringVar()
    site = tk.StringVar(value="indeed")
    days = tk.StringVar(value="7")
    count = tk.StringVar(value="20")
    remote = tk.BooleanVar(value=False)
    hide_mismatch = tk.BooleanVar(value=True)
    for row, (label, var) in enumerate([("Job position / role", role), ("Industry or key skills", industry), ("Seniority", seniority), ("City / location", location), ("Source", site), ("Posted within days", days), ("Maximum results", count)], start=2):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=7)
        if var is site:
            widget = ttk.Combobox(frame, textvariable=var, values=["indeed", "linkedin", "glassdoor"], state="readonly")
        elif var is seniority:
            widget = ttk.Combobox(frame, textvariable=var, values=["Any", "Junior / entry level", "Mid-level", "Senior"], state="readonly")
        else:
            widget = ttk.Entry(frame, textvariable=var)
        widget.grid(row=row, column=1, sticky="ew", padx=(18, 0), pady=7)
    frame.columnconfigure(1, weight=1)
    def preview(*unused):
        from smart_search import expand_queries
        try:
            queries.set("; ".join(expand_queries(role.get(), industry.get())))
        except ValueError:
            queries.set("")
    role.trace_add("write", preview)
    industry.trace_add("write", preview)
    preview()
    ttk.Label(frame, text="Search titles (editable)").grid(row=9, column=0, sticky="w", pady=10)
    ttk.Entry(frame, textvariable=queries).grid(row=9, column=1, sticky="ew", padx=(18, 0))
    ttk.Label(frame, text="Up to 4 searches, separated by semicolons. Seniority is checked after collection.", wraplength=690).grid(row=10, column=0, columnspan=2, sticky="w")
    ttk.Checkbutton(frame, text="Remote jobs only", variable=remote).grid(row=11, column=1, sticky="w", padx=(18, 0), pady=5)
    ttk.Checkbutton(frame, text="Hide clear experience mismatches", variable=hide_mismatch).grid(row=12, column=1, sticky="w", padx=(18, 0))
    status = tk.StringVar(value="Free local matching. Your role and location are sent to the selected job board.")
    proc = None
    log = None
    started = 0
    latest = None
    OUTPUT.mkdir(exist_ok=True)
    try:
        latest = json.loads((OUTPUT / "latest.json").read_text(encoding="utf-8"))
        status.set(f'Last search: {latest["count"]} listings for {latest["role"]}.')
    except (OSError, ValueError, KeyError):
        pass

    def open_results():
        if latest:
            webbrowser.open(Path(latest["report"]).as_uri())

    def finish():
        nonlocal log, proc
        if log:
            log.close()
            log = None
        proc = None
        button.configure(state="normal")
        cancel.configure(state="disabled")

    def stop():
        if proc:
            proc.kill()
            proc.wait(timeout=5)
            finish()
            status.set("Search stopped. Previous results are still available.")

    def poll():
        nonlocal latest
        if not proc:
            return
        if proc.poll() is None:
            if time.monotonic() - started > 300:
                stop()
                status.set("Search timed out after 5 minutes. Try fewer titles or another source.")
            else:
                app.after(300, poll)
            return
        code = proc.returncode
        finish()
        if code:
            status.set("Search failed. Try another source; details are in output/search.log.")
            return
        try:
            latest = json.loads((OUTPUT / "latest.json").read_text(encoding="utf-8"))
            status.set(f'{latest["count"]} listings found. HTML and CSV saved in the output folder.')
            results.configure(state="normal")
            open_results()
        except (OSError, ValueError, KeyError):
            status.set("Could not read the result file. Check output/search.log.")

    def run():
        nonlocal proc, log, started
        try:
            d, n = int(days.get()), int(count.get())
            if not 1 <= d <= 100 or not 1 <= n <= 100 or not role.get().strip() or not location.get().strip():
                raise ValueError()
        except ValueError:
            messagebox.showerror("Check search", "Enter a role and location, and whole numbers from 1 to 100 for days and results.")
            return
        cmd = [sys.executable, str(Path(__file__).resolve()), "--search", "--role", role.get().strip(), "--industry", industry.get().strip(), "--seniority", seniority.get(), "--queries", queries.get(), "--location", location.get().strip(), "--site", site.get(), "--days", str(d), "--count", str(n)]
        if hide_mismatch.get():
            cmd.append("--hide-mismatch")
        if remote.get():
            cmd.append("--remote")
        log = (OUTPUT / "search.log").open("w", encoding="utf-8")
        try:
            proc = subprocess.Popen(cmd, stdout=log, stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as exc:
            finish()
            messagebox.showerror("Could not start search", str(exc))
            return
        started = time.monotonic()
        button.configure(state="disabled")
        cancel.configure(state="normal")
        status.set(f"Searching related titles on {site.get()}, then ranking locally… Allow up to 5 minutes.")
        app.after(300, poll)

    actions = ttk.Frame(frame)
    actions.grid(row=13, column=0, columnspan=2, sticky="w", pady=20)
    button = ttk.Button(actions, text="Search jobs", command=run)
    button.pack(side="left")
    cancel = ttk.Button(actions, text="Cancel", command=stop, state="disabled")
    cancel.pack(side="left", padx=8)
    results = ttk.Button(actions, text="Open last results", command=open_results, state="normal" if latest else "disabled")
    results.pack(side="left")
    ttk.Label(frame, textvariable=status, wraplength=690).grid(row=14, column=0, columnspan=2, sticky="w")
    def close():
        stop()
        app.destroy()
    app.protocol("WM_DELETE_WINDOW", close)
    app.mainloop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--search", action="store_true")
    parser.add_argument("--role", default="software engineer")
    parser.add_argument("--location", default="Berlin, Germany")
    parser.add_argument("--site", choices=["indeed", "linkedin", "glassdoor"], default="indeed")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--remote", action="store_true")
    parser.add_argument("--industry", default="")
    parser.add_argument("--seniority", choices=["Any", "Junior / entry level", "Mid-level", "Senior"], default="Any")
    parser.add_argument("--queries", default="")
    parser.add_argument("--hide-mismatch", action="store_true")
    args = parser.parse_args()
    search(args) if args.search else desktop()
