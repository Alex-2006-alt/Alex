import sys, time, ollama
sys.stdout.reconfigure(encoding='utf-8')

p = (
    "You are Alex, an AI assistant on Windows.\n"
    "When asked to open an app or website, respond like:\n"
    "Sure thing! Opening YouTube for you.\n"
    "```action\n"
    '{"action": "web_open", "params": {"url": "https://www.youtube.com"}}\n'
    "```\n"
    "Keep responses short and friendly."
)

t0 = time.time()
res = ollama.chat(
    model='qwen3.5:4b',
    messages=[
        {'role': 'system', 'content': p},
        {'role': 'user', 'content': 'open youtube'}
    ],
    think=False,
    options={'temperature': 0.3}
)
print(f"Got in {round(time.time()-t0, 2)}s:")
print(res['message']['content'])
