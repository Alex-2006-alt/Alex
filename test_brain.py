import sys
sys.path.insert(0, 'e:/alex')
from core.brain import Brain
brain = Brain("gemini")
from core.tool_registry import ToolRegistry
import tools
brain.set_tool_registry(ToolRegistry.get_instance())
print("Playing song response:", brain.think("alex play songs"))
print("Open yt response:", brain.think("alex open yt"))
