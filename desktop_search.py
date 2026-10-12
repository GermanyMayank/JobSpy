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
    from matching import expand_queries, rank_jobs, deduplicate
    from sources import collect

    OUTPUT.mkdir(exist_ok=True)
    queries = args.queries.split(";") if args.queries else expand_queries(args.role, args.industry)
    queries = list(dict.fromkeys(q.strip() for q in queries if q.strip()))[:6]
    sites = ["indeed", "linkedin", "arbeitsagentur"] if args.site == "Combined" else [args.site]
    collected, warnings, coverage = collect(queries, sites, args.location, args.days, args.count, args.remote)
    rows = deduplicate(collected)
    candidate_count = len(rows)
    duplicate_count = len(collected) - len(rows)
    rows, rejected = rank_jobs(rows, args.role, args.industry, args.seniority, args.hide_mismatch, args.days, args.remote)
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
        cards.append(f'<article><h2>{len(cards)+1}. {esc("title")}</h2><p>{esc("company")} · {esc("location")}</p><p>{esc("sources")} · Posted: {esc("date_posted") or "Not supplied"}</p><p><strong>{esc("seniority_check")}</strong><br>{esc("fit_note")}</p><p>Relevant excerpt from the listing:</p><blockquote>{esc("evidence")}</blockquote>{link}<details><summary>Full description</summary><pre>{esc("description") or "Open the listing for the full description."}</pre></details></article>')
    title = html.escape(f"{args.role} — {args.location}")
    report = OUTPUT / f"jobs-{stamp}.html"
    coverage_html = '<h2>Source coverage</h2><ul>' + ''.join(f'<li>{html.escape(c["site"])} — {html.escape(c["query"])}: {html.escape(c["status"])} ({c["count"]})</li>' for c in coverage) + '</ul>'
    notes = " ".join(html.escape(w) for w in dict.fromkeys(warnings))

    report.write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Germany job results</title><style>body{font:16px system-ui;background:#f2f5fa;color:#15233b;max-width:950px;margin:40px auto;padding:0 20px}article{background:white;border:1px solid #d9e1ed;border-radius:12px;padding:22px;margin:16px 0}h2{font-size:20px}a{color:#1255ad}details{margin-top:18px}pre{white-space:pre-wrap;font:14px system-ui;overflow-wrap:anywhere}blockquote{border-left:3px solid #1255ad;padding-left:15px;color:#465775}</style>' + f'<h1>{title}</h1><p>{len(rows)} ranked listings from {candidate_count} candidates · {html.escape(args.site)} · Last {args.days} days · Retrieved {datetime.now():%Y-%m-%d %H:%M}</p><p>Industry / skills: {html.escape(args.industry) or "Any"} · Seniority: {html.escape(args.seniority)} · {rejected} listings excluded by date, remote or experience checks.</p><p>Searches: {html.escape("; ".join(queries))}</p><p>Ordered by transparent title, industry and experience checks, then newest first. No AI. Unknown dates or seniority are labelled for review. Location filtering is supplied by each source (approximately 50 km around a city).</p><p>{notes}</p>' + ("".join(cards) or '<p>No listings available. Broaden the role, industry or dates, or try another source.</p>') + coverage_html + f'<p>{duplicate_count} duplicate listings consolidated. Sources can fail or return incomplete results; this is not exhaustive coverage.</p></html>', encoding="utf-8")
    result = {"count": len(rows), "candidates": candidate_count, "queries": queries, "warnings": warnings, "coverage": coverage, "duplicates": duplicate_count, "report": str(report), "csv": str(csv_path), "role": args.role, "location": args.location}
    (OUTPUT / "latest.json").write_text(json.dumps(result), encoding="utf-8")
    print(json.dumps(result), flush=True)


def desktop():
    import tkinter as tk
    from tkinter import messagebox, ttk

    app = tk.Tk()
    app.title("JobSpy — Germany job search")
    app.geometry("780x700")
    app.minsize(720, 660)
    frame = ttk.Frame(app, padding=24)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Find jobs that fit", font=("Segoe UI", 20, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
    ttk.Label(frame, text="Multiple sources · English/German titles · Clear matching reasons").grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 20))
    role = tk.StringVar(value="Project manager")
    location = tk.StringVar(value="Germany")
    industry = tk.StringVar(value="Solar / photovoltaics")
    seniority = tk.StringVar(value="Junior / entry level")
    queries = tk.StringVar()
    site = tk.StringVar(value="Combined")
    days = tk.StringVar(value="7")
    count = tk.StringVar(value="20")
    remote = tk.BooleanVar(value=False)
    hide_mismatch = tk.BooleanVar(value=True)
    for row, (label, var) in enumerate([("Job position / role", role), ("Industry or key skills", industry), ("Seniority", seniority), ("City / location", location), ("Source", site), ("Posted within days", days), ("Maximum results", count)], start=2):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=7)
        if var is site:
            widget = ttk.Combobox(frame, textvariable=var, values=["Combined", "indeed", "linkedin", "arbeitsagentur", "glassdoor"], state="readonly")
        elif var is seniority:
            widget = ttk.Combobox(frame, textvariable=var, values=["Any", "Junior / entry level", "Mid-level", "Senior"], state="readonly")
        else:
            widget = ttk.Entry(frame, textvariable=var)
        widget.grid(row=row, column=1, sticky="ew", padx=(18, 0), pady=7)
    frame.columnconfigure(1, weight=1)
    def preview(*unused):
        from matching import expand_queries
        try:
            queries.set("; ".join(expand_queries(role.get(), industry.get())))
        except ValueError:
            queries.set("")
    role.trace_add("write", preview)
    industry.trace_add("write", preview)
    preview()
    ttk.Label(frame, text="Search titles (editable)").grid(row=9, column=0, sticky="w", pady=10)
    ttk.Entry(frame, textvariable=queries).grid(row=9, column=1, sticky="ew", padx=(18, 0))
    ttk.Label(frame, text="Up to 6 searches, separated by semicolons. Seniority is checked after collection.", wraplength=690).grid(row=10, column=0, columnspan=2, sticky="w")
    ttk.Checkbutton(frame, text="Remote flag required (excludes unknown/hybrid Arbeitsagentur jobs)", variable=remote).grid(row=11, column=1, sticky="w", padx=(18, 0), pady=5)
    ttk.Checkbutton(frame, text="Hide detected experience mismatches", variable=hide_mismatch).grid(row=12, column=1, sticky="w", padx=(18, 0))
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
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                proc.kill()
            proc.wait(timeout=5)
            finish()
            status.set("Search stopped. Previous results are still available.")

    def poll():
        nonlocal latest
        if not proc:
            return
        if proc.poll() is None:
            if time.monotonic() - started > 360:
                stop()
                status.set("Search timed out after 6 minutes. Try fewer titles or another source.")
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
        status.set(f"Searching related titles on {site.get()}, then ranking locally… Allow up to 6 minutes.")
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
    parser.add_argument("--site", choices=["Combined", "indeed", "linkedin", "arbeitsagentur", "glassdoor"], default="Combined")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--remote", action="store_true")
    parser.add_argument("--industry", default="")
    parser.add_argument("--seniority", choices=["Any", "Junior / entry level", "Mid-level", "Senior"], default="Any")
    parser.add_argument("--queries", default="")
    parser.add_argument("--hide-mismatch", action="store_true")
    args = parser.parse_args()
    search(args) if args.search else desktop()
