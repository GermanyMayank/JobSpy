"""Public Personio career feeds, with transactional local snapshots.

Only complete, validated snapshots can change availability. No paid service.
"""
import concurrent.futures
import html
import json
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'output'
INTERVAL = 6 * 3600
COMPANIES = [
    ('MaxSolar', 'maxsolar'), ('WIRSOL Roof Solutions', 'wrs'),
    ('Kronos Solar', 'kronos-solar'), ('heimWatt', 'heim-watt'),
    ('1KOMMA5°', '1komma5grad'), ('Trina Solar', 'trina-solar-1'),
    ('hep solar', 'hep-global-gmbh'), ('Sungrow Europe', 'sungrow-emea'),
    ('einhundert Energie', 'einhundert-energie-gmbh'),
    ('Solar Materials', 'solar-materials-gmbh'),
]


def connect(path=None):
    OUTPUT.mkdir(exist_ok=True)
    db = sqlite3.connect(path or OUTPUT / 'careers.sqlite3', timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript('''
      CREATE TABLE IF NOT EXISTS companies (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, attempted REAL,
        success REAL, status TEXT, error TEXT, count INTEGER);
      CREATE TABLE IF NOT EXISTS jobs (
        company TEXT, id TEXT, payload TEXT NOT NULL, first_seen REAL,
        last_seen REAL, missing_since REAL, misses INTEGER DEFAULT 0,
        PRIMARY KEY(company,id));
    ''')
    with db:
        db.executemany('INSERT OR IGNORE INTO companies(id,name) VALUES (?,?)',
                       [(slug, name) for name, slug in COMPANIES])
    return db


def company_id(url):
    p = urlsplit(url.strip())
    if p.scheme != 'https' or p.port or p.username or not re.fullmatch(
            r'[a-z0-9-]+\.jobs\.personio\.de', p.hostname or ''):
        raise ValueError('Use a public https://company.jobs.personio.de career-page URL. Other providers are not supported yet.')
    return p.hostname.split('.')[0]


def parse_feed(data, slug, name):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('Unexpected XML declarations')
    root = ET.fromstring(data)
    if root.tag != 'workzag-jobs' or any(p.tag != 'position' for p in root):
        raise ValueError('Unexpected feed format; previous jobs preserved')
    rows, ids = [], set()
    for p in root:
        jid, title = p.findtext('id', '').strip(), p.findtext('name', '').strip()
        if not jid.isdigit() or not title or jid in ids:
            raise ValueError('Incomplete or duplicate job records; previous jobs preserved')
        ids.add(jid)
        description = '\n'.join((x.findtext('name', '') + '\n' + x.findtext('value', ''))
                                for x in p.findall('jobDescriptions/jobDescription'))
        description = BeautifulSoup(html.unescape(description), 'html.parser').get_text(' ', strip=True)
        locations = [p.findtext('office', '')] + [x.text or '' for x in p.findall('additionalOffices/office')]
        rows.append(dict(id=jid, site='Company careers', title=title, company=name,
                         location=' | '.join(dict.fromkeys(filter(None, locations))),
                         description=description, date_posted=None, is_remote=None,
                         source_created_at=p.findtext('createdAt'),
                         job_url=f'https://{slug}.jobs.personio.de/job/{jid}'))
    return rows


def _fetch(slug, name):
    company_id(f'https://{slug}.jobs.personio.de')
    deadline = time.monotonic() + 40
    with requests.get(f'https://{slug}.jobs.personio.de/xml', timeout=(15, 15),
                      stream=True, allow_redirects=False,
                      headers={'User-Agent': 'JobSpy-local-career-reader/1.0'}) as response:
        if response.status_code != 200:
            raise ValueError(f'Feed returned HTTP {response.status_code}; XML may be disabled')
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > 15_000_000 or time.monotonic() > deadline:
                raise ValueError('Feed exceeded size/time limit')
            chunks.append(chunk)
    return parse_feed(b''.join(chunks), slug, name)


def fetch(slug, name):
    for attempt in range(2):
        try:
            return _fetch(slug, name)
        except (requests.Timeout, requests.ConnectionError):
            if attempt:
                raise
            time.sleep(1)


def snapshot(db, slug, rows, now=None, error=None):
    now = time.time() if now is None else now
    with db:
        if error is not None:
            db.execute('UPDATE companies SET attempted=?,status=?,error=? WHERE id=?',
                       (now, 'failed', str(error)[:400], slug))
            return
        previous = db.execute('SELECT success FROM companies WHERE id=?', (slug,)).fetchone()[0]
        seen = {r['id'] for r in rows}
        if len(seen) != len(rows):
            raise ValueError('Duplicate IDs')
        old = db.execute('SELECT * FROM jobs WHERE company=?', (slug,)).fetchall()
        missing = [r for r in old if r['id'] not in seen]
        for row in rows:
            db.execute('''INSERT INTO jobs(company,id,payload,first_seen,last_seen) VALUES (?,?,?,?,?)
              ON CONFLICT(company,id) DO UPDATE SET payload=excluded.payload,last_seen=excluded.last_seen,
              missing_since=NULL,misses=0''', (slug, row['id'], json.dumps(row), now, now))
        for row in missing:
            if row['missing_since'] is None:
                db.execute('UPDATE jobs SET missing_since=?,misses=1 WHERE company=? AND id=?', (now, slug, row['id']))
            elif now - row['missing_since'] >= INTERVAL and (previous is None or now - previous >= INTERVAL):
                db.execute('UPDATE jobs SET misses=misses+1 WHERE company=? AND id=?', (slug, row['id']))
        warning = f'{len(missing)} saved jobs absent; availability needs review' if missing else ''
        db.execute('UPDATE companies SET attempted=?,success=?,status=?,error=?,count=? WHERE id=?',
                   (now, now, 'checked', warning, len(rows), slug))


def refresh(force=False):
    db = connect()
    companies = [dict(r) for r in db.execute('SELECT * FROM companies')]
    due = [c for c in companies if force or not c['attempted'] or
           time.time()-c['attempted'] >= (300 if c['status'] == 'failed' else INTERVAL)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(fetch, c['id'], c['name']): c for c in due}
        for future in concurrent.futures.as_completed(futures):
            c = futures[future]
            try:
                rows = future.result()
                snapshot(db, c['id'], rows)
                print(f"{c['name']}: {len(rows)} jobs", flush=True)
            except Exception as exc:
                snapshot(db, c['id'], [], error=str(exc))
                print(f"{c['name']}: failed, saved jobs retained: {exc}", flush=True)
    db.close()
    return status_report()


# Conservative country evidence: unknown offices are withheld, never guessed from employer nationality.
GERMAN_PLACES = ('germany deutschland deutschlandweit bundesweit berlin hamburg munchen munich '
                 'koln cologne frankfurt leipzig dresden stuttgart dusseldorf dortmund essen bremen '
                 'hannover nurnberg nuremberg bonn augsburg magdeburg karlsruhe mannheim freiburg '
                 'potsdam kiel mainz wiesbaden regensburg traunstein salzhausen '
                 'waghausel sprakebull balingen bayern bayreuth bielefeld braunschweig '
                 'gottingen niedersachsen breidenbach bremerhaven chemnitz freiberg deggendorf '
                 'emmendingen euskirchen gustrow heidelberg hildesheim homburg kaiserslautern '
                 'kassel kempten konstanz luneburg seevetal merzig mohnesee munster '
                 'neukirchen-vluyn moers neumunster oldenburg osnabruck ostdeutschland '
                 'paderborn pforzheim nagold rostock neubrandenburg stralsund remscheid '
                 'riederich rosenheim saarbrucken saarlouis sigmaringen singen tangstedt '
                 'ulm weimar wurzburg').split()


def location_matches(location, requested):
    from matching import normalize, contains
    target = normalize(requested.split(',')[0])
    if target in ('germany', 'deutschland', 'de'):
        return any(contains(location, t) for t in GERMAN_PLACES)
    aliases = {'munich': 'munchen', 'cologne': 'koln', 'nuremberg': 'nurnberg'}
    terms = {target, aliases.get(target, target)}
    terms.update(k for k, v in aliases.items() if v == target)
    return any(contains(location, term) for term in terms)


def cached_jobs(role, location):
    from matching import role_terms, contains
    db = connect()
    rows, withheld = [], 0
    for item in db.execute('SELECT j.*,c.success,c.status FROM jobs j JOIN companies c ON c.id=j.company WHERE misses<2'):
        row = json.loads(item['payload'])
        if not location_matches(row['location'], location):
            withheld += 1
            continue
        if not any(contains(row['title'], t) for t in role_terms(role)):
            continue
        stamp = lambda t: time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(t))
        state = 'Not seen on last scan' if item['misses'] else 'Stale: refresh needed' if item['status'] == 'failed' or time.time()-item['success'] > INTERVAL else 'Present in last successful feed'
        row['career_status'] = f"{state}; first seen {stamp(item['first_seen'])}; last seen {stamp(item['last_seen'])}"
        rows.append(row)
    total = db.execute('SELECT count(*) FROM jobs').fetchone()[0]
    db.close()
    notes = [f'Company careers: {withheld} jobs withheld because the requested location was not confirmed. City matching uses names, not a radius. Career posting dates and fully remote eligibility are unknown unless supplied.']
    if not total:
        notes.append('Click Refresh companies to load the career-page database.')
    return rows, notes, [dict(site='Company careers', query=role, status='cached; use Company status for freshness', count=len(rows))]


