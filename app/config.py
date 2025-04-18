# app/config.py

import boto3
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Load from .env and ignore any extra env vars
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # drop any env vars not declared below
    )

    aws_region: str = "us-east-1"
    s3_bucket: str
    dynamo_table: str
    app_name: str = "ResumeParserAPI"


settings = Settings()

# AWS clients will pick up AWS_ACCESS_KEY_ID/SECRET from the env automatically
s3_client = boto3.client("s3", region_name=settings.aws_region)
ddb_table = (
    boto3
    .resource("dynamodb", region_name=settings.aws_region)
    .Table(settings.dynamo_table)
)
