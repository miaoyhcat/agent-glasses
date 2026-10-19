# Security boundary / v0.2

[中文](SECURITY.md) · **English**

This is a single-owner engineering prototype, not a public multi-tenant service. There is
currently **no penetration test, no Docker-isolation audit and no Windows or hardware
security certification** behind it.

## What is implemented and tested

- HTTPS ≥ TLS 1.2, full certificate fingerprint verification, hostname checks, one-time
  high-entropy pairing and revocable device tokens. The glasses never store account API keys.
- Only the **local operator token** can approve a task. The phone may name an already
  authorized project ID, one of inspect/fix/test, and free text — it cannot pass host
  commands, directories, Docker arguments or an upstream model URL.
- The original project is never mounted. The copy excludes common credential directories,
  `.codex`/`.claude`/MCP configuration, environment files and caches, and rejects symlinks
  and hard links. It cannot recognize arbitrary secrets on its own; the owner still has to
  audit what is authorized.
- Request shapes are checked against the installed version. Command and file approvals
  default to deny; permission requests are granted an empty set; unknown RPC requests are
  refused. Public events contain neither reasoning nor raw tool output.
- Model API calls are separately enabled by `allow_model_api` on the computer, and each
  task still needs local confirmation of data and cost. Vision and transcription are
  separate features, off by default, consented per call.

## Credentials and the new network boundary

v0.2 removes v0.1's `worker_auth_file` mount. Model keys exist only in the computer's
process; the container holds a short-lived task token. Docker arguments include
`--network=none`, a read-only root, a non-privileged UID, dropped capabilities, no
privilege escalation and resource limits; only the copy and a separate session directory
are mounted.

The fixed HTTP forwarder inside the worker binds only its own `127.0.0.1:9041`. Official
Codex requests cross a dedicated stdio channel to the computer's model broker, and the
computer only calls the fixed official Responses endpoint. There is no host model HTTP
port or Unix socket, and no Docker socket, home directory or account authentication is
mounted. The acknowledged chunk stream is bounded and keeps the cancel RPC serviceable.

The broker pins the model, allows at most 8 requests per task, 256 KiB of input per
request, 1 MiB cumulative input, 4096 output tokens per request and 1 MiB per response.
It forces no background execution, does not store cloud responses, defaults the service
tier, and does not follow redirects. Hosted search/execution/MCP tools, other servers'
conversation/prompt/previous-response references, and external image/file references are
refused. Only text code tasks and local functions/custom tools are supported here; vision
goes through the explicit consent flow.

These are **request and resource limits, not a limit on dollars**. Pricing, input tokens
and context changes affect the real bill. A malicious worker that reads the task token can
still consume this task's budget; it cannot obtain the long-lived model key or choose an
arbitrary upstream URL. Cancelling closes the model stream and explicitly cleans up this
task's container under a random unique name; whether cleanup was confirmed is recorded as
a separate event.

The related host tests use real subprocesses, TCP and stream/ACK behaviour, but the
upstream is an explicit test peer. No Docker network or host file boundary is claimed to
be accepted on that basis. Review the image source and pin the actual build digest; do not
run an unknown image.

## State and remaining risk

`completed` comes from a real `turn/completed` and means the agent's turn ended — it does
not prove the fix is correct. `verification_status` defaults to `not_verified`. A command
exiting 0 is not automatically all tests passing. On disconnect or a post-send timeout
without completion evidence the state stays `unknown`, and a restart does not replay the
task.

The database audit chain detects tampering; it cannot stop someone with write access to
the state directory from rewriting all history. The authorized source directory must be
quiescent while it is copied; this is not a race-safe copier against a local malicious
process with the same privileges. Old-version sessions must not be treated as new-broker
sessions — after upgrading, check pending tasks and open a new session rather than deleting
old media or authentication material.

A real target still needs testing for: container stop, tool network access, access to the
original project and host files, credential unreachability, limits, disconnection and
recovery. Windows Docker Desktop/WSL2, macOS volume semantics and ACLs remain unverified.
Remote access should use a personal VPN private network while keeping TLS and binding;
never expose Docker or the App Server port publicly.

The glasses have no secure boot, no flash encryption and no signed OTA. The camera
interlock test board does not solve reverse power feed through IO or external occlusion.
Battery, optical, thermal and RF safety must be verified on hardware; D0 is used on an
off-body bench only.

## Follow-up tasks, file types and acceptance isolation

A follow-up task may start only after the original worker confirms cleanup and no runner
is active on the same copy. The whole copy is checked before any permission is assigned:
symlinks (including Windows reparse points), hard links and special files such as devices
and FIFOs are refused. On POSIX the tree is opened with `O_NOFOLLOW`, the inode is
verified, then the descriptor is `fchmod`-ed; the target of a model-created link is never
`chmod`-ed. Model-created links currently cause the follow-up task to be refused — review
locally and make a fresh safe copy. The premise remains that no host owner modifies the
tree concurrently.

Independent acceptance of the public discount example copies only the safe AST modules and
the trusted original tests, refuses model-modified tests, and excludes every other file.
Python isolated mode, a separate cache and a fixed test entry prevent a forged
`unittest.py` or stale bytecode from manufacturing a pass. The acceptance container also
has a unique task name and explicit cleanup. It is a fixed-example acceptance, **not a
proof that an arbitrary project is correct**.

**Disk quota is still open:** the bind-mounted copy has no verified hard filesystem quota.
The 200 MiB / 10,000-file check runs only while preparing a task and cannot stop a running
worker from filling the host disk. Before production use, run continuous-write,
capacity-exhaustion and cleanup trials on a dedicated volume or VM with a quota. Do not
treat memory or CPU limits as disk isolation.
