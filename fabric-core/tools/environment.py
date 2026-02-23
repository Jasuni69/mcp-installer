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
async def list_environments(
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """List all environments in a workspace.

    Args:
        workspace: Workspace name or ID. Uses active workspace if not provided.
        ctx: Context object containing client information.

    Returns:
        Dictionary with list of environments (id, displayName, description, etc.).
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/environments"
        )

        environments: List[Dict[str, Any]]
        if isinstance(response, dict):
            environments = response.get("value", [])
        elif isinstance(response, list):
            environments = response
        else:
            environments = []

        return {"environments": environments, "count": len(environments)}
    except Exception as exc:
        logger.error("Failed to list environments in workspace '%s': %s", workspace, exc)
        return {"error": str(exc)}


@mcp.tool()
async def create_environment(
    display_name: str,
    workspace: Optional[str] = None,
    description: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Create a new environment in a workspace.

    Args:
        display_name: Display name for the new environment.
        workspace: Workspace name or ID. Uses active workspace if not provided.
        description: Optional description for the environment.
        ctx: Context object containing client information.

    Returns:
        Dictionary with the created environment details.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        payload: Dict[str, Any] = {"displayName": display_name}
        if description is not None:
            payload["description"] = description

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/environments",
            method="post",
            params=payload,
        )

        return response if isinstance(response, dict) else {"result": response}
    except Exception as exc:
        logger.error(
            "Failed to create environment '%s' in workspace '%s': %s",
            display_name,
            workspace,
            exc,
        )
        return {"error": str(exc)}


@mcp.tool()
async def get_environment(
    environment_id: str,
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Get details for a specific environment.

    Args:
        environment_id: ID of the environment.
        workspace: Workspace name or ID. Uses active workspace if not provided.
        ctx: Context object containing client information.

    Returns:
        Dictionary with environment metadata.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/environments/{environment_id}"
        )

        return response if isinstance(response, dict) else {"result": response}
    except Exception as exc:
        logger.error(
            "Failed to get environment '%s' in workspace '%s': %s",
            environment_id,
            workspace,
            exc,
        )
        return {"error": str(exc)}


@mcp.tool()
async def update_environment(
    environment_id: str,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Update properties of an existing environment.

    Args:
        environment_id: ID of the environment to update.
        display_name: New display name (optional).
        description: New description (optional).
        workspace: Workspace name or ID. Uses active workspace if not provided.
        ctx: Context object containing client information.

    Returns:
        Dictionary with the updated environment details.
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
        fabric_client = FabricApiClient(credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/environments/{environment_id}",
            method="patch",
            params=payload,
        )

        return response if isinstance(response, dict) else {"result": response}
    except Exception as exc:
        logger.error(
            "Failed to update environment '%s' in workspace '%s': %s",
            environment_id,
            workspace,
            exc,
        )
        return {"error": str(exc)}


@mcp.tool()
async def delete_environment(
    environment_id: str,
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Delete an environment from a workspace.

    Args:
        environment_id: ID of the environment to delete.
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
        fabric_client = FabricApiClient(credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/environments/{environment_id}",
            method="delete",
        )

        return {"success": True, "environment_id": environment_id}
    except Exception as exc:
        logger.error(
            "Failed to delete environment '%s' in workspace '%s': %s",
            environment_id,
            workspace,
            exc,
        )
        return {"error": str(exc)}


@mcp.tool()
async def publish_environment(
    environment_id: str,
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Publish a staged environment, making its configuration live.

    This is a long-running operation (LRO). The tool waits for completion
    before returning. Publishing can take several minutes.

    Args:
        environment_id: ID of the environment to publish.
        workspace: Workspace name or ID. Uses active workspace if not provided.
        ctx: Context object containing client information.

    Returns:
        Dictionary with the publish result or an error.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/environments/{environment_id}/staging/publish",
            method="post",
            params={},
            lro=True,
            lro_poll_interval=10,
            lro_timeout=600,
        )

        return response if isinstance(response, dict) else {"result": response}
    except Exception as exc:
        logger.error(
            "Failed to publish environment '%s' in workspace '%s': %s",
            environment_id,
            workspace,
            exc,
        )
        return {"error": str(exc)}


@mcp.tool()
async def cancel_publish_environment(
    environment_id: str,
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Cancel an in-progress publish operation for an environment.

    Args:
        environment_id: ID of the environment whose publish to cancel.
        workspace: Workspace name or ID. Uses active workspace if not provided.
        ctx: Context object containing client information.

    Returns:
        Dictionary confirming cancellation or an error.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/environments/{environment_id}/staging/cancelPublish",
            method="post",
            params={},
        )

        return {
            "success": True,
            "environment_id": environment_id,
            "result": response,
        }
    except Exception as exc:
        logger.error(
            "Failed to cancel publish for environment '%s' in workspace '%s': %s",
            environment_id,
            workspace,
            exc,
        )
        return {"error": str(exc)}
