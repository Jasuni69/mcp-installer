from helpers.utils.context import mcp, __ctx_cache
from mcp.server.fastmcp import Context
from helpers.utils.authentication import get_azure_credentials
from helpers.clients import (
    FabricApiClient,
    WorkspaceClient,
)


@mcp.tool()
async def set_workspace(workspace: str, ctx: Context) -> str:
    """Set the current workspace for the session.

    Args:
        workspace: Name or ID of the workspace
        ctx: Context object containing client information
    Returns:
        A string confirming the workspace has been set.
    """
    __ctx_cache[f"{ctx.client_id}_workspace"] = workspace
    return f"Workspace set to '{workspace}'."


@mcp.tool()
async def list_workspaces(ctx: Context) -> str:
    """List all available Fabric workspaces.

    Args:
        ctx: Context object containing client information

    Returns:
        A string containing the list of workspaces or an error message.
    """
    try:
        client = WorkspaceClient(
            FabricApiClient(get_azure_credentials(ctx.client_id, __ctx_cache))
        )

        workspaces = await client.list_workspaces()

        return workspaces

    except Exception as e:
        return f"Error listing workspaces: {str(e)}"


@mcp.tool()
async def create_workspace(
    display_name: str,
    capacity_id: str | None = None,
    description: str | None = None,
    domain_id: str | None = None,
    ctx: Context = None,
) -> str:
    """Create a new Fabric workspace.

    Args:
        display_name: Workspace display name
        capacity_id: Optional capacity ID
        description: Optional description
        domain_id: Optional domain identifier
        ctx: Context object containing client information
    Returns:
        A string confirming creation or an error message.
    """
    try:
        client = WorkspaceClient(
            FabricApiClient(get_azure_credentials(ctx.client_id, __ctx_cache))
        )
        resp = await client.create_workspace(
            display_name=display_name,
            capacity_id=capacity_id,
            description=description,
            domain_id=domain_id,
        )

        if isinstance(resp, dict):
            ws_id = resp.get("id", "")
            name = resp.get("displayName", display_name)
            return f"Workspace '{name}' created successfully with ID: {ws_id}."
        return str(resp)
    except Exception as e:
        return f"Error creating workspace: {str(e)}"


@mcp.tool()
async def update_workspace(
    workspace: str,
    display_name: str | None = None,
    description: str | None = None,
    ctx: Context = None,
) -> str:
    """Update an existing Fabric workspace (rename or change description).

    Args:
        workspace: Name or ID of the workspace to update
        display_name: New display name (optional)
        description: New description (optional)
        ctx: Context object containing client information
    Returns:
        A string confirming the update or an error message.
    """
    try:
        fabric_client = FabricApiClient(get_azure_credentials(ctx.client_id, __ctx_cache))
        _, workspace_id = await fabric_client.resolve_workspace_name_and_id(workspace)

        payload = {}
        if display_name is not None:
            payload["displayName"] = display_name
        if description is not None:
            payload["description"] = description

        if not payload:
            return "Nothing to update. Provide display_name or description."

        await fabric_client._make_request(
            endpoint=f"workspaces/{workspace_id}",
            method="PATCH",
            params=payload,
        )
        return f"Workspace '{workspace}' updated successfully."
    except Exception as e:
        return f"Error updating workspace: {str(e)}"


@mcp.tool()
async def delete_workspace(
    workspace: str,
    ctx: Context = None,
) -> str:
    """Delete a Fabric workspace and all items in it. This is irreversible.

    Args:
        workspace: Name or ID of the workspace to delete
        ctx: Context object containing client information
    Returns:
        A string confirming deletion or an error message.
    """
    try:
        fabric_client = FabricApiClient(get_azure_credentials(ctx.client_id, __ctx_cache))
        _, workspace_id = await fabric_client.resolve_workspace_name_and_id(workspace)

        await fabric_client._make_request(
            endpoint=f"workspaces/{workspace_id}",
            method="DELETE",
        )
        return f"Workspace '{workspace}' deleted successfully."
    except Exception as e:
        return f"Error deleting workspace: {str(e)}"