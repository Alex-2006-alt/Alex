"""
ALEX Tools Package
Automatically imports and registers all tools with the ToolRegistry.
"""

# Import all tool modules to trigger their @tool decorators and registration
from tools import web_tools
from tools import file_tools
from tools import code_tools
from tools import system_tools
from tools import notification_tools
from tools import data_tools

__all__ = ["web_tools", "file_tools", "code_tools", "system_tools", "notification_tools", "data_tools"]
