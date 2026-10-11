"""Private storage; callers supply server-generated keys only."""

import os
from pathlib import Path

from django.conf import settings


def storage_bucket():
    return (
        "local" if settings.PRIVATE_STORAGE_BACKEND == "local" else settings.R2_BUCKET
    )


def _path(key):
    root = Path(settings.PRIVATE_STORAGE_ROOT).resolve()
    path = (root / key).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("Invalid storage key")
    return path


def _client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=Config(connect_timeout=5, read_timeout=20, retries={"max_attempts": 2}),
    )


def write_object(bucket, key, data, *, content_type="application/pdf"):
    if bucket == "local":
        path = _path(key)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with os.fdopen(
            os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
        ) as stream:
            stream.write(data)
    else:
        _client().put_object(
            Bucket=bucket, Key=key, Body=data, ContentType=content_type
        )


def read_object(bucket, key):
    if bucket == "local":
        with _path(key).open("rb") as stream:
            return stream.read(settings.MAX_DOCUMENT_BYTES + 1)
    result = _client().get_object(Bucket=bucket, Key=key)
    try:
        return result["Body"].read(settings.MAX_DOCUMENT_BYTES + 1)
    finally:
        result["Body"].close()


def delete_object(bucket, key):
    if bucket == "local":
        _path(key).unlink(missing_ok=True)
    else:
        _client().delete_object(Bucket=bucket, Key=key)
