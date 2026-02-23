import json
from typing import Any, Dict, Optional

from mcp.server.fastmcp import Context

from helpers.clients import FabricApiClient
from helpers.logging_config import get_logger
from helpers.utils.authentication import get_azure_credentials
from helpers.utils.context import mcp, __ctx_cache


logger = get_logger(__name__)


AUDIENCE_SCOPES = {
    "fabric": "https://api.fabric.microsoft.com/.default",
    "powerbi": "https://analysis.windows.net/powerbi/api/.default",
    "graph": "https://graph.microsoft.com/.default",
    "storage": "https://storage.azure.com/.default",
    "azure": "https://management.azure.com/.default",
}

AUDIENCE_BASE_URLS = {
    "fabric": "https://api.fabric.microsoft.com",
    "powerbi": "https://api.powerbi.com",
    "graph": "https://graph.microsoft.com",
    "storage": "https://onelake.dfs.fabric.microsoft.com",
    "azure": "https://management.azure.com",
}


@mcp.tool()
async def raw_api_call(
    endpoint: str,
    method: str = "GET",
    audience: str = "fabric",
    body: Optional[str] = None,
    lro: bool = False,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Call any Microsoft API directly. Covers gaps where no dedicated tool exists.

    Uses the same retry logic, LRO polling, and error handling as all other tools.
    Supports Fabric REST, Power BI, Microsoft Graph, OneLake, and Azure ARM APIs.

    Args:
        endpoint: API path (e.g. "/v1/workspaces" for Fabric, "/v1.0/me" for Graph).
                  Can be relative (prepends base URL) or absolute (https://...).
        method: HTTP method — GET, POST, PATCH, PUT, DELETE
        audience: Target API — "fabric", "powerbi", "graph", "storage", or "azure"
        body: JSON request body as a string (for POST/PATCH/PUT). Pass null for GET/DELETE.
        lro: Set True for long-running operations (202 + polling). Default False.
        ctx: FastMCP context
    """
    try:
        if ctx is None:
            raise ValueError("Context is required.")

        audience_lower = audience.strip().lower()
        if audience_lower not in AUDIENCE_SCOPES:
            raise ValueError(
                f"Unknown audience '{audience}'. Must be one of: {', '.join(AUDIENCE_SCOPES.keys())}"
            )

        token_scope = AUDIENCE_SCOPES[audience_lower]
        base_url = AUDIENCE_BASE_URLS[audience_lower]

        # Build absolute URL
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            url = endpoint
        else:
            url = f"{base_url}/{endpoint.lstrip('/')}"

        # Parse body
        parsed_body = None
        if body:
            try:
                parsed_body = json.loads(body)
            except json.JSONDecodeError:
                return {"error": f"Invalid JSON in body: {body[:200]}"}

        credential = get_azure_credentials(ctx.client_id, __ctx_cache)
        fabric_client = FabricApiClient(credential)

        response = await fabric_client._make_request(
            endpoint=url,
            method=method.strip().upper(),
            params=parsed_body or {},
            token_scope=token_scope,
            lro=lro,
            lro_poll_interval=5,
            lro_timeout=300,
            raw_mode=True,
        )

        return response if isinstance(response, dict) else {"result": response}
    except Exception as exc:
        logger.error("raw_api_call error: %s", exc)
        return {"error": str(exc)}
