from helpers.utils.context import mcp, __ctx_cache
from mcp.server.fastmcp import Context
from helpers.utils.authentication import get_azure_credentials
from helpers.clients import (
    FabricApiClient,
    WarehouseClient,
)

from typing import Optional


@mcp.tool()
async def set_warehouse(warehouse: str, ctx: Context) -> str:
    """Set the current warehouse for the session.

    Args:
        warehouse: Name or ID of the warehouse
        ctx: Context object containing client information

    Returns:
        A string confirming the warehouse has been set.
    """
    __ctx_cache[f"{ctx.client_id}_warehouse"] = warehouse
    return f"Warehouse set to '{warehouse}'."


@mcp.tool()
async def list_warehouses(workspace: Optional[str] = None, ctx: Context = None) -> str:
    """List all warehouses in a Fabric workspace.

    Args:
        workspace: Name or ID of the workspace (optional)
        ctx: Context object containing client information

    Returns:
        A string containing the list of warehouses or an error message.
    """
    try:
        client = WarehouseClient(
            FabricApiClient(get_azure_credentials(ctx.client_id, __ctx_cache))
        )

        # Retrieve workspace from context if not provided
        workspace_ref = workspace or __ctx_cache.get(f"{ctx.client_id}_workspace")
        if not workspace_ref:
            return "Workspace not set. Please set a workspace using the 'set_workspace' command."

        warehouses = await client.list_warehouses(workspace_ref)

        return warehouses

    except Exception as e:
        return f"Error listing warehouses: {str(e)}"


@mcp.tool()
async def create_warehouse(
    name: str,
    workspace: Optional[str] = None,
    description: Optional[str] = None,
    folder_id: Optional[str] = None,
    ctx: Context = None,
) -> str:
    """Create a new warehouse in a Fabric workspace.

    Args:
        name: Name of the warehouse
        workspace: Name or ID of the workspace (optional)
        description: Description of the warehouse (optional)
        ctx: Context object containing client information
    Returns:
        A string confirming the warehouse has been created or an error message.
    """
    try:
        client = WarehouseClient(
            FabricApiClient(get_azure_credentials(ctx.client_id, __ctx_cache))
        )

        # Retrieve workspace from context if not provided
        workspace_ref = workspace or __ctx_cache.get(f"{ctx.client_id}_workspace")
        if not workspace_ref:
            return "Workspace not set. Please set a workspace using the 'set_workspace' command."

        response = await client.create_warehouse(
            name=name,
            workspace=workspace_ref,
            description=description,
            folder_id=folder_id,
        )

        if response is None:
            return "Error: Warehouse creation returned None response. The warehouse may have been created - please check the workspace."

        if isinstance(response, str):
            return response

        if not isinstance(response, dict):
            return f"Unexpected response when creating warehouse: {type(response).__name__}"

        warehouse_id = response.get("id")
        display_name = response.get("displayName", name)

        if warehouse_id:
            return f"Warehouse '{display_name}' created successfully with ID: {warehouse_id}."

        return f"Warehouse '{display_name}' created, but no ID was returned. Response: {response}"

    except Exception as e:
        return f"Error creating warehouse: {str(e)}"


@mcp.tool()
async def update_warehouse(
    warehouse: str,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> str:
    """Update a warehouse (rename or change description).

    Args:
        warehouse: Name or ID of the warehouse to update
        display_name: New display name (optional)
        description: New description (optional)
        workspace: Name or ID of the workspace (optional)
        ctx: Context object containing client information
    Returns:
        A string confirming the update or an error message.
    """
    try:
        fabric_client = FabricApiClient(get_azure_credentials(ctx.client_id, __ctx_cache))
        workspace_ref = workspace or __ctx_cache.get(f"{ctx.client_id}_workspace")
        if not workspace_ref:
            return "Workspace not set. Please set a workspace using the 'set_workspace' command."

        _, workspace_id = await fabric_client.resolve_workspace_name_and_id(workspace_ref)
        _, warehouse_id = await fabric_client.resolve_item_name_and_id(
            item=warehouse, type="Warehouse", workspace=workspace_id
        )

        await fabric_client.update_item(
            workspace_id=workspace_id,
            item_id=str(warehouse_id),
            item_type="warehouse",
            display_name=display_name,
            description=description,
        )
        return f"Warehouse '{warehouse}' updated successfully."
    except Exception as e:
        return f"Error updating warehouse: {str(e)}"


@mcp.tool()
async def delete_warehouse(
    warehouse: str,
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> str:
    """Delete a warehouse. This is irreversible.

    Args:
        warehouse: Name or ID of the warehouse to delete
        workspace: Name or ID of the workspace (optional)
        ctx: Context object containing client information
    Returns:
        A string confirming deletion or an error message.
    """
    try:
        fabric_client = FabricApiClient(get_azure_credentials(ctx.client_id, __ctx_cache))
        workspace_ref = workspace or __ctx_cache.get(f"{ctx.client_id}_workspace")
        if not workspace_ref:
            return "Workspace not set. Please set a workspace using the 'set_workspace' command."

        _, workspace_id = await fabric_client.resolve_workspace_name_and_id(workspace_ref)
        _, warehouse_id = await fabric_client.resolve_item_name_and_id(
            item=warehouse, type="Warehouse", workspace=workspace_id
        )

        await fabric_client.delete_item(
            workspace_id=workspace_id,
            item_id=str(warehouse_id),
            item_type="warehouse",
        )
        return f"Warehouse '{warehouse}' deleted successfully."
    except Exception as e:
        return f"Error deleting warehouse: {str(e)}"
