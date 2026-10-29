"""Local ASR and LLM adapters for the Pepper POC. No model binaries included."""
import json
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

SYSTEM_PROMPT = (
    "You are Pepper, a friendly robot practicing languages with a human. "
    "Keep your answer short, conversational and in the user's language. "
    "Return ONLY a valid JSON object with keys response_text (nonempty text you will speak) "
    "and tool_calls (array). The only permitted tool request is "
    '{"tool":"gesture","arguments":{"name":"greeting"}}. '
    "Never request tools unless the user explicitly asks you to wave or gesture. "
    "Never claim to see your surroundings. Do not mention prior conversations "
    "unless the provided message history supports them."
)


def parse_model_output(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.S)
    candidate = match.group(1) if match else raw
    try:
        value = json.loads(candidate)
    except (ValueError, TypeError):
        # Plain text is an acceptable graceful fallback for voice interaction.
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
            # Display only. The POC does not execute physical gestures.
            if name == "gesture" and isinstance(args, dict) and args == {"name": "greeting"}:
                allowed.append({"tool": "gesture", "arguments": {"name": "greeting"}})
    return {"response_text": response, "tool_calls": allowed}


class MockLLM:
    def generate(self, messages):
        latest = messages[-1]["content"]
        if "what is my name" in latest.lower() or "what's my name" in latest.lower():
            names = re.findall(r"my name is ([A-Za-z]+)",
                               "\n".join(m["content"] for m in messages[:-1]), re.I)
            return {"response_text": "Your name is " + names[-1] + "." if names else "You have not told me your name.",
                    "tool_calls": []}
        if "wave" in latest.lower() or "saluda" in latest.lower():
            return {"response_text": "Hello! Nice to meet you.",
                    "tool_calls": [{"tool": "gesture", "arguments": {"name": "greeting"}}]}
        return {"response_text": "Test reply: " + latest[:200], "tool_calls": []}


class LlamaAdapter:
    def __init__(self, url: str):
        self.url = url.rstrip("/") + "/v1/chat/completions"

    def generate(self, messages):
        # The upstream server must already be running on localhost. /no_think
        # works with Qwen3 templates; check actual behavior for newer models.
        prompt = [{"role": "system", "content": SYSTEM_PROMPT}] + list(messages)
        prompt[-1] = {**prompt[-1], "content": prompt[-1]["content"] + "\n/no_think"}
        request_data = json.dumps({
            "model": "local", "stream": False, "temperature": 0.2, "max_tokens": 320,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": prompt,
        }).encode("utf-8")
        request = urllib.request.Request(self.url, data=request_data,
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=110) as response:
            data = json.load(response)
        choice = data["choices"][0]
        message = choice["message"]
        raw = message.get("content") or ""
        if not raw.strip():
            raise RuntimeError("LLM response empty: finish_reason=%r, reasoning=%s" % (
                choice.get("finish_reason"), bool(message.get("reasoning_content"))))
        parsed = parse_model_output(raw)
        if not parsed["response_text"].strip():
            raise RuntimeError("LLM returned no response_text; check its JSON or template")
        return parsed


class MockASR:
    def transcribe(self, wav_data: bytes) -> str:
        return "Hello Pepper (mock audio transcription)"


class WhisperAdapter:
    def __init__(self, exe: str, model: str, vad_model: str):
        self.exe, self.model, self.vad_model = exe, model, vad_model
        for p in (exe, model, vad_model):
            if not Path(p).is_file():
                raise FileNotFoundError("Missing ASR asset: %s" % p)

    def transcribe(self, wav_data: bytes) -> str:
        with tempfile.TemporaryDirectory(prefix="pepper_asr_") as tmp:
            audio = Path(tmp) / "utterance.wav"
            prefix = Path(tmp) / "result"
            audio.write_bytes(wav_data)
            argv = [self.exe, "-m", self.model, "-f", str(audio),
                    "--vad", "--vad-model", self.vad_model,
                    "-otxt", "-of", str(prefix)]
            result = subprocess.run(argv, capture_output=True, text=True,
                                    timeout=100, check=False)
            if result.returncode != 0:
                raise RuntimeError("whisper-cli failed: " + result.stderr[-800:])
            output = Path(str(prefix) + ".txt")
            if not output.exists():
                raise RuntimeError("whisper-cli produced no text file")
            return " ".join(output.read_text(encoding="utf-8").split())[:1000]
