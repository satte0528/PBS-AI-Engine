from fastapi import APIRouter, UploadFile, Form, File
from app.utils import extract_text_from_pdf, extract_skills, clean_text
from app.models import model
from sentence_transformers import util

router = APIRouter()

@router.post("/match-resume/")
async def match_resume(resume: UploadFile = File(...), job_description: str = Form(...)):
    # Extract text from resume PDF
    resume_text = extract_text_from_pdf(resume.file)
    resume_text_cleaned = clean_text(resume_text)
    job_description_cleaned = clean_text(job_description)

    # Get key skills
    resume_skills = extract_skills(resume_text_cleaned)
    job_skills = extract_skills(job_description_cleaned)

    # Compute similarity score
    resume_embedding = model.encode(resume_text_cleaned, convert_to_tensor=True)
    job_embedding = model.encode(job_description_cleaned, convert_to_tensor=True)
    similarity_score = util.pytorch_cos_sim(resume_embedding, job_embedding).item()

    return {
        "match_score": round(similarity_score, 2),
        "resume_skills": resume_skills,
        "job_skills": job_skills,
        "matching_skills": list(set(resume_skills) & set(job_skills))
    }
