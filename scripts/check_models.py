"""Check available free models on OpenRouter and find the fastest one."""
import urllib.request
import json

import os

api_key = os.getenv("OPENROUTER_API_KEY", "")
headers = {}
if api_key:
    headers["Authorization"] = f"Bearer {api_key}"

req = urllib.request.Request(
    "https://openrouter.ai/api/v1/models",
    headers=headers
)
with urllib.request.urlopen(req, timeout=15) as resp:
    data = json.loads(resp.read())

free_models = [
    m for m in data["data"]
    if str(m.get("pricing", {}).get("prompt", "1")) == "0"
]

print(f"Found {len(free_models)} free models:\n")
for m in sorted(free_models, key=lambda x: x["id"]):
    ctx = m.get("context_length", 0)
    print(f"  {m['id']}  (ctx={ctx})")
