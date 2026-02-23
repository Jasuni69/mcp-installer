import json
from typing import Any, Dict, List, Optional

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
async def list_spark_job_definitions(
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """List all Spark Job Definitions in a workspace.

    Args:
        workspace: Workspace name or ID. Uses active workspace if not provided.
        ctx: Context object containing client information.

    Returns:
        Dictionary with list of Spark Job Definitions and count.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/sparkJobDefinitions"
        )

        items: List[Dict[str, Any]]
        if isinstance(response, dict):
            items = response.get("value", [])
        elif isinstance(response, list):
            items = response
        else:
            items = []

        return {"sparkJobDefinitions": items, "count": len(items)}
    except Exception as exc:
        logger.error("Failed to list Spark Job Definitions: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def create_spark_job_definition(
    display_name: str,
    workspace: Optional[str] = None,
    description: Optional[str] = None,
    definition: Optional[str] = None,
    folder_id: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Create a new Spark Job Definition in a workspace.

    Args:
        display_name: Display name for the new Spark Job Definition.
        workspace: Workspace name or ID. Uses active workspace if not provided.
        description: Optional description.
        definition: Optional JSON string with the Spark Job Definition content.
                    Format: {"format": "SparkJobDefinitionV1" or "SparkJobDefinitionV2",
                             "parts": [{"path": "...", "payload": "base64...",
                                        "payloadType": "InlineBase64"}]}
        folder_id: Optional folder ID to place the item in.
        ctx: Context object containing client information.

    Returns:
        Dictionary with the created Spark Job Definition details.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        payload: Dict[str, Any] = {"displayName": display_name}
        if description is not None:
            payload["description"] = description
        if definition is not None:
            payload["definition"] = json.loads(definition)
        if folder_id is not None:
            payload["folderId"] = folder_id

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/sparkJobDefinitions",
            method="post",
            params=payload,
            lro=True,
            lro_poll_interval=5,
            lro_timeout=300,
        )

        return response if isinstance(response, dict) else {"result": response}
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in definition parameter: %s", exc)
        return {"error": f"Invalid JSON in definition: {exc}"}
    except Exception as exc:
        logger.error("Failed to create Spark Job Definition '%s': %s", display_name, exc)
        return {"error": str(exc)}


@mcp.tool()
async def get_spark_job_definition(
    spark_job_definition_id: str,
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Get details for a specific Spark Job Definition.

    Args:
        spark_job_definition_id: ID of the Spark Job Definition.
        workspace: Workspace name or ID. Uses active workspace if not provided.
        ctx: Context object containing client information.

    Returns:
        Dictionary with Spark Job Definition metadata.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/sparkJobDefinitions/{spark_job_definition_id}"
        )

        return response if isinstance(response, dict) else {"result": response}
    except Exception as exc:
        logger.error(
            "Failed to get Spark Job Definition '%s': %s", spark_job_definition_id, exc
        )
        return {"error": str(exc)}


@mcp.tool()
async def update_spark_job_definition(
    spark_job_definition_id: str,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Update properties of an existing Spark Job Definition.

    Args:
        spark_job_definition_id: ID of the Spark Job Definition to update.
        display_name: New display name (optional).
        description: New description (optional).
        workspace: Workspace name or ID. Uses active workspace if not provided.
        ctx: Context object containing client information.

    Returns:
        Dictionary with the updated Spark Job Definition details.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        payload: Dict[str, Any] = {}
        if display_name is not None:
            payload["displayName"] = display_name
        if description is not None:
            payload["description"] = description

        if not payload:
            return {"error": "Nothing to update. Provide display_name or description."}

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/sparkJobDefinitions/{spark_job_definition_id}",
            method="patch",
            params=payload,
        )

        return response if isinstance(response, dict) else {"result": response}
    except Exception as exc:
        logger.error(
            "Failed to update Spark Job Definition '%s': %s", spark_job_definition_id, exc
        )
        return {"error": str(exc)}


@mcp.tool()
async def delete_spark_job_definition(
    spark_job_definition_id: str,
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Delete a Spark Job Definition.

    Args:
        spark_job_definition_id: ID of the Spark Job Definition to delete.
        workspace: Workspace name or ID. Uses active workspace if not provided.
        ctx: Context object containing client information.

    Returns:
        Dictionary confirming deletion or an error.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/sparkJobDefinitions/{spark_job_definition_id}",
            method="delete",
        )

        return {"success": True, "spark_job_definition_id": spark_job_definition_id}
    except Exception as exc:
        logger.error(
            "Failed to delete Spark Job Definition '%s': %s", spark_job_definition_id, exc
        )
        return {"error": str(exc)}


@mcp.tool()
async def get_spark_job_definition_definition(
    spark_job_definition_id: str,
    workspace: Optional[str] = None,
    format: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Get the content definition of a Spark Job Definition (parts and payloads).

    This is a long-running operation that retrieves the underlying definition
    including base64-encoded file contents.

    Args:
        spark_job_definition_id: ID of the Spark Job Definition.
        workspace: Workspace name or ID. Uses active workspace if not provided.
        format: Optional format version. "SparkJobDefinitionV1" or "SparkJobDefinitionV2".
        ctx: Context object containing client information.

    Returns:
        Dictionary with the Spark Job Definition content definition.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        endpoint = f"workspaces/{ws_id}/sparkJobDefinitions/{spark_job_definition_id}/getDefinition"
        if format is not None:
            endpoint = f"{endpoint}?format={format}"

        response = await fabric_client._make_request(
            endpoint=endpoint,
            method="post",
            params={},
            lro=True,
        )

        return response if isinstance(response, dict) else {"result": response}
    except Exception as exc:
        logger.error(
            "Failed to get definition for Spark Job Definition '%s': %s",
            spark_job_definition_id,
            exc,
        )
        return {"error": str(exc)}


@mcp.tool()
async def update_spark_job_definition_definition(
    spark_job_definition_id: str,
    definition: str,
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Update the content definition of a Spark Job Definition.

    This replaces the underlying definition (files, entry point, etc.)
    and is a long-running operation.

    Args:
        spark_job_definition_id: ID of the Spark Job Definition to update.
        definition: JSON string with the new definition.
                    Format: {"format": "SparkJobDefinitionV1" or "SparkJobDefinitionV2",
                             "parts": [{"path": "...", "payload": "base64...",
                                        "payloadType": "InlineBase64"}]}
        workspace: Workspace name or ID. Uses active workspace if not provided.
        ctx: Context object containing client information.

    Returns:
        Dictionary with the result or an error.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        parsed_definition = json.loads(definition)

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/sparkJobDefinitions/{spark_job_definition_id}/updateDefinition",
            method="post",
            params=parsed_definition,
            lro=True,
        )

        return response if isinstance(response, dict) else {"result": response}
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in definition parameter: %s", exc)
        return {"error": f"Invalid JSON in definition: {exc}"}
    except Exception as exc:
        logger.error(
            "Failed to update definition for Spark Job Definition '%s': %s",
            spark_job_definition_id,
            exc,
        )
        return {"error": str(exc)}
