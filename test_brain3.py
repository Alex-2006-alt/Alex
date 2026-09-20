import sys
sys.path.insert(0, 'e:/alex')
from core.brain import Brain
brain = Brain("gemini")
from core.tool_registry import ToolRegistry
import tools
brain.set_tool_registry(ToolRegistry.get_instance())
print("Preference rule response:", brain.think("alex play sad songs in youtube"))
