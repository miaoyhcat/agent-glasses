# Desktop connector

[中文](README.md) · **English**

Python 3.11+, an aiohttp HTTPS service, and SQLite WAL for persistent state; the CLI performs
local approval. The browser workbench is a same-origin admin UI served by this program, not a
separately deployed website. Software tests run on Linux; Windows/macOS installation, file
ACLs, Docker volumes and device connection still need real-hardware acceptance.

`codexglasses init` creates a private state directory, a TLS certificate and a separate
operator token. On Windows, initialization uses `icacls` to remove inherited permissions and
stops if that fails. The phone only ever receives a device token; the operator token never
goes to the phone, the glasses or a URL.

Real mode requires `runtime_isolation="docker"`; otherwise tasks fail closed. The default
configuration does not turn the phone into a remote shell on the host. Directory authorization
must be configured locally, and only the three high-level actions inspect/fix/test are
accepted. Every launch and every follow-up needs local approval of the project copy and of
model-service data handling. Configuration and real acceptance are covered in
`agent-integration/codex/README.md`.

Media lives in the private state directory, at most 64 MiB per file with a 512 MiB total
reservation; nothing is cleaned up automatically without confirmation. When disk space must be
reclaimed, the local operator backs up and then clears completed media and work copies. Do not
edit the database directly while the service is running.

After a disconnect the client resumes with its cursor; a service restart marks in-flight tasks
`unknown`. `unknown` is not a licence to retry blindly after a failure — first check the real
worker and session, to avoid duplicate model cost, duplicate edits or a wrong merge. There is
currently no automatic orchestration that resumes an active turn in the background.
