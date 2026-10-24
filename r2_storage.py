"""Private Cloudflare R2 downloads for StreamDex.

R2 credentials are read only from Streamlit secrets. No public bucket URLs are
used; each eligible download receives a short-lived, object-specific GET URL.
"""
import re
from pathlib import PurePosixPath

import streamlit as st

R2_URL_TTL_SECONDS = 300
_ACCOUNT_ID_RE = re.compile(r"^[a-fA-F0-9]{32}$")


def is_valid_r2_object_key(value):
    """Accept a relative R2 key, rejecting traversal, URL fragments, and controls."""
    if not isinstance(value, str):
        return False
    key = value.strip()
    if not key or len(key) > 512 or key.startswith("/") or "\\" in key:
        return False
    if any(ord(char) < 32 or ord(char) == 127 for char in key):
        return False
    if any(char in key for char in ("?", "#")) or "//" in key:
        return False
    parts = key.split("/")
    return all(part not in ("", ".", "..") for part in parts)


def _r2_settings():
    try:
        cfg = st.secrets.get("r2", {})
        if not hasattr(cfg, "get"):
            return {}
        account_id = str(cfg.get("account_id") or "").strip()
        bucket = str(cfg.get("bucket_name") or "").strip()
        access_key = str(cfg.get("access_key_id") or "").strip()
        secret_key = str(cfg.get("secret_access_key") or "").strip()
    except Exception:
        return {}
    if not _ACCOUNT_ID_RE.fullmatch(account_id):
        return {}
    if not bucket or not access_key or not secret_key:
        return {}
    return {
        "account_id": account_id,
        "bucket_name": bucket,
        "access_key_id": access_key,
        "secret_access_key": secret_key,
    }


def r2_is_configured():
    """Return whether the minimum R2 settings are present without exposing values."""
    return bool(_r2_settings())


def create_presigned_download_url(object_key):
    """Create a five-minute, read-only URL for a validated private R2 object."""
    if not is_valid_r2_object_key(object_key):
        return None
    cfg = _r2_settings()
    if not cfg:
        return None

    try:
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=f"https://{cfg['account_id']}.r2.cloudflarestorage.com",
            aws_access_key_id=cfg["access_key_id"],
            aws_secret_access_key=cfg["secret_access_key"],
            region_name="auto",
        )
        filename = PurePosixPath(object_key).name
        safe_filename = re.sub(r"[^A-Za-z0-9._-]", "_", filename)[:180] or "game-download"
        return client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": cfg["bucket_name"],
                "Key": object_key,
                "ResponseContentDisposition": f'attachment; filename="{safe_filename}"',
            },
            ExpiresIn=R2_URL_TTL_SECONDS,
            HttpMethod="GET",
        )
    except Exception:
        # Do not log credentials, object URLs, or provider exception payloads.
        return None
