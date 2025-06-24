# app/models.py

from pydantic import BaseModel, Field
from typing import List, Optional, Union


class UploadResponse(BaseModel):
    resume_id: str = Field(..., description="Unique ID generated for the uploaded resume")
    message: str = Field(..., description="Confirmation message")


class SearchRequest(BaseModel):
    job_description: str = Field(..., description="Free-text job description to match against resumes")
    threshold: float = Field(
        ...,
        ge=0,
        le=100,
        description="Minimum match percentage (0–100) required to include a resume"
    )


class ResumeMatch(BaseModel):
    resume_id: str = Field(..., description="ID of the matching resume")
    emails: List[str] = Field(..., description="Extracted email addresses from the resume")
    phones: List[str] = Field(..., description="Extracted phone numbers from the resume")
    skills: List[str] = Field(..., description="Extracted skills from the resume")
    download_url: str = Field(..., description="Presigned S3 URL valid for 10 minutes")


class DocumentInfo(BaseModel):
    document_id: str
    download_url: str


class SearchResponse(BaseModel):
    matches: List[ResumeMatch] = Field(..., description="List of resumes meeting the search criteria")


class CandidateInfo(BaseModel):
    id: int = Field(..., description="Primary ID of the candidate")
    user_oid: Union[str, int] = Field(..., description="User OID as UUID or int from DB")
    first_name: str = Field(..., description="Candidate's first name")
    last_name: str = Field(..., description="Candidate's last name")
    current_job_title: Optional[str] = Field(None, description="Current job title")
    experience_yoe: Optional[int] = Field(None, description="Years of experience")
    employment_type: Optional[str] = Field(None, description="Full-time, contract, etc.")
    work_auth_type: Optional[str] = Field(None, description="Work authorization type (e.g., US Citizen, H1B)")
    current_location: Optional[str] = Field(None, description="Current city/state/country")
    relocation: Optional[bool] = Field(None, description="Is candidate open to relocation?")
    job_alert: Optional[bool] = Field(None, description="Has the candidate enabled job alerts?")
class CandidateIdRequest(BaseModel):
    candidate_id: int
    threshold: float = Field(..., ge=0, le=100)

class JobMatch(BaseModel):
    job_id: int = Field(..., description="Primary key of the job")
    job_title: str = Field(..., description="Title of the job")
    job_description: str = Field(..., description="Full job description")
    job_location: Optional[str] = Field(None, description="Location of the job")
    job_type: Optional[str] = Field(None, description="Job type such as full-time, part-time, etc.")
    required_yoe: Optional[int] = Field(None, description="Required years of experience")
    accepted_work_auth: Optional[str] = Field(None, description="Work authorization types accepted")
    company_name: Optional[str] = Field(None, description="Name of the company")
    job_promotion: Optional[bool] = Field(None, description="Is this a promoted/featured job?")
    match_score: float = Field(..., description="Fuzzy match score between resume and job (0–100)")


class JobSearchResponse(BaseModel):
    matches: List[JobMatch] = Field(..., description="List of job matches for the resume")
