"""Read model metadata via TOM API — tables, columns, measures, hierarchies."""

from __future__ import annotations

from fastmcp import FastMCP

from .connection import require_tom_connected


def register_tools(mcp: FastMCP) -> None:
    """Register all metadata-reading tools on the MCP server."""

    @mcp.tool()
    def get_model_info() -> dict:
        """Get high-level model info: name, compat level, culture, object counts."""
        state = require_tom_connected()
        db = state.database
        model = state.model

        return {
            "database_name": db.Name,
            "model_name": model.Name,
            "compatibility_level": db.CompatibilityLevel,
            "culture": model.Culture if model.Culture else "",
            "description": model.Description if model.Description else "",
            "table_count": model.Tables.Count,
            "relationship_count": model.Relationships.Count,
            "culture_count": model.Cultures.Count,
        }

    @mcp.tool()
    def list_tables() -> list[dict]:
        """List all tables with description, visibility, and column/measure counts."""
        state = require_tom_connected()
        model = state.model
        tables = []

        for table in model.Tables:
            tables.append({
                "name": table.Name,
                "description": table.Description if table.Description else "",
                "is_hidden": table.IsHidden,
                "column_count": table.Columns.Count,
                "measure_count": table.Measures.Count,
                "hierarchy_count": table.Hierarchies.Count,
            })

        return tables

    @mcp.tool()
    def list_columns(table_name: str) -> list[dict]:
        """List all columns in a table with type, displayFolder, visibility."""
        state = require_tom_connected()
        model = state.model

        table = model.Tables.Find(table_name)
        if table is None:
            raise ValueError(f"Table '{table_name}' not found.")

        columns = []
        for col in table.Columns:
            columns.append({
                "name": col.Name,
                "data_type": str(col.DataType),
                "description": col.Description if col.Description else "",
                "display_folder": col.DisplayFolder if col.DisplayFolder else "",
                "is_hidden": col.IsHidden,
                "type": str(col.Type),
            })

        return columns

    @mcp.tool()
    def list_measures(table_name: str) -> list[dict]:
        """List all measures in a table with expression snippet and displayFolder."""
        state = require_tom_connected()
        model = state.model

        table = model.Tables.Find(table_name)
        if table is None:
            raise ValueError(f"Table '{table_name}' not found.")

        measures = []
        for m in table.Measures:
            expr = m.Expression if m.Expression else ""
            # Truncate long DAX expressions for readability
            snippet = expr[:200] + "..." if len(expr) > 200 else expr

            measures.append({
                "name": m.Name,
                "description": m.Description if m.Description else "",
                "display_folder": m.DisplayFolder if m.DisplayFolder else "",
                "expression_snippet": snippet,
                "is_hidden": m.IsHidden,
            })

        return measures

    @mcp.tool()
    def list_hierarchies(table_name: str) -> list[dict]:
        """List all hierarchies in a table with their levels."""
        state = require_tom_connected()
        model = state.model

        table = model.Tables.Find(table_name)
        if table is None:
            raise ValueError(f"Table '{table_name}' not found.")

        hierarchies = []
        for h in table.Hierarchies:
            levels = []
            for lv in h.Levels:
                levels.append({
                    "name": lv.Name,
                    "ordinal": lv.Ordinal,
                    "column": lv.Column.Name if lv.Column else "",
                })
            hierarchies.append({
                "name": h.Name,
                "description": h.Description if h.Description else "",
                "display_folder": h.DisplayFolder if h.DisplayFolder else "",
                "is_hidden": h.IsHidden,
                "levels": levels,
            })

        return hierarchies

    @mcp.tool()
    def get_full_metadata() -> dict:
        """Get complete model inventory as single JSON blob.

        Returns all tables, columns, measures, and hierarchies.
        Use for pipeline/inventory.json generation.
        """
        state = require_tom_connected()
        model = state.model
        db = state.database

        inventory = {
            "database_name": db.Name,
            "model_name": model.Name,
            "compatibility_level": db.CompatibilityLevel,
            "culture": model.Culture if model.Culture else "",
            "tables": [],
        }

        for table in model.Tables:
            t_data: dict = {
                "name": table.Name,
                "description": table.Description if table.Description else "",
                "is_hidden": table.IsHidden,
                "columns": [],
                "measures": [],
                "hierarchies": [],
            }

            for col in table.Columns:
                t_data["columns"].append({
                    "name": col.Name,
                    "data_type": str(col.DataType),
                    "description": col.Description if col.Description else "",
                    "display_folder": col.DisplayFolder if col.DisplayFolder else "",
                    "is_hidden": col.IsHidden,
                    "type": str(col.Type),
                })

            for m in table.Measures:
                expr = m.Expression if m.Expression else ""
                snippet = expr[:200] + "..." if len(expr) > 200 else expr
                t_data["measures"].append({
                    "name": m.Name,
                    "description": m.Description if m.Description else "",
                    "display_folder": m.DisplayFolder if m.DisplayFolder else "",
                    "expression_snippet": snippet,
                    "is_hidden": m.IsHidden,
                })

            for h in table.Hierarchies:
                levels = []
                for lv in h.Levels:
                    levels.append({
                        "name": lv.Name,
                        "ordinal": lv.Ordinal,
                        "column": lv.Column.Name if lv.Column else "",
                    })
                t_data["hierarchies"].append({
                    "name": h.Name,
                    "description": h.Description if h.Description else "",
                    "display_folder": h.DisplayFolder if h.DisplayFolder else "",
                    "is_hidden": h.IsHidden,
                    "levels": levels,
                })

            inventory["tables"].append(t_data)

        return inventory
