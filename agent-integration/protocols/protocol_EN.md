# CodexGlasses Protocol 1

[中文](protocol.md) · **English**

This is the project's own accessory protocol; it does not impersonate the Codex API. The
desktop calls Codex through the official App Server's JSONL stdio.

## HTTPS control plane

Every route requires TLS ≥ 1.2. Android pins the whole certificate by the DER SHA-256
fingerprint verified out of band; the CLI uses local certificate trust. Replacing the
certificate requires re-verifying the fingerprint. Except for `/health`, the index page and
`/v1/pair`, a request must carry `Authorization: Bearer <256-bit-token>`. Tokens in URLs are
forbidden. No raw Codex port is exposed publicly.

| Route | Content / return |
|---|---|
| POST /v1/pair | `{code,name}`; single-use, 300-second code; returns a device token |
| GET /v1/projects | Locally configured project IDs; never reveals absolute paths |
| POST /v1/tasks | `{v:1,request_id,project,action,prompt,parent_task_id?}`; action=inspect/fix/test |
| GET /v1/tasks | Latest 100 tasks, without source files or raw logs |
| GET /v1/tasks/{id} | Real task state, actual thread_id/turn_id, stored last_summary, progress_text/progress_event_seq derived from real events; verification_status defaults to not_verified |
| POST /v1/tasks/{id}/cancel | Request an interrupt; only an official completion event marks it cancelled |
| GET /v1/events?after=N | Monotonic seq, at most 200 records; returns a cursor; a reconnect resumes from the last cursor |
| GET /v1/operator/pending | Loopback only + separate operator token; includes the full instruction awaiting approval |
| POST /v1/operator/tasks/{id}/decision | Local approve/reject; approval must acknowledge the copy and model-service data handling |
| POST /v1/operator/tasks/{id}/voice-decision | Voice approval: transcript → fixed phrase → the same approval path; **off by default** |
| POST /v1/media | `{size,sha256,mime,request_id?}`; idempotent per device; returns ID/offset/complete |
| GET /v1/media/{id} | size/received/complete |
| PUT /v1/media/{id}/chunks?offset=N | Sequential raw chunk, ≤256 KiB; an exact repeat may be resent safely |
| POST /v1/media/{id}/commit | Commits once length and SHA-256 match; returns the full state |
| POST /v1/ai | Committed media_id, kind=transcribe/vision, question, consent_upload_and_cost=true; cloud services are refused by default |

### Voice approval

`POST /v1/operator/tasks/{id}/voice-decision`, body:
`{transcript, acknowledge_snapshot_and_provider}`.

- **Off by default.** Enable it by writing `"allow_voice_approval": true` in the desktop
  `config.json`. While disabled it returns `400 {"error":"voice_approval_disabled"}` and the
  task state does not change.
- Only fixed phrases are accepted (`批准` / `确认批准` / `拒绝` / `不批准` and a few English
  equivalents), and **negation wins**: "不批准" (do not approve) contains "批准" (approve),
  so negation is checked first. Reversing that order is a false approval.
- Unrecognized input (empty, too long, ambiguous) returns
  `400 {"error":"voice_not_recognized"}` and **changes no state at all**.
- A successful approval takes exactly the same path as a click: the same
  `acknowledge_snapshot_and_provider` requirement, the same concurrency limit, copy-busy and
  parent-cleanup checks. Only the entry point differs.
- The audit log stores only the matched phrase (a `voice_decision` event), **never the whole
  transcript** — it may contain speech the user did not mean to publish.

`request_id` is idempotent within one device. A repeated ID with identical parameters returns
the original task; different parameters return 400 and cannot start a second run. Tasks are
not replayed after a disconnect. HTTP 401 = re-pair or the token was revoked; 403 =
insufficient permission; 429 = back off and retry; any other 400 = fix the request and retry.
This first implementation targets one personal owner; every paired device shares that owner's
task history — **it is not a multi-tenant service**. Media resources are limited to the
uploading device.

`parent_task_id` accepts only completed tasks of the same project; each follow-up still needs
local approval and reuses the original copy and the real session. `/v1/ai` is not an
idempotent paid endpoint and is never retried automatically; it must be enabled locally and
consented per request, with a default cap of 20 calls per day.

State flow: pending → preparing → running → completed/failed/cancelled. `cancel_requested`
is a request state; a service restart or missing completion evidence yields `unknown`.
Completion is never inferred from elapsed time. The UI shows no guessed percentages and never
calls exit code 0 "all tests passed". Externally exposed: public plan, item type/lifecycle/exit
code, and agentMessage. All reasoning, arbitrary tool arguments and raw tool output are
filtered out.

## Glasses BLE / USB framing

