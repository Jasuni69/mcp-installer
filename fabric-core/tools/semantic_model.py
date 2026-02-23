from helpers.utils.context import mcp, __ctx_cache
from mcp.server.fastmcp import Context
from helpers.utils.authentication import get_azure_credentials
from helpers.clients import (
    FabricApiClient,
    SemanticModelClient,
)
from helpers.logging_config import get_logger

from typing import Optional, Dict, Any, List
import json

logger = get_logger(__name__)


@mcp.tool()
async def list_semantic_models(
    workspace: Optional[str] = None, ctx: Context = None
) -> str:
    """List all semantic models in a Fabric workspace.

    Args:
        workspace: Name or ID of the workspace (optional)
        ctx: Context object containing client information

    Returns:
        A string containing the list of semantic models or an error message.
    """
    try:
        client = SemanticModelClient(
            FabricApiClient(get_azure_credentials(ctx.client_id, __ctx_cache))
        )

        workspace_ref = workspace if workspace else __ctx_cache[f"{ctx.client_id}_workspace"]
        models = await client.list_semantic_models(workspace_ref)

        if not models:
            return f"No semantic models found in workspace '{workspace_ref}'."

        markdown = f"# Semantic Models in workspace '{workspace_ref}'\n\n"
        markdown += "| ID | Name | Folder ID | Description |\n"
        markdown += "|-----|------|-----------|-------------|\n"

        for model in models:
            markdown += f"| {model.get('id', 'N/A')} | {model.get('displayName', 'N/A')} | {model.get('folderId', 'N/A')} | {model.get('description', 'N/A')} |\n"

        return markdown

    except Exception as e:
        return f"Error listing semantic models: {str(e)}"


@mcp.tool()
async def get_semantic_model(
    workspace: Optional[str] = None,
    model_id: Optional[str] = None,
    ctx: Context = None,
) -> str:
    """Get a specific semantic model by ID.

    Args:
        workspace: Name or ID of the workspace (optional)
        model_id: ID of the semantic model (optional)
        ctx: Context object containing client information

    Returns:
        A string containing the details of the semantic model or an error message.
    """
    try:
        fabric_client = FabricApiClient(get_azure_credentials(ctx.client_id, __ctx_cache))
        client = SemanticModelClient(fabric_client)

        workspace_ref = workspace if workspace else __ctx_cache[f"{ctx.client_id}_workspace"]
        _, workspace_id = await fabric_client.resolve_workspace_name_and_id(workspace_ref)

        model = await client.get_semantic_model(
            workspace_id,
            model_id if model_id else __ctx_cache[f"{ctx.client_id}_semantic_model"],
        )

        return f"Semantic Model '{model['displayName']}' details:\n\n{model}"

    except Exception as e:
        return f"Error retrieving semantic model: {str(e)}"


