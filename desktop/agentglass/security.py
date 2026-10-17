"""TLS bootstrap and a conservative project snapshot boundary."""
from __future__ import annotations

import datetime
import hashlib
import ipaddress
import json
import os
import shutil
import ssl
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


def private_file(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def make_tls(directory: Path, hosts: list[str]):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AgentGlass local bridge")])
    san = []
    for host in dict.fromkeys(["localhost", "127.0.0.1", "::1", *hosts]):
        try:
            san.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            san.append(x509.DNSName(host))
    now = datetime.datetime.now(datetime.timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now-datetime.timedelta(minutes=5)).not_valid_after(now+datetime.timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256()))
    private_file(directory/"server.key", key.private_bytes(serialization.Encoding.PEM,
                     serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    private_file(directory/"server.pem", certificate.public_bytes(serialization.Encoding.PEM))
    return hashlib.sha256(certificate.public_bytes(serialization.Encoding.DER)).hexdigest()


def tls_context(directory: Path):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(directory/"server.pem", directory/"server.key")
    return ctx


EXCLUDED = {".git", ".env", ".ssh", ".aws", ".azure", ".codex", ".claude", ".kube", ".gnupg",
            ".npmrc", ".pypirc", ".netrc", ".mcp.json", "node_modules", ".venv", "__pycache__"}


def snapshot_project(root: Path, destination: Path, *, max_bytes=100*1024*1024, max_files=5000):
    """Copy regular files only. Never mount the original writable project into an agent.

    Does not identify arbitrary secrets; the operator must review the authorized tree.
    A separate container boundary and Codex sandbox are additionally required.
    """
    root = root.resolve(strict=True)
    if not root.is_dir() or destination.exists():
        raise ValueError("invalid_snapshot_destination")
    if destination.resolve().is_relative_to(root):
        raise ValueError("snapshot_must_be_outside_project")
    candidates, total = [], 0
    for current, dirs, files in os.walk(root, followlinks=False):
        base = Path(current)
        for entry in dirs+files:
            if (base/entry).is_symlink():
                raise ValueError("symlink_in_project")
        dirs[:] = [d for d in dirs if d not in EXCLUDED]
        for filename in files:
            path = base/filename
            if filename in EXCLUDED or filename.startswith(".env."):
                continue
            if not path.is_file() or path.stat().st_nlink > 1:
                raise ValueError("nonregular_or_hardlinked_file")
            total += path.stat().st_size
            candidates.append(path)
            if total > max_bytes or len(candidates) > max_files:
                raise ValueError("snapshot_budget_exceeded")
    destination.mkdir(parents=True, mode=0o700)
    try:
        for src in candidates:
            # Recheck immediately before copy. The project must not be mutated during snapshot.
            if src.is_symlink() or not src.resolve().is_relative_to(root):
                raise ValueError("project_changed_during_snapshot")
            dst = destination/src.relative_to(root)
            dst.parent.mkdir(parents=True, exist_ok=True)
            with src.open("rb") as inf, dst.open("xb") as outf:
                shutil.copyfileobj(inf, outf)
        return {"files": len(candidates), "bytes": total}
    except BaseException:
        shutil.rmtree(destination)
        raise


def load_config(directory: Path):
    data = json.loads((directory/"config.json").read_text())
    projects = data.get("projects", {})
    if not isinstance(projects, dict):
        raise ValueError("invalid_projects")
    for name, project in projects.items():
        if not name or not isinstance(project, dict) or not Path(project["path"]).is_absolute():
            raise ValueError("project_requires_absolute_path")
    return data


def prepare_worker_tree(workspace: Path, *, writable: bool, max_bytes=200*1024*1024, max_files=10000):
    """Validate a quiescent disposable tree before assigning container UID access.

    A completed worker must be stopped before this is called. Refuse links,
    devices, FIFOs and hardlinks; never chmod through a model-created link.
    This is not a filesystem quota or protection against a concurrent host owner.
    """
    import stat
    workspace = Path(workspace).absolute()
    root_stat = workspace.lstat()
    if not stat.S_ISDIR(root_stat.st_mode) or getattr(root_stat,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0):
        raise ValueError('unsafe_worker_tree')
    entries=[(workspace,root_stat)];total=0;files=0
    for current, directories, names in os.walk(workspace, followlinks=False):
        for name in directories+names:
            path=Path(current)/name;info=path.lstat()
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)) or getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0):
                raise ValueError('unsafe_worker_tree')
            if stat.S_ISREG(info.st_mode):
                if info.st_nlink!=1:raise ValueError('unsafe_worker_hardlink')
                files+=1;total+=info.st_size
                if files>max_files or total>max_bytes:raise ValueError('worker_tree_budget_exceeded')
            entries.append((path,info))
    if os.name!='nt':
        if not hasattr(os,'O_NOFOLLOW'):raise ValueError('nofollow_permissions_unavailable')
        for path,before in entries:
            flags=os.O_RDONLY|os.O_NOFOLLOW
            is_dir=stat.S_ISDIR(before.st_mode)
            if is_dir:flags|=os.O_DIRECTORY
            fd=os.open(path,flags)
            try:
                after=os.fstat(fd)
                if (after.st_dev,after.st_ino)!=(before.st_dev,before.st_ino):raise ValueError('worker_tree_changed')
                if not is_dir and after.st_nlink!=1:raise ValueError('unsafe_worker_hardlink')
                os.fchmod(fd,(0o777 if writable else 0o755) if is_dir else (0o666 if writable else 0o644))
            finally:os.close(fd)
    return {'files':files,'bytes':total}
