"""Durable state, scoped device credentials, resumable events and audit chain."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import time
import uuid
from pathlib import Path


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


TERMINAL = {"completed", "failed", "cancelled", "rejected", "unknown"}
TRANSITIONS = {
    "pending": {"preparing", "rejected", "cancelled"},
    "preparing": {"running", "failed", "cancel_requested", "unknown"},
    "running": {"completed", "failed", "cancel_requested", "cancelled", "unknown"},
    "cancel_requested": {"cancelled", "completed", "failed", "unknown"},
}


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY,name TEXT NOT NULL,
          token_hash TEXT UNIQUE NOT NULL,role TEXT NOT NULL,revoked INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS pairing(code_hash TEXT PRIMARY KEY,expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,device TEXT NOT NULL,
          request_id TEXT NOT NULL,request_hash TEXT NOT NULL,project TEXT NOT NULL,
          action TEXT NOT NULL,prompt TEXT NOT NULL,status TEXT NOT NULL,
          thread_id TEXT,turn_id TEXT,workspace TEXT,created REAL NOT NULL,
          UNIQUE(device,request_id));
        CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,
          task_id TEXT NOT NULL,kind TEXT NOT NULL,data TEXT NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY AUTOINCREMENT,
          body TEXT NOT NULL,previous TEXT NOT NULL,hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS media(id TEXT PRIMARY KEY,device TEXT NOT NULL,
          size INTEGER NOT NULL,sha256 TEXT NOT NULL,mime TEXT NOT NULL,
          received INTEGER DEFAULT 0,complete INTEGER DEFAULT 0);
        """)
        self.db.commit()
        if "parent_task_id" not in {r[1] for r in self.db.execute("PRAGMA table_info(tasks)")}:
            self.db.execute("ALTER TABLE tasks ADD COLUMN parent_task_id TEXT")
            self.db.commit()
        if "request_id" not in {r[1] for r in self.db.execute("PRAGMA table_info(media)")}:
            self.db.execute("ALTER TABLE media ADD COLUMN request_id TEXT")
            self.db.commit()
        self.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS media_request ON media(device,request_id) WHERE request_id IS NOT NULL")
        self.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS active_workspace ON tasks(workspace) WHERE workspace IS NOT NULL AND status IN ('preparing','running','cancel_requested')")

    def close(self):
        self.db.close()

    def add_device(self, name: str, role="device") -> tuple[str, str]:
        device_id, token = str(uuid.uuid4()), secrets.token_urlsafe(32)
        with self.db:
            self.db.execute("INSERT INTO devices(id,name,token_hash,role) VALUES(?,?,?,?)",
                            (device_id, name[:80], digest(token), role))
            self.audit("device.created", {"id": device_id, "role": role})
        return device_id, token

    def authenticate(self, token: str):
        row = self.db.execute("SELECT * FROM devices WHERE token_hash=? AND revoked=0",
                              (digest(token),)).fetchone()
        return dict(row) if row else None

    def revoke(self, device_id: str):
        with self.db:
            self.db.execute("UPDATE devices SET revoked=1 WHERE id=?", (device_id,))
            self.audit("device.revoked", {"id": device_id})

    def pairing_code(self, ttl=300) -> str:
        code = secrets.token_urlsafe(12)  # 96 bits, displayed out of band; not a six-digit PIN.
        with self.db:
            self.db.execute("DELETE FROM pairing")  # only the latest code is valid
            self.db.execute("INSERT INTO pairing VALUES(?,?)", (digest(code), time.time()+ttl))
        return code

    def pair(self, code: str, name: str):
        with self.db:
            row = self.db.execute("SELECT * FROM pairing WHERE code_hash=?", (digest(code),)).fetchone()
            if not row or row["expires"] < time.time():
                raise ValueError("invalid_or_expired_pairing")
            self.db.execute("DELETE FROM pairing WHERE code_hash=?", (digest(code),))
            return self.add_device(name)

    def audit(self, kind: str, data: dict):
        # Called inside a transaction by all mutations. This is tamper evidence, not WORM storage.
        last = self.db.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        previous = last[0] if last else "0"*64
        body = canonical({"kind": kind, "data": data, "time": time.time()})
        checksum = digest(previous + body)
        self.db.execute("INSERT INTO audit(body,previous,hash) VALUES(?,?,?)", (body, previous, checksum))

    def verify_audit(self) -> bool:
        previous = "0"*64
        for row in self.db.execute("SELECT * FROM audit ORDER BY seq"):
            if not hmac.compare_digest(row["previous"], previous):
                return False
            if not hmac.compare_digest(row["hash"], digest(previous+row["body"])):
                return False
            previous = row["hash"]
        return True

    def task(self, task_id: str):
        row = self.db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            raise KeyError("task_not_found")
        return dict(row)

    def create_task(self, device: str, request_id: str, project: str, action: str, prompt: str, parent_task_id=None):
        fingerprint = digest(canonical([project, action, prompt, parent_task_id]))
        old = self.db.execute("SELECT * FROM tasks WHERE device=? AND request_id=?", (device, request_id)).fetchone()
        if old:
            if old["request_hash"] != fingerprint:
                raise ValueError("idempotency_conflict")
            return dict(old), False
        task_id = str(uuid.uuid4())
        workspace = None
        if parent_task_id:
            parent = self.task(parent_task_id)
            if parent["project"] != project or parent["status"] != "completed" or not parent["workspace"]:
                raise ValueError("parent_task_not_resumable")
            workspace = parent["workspace"]
        with self.db:
            self.db.execute("""INSERT INTO tasks(id,device,request_id,request_hash,project,action,prompt,status,created,parent_task_id,workspace)
             VALUES(?,?,?,?,?,?,?,'pending',?,?,?)""", (task_id, device, request_id, fingerprint, project, action, prompt, time.time(),parent_task_id,workspace))
            self._event(task_id, "status", {"status": "pending", "stage": "awaiting_desktop_approval"})
            self.audit("task.requested", {"id": task_id, "project": project, "action": action, "prompt_hash": digest(prompt)})
        return self.task(task_id), True

    def _event(self, task_id, kind, data):
        self.db.execute("INSERT INTO events(task_id,kind,data,created) VALUES(?,?,?,?)",
                        (task_id, kind, canonical(data), time.time()))

    def event(self, task_id, kind, data):
        with self.db:
            self._event(task_id, kind, data)

    def transition(self, task_id, status, **fields):
        current = self.task(task_id)["status"]
        if status == current:
            return
        if status not in TRANSITIONS.get(current, set()):
            raise ValueError(f"invalid_transition:{current}:{status}")
        with self.db:
            self.db.execute("UPDATE tasks SET status=? WHERE id=?", (status, task_id))
            self._event(task_id, "status", {"status": status, **fields})
            self.audit("task.status", {"id": task_id, "from": current, "to": status})

    def attach(self, task_id, *, thread_id=None, turn_id=None, workspace=None):
        with self.db:
            for key, value in [("thread_id", thread_id), ("turn_id", turn_id), ("workspace", workspace)]:
                if value is not None:
                    self.db.execute(f"UPDATE tasks SET {key}=? WHERE id=?", (value, task_id))

    def events(self, after=0, limit=200, task_id=None):
        if task_id:
            rows = self.db.execute("SELECT * FROM events WHERE seq>? AND task_id=? ORDER BY seq LIMIT ?", (after, task_id, limit))
        else:
            rows = self.db.execute("SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT ?", (after, limit))
        return [{**dict(row), "data": json.loads(row["data"])} for row in rows]

    def recover(self):
        ids = [r[0] for r in self.db.execute("SELECT id FROM tasks WHERE status IN ('running','preparing','cancel_requested')")]
        for task_id in ids:
            self.transition(task_id, "unknown", stage="desktop_restarted_no_automatic_replay")
