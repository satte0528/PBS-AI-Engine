# app/config.py

import json
import os
import boto3
from botocore.exceptions import ClientError
from pydantic_settings import BaseSettings, SettingsConfigDict
from requests_aws4auth import AWS4Auth
from opensearchpy import OpenSearch, RequestsHttpConnection
import psycopg2
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

def load_aws_secret(secret_name: str):
    client = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION", "us-east-1"))
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
    s3_bucket_dms: str
    s3_bucket_resume: str
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
class DbConnection:
    def __init__(self):
        # Load secrets
        secret_name = os.getenv("AWS_RDS_SECRET_NAME", "pb-datasource")
        region = os.getenv("AWS_REGION", "us-east-1")

        client = boto3.client("secretsmanager", region_name=region)
        response = client.get_secret_value(SecretId=secret_name)
        secret = json.loads(response["SecretString"])

        # Parse JDBC URL
        url = secret["url"].replace("jdbc:", "")
        parsed = urlparse(url)

        self.conn = psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port,
            database=parsed.path.lstrip("/"),
            user=secret["username"],
            password=secret["password"]
        )

        # Optional: test query
        with self.conn.cursor() as cur:
            cur.execute("SELECT 1;")
            print("✅ RDS connection verified.")

    def get_cursor(self):
        return self.conn.cursor()

    def close(self):
        if self.conn:
            self.conn.close()