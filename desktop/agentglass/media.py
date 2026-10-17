"""Sequential resumable uploads; completion requires size and SHA-256 agreement."""
import hashlib
import re
import uuid
import os
from pathlib import Path

ALLOWED_MIME = {"image/jpeg", "audio/wav", "video/x-motion-jpeg"}
MAX_MEDIA = 64*1024*1024
MAX_CHUNK = 256*1024


class MediaStore:
    def __init__(self, directory: Path, store, quota=512*1024*1024):
        self.directory, self.store, self.quota = directory, store, quota
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)

    def create(self, device, *, size, sha256, mime, request_id=None):
        if type(size) is not int or not 1 <= size <= MAX_MEDIA:
            raise ValueError("invalid_media_size")
        if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256) or mime not in ALLOWED_MIME:
            raise ValueError("invalid_media_metadata")
        if request_id is not None:
            if not isinstance(request_id,str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}",request_id):
                raise ValueError("invalid_media_request_id")
            old=self.store.db.execute("SELECT * FROM media WHERE device=? AND request_id=?",(device,request_id)).fetchone()
            if old:
                if (old['size'],old['sha256'],old['mime'])!=(size,sha256,mime):
                    raise ValueError("media_idempotency_conflict")
                return old['id']
        # Reserve the declared full length, including partial uploads.
        reserved = self.store.db.execute("SELECT COALESCE(SUM(size),0) FROM media").fetchone()[0]
        if reserved+size > self.quota:
            raise ValueError("media_quota_exceeded")
        media_id = str(uuid.uuid4())
        partial=self.directory/(media_id+".part")
        with partial.open('xb') as f:
            os.chmod(partial,0o600)
            f.flush();os.fsync(f.fileno())
        try:
            with self.store.db:
                self.store.db.execute("INSERT INTO media(id,device,size,sha256,mime,request_id) VALUES(?,?,?,?,?,?)",
                                     (media_id, device, size, sha256, mime, request_id))
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        return media_id

    def info(self, device, media_id):
        row = self.store.db.execute("SELECT * FROM media WHERE id=? AND device=?", (media_id, device)).fetchone()
        if not row:
            raise KeyError("media_not_found")
        result=dict(row)
        result['complete']=bool(result['complete'])
        return result

    def append(self, device, media_id, offset, data: bytes):
        row = self.info(device, media_id)
        if row["complete"]:
            raise ValueError("media_already_complete")
        if type(offset) is not int or not 0 <= offset <= row["size"] or not 0 < len(data) <= MAX_CHUNK:
            raise ValueError("invalid_chunk")
        path = self.directory/(row["id"]+".part")
        # Disk length is authoritative after crash between fsync and SQLite commit.
        length = path.stat().st_size
        if offset < length and offset+len(data) <= length:
            with path.open("rb") as f:
                f.seek(offset)
                if f.read(len(data)) == data:
                    return length  # exact retry is idempotent
            raise ValueError("conflicting_chunk")
        if offset != length or length+len(data) > row["size"]:
            raise ValueError("offset_conflict")
        with path.open("ab") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        with self.store.db:
            self.store.db.execute("UPDATE media SET received=? WHERE id=?", (length+len(data), row["id"]))
        return length+len(data)

    def commit(self, device, media_id):
        row = self.info(device, media_id)
        if row["complete"]:
            return row
        path = self.directory/(row["id"]+".part")
        if path.stat().st_size != row["size"]:
            raise ValueError("incomplete_media")
        with path.open("rb") as f:
            checksum = hashlib.file_digest(f, "sha256").hexdigest()
        if checksum != row["sha256"]:
            raise ValueError("media_hash_mismatch")
        # Rename before metadata update; recover a completed rename on restart.
        path.rename(self.directory/(row["id"]+".bin"))
        if __import__('os').name != 'nt':
            import os
            fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        with self.store.db:
            self.store.db.execute("UPDATE media SET complete=1,received=size WHERE id=?", (row["id"],))
            self.store.audit("media.committed", {"id": row["id"], "size": row["size"], "sha256": checksum})
        return self.info(device, media_id)

    def recover(self):
        for row in self.store.db.execute("SELECT * FROM media WHERE complete=0").fetchall():
            final = self.directory/(row["id"]+".bin")
            partial = self.directory/(row["id"]+".part")
            if final.exists():
                with final.open("rb") as f:
                    valid = final.stat().st_size == row["size"] and hashlib.file_digest(f, "sha256").hexdigest() == row["sha256"]
                if valid:
                    with self.store.db:
                        self.store.db.execute("UPDATE media SET complete=1,received=size WHERE id=?", (row["id"],))
            elif partial.exists():
                with self.store.db:
                    self.store.db.execute("UPDATE media SET received=? WHERE id=?", (partial.stat().st_size, row["id"]))
