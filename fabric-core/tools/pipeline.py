from typing import Any, Dict, Optional

from helpers.clients import FabricApiClient
from helpers.logging_config import get_logger
from helpers.utils.authentication import get_azure_credentials
from helpers.utils.context import mcp, __ctx_cache
from mcp.server.fastmcp import Context
from helpers.utils import _is_valid_uuid


logger = get_logger(__name__)

# Fabric Job Scheduler uses item-specific job type names
_ITEM_JOB_TYPES = {
    "Notebook": "RunNotebook",
    "SparkJobDefinition": "SparkJobDefinitionV1",
    "Pipeline": "Pipeline",
    "DataPipeline": "Pipeline",
    "Lakehouse": "TableMaintenance",
}


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


async def _resolve_workspace_item(
    ctx: Context,
    workspace: Optional[str],
    item: Optional[str],
    item_type: str,
) -> Dict[str, Any]:
    context = await _resolve_workspace(ctx, workspace)

    item_ref = item or __ctx_cache.get(f"{ctx.client_id}_{item_type.lower()}")
    if not item_ref:
        raise ValueError(f"{item_type} must be specified or stored in context.")

    item_name, item_id = await context["fabric_client"].resolve_item_name_and_id(
        item=item_ref,
        type=item_type,
        workspace=context["workspace_id"],
    )

    context.update({
        "item_id": str(item_id),
        "item_name": item_name,
        "item_ref": item_ref,
        "item_type": item_type,
    })
    return context


