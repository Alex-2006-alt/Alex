import sys
sys.path.insert(0, 'e:/alex')
from core.brain import Brain
from core.tool_registry import ToolRegistry
import tools

brain = Brain("gemini")
brain.set_tool_registry(ToolRegistry.get_instance())

print("Open youtube and play songs:", brain.think("open youtube and play songs"))
