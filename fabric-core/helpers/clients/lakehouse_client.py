from helpers.utils import _is_valid_uuid
from helpers.logging_config import get_logger
from helpers.clients.fabric_client import FabricApiClient
from typing import Optional, Dict, Any

logger = get_logger(__name__)


class LakehouseClient:
    def __init__(self, client: FabricApiClient):
        self.client = client

    async def list_lakehouses(self, workspace: str):
        """List all lakehouses in a workspace."""
        # Resolve workspace name to ID if needed
        workspace_name, workspace_id = await self.client.resolve_workspace_name_and_id(workspace)

        lakehouses = await self.client.get_lakehouses(workspace_id)

        if not lakehouses:
            return f"No lakehouses found in workspace '{workspace_name or workspace}'."

        markdown = f"# Lakehouses in workspace '{workspace_name or workspace}'\n\n"
        markdown += "| ID | Name |\n"
        markdown += "|-----|------|\n"

        for lh in lakehouses:
            markdown += f"| {lh['id']} | {lh['displayName']} |\n"

        return markdown

    async def get_lakehouse(
        self,
        workspace: str,
        lakehouse: str,
    ) -> Optional[Dict[str, Any]]:
        """Get details of a specific lakehouse."""
        # Resolve workspace name to ID if needed
        _, workspace_id = await self.client.resolve_workspace_name_and_id(workspace)

        if not lakehouse:
            raise ValueError("Lakehouse name cannot be empty.")

        response = await self.client.get_item(
            workspace_id=workspace_id, item_id=lakehouse, item_type="lakehouse"
        )
        logger.info(f"Lakehouse details: {response}")
        return response

    async def resolve_lakehouse(self, workspace_id: str, lakehouse_name: str):
        """Resolve lakehouse name to lakehouse ID."""
        return await self.client.resolve_item_name_and_id(
            workspace=workspace_id, item=lakehouse_name, type="Lakehouse"
        )

    async def create_lakehouse(
        self,
        name: str,
        workspace: str,
        description: Optional[str] = None,
        enable_schemas: bool = True,
        folder_id: Optional[str] = None,
    ):
        """Create a new lakehouse."""
        # Resolve workspace to ID if a name was provided
        if not _is_valid_uuid(workspace):
            (_, workspace) = await self.client.resolve_workspace_name_and_id(workspace)

        if not name:
            raise ValueError("Lakehouse name cannot be empty.")

        creation_payload = None
        if enable_schemas:
            creation_payload = {"enableSchemas": True}

        return await self.client.create_item(
            name=name,
            workspace=workspace,
            description=description,
            type="Lakehouse",
            folder_id=folder_id,
            creation_payload=creation_payload,
        )
