"""Windows-friendly manual client. Stable session enables multi-turn tests."""
import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--url", default="http://127.0.0.1:8765")
p.add_argument("--token", default="")
p.add_argument("--session", default="cli-trial", help="reuse for follow-up turns")
p.add_argument("--text", default="Hello Pepper")
p.add_argument("--wav", type=Path, default=None)
p.add_argument("--reset", action="store_true", help="clear this session")
a = p.parse_args()
if a.reset:
    data = b"{}"
    endpoint = "/session/reset"
    content_type = "application/json"
elif a.wav:
    data = a.wav.read_bytes()
    endpoint = "/audio"
    content_type = "audio/wav"
else:
    data = json.dumps({"text": a.text}).encode("utf-8")
    endpoint = "/text"
    content_type = "application/json"
request = urllib.request.Request(a.url.rstrip("/") + endpoint, data=data,
                                 headers={"Content-Type": content_type,
                                          "X-Session-Token": a.token,
                                          "X-Session-Id": a.session})
try:
    with urllib.request.urlopen(request, timeout=150) as result:
        print(json.dumps(json.load(result), indent=2, ensure_ascii=False))
except urllib.error.HTTPError as exc:
    print("HTTP", exc.code, exc.read().decode("utf-8", "replace"))
    raise SystemExit(1)
