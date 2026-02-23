import struct
import urllib.parse
from itertools import chain, repeat
from typing import Any, Dict, Optional, Tuple

import polars as pl
from azure.identity import DefaultAzureCredential
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import ResourceClosedError

from helpers.logging_config import get_logger
from helpers.clients.fabric_client import FabricApiClient
from helpers.clients.lakehouse_client import LakehouseClient
from helpers.clients.warehouse_client import WarehouseClient


logger = get_logger(__name__)

DRIVER = "{ODBC Driver 18 for SQL Server}"
RESOURCE_URL = "https://database.windows.net/.default"


def _build_access_token_bytes(token: str) -> bytes:
    token_as_bytes = token.encode("utf-8")
    encoded_bytes = bytes(chain.from_iterable(zip(token_as_bytes, repeat(0))))
    return struct.pack("<i", len(encoded_bytes)) + encoded_bytes


def _parse_connection_string(connection_string: str) -> Tuple[str, str]:
    if not connection_string:
        raise ValueError("Connection string is empty.")

    components: Dict[str, str] = {}
    for segment in connection_string.split(";"):
        if not segment or "=" not in segment:
            continue
        key, value = segment.split("=", 1)
        components[key.strip().lower()] = value.strip()

    server = components.get("data source") or components.get("server")
    database = components.get("initial catalog") or components.get("database")

    if not server or not database:
        raise ValueError("Unable to parse server or database from connection string.")

    return server, database


def _create_engine(
    server: str,
    database: str,
    credential: DefaultAzureCredential,
    driver: str = DRIVER,
) -> Engine:
    connection_string = (
        f"Driver={driver};Server={server};Database={database};Encrypt=Yes;TrustServerCertificate=No"
    )
    params = urllib.parse.quote(connection_string)

    token = credential.get_token(RESOURCE_URL)
    attrs_before = {1256: _build_access_token_bytes(token.token)}

    return create_engine(
        f"mssql+pyodbc:///?odbc_connect={params}",
        connect_args={"attrs_before": attrs_before},
    )


