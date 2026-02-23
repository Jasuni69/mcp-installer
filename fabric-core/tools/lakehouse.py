from helpers.utils.context import mcp, __ctx_cache
from mcp.server.fastmcp import Context
from helpers.utils.authentication import get_azure_credentials
from helpers.clients import (
    FabricApiClient,
    LakehouseClient,
)
from helpers.logging_config import get_logger

# import sempy_labs as labs
# import sempy_labs.lakehouse as slh

from typing import Any, Dict, List, Optional

logger = get_logger(__name__)


@mcp.tool()
async def set_lakehouse(lakehouse: str, ctx: Context) -> str:
    """Set the current lakehouse for the session.

    Args:
        lakehouse: Name or ID of the lakehouse
        ctx: Context object containing client information

    Returns:
        A string confirming the lakehouse has been set.
    """
    __ctx_cache[f"{ctx.client_id}_lakehouse"] = lakehouse
    return f"Lakehouse set to '{lakehouse}'."


@mcp.tool()
async def list_lakehouses(workspace: Optional[str] = None, ctx: Context = None) -> str:
    """List all lakehouses in a Fabric workspace.

    Args:
        workspace: Name or ID of the workspace (optional)
        ctx: Context object containing client information

    Returns:
        A string containing the list of lakehouses or an error message.
    """
    try:
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)
        lakehouse_client = LakehouseClient(client=fabric_client)
        ws = workspace or __ctx_cache.get(f"{ctx.client_id}_workspace")
        if not ws:
            return "Workspace not set. Please set a workspace using the 'set_workspace' command."
        return await lakehouse_client.list_lakehouses(workspace=ws)
    except Exception as e:
        logger.error(f"Error listing lakehouses: {e}")
        return f"Error listing lakehouses: {e}"


# @mcp.tool()
# async def list_lakehouses_semantic_link(workspace: Optional[str] = None, ctx: Context = None) -> str:
#     """List all lakehouses in a Fabric workspace using semantic-link-labs."""
#     try:
#         manager = LakehouseManager()
#         lakehouses = manager.list_lakehouses(workspace_id=workspace or __ctx_cache.get(f"{ctx.client_id}_workspace"))
#         markdown = f"# Lakehouses (semantic-link-labs) in workspace '{workspace}'\n\n"
#         markdown += "| ID | Name |\n"
#         markdown += "|-----|------|\n"
#         for lh in lakehouses:
#             markdown += f"| {lh.get('id', 'N/A')} | {lh.get('displayName', 'N/A')} |\n"
#         return markdown
#     except Exception as e:
#         return f"Error listing lakehouses with semantic-link-labs: {str(e)}"


@mcp.tool()
async def create_lakehouse(
    name: str,
    workspace: Optional[str] = None,
    description: Optional[str] = None,
    enable_schemas: bool = True,
    folder_id: Optional[str] = None,
    ctx: Context = None,
) -> str:
    """Create a new lakehouse in a Fabric workspace.

    Args:
        name: Name of the lakehouse
        workspace: Name or ID of the workspace (optional)
        description: Description of the lakehouse (optional)
        enable_schemas: Enable schema support for the lakehouse (default: True)
        folder_id: ID of the folder to create the lakehouse in (optional)
        ctx: Context object containing client information
    Returns:
        A string confirming the lakehouse has been created or an error message.
    """
    try:
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)
        lakehouse_client = LakehouseClient(client=fabric_client)
        ws = workspace or __ctx_cache.get(f"{ctx.client_id}_workspace")
        if not ws:
            return "Workspace not set. Please set a workspace using the 'set_workspace' command."

        result = await lakehouse_client.create_lakehouse(
            name=name, workspace=ws, description=description,
            enable_schemas=enable_schemas, folder_id=folder_id,
        )

        # Format the response to be more user-friendly
        if result and isinstance(result, dict):
            lakehouse_id = result.get('id', 'N/A')
            lakehouse_name = result.get('displayName', name)
            return f"✓ Successfully created lakehouse '{lakehouse_name}' with ID: {lakehouse_id} in workspace '{ws}'"
        elif result:
            return f"Lakehouse creation returned: {result}"
        else:
            return f"⚠ Lakehouse creation returned no response. This may indicate a permissions issue or API failure."

    except Exception as e:
        logger.error(f"Error creating lakehouse: {e}")
        import traceback
        error_details = traceback.format_exc()
        return f"Error creating lakehouse '{name}':\n{str(e)}\n\nDetails:\n{error_details}"


