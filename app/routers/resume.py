# app/routers/resume.py

import os
import uuid
import tempfile
from datetime import datetime

from fastapi import APIRouter, File, UploadFile, BackgroundTasks, HTTPException

from app.config import settings, s3_client, ddb_table
from app.utils import parse_resume
from app.models import UploadResponse

router = APIRouter(prefix="/resume", tags=["resume"])


def process_and_store(user_id: str, resume_id: str, s3_key: str, local_path: str):
    data = parse_resume(local_path, default_region="US")
    item = {
        "user_id": user_id,
        "resume_id": resume_id,
        "s3_key": s3_key,
        "emails": data["emails"],
        "phones": data["phones"],
        "skills": data["skills"],
        "uploaded_at": datetime.utcnow().isoformat() + "Z",
    }
    ddb_table.put_item(Item=item)
    try:
        os.remove(local_path)
    except OSError:
        pass


@router.post("/upload", response_model=UploadResponse)
async def upload_resume(
        user_id: str,
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...)
):
    resume_id = str(uuid.uuid4())
    ext = file.filename.rsplit(".", 1)[-1]
    s3_key = f"{user_id}/{resume_id}.{ext}"

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
    except Exception as e:
        raise HTTPException(500, f"Failed to save upload: {e}")

    try:
        s3_client.upload_file(tmp_path, settings.s3_bucket, s3_key)
    except Exception as e:
        os.remove(tmp_path)
        raise HTTPException(500, f"S3 upload failed: {e}")

    background_tasks.add_task(
        process_and_store, user_id, resume_id, s3_key, tmp_path
    )

    return UploadResponse(
        resume_id=resume_id,
        message="Upload successful; parsing & storage enqueued."
    )
