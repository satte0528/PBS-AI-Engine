# app/routers/dms.py
import time
import uuid
import tempfile
import os
from datetime import datetime
from typing import List

import boto3
from boto3.dynamodb.conditions import Key
from docx import Document
from fastapi import APIRouter, File, UploadFile, BackgroundTasks, HTTPException
from loguru import logger
from starlette import status

from app.config import settings, s3_client, os_client
from app.models import DocumentInfo
from app.utils import extract_full_text_from_textract

# DynamoDB table for documents
dms_table = boto3.resource(
    "dynamodb",
    region_name=settings.aws_region
).Table("Documents")

# Textract client for text extraction
textract_client = boto3.client(
    "textract",
    region_name=settings.aws_region
)

router = APIRouter(prefix="/dms", tags=["dms"])


def process_and_store_document(
    user_id: str,
    document_name: str,
    document_type: str,
    document_id: str,
    s3_key: str,
    local_path: str
):
    # 1) Extract full text
    if document_type in ["png", "jpg", "jpeg"]:
        resp = textract_client.detect_document_text(
            Document={"S3Object": {"Bucket": settings.s3_bucket_dms, "Name": s3_key}}
        )
        full_text = extract_full_text_from_textract(resp)

    elif document_type == "pdf":
        # start an async job
        start = textract_client.start_document_text_detection(
            DocumentLocation={"S3Object": {"Bucket": settings.s3_bucket_dms, "Name": s3_key}}
        )
        job_id = start["JobId"]

        # poll for completion
        while True:
            status = textract_client.get_document_text_detection(JobId=job_id)["JobStatus"]
            if status in ("SUCCEEDED", "FAILED"):
                break
            time.sleep(1)

        if status != "SUCCEEDED":
            full_text = ""
        else:
            # collect all pages
            pages = []
            next_tok = None
            while True:
                kwargs = {"JobId": job_id}
                if next_tok:
                    kwargs["NextToken"] = next_tok
                out = textract_client.get_document_text_detection(**kwargs)
                for b in out["Blocks"]:
                    if b["BlockType"] == "LINE":
                        pages.append(b["Text"])
                next_tok = out.get("NextToken")
                if not next_tok:
                    break
            full_text = "\n".join(pages)
    elif document_type == "txt":
        with open(local_path, "r") as f:
            full_text = f.read()
    elif document_type == "docx":
        full_text = "\n".join(
            [p.text for p in Document(local_path).paragraphs]
        )
    elif document_type == "rtf":
        with open(local_path, "r") as f:
            full_text = f.read()
    else:
        logger.error("Unknown Format {}", document_type)
        full_text = ""

    # 2) Prepare item
    item = {
        "user_id":       user_id,
        "document_id":   document_id,
        "document_name": document_name,
        "document_type": document_type,
        "s3_key":        s3_key,
        "uploaded_at":   datetime.utcnow().isoformat() + "Z",
        "full_text":     full_text,
    }

    # 3) Store in DynamoDB
    dms_table.put_item(Item=item)

    # 4) Index into OpenSearch
    os_client.index(
        index="documents",
        id=document_id,
        body=item
    )

    # 5) Cleanup local file
    try:
        os.remove(local_path)
    except OSError:
        pass


@router.post("/upload")
async def upload_document(
    user_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    document_id = str(uuid.uuid4())
    document_name = file.filename
    document_type = file.filename.rsplit('.', 1)[-1].lower()
    s3_key = f"{user_id}/{document_id}.{document_type}"

    # 1) Save file locally
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{document_type}") as tmp:
            content = await file.read()
            tmp.write(content)
            local_path = tmp.name
    except Exception as e:
        raise HTTPException(500, f"Failed to save upload: {e}")

    # 2) Upload to S3
    try:
        s3_client.upload_file(local_path, settings.s3_bucket_dms, s3_key)
    except Exception as e:
        os.remove(local_path)
        raise HTTPException(500, f"S3 upload failed: {e}")

    # 3) Enqueue background processing
    background_tasks.add_task(
        process_and_store_document,
        user_id,
        document_name,
        document_type,
        document_id,
        s3_key,
        local_path
    )

    # 4) Generate presigned GET URL (10 min)
    presigned_url = s3_client.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": settings.s3_bucket_dms, "Key": s3_key},
        ExpiresIn=600
    )

    return {
        "document_id":  document_id,
        "message":      "Upload successful; parsing & storage enqueued.",
        "download_url": presigned_url
    }


@router.get("/list", response_model=List[DocumentInfo])
async def list_documents(user_id: str):
    # 1) Query DynamoDB by the user’s partition key
    resp = dms_table.query(
        KeyConditionExpression=Key("user_id").eq(user_id)
    )
    items = resp.get("Items", [])

    result = []
    for item in items:
        doc_id = item["document_id"]
        doc_type = item["document_type"]
        key = f"{user_id}/{doc_id}.{doc_type}"
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket_dms, "Key": key},
            ExpiresIn=600
        )
        result.append(DocumentInfo(document_id=doc_id, download_url=url))

    return result


@router.delete("/delete", status_code=status.HTTP_200_OK)
async def delete_document(user_id: str, document_id: str):
    # 1) Fetch Dynamo item to know its file extension
    resp = dms_table.get_item(Key={"user_id": user_id, "document_id": document_id})
    item = resp.get("Item")
    if not item:
        raise HTTPException(404, "Document not found")

    doc_type = item["document_type"]
    s3_key = f"{user_id}/{document_id}.{doc_type}"

    # 2) Delete from S3
    s3_client.delete_object(Bucket=settings.s3_bucket_dms, Key=s3_key)

    # 3) Delete from DynamoDB
    dms_table.delete_item(Key={"user_id": user_id, "document_id": document_id})

    # 4) Delete from OpenSearch
    os_client.delete(index="documents", id=document_id, ignore=[404])


@router.get("/search", response_model=List[DocumentInfo])
async def search_documents(user_id: str, keyword: str):
    q = {
        "size": 50,
        "query": {
            "bool": {
                "must": [
                    {"term": {"user_id": user_id}},
                    {
                        "match": {
                            "full_text": {
                                "query": keyword,
                                "operator": "and"
                            }
                        }
                    }
                ]
            }
        }
    }

    try:
        resp = os_client.search(index="documents", body=q)
    except Exception as e:
        raise HTTPException(500, f"OpenSearch query failed: {e}")

    hits = resp.get("hits", {}).get("hits", [])
    results: List[DocumentInfo] = []

    for hit in hits:
        src = hit["_source"]
        doc_id = src["document_id"]
        doc_type = src["document_type"]
        key = f"{user_id}/{doc_id}.{doc_type}"
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket_dms, "Key": key},
            ExpiresIn=600
        )
        results.append(DocumentInfo(document_id=doc_id, download_url=url))

    return results

