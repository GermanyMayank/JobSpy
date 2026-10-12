"""Explainable matching rules. No AI models or inference dependencies."""
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, parse_qsl, urlencode, urlunsplit
FAMILIES = [
    ("project manager", "project coordinator", "Projektmanager", "Projektleiter", "Projektkoordinator", "Projektassistenz", "project assistant"),
    ("product manager", "product owner", "Produktmanager"),
    ("software engineer", "software developer", "Softwareentwickler"),
    ("data analyst", "business intelligence analyst", "Datenanalyst"),
    ("data engineer", "data engineering", "Dateningenieur"),
    ("data scientist", "machine learning engineer", "KI Entwickler"),
    ("electrical engineer", "Elektroingenieur", "Ingenieur Elektrotechnik"),
    ("mechanical engineer", "Maschinenbauingenieur", "Konstrukteur"),
    ("civil engineer", "Bauingenieur", "Bauleiter"),
    ("business analyst", "Prozessanalyst", "Business Analyst"),
    ("sales manager", "account manager", "Vertriebsmanager"),
    ("marketing manager", "online marketing", "Marketingmanager"),
    ("operations manager", "Betriebsleiter", "Operations Specialist"),
    ("supply chain manager", "logistics coordinator", "Logistikmanager"),
    ("quality engineer", "quality assurance", "Qualitätsingenieur"),
    ("research assistant", "research associate", "Wissenschaftlicher Mitarbeiter"),
    ("financial analyst", "finance analyst", "Finanzanalyst"),
    ("HR specialist", "human resources", "Personalreferent"),
]
JUNIOR = r"\b(junior|entry.level|graduate|trainee|berufseinsteiger|nachwuchs)\b"
SENIOR = r"\b(senior|sr\.?|lead|principal|staff|head|director|leiterin? der|bereichsleiter|abteilungsleiter)\b"
YEARS = r"(?:at least|minimum(?: of)?|mindestens|min\.?|mehr als)\s*(\d+)\s*(?:\+\s*)?(?:years?|jahre[n]?)"


def assess_seniority(title, description, desired):
    senior = bool(re.search(SENIOR, title, re.I))
    junior = bool(re.search(JUNIOR, title, re.I))
    years = [int(n) for n in re.findall(YEARS, description, re.I)]
    required = max(years, default=0)
    label = "Senior title" if senior else "Junior / entry-level title" if junior else "Seniority not explicit in title"
    if required:
        label += f"; mentions a minimum of {required} years — verify the requirement"
    mismatch = desired == "Junior / entry level" and (senior or required >= 4)
    mismatch |= desired == "Senior" and junior and not senior
    mismatch |= desired == "Mid-level" and (junior or bool(re.search(r"\b(head|director|principal|staff)\b", title, re.I)))
    return label, mismatch



def normalize(value):
    value = unicodedata.normalize('NFKD', str(value or '').casefold())
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in value if not unicodedata.combining(c))).strip()


def contains(text, phrase):
    return bool(re.search(r'(?<!\w)' + re.escape(normalize(phrase)) + r'(?!\w)', normalize(text)))


def role_terms(role):
    base = re.sub(JUNIOR + '|' + SENIOR, '', role, flags=re.I).strip(' -,')
    if not base:
        raise ValueError('Enter a job role, such as Project manager.')
    for family in FAMILIES:
        if any(contains(base, t) for t in family):
            return list(dict.fromkeys([base] + list(family)))
    return [base]


def industry_terms(industry):
    if re.search(r'solar|photovolta', industry, re.I):
        return ['solar', 'photovoltaik', 'photovoltaics', 'photovoltaic', 'pv']
    if re.search(r'renewable|erneuerbar', industry, re.I):
        return ['renewable energy', 'erneuerbare energien', 'solar', 'photovoltaik', 'windenergie']
    return [x.strip() for x in re.split(r'[,;/]', industry) if x.strip()]


