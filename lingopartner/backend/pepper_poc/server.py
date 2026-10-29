"""Pepper LAN HTTP gateway. Text history optional; audio never stored persistently."""
import argparse
import io
import json
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .conversation import ConversationManager
from .pipeline import LlamaAdapter, MockLLM, MockASR, WhisperAdapter

MAX_JSON = 8192
MAX_WAV = 16000 * 2 * 15 + 1024  # 15 seconds; some WAV metadata permitted


def validate_wav(body: bytes):
    try:
        with wave.open(io.BytesIO(body), "rb") as f:
            if (f.getnchannels(), f.getsampwidth(), f.getframerate(), f.getcomptype()) != (1, 2, 16000, 'NONE'):
                raise ValueError("Require 16 kHz, mono, signed 16-bit PCM WAV")
            if not 0 < f.getnframes() <= 16000 * 15:
                raise ValueError("Audio duration must be >0 and <=15 seconds")
    except (wave.Error, EOFError) as e:
        raise ValueError("Invalid WAV: " + str(e)) from e


class Handler(BaseHTTPRequestHandler):
    llm = MockLLM()
    asr = MockASR()
    conversations = ConversationManager()
    token = ""
    mode = "mock"

    def send_json(self, code, value):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if self.path == "/health":
            return self.send_json(200, {"ok": True, "mode": self.mode,
                                        "persistent_text_history": self.conversations.persistent})
        if self.path == "/learning/progress":
            if self.token and self.headers.get("X-Session-Token") != self.token:
                return self.send_json(401, {"error": "wrong or missing session token"})
            try:
                sid = self.conversations.checked_session(self.headers.get("X-Session-Id", "legacy"))
                return self.send_json(200, {"session_id": sid,
                                            "lessons": self.conversations.get_progress(sid)})
            except ValueError as exc:
                return self.send_json(400, {"error": str(exc)})
            except RuntimeError as exc:
                return self.send_json(409, {"error": str(exc)})
        return self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path not in ("/text", "/audio", "/session/reset", "/learning/progress", "/learning/reset"):
            return self.send_json(404, {"error": "not found"})
        if self.token and self.headers.get("X-Session-Token") != self.token:
            return self.send_json(401, {"error": "wrong or missing session token"})
        try:
            session_id = self.conversations.checked_session(
                self.headers.get("X-Session-Id", "legacy"))
        except ValueError as exc:
            return self.send_json(400, {"error": str(exc)})
        size_limit = MAX_JSON if self.path != "/audio" else MAX_WAV
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length < 1 or length > size_limit:
            return self.send_json(413, {"error": "request empty or too large"})
        data = self.rfile.read(length)
        try:
            if self.path == "/session/reset":
                self.conversations.reset(session_id)
                return self.send_json(200, {"ok": True, "session_id": session_id,
                                            "history_turns": 0})
            if self.path == "/learning/reset":
                if not self.conversations.persistent:
                    return self.send_json(409, {"error": "Requires --db-path"})
                self.conversations.reset_progress(session_id)
                return self.send_json(200, {"ok": True, "session_id": session_id, "lessons": []})
            if self.path == "/learning/progress":
                if not self.conversations.persistent:
                    return self.send_json(409, {"error": "Requires --db-path"})
                obj = json.loads(data)
                if not isinstance(obj, dict):
                    raise ValueError("JSON object expected")
                self.conversations.save_progress(session_id, obj.get("lesson_id"),
                    obj.get("language"), obj.get("completed"), obj.get("correct"))
                return self.send_json(200, {"ok": True, "session_id": session_id,
                    "lessons": self.conversations.get_progress(session_id)})
            if self.path == "/text":
                obj = json.loads(data)
                utterance = obj.get("text", "") if isinstance(obj, dict) else ""
                if not isinstance(utterance, str) or not utterance.strip() or len(utterance) > 1000:
                    return self.send_json(400, {"error": "text must be 1-1000 characters"})
            else:
                validate_wav(data)
                utterance = self.asr.transcribe(data)
                if not utterance.strip():
                    return self.send_json(422, {"error": "no speech recognized"})
            result = self.conversations.reply(self.llm, session_id, utterance)
            return self.send_json(200, {"transcript": utterance, "session_id": session_id, **result})
        except (ValueError, json.JSONDecodeError) as exc:
            return self.send_json(400, {"error": str(exc)})
        except Exception as exc:
            print("[BACKEND ERROR] %s: %s" % (type(exc).__name__, exc), flush=True)
            return self.send_json(502, {"error": "local ASR/LLM failed; see server console"})


def main():
    p = argparse.ArgumentParser(description="Pepper local conversation server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--token", default="", help="required for LAN; prototype-only shared secret")
    p.add_argument("--live", action="store_true")
    p.add_argument("--llama-url", default="http://127.0.0.1:8080")
    p.add_argument("--whisper-exe", default="")
    p.add_argument("--whisper-model", default="")
    p.add_argument("--vad-model", default="")
    p.add_argument("--db-path", default="", help="opt-in persistent TEXT history SQLite path")
    p.add_argument("--history-turns", type=int, default=6)
    args = p.parse_args()
    if args.host not in ("127.0.0.1", "localhost", "::1") and not args.token:
        p.error("--token mandatory when listening on LAN")
    if not 1 <= args.history_turns <= 12:
        p.error("--history-turns must be 1-12")
    Handler.conversations = ConversationManager(args.db_path or None, args.history_turns)
    Handler.llm = LlamaAdapter(args.llama_url) if args.live else MockLLM()
    Handler.asr = (WhisperAdapter(args.whisper_exe, args.whisper_model, args.vad_model)
                   if args.live else MockASR())
    Handler.mode = "live" if args.live else "mock"
    Handler.token = args.token
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("Ready: http://%s:%d/health  mode=%s persistent=%s" % (
        args.host, args.port, Handler.mode, Handler.conversations.persistent), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
