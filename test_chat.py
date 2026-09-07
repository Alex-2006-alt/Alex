import requests

base = "http://127.0.0.1:5000"

print("Testing chat with Llama 3.2 3B (fast free model)...")
r = requests.post(base + "/api/chat", json={"message": "Hi! Say hello in one short sentence."}, timeout=60)
d = r.json()
print("Response:", d.get("response", "ERROR: " + str(d)))

print()
r2 = requests.get(base + "/api/status")
d2 = r2.json()
print(f"LLM: {d2.get('llm_provider')} / {d2.get('llm_model')}")
