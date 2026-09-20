import sys
sys.path.insert(0, 'e:/alex')
from core.brain import Brain
from core.tool_registry import ToolRegistry
import tools
import config

brain = Brain("ollama")
brain.set_tool_registry(ToolRegistry.get_instance())

# Let's just use think() directly, which will invoke Ollama
print("Ollama test:", brain.think("alex open yt and play songs"))
