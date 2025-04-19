# app/routers/resume.py

import os
import uuid
import tempfile
from datetime import datetime

from fastapi import APIRouter, File, UploadFile, BackgroundTasks, HTTPException

from app.utils import parse_resume
from app.models import UploadResponse
from app.config import settings, s3_client, ddb_table, os_client
from app.models import SearchRequest, ResumeMatch, SearchResponse

router = APIRouter(prefix="/resume", tags=["resume"])


def process_and_store(user_id: str, resume_id: str, s3_key: str, local_path: str):
    data = parse_resume(local_path, default_region="US")

    # 1) Write to DynamoDB
    item = {
        "user_id": user_id,
        "resume_id": resume_id,
        "s3_key": s3_key,
        "emails": data["emails"],
        "phones": data["phones"],
        "skills": data["skills"],
        "full_text": data["full_text"],
        "uploaded_at": datetime.utcnow().isoformat() + "Z",
    }
    ddb_table.put_item(Item=item)

    # 2) Index into OpenSearch
    os_client.index(
        index=settings.opensearch_index,
        id=resume_id,
        body=item
    )

    # 3) Cleanup
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


@router.post("/search", response_model=SearchResponse)
async def search_resumes(request: SearchRequest):
    """
    Use OpenSearch full-text + skills match with fuzziness and threshold.
    """
    jd = request.job_description
    thr = request.threshold

    # Construct a bool query: multi_match across skills & full_text
    query = {
        "size": 50,
        "query": {
            "bool": {
                "should": [
                    {
                        "multi_match": {
                            "query": jd,
                            "fields": ["skills^2", "full_text"],
                            "type": "most_fields",
                            "fuzziness": "AUTO",
                            "minimum_should_match": f"{int(thr)}%"
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

    matches = []
    for hit in res["hits"]["hits"]:
        src = hit["_source"]

        download_url = s3_client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": settings.s3_bucket, "Key": src["s3_key"]},
            ExpiresIn=600
        )

        matches.append(ResumeMatch(
            resume_id=src["resume_id"],
            emails=src.get("emails", []),
            phones=src.get("phones", []),
            skills=src.get("skills", []),
            download_url=download_url
        ))

    return SearchResponse(matches=matches)
