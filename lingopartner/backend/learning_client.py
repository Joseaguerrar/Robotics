"""Optional explicit learner-progress API test; never infers scores from the LLM."""
import argparse
import json
import urllib.error
import urllib.request

p = argparse.ArgumentParser()
p.add_argument("--url", default="http://127.0.0.1:8765")
p.add_argument("--token", default="")
p.add_argument("--session", default="cli-trial")
p.add_argument("--lesson", default="intro-spanish")
p.add_argument("--language", default="es")
p.add_argument("--completed", type=int, default=5)
p.add_argument("--correct", type=int, default=4)
p.add_argument("--show", action="store_true")
p.add_argument("--reset", action="store_true")
a = p.parse_args()
if a.show:
    endpoint, method, body = "/learning/progress", "GET", None
elif a.reset:
    endpoint, method, body = "/learning/reset", "POST", b"{}"
else:
    endpoint, method = "/learning/progress", "POST"
    body = json.dumps({"lesson_id": a.lesson, "language": a.language,
                       "completed": a.completed, "correct": a.correct}).encode("utf-8")
request = urllib.request.Request(a.url.rstrip("/") + endpoint, data=body, method=method,
    headers={"X-Session-Token": a.token, "X-Session-Id": a.session,
             "Content-Type": "application/json"})
try:
    with urllib.request.urlopen(request, timeout=10) as response:
        print(json.dumps(json.load(response), indent=2, ensure_ascii=False))
except urllib.error.HTTPError as exc:
    print("HTTP", exc.code, exc.read().decode("utf-8", "replace"))
    raise SystemExit(1)
