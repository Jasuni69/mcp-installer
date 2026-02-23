import base64
from typing import Any, Dict, Optional

from mcp.server.fastmcp import Context

from helpers.clients import FabricApiClient, OneLakeClient, TableClient
from helpers.logging_config import get_logger
from helpers.utils.authentication import get_azure_credentials
from helpers.utils.context import mcp, __ctx_cache


logger = get_logger(__name__)


async def _resolve_lakehouse_context(
    ctx: Context,
    workspace: Optional[str],
    lakehouse: str,
):
    if ctx is None:
        raise ValueError("Context is required for OneLake operations.")

    ws = workspace or __ctx_cache.get(f"{ctx.client_id}_workspace")
    if not ws:
        raise ValueError(
            "Workspace not set. Provide a workspace value or call set_workspace first."
        )

    credential = get_azure_credentials(ctx.client_id, __ctx_cache)
    fabric_client = FabricApiClient(credential=credential)

    workspace_name, workspace_id = await fabric_client.resolve_workspace_name_and_id(ws)
    _, lakehouse_id = await fabric_client.resolve_item_name_and_id(
        item=lakehouse,
        type="Lakehouse",
        workspace=workspace_id,
    )

    logger.debug(
        "Resolved workspace '%s' (%s) and lakehouse '%s' (%s)",
        workspace_name,
        workspace_id,
        lakehouse,
        lakehouse_id,
    )

    return credential, workspace_id, lakehouse_id


