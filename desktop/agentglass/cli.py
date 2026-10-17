from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import os
import ssl
import subprocess
from pathlib import Path

from aiohttp import ClientSession, web
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from .security import make_tls, private_file, tls_context, load_config
from .server import Bridge
from .store import Store


def secure_directory(directory):
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    directory.chmod(0o700)
    if os.name == "nt":
        user = subprocess.check_output(["whoami"], text=True).strip()
        subprocess.run(["icacls", str(directory), "/inheritance:r", "/grant:r", f"{user}:(OI)(CI)F"], check=True,
                       stdout=subprocess.DEVNULL)


def initialize(directory, hosts, name="AgentGlass PC"):
    if not isinstance(name,str) or not 1 <= len(name) <= 64 or any(ord(c)<32 for c in name):
        raise ValueError("invalid_computer_name")
    if (directory/"config.json").exists():
        raise ValueError("already_initialized")
    secure_directory(directory)
    fingerprint = make_tls(directory, hosts)
    store = Store(directory/"state.db")
    _, token = store.add_device("Local desktop operator", "operator")
    store.close()
    private_file(directory/"operator.token", token.encode())
    private_file(directory/"config.json", json.dumps({
        "listen": "127.0.0.1", "port": 9443, "projects": {}, "computer_name": name,
        "runtime_isolation": "disabled", "worker_image": "agentglass-codex:0.162.1-broker1", "codex_model": None,
        "allow_paid_cloud": False,"allow_model_api":False
    }, indent=2).encode())
    return {"certificate_sha256": fingerprint, "state_directory": str(directory)}


async def operator_request(directory, method, path, payload=None):
    config = load_config(directory)
    ctx = ssl.create_default_context(cafile=str(directory/"server.pem"))
    token = (directory/"operator.token").read_text().strip()
    async with ClientSession(headers={"Authorization": "Bearer "+token}) as session:
        async with session.request(method, f"https://127.0.0.1:{config.get('port',9443)}"+path, json=payload, ssl=ctx) as r:
            result = await r.json()
            if r.status >= 400:
                raise ValueError(f"http_{r.status}:{result.get('error')}")
            return result


def main():
    parser = argparse.ArgumentParser(prog="agentglass")
    parser.add_argument("--state", type=Path, default=Path.cwd()/"runtime")
    subs = parser.add_subparsers(dest="command", required=True)
    init = subs.add_parser("init"); init.add_argument("--host", action="append", default=[])
    init.add_argument("--name", default="AgentGlass PC")
    project = subs.add_parser("project-add"); project.add_argument("id"); project.add_argument("path", type=Path)
    project.add_argument("--allow-snapshot-writes", action="store_true")
    pair = subs.add_parser("pair-code"); pair.add_argument("--ttl", type=int, default=300)
    revoke = subs.add_parser("revoke"); revoke.add_argument("device_id")
    serve = subs.add_parser("serve"); serve.add_argument("--simulate", action="store_true")
    serve.add_argument("--listen", default=None)
    subs.add_parser("pending")
    decision = subs.add_parser("decide"); decision.add_argument("task_id"); decision.add_argument("decision", choices=["approve", "reject"])
    decision.add_argument("--acknowledge-snapshot-and-provider", action="store_true")
    subs.add_parser("audit-check")
    subs.add_parser("fingerprint")
    subs.add_parser("doctor")
    args = parser.parse_args()
    directory = args.state.resolve()
    try:
        if args.command == "init":
            print(json.dumps(initialize(directory, args.host, args.name), indent=2))
        elif args.command == "project-add":
            import re
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", args.id) or not args.path.resolve().is_dir():
                raise ValueError("invalid_project")
            config = load_config(directory)
            config["projects"][args.id] = {"path": str(args.path.resolve()), "allow_write": args.allow_snapshot_writes}
            (directory/"config.json").write_text(json.dumps(config, indent=2))
            print("Project registered. Restart the bridge after configuration changes.")
        elif args.command == "serve":
            config = load_config(directory)
            bridge = Bridge(directory, config, simulate=args.simulate)
            print("SIMULATOR: no Codex execution" if args.simulate else "Codex mode: each task requires local launch approval")
            web.run_app(bridge.app(), host=args.listen or config.get("listen", "127.0.0.1"), port=config.get("port", 9443),
                        ssl_context=tls_context(directory), access_log=None)
        elif args.command in {"pair-code", "revoke", "audit-check"}:
            store = Store(directory/"state.db")
            try:
                if args.command == "pair-code":
                    if not 30 <= args.ttl <= 600:
                        raise ValueError("ttl_out_of_range")
                    print(store.pairing_code(args.ttl))
                elif args.command == "revoke":
                    store.revoke(args.device_id); print("Revoked")
                else:
                    valid = store.verify_audit(); print("PASS" if valid else "FAIL")
                    if not valid:
                        raise SystemExit(1)
            finally:
                store.close()
        elif args.command == "fingerprint":
            cert = x509.load_pem_x509_certificate((directory/"server.pem").read_bytes())
            print(hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest())
        elif args.command == 'doctor':
            from .doctor import readiness
            result=readiness(load_config(directory));print(json.dumps(result,indent=2))
            if not result['launch_prerequisites_present']:raise SystemExit(1)
        elif args.command == "pending":
            print(json.dumps(asyncio.run(operator_request(directory, "GET", "/v1/operator/pending")), ensure_ascii=False, indent=2))
        elif args.command == "decide":
            print(json.dumps(asyncio.run(operator_request(directory, "POST", f"/v1/operator/tasks/{args.task_id}/decision", {
                "decision": args.decision, "acknowledge_snapshot_and_provider": args.acknowledge_snapshot_and_provider
            })), indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"AgentGlass: {exc}\n")


if __name__ == "__main__":
    main()
