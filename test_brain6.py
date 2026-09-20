import sys
sys.path.insert(0, 'e:/alex')
from core.brain import Brain
from core.tool_registry import ToolRegistry
import tools

brain = Brain("ollama")
brain.set_tool_registry(ToolRegistry.get_instance())

print("Ollama test:", brain.think("alex open yt and play songs"))