@mcp.tool()
async def pipeline_run(
    workspace: Optional[str] = None,
    pipeline: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    try:
        context = await _resolve_workspace_item(ctx, workspace, pipeline, "DataPipeline")
        payload = {}
        if parameters:
            payload["executionData"] = {"parameters": parameters}
        response = await context["fabric_client"]._make_request(
            endpoint=f"workspaces/{context['workspace_id']}/items/{context['item_id']}/jobs/instances?jobType=Pipeline",
            params=payload,
            method="post",
        )
        return response
    except Exception as exc:
        logger.error("Error triggering pipeline run: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def pipeline_status(
    workspace: Optional[str] = None,
    pipeline: Optional[str] = None,
    run_id: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    try:
        context = await _resolve_workspace_item(ctx, workspace, pipeline, "DataPipeline")
        if not run_id:
            raise ValueError("run_id must be provided.")

        response = await context["fabric_client"]._make_request(
            endpoint=f"workspaces/{context['workspace_id']}/items/{context['item_id']}/jobs/instances/{run_id}"
        )
        return response
    except Exception as exc:
        logger.error("Error retrieving pipeline status: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def pipeline_logs(
    workspace: Optional[str] = None,
    pipeline: Optional[str] = None,
    run_id: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    try:
        context = await _resolve_workspace_item(ctx, workspace, pipeline, "DataPipeline")
        if run_id:
            # Get specific job instance details (includes failure reason, timing, etc.)
            response = await context["fabric_client"]._make_request(
                endpoint=f"workspaces/{context['workspace_id']}/items/{context['item_id']}/jobs/instances/{run_id}"
            )
        else:
            # List recent job instances for the pipeline
            response = await context["fabric_client"]._make_request(
                endpoint=f"workspaces/{context['workspace_id']}/items/{context['item_id']}/jobs/instances"
            )
        return response
    except Exception as exc:
        logger.error("Error retrieving pipeline logs: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def dataflow_refresh(
    workspace: Optional[str] = None,
    dataflow: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    try:
        context = await _resolve_workspace_item(ctx, workspace, dataflow, "Dataflow")
        response = await context["fabric_client"]._make_request(
            endpoint=f"workspaces/{context['workspace_id']}/dataflows/{context['item_id']}/refreshes",
            params={},
            method="post",
        )
        return response
    except Exception as exc:
        logger.error("Error triggering dataflow refresh: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def schedule_list(
    workspace: Optional[str] = None,
    item: Optional[str] = None,
    job_type: str = "DefaultJob",
    ctx: Context = None,
) -> Dict[str, Any]:
    try:
        if not item:
            raise ValueError("Item must be specified to list schedules.")

        context = await _resolve_workspace(ctx, workspace)
        fabric_client = context["fabric_client"]

        resolved_item_type = None
        if _is_valid_uuid(item):
            item_name = item
            item_id = item
        else:
            item_name = None
            item_id = None
            for try_type in [
                "SemanticModel",
                "DataPipeline",
                "Dataflow",
                "Lakehouse",
                "Warehouse",
                "Notebook",
                "Report",
            ]:
                try:
                    resolved_name, resolved_id = await fabric_client.resolve_item_name_and_id(
                        item=item,
                        type=try_type,
                        workspace=context["workspace_id"],
                    )
                    item_name, item_id = resolved_name, resolved_id
                    resolved_item_type = try_type
                    break
                except Exception:
                    continue

            if not item_id:
                raise ValueError(
                    f"Unable to resolve item '{item}' in workspace."
                )

        # Auto-detect job type when using default
        effective_job_type = job_type
        if job_type == "DefaultJob" and resolved_item_type in _ITEM_JOB_TYPES:
            effective_job_type = _ITEM_JOB_TYPES[resolved_item_type]

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{context['workspace_id']}/items/{item_id}/jobs/{effective_job_type}/schedules"
        )
        return {"item": item_name, "job_type": effective_job_type, "schedules": response}
    except Exception as exc:
        logger.error("Error listing schedules: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def schedule_set(
    workspace: Optional[str] = None,
    item: Optional[str] = None,
    job_type: str = "DefaultJob",
    schedule: Optional[Dict[str, Any]] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    try:
        if not item:
            raise ValueError("Item must be specified when setting a schedule.")
        if not schedule:
            raise ValueError("Schedule configuration must be provided.")

        context = await _resolve_workspace(ctx, workspace)
        fabric_client = context["fabric_client"]

        resolved_item_type = None
        if _is_valid_uuid(item):
            item_id = item
        else:
            item_id = None
            for try_type in [
                "SemanticModel",
                "DataPipeline",
                "Dataflow",
                "Lakehouse",
                "Warehouse",
                "Notebook",
                "Report",
            ]:
                try:
                    _, resolved_id = await fabric_client.resolve_item_name_and_id(
                        item=item,
                        type=try_type,
                        workspace=context["workspace_id"],
                    )
                    item_id = resolved_id
                    resolved_item_type = try_type
                    break
                except Exception:
                    continue

            if not item_id:
                raise ValueError(
                    f"Unable to resolve item '{item}' in workspace."
                )

        # Auto-detect job type when using default
        effective_job_type = job_type
        if job_type == "DefaultJob" and resolved_item_type in _ITEM_JOB_TYPES:
            effective_job_type = _ITEM_JOB_TYPES[resolved_item_type]

        response = await fabric_client._make_request(
            endpoint=f"workspaces/{context['workspace_id']}/items/{item_id}/jobs/{effective_job_type}/schedules",
            params=schedule,
            method="post",
        )
        return response
    except Exception as exc:
        logger.error("Error setting schedule: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def create_data_pipeline(
    pipeline_name: str,
    pipeline_definition: Dict[str, Any],
    workspace: Optional[str] = None,
    description: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """
    Create a Data Pipeline in a Fabric workspace with custom activities and dependencies.

    Perfect for orchestrating medallion architecture workflows (Bronze → Silver → Gold).

    Args:
        pipeline_name: Name for the pipeline
        pipeline_definition: Pipeline JSON definition with activities and dependencies
        workspace: Workspace name or ID (optional, uses context if not provided)
        description: Optional description for the pipeline
        ctx: Context object

    Returns:
        Dictionary with pipeline details including ID and status

    Example - Bronze to Silver to Gold cascade:
        pipeline_definition = {
            "properties": {
                "activities": [
                    {
                        "name": "Bronze_Ingestion",
                        "type": "Notebook",
                        "typeProperties": {
                            "notebook": {"name": "bronze_ingest_notebook"}
                        },
                        "dependsOn": []
                    },
                    {
                        "name": "Silver_Transform",
                        "type": "Notebook",
                        "typeProperties": {
                            "notebook": {"name": "silver_transform_notebook"}
                        },
                        "dependsOn": [
                            {
                                "activity": "Bronze_Ingestion",
                                "dependencyConditions": ["Succeeded"]
                            }
                        ]
                    },
                    {
                        "name": "Gold_Transform",
                        "type": "Notebook",
                        "typeProperties": {
                            "notebook": {"name": "gold_transform_notebook"}
                        },
                        "dependsOn": [
                            {
                                "activity": "Silver_Transform",
                                "dependencyConditions": ["Succeeded"]
                            }
                        ]
                    }
                ]
            }
        }

        create_data_pipeline(
            pipeline_name="Medallion_ETL_Pipeline",
            pipeline_definition=pipeline_definition,
            workspace="PROD-Analytics",
            description="Orchestrates Bronze → Silver → Gold transformations"
        )
    """
    try:
        context = await _resolve_workspace(ctx, workspace)
        fabric_client = context["fabric_client"]

        logger.info(f"Creating pipeline '{pipeline_name}' in workspace '{context['workspace_name']}'")

        response = await fabric_client.create_pipeline(
            workspace_id=context["workspace_id"],
            pipeline_name=pipeline_name,
            pipeline_definition=pipeline_definition,
            description=description,
        )

        return {
            "success": True,
            "pipeline": response,
            "workspace": context["workspace_name"],
            "pipeline_name": pipeline_name,
        }

    except Exception as exc:
        logger.error("Failed to create data pipeline: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def get_pipeline_definition(
    pipeline: str,
    workspace: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """
    Get the definition of an existing Data Pipeline including activities and dependencies.

    Args:
        pipeline: Pipeline name or ID
        workspace: Workspace name or ID (optional, uses context if not provided)
        ctx: Context object

    Returns:
        Dictionary with pipeline definition including decoded activities

    Example:
        get_pipeline_definition(
            pipeline="Medallion_ETL_Pipeline",
            workspace="PROD-Analytics"
        )
    """
    try:
        context = await _resolve_workspace_item(ctx, workspace, pipeline, "DataPipeline")
        fabric_client = context["fabric_client"]

        logger.info(f"Retrieving pipeline definition for '{context['item_name']}'")

        response = await fabric_client.get_pipeline_definition(
            workspace_id=context["workspace_id"],
            pipeline_id=context["item_id"],
        )

        return {
            "success": True,
            "workspace": context["workspace_name"],
            "pipeline_name": context["item_name"],
            "definition": response,
        }

    except Exception as exc:
        logger.error("Failed to get pipeline definition: %s", exc)
        return {"error": str(exc)}


