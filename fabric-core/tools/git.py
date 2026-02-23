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
async def git_connect(
    git_provider_type: str,
    repository_name: str,
    branch_name: str,
    directory_name: str,
    workspace: Optional[str] = None,
    organization_name: Optional[str] = None,
    project_name: Optional[str] = None,
    owner_name: Optional[str] = None,
    connection_id: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Connect a Fabric workspace to a Git repository.

    Args:
        git_provider_type: "AzureDevOps" or "GitHub"
        repository_name: Name of the Git repository
        branch_name: Branch to connect to
        directory_name: Directory path within the repository
        workspace: Workspace name or ID (optional, uses context if not set)
        organization_name: Azure DevOps organization name (AzureDevOps only)
        project_name: Azure DevOps project name (AzureDevOps only)
        owner_name: GitHub repository owner (GitHub only)
        connection_id: Connection ID for configured credentials (optional)
        ctx: Context object containing client information
    Returns:
        Dict confirming connection or containing error.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        if git_provider_type == "AzureDevOps":
            git_provider_details = {
                "gitProviderType": "AzureDevOps",
                "organizationName": organization_name,
                "projectName": project_name,
                "repositoryName": repository_name,
                "branchName": branch_name,
                "directoryName": directory_name,
            }
        elif git_provider_type == "GitHub":
            git_provider_details = {
                "gitProviderType": "GitHub",
                "ownerName": owner_name,
                "repositoryName": repository_name,
                "branchName": branch_name,
                "directoryName": directory_name,
            }
        else:
            raise ValueError(
                f"Invalid git_provider_type '{git_provider_type}'. Must be 'AzureDevOps' or 'GitHub'."
            )

        payload: Dict[str, Any] = {"gitProviderDetails": git_provider_details}

        if connection_id:
            payload["myGitCredentials"] = {
                "source": "ConfiguredConnection",
                "connectionId": connection_id,
            }

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/git/connect",
            params=payload,
            method="POST",
        )

        return {
            "workspace": ws,
            "gitProviderType": git_provider_type,
            "repositoryName": repository_name,
            "branchName": branch_name,
            "result": response,
        }
    except Exception as exc:
        logger.error("Failed to connect workspace '%s' to Git: %s", workspace, exc)
        return {"error": str(exc)}


@mcp.tool()
async def git_disconnect(
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Disconnect a Fabric workspace from its Git repository.

    Args:
        workspace: Workspace name or ID (optional, uses context if not set)
        ctx: Context object containing client information
    Returns:
        Dict confirming disconnection or containing error.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/git/disconnect",
            params={},
            method="POST",
        )

        return {"workspace": ws, "result": response}
    except Exception as exc:
        logger.error("Failed to disconnect workspace '%s' from Git: %s", workspace, exc)
        return {"error": str(exc)}


@mcp.tool()
async def git_get_connection(
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Get Git connection details for a Fabric workspace.

    Args:
        workspace: Workspace name or ID (optional, uses context if not set)
        ctx: Context object containing client information
    Returns:
        Dict with Git connection details or error.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/git/connection",
        )

        return {"workspace": ws, "connection": response}
    except Exception as exc:
        logger.error("Failed to get Git connection for workspace '%s': %s", workspace, exc)
        return {"error": str(exc)}


@mcp.tool()
async def git_get_status(
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Get Git sync status for a Fabric workspace.

    Returns the workspace head commit, remote commit hash, and pending changes
    including item metadata, workspace changes, remote changes, and conflict types.

    Args:
        workspace: Workspace name or ID (optional, uses context if not set)
        ctx: Context object containing client information
    Returns:
        Dict with workspaceHead, remoteCommitHash, and changes list, or error.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/git/status",
            lro=True,
        )

        return {"workspace": ws, "status": response}
    except Exception as exc:
        logger.error("Failed to get Git status for workspace '%s': %s", workspace, exc)
        return {"error": str(exc)}


@mcp.tool()
async def git_commit_to_git(
    workspace: Optional[str] = None,
    mode: str = "All",
    comment: Optional[str] = None,
    workspace_head: Optional[str] = None,
    items: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Commit workspace changes to the connected Git repository.

    Args:
        workspace: Workspace name or ID (optional, uses context if not set)
        mode: "All" to commit all changes, or "Selective" to commit specific items
        comment: Optional commit message (max 300 characters)
        workspace_head: Full SHA hash of workspace head from git_get_status (recommended)
        items: Comma-separated object IDs to commit (required when mode is "Selective")
        ctx: Context object containing client information
    Returns:
        Dict with commit result or error.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        if mode not in ("All", "Selective"):
            raise ValueError("mode must be 'All' or 'Selective'.")

        if comment and len(comment) > 300:
            raise ValueError("comment must be 300 characters or fewer.")

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        payload: Dict[str, Any] = {"mode": mode}

        if comment:
            payload["comment"] = comment

        if workspace_head:
            payload["workspaceHead"] = workspace_head

        if mode == "Selective" and items:
            object_ids = [oid.strip() for oid in items.split(",") if oid.strip()]
            payload["items"] = [{"objectId": oid} for oid in object_ids]

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/git/commitToGit",
            params=payload,
            method="POST",
            lro=True,
            lro_poll_interval=5,
            lro_timeout=600,
        )

        return {"workspace": ws, "mode": mode, "result": response}
    except Exception as exc:
        logger.error("Failed to commit to Git for workspace '%s': %s", workspace, exc)
        return {"error": str(exc)}


