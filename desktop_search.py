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
    from jobspy import scrape_jobs

    OUTPUT.mkdir(exist_ok=True)
    jobs = scrape_jobs(
        site_name=[args.site], search_term=args.role, location=args.location,
        country_indeed="Germany", results_wanted=args.count,
        hours_old=args.days * 24, is_remote=args.remote, verbose=1,
    )
    if not jobs.empty:
        jobs = jobs.drop_duplicates(subset=["job_url"])
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    csv_path = OUTPUT / f"jobs-{stamp}.csv"
    # Protect spreadsheet users from formula-like values in scraped text.
    safe = jobs.map(lambda v: "'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v)
    safe.to_csv(csv_path, index=False, encoding="utf-8-sig")
    rows = json.loads(jobs.to_json(orient="records", date_format="iso"))
    cards = []
    for row in rows:
        esc = lambda key: html.escape(str(row.get(key) or ""))
        url = str(row.get("job_url") or "")
        link = f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">Open job listing</a>' if url.startswith(("https://", "http://")) else ""
        cards.append(f'<article><h2>{esc("title")}</h2><p>{esc("company")} · {esc("location")}</p><p>{esc("site")} · Posted: {esc("date_posted") or "Not supplied"}</p>{link}<details><summary>Description</summary><pre>{esc("description") or "Open the listing for the full description."}</pre></details></article>')
    title = html.escape(f"{args.role} — {args.location}")
    report = OUTPUT / f"jobs-{stamp}.html"
    report.write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>JobSpy results</title><style>body{font:16px system-ui;background:#f2f5fa;color:#15233b;max-width:950px;margin:40px auto;padding:0 20px}article{background:white;border:1px solid #d9e1ed;border-radius:12px;padding:22px;margin:16px 0}h2{font-size:20px}a{color:#1255ad}details{margin-top:18px}pre{white-space:pre-wrap;font:14px system-ui;overflow-wrap:anywhere}</style>' + f'<h1>{title}</h1><p>{len(rows)} listings · {html.escape(args.site)} · Last {args.days} days · Retrieved {datetime.now():%Y-%m-%d %H:%M}</p><p>These are search results, not CV matches. Verify requirements and availability on the listing.</p>' + ("".join(cards) or '<p>No listings returned. Try a broader role or another source. A site may also be temporarily blocking requests; see search.log.</p>') + '</html>', encoding="utf-8")
    result = {"count": len(rows), "report": str(report), "csv": str(csv_path), "role": args.role, "location": args.location}
    (OUTPUT / "latest.json").write_text(json.dumps(result), encoding="utf-8")
    print(json.dumps(result), flush=True)


def desktop():
    import tkinter as tk
    from tkinter import messagebox, ttk

    app = tk.Tk()
    app.title("JobSpy — Germany job search")
    app.geometry("670x490")
    app.minsize(600, 460)
    frame = ttk.Frame(app, padding=24)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Find jobs in Germany", font=("Segoe UI", 20, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
    ttk.Label(frame, text="Free local search · No subscription or API key").grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 20))
    role = tk.StringVar(value="software engineer")
    location = tk.StringVar(value="Berlin, Germany")
    site = tk.StringVar(value="indeed")
    days = tk.StringVar(value="7")
    count = tk.StringVar(value="20")
    remote = tk.BooleanVar(value=False)
    for row, (label, var) in enumerate([("Role or keywords", role), ("City / location", location), ("Source", site), ("Posted within days", days), ("Maximum results", count)], start=2):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=7)
        if var is site:
            widget = ttk.Combobox(frame, textvariable=var, values=["indeed", "linkedin", "glassdoor"], state="readonly")
        else:
            widget = ttk.Entry(frame, textvariable=var)
        widget.grid(row=row, column=1, sticky="ew", padx=(18, 0), pady=7)
    frame.columnconfigure(1, weight=1)
    ttk.Checkbutton(frame, text="Remote jobs only", variable=remote).grid(row=7, column=1, sticky="w", padx=(18, 0))
    status = tk.StringVar(value="Example search shown. Change the role and location to suit you.")
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
            if time.monotonic() - started > 120:
                stop()
                status.set("Source timed out after 2 minutes. Try later or choose another source.")
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
        cmd = [sys.executable, str(Path(__file__).resolve()), "--search", "--role", role.get().strip(), "--location", location.get().strip(), "--site", site.get(), "--days", str(d), "--count", str(n)]
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
        status.set(f"Searching {site.get()}… This can take up to 2 minutes.")
        app.after(300, poll)

    actions = ttk.Frame(frame)
    actions.grid(row=8, column=0, columnspan=2, sticky="w", pady=20)
    button = ttk.Button(actions, text="Search jobs", command=run)
    button.pack(side="left")
    cancel = ttk.Button(actions, text="Cancel", command=stop, state="disabled")
    cancel.pack(side="left", padx=8)
    results = ttk.Button(actions, text="Open last results", command=open_results, state="normal" if latest else "disabled")
    results.pack(side="left")
    ttk.Label(frame, textvariable=status, wraplength=590).grid(row=9, column=0, columnspan=2, sticky="w")
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
    args = parser.parse_args()
    search(args) if args.search else desktop()
