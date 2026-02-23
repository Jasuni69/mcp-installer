"""CRUD operations for TOM cultures and translations."""

from __future__ import annotations

from fastmcp import FastMCP

from .connection import require_tom_connected


def register_tools(mcp: FastMCP) -> None:
    """Register all translation tools on the MCP server."""

    @mcp.tool()
    def list_cultures() -> list[dict]:
        """List all cultures (translations) in the model with counts."""
        state = require_tom_connected()
        model = state.model

        cultures = []
        for culture in model.Cultures:
            trans_count = culture.ObjectTranslations.Count if culture.ObjectTranslations else 0
            cultures.append({
                "name": culture.Name,
                "translation_count": trans_count,
            })

        return cultures

    @mcp.tool()
    def add_culture(culture_name: str) -> dict:
        """Add a new culture to the model (e.g. 'sv-SE').

        If the culture already exists, returns info about it instead.
        """
        state = require_tom_connected()
        model = state.model

        from Microsoft.AnalysisServices.Tabular import Culture  # type: ignore

        existing = model.Cultures.Find(culture_name)
        if existing is not None:
            return {
                "status": "already_exists",
                "culture": culture_name,
                "translation_count": existing.ObjectTranslations.Count,
            }

        new_culture = Culture()
        new_culture.Name = culture_name
        model.Cultures.Add(new_culture)
        model.SaveChanges()

        return {
            "status": "created",
            "culture": culture_name,
        }

    @mcp.tool()
    def get_translations(culture_name: str) -> dict:
        """Get all translations for a specific culture.

        Returns organized by object type (table, column, measure, hierarchy).
        """
        state = require_tom_connected()
        model = state.model

        culture = model.Cultures.Find(culture_name)
        if culture is None:
            raise ValueError(f"Culture '{culture_name}' not found. Use add_culture first.")


        translations: list[dict] = []
        for ot in culture.ObjectTranslations:
            obj = ot.Object

            # Figure out what kind of object this is
            parent_table = ""
            object_name = ""
            object_type = type(obj).__name__

            if hasattr(obj, "Table") and obj.Table is not None:
                parent_table = obj.Table.Name
            elif hasattr(obj, "Parent") and obj.Parent is not None:
                if hasattr(obj.Parent, "Name"):
                    parent_table = obj.Parent.Name

            if hasattr(obj, "Name"):
                object_name = obj.Name

            prop_type = str(ot.Property)

            translations.append({
                "object_type": object_type,
                "table": parent_table,
                "object_name": object_name,
                "property": prop_type,
                "value": ot.Value if ot.Value else "",
            })

        return {
            "culture": culture_name,
            "count": len(translations),
            "translations": translations,
        }

    @mcp.tool()
    def set_translation(
        culture_name: str,
        object_type: str,
        table_name: str,
        object_name: str,
        property_type: str = "Caption",
        value: str = "",
    ) -> dict:
        """Set a single translation for a model object.

        Args:
            culture_name: Target culture (e.g. 'sv-SE')
            object_type: One of 'Table', 'Column', 'Measure', 'Hierarchy', 'Level'
            table_name: Parent table name
            object_name: Name of the object (for Table type, same as table_name)
            property_type: 'Caption', 'Description', or 'DisplayFolder'
            value: Translated text
        """
        state = require_tom_connected()
        model = state.model

        from Microsoft.AnalysisServices.Tabular import (  # type: ignore
            ObjectTranslation,
            TranslatedProperty,
        )

        culture = model.Cultures.Find(culture_name)
        if culture is None:
            raise ValueError(f"Culture '{culture_name}' not found.")

        # Resolve the target object
        tom_obj = _resolve_object(model, object_type, table_name, object_name)

        # Map property string to enum
        prop = _parse_property(property_type)

        # TOM pattern: remove existing translation, then add new one
        # pythonnet: ObjectTranslationCollection.Find() not available
        existing = _find_translation(culture, tom_obj, prop)
        if existing is not None:
            culture.ObjectTranslations.Remove(existing)

        if value:  # Only add if non-empty
            new_trans = ObjectTranslation()
            new_trans.Object = tom_obj
            new_trans.Property = prop
            new_trans.Value = value
            culture.ObjectTranslations.Add(new_trans)

        model.SaveChanges()

        return {
            "status": "set",
            "culture": culture_name,
            "object_type": object_type,
            "table": table_name,
            "object_name": object_name,
            "property": property_type,
            "value": value,
        }

    @mcp.tool()
    def set_translations_bulk(
        culture_name: str,
        translations: list[dict],
    ) -> dict:
        """Bulk-apply translations in a single SaveChanges() call.

        Each item in translations should have:
            object_type, table_name, object_name, property_type, value

        This is much faster than calling set_translation one at a time.
        """
        state = require_tom_connected()
        model = state.model

        from Microsoft.AnalysisServices.Tabular import (  # type: ignore
            ObjectTranslation,
            TranslatedProperty,
        )

        culture = model.Cultures.Find(culture_name)
        if culture is None:
            raise ValueError(f"Culture '{culture_name}' not found. Use add_culture first.")

        results: list[dict] = []
        errors: list[dict] = []

        for t in translations:
            obj_type = t.get("object_type", "")
            table_name = t.get("table_name", "")
            obj_name = t.get("object_name", "")
            prop_type = t.get("property_type", "Caption")
            value = t.get("value", "")

            try:
                tom_obj = _resolve_object(model, obj_type, table_name, obj_name)
                prop = _parse_property(prop_type)

                # pythonnet: ObjectTranslationCollection.Find() not available
                # Iterate to find and remove existing translation
                existing = _find_translation(culture, tom_obj, prop)
                if existing is not None:
                    culture.ObjectTranslations.Remove(existing)

                if value:
                    new_trans = ObjectTranslation()
                    new_trans.Object = tom_obj
                    new_trans.Property = prop
                    new_trans.Value = value
                    culture.ObjectTranslations.Add(new_trans)

                results.append({
                    "object": f"{table_name}.{obj_name}",
                    "property": prop_type,
                    "status": "ok",
                })
            except Exception as e:
                errors.append({
                    "object": f"{table_name}.{obj_name}",
                    "property": prop_type,
                    "error": str(e),
                })

        # Single save for all translations
        model.SaveChanges()

        return {
            "culture": culture_name,
            "applied": len(results),
            "errors": len(errors),
            "error_details": errors if errors else [],
        }

    @mcp.tool()
    def remove_culture(culture_name: str) -> dict:
        """Remove a culture and all its translations from the model."""
        state = require_tom_connected()
        model = state.model

        culture = model.Cultures.Find(culture_name)
        if culture is None:
            raise ValueError(f"Culture '{culture_name}' not found.")

        trans_count = culture.ObjectTranslations.Count
        model.Cultures.Remove(culture)
        model.SaveChanges()

        return {
            "status": "removed",
            "culture": culture_name,
            "translations_removed": trans_count,
        }


