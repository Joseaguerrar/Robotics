"""Adapters and conservative parsing for the Pepper POC.

Real mode uses an existing llama-server and whisper-cli; neither is embedded.
"""
import json
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Any


def parse_model_output(raw: str) -> dict[str, Any]:
    """Never execute generated code; return text and allowlisted tool requests."""
    raw = raw.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.S)
    candidate = match.group(1) if match else raw
    try:
        value = json.loads(candidate)
    except (ValueError, TypeError):
        return {"response_text": raw[:500], "tool_calls": []}
    if not isinstance(value, dict):
        return {"response_text": raw[:500], "tool_calls": []}
    response = value.get("response_text", "")
    response = response[:500] if isinstance(response, str) else ""
    allowed = []
    tools = value.get("tool_calls", [])
    if isinstance(tools, list):
        for tool in tools[:2]:
            if not isinstance(tool, dict):
                continue
            name, args = tool.get("tool"), tool.get("arguments")
            # Only a gesture *request* for the demonstration. On today's app this
            # is acknowledged on screen; it is NOT an implemented physical wave.
            if name == "gesture" and isinstance(args, dict) and args == {"name": "greeting"}:
                allowed.append({"tool": "gesture", "arguments": {"name": "greeting"}})
    return {"response_text": response, "tool_calls": allowed}


class MockLLM:
    def generate(self, user_text: str) -> dict[str, Any]:
        if "wave" in user_text.lower() or "saluda" in user_text.lower():
            return {"response_text": "Hello! Nice to meet you.",
                    "tool_calls": [{"tool": "gesture", "arguments": {"name": "greeting"}}]}
        return {"response_text": "Test reply: " + user_text[:200], "tool_calls": []}


class LlamaAdapter:
    def __init__(self, url: str):
        self.url = url.rstrip("/") + "/v1/chat/completions"

    
    def generate(self, user_text: str) -> dict[str, Any]:
        system = (
            "You are Pepper, a friendly language-learning robot. "
            "Return ONLY one valid JSON object with exactly these keys: "
            "response_text and tool_calls. "
            "response_text MUST contain a short sentence that Pepper can speak. "
            "tool_calls MUST be an array. "
            "The only allowed tool is "
            '{"tool":"gesture","arguments":{"name":"greeting"}}. '
            "Use no tools unless the user explicitly requests a greeting gesture. "
            "Do not claim to see anything. Keep your response brief."
        )

        request_data = json.dumps({
            "model": "local",
            "stream": False,
            "temperature": 0.2,
            "max_tokens": 320,
            "chat_template_kwargs": {
                "enable_thinking": False
            },
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": user_text + "\n/no_think"
                }
            ]
        }).encode("utf-8")

        request = urllib.request.Request(
            self.url,
            data=request_data,
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.load(response)

        choice = data["choices"][0]
        message = choice["message"]
        raw = message.get("content") or ""

        if not raw.strip():
            raise RuntimeError(
                "Qwen returned empty content. "
                f"finish_reason={choice.get('finish_reason')}, "
                f"reasoning_present={bool(message.get('reasoning_content'))}, "
                f"completion_tokens={data.get('usage', {}).get('completion_tokens')}"
            )

        result = parse_model_output(raw)

        if not result["response_text"].strip():
            raise RuntimeError(
                "Qwen returned no speakable response. "
                f"Raw output: {raw[:300]!r}"
            )

        return result



class MockASR:
    def transcribe(self, wav_data: bytes) -> str:
        return "Hello Pepper (mock audio transcription)"


class WhisperAdapter:
    def __init__(self, exe: str, model: str, vad_model: str):
        self.exe, self.model, self.vad_model = exe, model, vad_model
        for p in (exe, model, vad_model):
            if not Path(p).is_file():
                raise FileNotFoundError(f"Missing ASR asset: {p}")

    def transcribe(self, wav_data: bytes) -> str:
        with tempfile.TemporaryDirectory(prefix="pepper_asr_") as tmp:
            audio = Path(tmp) / "utterance.wav"
            prefix = Path(tmp) / "result"
            audio.write_bytes(wav_data)
            argv = [self.exe, "-m", self.model, "-f", str(audio),
                    "--vad", "--vad-model", self.vad_model,
                    "-otxt", "-of", str(prefix)]
            result = subprocess.run(argv, capture_output=True, text=True, timeout=100, check=False)
            if result.returncode != 0:
                raise RuntimeError("whisper-cli failed: " + result.stderr[-800:])
            output = Path(str(prefix) + ".txt")
            if not output.exists():
                raise RuntimeError("whisper-cli produced no text file")
            return " ".join(output.read_text(encoding="utf-8").split())[:1000]
