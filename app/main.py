# app/main.py

from fastapi import FastAPI
from app.config import settings
from app.routers.resume import router as resume_router

app = FastAPI(title=settings.app_name)

# mount the resume router
app.include_router(resume_router)
