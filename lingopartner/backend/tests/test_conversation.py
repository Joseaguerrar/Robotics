import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import wave
from pathlib import Path
from http.server import ThreadingHTTPServer
from pepper_poc.conversation import ConversationManager
from pepper_poc.pipeline import MockLLM, MockASR
from pepper_poc.server import Handler


def wav():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 3200)
    return buf.getvalue()


class MemoryTests(unittest.TestCase):
    def test_session_memory_and_separation(self):
        m = ConversationManager(max_turns=3)
        m.reply(MockLLM(), "pepper1", "My name is Carlos")
        self.assertIn("Carlos", m.reply(MockLLM(), "pepper1", "What is my name?")["response_text"])
        self.assertNotIn("Carlos", m.reply(MockLLM(), "pepper2", "What is my name?")["response_text"])
        m.reset("pepper1")
        self.assertEqual(m.count_turns("pepper1"), 0)

    def test_persistence_and_reset(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "private" / "history.sqlite3"
            a = ConversationManager(path)
            a.reply(MockLLM(), "pepper1", "My name is Ana")
            b = ConversationManager(path)
            self.assertIn("Ana", b.reply(MockLLM(), "pepper1", "What is my name?")["response_text"])
            b.reset("pepper1")
            c = ConversationManager(path)
            self.assertEqual(c.count_turns("pepper1"), 0)
            self.assertTrue(c.persistent)

    def test_learning_progress_explicit_storage_and_reset(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "history.sqlite3"
            m = ConversationManager(path)
            m.save_progress("pepper1", "lesson-1", "es", 5, 4)
            self.assertEqual(ConversationManager(path).get_progress("pepper1")[0]["correct"], 4)
            self.assertEqual(m.get_progress("pepper2"), [])
            m.reset("pepper1")  # conversation reset intentionally does not erase lesson scores
            self.assertEqual(len(m.get_progress("pepper1")), 1)
            m.reset_progress("pepper1")
            self.assertEqual(m.get_progress("pepper1"), [])
            with self.assertRaises(ValueError):
                m.save_progress("pepper1", "lesson-1", "es", 4, 7)

    def test_reject_bad_session_id(self):
        m = ConversationManager()
        for value in ("../../secrets", "", "hello there", "école"):
            with self.assertRaises(ValueError):
                m.reply(MockLLM(), value, "Hi")

    def test_learning_progress_http_endpoints(self):
        with tempfile.TemporaryDirectory() as d:
            class H(Handler):
                llm = MockLLM()
                asr = MockASR()
                conversations = ConversationManager(Path(d) / "history.sqlite3")
                token = "secret"
                mode = "mock"
            server = ThreadingHTTPServer(("127.0.0.1", 0), H)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = "http://127.0.0.1:%d" % server.server_port
            headers = {"Content-Type":"application/json", "X-Session-Token":"secret", "X-Session-Id":"alpha"}
            def req(path, body=None):
                with urllib.request.urlopen(urllib.request.Request(base+path, data=body, headers=headers)) as r:
                    return json.load(r)
            try:
                req("/learning/progress", json.dumps({"lesson_id":"intro", "language":"es", "completed":6, "correct":5}).encode())
                self.assertEqual(req("/learning/progress")["lessons"][0]["correct"], 5)
                req("/learning/reset", b"{}")
                self.assertEqual(req("/learning/progress")["lessons"], [])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_no_empty_model_output_saved(self):
        class Empty:
            def generate(self, messages):
                return {"response_text": "", "tool_calls": []}
        m = ConversationManager()
        with self.assertRaises(RuntimeError):
            m.reply(Empty(), "pepper", "Hello")
        self.assertEqual(m.count_turns("pepper"), 0)

    def test_http_session_reset_and_audio(self):
        class H(Handler):
            llm = MockLLM()
            asr = MockASR()
            conversations = ConversationManager()
            token = "secret"
            mode = "mock"
        server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:%d" % server.server_port
        def req(path, body, sid="alpha", token="secret", ctype="application/json"):
            request = urllib.request.Request(base + path, data=body, headers={
                "Content-Type": ctype, "X-Session-Token": token, "X-Session-Id": sid})
            with urllib.request.urlopen(request) as response:
                return json.load(response)
        try:
            req("/text", b'{"text":"My name is Ana"}')
            result = req("/text", b'{"text":"What is my name?"}')
            self.assertIn("Ana", result["response_text"])
            self.assertEqual(result["history_turns"], 2)
            self.assertTrue(req("/audio", wav(), ctype="audio/wav")["transcript"])
            self.assertEqual(req("/session/reset", b"{}")["history_turns"], 0)
            with self.assertRaises(urllib.error.HTTPError) as cm:
                req("/session/reset", b"{}", token="bad")
            self.assertEqual(cm.exception.code, 401)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
