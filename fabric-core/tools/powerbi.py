from typing import Any, Dict, Optional

from helpers.clients import FabricApiClient
from helpers.logging_config import get_logger
from helpers.utils import _is_valid_uuid
from helpers.utils.authentication import get_azure_credentials
from helpers.utils.context import mcp, __ctx_cache
from mcp.server.fastmcp import Context


logger = get_logger(__name__)


async def _resolve_workspace(
    ctx: Context,
    workspace: Optional[str],
) -> Dict[str, Any]:
    if ctx is None:
        raise ValueError("Context (ctx) must be provided.")

    credential = get_azure_credentials(ctx.client_id, __ctx_cache)
    fabric_client = FabricApiClient(credential)

    workspace_ref = workspace or __ctx_cache.get(f"{ctx.client_id}_workspace")
    if not workspace_ref:
        raise ValueError("Workspace must be specified or set via set_workspace.")

    workspace_name, workspace_id = await fabric_client.resolve_workspace_name_and_id(
        workspace_ref
    )

    return {
        "credential": credential,
        "fabric_client": fabric_client,
        "workspace_id": workspace_id,
        "workspace_name": workspace_name,
        "workspace_ref": workspace_ref,
    }


async def _resolve_item(
    ctx: Context,
    workspace: Optional[str],
    item: Optional[str],
    item_type: str,
) -> Dict[str, Any]:
    context = await _resolve_workspace(ctx, workspace)

    item_ref = item
    if not item_ref:
        context_key = f"{ctx.client_id}_{item_type.lower()}"
        item_ref = __ctx_cache.get(context_key)

    if not item_ref:
        raise ValueError(f"{item_type} must be specified or stored in context.")

    if _is_valid_uuid(item_ref):
        item_name = item_ref
        item_id = item_ref
    else:
        item_name, item_id = await context["fabric_client"].resolve_item_name_and_id(
            item=item_ref,
            type=item_type,
            workspace=context["workspace_id"],
        )

    context.update({
        "item_id": str(item_id),
        "item_name": item_name,
        "item_type": item_type,
    })
    return context


@mcp.tool()
async def semantic_model_refresh(
    workspace: Optional[str] = None,
    model: Optional[str] = None,
    refresh_type: str = "Full",
    objects: Optional[str] = None,
    commit_mode: Optional[str] = None,
    max_parallelism: Optional[int] = None,
    retry_count: Optional[int] = None,
    apply_refresh_policy: Optional[bool] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Trigger a refresh of a semantic model via Enhanced Refresh API.

    Args:
        workspace: Workspace name or ID
        model: Semantic model name or ID
        refresh_type: Full, Automatic, DataOnly, Calculate, ClearValues
        objects: Selective refresh — comma-separated table names (e.g. "Sales,Products")
        commit_mode: transactionalBatch (all-or-nothing) or partialBatch (commit what succeeds)
        max_parallelism: Max parallel refresh operations (2-20)
        retry_count: Number of retries on transient failures
        apply_refresh_policy: Apply incremental refresh policy (True/False)
        ctx: FastMCP context
    """
    try:
        context = await _resolve_item(ctx, workspace, model, "SemanticModel")
        payload: Dict[str, Any] = {"type": refresh_type}

        if objects:
            payload["objects"] = [
                {"table": t.strip()} for t in objects.split(",") if t.strip()
            ]
        if commit_mode:
            payload["commitMode"] = commit_mode
        if max_parallelism is not None:
            payload["maxParallelism"] = max_parallelism
        if retry_count is not None:
            payload["retryCount"] = retry_count
        if apply_refresh_policy is not None:
            payload["applyRefreshPolicy"] = apply_refresh_policy

        response = await context["fabric_client"]._make_request(
            endpoint=f"https://api.powerbi.com/v1.0/myorg/groups/{context['workspace_id']}/datasets/{context['item_id']}/refreshes",
            params=payload,
            method="post",
            token_scope="https://analysis.windows.net/powerbi/api/.default",
        )
        return response
    except Exception as exc:
        logger.error("Error triggering semantic model refresh: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def dax_query(
    dataset: str,
    query: str,
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    try:
        context = await _resolve_item(ctx, workspace, dataset, "SemanticModel")
        payload = {
            "queries": [{"query": query}],
            "serializerSettings": {"includeNulls": True},
        }
        response = await context["fabric_client"]._make_request(
            endpoint=f"https://api.powerbi.com/v1.0/myorg/groups/{context['workspace_id']}/datasets/{context['item_id']}/executeQueries",
            params=payload,
            method="post",
            token_scope="https://analysis.windows.net/powerbi/api/.default",
        )
        return response
    except Exception as exc:
        logger.error("Error executing DAX query: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def report_export(
    workspace: Optional[str] = None,
    report: Optional[str] = None,
    format: str = "pdf",
    ctx: Context = None,
) -> Dict[str, Any]:
    try:
        context = await _resolve_item(ctx, workspace, report, "Report")
        payload = {"format": format}
        response = await context["fabric_client"]._make_request(
            endpoint=f"workspaces/{context['workspace_id']}/reports/{context['item_id']}/exports",
            params=payload,
            method="post",
        )
        return response
    except Exception as exc:
        logger.error("Error exporting report: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def report_params_list(
    workspace: Optional[str] = None,
    report: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    try:
        context = await _resolve_item(ctx, workspace, report, "Report")
        response = await context["fabric_client"]._make_request(
            endpoint=f"workspaces/{context['workspace_id']}/reports/{context['item_id']}/parameters"
        )
        return response
    except Exception as exc:
        logger.error("Error listing report parameters: %s", exc)
        return {"error": str(exc)}



