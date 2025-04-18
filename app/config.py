# app/config.py

import json
import os
import boto3
from botocore.exceptions import ClientError
from pydantic_settings import BaseSettings, SettingsConfigDict
from requests_aws4auth import AWS4Auth
from opensearchpy import OpenSearch, RequestsHttpConnection


def load_aws_secret(secret_name: str):
    client = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION", "us‑east‑1"))
    try:
        resp = client.get_secret_value(SecretId=secret_name)
        return json.loads(resp["SecretString"])
    except ClientError as e:
        raise RuntimeError(f"Unable to fetch secrets: {e}")


secret = load_aws_secret("service-secrets")
os.environ.update(secret)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    aws_region: str = "us-east-1"
    s3_bucket: str
    dynamo_table: str
    opensearch_host: str
    opensearch_index: str
    opensearch_user: str
    opensearch_pass: str
    app_name: str = "ResumeParserAPI"


settings = Settings()

# AWS clients
s3_client = boto3.client("s3", region_name=settings.aws_region)
ddb_table = boto3.resource("dynamodb", region_name=settings.aws_region).Table(settings.dynamo_table)

# OpenSearch client with AWS SigV4
session = boto3.Session()
credentials = session.get_credentials()
awsauth = AWS4Auth(
    credentials.access_key,
    credentials.secret_key,
    settings.aws_region,
    "es",
    session_token=credentials.token
)

os_client = OpenSearch(
    hosts=[{"host": settings.opensearch_host, "port": 443}],
    http_auth=(settings.opensearch_user, settings.opensearch_pass),
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection
)

# Ensure the index exists with appropriate mapping
if not os_client.indices.exists(index=settings.opensearch_index):
    mapping = {
        "settings": {
            "number_of_shards": 1,
            "analysis": {
                "analyzer": {
                    "rebuilt_standard": {
                        "tokenizer": "standard",
                        "filter": ["lowercase", "stop", "porter_stem"]
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "resume_id": {"type": "keyword"},
                "user_id": {"type": "keyword"},
                "s3_key": {"type": "keyword"},
                "uploaded_at": {"type": "date"},
                "emails": {"type": "keyword"},
                "phones": {"type": "keyword"},
                "skills": {
                    "type": "text",
                    "analyzer": "rebuilt_standard"
                },
                "full_text": {
                    "type": "text",
                    "analyzer": "rebuilt_standard"
                }
            }
        }
    }
    os_client.indices.create(index=settings.opensearch_index, body=mapping)