@mcp.tool()
async def update_lakehouse(
    lakehouse: str,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> str:
    """Update a lakehouse (rename or change description).

    Args:
        lakehouse: Name or ID of the lakehouse to update
        display_name: New display name (optional)
        description: New description (optional)
        workspace: Name or ID of the workspace (optional)
        ctx: Context object containing client information
    Returns:
        A string confirming the update or an error message.
    """
    try:
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)
        ws = workspace or __ctx_cache.get(f"{ctx.client_id}_workspace")
        if not ws:
            return "Workspace not set. Please set a workspace using the 'set_workspace' command."

        _, workspace_id = await fabric_client.resolve_workspace_name_and_id(ws)
        _, lakehouse_id = await fabric_client.resolve_item_name_and_id(
            item=lakehouse, type="Lakehouse", workspace=workspace_id
        )

        await fabric_client.update_item(
            workspace_id=workspace_id,
            item_id=str(lakehouse_id),
            item_type="lakehouse",
            display_name=display_name,
            description=description,
        )
        return f"Lakehouse '{lakehouse}' updated successfully."
    except Exception as e:
        logger.error(f"Error updating lakehouse: {e}")
        return f"Error updating lakehouse: {str(e)}"


@mcp.tool()
async def delete_lakehouse(
    lakehouse: str,
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> str:
    """Delete a lakehouse and its SQL endpoint. This is irreversible.

    Args:
        lakehouse: Name or ID of the lakehouse to delete
        workspace: Name or ID of the workspace (optional)
        ctx: Context object containing client information
    Returns:
        A string confirming deletion or an error message.
    """
    try:
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)
        ws = workspace or __ctx_cache.get(f"{ctx.client_id}_workspace")
        if not ws:
            return "Workspace not set. Please set a workspace using the 'set_workspace' command."

        _, workspace_id = await fabric_client.resolve_workspace_name_and_id(ws)
        _, lakehouse_id = await fabric_client.resolve_item_name_and_id(
            item=lakehouse, type="Lakehouse", workspace=workspace_id
        )

        await fabric_client.delete_item(
            workspace_id=workspace_id,
            item_id=str(lakehouse_id),
            item_type="lakehouse",
        )
        return f"Lakehouse '{lakehouse}' deleted successfully."
    except Exception as e:
        logger.error(f"Error deleting lakehouse: {e}")
        return f"Error deleting lakehouse: {str(e)}"


