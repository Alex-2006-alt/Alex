"""
Quick test: Does the LLM actually respond?
Run this to verify your API key and model are working without needing
audio hardware, Whisper, or the full assistant.

Usage:
    python test_brain.py
"""

import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent))

# Fix Windows console encoding for emoji output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config

print(f"{'='*60}")
print(f"  🧪 ALEX — Brain Quick Test")
print(f"  Provider : {config.LLM_PROVIDER}")

# Resolve model name dynamically
model_attr = f"{config.LLM_PROVIDER.upper()}_MODEL"
model_name = getattr(config, model_attr, "unknown")
print(f"  Model    : {model_name}")
print(f"  Max Tokens: {config.LLM_MAX_TOKENS}")
print(f"  Retries  : {config.LLM_RETRY_COUNT}")
print(f"{'='*60}\n")

# Test 1: Simple conversation
print("  [1/3] Testing simple conversation...")
try:
    from core.brain import Brain
    brain = Brain()
    result = brain.think("Hello! What is your name and what can you do?")
    response = result.get("response", "")
    if response and response.strip():
        print(f"    ✅ Response: \"{response[:120]}{'...' if len(response) > 120 else ''}\"")
    else:
        print(f"    ❌ EMPTY response! This is the bug. Check your API key and model.")
        sys.exit(1)
except Exception as e:
    print(f"    ❌ FAILED: {e}")
    sys.exit(1)

# Test 2: Action request
print("\n  [2/3] Testing action request...")
try:
    result = brain.think("Open Chrome for me")
    response = result.get("response", "")
    action = result.get("action")
    print(f"    ✅ Response: \"{response[:100]}\"")
    print(f"    ✅ Action: {action}")
    print(f"    ✅ Params: {result.get('params')}")
except Exception as e:
    print(f"    ❌ FAILED: {e}")

# Test 3: Edge case — very short input
print("\n  [3/3] Testing short input...")
try:
    result = brain.think("Hi")
    response = result.get("response", "")
    if response and response.strip():
        print(f"    ✅ Response: \"{response[:100]}\"")
    else:
        print(f"    ⚠️ Empty response for 'Hi' — model may struggle with short inputs")
except Exception as e:
    print(f"    ❌ FAILED: {e}")

print(f"\n{'='*60}")
print(f"  🎉 Brain test complete!")
print(f"{'='*60}\n")
