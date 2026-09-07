"""
ALEX — Plugin Loader
Dynamically discovers and loads plugins from the plugins directory.
"""

import importlib
import inspect
from pathlib import Path

from utils.logger import log
import config


class PluginBase:
    """Base class that all plugins should inherit from."""

    name: str = "unnamed_plugin"
    description: str = "No description"
    actions: list[str] = []  # Action names this plugin handles

    def execute(self, params: dict) -> str:
        """Execute the plugin action. Override this."""
        raise NotImplementedError("Plugin must implement execute()")


class PluginLoader:
    """
    Discovers and loads plugins from the plugins directory.
    Plugins are Python files that contain classes inheriting from PluginBase.
    """

    def __init__(self, plugin_dir: Path | None = None):
        self.plugin_dir = plugin_dir or config.PLUGINS_DIR
        self.plugins: dict[str, PluginBase] = {}

    def discover(self) -> dict[str, PluginBase]:
        """
        Discover and load all plugins.

        Returns:
            Dict mapping action names to plugin instances
        """
        log.info(f"🔌 Discovering plugins in {self.plugin_dir}...")

        if not self.plugin_dir.exists():
            log.warning(f"Plugin directory not found: {self.plugin_dir}")
            return self.plugins

        for py_file in self.plugin_dir.glob("*_plugin.py"):
            try:
                self._load_plugin_file(py_file)
            except Exception as e:
                log.error(f"Failed to load plugin {py_file.name}: {e}")

        log.info(f"🔌 Loaded {len(self.plugins)} plugin action(s)")
        return self.plugins

    def _load_plugin_file(self, filepath: Path):
        """Load a single plugin file."""
        module_name = f"plugins.{filepath.stem}"

        try:
            module = importlib.import_module(module_name)
        except ImportError as e:
            log.warning(f"Could not import {module_name}: {e}")
            return

        # Find all classes that inherit from PluginBase
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, PluginBase) and obj is not PluginBase:
                try:
                    instance = obj()
                    for action in instance.actions:
                        self.plugins[action] = instance
                        log.info(f"  🔌 Registered: {action} → {instance.name}")
                except Exception as e:
                    log.error(f"Failed to instantiate plugin {name}: {e}")

    def get_plugin(self, action: str) -> PluginBase | None:
        """Get the plugin for a given action."""
        return self.plugins.get(action)

    def list_plugins(self) -> list[dict]:
        """List all loaded plugins."""
        seen = set()
        result = []
        for action, plugin in self.plugins.items():
            if plugin.name not in seen:
                seen.add(plugin.name)
                result.append({
                    "name": plugin.name,
                    "description": plugin.description,
                    "actions": plugin.actions,
                })
        return result
