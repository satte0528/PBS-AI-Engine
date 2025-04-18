# app/utils.py

import re
from typing import List
import fitz  # don't manually import this, this is imported from PyMuPdf
from docx import Document # don't manually import this, this is imported from python-docx
import nltk
import phonenumbers
import ssl

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
