"""Find which free OpenRouter model responds fastest right now."""
import urllib.request
import json

import os

API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Models to try in order (fastest/smallest first)
CANDIDATES = [
    "liquid/lfm-2.5-1.2b-instruct:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-nano-9b-v2:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "qwen/qwen3-coder:free",
    "openrouter/free",
]

payload = json.dumps({
    "model": None,
    "messages": [{"role": "user", "content": "Reply with only: ALIVE"}],
    "max_tokens": 10,
}).encode()

for model in CANDIDATES:
    try:
        body = payload.replace(b'"model": null', f'"model": "{model}"'.encode())
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            result = json.loads(resp.read())
            text = result["choices"][0]["message"]["content"].strip()
            print(f"[OK]  {model}  => '{text}'")
    except Exception as e:
        err = str(e)[:80]
        print(f"[FAIL] {model}  => {err}")
