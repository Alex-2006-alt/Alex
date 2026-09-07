"""
ALEX — Data Tools
CSV, JSON, Excel read/write and basic analysis.
"""

import json
import os
from pathlib import Path

from core.tool_registry import tool, ToolResult
from utils.logger import log


@tool(
    name="data_read_json",
    description="Read a JSON file and return its contents",
    parameters={
        "path": {"type": "string", "description": "Path to the JSON file", "required": True},
    },
    category="data",
)
def data_read_json(params: dict) -> ToolResult:
    path = Path(params.get("path", "")).expanduser().resolve()
    if not path.exists():
        return ToolResult(success=False, error=f"File not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        preview = json.dumps(data, indent=2)[:2000]
        return ToolResult(success=True, message=f"JSON from {path.name}:\n{preview}", data=data)
    except Exception as e:
        return ToolResult(success=False, error=f"Failed to read JSON: {e}")


@tool(
    name="data_write_json",
    description="Write data to a JSON file",
    parameters={
        "path": {"type": "string", "description": "Path to write JSON to", "required": True},
        "data": {"type": "object", "description": "JSON-serializable data to write", "required": True},
        "pretty": {"type": "boolean", "description": "Pretty-print the JSON (default: true)", "required": False},
    },
    category="data",
)
def data_write_json(params: dict) -> ToolResult:
    path = Path(params.get("path", "")).expanduser().resolve()
    data = params.get("data", {})
    pretty = params.get("pretty", True)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2 if pretty else None, ensure_ascii=False)
        return ToolResult(success=True, message=f"JSON saved to {path}", artifacts=[str(path)])
    except Exception as e:
        return ToolResult(success=False, error=f"Failed to write JSON: {e}")


@tool(
    name="data_read_csv",
    description="Read a CSV file and return its contents as a table summary",
    parameters={
        "path": {"type": "string", "description": "Path to the CSV file", "required": True},
        "max_rows": {"type": "integer", "description": "Max rows to read (default: 100)", "required": False},
    },
    category="data",
)
def data_read_csv(params: dict) -> ToolResult:
    path = Path(params.get("path", "")).expanduser().resolve()
    max_rows = int(params.get("max_rows", 100))

    if not path.exists():
        return ToolResult(success=False, error=f"File not found: {path}")

    try:
        import csv
        rows = []
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            for i, row in enumerate(reader):
                if i >= max_rows:
                    break
                rows.append(dict(row))

        lines = [f"CSV: {path.name} ({len(rows)} rows, {len(headers)} columns)"]
        lines.append(f"Columns: {', '.join(headers)}")
        lines.append("First 5 rows:")
        for row in rows[:5]:
            lines.append("  " + " | ".join(f"{k}: {v}" for k, v in list(row.items())[:6]))

        return ToolResult(success=True, message="\n".join(lines), data={"headers": headers, "rows": rows, "count": len(rows)})
    except Exception as e:
        return ToolResult(success=False, error=f"Failed to read CSV: {e}")


@tool(
    name="data_write_csv",
    description="Write a list of dictionaries to a CSV file",
    parameters={
        "path": {"type": "string", "description": "Path to save CSV", "required": True},
        "rows": {"type": "array", "description": "List of dictionaries (each dict = one row)", "required": True},
    },
    category="data",
)
def data_write_csv(params: dict) -> ToolResult:
    path = Path(params.get("path", "")).expanduser().resolve()
    rows = params.get("rows", [])

    if not rows:
        return ToolResult(success=False, error="No rows provided")

    try:
        import csv
        path.parent.mkdir(parents=True, exist_ok=True)
        headers = list(rows[0].keys())

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

        return ToolResult(success=True, message=f"CSV saved: {path} ({len(rows)} rows)", artifacts=[str(path)])
    except Exception as e:
        return ToolResult(success=False, error=f"Failed to write CSV: {e}")


@tool(
    name="data_analyze",
    description="Perform basic statistical analysis on a CSV/JSON dataset: counts, averages, min/max",
    parameters={
        "path": {"type": "string", "description": "Path to CSV or JSON file", "required": True},
        "column": {"type": "string", "description": "Column/field name to analyze (optional)", "required": False},
    },
    category="data",
)
def data_analyze(params: dict) -> ToolResult:
    path = Path(params.get("path", "")).expanduser().resolve()
    column = params.get("column", "")

    if not path.exists():
        return ToolResult(success=False, error=f"File not found: {path}")

    try:
        # Load data
        if path.suffix.lower() == ".json":
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, list):
                rows = data
            else:
                rows = [data]
        else:
            import csv
            with open(path, "r", encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))

        if not rows:
            return ToolResult(success=False, error="No data found in file")

        headers = list(rows[0].keys())
        lines = [f"Dataset: {path.name}", f"  Rows: {len(rows)}", f"  Columns: {', '.join(headers)}"]

        if column and column in headers:
            values = []
            for r in rows:
                try:
                    values.append(float(r[column]))
                except (ValueError, TypeError):
                    pass
            if values:
                lines.append(f"\nColumn '{column}' stats:")
                lines.append(f"  Count: {len(values)}")
                lines.append(f"  Min: {min(values):.2f}")
                lines.append(f"  Max: {max(values):.2f}")
                lines.append(f"  Average: {sum(values)/len(values):.2f}")
                lines.append(f"  Sum: {sum(values):.2f}")
        else:
            # Summary for all numeric columns
            for col in headers[:10]:
                values = []
                for r in rows:
                    try:
                        values.append(float(r[col]))
                    except (ValueError, TypeError):
                        pass
                if values:
                    lines.append(f"\n  {col}: avg={sum(values)/len(values):.2f}, min={min(values):.2f}, max={max(values):.2f}")

        return ToolResult(success=True, message="\n".join(lines), data={"rows": len(rows), "headers": headers})
    except Exception as e:
        return ToolResult(success=False, error=f"Analysis failed: {e}")
