import json
from typing import Any, Dict, Optional

from mcp.server.fastmcp import Context

from helpers.clients import FabricApiClient
from helpers.logging_config import get_logger
from helpers.utils.authentication import get_azure_credentials
from helpers.utils.context import mcp, __ctx_cache


logger = get_logger(__name__)


def _resolve_workspace(ctx: Context, workspace: Optional[str]) -> str:
    ws = workspace or __ctx_cache.get(f"{ctx.client_id}_workspace")
    if not ws:
        raise ValueError(
            "Workspace not set. Provide a workspace parameter or call set_workspace first."
        )
    return ws


@mcp.tool()
async def export_item_definition(
    item_id: str,
    workspace: Optional[str] = None,
    format: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Export the definition of any Fabric item (Notebook, SemanticModel, DataPipeline, etc.).

    Returns the raw definition including Base64-encoded part payloads. The API may
    respond synchronously (200) or asynchronously (202 LRO) depending on item type.

    Args:
        item_id: ID of the item to export
        workspace: Workspace name or ID (uses active workspace if not provided)
        format: Optional format hint (e.g. "ipynb" for notebooks). Item-type-specific.
        ctx: MCP context
    """
    try:
        if ctx is None:
            raise ValueError("Context is required for exporting item definitions.")

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        endpoint = f"workspaces/{ws_id}/items/{item_id}/getDefinition"
        query_params: Dict[str, str] = {}
        if format:
            query_params["format"] = format

        response = await fabric_client._make_request(
            endpoint=endpoint,
            method="post",
            params=query_params if query_params else None,
            lro=True,
            lro_poll_interval=3,
            lro_timeout=300,
        )

        return response if isinstance(response, dict) else {"result": response}
    except Exception as exc:
        logger.error("Failed to export definition for item '%s': %s", item_id, exc)
        return {"error": str(exc)}


@mcp.tool()
async def import_item(
    display_name: str,
    item_type: str,
    workspace: Optional[str] = None,
    description: Optional[str] = None,
    definition: Optional[str] = None,
    folder_id: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Create a new Fabric item, optionally seeding it with a definition.

    Use this to import items exported via export_item_definition, or to create items
    from a known definition structure. Supports any item type that the Fabric REST API
    accepts via POST /workspaces/{workspaceId}/items.

    Args:
        display_name: Display name for the new item
        item_type: Item type — Lakehouse, Notebook, SemanticModel, Report,
                   DataPipeline, SparkJobDefinition, Environment, Warehouse, etc.
        workspace: Workspace name or ID (uses active workspace if not provided)
        description: Optional description
        definition: JSON string with the item definition.
                    Expected shape: {"parts": [{"path": "...", "payload": "base64...",
                    "payloadType": "InlineBase64"}]}
        folder_id: Optional folder ID to place the item into
        ctx: MCP context
    """
    try:
        if ctx is None:
            raise ValueError("Context is required for importing items.")

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        payload: Dict[str, Any] = {
            "displayName": display_name,
            "type": item_type,
        }
        if description is not None:
            payload["description"] = description
        if definition is not None:
            payload["definition"] = json.loads(definition)
        if folder_id is not None:
            payload["folderId"] = folder_id

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/items",
            method="post",
            params=payload,
            lro=True,
            lro_poll_interval=5,
            lro_timeout=300,
        )

        return response if isinstance(response, dict) else {"result": response}
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in definition for item '%s': %s", display_name, exc)
        return {"error": f"definition is not valid JSON: {exc}"}
    except Exception as exc:
        logger.error("Failed to import item '%s' (type=%s): %s", display_name, item_type, exc)
        return {"error": str(exc)}


@mcp.tool()
async def update_item_definition(
    item_id: str,
    definition: str,
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Update the definition of an existing Fabric item.

    Replaces the item's current definition with the supplied one. The definition
    must include all parts required by the item type — partial updates are not
    supported by the Fabric API.

    Args:
        item_id: ID of the item to update
        definition: JSON string with the full item definition.
                    Expected shape: {"parts": [{"path": "...", "payload": "base64...",
                    "payloadType": "InlineBase64"}]}
        workspace: Workspace name or ID (uses active workspace if not provided)
        ctx: MCP context
    """
    try:
        if ctx is None:
            raise ValueError("Context is required for updating item definitions.")

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        parsed_definition = json.loads(definition)
        payload: Dict[str, Any] = {"definition": parsed_definition}

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/items/{item_id}/updateDefinition",
            method="post",
            params=payload,
            lro=True,
            lro_poll_interval=5,
            lro_timeout=300,
        )

        return response if isinstance(response, dict) else {"result": response}
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in definition for item '%s': %s", item_id, exc)
        return {"error": f"definition is not valid JSON: {exc}"}
    except Exception as exc:
        logger.error("Failed to update definition for item '%s': %s", item_id, exc)
        return {"error": str(exc)}