@mcp.tool()
async def onelake_ls(
    lakehouse: str,
    path: Optional[str] = None,
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """List files and folders within a OneLake lakehouse path."""

    try:
        credential, workspace_id, lakehouse_id = await _resolve_lakehouse_context(
            ctx, workspace, lakehouse
        )

        # "Tables" root is a virtual mount in OneLake - list via Fabric API instead
        if path and path.strip("/").lower() == "tables":
            fabric_client = FabricApiClient(credential=credential)
            table_client = TableClient(fabric_client)
            tables = await table_client.list_tables(workspace_id, lakehouse_id, "lakehouse")
            entries = []
            if isinstance(tables, list):
                for t in tables:
                    entries.append({
                        "name": f"Tables/{t.get('name')}",
                        "is_directory": True,
                        "size": None,
                        "last_modified": None,
                        "format": t.get("format"),
                    })
            return {
                "workspaceId": workspace_id,
                "lakehouseId": lakehouse_id,
                "path": "Tables",
                "entries": entries,
            }

        client = OneLakeClient(credential)
        entries = await client.list_directory(workspace_id, lakehouse_id, path)
        return {
            "workspaceId": workspace_id,
            "lakehouseId": lakehouse_id,
            "path": path or "Files",
            "entries": entries,
        }
    except Exception as exc:
        logger.error("OneLake list failed: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def onelake_read(
    lakehouse: str,
    path: str,
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Read file contents from OneLake."""

    try:
        credential, workspace_id, lakehouse_id = await _resolve_lakehouse_context(
            ctx, workspace, lakehouse
        )
        client = OneLakeClient(credential)
        return await client.read_file(workspace_id, lakehouse_id, path)
    except Exception as exc:
        logger.error("OneLake read failed: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def onelake_write(
    lakehouse: str,
    path: str,
    content: str,
    workspace: Optional[str] = None,
    overwrite: bool = True,
    encoding: str = "utf-8",
    is_base64: bool = False,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Write text or base64 content to OneLake."""

    try:
        credential, workspace_id, lakehouse_id = await _resolve_lakehouse_context(
            ctx, workspace, lakehouse
        )

        if is_base64:
            data = base64.b64decode(content)
        else:
            data = content.encode(encoding)

        client = OneLakeClient(credential)
        result = await client.write_file(
            workspace_id, lakehouse_id, path, data, overwrite=overwrite
        )
        result["encoding"] = "base64" if is_base64 else encoding
        return result
    except Exception as exc:
        logger.error("OneLake write failed: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def onelake_rm(
    lakehouse: str,
    path: str,
    workspace: Optional[str] = None,
    recursive: bool = False,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Delete a file or directory from OneLake."""

    try:
        credential, workspace_id, lakehouse_id = await _resolve_lakehouse_context(
            ctx, workspace, lakehouse
        )
        client = OneLakeClient(credential)
        return await client.delete_path(
            workspace_id, lakehouse_id, path, recursive=recursive
        )
    except Exception as exc:
        logger.error("OneLake delete failed: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def onelake_create_shortcut(
    lakehouse: str,
    shortcut_name: str,
    shortcut_path: str,
    target_workspace: str,
    target_lakehouse: str,
    target_path: str,
    workspace: Optional[str] = None,
    conflict_policy: str = "CreateOrOverwrite",
    ctx: Context = None,
) -> Dict[str, Any]:
    """
    Create a OneLake shortcut from one lakehouse to another.

    This allows you to reference data from a target lakehouse without duplicating it.
    Perfect for medallion architectures where Dev/Test/Prod read from a central Bronze layer.

    Args:
        lakehouse: Source lakehouse name or ID (where the shortcut will appear)
        shortcut_name: Name for the shortcut
        shortcut_path: Path in source where shortcut appears (e.g., "Tables", "Files/exports")
        target_workspace: Target workspace name or ID (containing the data)
        target_lakehouse: Target lakehouse name or ID (containing the data)
        target_path: Path in target to link to (e.g., "Tables/customers_raw", "Files/bronze")
        workspace: Source workspace name or ID (optional, uses context if not provided)
        conflict_policy: Action when shortcut exists (Abort, GenerateUniqueName, CreateOrOverwrite, OverwriteOnly)
        ctx: Context object

    Returns:
        Dictionary with shortcut details including name, path, and target

    Example:
        # Create shortcut from DEV silver lakehouse to central Bronze
        onelake_create_shortcut(
            workspace="DEV-Analytics",
            lakehouse="silver_dev",
            shortcut_name="bronze_customers",
            shortcut_path="Tables",
            target_workspace="RAW-Bronze-Central",
            target_lakehouse="bronze_central",
            target_path="Tables/customers_raw"
        )
    """
    try:
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        # Resolve source workspace and lakehouse
        source_ws = workspace or __ctx_cache.get(f"{ctx.client_id}_workspace")
        if not source_ws:
            raise ValueError(
                "Workspace not set. Provide a workspace value or call set_workspace first."
            )

        source_workspace_name, source_workspace_id = await fabric_client.resolve_workspace_name_and_id(source_ws)
        _, source_lakehouse_id = await fabric_client.resolve_item_name_and_id(
            item=lakehouse,
            type="Lakehouse",
            workspace=source_workspace_id,
        )

        # Resolve target workspace and lakehouse
        target_workspace_name, target_workspace_id = await fabric_client.resolve_workspace_name_and_id(target_workspace)
        _, target_lakehouse_id = await fabric_client.resolve_item_name_and_id(
            item=target_lakehouse,
            type="Lakehouse",
            workspace=target_workspace_id,
        )

        logger.info(
            f"Creating shortcut '{shortcut_name}' in {source_workspace_name}/{lakehouse}/{shortcut_path} "
            f"→ {target_workspace_name}/{target_lakehouse}/{target_path}"
        )

        # Create the shortcut
        result = await fabric_client.create_shortcut(
            workspace_id=source_workspace_id,
            item_id=source_lakehouse_id,
            shortcut_name=shortcut_name,
            shortcut_path=shortcut_path,
            target_workspace_id=target_workspace_id,
            target_item_id=target_lakehouse_id,
            target_path=target_path,
            conflict_policy=conflict_policy,
        )

        return {
            "success": True,
            "shortcut": result,
            "source": f"{source_workspace_name}/{lakehouse}/{shortcut_path}/{shortcut_name}",
            "target": f"{target_workspace_name}/{target_lakehouse}/{target_path}",
        }

    except Exception as exc:
        logger.error("Failed to create OneLake shortcut: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def onelake_list_shortcuts(
    lakehouse: str,
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """
    List all OneLake shortcuts in a lakehouse.

    Args:
        lakehouse: Lakehouse name or ID
        workspace: Workspace name or ID (optional, uses context if not provided)
        ctx: Context object

    Returns:
        Dictionary with list of shortcuts

    Example:
        onelake_list_shortcuts(
            workspace="DEV-Analytics",
            lakehouse="silver_dev"
        )
    """
    try:
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        # Resolve workspace and lakehouse
        ws = workspace or __ctx_cache.get(f"{ctx.client_id}_workspace")
        if not ws:
            raise ValueError(
                "Workspace not set. Provide a workspace value or call set_workspace first."
            )

        workspace_name, workspace_id = await fabric_client.resolve_workspace_name_and_id(ws)
        _, lakehouse_id = await fabric_client.resolve_item_name_and_id(
            item=lakehouse,
            type="Lakehouse",
            workspace=workspace_id,
        )

        logger.info(f"Listing shortcuts in {workspace_name}/{lakehouse}")

        # List shortcuts
        shortcuts = await fabric_client.list_shortcuts(
            workspace_id=workspace_id,
            item_id=lakehouse_id,
        )

        return {
            "workspace": workspace_name,
            "lakehouse": lakehouse,
            "shortcut_count": len(shortcuts) if shortcuts else 0,
            "shortcuts": shortcuts if shortcuts else [],
        }

    except Exception as exc:
        logger.error("Failed to list OneLake shortcuts: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def onelake_delete_shortcut(
    lakehouse: str,
    shortcut_path: str,
    shortcut_name: str,
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """
    Delete a OneLake shortcut from a lakehouse.

    Args:
        lakehouse: Lakehouse name or ID containing the shortcut
        shortcut_path: Path where shortcut exists (e.g., "Tables", "Files/exports")
        shortcut_name: Name of the shortcut to delete
        workspace: Workspace name or ID (optional, uses context if not provided)
        ctx: Context object

    Returns:
        Dictionary with success status

    Example:
        onelake_delete_shortcut(
            workspace="DEV-Analytics",
            lakehouse="silver_dev",
            shortcut_path="Tables",
            shortcut_name="bronze_customers"
        )
    """
    try:
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        # Resolve workspace and lakehouse
        ws = workspace or __ctx_cache.get(f"{ctx.client_id}_workspace")
        if not ws:
            raise ValueError(
                "Workspace not set. Provide a workspace value or call set_workspace first."
            )

        workspace_name, workspace_id = await fabric_client.resolve_workspace_name_and_id(ws)
        _, lakehouse_id = await fabric_client.resolve_item_name_and_id(
            item=lakehouse,
            type="Lakehouse",
            workspace=workspace_id,
        )

        logger.info(f"Deleting shortcut '{shortcut_name}' from {workspace_name}/{lakehouse}/{shortcut_path}")

        # Delete the shortcut
        result = await fabric_client.delete_shortcut(
            workspace_id=workspace_id,
            item_id=lakehouse_id,
            shortcut_path=shortcut_path,
            shortcut_name=shortcut_name,
        )

        return {
            "success": True,
            "message": f"Shortcut '{shortcut_name}' deleted from {workspace_name}/{lakehouse}/{shortcut_path}",
            "details": result,
        }

    except Exception as exc:
        logger.error("Failed to delete OneLake shortcut: %s", exc)
        return {"error": str(exc)}


