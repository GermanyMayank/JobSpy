"""Local multilingual semantic ranking; no hosted inference or profile upload."""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("HF_HOME", str(ROOT / ".models"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
FAMILIES = [
    ("project manager", "project coordinator", "Projektmanager", "Projektleiter", "Projektkoordinator"),
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


def simplify_role(role):
    return re.sub(JUNIOR + "|" + SENIOR, "", role, flags=re.I).strip(" -,")


def expand_queries(role, industry=""):
    base = simplify_role(role)
    if not base:
        raise ValueError("Enter a job role, such as Project manager.")
    variants = [base]
    for family in FAMILIES:
        if any(re.search(r"\b" + re.escape(t) + r"\b", base, re.I) for t in family):
            variants += list(family)
            break
    variants = list(dict.fromkeys(t.casefold() for t in variants))
    # One original, one related and one German title when a known family exists.
    german = next((t for t in variants if re.search(r"projekt|entwickler|ingenieur|datenanalyst|prozess|vertrieb|personal|logistik|qualit|betrieb|finanz", t)), None)
    chosen = variants[:2]
    if german and german not in chosen:
        chosen.append(german)
    elif len(variants) > 2:
        chosen.append(variants[2])
    sector = industry.strip()
    if re.search(r"solar|photovolta|renewable|erneuerbar", sector, re.I):
        terms = ["solar", "renewable energy", "Photovoltaik"]
        return [f"{q} {terms[i]}" for i, q in enumerate(chosen)]
    return [f"{q} {sector}".strip() for q in chosen]


def load_model():
    from sentence_transformers import SentenceTransformer
    local = ROOT / ".models" / "local-minilm"
    if (local / "model.safetensors").exists():
        return SentenceTransformer(str(local), device="cpu", local_files_only=True, trust_remote_code=False)
    return SentenceTransformer(MODEL, device="cpu", cache_folder=str(ROOT / ".models"), trust_remote_code=False)


def text_chunks(text):
    words = re.sub(r"<[^>]+>", " ", text).split()
    chunks = [" ".join(words[i:i + 65]) for i in range(0, len(words), 55)]
    return chunks[:15] + chunks[-5:] if len(chunks) > 20 else chunks


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


def rank_jobs(rows, role, industry, seniority, hide_mismatch=False, model=None):
    import numpy as np
    if not rows:
        return [], 0
    model = model or load_model()
    query = f"{simplify_role(role)}. {industry}".strip(". ")
    documents, spans = [], []
    for row in rows:
        title = str(row.get("title") or "")
        chunks = text_chunks(str(row.get("description") or "")) or [title]
        start = len(documents)
        documents += [title] + chunks
        spans.append((start, len(documents)))
    vectors = model.encode([query] + documents, normalize_embeddings=True, show_progress_bar=False, batch_size=32)
    similarity = vectors[1:] @ vectors[0]
    rejected = 0
    ranked = []
    for row, (start, end) in zip(rows, spans):
        best = start + 1 + int(np.argmax(similarity[start + 1:end]))
        score = 0.55 * float(similarity[start]) + 0.45 * float(similarity[best])
        title = str(row.get("title") or "")
        description = str(row.get("description") or "")
        label, mismatch = assess_seniority(title, description, seniority)
        if mismatch and hide_mismatch:
            rejected += 1
            continue
        if mismatch:
            score -= 0.20
        elif seniority == "Junior / entry level" and re.search(JUNIOR, title, re.I):
            score += 0.08
        elif seniority == "Senior" and re.search(SENIOR, title, re.I):
            score += 0.08
        row.update(relevance=round(score, 3), seniority_check=label,
                   fit_note="Possible experience mismatch" if mismatch else "Compare the requirements with your experience",
                   evidence=documents[best] if description else "Description unavailable; ranked from the title only.")
        ranked.append(row)
    return sorted(ranked, key=lambda r: r["relevance"], reverse=True), rejected
