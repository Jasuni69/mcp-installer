from helpers.utils.context import mcp, __ctx_cache
from mcp.server.fastmcp import Context
from helpers.utils.authentication import get_azure_credentials
from helpers.clients import FabricApiClient
from helpers.logging_config import get_logger
import asyncio
import tempfile
import os
import requests
from typing import Optional

logger = get_logger(__name__)


@mcp.tool()
async def load_data_from_url(
    url: str,
    destination_table: str,
    workspace: Optional[str] = None,
    lakehouse: Optional[str] = None,
    warehouse: Optional[str] = None,
    ctx: Context = None,
) -> str:
    """Load data from a URL into a delta table in a lakehouse via OneLake.

    Args:
        url: The URL to download data from (CSV or Parquet supported).
        destination_table: The name of the table to load data into.
        workspace: Name or ID of the workspace (optional).
        lakehouse: Name or ID of the lakehouse (optional).
        warehouse: Name or ID of the warehouse (optional, uses SQL for warehouses).
        ctx: Context object containing client information.
    Returns:
        A string confirming the data load or an error message.
    """
    try:
        # Download the file
        response = requests.get(url, timeout=120)
        if response.status_code != 200:
            return f"Failed to download file from URL: {url}"
        file_ext = url.split("?")[0].split(".")[-1].lower()
        if file_ext not in ("csv", "parquet"):
            return f"Unsupported file type: {file_ext}. Only CSV and Parquet are supported."
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=f".{file_ext}"
        ) as tmp_file:
            tmp_file.write(response.content)
            tmp_path = tmp_file.name

        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        workspace_ref = workspace or __ctx_cache.get(f"{ctx.client_id}_workspace")
        if not workspace_ref:
            os.remove(tmp_path)
            return "Workspace not set. Please set a workspace using set_workspace."

        resource_type = None
        resource_ref = None
        if lakehouse:
            resource_type = "lakehouse"
            resource_ref = lakehouse
        elif warehouse:
            resource_type = "warehouse"
            resource_ref = warehouse
        else:
            # Fall back to context
            ctx_lakehouse = __ctx_cache.get(f"{ctx.client_id}_lakehouse")
            ctx_warehouse = __ctx_cache.get(f"{ctx.client_id}_warehouse")
            if ctx_lakehouse:
                resource_type = "lakehouse"
                resource_ref = ctx_lakehouse
            elif ctx_warehouse:
                resource_type = "warehouse"
                resource_ref = ctx_warehouse
            else:
                os.remove(tmp_path)
                return "Either lakehouse or warehouse must be specified or set via set_lakehouse/set_warehouse."

        try:
            import pyarrow as pa
            import pyarrow.csv as pcsv
            import pyarrow.parquet as pq
            from deltalake import write_deltalake

            if file_ext == "csv":
                table = pcsv.read_csv(tmp_path)
            else:
                table = pq.read_table(tmp_path)

            row_count = table.num_rows

            # Resolve workspace and lakehouse IDs
            _, workspace_id = await fabric_client.resolve_workspace_name_and_id(
                workspace_ref
            )

            if resource_type == "lakehouse":
                _, lakehouse_id = await fabric_client.resolve_item_name_and_id(
                    item=resource_ref, type="Lakehouse", workspace=workspace_id
                )

                # Write directly to OneLake as delta table
                table_path = (
                    f"abfss://{workspace_id}@onelake.dfs.fabric.microsoft.com"
                    f"/{lakehouse_id}/Tables/{destination_table}"
                )
                token = credential.get_token(
                    "https://storage.azure.com/.default"
                ).token
                storage_options = {
                    "bearer_token": token,
                    "use_fabric_endpoint": "true",
                }

                await asyncio.to_thread(
                    write_deltalake,
                    table_path,
                    table,
                    mode="overwrite",
                    schema_mode="overwrite",
                    storage_options=storage_options,
                )
            else:
                # Warehouse: use SQL endpoint (warehouses support DDL)
                from helpers.clients import get_sql_endpoint
                from helpers.clients.sql_client import SQLClient
                import polars as pl

                _, endpoint = await get_sql_endpoint(
                    workspace=workspace_ref,
                    warehouse=resource_ref,
                    type="warehouse",
                    credential=credential,
                )
                if not endpoint:
                    return f"Unable to resolve SQL endpoint for warehouse '{resource_ref}'."

                df = pl.from_arrow(table)
                sql_client = SQLClient(
                    endpoint["server"], endpoint["database"], credential
                )
                await asyncio.to_thread(
                    sql_client.load_data, df, destination_table, "replace"
                )

            return f"Loaded {row_count} rows from {url} into table '{destination_table}' in {resource_type} '{resource_ref}'."
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception as e:
        return f"Error loading data: {str(e)}"