BLE service `6e400001-b5a3-f393-e0a9-e50e24dcca9e`, RX write `...0002...`, TX notify
`...0003...`. USB carries the same LF-framed messages; USB is for debugging and first-time
local configuration only. Each message is < 4096 bytes; BLE requests MTU 247; data is sliced
into min(180, actual MTU − 3) byte chunks, falling back to 20 bytes if negotiation fails, and
only an LF executes a command — an over-long frame clears the buffer. The 32-byte HMAC key is
written once over a trusted USB serial port. The application-layer HMAC authenticates
commands but provides no link confidentiality; a BLE device must complete encrypted pairing
with a displayed passkey first, and sensitive media operations stay closed until it is bound.

A powered device sends `{v:1,type:"hello",session:"<32 lowercase hex>",...}`. The session is
random per boot, and seq increases strictly within that session. The host builds the **exact
body string** and computes:

```
hex(HMAC-SHA256(key, utf8(session + "\n" + decimal(seq) + "\n" + body)))
```

Envelope `{v:1,seq:1,body:"{\"op\":\"status\"}",mac:"..."}`, terminated by LF. A failed
authentication does not advance seq. An authenticated command with invalid parameters still
consumes seq, which prevents replay. There is no arbitrary Lua/shell/file-path execution
operation.

| op | Function |
|---|---|
| hud | `bitmap`: 128×64, MSB-first, a 1024-byte 1-bit bitmap in Base64; the phone rasterizes the Chinese font |
| photo | Captures a JPEG only after the front physical switch and the LED electrical gate both pass; written locally before any notification |
| record | `seconds`=1..15, a JPEG frame container, not H.264; failures and full storage are reported explicitly |
| audio | `seconds`=1..8, local 16 kHz PCM WAV; offline natural-language ASR is not claimed |
| speaker_start / speaker_data / speaker_play | At most 256000 bytes of 16 kHz PCM16 mono; length and SHA-256 declared first, sequential 384-byte chunks, the device returns speaker_ack.offset per chunk, playback after full verification; the buffer is dropped after 30 s without a new chunk |
| list | Metadata of locally unacknowledged media |
| read | Only a 26-character lowercase Base32 or legacy 1–10 digit ID, plus offset; each reply carries ≤384 bytes of Base64 and the offset |
| ack | ID + SHA-256; the host persists and verifies before confirming, and only then may local cache be deleted |
| sleep | Display off, camera off, sleep; the physical button wakes it |
| status | Current power/cache/camera state; an unknown battery level is null, never a fabricated percentage |

`status` may carry `unix` and `tz_minutes`; time is set after authentication and out-of-range
values are refused. Short audio is played after the whole fragment is received — it is not a
proven low-latency continuous stream.

The firmware's actual support and porting status are in `firmware/README.md`. This protocol
does not present unfinished optical drivers as implemented.

## v0.2 reliability and real-model boundary

Android persists a random `upload_request_id` before the first media initialization request;
the HTTP field is named `request_id`. Same device + same ID + same content returns the
original media and its received offset; a parameter conflict is refused and other devices
cannot query it. Device BLE media IDs and desktop UUIDs are different namespaces, and the
phone stores the mapping. The phone uses a temporary file, file fsync, atomic rename,
directory sync and SHA-256 before sending the device ack; a power-loss test has not been run.

`completed` only means the official `turn/completed` arrived. It does not prove the code fix
is correct; external `verification_status` defaults to `not_verified`, and neither agent text
nor tool output can promote it. An independent acceptance script runs the fixed tests
separately and keeps the real exit code. `worker_cleanup_confirmed` is true only when the
container removal command actually ran and succeeded.

The phone uses single-flight for polling, latest-only for the HUD, and a separate bounded
queue for cancellation; after switching target computers, responses from the old connection
cannot be committed to the new one. The UI is still a foreground engineering prototype:
background service and full BLE reconnect acceptance are not done.

### Desktop to isolated worker (not a glasses protocol)

The container is fixed to `--network=none`. The official Codex App Server's JSONL is wrapped
by a fixed Python entry point as `channel=codex`; only frames returning to the desktop model
proxy may use `channel=model`. A short-lived per-task token, request count/size/output limits
and the model allow-list are all enforced by the desktop. The real API key exists only on the
desktop and is never written into the container. The proxy has no host TCP listening port and
pins the upstream to the OpenAI HTTPS Responses endpoint; responses are Base64-chunked with
sequence numbers and the worker ACKs after consuming them, which prevents unbounded
buffering.

The worker's internal loopback HTTP is an adapter for the Codex provider and is not reachable
from the phone. The stdio envelope is not part of the official Codex protocol; official
`initialize/thread/start/turn/start/turn/completed` keep their original structure. See the
[integration guide](../codex/README.md) and [security boundary](../../SECURITY.md). The
container rules have software tests; real Docker isolation acceptance has not been run.

Local approval of a follow-up task is refused while the old worker has not exited, cleanup is
unconfirmed, or a runner is still active on the same copy; the public response is a generic
400 that does not leak host file details. Copies containing links, hard links or special files
never enter permission reassignment.
