from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ieim.raw_store import RawStorePutResult, sha256_prefixed


@dataclass(frozen=True)
class S3ObjectStoreConfig:
    bucket: str
    endpoint_url: Optional[str] = None
    region_name: Optional[str] = None
    key_prefix: str = ""
    force_path_style: bool = True


class S3ObjectStore:
    def __init__(self, *, config: S3ObjectStoreConfig) -> None:
        self._config = config
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        try:
            import boto3  # type: ignore
            from botocore.config import Config as BotoConfig  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError("boto3 is required for S3ObjectStore (requirements/runtime.txt)") from e

        s3_cfg = {}
        if self._config.force_path_style:
            s3_cfg["addressing_style"] = "path"
        botocfg = BotoConfig(s3=s3_cfg) if s3_cfg else None

        self._client = boto3.client(
            "s3",
            endpoint_url=self._config.endpoint_url,
            region_name=self._config.region_name,
            config=botocfg,
        )
        return self._client

    def put_bytes(
        self,
        *,
        kind: str,
        data: bytes,
        file_extension: Optional[str] = None,
    ) -> RawStorePutResult:
        if not kind or "/" in kind or "\\" in kind:
            raise ValueError("kind must be a simple token")
        if file_extension and not file_extension.startswith("."):
            raise ValueError("file_extension must start with '.'")

        sha = sha256_prefixed(data)
        hex_hash = sha.split(":", 1)[1]
        ext = file_extension or ""
        key = f"raw_store/{kind}/{hex_hash}{ext}"
        if self._config.key_prefix:
            key = f"{self._config.key_prefix.rstrip('/')}/{key}"

        client = self._get_client()

        try:
            head = client.head_object(Bucket=self._config.bucket, Key=key)
        except Exception:
            head = None

        if head is not None:
            meta = head.get("Metadata") if isinstance(head, dict) else None
            meta_sha = meta.get("sha256") if isinstance(meta, dict) else None
            if meta_sha and meta_sha != sha:
                raise RuntimeError("immutability violation: existing object metadata sha256 mismatch")
            return RawStorePutResult(uri=key, sha256=sha, size_bytes=len(data))

        client.put_object(
            Bucket=self._config.bucket,
            Key=key,
            Body=data,
            Metadata={"sha256": sha, "size_bytes": str(len(data))},
        )

        return RawStorePutResult(uri=key, sha256=sha, size_bytes=len(data))

    def get_bytes(self, *, uri: str) -> bytes:
        client = self._get_client()
        obj = client.get_object(Bucket=self._config.bucket, Key=uri)
        body = obj.get("Body") if isinstance(obj, dict) else None
        if body is None:
            raise RuntimeError("S3 get_object returned no Body")
        return body.read()

