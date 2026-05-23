from __future__ import annotations

from fastapi import HTTPException, UploadFile

MAX_UPLOAD_SIZE = 10 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024


async def read_limited_upload(file: UploadFile, *, max_size: int = MAX_UPLOAD_SIZE) -> bytes:
    chunks = []
    total = 0
    while True:
        chunk = await file.read(UPLOAD_CHUNK_SIZE)
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > max_size:
            raise HTTPException(status_code=413, detail="File too large")
        chunks.append(chunk)