@mcp.tool()
async def lakehouse_table_maintenance(
    table_name: str,
    lakehouse: Optional[str] = None,
    workspace: Optional[str] = None,
    schema_name: Optional[str] = None,
    v_order: bool = True,
    z_order_by: Optional[str] = None,
    vacuum_retention: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Run Fabric-native table maintenance job (optimize + vacuum) on a lakehouse delta table.

    Unlike optimize_delta/vacuum_delta which use notebooks, this uses the native
    Fabric Jobs API for table maintenance. Runs as a background job.

    Args:
        table_name: Name of the delta table to maintain
        lakehouse: Name or ID of the lakehouse (optional, uses active)
        workspace: Name or ID of the workspace (optional, uses active)
        schema_name: Schema name if lakehouse has schemas enabled (optional)
        v_order: Enable V-Order optimization during compaction (default: True)
        z_order_by: Comma-separated column names for Z-Order optimization (optional)
        vacuum_retention: Retention period in "d.hh:mm:ss" format, e.g. "7.00:00:00" for 7 days (optional).
                         If not provided, only optimize runs (no vacuum).
        ctx: Context object containing client information

    Returns:
        Dictionary with job instance ID and status, or an error.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        ws = workspace or __ctx_cache.get(f"{ctx.client_id}_workspace")
        if not ws:
            return {"error": "Workspace not set. Use set_workspace first."}

        lh = lakehouse or __ctx_cache.get(f"{ctx.client_id}_lakehouse")
        if not lh:
            return {"error": "Lakehouse not set. Use set_lakehouse first."}

        _, workspace_id = await fabric_client.resolve_workspace_name_and_id(ws)
        _, lakehouse_id = await fabric_client.resolve_item_name_and_id(
            item=lh, type="Lakehouse", workspace=workspace_id
        )

        execution_data: Dict[str, Any] = {"tableName": table_name}
        if schema_name:
            execution_data["schemaName"] = schema_name

        optimize_settings: Dict[str, Any] = {"vOrder": v_order}
        if z_order_by:
            columns = [c.strip() for c in z_order_by.split(",") if c.strip()]
            optimize_settings["zOrderBy"] = columns
        execution_data["optimizeSettings"] = optimize_settings

        if vacuum_retention:
            execution_data["vacuumSettings"] = {
                "retentionPeriod": vacuum_retention
            }

        payload = {"executionData": execution_data}

        response = await fabric_client._make_request(
            endpoint=(
                f"workspaces/{workspace_id}/lakehouses/{lakehouse_id}"
                f"/jobs/instances?jobType=TableMaintenance"
            ),
            method="post",
            params=payload,
            lro=True,
            lro_poll_interval=5,
            lro_timeout=600,
        )

        if isinstance(response, dict):
            return {
                "success": True,
                "table": table_name,
                "lakehouse_id": str(lakehouse_id),
                "result": response,
            }
        return {"success": True, "table": table_name, "result": response}
    except Exception as e:
        logger.error(f"Error running table maintenance on '{table_name}': {e}")
        return {"error": str(e)}


@mcp.tool()
async def lakehouse_load_table(
    table_name: str,
    relative_path: str,
    path_type: str = "File",
    mode: str = "Overwrite",
    file_format: str = "Csv",
    header: bool = True,
    delimiter: str = ",",
    recursive: bool = False,
    lakehouse: Optional[str] = None,
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Load data from OneLake Files into a lakehouse delta table via the official Fabric API.

    The source file must already exist in the lakehouse's Files section
    (upload via onelake_write or load_data_from_url first).

    Args:
        table_name: Name of the destination delta table (created if not exists)
        relative_path: Path to source file/folder relative to lakehouse root,
                       e.g. "Files/raw/sales.csv" or "Files/raw/parquet_folder"
        path_type: "File" for a single file, "Folder" for a directory of files
        mode: "Overwrite" replaces table, "Append" adds rows
        file_format: "Csv" or "Parquet"
        header: Whether CSV has a header row (ignored for Parquet)
        delimiter: CSV delimiter character (ignored for Parquet)
        recursive: Search subfolders when path_type is "Folder"
        lakehouse: Name or ID of the lakehouse (optional, uses active)
        workspace: Name or ID of the workspace (optional, uses active)
        ctx: Context object containing client information

    Returns:
        Dictionary with operation result or an error.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        ws = workspace or __ctx_cache.get(f"{ctx.client_id}_workspace")
        if not ws:
            return {"error": "Workspace not set. Use set_workspace first."}

        lh = lakehouse or __ctx_cache.get(f"{ctx.client_id}_lakehouse")
        if not lh:
            return {"error": "Lakehouse not set. Use set_lakehouse first."}

        _, workspace_id = await fabric_client.resolve_workspace_name_and_id(ws)
        _, lakehouse_id = await fabric_client.resolve_item_name_and_id(
            item=lh, type="Lakehouse", workspace=workspace_id
        )

        payload: Dict[str, Any] = {
            "relativePath": relative_path,
            "pathType": path_type,
            "mode": mode,
            "recursive": recursive,
        }

        fmt = file_format.strip().lower()
        if fmt == "csv":
            payload["formatOptions"] = {
                "format": "Csv",
                "header": header,
                "delimiter": delimiter,
            }
        elif fmt == "parquet":
            payload["formatOptions"] = {"format": "Parquet"}

        response = await fabric_client._make_request(
            endpoint=(
                f"workspaces/{workspace_id}/lakehouses/{lakehouse_id}"
                f"/tables/{table_name}/load"
            ),
            method="post",
            params=payload,
            lro=True,
            lro_poll_interval=5,
            lro_timeout=600,
        )

        return {
            "success": True,
            "table": table_name,
            "source": relative_path,
            "mode": mode,
            "result": response if isinstance(response, dict) else str(response),
        }
    except Exception as e:
        logger.error(f"Error loading table '{table_name}': {e}")
        return {"error": str(e)}
