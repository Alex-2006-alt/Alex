"""
ALEX — File Tools
Enhanced file system operations: read, write, find, list, move, copy, delete.
"""

import os
import re
import shutil
import fnmatch
from pathlib import Path
from datetime import datetime

from core.tool_registry import tool, ToolResult, SafetyLevel
from utils.logger import log
import config


def _is_allowed_path(path) -> bool:
    """
    Check whether a path is inside one of config.ALLOWED_FILE_PATHS.

    resolve() collapses '..' first, so traversal out of an allowed root is
    caught rather than matched on the literal prefix.
    """
    if not config.ENFORCE_FILE_ALLOWLIST or not config.ALLOWED_FILE_PATHS:
        return True  # No restrictions
    path_obj = Path(path).expanduser().resolve()
    for allowed in config.ALLOWED_FILE_PATHS:
        try:
            path_obj.relative_to(Path(allowed).expanduser().resolve())
            return True
        except ValueError:
            continue
    return False


def _deny_if_outside(path, what: str = "write to") -> ToolResult | None:
    """
    Guard for the tools that modify the filesystem. Returns a failure
    ToolResult to hand straight back, or None when the path is allowed.

    Reading and listing are deliberately unrestricted — the allow-list exists
    to stop Alex from *changing* things outside the user's own directories.
    """
    if _is_allowed_path(path):
        return None

    roots = ", ".join(config.ALLOWED_FILE_PATHS)
    log.error(f"⛔ Refused to {what} outside the allow-list: {path}")
    return ToolResult(
        success=False,
        message=f"I can only {what} files inside your own folders.",
        error=f"Path {path} is outside ALLOWED_FILE_PATHS ({roots})",
    )


@tool(
    name="file_read",
    description="Read the contents of a file and return its text",
    parameters={
        "path": {"type": "string", "description": "Absolute or relative path to the file", "required": True},
        "encoding": {"type": "string", "description": "File encoding (default: utf-8)", "required": False},
    },
    category="files",
)
def file_read(params: dict) -> ToolResult:
    path = params.get("path", "")
    encoding = params.get("encoding", "utf-8")

    if not path:
        return ToolResult(success=False, error="No file path provided")

    p = Path(path).expanduser().resolve()

    if not p.exists():
        return ToolResult(success=False, error=f"File not found: {path}")
    if not p.is_file():
        return ToolResult(success=False, error=f"Not a file: {path}")

    try:
        content = p.read_text(encoding=encoding, errors="replace")
        log.info(f"📖 Read file: {p} ({len(content)} chars)")
        # Truncate for LLM
        truncated = content[:4000]
        note = "" if len(content) <= 4000 else f"\n... [truncated, file is {len(content)} chars total]"
        return ToolResult(success=True, message=truncated + note, data={"path": str(p), "content": content, "size": len(content)})
    except Exception as e:
        return ToolResult(success=False, error=f"Could not read file: {e}")


@tool(
    name="file_write",
    description="Write text content to a file, creating it if it doesn't exist",
    parameters={
        "path": {"type": "string", "description": "Path to write to", "required": True},
        "content": {"type": "string", "description": "Text content to write", "required": True},
        "mode": {"type": "string", "description": "'write' (overwrite) or 'append' (default: write)", "required": False},
        "encoding": {"type": "string", "description": "Encoding (default: utf-8)", "required": False},
    },
    category="files",
    safety=SafetyLevel.WARN,
)
def file_write(params: dict) -> ToolResult:
    path = params.get("path", "")
    content = params.get("content", "")
    mode = params.get("mode", "write")
    encoding = params.get("encoding", "utf-8")

    if not path:
        return ToolResult(success=False, error="No file path provided")

    p = Path(path).expanduser().resolve()

    denied = _deny_if_outside(p, "write to")
    if denied:
        return denied

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        write_mode = "a" if mode == "append" else "w"
        p.write_text(content, encoding=encoding) if write_mode == "w" else open(p, "a", encoding=encoding).write(content)
        log.info(f"✏️ Wrote file: {p} ({len(content)} chars, mode={mode})")
        return ToolResult(success=True, message=f"File saved: {p}", data={"path": str(p), "bytes": len(content)}, artifacts=[str(p)])
    except Exception as e:
        return ToolResult(success=False, error=f"Could not write file: {e}")


@tool(
    name="file_find",
    description="Search for files matching a pattern in a directory (recursively)",
    parameters={
        "directory": {"type": "string", "description": "Directory to search in", "required": True},
        "pattern": {"type": "string", "description": "Glob pattern like '*.pdf' or filename substring", "required": True},
        "recursive": {"type": "boolean", "description": "Search subdirectories (default: true)", "required": False},
        "max_results": {"type": "integer", "description": "Max files to return (default: 50)", "required": False},
    },
    category="files",
)
def file_find(params: dict) -> ToolResult:
    directory = params.get("directory", str(Path.home()))
    pattern = params.get("pattern", "*")
    recursive = params.get("recursive", True)
    max_results = int(params.get("max_results", 50))

    base = Path(directory).expanduser().resolve()
    if not base.exists():
        return ToolResult(success=False, error=f"Directory not found: {directory}")

    try:
        if recursive:
            matches = list(base.rglob(pattern))
        else:
            matches = list(base.glob(pattern))

        matches = matches[:max_results]

        results = []
        for p in matches:
            stat = p.stat()
            results.append({
                "path": str(p),
                "name": p.name,
                "size_bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "is_dir": p.is_dir(),
            })

        message = f"Found {len(results)} files matching '{pattern}' in {directory}:\n"
        message += "\n".join(f"  {r['path']} ({r['size_bytes']} bytes)" for r in results[:20])
        if len(results) > 20:
            message += f"\n  ... and {len(results) - 20} more"

        log.info(f"🔍 File find '{pattern}' in {base}: {len(results)} results")
        return ToolResult(success=True, message=message, data={"results": results, "count": len(results)})
    except Exception as e:
        return ToolResult(success=False, error=f"File search failed: {e}")


