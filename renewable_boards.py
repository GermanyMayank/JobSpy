"""Public recent-job Atom feeds, enriched with the publisher's JobPosting data."""
import json
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from careers import location_matches
from matching import contains, role_terms, normalize

BOARDS = {name: f'https://www.{name}.de' for name in ('eejobs', 'greenjobs')}
ATOM = '{http://www.w3.org/2005/Atom}'


def energy_related(row):
    text = normalize(row['title'] + ' ' + row['description'])
    return bool(re.search(r'\b(solar\w*|photovolta\w*|windenergie\w*|windkraft\w*|windpark\w*|energiewende\w*|erneuerbar\w*|renewable\w*|batteriespeicher\w*|energiespeicher\w*|stromnetz\w*|netzanschluss\w*|bess)\b', text))


def download(url):
    with requests.get(url, timeout=(4, 6), stream=True, allow_redirects=False) as response:
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError('Unexpected redirect or response')
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > 3_000_000:
                raise ValueError('Publisher response too large')
            chunks.append(chunk)
        return b''.join(chunks)


def feed_links(data, board):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('Unsupported XML declarations')
    root = ET.fromstring(data)
    if root.tag != ATOM + 'feed':
        raise ValueError('Unexpected feed format')
    links = []
    for entry in root.findall(ATOM + 'entry'):
        for link in entry.findall(ATOM + 'link'):
            url = link.get('href', '')
            parsed = urlparse(url)
            if link.get('rel', 'alternate') == 'alternate' and parsed.scheme == 'https' and parsed.netloc == urlparse(BOARDS[board]).netloc:
                links.append((entry.findtext(ATOM + 'title', ''), url))
                break
    return list(dict.fromkeys(links))


def parse_job(data, url, board):
    soup = BeautifulSoup(data, 'html.parser')
    candidates = []
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            value = json.loads(script.string or script.get_text())
            candidates.extend(value if isinstance(value, list) else [value])
        except (ValueError, TypeError):
            continue
    for value in list(candidates):
        if isinstance(value, dict):
            candidates.extend(value.get('@graph', []))
    job = next((x for x in candidates if isinstance(x, dict) and x.get('@type') == 'JobPosting'), None)
    if not job or not job.get('title'):
        raise ValueError('Missing structured job posting')
    locations = job.get('jobLocation', [])
    locations = locations if isinstance(locations, list) else [locations]
    places = []
    for place in locations:
        address = place.get('address', {})
        country = address.get('addressCountry', '')
        if isinstance(country, dict):
            country = country.get('name', '')
        places.append(', '.join(str(x) for x in (address.get('addressLocality'), 'Germany' if country == 'DE' else country) if x))
    return dict(title=job['title'], company=job.get('hiringOrganization', {}).get('name', ''),
                location='; '.join(places), date_posted=job.get('datePosted'),
                valid_through=job.get('validThrough'), job_url=url, site=board,
                description=BeautifulSoup(job.get('description', ''), 'html.parser').get_text(' ', strip=True),
                is_remote=job.get('jobLocationType') == 'TELECOMMUTE')


def collect(board, role, location, days, count, remote):
    links = feed_links(download(BOARDS[board] + '/angebote/neueste.html?feed=atom'), board)
    terms = role_terms(role)
    selected = [(title, url) for title, url in links if any(contains(title, term) for term in terms)]
    limit = min(18, max(15, count))
    notes = [f'{board}: recent feed only ({len(links)} entries); not the full archive.']
    if len(selected) > limit:
        notes.append(f'{board}: checked the first {limit} of {len(selected)} related titles.')
    def detail(item):
        try:
            return parse_job(download(item[1]), item[1], board), None
        except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
            return None, str(exc)
    rows, failures = [], 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        for row, error in pool.map(detail, selected[:limit]):
            if error:
                failures += 1
                continue
            if not location_matches(row['location'], location) or (remote and not row['is_remote']):
                continue
            if board == 'greenjobs' and not energy_related(row):
                continue
            try:
                if row['date_posted'] and date.fromisoformat(row['date_posted'][:10]) < date.today() - timedelta(days=days):
                    continue
                if row['valid_through'] and date.fromisoformat(row['valid_through'][:10]) < date.today():
                    continue
            except ValueError:
                row['date_posted'] = None
            rows.append(row)
    if failures:
        if failures == len(selected[:limit]):
            raise ValueError(f'{board}: all {failures} selected job details failed')
        notes.append(f'{board}: {failures} job details failed; these listings were omitted.')
    return rows, notes