def _find_translation(culture, tom_obj, prop):
    """Find existing ObjectTranslation by iterating (pythonnet-safe).

    ObjectTranslationCollection.Find() is not available in pythonnet,
    so we iterate through the collection manually.
    """
    for ot in culture.ObjectTranslations:
        if ot.Object == tom_obj and ot.Property == prop:
            return ot
    return None


def _resolve_object(model, object_type: str, table_name: str, object_name: str):
    """Find a TOM object by type, table, and name."""
    table = model.Tables.Find(table_name)
    if table is None and object_type.lower() != "model":
        raise ValueError(f"Table '{table_name}' not found.")

    otype = object_type.lower()

    if otype == "table":
        return table
    elif otype == "column":
        col = table.Columns.Find(object_name)
        if col is None:
            raise ValueError(f"Column '{object_name}' not found in table '{table_name}'.")
        return col
    elif otype == "measure":
        m = table.Measures.Find(object_name)
        if m is None:
            raise ValueError(f"Measure '{object_name}' not found in table '{table_name}'.")
        return m
    elif otype == "hierarchy":
        h = table.Hierarchies.Find(object_name)
        if h is None:
            raise ValueError(f"Hierarchy '{object_name}' not found in table '{table_name}'.")
        return h
    elif otype == "level":
        # Levels are nested: need to search all hierarchies in the table
        for h in table.Hierarchies:
            for lv in h.Levels:
                if lv.Name == object_name:
                    return lv
        raise ValueError(f"Level '{object_name}' not found in any hierarchy in table '{table_name}'.")
    else:
        raise ValueError(f"Unknown object_type: '{object_type}'. Use Table/Column/Measure/Hierarchy/Level.")


def _parse_property(property_type: str):
    """Convert property string to TOM TranslatedProperty enum."""
    from Microsoft.AnalysisServices.Tabular import TranslatedProperty  # type: ignore

    mapping = {
        "caption": TranslatedProperty.Caption,
        "description": TranslatedProperty.Description,
        "displayfolder": TranslatedProperty.DisplayFolder,
        "display_folder": TranslatedProperty.DisplayFolder,
    }

    key = property_type.lower().strip()
    if key not in mapping:
        raise ValueError(f"Unknown property_type: '{property_type}'. Use Caption/Description/DisplayFolder.")
    return mapping[key]