@tool(
    name="file_list",
    description="List files and folders in a directory",
    parameters={
        "directory": {"type": "string", "description": "Directory path to list", "required": True},
        "show_hidden": {"type": "boolean", "description": "Show hidden files (default: false)", "required": False},
    },
    category="files",
)
def file_list(params: dict) -> ToolResult:
    directory = params.get("directory", str(Path.home()))
    show_hidden = params.get("show_hidden", False)

    base = Path(directory).expanduser().resolve()
    if not base.exists():
        return ToolResult(success=False, error=f"Directory not found: {directory}")

    try:
        items = []
        for entry in sorted(base.iterdir()):
            if not show_hidden and entry.name.startswith("."):
                continue
            stat = entry.stat()
            items.append({
                "name": entry.name,
                "path": str(entry),
                "is_dir": entry.is_dir(),
                "size_bytes": stat.st_size if entry.is_file() else None,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            })

        dirs = [i for i in items if i["is_dir"]]
        files = [i for i in items if not i["is_dir"]]

        lines = [f"Contents of {directory}:", f"  📁 {len(dirs)} folders, 📄 {len(files)} files"]
        for d in dirs[:20]:
            lines.append(f"  📁 {d['name']}/")
        for f in files[:30]:
            size = f"{f['size_bytes']:,} bytes" if f["size_bytes"] is not None else ""
            lines.append(f"  📄 {f['name']} {size}")

        return ToolResult(success=True, message="\n".join(lines), data={"items": items, "directory": str(base)})
    except Exception as e:
        return ToolResult(success=False, error=f"Could not list directory: {e}")


@tool(
    name="file_move",
    description="Move or rename a file or folder",
    parameters={
        "source": {"type": "string", "description": "Source file/folder path", "required": True},
        "destination": {"type": "string", "description": "Destination path", "required": True},
    },
    category="files",
    safety=SafetyLevel.WARN,
)
def file_move(params: dict) -> ToolResult:
    src = Path(params.get("source", "")).expanduser().resolve()
    dst = Path(params.get("destination", "")).expanduser().resolve()

    if not src.exists():
        return ToolResult(success=False, error=f"Source not found: {src}")

    # A move changes both ends, so both must be allowed
    for candidate in (src, dst):
        denied = _deny_if_outside(candidate, "move")
        if denied:
            return denied

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        log.info(f"📦 Moved: {src} → {dst}")
        return ToolResult(success=True, message=f"Moved {src.name} to {dst}", data={"from": str(src), "to": str(dst)})
    except Exception as e:
        return ToolResult(success=False, error=f"Move failed: {e}")


@tool(
    name="file_copy",
    description="Copy a file or folder to a new location",
    parameters={
        "source": {"type": "string", "description": "Source file/folder path", "required": True},
        "destination": {"type": "string", "description": "Destination path", "required": True},
    },
    category="files",
)
def file_copy(params: dict) -> ToolResult:
    src = Path(params.get("source", "")).expanduser().resolve()
    dst = Path(params.get("destination", "")).expanduser().resolve()

    if not src.exists():
        return ToolResult(success=False, error=f"Source not found: {src}")

    # Only the destination is created, so only it needs to be allowed
    denied = _deny_if_outside(dst, "copy to")
    if denied:
        return denied

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(str(src), str(dst))
        else:
            shutil.copy2(str(src), str(dst))
        log.info(f"📋 Copied: {src} → {dst}")
        return ToolResult(success=True, message=f"Copied {src.name} to {dst}", data={"from": str(src), "to": str(dst)}, artifacts=[str(dst)])
    except Exception as e:
        return ToolResult(success=False, error=f"Copy failed: {e}")


@tool(
    name="file_delete",
    description="Delete a file or empty folder",
    parameters={
        "path": {"type": "string", "description": "Path to delete", "required": True},
        "recursive": {"type": "boolean", "description": "Delete folder and all contents (default: false)", "required": False},
    },
    category="files",
    safety=SafetyLevel.CONFIRM,
)
def file_delete(params: dict) -> ToolResult:
    path = Path(params.get("path", "")).expanduser().resolve()
    recursive = params.get("recursive", False)

    if not path.exists():
        return ToolResult(success=False, error=f"Path not found: {path}")

    denied = _deny_if_outside(path, "delete")
    if denied:
        return denied

    try:
        if path.is_dir():
            if recursive:
                shutil.rmtree(str(path))
            else:
                path.rmdir()
        else:
            path.unlink()
        log.warning(f"🗑️ Deleted: {path}")
        return ToolResult(success=True, message=f"Deleted: {path.name}")
    except Exception as e:
        return ToolResult(success=False, error=f"Delete failed: {e}")


@tool(
    name="file_mkdir",
    description="Create a new directory (including all parent directories)",
    parameters={
        "path": {"type": "string", "description": "Directory path to create", "required": True},
    },
    category="files",
)
def file_mkdir(params: dict) -> ToolResult:
    path = Path(params.get("path", "")).expanduser().resolve()

    denied = _deny_if_outside(path, "create folders in")
    if denied:
        return denied

    try:
        path.mkdir(parents=True, exist_ok=True)
        return ToolResult(success=True, message=f"Created directory: {path}", artifacts=[str(path)])
    except Exception as e:
        return ToolResult(success=False, error=f"Could not create directory: {e}")
