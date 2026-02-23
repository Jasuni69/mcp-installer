from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context

from helpers.clients import FabricApiClient
from helpers.logging_config import get_logger
from helpers.utils.authentication import get_azure_credentials
from helpers.utils.context import mcp, __ctx_cache


logger = get_logger(__name__)


@mcp.tool()
async def list_deployment_pipelines(
    ctx: Context = None,
) -> Dict[str, Any]:
    """List all deployment pipelines accessible to the current user.

    Args:
        ctx: Context object containing client information

    Returns:
        Dictionary with list of deployment pipelines (id, displayName, description).
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        response = await fabric_client._make_request(
            endpoint="deploymentPipelines"
        )

        pipelines: List[Dict[str, Any]]
        if isinstance(response, dict):
            pipelines = response.get("value", [])
        elif isinstance(response, list):
            pipelines = response
        else:
            pipelines = []

        return {"pipelines": pipelines, "count": len(pipelines)}
    except Exception as exc:
        logger.error("Failed to list deployment pipelines: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def create_deployment_pipeline(
    display_name: str,
    description: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Create a new deployment pipeline.

    Args:
        display_name: Display name for the new pipeline
        description: Optional description
        ctx: Context object containing client information

    Returns:
        Dictionary with the created pipeline details.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        payload: Dict[str, Any] = {"displayName": display_name}
        if description is not None:
            payload["description"] = description

        response = await fabric_client._make_request(
            endpoint="deploymentPipelines",
            method="post",
            params=payload,
        )

        return response if isinstance(response, dict) else {"result": response}
    except Exception as exc:
        logger.error("Failed to create deployment pipeline '%s': %s", display_name, exc)
        return {"error": str(exc)}


@mcp.tool()
async def get_deployment_pipeline(
    pipeline_id: str,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Get details for a specific deployment pipeline.

    Args:
        pipeline_id: ID of the deployment pipeline
        ctx: Context object containing client information

    Returns:
        Dictionary with pipeline metadata.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        response = await fabric_client._make_request(
            endpoint=f"deploymentPipelines/{pipeline_id}"
        )

        return response if isinstance(response, dict) else {"result": response}
    except Exception as exc:
        logger.error("Failed to get deployment pipeline '%s': %s", pipeline_id, exc)
        return {"error": str(exc)}


@mcp.tool()
async def update_deployment_pipeline(
    pipeline_id: str,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Update properties of an existing deployment pipeline.

    Args:
        pipeline_id: ID of the deployment pipeline to update
        display_name: New display name (optional)
        description: New description (optional)
        ctx: Context object containing client information

    Returns:
        Dictionary with the updated pipeline details or a confirmation.
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

        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        response = await fabric_client._make_request(
            endpoint=f"deploymentPipelines/{pipeline_id}",
            method="patch",
            params=payload,
        )

        return response if isinstance(response, dict) else {"result": response}
    except Exception as exc:
        logger.error("Failed to update deployment pipeline '%s': %s", pipeline_id, exc)
        return {"error": str(exc)}


@mcp.tool()
async def delete_deployment_pipeline(
    pipeline_id: str,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Delete a deployment pipeline.

    Args:
        pipeline_id: ID of the deployment pipeline to delete
        ctx: Context object containing client information

    Returns:
        Dictionary confirming deletion or an error.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        await fabric_client._make_request(
            endpoint=f"deploymentPipelines/{pipeline_id}",
            method="delete",
        )

        return {"success": True, "pipeline_id": pipeline_id}
    except Exception as exc:
        logger.error("Failed to delete deployment pipeline '%s': %s", pipeline_id, exc)
        return {"error": str(exc)}


@mcp.tool()
async def list_deployment_pipeline_stages(
    pipeline_id: str,
    ctx: Context = None,
) -> Dict[str, Any]:
    """List all stages in a deployment pipeline (typically Dev, Test, Production).

    Args:
        pipeline_id: ID of the deployment pipeline
        ctx: Context object containing client information

    Returns:
        Dictionary with list of stages for the pipeline.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        response = await fabric_client._make_request(
            endpoint=f"deploymentPipelines/{pipeline_id}/stages"
        )

        stages: List[Dict[str, Any]]
        if isinstance(response, dict):
            stages = response.get("value", [])
        elif isinstance(response, list):
            stages = response
        else:
            stages = []

        return {"pipeline_id": pipeline_id, "stages": stages, "count": len(stages)}
    except Exception as exc:
        logger.error(
            "Failed to list stages for deployment pipeline '%s': %s", pipeline_id, exc
        )
        return {"error": str(exc)}