async def get_sql_endpoint(
    workspace: Optional[str] = None,
    lakehouse: Optional[str] = None,
    warehouse: Optional[str] = None,
    type: Optional[str] = None,
    credential: Optional[DefaultAzureCredential] = None,
) -> Tuple[Optional[str], Optional[Dict[str, str]]]:
    try:
        credential = credential or DefaultAzureCredential()
        client = FabricApiClient(credential)

        _, workspace_id = await client.resolve_workspace_name_and_id(workspace)

        connection_string: Optional[str] = None
        resource_name: Optional[str] = None
        resource_id: Optional[str] = None

        if type and type.lower() == "lakehouse":
            lakehouse_client = LakehouseClient(client)
            resource_name, resource_id = await client.resolve_item_name_and_id(
                workspace=workspace_id, item=lakehouse, type="Lakehouse"
            )
            lakehouse_obj = await lakehouse_client.get_lakehouse(
                workspace=workspace_id, lakehouse=resource_id
            )

            # Try to get connection string from lakehouse properties first
            connection_string = (
                lakehouse_obj.get("properties", {})
                .get("sqlEndpointProperties", {})
                .get("connectionString")
            )

            # Find the SQLEndpoint item - we need its ID as the database name
            sql_endpoint_id = None
            items = await client.get_items(workspace_id=workspace_id)
            for item in items:
                if item.get("type") == "SQLEndpoint" and item.get("displayName") == resource_name:
                    sql_endpoint_id = item["id"]
                    logger.info(f"Found SQLEndpoint item: {sql_endpoint_id}")
                    break

            # If no connection string from lakehouse properties, try the SQLEndpoint item
            if not connection_string and sql_endpoint_id:
                logger.info(f"sqlEndpointProperties not found in lakehouse, querying SQLEndpoint item...")
                try:
                    sql_endpoint_details = await client.get_item(
                        workspace_id=workspace_id,
                        item_id=sql_endpoint_id,
                        item_type="sqlendpoint"
                    )
                    connection_string = (
                        sql_endpoint_details.get("properties", {})
                        .get("connectionString")
                    )
                    if connection_string:
                        logger.info("Successfully retrieved connection string from SQLEndpoint item")
                except Exception as e:
                    logger.warning(f"SQLEndpoint typed endpoint failed: {e}")

                # Fallback: try generic items endpoint
                if not connection_string:
                    try:
                        generic_item = await client._make_request(
                            endpoint=f"workspaces/{workspace_id}/items/{sql_endpoint_id}"
                        )
                        connection_string = (
                            generic_item.get("properties", {}).get("connectionString")
                            or generic_item.get("properties", {})
                            .get("sqlEndpointProperties", {})
                            .get("connectionString")
                        )
                        if connection_string:
                            logger.info("Retrieved connection string from generic items endpoint")
                    except Exception as e:
                        logger.warning(f"Fallback generic items endpoint failed: {e}")

            if not sql_endpoint_id:
                logger.warning(f"No SQLEndpoint item found for lakehouse '{resource_name}'")

            # Use the SQL endpoint ID as database, not the lakehouse ID
            if sql_endpoint_id:
                resource_id = sql_endpoint_id
        elif type and type.lower() == "warehouse":
            warehouse_client = WarehouseClient(client)
            resource_name, resource_id = await client.resolve_item_name_and_id(
                workspace=workspace_id, item=warehouse, type="Warehouse"
            )
            warehouse_obj = await warehouse_client.get_warehouse(
                workspace=workspace, warehouse=resource_id
            )
            connection_string = (
                warehouse_obj.get("properties", {})
                .get("connectionString")
            )
        else:
            raise ValueError("Type must be 'lakehouse' or 'warehouse'.")

        if not connection_string:
            return None, None

        # Check if connection_string is just a server name (no semicolons)
        # This is what Fabric API returns for lakehouses and warehouses
        if ";" not in connection_string:
            server = connection_string
            # For both lakehouses and warehouses, the database name is the resource ID
            database = resource_id
            if not database:
                logger.error(f"Cannot determine database name for {type}")
                return None, None
            logger.info(f"Parsed server from hostname: {server}, database: {database}")
        else:
            # It's a full connection string, parse it
            server, database = _parse_connection_string(connection_string)

        return resource_name, {
            "workspaceId": workspace_id,
            "resourceId": resource_id,
            "server": server,
            "database": database,
            "connectionString": connection_string,
        }
    except Exception as exc:
        logger.error("Failed to resolve SQL endpoint: %s", exc)
        return None, None


class SQLClient:
    def __init__(
        self,
        server: str,
        database: str,
        credential: DefaultAzureCredential,
    ) -> None:
        self._server = server
        self._database = database
        self._credential = credential
        self.engine = _create_engine(server, database, credential)

    def _refresh_engine(self) -> None:
        """Recreate engine with fresh token. Azure tokens expire after ~1 hour."""
        if self.engine:
            self.engine.dispose()
        self.engine = _create_engine(self._server, self._database, self._credential)

    def run_query(self, query: str) -> pl.DataFrame:
        try:
            return pl.read_database(query, connection=self.engine)
        except Exception as e:
            if "login" in str(e).lower() or "token" in str(e).lower() or "expired" in str(e).lower():
                logger.info("SQL token may have expired, refreshing engine...")
                self._refresh_engine()
                return pl.read_database(query, connection=self.engine)
            raise

    def load_data(
        self,
        df: pl.DataFrame,
        table_name: str,
        if_exists: str = "append",
    ) -> None:
        pdf = df.to_pandas()
        pdf.to_sql(table_name, con=self.engine, if_exists=if_exists, index=False)

    def execute(self, statement: str) -> Dict[str, Any]:
        """Execute a SQL statement that may not return a result set."""

        with self.engine.connect() as connection:
            result = connection.exec_driver_sql(statement)
            response: Dict[str, Any] = {"rowcount": result.rowcount}
            try:
                rows = result.fetchall()
                columns = list(result.keys())
                response["columns"] = columns
                response["rows"] = [dict(zip(columns, row)) for row in rows]
            except ResourceClosedError:
                response["columns"] = []
                response["rows"] = []
            return response
