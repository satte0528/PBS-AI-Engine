# app/models.py

from pydantic import BaseModel, Field
from typing import List, Optional


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


class SearchResponse(BaseModel):
    matches: List[ResumeMatch] = Field(..., description="List of resumes meeting the search criteria")
