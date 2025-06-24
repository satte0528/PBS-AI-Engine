# app/utils.py

import re
from typing import List
import fitz  # don't manually import this, this is imported from PyMuPdf
from docx import Document # don't manually import this, this is imported from python-docx
import nltk
import phonenumbers
import ssl
from app.config import DbConnection
from app.models import ResumeMatch, SearchResponse
from typing import Optional, Dict
from fastapi import HTTPException
from app.config import settings, os_client, s3_client
from typing import List
from app.models import ResumeMatch, JobMatch, JobSearchResponse
from app.config import DbConnection
from rapidfuzz import fuzz
try:
    _create_unverified = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified

nltk.download("punkt")
nltk.download('punkt_tab')
nltk.download("averaged_perceptron_tagger")
nltk.download("averaged_perceptron_tagger_eng")


EMAIL_REGEX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def extract_all_emails(text: str) -> List[str]:
    return list(set(EMAIL_REGEX.findall(text)))


def extract_all_phones(text: str, default_region: str = None) -> List[str]:
    found = []
    for m in phonenumbers.PhoneNumberMatcher(text, default_region):
        found.append(phonenumbers.format_number(
            m.number, phonenumbers.PhoneNumberFormat.E164
        ))
    return list(set(found))


def extract_full_text_from_textract(response):
    # Keep only the LINE blocks
    lines = [b for b in response["Blocks"] if b["BlockType"] == "LINE"]

    # Sort by their vertical position on the page
    lines.sort(key=lambda l: l["Geometry"]["BoundingBox"]["Top"])

    # Concatenate into one big string, with line breaks
    return "\n".join(l["Text"] for l in lines)


def extract_text_from_file(path: str) -> str:
    path_lower = path.lower()
    if path_lower.endswith(".pdf"):
        doc = fitz.open(path)
        text = []
        for page in doc:
            text.append(page.get_text())
        doc.close()
        return "\n".join(text)

    elif path_lower.endswith(".docx"):
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs)

    else:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()


def find_skills_block(text: str) -> str:
    lines = text.splitlines()
    start = None
    for i, L in enumerate(lines):
        if re.match(r"^\s*(Technologies|Skills|Technical Skills|Skills & Technologies)\s*[:\-]?\s*$", L, re.I):
            start = i + 1
            break
    if start is None:
        for i, L in enumerate(lines):
            if "skills" in L.lower():
                start = i + 1
                break
    if start is None:
        return ""
    block = []
    for L in lines[start:]:
        if not L.strip() or re.match(r"^[A-Z0-9 \-]{3,}[:\-]?\s*$", L):
            break
        block.append(L.strip())
    return " ".join(block)


def extract_skills(text: str) -> List[str]:
    block = find_skills_block(text)
    raw_items = re.split(r"[,\•;\n]", block)
    skills = []
    for item in raw_items:
        skill = item.strip(" •\t\n\r")
        if not skill:
            continue
        tokens = nltk.word_tokenize(skill)
        tags = nltk.pos_tag(tokens)
        nouns = sum(1 for _, t in tags if t.startswith(("NN", "JJ")))
        if tokens and nouns >= len(tags) / 2:
            skills.append(skill)
    seen, unique = set(), []
    for s in skills:
        key = s.lower()
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return unique


# 5) Master parse function
def parse_resume(path: str, default_region: str = None) -> dict:
    text = extract_text_from_file(path)
    return {
        "emails": extract_all_emails(text),
        "phones": extract_all_phones(text, default_region),
        "skills": extract_skills(text),
        "full_text": text,
    }


def get_candidate_resume_by_id(candidate_id: int) -> Optional[Dict]:
    db = DbConnection()
    cur = None
    try:
        cur = db.get_cursor()
        cur.execute("""
            SELECT * FROM public.candidates
            WHERE id = %s
        """, (candidate_id,))
        row = cur.fetchone()
        if not row:
            return None
        columns = [col.name for col in cur.description]
        return dict(zip(columns, row))
    finally:
        if cur:
            cur.close()
        db.close()




def get_candidate_resume_by_name(candidate_name: str) -> SearchResponse:
    # Build fuzzy search query on candidate name
    query = {
        "size": 50,
        "query": {
            "bool": {
                "should": [
                    {
                        "multi_match": {
                            "query": candidate_name,
                            "type": "most_fields",
                            "fuzziness": "AUTO",
                            "minimum_should_match": f"{int(100)}%"
                        }
                    }
                ],
                "minimum_should_match": 1
            }
        }
    }

    try:
        res = os_client.search(index=settings.opensearch_index, body=query)
    except Exception as e:
        raise HTTPException(500, f"OpenSearch query failed: {e}")

    hits = res.get("hits", {}).get("hits", [])
    if not hits:
        return SearchResponse(matches=[])

    matches: List[ResumeMatch] = []
    for hit in hits:
        src = hit["_source"]
        try:
            download_url = s3_client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": settings.s3_bucket_resume, "Key": src["s3_key"]},
                ExpiresIn=600
            )
        except Exception as e:
            raise HTTPException(500, f"Failed to generate download URL: {e}")

        matches.append(ResumeMatch(
            resume_id=src["resume_id"],
            emails=src.get("emails", []),
            phones=src.get("phones", []),
            skills=src.get("skills", []),
            download_url=download_url
        ))

    return SearchResponse(matches=matches)



def fuzzy_match_jobs_from_resume(
    resume: ResumeMatch,
    threshold: float = 60.0
) -> JobSearchResponse:
    # 1) Clean up the skills_text
    skills = [
        re.sub(r"^Skills[:：]\s*", "", s, flags=re.IGNORECASE)
        for s in resume.skills or []
    ]
    skills_text = " ".join(skills)

    db = DbConnection()
    cur = db.get_cursor()
    try:
        cur.execute("""
            SELECT id, job_title, job_description, job_location, job_type,
                   required_yoe, accepted_work_auth, company_name, job_promotion
            FROM jobs
            WHERE job_status = 'ACTIVE'
        """)
        jobs = cur.fetchall()

        matches: List[JobMatch] = []

        for job in jobs:
            (
                job_id, title, desc, location, jtype,
                yoe, auth, company, promo
            ) = job

            # 2) Combine title + description
            combined = f"{title or ''} {desc or ''}"

            # 3) Compute a weighted fuzzy score
            score = fuzz.WRatio(skills_text, combined)

            # 4) DEBUG: print or log each score
            print(f"[DEBUG] Job {job_id} ('{title}') → score: {score}")

            if score >= threshold:
                matches.append(JobMatch(
                    job_id=job_id,
                    job_title=title,
                    job_description=desc,
                    job_location=location,
                    job_type=jtype,
                    required_yoe=yoe,
                    accepted_work_auth=auth,
                    company_name=company,
                    job_promotion=promo,
                    match_score=round(score, 2)
                ))

        # 5) Sort descending
        matches.sort(key=lambda m: m.match_score, reverse=True)
        return JobSearchResponse(matches=matches)

    finally:
        cur.close()
        db.close()