def status_report():
    db = connect()
    parts = []
    for c in db.execute('SELECT * FROM companies ORDER BY name'):
        success = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(c['success'])) if c['success'] else 'Never'
        parts.append('<tr>' + ''.join(f'<td>{html.escape(str(v))}</td>' for v in
                     (c['name'], c['status'] or 'Not checked', c['count'] if c['count'] is not None else '—', success, c['error'] or '')) + '</tr>')
    db.close()
    path = OUTPUT / 'company-status.html'
    path.write_text('<!doctype html><meta charset="utf-8"><title>Company career coverage</title><style>body{font:16px system-ui;margin:35px}td,th{padding:12px;text-align:left;border-bottom:1px solid #ccc}table{border-collapse:collapse}</style><h1>Company career coverage</h1><p>Public Personio feeds. Successful feeds have a 6-hour refresh cooldown; failed feeds can be retried after 5 minutes. Counts include all countries and roles. Failed scans preserve saved jobs. Jobs absent in two successful scans at least 6 hours apart are hidden, not deleted. Refresh runs only when requested while this app is open.</p><table><tr><th>Company</th><th>Status</th><th>Feed jobs</th><th>Last success</th><th>Notes</th></tr>' + ''.join(parts) + '</table>', encoding='utf-8')
    return path


if __name__ == '__main__':
    import argparse
    import sys
    sys.stdout.reconfigure(errors='replace')
    parser = argparse.ArgumentParser()
    parser.add_argument('--add-url')
    parser.add_argument('--name')
    parser.add_argument('--force', action='store_true', help='Bypass refresh cooldown; does not bypass missing-job protection')
    args = parser.parse_args()
    if args.add_url:
        slug = company_id(args.add_url)
        name = (args.name or slug).strip()
        rows = fetch(slug, name)
        db = connect()
        with db:
            db.execute('INSERT OR IGNORE INTO companies(id,name) VALUES (?,?)', (slug, name))
        snapshot(db, slug, rows)
        db.close()
        status_report()
    else:
        refresh(force=args.force)
