"""TMDL file parser/writer for PBIP mode.

Minimal parser — extracts names, captions, descriptions, display folders
from .tmdl files. Does not attempt to parse full TMDL grammar.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastmcp import FastMCP

from .connection import get_state, ConnectionMode


def register_tools(mcp: FastMCP) -> None:
    """Register TMDL tools on the MCP server."""

    @mcp.tool()
    def list_tmdl_files(folder_path: str = "") -> list[dict]:
        """List all .tmdl files in a PBIP folder.

        Args:
            folder_path: Override folder. If empty, uses current PBIP connection.
        """
        root = _get_pbip_root(folder_path)
        files = []
        for f in sorted(root.rglob("*.tmdl")):
            rel = f.relative_to(root)
            files.append({
                "path": str(rel),
                "size_bytes": f.stat().st_size,
                "parent_folder": str(rel.parent),
            })
        return files

    @mcp.tool()
    def read_tmdl_model(folder_path: str = "") -> dict:
        """Parse a PBIP/TMDL folder and extract translatable objects.

        Returns structure similar to get_full_metadata() but from files.
        """
        root = _get_pbip_root(folder_path)
        definition_dir = root / "definition"
        if not definition_dir.exists():
            definition_dir = root

        tables_dir = definition_dir / "tables"
        model_tmdl = definition_dir / "model.tmdl"

        inventory: dict = {
            "source": "tmdl",
            "folder": str(root),
            "model_name": "",
            "culture": "",
            "tables": [],
        }

        # Parse model.tmdl for top-level info
        if model_tmdl.exists():
            model_text = model_tmdl.read_text(encoding="utf-8")
            name_match = re.search(r'^model\s+(.+)$', model_text, re.MULTILINE)
            if name_match:
                inventory["model_name"] = _unquote(name_match.group(1).strip())
            culture_match = re.search(r'^\s+culture:\s+(.+)$', model_text, re.MULTILINE)
            if culture_match:
                inventory["culture"] = culture_match.group(1).strip()

        # Parse table files
        if tables_dir.exists():
            for table_dir in sorted(tables_dir.iterdir()):
                if not table_dir.is_dir():
                    # Could be a single .tmdl file for simple tables
                    if table_dir.suffix == ".tmdl":
                        table_data = _parse_table_file(table_dir)
                        if table_data:
                            inventory["tables"].append(table_data)
                    continue

                # Look for definition.tmdl in the table directory
                table_def = table_dir / "definition.tmdl"
                if not table_def.exists():
                    # Try the table name as filename
                    candidates = list(table_dir.glob("*.tmdl"))
                    if candidates:
                        table_def = candidates[0]
                    else:
                        continue

                table_data = _parse_table_file(table_def)
                if table_data:
                    # Also look for separate measure/column files
                    for sub_tmdl in table_dir.glob("*.tmdl"):
                        if sub_tmdl == table_def:
                            continue
                        _parse_sub_objects(sub_tmdl, table_data)
                    inventory["tables"].append(table_data)

        return inventory

    @mcp.tool()
    def write_tmdl_culture(
        culture_name: str,
        translations: list[dict],
        folder_path: str = "",
    ) -> dict:
        """Write a culture .tmdl file with translations.

        Args:
            culture_name: e.g. 'sv-SE'
            translations: List of dicts with object_type, table_name, object_name,
                         property_type, value
            folder_path: Override folder. If empty, uses current PBIP connection.
        """
        root = _get_pbip_root(folder_path)
        definition_dir = root / "definition"
        if not definition_dir.exists():
            definition_dir = root

        cultures_dir = definition_dir / "cultures"
        cultures_dir.mkdir(parents=True, exist_ok=True)

        culture_file = cultures_dir / f"{culture_name}.tmdl"

        lines = [f"culture {culture_name}", ""]

        # Group translations by table
        by_table: dict[str, list[dict]] = {}
        table_level: list[dict] = []

        for t in translations:
            obj_type = t.get("object_type", "").lower()
            table_name = t.get("table_name", "")
            if obj_type == "table":
                table_level.append(t)
            else:
                by_table.setdefault(table_name, []).append(t)

        # Write table-level translations
        for t in table_level:
            table_name = t.get("table_name", "")
            prop = t.get("property_type", "Caption").lower()
            value = t.get("value", "")
            lines.append(f"\tlinguisticMetadata = table '{table_name}'")
            lines.append(f"\t\t{prop}: {_quote(value)}")
            lines.append("")

        # Write object-level translations
        for table_name, trans_list in sorted(by_table.items()):
            for t in trans_list:
                obj_type = t.get("object_type", "").lower()
                obj_name = t.get("object_name", "")
                prop = t.get("property_type", "Caption").lower()
                value = t.get("value", "")

                if obj_type == "column":
                    lines.append(f"\tlinguisticMetadata = table '{table_name}' > column '{obj_name}'")
                elif obj_type == "measure":
                    lines.append(f"\tlinguisticMetadata = table '{table_name}' > measure '{obj_name}'")
                elif obj_type == "hierarchy":
                    lines.append(f"\tlinguisticMetadata = table '{table_name}' > hierarchy '{obj_name}'")
                else:
                    lines.append(f"\tlinguisticMetadata = table '{table_name}' > {obj_type} '{obj_name}'")

                lines.append(f"\t\t{prop}: {_quote(value)}")
                lines.append("")

        content = "\n".join(lines)
        culture_file.write_text(content, encoding="utf-8")

        return {
            "status": "written",
            "file": str(culture_file),
            "culture": culture_name,
            "translation_count": len(translations),
        }


def _get_pbip_root(folder_path: str) -> Path:
    """Get PBIP root from arg or current connection."""
    if folder_path:
        p = Path(folder_path)
        if not p.exists():
            raise RuntimeError(f"Folder not found: {folder_path}")
        return p

    state = get_state()
    if state.mode != ConnectionMode.PBIP or not state.pbip_folder:
        raise RuntimeError("No PBIP folder. Provide folder_path or use connect_pbip first.")
    return Path(state.pbip_folder)


def _unquote(s: str) -> str:
    """Remove TMDL quotes from a string."""
    s = s.strip()
    if s.startswith("'") and s.endswith("'"):
        return s[1:-1]
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    return s


def _quote(s: str) -> str:
    """Quote a string for TMDL."""
    if "'" in s:
        return f'"{s}"'
    return f"'{s}'"


def _parse_table_file(path: Path) -> dict | None:
    """Parse a .tmdl file for table definition."""
    text = path.read_text(encoding="utf-8")

    table_match = re.search(r'^table\s+(.+)$', text, re.MULTILINE)
    if not table_match:
        return None

    table_name = _unquote(table_match.group(1).strip())

    table_data: dict = {
        "name": table_name,
        "description": "",
        "is_hidden": False,
        "columns": [],
        "measures": [],
        "hierarchies": [],
    }

    # Extract description
    desc_match = re.search(r'^\s+description:\s*(.+)$', text, re.MULTILINE)
    if desc_match:
        table_data["description"] = _unquote(desc_match.group(1).strip())

    # Extract isHidden
    if re.search(r'^\s+isHidden\s*$', text, re.MULTILINE):
        table_data["is_hidden"] = True

    # Parse columns
    for col_match in re.finditer(r'^\tcolumn\s+(.+)$', text, re.MULTILINE):
        col_name = _unquote(col_match.group(1).strip())
        col_block = _get_block(text, col_match.start())
        col_data = {
            "name": col_name,
            "description": _extract_prop(col_block, "description"),
            "display_folder": _extract_prop(col_block, "displayFolder"),
            "is_hidden": "isHidden" in col_block,
            "data_type": _extract_prop(col_block, "dataType"),
            "type": "Data",
        }
        table_data["columns"].append(col_data)

    # Parse measures
    for m_match in re.finditer(r'^\tmeasure\s+(.+)$', text, re.MULTILINE):
        m_name = _unquote(m_match.group(1).strip())
        m_block = _get_block(text, m_match.start())
        m_data = {
            "name": m_name,
            "description": _extract_prop(m_block, "description"),
            "display_folder": _extract_prop(m_block, "displayFolder"),
            "is_hidden": "isHidden" in m_block,
            "expression_snippet": "",
        }
        table_data["measures"].append(m_data)

    # Parse hierarchies
    for h_match in re.finditer(r'^\thierarchy\s+(.+)$', text, re.MULTILINE):
        h_name = _unquote(h_match.group(1).strip())
        h_block = _get_block(text, h_match.start())
        levels = []
        for lv_match in re.finditer(r'level\s+(.+)$', h_block, re.MULTILINE):
            levels.append({
                "name": _unquote(lv_match.group(1).strip()),
                "ordinal": len(levels),
                "column": "",
            })
        h_data = {
            "name": h_name,
            "description": _extract_prop(h_block, "description"),
            "display_folder": _extract_prop(h_block, "displayFolder"),
            "is_hidden": "isHidden" in h_block,
            "levels": levels,
        }
        table_data["hierarchies"].append(h_data)

    return table_data


def _parse_sub_objects(path: Path, table_data: dict) -> None:
    """Parse additional .tmdl files in a table directory for columns/measures."""
    text = path.read_text(encoding="utf-8")

    for col_match in re.finditer(r'^column\s+(.+)$', text, re.MULTILINE):
        col_name = _unquote(col_match.group(1).strip())
        col_block = _get_block(text, col_match.start())
        table_data["columns"].append({
            "name": col_name,
            "description": _extract_prop(col_block, "description"),
            "display_folder": _extract_prop(col_block, "displayFolder"),
            "is_hidden": "isHidden" in col_block,
            "data_type": _extract_prop(col_block, "dataType"),
            "type": "Data",
        })

    for m_match in re.finditer(r'^measure\s+(.+)$', text, re.MULTILINE):
        m_name = _unquote(m_match.group(1).strip())
        m_block = _get_block(text, m_match.start())
        table_data["measures"].append({
            "name": m_name,
            "description": _extract_prop(m_block, "description"),
            "display_folder": _extract_prop(m_block, "displayFolder"),
            "is_hidden": "isHidden" in m_block,
            "expression_snippet": "",
        })


def _get_block(text: str, start: int) -> str:
    """Get the indented block following an object declaration."""
    lines = text[start:].split("\n")
    if not lines:
        return ""

    block_lines = [lines[0]]
    base_indent = len(lines[0]) - len(lines[0].lstrip())

    for line in lines[1:]:
        if not line.strip():
            block_lines.append(line)
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= base_indent:
            break
        block_lines.append(line)

    return "\n".join(block_lines)


def _extract_prop(block: str, prop_name: str) -> str:
    """Extract a property value from a TMDL block."""
    pattern = rf'^\s+{prop_name}:\s*(.+)$'
    match = re.search(pattern, block, re.MULTILINE)
    if match:
        return _unquote(match.group(1).strip())
    return ""
