from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context

from helpers.clients import FabricApiClient
from helpers.logging_config import get_logger
from helpers.utils.authentication import get_azure_credentials
from helpers.utils.context import mcp, __ctx_cache


logger = get_logger(__name__)


@mcp.tool()
async def list_capacities(
    ctx: Context = None,
) -> Dict[str, Any]:
    """List all Fabric and Power BI capacities accessible to the current user.

    Returns capacity IDs, display names, SKUs, regions, and state.
    Use capacity IDs when creating workspaces or assigning workspaces to capacity.
    """
    try:
        if ctx is None:
            raise ValueError("Context (ctx) must be provided.")

        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        response = await fabric_client._make_request(
            endpoint="capacities",
            use_pagination=True,
        )

        if not response:
            return {"capacities": [], "message": "No capacities found."}

        return {"capacities": response}
    except Exception as exc:
        logger.error("Error listing capacities: %s", exc)
        return {"error": str(exc)}
