import json
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context

from helpers.clients import FabricApiClient
from helpers.logging_config import get_logger
from helpers.utils.authentication import get_azure_credentials
from helpers.utils.context import mcp, __ctx_cache


logger = get_logger(__name__)


@mcp.tool()
async def list_connections(
    ctx: Context = None,
) -> Dict[str, Any]:
    """List all connections accessible to the current user.

    Args:
        ctx: Context object containing client information

    Returns:
        Dictionary with list of connections.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        response = await fabric_client._make_request(
            endpoint="connections"
        )

        connections: List[Dict[str, Any]]
        if isinstance(response, dict):
            connections = response.get("value", [])
        elif isinstance(response, list):
            connections = response
        else:
            connections = []

        return {"connections": connections, "count": len(connections)}
    except Exception as exc:
        logger.error("Failed to list connections: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def create_connection(
    display_name: str,
    connectivity_type: str,
    connection_details: str,
    credential_details: str,
    privacy_level: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Create a new connection.

    Args:
        display_name: Display name for the connection
        connectivity_type: One of "ShareableCloud", "OnPremisesGateway",
            "VirtualNetworkGateway", or "OnPremisesGatewayPersonal"
        connection_details: JSON string with connection type, creation method, and
            parameters. Example: {"type": "SQL", "creationMethod": "SQL",
            "parameters": [{"name": "server", "value": "myserver.database.windows.net"},
            {"name": "database", "value": "mydb"}]}
        credential_details: JSON string with credential configuration. Example:
            {"singleCredential": {"credentialType": "Basic",
            "connectionEncryption": "Encrypted", "skipTestConnection": false,
            "credentials": {"username": "user", "password": "pass"}}}
        privacy_level: Optional privacy level — "None", "Organizational",
            "Private", or "Public"
        ctx: Context object containing client information

    Returns:
        Dictionary with the created connection details.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        parsed_connection_details = json.loads(connection_details)
        parsed_credential_details = json.loads(credential_details)

        payload: Dict[str, Any] = {
            "connectivityType": connectivity_type,
            "displayName": display_name,
            "connectionDetails": parsed_connection_details,
            "credentialDetails": parsed_credential_details,
        }

        if privacy_level is not None:
            payload["privacyLevel"] = privacy_level

        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        response = await fabric_client._make_request(
            endpoint="connections",
            method="post",
            params=payload,
        )

        return response if isinstance(response, dict) else {"result": response}
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in connection parameters: %s", exc)
        return {"error": f"Invalid JSON: {str(exc)}"}
    except Exception as exc:
        logger.error("Failed to create connection '%s': %s", display_name, exc)
        return {"error": str(exc)}


@mcp.tool()
async def get_connection(
    connection_id: str,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Get details for a specific connection.

    Args:
        connection_id: ID of the connection
        ctx: Context object containing client information

    Returns:
        Dictionary with connection details.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        response = await fabric_client._make_request(
            endpoint=f"connections/{connection_id}"
        )

        return response if isinstance(response, dict) else {"result": response}
    except Exception as exc:
        logger.error("Failed to get connection '%s': %s", connection_id, exc)
        return {"error": str(exc)}


@mcp.tool()
async def update_connection(
    connection_id: str,
    connectivity_type: Optional[str] = None,
    connection_details: Optional[str] = None,
    credential_details: Optional[str] = None,
    display_name: Optional[str] = None,
    privacy_level: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Update properties of an existing connection.

    Args:
        connection_id: ID of the connection to update
        connectivity_type: New connectivity type (optional) — "ShareableCloud",
            "OnPremisesGateway", "VirtualNetworkGateway", or "OnPremisesGatewayPersonal"
        connection_details: JSON string with updated connection details (optional)
        credential_details: JSON string with updated credential details (optional)
        display_name: New display name (optional)
        privacy_level: New privacy level (optional) — "None", "Organizational",
            "Private", or "Public"
        ctx: Context object containing client information

    Returns:
        Dictionary with the updated connection details or a confirmation.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        payload: Dict[str, Any] = {}

        if connectivity_type is not None:
            payload["connectivityType"] = connectivity_type
        if display_name is not None:
            payload["displayName"] = display_name
        if privacy_level is not None:
            payload["privacyLevel"] = privacy_level
        if connection_details is not None:
            payload["connectionDetails"] = json.loads(connection_details)
        if credential_details is not None:
            payload["credentialDetails"] = json.loads(credential_details)

        if not payload:
            return {"error": "Nothing to update. Provide at least one field to change."}

        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        response = await fabric_client._make_request(
            endpoint=f"connections/{connection_id}",
            method="patch",
            params=payload,
        )

        return response if isinstance(response, dict) else {"result": response}
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in update parameters for connection '%s': %s", connection_id, exc)
        return {"error": f"Invalid JSON: {str(exc)}"}
    except Exception as exc:
        logger.error("Failed to update connection '%s': %s", connection_id, exc)
        return {"error": str(exc)}


@mcp.tool()
async def delete_connection(
    connection_id: str,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Delete a connection.

    Args:
        connection_id: ID of the connection to delete
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
            endpoint=f"connections/{connection_id}",
            method="delete",
        )

        return {"success": True, "connection_id": connection_id}
    except Exception as exc:
        logger.error("Failed to delete connection '%s': %s", connection_id, exc)
        return {"error": str(exc)}


@mcp.tool()
async def list_supported_connection_types(
    gateway_id: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """List supported connection type definitions.

    Args:
        gateway_id: Optional gateway ID to filter supported types by a specific gateway
        ctx: Context object containing client information

    Returns:
        Dictionary with list of supported connection type definitions.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        endpoint = "connections/supportedConnectionTypes"
        query_params: Dict[str, str] = {}
        if gateway_id is not None:
            query_params["gatewayId"] = gateway_id

        if query_params:
            query_string = "&".join(f"{k}={v}" for k, v in query_params.items())
            endpoint = f"{endpoint}?{query_string}"

        response = await fabric_client._make_request(endpoint=endpoint)

        connection_types: List[Dict[str, Any]]
        if isinstance(response, dict):
            connection_types = response.get("value", [])
        elif isinstance(response, list):
            connection_types = response
        else:
            connection_types = []

        return {"connection_types": connection_types, "count": len(connection_types)}
    except Exception as exc:
        logger.error("Failed to list supported connection types: %s", exc)
        return {"error": str(exc)}
