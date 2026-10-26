"""Gzipped JSONL shards with fail-safe local spool and optional Azure uploads."""
import gzip
import json
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone

class ShardWriter:
    def __init__(self, root, connection_string="", container="btc-orderflow", upload=True):
        self.root = Path(root)
        self.root.mkdir(parents=True,exist_ok=True)
        self.container = container
        self.client = None
        if connection_string and upload:
            from azure.storage.blob import BlobServiceClient
            self.client = BlobServiceClient.from_connection_string(connection_string)
        self.written = self.uploaded = 0

    def write(self, stream, records, now=None):
        if not records:
            return None
        now = now or datetime.now(timezone.utc)
        prefix = now.strftime("%Y/%m/%d/%H")
        name = f"{stream}/{prefix}/{now.strftime('%Y%m%dT%H%M%S%fZ')}-{os.urandom(4).hex()}.jsonl.gz"
        dest = self.root / name
        dest.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=dest.parent,delete=False) as tmp:
            path=tmp.name
        try:
            with gzip.open(path,"wt",encoding="utf-8",compresslevel=6) as f:
                for rec in records:
                    f.write(json.dumps(rec,separators=(",",":"),allow_nan=False)+"\n")
            os.replace(path,dest)
        finally:
            if os.path.exists(path):
                os.unlink(path)
        self.written += 1
        if self.client:
            self._upload(dest,name)
        return name

    def _upload(self,path,name):
        from azure.storage.blob import ContentSettings
        with open(path,"rb") as f:
            self.client.get_blob_client(self.container,name).upload_blob(
                f,overwrite=False,content_settings=ContentSettings(
                    content_type="application/x-ndjson",content_encoding="gzip"))
        path.unlink()
        self.uploaded += 1

    def retry_spool(self):
        if not self.client:
            return 0
        count=0
        for p in self.root.rglob("*.jsonl.gz"):
            self._upload(p,p.relative_to(self.root).as_posix())
            count+=1
        return count
