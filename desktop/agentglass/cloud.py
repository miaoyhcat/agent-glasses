"""Opt-in official API calls, independent of Codex subscription credentials."""
import base64
import io
import os
import wave

from aiohttp import ClientSession, ClientTimeout, FormData


class CloudAI:
    def __init__(self, config):
        self.config = config

    async def analyze(self, kind, content, mime, question):
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("cloud_api_key_not_configured")
        headers = {"Authorization": "Bearer "+key}
        async with ClientSession(headers=headers, timeout=ClientTimeout(total=60)) as session:
            if kind == "transcribe":
                if mime != "audio/wav":
                    raise ValueError("wav_required")
                with wave.open(io.BytesIO(content)) as audio:
                    if audio.getnframes()/audio.getframerate() > 10 or audio.getsampwidth() != 2:
                        raise ValueError("short_pcm16_wav_required")
                model = self.config.get("transcription_model", "gpt-4o-mini-transcribe")
                form = FormData(); form.add_field("model", model)
                form.add_field("response_format", "json")
                form.add_field("file", content, filename="capture.wav", content_type="audio/wav")
                async with session.post("https://api.openai.com/v1/audio/transcriptions", data=form, allow_redirects=False) as r:
                    if r.status != 200:
                        raise ValueError("transcription_provider_http_"+str(r.status))
                    result = await r.json()
                    return str(result.get("text", ""))[:4000]
            if kind == "vision":
                if mime != "image/jpeg" or len(content) > 5*1024*1024 or not content.startswith(b"\xff\xd8"):
                    raise ValueError("jpeg_under_5mb_required")
                model = self.config.get("vision_model")
                if not model:
                    raise ValueError("vision_model_not_configured")
                payload = {"model": model, "store": False, "max_output_tokens": 400, "input": [{"role": "user", "content": [
                    {"type": "input_text", "text": question},
                    {"type": "input_image", "image_url": "data:image/jpeg;base64,"+base64.b64encode(content).decode(), "detail": "low"}]}]}
                async with session.post("https://api.openai.com/v1/responses", json=payload, allow_redirects=False) as r:
                    if r.status != 200:
                        raise ValueError("vision_provider_http_"+str(r.status))
                    result = await r.json()
                    return "\n".join(part.get("text", "") for item in result.get("output", [])
                        if item.get("type") == "message" for part in item.get("content", [])
                        if part.get("type") == "output_text")[:4000]
            raise ValueError("unsupported_ai_operation")
