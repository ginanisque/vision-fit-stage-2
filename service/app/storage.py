"""Private Neon Object Storage access using its S3-compatible API."""
from __future__ import annotations

import os
from functools import lru_cache

import boto3
from botocore.config import Config

from .settings import get_settings


@lru_cache
def client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        region_name=settings.s3_region,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def put_private(key: str, data: bytes, content_type: str) -> None:
    client().put_object(
        Bucket=get_settings().s3_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
        ServerSideEncryption="AES256",
    )


def get_private(key: str) -> bytes:
    response = client().get_object(Bucket=get_settings().s3_bucket, Key=key)
    return response["Body"].read()


def delete_private(key: str) -> None:
    client().delete_object(Bucket=get_settings().s3_bucket, Key=key)


def signed_download_url(key: str, expires_seconds: int = 900) -> str:
    return client().generate_presigned_url(
        "get_object",
        Params={"Bucket": get_settings().s3_bucket, "Key": key},
        ExpiresIn=expires_seconds,
    )
