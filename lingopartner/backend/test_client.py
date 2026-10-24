"""Portable manual client for the mock/live local server."""
import argparse
import json
import urllib.request
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--url", default="http://127.0.0.1:8765")
p.add_argument("--token", default="")
p.add_argument("--text", default="Hello Pepper")
p.add_argument("--wav", type=Path, default=None)
a = p.parse_args()
if a.wav:
    data = a.wav.read_bytes()
    endpoint = "/audio"
    content_type = "audio/wav"
else:
    data = json.dumps({"text": a.text}).encode()
    endpoint = "/text"
    content_type = "application/json"
request = urllib.request.Request(a.url.rstrip("/") + endpoint, data=data,
                                 headers={"Content-Type": content_type,
                                          "X-Session-Token": a.token})
with urllib.request.urlopen(request, timeout=120) as result:
    print(json.dumps(json.load(result), indent=2, ensure_ascii=False))
