"""Thread-safe, bounded per-session conversations with optional SQLite persistence.

Only transcribed text and assistant replies are stored, never audio bytes.
SQLite is opt-in via --db-path and must be kept outside the Git repository.
"""
import re
import sqlite3
from contextlib import contextmanager
import threading
from pathlib import Path

SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


class ConversationManager:
    def __init__(self, db_path=None, max_turns=6):
        self._lock = threading.RLock()
        self._recent = {}
        self.max_turns = max_turns
        self.db_path = str(db_path) if db_path else None
        if self.db_path:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS messages (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )""")
                conn.execute("CREATE INDEX IF NOT EXISTS by_session ON messages(session_id, seq)")
                conn.execute("""CREATE TABLE IF NOT EXISTS learning_progress (
                    session_id TEXT NOT NULL,
                    lesson_id TEXT NOT NULL,
                    language TEXT NOT NULL,
                    completed INTEGER NOT NULL,
                    correct INTEGER NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(session_id, lesson_id)
                )""")

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def checked_session(session_id):
        if not isinstance(session_id, str) or not SESSION_RE.fullmatch(session_id):
            raise ValueError("session_id must have 1-80 ASCII letters/digits/_/-")
        return session_id

    def _get(self, session_id):
        if self.db_path:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT role, content FROM messages WHERE session_id=? ORDER BY seq DESC LIMIT ?",
                    (session_id, 2 * self.max_turns),
                ).fetchall()
            return [{"role": role, "content": content} for role, content in reversed(rows)]
        return list(self._recent.get(session_id, []))[-2 * self.max_turns:]

    def count_turns(self, session_id):
        session_id = self.checked_session(session_id)
        with self._lock:
            return len(self._get(session_id)) // 2

    def reply(self, llm, session_id, utterance):
        session_id = self.checked_session(session_id)
        utterance = utterance.strip()[:1000]
        if not utterance:
            raise ValueError("empty utterance")
        # Serialize the read -> infer -> commit transaction. The first POC
        # handles one robot at a time; this prevents concurrent turn reordering.
        with self._lock:
            history = self._get(session_id)
            # Keep content in the 2048-token model context. This is a character
            # budget, not a precise token count; lower max_turns if needed.
            history = [{"role": item["role"], "content": item["content"][:500]}
                       for item in history]
            # Only the newest ~2200 characters are injected into the prompt,
            # independent of the number of turns retained in SQLite.
            prompt_history = []
            remaining = 2200
            for item in reversed(history):
                if remaining <= 0:
                    break
                content = item["content"][-remaining:]
                prompt_history.append({"role": item["role"], "content": content})
                remaining -= len(content)
            messages = list(reversed(prompt_history)) + [
                {"role": "user", "content": utterance}]
            result = llm.generate(messages)
            answer = result.get("response_text", "")
            if not isinstance(answer, str) or not answer.strip():
                raise RuntimeError("LLM returned no speakable response; conversation not saved")
            answer = answer[:500]
            if self.db_path:
                with self._connect() as conn:
                    conn.executemany(
                        "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                        [(session_id, "user", utterance), (session_id, "assistant", answer)],
                    )
                    # Bound database growth per session. Retain at most 100 turns
                    # for optional persistence; only most recent max_turns enter prompts.
                    conn.execute("""DELETE FROM messages WHERE session_id=? AND seq NOT IN (
                         SELECT seq FROM messages WHERE session_id=? ORDER BY seq DESC LIMIT 200)""",
                         (session_id, session_id))
            else:
                self._recent[session_id] = (history + [
                    {"role": "user", "content": utterance},
                    {"role": "assistant", "content": answer},
                ])[-2 * self.max_turns:]
            return {**result, "response_text": answer,
                    "history_turns": len(self._get(session_id)) // 2}

    def reset(self, session_id):
        session_id = self.checked_session(session_id)
        with self._lock:
            self._recent.pop(session_id, None)
            if self.db_path:
                with self._connect() as conn:
                    conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))

    @property
    def persistent(self):
        return bool(self.db_path)

    def save_progress(self, session_id, lesson_id, language, completed, correct):
        """Persist only explicitly submitted, aggregate lesson results (not audio)."""
        session_id = self.checked_session(session_id)
        if not self.db_path:
            raise RuntimeError("Persistent learning progress requires --db-path")
        if not isinstance(lesson_id, str) or not SESSION_RE.fullmatch(lesson_id):
            raise ValueError("lesson_id must contain 1-80 ASCII letters/digits/_/-")
        if language not in ("es", "en", "fr", "pt", "it", "de"):
            raise ValueError("language must be one of es/en/fr/pt/it/de")
        if (type(completed) is not int or type(correct) is not int or
                not 0 <= correct <= completed <= 10000):
            raise ValueError("Require integers: 0 <= correct <= completed <= 10000")
        with self._lock, self._connect() as conn:
            conn.execute("""INSERT OR REPLACE INTO learning_progress
                            (session_id, lesson_id, language, completed, correct, updated_at)
                            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                         (session_id, lesson_id, language, completed, correct))

    def get_progress(self, session_id):
        session_id = self.checked_session(session_id)
        if not self.db_path:
            raise RuntimeError("Persistent learning progress requires --db-path")
        with self._lock, self._connect() as conn:
            rows = conn.execute("""SELECT lesson_id, language, completed, correct, updated_at
                                   FROM learning_progress WHERE session_id=? ORDER BY lesson_id""",
                                (session_id,)).fetchall()
        return [dict(zip(("lesson_id", "language", "completed", "correct", "updated_at"), row))
                for row in rows]

    def reset_progress(self, session_id):
        session_id = self.checked_session(session_id)
        if not self.db_path:
            raise RuntimeError("Persistent learning progress requires --db-path")
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM learning_progress WHERE session_id=?", (session_id,))
