"""Versioned REST and BLE contracts; see agent-integration/protocols/protocol.md."""
import hashlib
import hmac
import json
import re

VERSION = 1
ACTIONS = {"inspect", "fix", "test"}
MAX_PROMPT = 4000
MAX_BLE_FRAME = 4096
OPS = {"hud", "photo", "record", "audio", "speaker_start", "speaker_data", "speaker_play", "list", "read", "ack", "sleep", "status"}


def task_request(body):
    if not isinstance(body, dict) or body.get("v") != VERSION:
        raise ValueError("unsupported_protocol")
    if set(body)-{"v", "request_id", "project", "action", "prompt", "parent_task_id"}:
        raise ValueError("unknown_field")
    for name in ["request_id", "project", "action", "prompt"]:
        if not isinstance(body.get(name), str):
            raise ValueError("missing_or_invalid_field")
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", body["request_id"]):
        raise ValueError("invalid_request_id")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", body["project"]):
        raise ValueError("invalid_project")
    if body["action"] not in ACTIONS:
        raise ValueError("unsupported_action")
    if not 1 <= len(body["prompt"].strip()) <= MAX_PROMPT:
        raise ValueError("invalid_prompt")
    if body.get("parent_task_id") is not None:
        import uuid
        if not isinstance(body["parent_task_id"], str):
            raise ValueError("invalid_parent_task")
        uuid.UUID(body["parent_task_id"])
    return body


def ble_sign(key: bytes, session: str, seq: int, body: str):
    if seq < 1 or not re.fullmatch(r"[0-9a-f]{32}", session):
        raise ValueError("bad_session_or_sequence")
    message = f"{session}\n{seq}\n{body}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def ble_packet(key: bytes, session: str, seq: int, op: str, **args):
    if len(key) != 32 or op not in OPS:
        raise ValueError("bad_key_or_operation")
    body = json.dumps({"op": op, **args}, ensure_ascii=True, separators=(",", ":"))
    packet = json.dumps({"v": 1, "seq": seq, "body": body, "mac": ble_sign(key, session, seq, body)}, separators=(",", ":"))
    if len(packet.encode()) >= MAX_BLE_FRAME:
        raise ValueError("frame_too_large")
    return packet+"\n"


def ble_verify(key, session, last_sequence, packet):
    if len(packet.encode()) >= MAX_BLE_FRAME:
        raise ValueError("frame_too_large")
    message = json.loads(packet)
    if message.get("v") != 1 or type(message.get("seq")) is not int or message["seq"] <= last_sequence:
        raise ValueError("replay_or_version")
    mac = ble_sign(key, session, message["seq"], message["body"])
    if not hmac.compare_digest(mac, message.get("mac", "")):
        raise ValueError("authentication_failed")
    body = json.loads(message["body"])
    if body.get("op") not in OPS:
        raise ValueError("unsupported_operation")
    return message["seq"], body
