import io
import json
import threading
import unittest
import urllib.request
import wave
from http.server import ThreadingHTTPServer
from pepper_poc.pipeline import parse_model_output, MockASR, MockLLM
from pepper_poc.server import Handler, validate_wav


def silent_wav():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(b"\x00\x00" * 1600)
    return buf.getvalue()


class ContractTest(unittest.TestCase):
    def test_model_output_accepts_allowlisted_greeting(self):
        result = parse_model_output(json.dumps({"response_text": "Hello", "tool_calls": [
            {"tool": "gesture", "arguments": {"name": "greeting"}}]}))
        self.assertEqual(result["tool_calls"][0]["tool"], "gesture")

    def test_reject_unknown_or_malformed_tools(self):
        result = parse_model_output('{"response_text":"Ok","tool_calls":[{"tool":"move_to","arguments":{"x":10}}]}')
        self.assertEqual(result["tool_calls"], [])
        self.assertEqual(parse_model_output("plain response")["response_text"], "plain response")

    def test_wav_contract(self):
        validate_wav(silent_wav())
        with self.assertRaises(ValueError):
            validate_wav(b"garbage")

    def test_http_mock_text_and_audio(self):
        Handler.llm, Handler.asr, Handler.mode, Handler.token = MockLLM(), MockASR(), "mock", "test-token"
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        th = threading.Thread(target=server.serve_forever, daemon=True)
        th.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urllib.request.urlopen(base + "/health") as result:
                self.assertTrue(json.load(result)["ok"])
            for path, data, ctype in (
                    ("/text", b'{"text":"Please wave"}', "application/json"),
                    ("/audio", silent_wav(), "audio/wav")):
                request = urllib.request.Request(base + path, data=data, headers={
                    "X-Session-Token": "test-token", "Content-Type": ctype})
                with urllib.request.urlopen(request) as result:
                    reply = json.load(result)
                    self.assertIn("response_text", reply)
                    self.assertIn("transcript", reply)
        finally:
            server.shutdown()
            server.server_close()
            th.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
