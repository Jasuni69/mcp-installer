from helpers.logging_config import get_logger
from helpers.clients.fabric_client import FabricApiClient
from helpers.utils import _is_valid_uuid
from typing import Optional, Dict, Any

logger = get_logger(__name__)


class WarehouseClient:
    def __init__(self, client: FabricApiClient):
        self.client = client

    async def list_warehouses(self, workspace: str):
        """List all warehouses in a workspace."""
        if not _is_valid_uuid(workspace):
            (_, workspace) = await self.client.resolve_workspace_name_and_id(workspace)
        warehouses = await self.client.get_warehouses(workspace)

        if not warehouses:
            return f"No warehouses found in workspace '{workspace}'."

        markdown = f"# Warehouses in workspace '{workspace}'\n\n"
        markdown += "| ID | Name |\n"
        markdown += "|-----|------|\n"

        for wh in warehouses:
            markdown += f"| {wh['id']} | {wh['displayName']} |\n"

        return markdown

    async def get_warehouse(
        self,
        workspace: str,
        warehouse: str,
    ) -> Optional[Dict[str, Any]]:
        """Get details of a specific warehouse."""
        if not warehouse:
            raise ValueError("Warehouse name cannot be empty.")

        return await self.client.get_item(
            workspace_id=workspace, item_id=warehouse, item_type="warehouse"
        )

    async def create_warehouse(
        self,
        name: str,
        workspace: str,
        description: Optional[str] = None,
        folder_id: Optional[str] = None,
    ):
        """Create a new warehouse."""
        if not name:
            raise ValueError("Warehouse name cannot be empty.")

        return await self.client.create_item(
            name=name,
            workspace=workspace,
            description=description,
            type="Warehouse",
            lro=True,
            folder_id=folder_id,
        )
