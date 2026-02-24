from azure.identity import DefaultAzureCredential
from cachetools import TTLCache


def get_azure_credentials(session_id: str, cache: TTLCache) -> DefaultAzureCredential:
    """
    Get or create cached Azure credentials keyed by MCP session ID.
    """
    key = f"{session_id}_creds"
    if key not in cache:
        cache[key] = DefaultAzureCredential()
    return cache[key]
