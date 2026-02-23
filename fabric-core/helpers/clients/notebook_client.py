from helpers.utils import _is_valid_uuid
from helpers.logging_config import get_logger
from helpers.clients.fabric_client import FabricApiClient
from typing import Dict, Any

logger = get_logger(__name__)


class NotebookClient:
    def __init__(self, client: FabricApiClient):
        self.client = client

    async def list_notebooks(self, workspace: str):
        """List all notebooks in a workspace."""
        # Accept workspace name or ID
        if not _is_valid_uuid(workspace):
            (_, workspace) = await self.client.resolve_workspace_name_and_id(workspace)
        notebooks = await self.client.get_notebooks(workspace)

        if not notebooks:
            return f"No notebooks found in workspace '{workspace}'."

        markdown = f"# Notebooks in workspace '{workspace}'\n\n"
        markdown += "| ID | Name |\n"
        markdown += "|-----|------|\n"

        for nb in notebooks:
            markdown += f"| {nb['id']} | {nb['displayName']} |\n"

        return markdown

    async def get_notebook(self, workspace: str, notebook_id: str) -> Dict[str, Any]:
        """Get a specific notebook by ID or name."""
        if not _is_valid_uuid(workspace):
            (_, workspace) = await self.client.resolve_workspace_name_and_id(workspace)

        # Allow passing notebook name; resolve to ID when needed
        resolved_notebook_id = notebook_id
        if not _is_valid_uuid(notebook_id):
            resolved_notebook_id = await self.client.resolve_item_id(
                item=notebook_id, type="Notebook", workspace=workspace
            )

        notebook = await self.client.get_notebook(workspace, str(resolved_notebook_id))

        if not notebook:
            return (
                f"No notebook found with ID '{notebook_id}' in workspace '{workspace}'."
            )

        return notebook

    async def create_notebook(
        self, workspace: str, notebook_name: str, content: str
    ) -> Dict[str, Any]:
        """Create a new notebook."""
        try:
            ws_name, workspace_id = await self.client.resolve_workspace_name_and_id(
                workspace
            )
            if not workspace_id:
                raise ValueError("Invalid workspace ID.")

            logger.info(
                f"Creating notebook '{notebook_name}' in workspace '{ws_name}' (ID: {workspace_id})."
            )

            try:
                response = await self.client.create_notebook(
                    workspace_id=workspace_id,
                    notebook_name=notebook_name,
                    ipynb_name=notebook_name,
                    content=content,
                )
            except Exception as e:
                error_msg = (
                    f"Failed to create notebook '{notebook_name}' in workspace '{ws_name}': {str(e)}"
                )
                logger.error(error_msg)
                return {"error": error_msg}

            # Check if response is None
            if response is None:
                logger.warning(f"Notebook creation returned None response. The notebook may have been created successfully.")
                # Try to fetch the notebook by name to confirm
                try:
                    notebooks = await self.client.get_notebooks(workspace_id)
                    for nb in notebooks:
                        if nb.get("displayName") == notebook_name:
                            logger.info(f"Found created notebook '{notebook_name}' with ID: {nb['id']}")
                            return nb
                except Exception as fetch_error:
                    logger.warning(f"Could not verify notebook creation: {fetch_error}")
                return {"error": "Notebook creation returned None response"}

            if isinstance(response, dict) and response.get("id"):
                logger.info(
                    f"Successfully created notebook '{notebook_name}' with ID: {response['id']}"
                )
                return response

            # LRO succeeded but response has no notebook ID - look it up by name
            logger.warning(f"Notebook creation returned unexpected response: {response}")
            try:
                notebooks = await self.client.get_notebooks(workspace_id)
                for nb in notebooks:
                    if nb.get("displayName") == notebook_name:
                        logger.info(f"Found created notebook '{notebook_name}' with ID: {nb['id']}")
                        return nb
            except Exception as fetch_error:
                logger.warning(f"Could not verify notebook creation: {fetch_error}")
            return {"message": "Notebook creation submitted", "response": response}

        except Exception as e:
            error_msg = f"Error creating notebook '{notebook_name}': {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}