@mcp.tool()
async def list_deployment_pipeline_stage_items(
    pipeline_id: str,
    stage_id: str,
    ctx: Context = None,
) -> Dict[str, Any]:
    """List all items in a specific stage of a deployment pipeline.

    Args:
        pipeline_id: ID of the deployment pipeline
        stage_id: ID of the stage to list items for
        ctx: Context object containing client information

    Returns:
        Dictionary with list of items in the stage.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        response = await fabric_client._make_request(
            endpoint=f"deploymentPipelines/{pipeline_id}/stages/{stage_id}/items"
        )

        items: List[Dict[str, Any]]
        if isinstance(response, dict):
            items = response.get("value", [])
        elif isinstance(response, list):
            items = response
        else:
            items = []

        return {
            "pipeline_id": pipeline_id,
            "stage_id": stage_id,
            "items": items,
            "count": len(items),
        }
    except Exception as exc:
        logger.error(
            "Failed to list items for stage '%s' in pipeline '%s': %s",
            stage_id,
            pipeline_id,
            exc,
        )
        return {"error": str(exc)}


@mcp.tool()
async def deploy_stage_content(
    pipeline_id: str,
    source_stage_id: str,
    target_stage_id: str,
    items: Optional[str] = None,
    note: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Deploy content from one pipeline stage to another.

    This is a long-running operation (LRO). The tool waits for completion
    before returning. Deployment can take several minutes for large workspaces.

    Args:
        pipeline_id: ID of the deployment pipeline
        source_stage_id: ID of the source stage to deploy from
        target_stage_id: ID of the target stage to deploy to
        items: Optional comma-separated list of item objectIds to deploy selectively.
               If not provided, all items in the source stage are deployed.
        note: Optional deployment note / comment
        ctx: Context object containing client information

    Returns:
        Dictionary with the deployment result or an error.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        payload: Dict[str, Any] = {
            "sourceStageId": source_stage_id,
            "targetStageId": target_stage_id,
        }

        if items:
            object_ids = [oid.strip() for oid in items.split(",") if oid.strip()]
            payload["items"] = [{"objectId": oid} for oid in object_ids]

        if note:
            payload["note"] = note

        response = await fabric_client._make_request(
            endpoint=f"deploymentPipelines/{pipeline_id}/deploy",
            method="post",
            params=payload,
            lro=True,
            lro_poll_interval=5,
            lro_timeout=600,
        )

        return response if isinstance(response, dict) else {"result": response}
    except Exception as exc:
        logger.error(
            "Failed to deploy from stage '%s' to '%s' in pipeline '%s': %s",
            source_stage_id,
            target_stage_id,
            pipeline_id,
            exc,
        )
        return {"error": str(exc)}


@mcp.tool()
async def assign_workspace_to_stage(
    pipeline_id: str,
    stage_id: str,
    workspace: str,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Assign a workspace to a specific stage in a deployment pipeline.

    Args:
        pipeline_id: ID of the deployment pipeline
        stage_id: ID of the stage to assign the workspace to
        workspace: Name or ID of the workspace to assign
        ctx: Context object containing client information

    Returns:
        Dictionary confirming the assignment or an error.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        _, workspace_id = await fabric_client.resolve_workspace_name_and_id(workspace)

        payload: Dict[str, Any] = {"workspaceId": str(workspace_id)}

        response = await fabric_client._make_request(
            endpoint=f"deploymentPipelines/{pipeline_id}/stages/{stage_id}/assignWorkspace",
            method="post",
            params=payload,
        )

        return {
            "success": True,
            "pipeline_id": pipeline_id,
            "stage_id": stage_id,
            "workspace_id": str(workspace_id),
            "result": response,
        }
    except Exception as exc:
        logger.error(
            "Failed to assign workspace '%s' to stage '%s' in pipeline '%s': %s",
            workspace,
            stage_id,
            pipeline_id,
            exc,
        )
        return {"error": str(exc)}


@mcp.tool()
async def unassign_workspace_from_stage(
    pipeline_id: str,
    stage_id: str,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Unassign the workspace from a specific stage in a deployment pipeline.

    Args:
        pipeline_id: ID of the deployment pipeline
        stage_id: ID of the stage to unassign the workspace from
        ctx: Context object containing client information

    Returns:
        Dictionary confirming the unassignment or an error.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        response = await fabric_client._make_request(
            endpoint=f"deploymentPipelines/{pipeline_id}/stages/{stage_id}/unassignWorkspace",
            method="post",
            params={},
        )

        return {
            "success": True,
            "pipeline_id": pipeline_id,
            "stage_id": stage_id,
            "result": response,
        }
    except Exception as exc:
        logger.error(
            "Failed to unassign workspace from stage '%s' in pipeline '%s': %s",
            stage_id,
            pipeline_id,
            exc,
        )
        return {"error": str(exc)}