@mcp.tool()
async def get_model_schema(
    workspace: Optional[str] = None,
    model: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Get the complete schema of a semantic model including tables, columns, measures, and relationships.

    This retrieves the model definition in TMSL format and parses the structure.

    Args:
        workspace: Name or ID of the workspace (optional)
        model: Name or ID of the semantic model (optional)
        ctx: Context object containing client information

    Returns:
        A dictionary containing the model schema with tables, columns, measures, and relationships.
    """
    try:
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        # Resolve workspace and model
        ws = workspace or __ctx_cache.get(f"{ctx.client_id}_workspace")
        if not ws:
            return {"error": "Workspace must be specified or set with set_workspace."}

        workspace_name, workspace_id = await fabric_client.resolve_workspace_name_and_id(ws)

        model_ref = model or __ctx_cache.get(f"{ctx.client_id}_semantic_model")
        if not model_ref:
            return {"error": "Model must be specified or set."}

        model_name, model_id = await fabric_client.resolve_item_name_and_id(
            workspace=workspace_id, item=model_ref, type="SemanticModel"
        )

        # Get model definition using Fabric API
        definition_response = await fabric_client._make_request(
            endpoint=f"workspaces/{workspace_id}/semanticModels/{model_id}/getDefinition",
            method="post",
            lro=True,
        )

        logger.info(f"Got model definition for {model_name}")

        # Parse the definition to extract schema information
        # The definition comes in TMSL format with model.bim file
        schema = {
            "modelName": model_name,
            "modelId": model_id,
            "workspaceId": workspace_id,
            "tables": [],
            "relationships": [],
            "measures": [],
            "definition": definition_response
        }

        # If we have the definition, parse it
        if isinstance(definition_response, dict) and "definition" in definition_response:
            def_parts = definition_response["definition"].get("parts", [])

            for part in def_parts:
                if part.get("path") == "model.bim":
                    # This contains the TMSL model definition
                    payload_content = part.get("payload")
                    if payload_content:
                        # Parse the model.bim JSON
                        try:
                            model_bim = json.loads(payload_content) if isinstance(payload_content, str) else payload_content
                            model_def = model_bim.get("model", {})

                            # Extract tables and columns
                            tables_list = model_def.get("tables", [])
                            for table in tables_list:
                                table_info = {
                                    "name": table.get("name"),
                                    "isHidden": table.get("isHidden", False),
                                    "columns": [],
                                    "measures": []
                                }

                                # Extract columns
                                for col in table.get("columns", []):
                                    table_info["columns"].append({
                                        "name": col.get("name"),
                                        "dataType": col.get("dataType"),
                                        "isHidden": col.get("isHidden", False),
                                        "sourceColumn": col.get("sourceColumn")
                                    })

                                # Extract measures from this table
                                for measure in table.get("measures", []):
                                    measure_info = {
                                        "name": measure.get("name"),
                                        "expression": measure.get("expression"),
                                        "formatString": measure.get("formatString"),
                                        "isHidden": measure.get("isHidden", False),
                                        "table": table.get("name")
                                    }
                                    table_info["measures"].append(measure_info)
                                    schema["measures"].append(measure_info)

                                schema["tables"].append(table_info)

                            # Extract relationships
                            relationships_list = model_def.get("relationships", [])
                            for rel in relationships_list:
                                schema["relationships"].append({
                                    "name": rel.get("name"),
                                    "fromTable": rel.get("fromTable"),
                                    "fromColumn": rel.get("fromColumn"),
                                    "toTable": rel.get("toTable"),
                                    "toColumn": rel.get("toColumn"),
                                    "crossFilteringBehavior": rel.get("crossFilteringBehavior")
                                })

                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse model.bim: {e}")

        # Remove the full definition to keep response clean
        schema.pop("definition", None)

        return schema

    except Exception as exc:
        logger.error(f"Error getting model schema: {exc}")
        return {"error": str(exc)}


@mcp.tool()
async def list_measures(
    workspace: Optional[str] = None,
    model: Optional[str] = None,
    ctx: Context = None,
) -> List[Dict[str, Any]]:
    """List all DAX measures in a semantic model.

    Args:
        workspace: Name or ID of the workspace (optional)
        model: Name or ID of the semantic model (optional)
        ctx: Context object containing client information

    Returns:
        A list of measures with their definitions.
    """
    try:
        # Get the full schema
        schema = await get_model_schema(workspace=workspace, model=model, ctx=ctx)

        if "error" in schema:
            return schema

        measures = schema.get("measures", [])

        return {
            "modelName": schema.get("modelName"),
            "measureCount": len(measures),
            "measures": measures
        }

    except Exception as exc:
        logger.error(f"Error listing measures: {exc}")
        return {"error": str(exc)}


@mcp.tool()
async def get_measure(
    measure_name: str,
    workspace: Optional[str] = None,
    model: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Get a specific DAX measure definition by name.

    Args:
        measure_name: Name of the measure to retrieve
        workspace: Name or ID of the workspace (optional)
        model: Name or ID of the semantic model (optional)
        ctx: Context object containing client information

    Returns:
        The measure definition including DAX expression.
    """
    try:
        measures_result = await list_measures(workspace=workspace, model=model, ctx=ctx)

        if "error" in measures_result:
            return measures_result

        measures = measures_result.get("measures", [])

        for measure in measures:
            if measure.get("name") == measure_name:
                return {
                    "found": True,
                    "measure": measure
                }

        return {
            "found": False,
            "error": f"Measure '{measure_name}' not found in model"
        }

    except Exception as exc:
        logger.error(f"Error getting measure: {exc}")
        return {"error": str(exc)}


@mcp.tool()
async def create_measure(
    measure_name: str,
    dax_expression: str,
    table_name: str,
    workspace: Optional[str] = None,
    model: Optional[str] = None,
    format_string: Optional[str] = None,
    description: Optional[str] = None,
    is_hidden: bool = False,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Create a new DAX measure in a semantic model.

    Args:
        measure_name: Name of the measure to create
        dax_expression: DAX formula for the measure
        table_name: Name of the table to add the measure to
        workspace: Name or ID of the workspace (optional)
        model: Name or ID of the semantic model (optional)
        format_string: Display format string (e.g., "#,0.00", "0.0%") (optional)
        description: Description of the measure (optional)
        is_hidden: Whether to hide the measure from client tools (default: False)
        ctx: Context object containing client information

    Returns:
        A dictionary containing success status and the created measure details.
    """
    try:
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        # Resolve workspace and model
        ws = workspace or __ctx_cache.get(f"{ctx.client_id}_workspace")
        if not ws:
            return {"error": "Workspace must be specified or set with set_workspace."}

        workspace_name, workspace_id = await fabric_client.resolve_workspace_name_and_id(ws)

        model_ref = model or __ctx_cache.get(f"{ctx.client_id}_semantic_model")
        if not model_ref:
            return {"error": "Model must be specified or set."}

        model_name, model_id = await fabric_client.resolve_item_name_and_id(
            workspace=workspace_id, item=model_ref, type="SemanticModel"
        )

        # Get current model definition
        definition_response = await fabric_client._make_request(
            endpoint=f"workspaces/{workspace_id}/semanticModels/{model_id}/getDefinition",
            method="post",
            lro=True,
        )

        if not isinstance(definition_response, dict) or "definition" not in definition_response:
            return {"error": "Failed to retrieve model definition"}

        # Parse and modify the model.bim
        def_parts = definition_response["definition"].get("parts", [])
        model_bim_part = None
        model_bim_index = -1

        for i, part in enumerate(def_parts):
            if part.get("path") == "model.bim":
                model_bim_part = part
                model_bim_index = i
                break

        if not model_bim_part:
            return {"error": "model.bim not found in definition"}

        # Parse the model.bim JSON
        payload_content = model_bim_part.get("payload")
        model_bim = json.loads(payload_content) if isinstance(payload_content, str) else payload_content
        model_def = model_bim.get("model", {})
        tables_list = model_def.get("tables", [])

        # Find the target table
        target_table = None
        for table in tables_list:
            if table.get("name") == table_name:
                target_table = table
                break

        if not target_table:
            return {"error": f"Table '{table_name}' not found in model"}

        # Check if measure already exists
        existing_measures = target_table.get("measures", [])
        for measure in existing_measures:
            if measure.get("name") == measure_name:
                return {"error": f"Measure '{measure_name}' already exists in table '{table_name}'"}

        # Create new measure object
        new_measure = {
            "name": measure_name,
            "expression": dax_expression,
            "isHidden": is_hidden
        }

        if format_string:
            new_measure["formatString"] = format_string
        if description:
            new_measure["description"] = description

        # Add measure to table
        if "measures" not in target_table:
            target_table["measures"] = []
        target_table["measures"].append(new_measure)

        # Update the model.bim in the definition
        updated_payload = json.dumps(model_bim)
        def_parts[model_bim_index]["payload"] = updated_payload

        # Call updateDefinition API
        update_request = {
            "definition": {
                "parts": def_parts
            }
        }

        update_response = await fabric_client._make_request(
            endpoint=f"workspaces/{workspace_id}/semanticModels/{model_id}/updateDefinition",
            method="post",
            params=update_request,
            lro=True,
        )

        logger.info(f"Created measure '{measure_name}' in table '{table_name}' of model '{model_name}'")

        return {
            "success": True,
            "message": f"Measure '{measure_name}' created successfully",
            "measure": new_measure,
            "table": table_name,
            "model": model_name
        }

    except Exception as exc:
        logger.error(f"Error creating measure: {exc}")
        return {"error": str(exc)}


@mcp.tool()
async def update_measure(
    measure_name: str,
    workspace: Optional[str] = None,
    model: Optional[str] = None,
    dax_expression: Optional[str] = None,
    format_string: Optional[str] = None,
    description: Optional[str] = None,
    is_hidden: Optional[bool] = None,
    new_name: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Update an existing DAX measure in a semantic model.

    Args:
        measure_name: Current name of the measure to update
        workspace: Name or ID of the workspace (optional)
        model: Name or ID of the semantic model (optional)
        dax_expression: New DAX formula (optional)
        format_string: New display format string (optional)
        description: New description (optional)
        is_hidden: New hidden status (optional)
        new_name: New name for the measure (optional)
        ctx: Context object containing client information

    Returns:
        A dictionary containing success status and the updated measure details.
    """
    try:
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        # Resolve workspace and model
        ws = workspace or __ctx_cache.get(f"{ctx.client_id}_workspace")
        if not ws:
            return {"error": "Workspace must be specified or set with set_workspace."}

        workspace_name, workspace_id = await fabric_client.resolve_workspace_name_and_id(ws)

        model_ref = model or __ctx_cache.get(f"{ctx.client_id}_semantic_model")
        if not model_ref:
            return {"error": "Model must be specified or set."}

        model_name, model_id = await fabric_client.resolve_item_name_and_id(
            workspace=workspace_id, item=model_ref, type="SemanticModel"
        )

        # Get current model definition
        definition_response = await fabric_client._make_request(
            endpoint=f"workspaces/{workspace_id}/semanticModels/{model_id}/getDefinition",
            method="post",
            lro=True,
        )

        if not isinstance(definition_response, dict) or "definition" not in definition_response:
            return {"error": "Failed to retrieve model definition"}

        # Parse and modify the model.bim
        def_parts = definition_response["definition"].get("parts", [])
        model_bim_part = None
        model_bim_index = -1

        for i, part in enumerate(def_parts):
            if part.get("path") == "model.bim":
                model_bim_part = part
                model_bim_index = i
                break

        if not model_bim_part:
            return {"error": "model.bim not found in definition"}

        # Parse the model.bim JSON
        payload_content = model_bim_part.get("payload")
        model_bim = json.loads(payload_content) if isinstance(payload_content, str) else payload_content
        model_def = model_bim.get("model", {})
        tables_list = model_def.get("tables", [])

        # Find the measure
        measure_found = False
        target_table_name = None
        for table in tables_list:
            measures = table.get("measures", [])
            for measure in measures:
                if measure.get("name") == measure_name:
                    measure_found = True
                    target_table_name = table.get("name")

                    # Update measure properties
                    if dax_expression is not None:
                        measure["expression"] = dax_expression
                    if format_string is not None:
                        measure["formatString"] = format_string
                    if description is not None:
                        measure["description"] = description
                    if is_hidden is not None:
                        measure["isHidden"] = is_hidden
                    if new_name is not None:
                        measure["name"] = new_name

                    break
            if measure_found:
                break

        if not measure_found:
            return {"error": f"Measure '{measure_name}' not found in model"}

        # Update the model.bim in the definition
        updated_payload = json.dumps(model_bim)
        def_parts[model_bim_index]["payload"] = updated_payload

        # Call updateDefinition API
        update_request = {
            "definition": {
                "parts": def_parts
            }
        }

        update_response = await fabric_client._make_request(
            endpoint=f"workspaces/{workspace_id}/semanticModels/{model_id}/updateDefinition",
            method="post",
            params=update_request,
            lro=True,
        )

        logger.info(f"Updated measure '{measure_name}' in model '{model_name}'")

        return {
            "success": True,
            "message": f"Measure '{new_name or measure_name}' updated successfully",
            "table": target_table_name,
            "model": model_name
        }

    except Exception as exc:
        logger.error(f"Error updating measure: {exc}")
        return {"error": str(exc)}


@mcp.tool()
async def delete_measure(
    measure_name: str,
    workspace: Optional[str] = None,
    model: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Delete a DAX measure from a semantic model.

    Args:
        measure_name: Name of the measure to delete
        workspace: Name or ID of the workspace (optional)
        model: Name or ID of the semantic model (optional)
        ctx: Context object containing client information

    Returns:
        A dictionary containing success status and deletion details.
    """
    try:
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        # Resolve workspace and model
        ws = workspace or __ctx_cache.get(f"{ctx.client_id}_workspace")
        if not ws:
            return {"error": "Workspace must be specified or set with set_workspace."}

        workspace_name, workspace_id = await fabric_client.resolve_workspace_name_and_id(ws)

        model_ref = model or __ctx_cache.get(f"{ctx.client_id}_semantic_model")
        if not model_ref:
            return {"error": "Model must be specified or set."}

        model_name, model_id = await fabric_client.resolve_item_name_and_id(
            workspace=workspace_id, item=model_ref, type="SemanticModel"
        )

        # Get current model definition
        definition_response = await fabric_client._make_request(
            endpoint=f"workspaces/{workspace_id}/semanticModels/{model_id}/getDefinition",
            method="post",
            lro=True,
        )

        if not isinstance(definition_response, dict) or "definition" not in definition_response:
            return {"error": "Failed to retrieve model definition"}

        # Parse and modify the model.bim
        def_parts = definition_response["definition"].get("parts", [])
        model_bim_part = None
        model_bim_index = -1

        for i, part in enumerate(def_parts):
            if part.get("path") == "model.bim":
                model_bim_part = part
                model_bim_index = i
                break

        if not model_bim_part:
            return {"error": "model.bim not found in definition"}

        # Parse the model.bim JSON
        payload_content = model_bim_part.get("payload")
        model_bim = json.loads(payload_content) if isinstance(payload_content, str) else payload_content
        model_def = model_bim.get("model", {})
        tables_list = model_def.get("tables", [])

        # Find and delete the measure
        measure_found = False
        target_table_name = None
        for table in tables_list:
            measures = table.get("measures", [])
            for i, measure in enumerate(measures):
                if measure.get("name") == measure_name:
                    measure_found = True
                    target_table_name = table.get("name")
                    # Remove the measure from the list
                    measures.pop(i)
                    break
            if measure_found:
                break

        if not measure_found:
            return {"error": f"Measure '{measure_name}' not found in model"}

        # Update the model.bim in the definition
        updated_payload = json.dumps(model_bim)
        def_parts[model_bim_index]["payload"] = updated_payload

        # Call updateDefinition API
        update_request = {
            "definition": {
                "parts": def_parts
            }
        }

        update_response = await fabric_client._make_request(
            endpoint=f"workspaces/{workspace_id}/semanticModels/{model_id}/updateDefinition",
            method="post",
            params=update_request,
            lro=True,
        )

        logger.info(f"Deleted measure '{measure_name}' from model '{model_name}'")

        return {
            "success": True,
            "message": f"Measure '{measure_name}' deleted successfully",
            "table": target_table_name,
            "model": model_name
        }

    except Exception as exc:
        logger.error(f"Error deleting measure: {exc}")
        return {"error": str(exc)}


@mcp.tool()
async def analyze_dax_query(
    dax_query: str,
    workspace: Optional[str] = None,
    model: Optional[str] = None,
    include_execution_plan: bool = True,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Analyze a DAX query for performance insights and execution plan.

    This tool executes a DAX query and returns performance metrics including
    execution time, scan counts, and optionally the query execution plan.

    Args:
        dax_query: DAX query to analyze
        workspace: Name or ID of the workspace (optional)
        model: Name or ID of the semantic model (optional)
        include_execution_plan: Whether to include detailed execution plan (default: True)
        ctx: Context object containing client information

    Returns:
        A dictionary containing query results, execution metrics, and optionally the execution plan.
    """
    try:
        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        # Resolve workspace and model
        ws = workspace or __ctx_cache.get(f"{ctx.client_id}_workspace")
        if not ws:
            return {"error": "Workspace must be specified or set with set_workspace."}

        workspace_name, workspace_id = await fabric_client.resolve_workspace_name_and_id(ws)

        model_ref = model or __ctx_cache.get(f"{ctx.client_id}_semantic_model")
        if not model_ref:
            return {"error": "Model must be specified or set."}

        model_name, model_id = await fabric_client.resolve_item_name_and_id(
            workspace=workspace_id, item=model_ref, type="SemanticModel"
        )

        # Execute DAX query with performance analysis
        # Using the Power BI executeQueries endpoint
        query_request = {
            "queries": [
                {
                    "query": dax_query
                }
            ],
            "serializerSettings": {"includeNulls": True},
        }

        import time
        start_time = time.time()

        query_response = await fabric_client._make_request(
            endpoint=f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/datasets/{model_id}/executeQueries",
            method="post",
            params=query_request,
            token_scope="https://analysis.windows.net/powerbi/api/.default",
        )

        execution_time = time.time() - start_time

        # Parse the response
        result = {
            "modelName": model_name,
            "modelId": model_id,
            "workspaceId": workspace_id,
            "executionTimeSeconds": round(execution_time, 3),
            "query": dax_query
        }

        if isinstance(query_response, dict):
            # Extract results from response
            results = query_response.get("results", [])
            if results:
                first_result = results[0]

                # Add table data if present
                tables = first_result.get("tables", [])
                if tables:
                    first_table = tables[0]
                    rows = first_table.get("rows", [])
                    result["rowCount"] = len(rows)

                    # Get column names
                    columns = first_table.get("columns", [])
                    if columns:
                        result["columns"] = []
                        for col in columns:
                            col_name = col.get("name") or col.get("columnName", "Unknown")
                            result["columns"].append(col_name)

                    # Sample rows (first 10)
                    result["sampleRows"] = rows[:10] if rows else []

        # If execution plan requested, add basic metrics
        # Note: Full execution plan analysis requires XMLA endpoint access
        if include_execution_plan:
            result["executionPlan"] = {
                "note": "Full execution plan analysis requires XMLA endpoint access via external tools",
                "basicMetrics": {
                    "executionTimeSeconds": result["executionTimeSeconds"],
                    "rowsReturned": result.get("rowCount", 0)
                },
                "recommendation": "For detailed performance analysis, use DAX Studio or Tabular Editor with XMLA endpoint"
            }

        logger.info(f"Analyzed DAX query on model '{model_name}': {execution_time:.3f}s, {result.get('rowCount', 0)} rows")

        return result

    except Exception as exc:
        logger.error(f"Error analyzing DAX query: {exc}")
        return {"error": str(exc)}
