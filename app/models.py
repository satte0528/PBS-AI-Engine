# app/models.py

from pydantic import BaseModel
from typing import List


class UploadResponse(BaseModel):
    resume_id: str
    message: str


class ResumeData(BaseModel):
    emails: List[str]
    phones: List[str]
    skills: List[str]
