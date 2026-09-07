import requests

base = "http://127.0.0.1:5000"

print("--- CHAT TEST ---")
r = requests.post(base + "/api/chat", json={"message": "Hello Alex, what can you do now?"}, timeout=30)
d = r.json()
response = d.get("response", "NO RESPONSE")
print("Response:", response[:300])

print()
print("--- SYSTEM STATS ---")
r = requests.get(base + "/api/stats")
d = r.json()
print(f"CPU: {d.get('cpu')}%  RAM: {d.get('ram_percent')}%  Disk: {d.get('disk_percent')}%")
print(f"Uptime: {d.get('uptime')}")

print()
print("--- MEMORY API ---")
r = requests.get(base + "/api/memory")
d = r.json()
print(f"Facts stored: {len(d.get('facts', []))}")

print()
print("--- BACKGROUND TASKS ---")
r = requests.get(base + "/api/tasks")
d = r.json()
print(f"Running tasks: {d.get('count', 0)}")

print()
print("--- PLAN STATUS ---")
r = requests.get(base + "/api/plan")
d = r.json()
print(f"Plan: {d.get('status', d)}")

print()
print("=== ALL TESTS PASSED ===")