@mcp.tool()
async def git_update_from_git(
    remote_commit_hash: str,
    workspace: Optional[str] = None,
    workspace_head: Optional[str] = None,
    conflict_resolution_policy: Optional[str] = None,
    allow_override_items: bool = True,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Pull changes from the Git repository into the Fabric workspace.

    Args:
        remote_commit_hash: The remote commit hash to update from (from git_get_status)
        workspace: Workspace name or ID (optional, uses context if not set)
        workspace_head: Full SHA hash of current workspace head (optional, for conflict detection)
        conflict_resolution_policy: "PreferRemote" or "PreferWorkspace" (optional)
        allow_override_items: Whether to allow overriding workspace items (default True)
        ctx: Context object containing client information
    Returns:
        Dict with update result or error.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        if conflict_resolution_policy and conflict_resolution_policy not in (
            "PreferRemote",
            "PreferWorkspace",
        ):
            raise ValueError(
                "conflict_resolution_policy must be 'PreferRemote' or 'PreferWorkspace'."
            )

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        payload: Dict[str, Any] = {"remoteCommitHash": remote_commit_hash}

        if workspace_head:
            payload["workspaceHead"] = workspace_head

        if conflict_resolution_policy:
            payload["conflictResolution"] = {
                "conflictResolutionPolicy": conflict_resolution_policy,
            }

        payload["options"] = {"allowOverrideItems": allow_override_items}

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/git/updateFromGit",
            params=payload,
            method="POST",
            lro=True,
            lro_poll_interval=5,
            lro_timeout=600,
        )

        return {"workspace": ws, "remoteCommitHash": remote_commit_hash, "result": response}
    except Exception as exc:
        logger.error("Failed to update workspace '%s' from Git: %s", workspace, exc)
        return {"error": str(exc)}


@mcp.tool()
async def git_initialize_connection(
    workspace: Optional[str] = None,
    initialization_strategy: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Initialize the Git connection for a workspace after connecting.

    This must be called after git_connect to sync the initial state between
    the workspace and the repository.

    Args:
        workspace: Workspace name or ID (optional, uses context if not set)
        initialization_strategy: "PreferWorkspace" or "PreferRemote" (optional)
        ctx: Context object containing client information
    Returns:
        Dict with initialization result or error.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        if initialization_strategy and initialization_strategy not in (
            "PreferWorkspace",
            "PreferRemote",
        ):
            raise ValueError(
                "initialization_strategy must be 'PreferWorkspace' or 'PreferRemote'."
            )

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        payload: Dict[str, Any] = {}
        if initialization_strategy:
            payload["initializationStrategy"] = initialization_strategy

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/git/initializeConnection",
            params=payload,
            method="POST",
            lro=True,
        )

        return {"workspace": ws, "initializationStrategy": initialization_strategy, "result": response}
    except Exception as exc:
        logger.error(
            "Failed to initialize Git connection for workspace '%s': %s", workspace, exc
        )
        return {"error": str(exc)}


@mcp.tool()
async def git_get_my_credentials(
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Get the current user's Git credentials configuration for a workspace.

    Args:
        workspace: Workspace name or ID (optional, uses context if not set)
        ctx: Context object containing client information
    Returns:
        Dict with credentials details or error.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/git/myGitCredentials",
        )

        return {"workspace": ws, "credentials": response}
    except Exception as exc:
        logger.error(
            "Failed to get Git credentials for workspace '%s': %s", workspace, exc
        )
        return {"error": str(exc)}


@mcp.tool()
async def git_update_my_credentials(
    source: str,
    workspace: Optional[str] = None,
    connection_id: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Update the current user's Git credentials for a workspace.

    Args:
        source: Credential source - "Automatic", "ConfiguredConnection", or "None"
        workspace: Workspace name or ID (optional, uses context if not set)
        connection_id: Connection ID (required when source is "ConfiguredConnection")
        ctx: Context object containing client information
    Returns:
        Dict with update result or error.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        valid_sources = ("Automatic", "ConfiguredConnection", "None")
        if source not in valid_sources:
            raise ValueError(
                f"source must be one of: {', '.join(valid_sources)}."
            )

        if source == "ConfiguredConnection" and not connection_id:
            raise ValueError(
                "connection_id is required when source is 'ConfiguredConnection'."
            )

        ws = _resolve_workspace(ctx, workspace)
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential=credential)

        _, ws_id = await fabric_client.resolve_workspace_name_and_id(ws)

        payload: Dict[str, Any] = {"source": source}

        if source == "ConfiguredConnection":
            payload["connectionId"] = connection_id

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{ws_id}/git/myGitCredentials",
            params=payload,
            method="PATCH",
        )

        return {"workspace": ws, "source": source, "result": response}
    except Exception as exc:
        logger.error(
            "Failed to update Git credentials for workspace '%s': %s", workspace, exc
        )
        return {"error": str(exc)}
