from fastapi import APIRouter, HTTPException
from app.models import JobSearchResponse, CandidateIdRequest, SearchResponse
from app.utils import get_candidate_resume_by_name, get_candidate_resume_by_id, fuzzy_match_jobs_from_resume

router = APIRouter(prefix="/candidate", tags=["candidate"])


@router.post("/getjobs", response_model=JobSearchResponse)
async def get_jobs(payload: CandidateIdRequest):
    can_id = payload.candidate_id
    thr = payload.threshold

    candidate = get_candidate_resume_by_id(can_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    candidate_name = candidate.get("first_name", "") + " " + candidate.get("last_name", "")
    resume = get_candidate_resume_by_name(candidate_name)

    resume = resume.matches[0]
    job_matches = fuzzy_match_jobs_from_resume(resume, threshold=thr)
    return job_matches