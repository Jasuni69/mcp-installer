from typing import Any, Dict

from mcp.server.fastmcp import Context

from helpers.clients import FabricApiClient
from helpers.logging_config import get_logger
from helpers.utils.authentication import get_azure_credentials
from helpers.utils.context import mcp, __ctx_cache


logger = get_logger(__name__)


@mcp.tool()
async def list_tenant_settings(
    ctx: Context = None,
) -> Dict[str, Any]:
    """List all Fabric tenant settings for the organization.

    Returns admin-level tenant configuration: feature toggles, capacity
    delegation, export settings, etc. Requires Fabric Admin role.

    Args:
        ctx: Context object containing client information

    Returns:
        Dictionary with tenant settings list.
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        response = await fabric_client._make_request(
            endpoint="admin/tenantsettings"
        )

        settings = []
        if isinstance(response, dict):
            settings = response.get("tenantSettings", response.get("value", []))
        elif isinstance(response, list):
            settings = response

        return {"settings": settings, "count": len(settings)}
    except Exception as exc:
        logger.error("Failed to list tenant settings: %s", exc)
        return {"error": str(exc)}
