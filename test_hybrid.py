import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import config
from core.brain import Brain
from core.tool_registry import ToolRegistry
import tools

print("=" * 60)
print(f"🤖 Testing Hybrid Dual-Model Brain")
print(f"   Provider : {config.LLM_PROVIDER}")
print(f"   Cloud    : Gemini ({config.GEMINI_MODEL})")
print(f"   Local    : Ollama ({config.OLLAMA_MODEL})")
print("=" * 60)

brain = Brain("hybrid")
brain.set_tool_registry(ToolRegistry.get_instance())

# Test 1: Fast conversation query
print("\n[Test 1] Testing conversation query with parallel dual-model...")
res1 = brain.think("Hi Alex, who are you and how are you feeling today?")
print("Result 1:")
print(f"  Model used : {res1.get('model', 'unknown')}")
print(f"  Response   : {res1.get('response')[:150]}...")
print(f"  Action     : {res1.get('action')}")

# Test 2: Action query (should trigger fast action detection)
print("\n[Test 2] Testing PC command query...")
res2 = brain.think("alex open youtube")
print("Result 2:")
print(f"  Model used : {res2.get('model', 'unknown')}")
print(f"  Response   : {res2.get('response')}")
print(f"  Action     : {res2.get('action')}")
print(f"  Params     : {res2.get('params')}")

print("\n" + "=" * 60)
print("✅ Hybrid dual-model test completed successfully!")
print("=" * 60)
