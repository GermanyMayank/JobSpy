"""Bounded source collection; source failures do not discard other results."""
import base64
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote


def arbeitsagentur(query, location, days, count, remote):
    import requests
    base = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
    session = requests.Session()
    session.headers["X-API-Key"] = "jobboerse-jobsuche"
    params = dict(was=query, size=count, page=1, veroeffentlichtseit=days, angebotsart=1)
    if location.strip().casefold() not in ("germany", "deutschland", "de"):
        params.update(wo=location, umkreis=50)
    response = session.get(base + "/pc/v6/jobs", params=params, timeout=12)
    response.raise_for_status()
    payload = response.json()
    if payload.get("maxErgebnisse") == 0:
        return [], []
    if "ergebnisliste" not in payload:
        raise ValueError("Arbeitsagentur returned an unexpected response")
    rows, warnings = [], []
    for job in payload["ergebnisliste"]:
        ref = job.get("referenznummer")
        if not ref:
            continue
        places = [x.get("adresse", {}).get("ort", "") for x in job.get("stellenlokationen", [])]
        rows.append(dict(title=job.get("stellenangebotsTitel"), company=job.get("firma"),
                         location=", ".join(sorted(set(filter(None, places)))),
                         date_posted=job.get("datumErsteVeroeffentlichung"),
                         job_url="https://www.arbeitsagentur.de/jobsuche/jobdetail/" + quote(ref, safe=""),
                         job_url_direct=job.get("externeURL"), site="arbeitsagentur", description="",
                         is_remote=None, workplace_note="Home office possible (may be hybrid)" if job.get("homeofficemoeglich") else "Remote status not verified",
                         reference=ref))
    def detail(row):
        try:
            encoded = quote(base64.b64encode(row["reference"].encode()).decode(), safe="")
            r = requests.get(base + "/pc/v4/jobdetails/" + encoded, headers={"X-API-Key": "jobboerse-jobsuche"}, timeout=5)
            r.raise_for_status()
            data = r.json()
            row["description"] = data.get("stellenangebotsBeschreibung") or data.get("stellenbeschreibung") or ""
            return not bool(row["description"])
        except (requests.RequestException, ValueError):
            return True
    with ThreadPoolExecutor(max_workers=5) as pool:
        missing = sum(pool.map(detail, rows))
    if missing:
        warnings.append(f"{missing} Arbeitsagentur listings have no accessible description; matching uses their titles.")
    return rows, warnings


def worker(options):
    if options["site"] in ("eejobs", "greenjobs"):
        from renewable_boards import collect as board_collect
        return board_collect(options["site"], options["query"], options["location"], options["days"], options["count"], options["remote"])
    if options["site"] == "arbeitsagentur":
        return arbeitsagentur(options["query"], options["location"], options["days"], options["count"], options["remote"])
    from jobspy import scrape_jobs
    frame = scrape_jobs(site_name=[options["site"]], search_term=options["query"],
                        location=options["location"], country_indeed="Germany", distance=31,
                        results_wanted=options["count"], hours_old=options["days"] * 24,
                        is_remote=options["remote"], fetch_description=options["site"] == "linkedin", verbose=1)
    return json.loads(frame.to_json(orient="records", date_format="iso")), []


def collect(queries, sites, location, days, count, remote, role=None):
    tasks = [dict(query=q, site=s, location=location, days=days, count=min(30, max(15, count)), remote=remote) for s in sites for q in ([role or queries[0]] if s in ("eejobs", "greenjobs") else queries)]
    def run(options):
        try:
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve())], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                stdout, stderr = process.communicate(json.dumps(options), timeout=45)
            except subprocess.TimeoutExpired:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    process.kill()
                process.communicate()
                raise
            if process.returncode:
                return [], [], {**options, "status": "failed", "count": 0, "detail": stderr[-500:]}
            rows, notes = json.loads(stdout)
            return rows, notes, {**options, "status": "ok" if rows else "empty or blocked", "count": len(rows)}
        except subprocess.TimeoutExpired:
            return [], [], {**options, "status": "timed out (45s)", "count": 0}
        except (OSError, ValueError) as exc:
            return [], [], {**options, "status": "failed", "count": 0, "detail": str(exc)}
    rows, notes, coverage = [], [], []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for future in as_completed([pool.submit(run, task) for task in tasks]):
            batch, warnings, status = future.result()
            rows.extend(batch)
            notes.extend(warnings)
            coverage.append(status)
            print(f'{status["site"]}: {status["query"]} — {status["status"]}, {status["count"]} listings', flush=True)
    return rows, notes, sorted(coverage, key=lambda r: (r["site"], r["query"]))


if __name__ == "__main__":
    print(json.dumps(worker(json.loads(sys.stdin.read()))))
