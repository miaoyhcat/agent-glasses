"""Construct an isolated Codex worker; never accept Docker arguments from a phone."""
from pathlib import Path
import re
import uuid


def container_command(config, workspace: Path, *, writable=False, session_directory=None):
    if config.get("runtime_isolation") != "docker":
        raise ValueError("real_codex_requires_docker_isolation")
    image = config.get("worker_image", "agentglass-codex:0.162.1-broker1")
    if not isinstance(image, str) or not re.fullmatch(r"[a-zA-Z0-9_./:@-]{1,200}", image):
        raise ValueError("invalid_worker_image")
    workspace = workspace.resolve(strict=True)
    if session_directory is None:
        session_directory = workspace.parent/(workspace.name+"-codex-session")
    session_directory = Path(session_directory).resolve()
    session_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (session_directory/'auth.json').exists():raise ValueError('legacy_auth_file_in_worker_session_refused')
    if any("," in str(path) for path in [workspace,session_directory]):
        raise ValueError("docker_mount_path_contains_comma")
    # No Docker socket, host root, home directory, SSH agent, or original project mount.
    return ["docker", "run", "--rm", "--pull=never", "--network=none", "--name", "agentglass-"+uuid.uuid4().hex,
        "--label", "dev.agentglass.temporary-worker=true", "-i", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--pids-limit=128", "--memory=2g", "--cpus=2",
        "--user=10001:10001", "--tmpfs=/tmp:rw,nosuid,nodev,size=256m",
        "--mount", f"type=bind,source={session_directory},target=/home/agent/.codex",
        "--mount", f"type=bind,source={workspace},target=/workspace"+("" if writable else ",readonly"),
        "--env", "AGENTGLASS_PROXY_TOKEN",
        "--workdir=/workspace", image]