def expand_queries(role, industry=''):
    terms = role_terms(role)
    sector = industry_terms(industry)
    if len(terms) > 1 and any(contains(role, t) for t in FAMILIES[0]):
        terms = [terms[0], 'Projektmanager', 'Projektleiter', 'Projektkoordinator', 'Projektassistenz', 'project coordinator']
    terms = list(dict.fromkeys(terms))[:6]
    return [f'{t} {sector[i % min(len(sector), 2)]}'.strip() if sector else t for i, t in enumerate(terms)]


def canonical_url(value):
    try:
        p = urlsplit(str(value or ''))
        if not p.hostname:
            return ''
        q = [(k, v) for k, v in parse_qsl(p.query) if k.lower() not in ('source', 'ref', 'trackingid', 'trk') and not k.lower().startswith('utm_')]
        return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip('/'), urlencode(sorted(q)), ''))
    except ValueError:
        return ''


def deduplicate(rows):
    output, seen_url, seen_identity = [], {}, {}
    for original in rows:
        row = dict(original)
        urls = [canonical_url(row.get(k)) for k in ('job_url', 'job_url_direct')]
        urls = [u for u in urls if u]
        identity = tuple(normalize(row.get(k)) for k in ('title', 'company', 'location'))
        idx = next((seen_url[u] for u in urls if u in seen_url), None)
        if idx is None and all(identity):
            idx = seen_identity.get(identity)
        if idx is None:
            idx = len(output)
            row['sources'] = row.get('site', '')
            row['listing_urls'] = list(dict.fromkeys(urls))
            output.append(row)
        else:
            existing = output[idx]
            existing['sources'] = ', '.join(sorted(set(existing['sources'].split(', ') + [row.get('site', '')])))
            existing['listing_urls'] = list(dict.fromkeys(existing['listing_urls'] + urls))
            if len(str(row.get('description') or '')) > len(str(existing.get('description') or '')):
                existing['description'] = row['description']
        for u in urls:
            seen_url[u] = idx
        if all(identity):
            seen_identity[identity] = idx
    return output


def rank_jobs(rows, role, industry, seniority, hide_mismatch=False, days=100, remote=False):
    roles, sectors = role_terms(role), industry_terms(industry)
    ranked, rejected = [], 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    for original in rows:
        row = dict(original)
        title, description = str(row.get('title') or ''), str(row.get('description') or '')
        label, mismatch = assess_seniority(title, description, seniority)
        if hide_mismatch and mismatch:
            rejected += 1
            continue
        date = str(row.get('date_posted') or '')[:10]
        try:
            if datetime.fromisoformat(date).date() < cutoff:
                rejected += 1
                continue
        except ValueError:
            date = ''
        if remote and row.get('is_remote') is not True:
            rejected += 1
            continue
        role_hits = [t for t in roles if contains(title, t)]
        description_roles = [t for t in roles if contains(description, t)]
        sector_hits = [t for t in sectors if contains(title + ' ' + description, t)]
        # Points reflect documented evidence, never an AI match percentage.
        score = 50 if role_hits else 20 if description_roles else 0
        reasons = ['Related role in title: ' + ', '.join(role_hits)] if role_hits else ['Related role in description'] if description_roles else ['Role match not confirmed']
        if sectors:
            if sector_hits:
                score += 30
                reasons.append('Industry/skill terms found: ' + ', '.join(sector_hits))
            else:
                reasons.append('Industry/skill match not confirmed')
        if seniority == 'Junior / entry level' and re.search(JUNIOR, title, re.I):
            score += 15
        if seniority == 'Senior' and re.search(SENIOR, title, re.I):
            score += 15
        if mismatch:
            score -= 40
            reasons.append('Possible experience mismatch')
        if not date:
            reasons.append('Posting date unknown; retained for review')
        if not description:
            reasons.append('Description unavailable; check the listing')
        clean = re.sub(r'<[^>]+>', ' ', description)
        sentences = re.split(r'(?<=[.!?])\s+|\n', clean)
        evidence = next((s.strip() for s in sentences if any(contains(s, t) for t in sectors + roles)), '')
        row.update(relevance=score, seniority_check=label, fit_note='; '.join(reasons), evidence=evidence[:650] or 'No matching description excerpt available.')
        ranked.append(row)
    return sorted(ranked, key=lambda r: (r['relevance'], str(r.get('date_posted') or '')), reverse=True), rejected
