from pydantic import BaseModel
from typing import Dict, Any, List, Optional, Tuple, Union
import base64
from urllib.parse import quote
from functools import lru_cache
import requests
from azure.identity import DefaultAzureCredential
from helpers.logging_config import get_logger
from helpers.utils import _is_valid_uuid
import json
from uuid import UUID

logger = get_logger(__name__)
# from  sempy_labs._helper_functions import create_item



class FabricApiConfig(BaseModel):
    """Configuration for Fabric API"""

    base_url: str = "https://api.fabric.microsoft.com/v1"
    max_results: int = 100


class FabricApiClient:
    """Client for communicating with the Fabric API"""

    def __init__(self, credential=None, config=None):
        self.credential = credential or DefaultAzureCredential()
        self.config = config or FabricApiConfig()
        # Initialize cached methods
        self._cached_resolve_workspace = lru_cache(maxsize=128)(self._resolve_workspace)
        self._cached_resolve_lakehouse = lru_cache(maxsize=128)(self._resolve_lakehouse)

    def _get_headers(self, token_scope: Optional[str] = None) -> Dict[str, str]:
        """Get headers for Fabric API calls"""
        scope = token_scope or "https://api.fabric.microsoft.com/.default"
        return {
            "Authorization": f"Bearer {self.credential.get_token(scope).token}"
        }

    def _build_url(
        self, endpoint: str, continuation_token: Optional[str] = None
    ) -> str:
        # If the endpoint starts with http, use it as-is.
        url = (
            endpoint
            if endpoint.startswith("http")
            else f"{self.config.base_url}/{endpoint.lstrip('/')}"
        )
        if continuation_token:
            separator = "&" if "?" in url else "?"
            encoded_token = quote(continuation_token)
            url += f"{separator}continuationToken={encoded_token}"
        return url

    async def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        method: str = "GET",
        use_pagination: bool = False,
        data_key: str = "value",
        lro: bool = False,
        lro_poll_interval: int = 2,  # seconds between polls
        lro_timeout: int = 300,  # max seconds to wait
        token_scope: Optional[str] = None,
        max_retries: int = 3,
        raw_mode: bool = False,
    ) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Make an asynchronous call to the Fabric API.

        If use_pagination is True, it will automatically handle paginated responses.

        If lro is True, will poll for long-running operation completion.

        Retries on 429 (Too Many Requests) and 503 (Service Unavailable) with exponential backoff.
        """
        import time

        params = params or {}

        if not use_pagination:
            url = self._build_url(endpoint=endpoint)
            response = None
            for attempt in range(max_retries + 1):
                try:
                    if method.upper() in ("POST", "PATCH"):
                        response = requests.request(
                            method=method.upper(),
                            url=url,
                            headers=self._get_headers(token_scope),
                            json=params,
                            timeout=120,
                        )
                    elif method.upper() == "DELETE":
                        response = requests.delete(
                            url,
                            headers=self._get_headers(token_scope),
                            timeout=120,
                        )
                    else:
                        query_params = params.copy()
                        if not raw_mode and "maxResults" not in query_params:
                            query_params["maxResults"] = self.config.max_results
                        response = requests.request(
                            method=method.upper(),
                            url=url,
                            headers=self._get_headers(token_scope),
                            params=query_params,
                            timeout=120,
                        )

                    # Retry on 429 and 503
                    if response.status_code in (429, 503) and attempt < max_retries:
                        retry_after = int(response.headers.get("Retry-After", 2 ** attempt))
                        logger.warning(
                            f"Got {response.status_code}, retrying in {retry_after}s (attempt {attempt + 1}/{max_retries})"
                        )
                        time.sleep(retry_after)
                        continue
                    break
                except requests.ConnectionError as conn_err:
                    if attempt < max_retries:
                        wait = 2 ** attempt
                        logger.warning(f"Connection error, retrying in {wait}s: {conn_err}")
                        time.sleep(wait)
                        continue
                    raise

            try:
    
                # LRO support: check for 202 and Operation-Location/Location
                if lro and response.status_code == 202:
                    # Fabric APIs use two headers:
                    # - Operation-Location: URL to poll for operation status
                    # - Location: URL to GET the actual result after operation completes
                    op_location = (
                        response.headers.get("Operation-Location")
                        or response.headers.get("operation-location")
                    )
                    location = (
                        response.headers.get("Location")
                        or response.headers.get("location")
                    )

                    # If both exist, poll op_location and fetch result from location
                    # If only location exists, use it for polling (legacy pattern)
                    op_url = op_location or location
                    result_url = location if op_location and location and op_location != location else None

                    if not op_url:
                        logger.error("LRO: No Operation-Location header found in 202 response.")
                        logger.error(f"LRO: Response headers: {dict(response.headers)}")
                        logger.error(f"LRO: Response body: {response.text[:500] if response.text else 'empty'}")
                        try:
                            body = response.json()
                            logger.info(f"LRO: Returning response body despite missing Operation-Location")
                            return body
                        except Exception:
                            return None
                    logger.info(f"LRO: Polling {op_url} for operation status...")
                    if result_url:
                        logger.info(f"LRO: Result will be fetched from {result_url}")
                    start_time = time.time()
                    while True:
                        # Respect Retry-After when provided
                        retry_after_header = response.headers.get("Retry-After") or response.headers.get("retry-after")
                        retry_after = None
                        try:
                            if retry_after_header is not None:
                                retry_after = int(retry_after_header)
                        except Exception:
                            retry_after = None
                        poll_resp = requests.get(
                            op_url, headers=self._get_headers(), timeout=60
                        )
                        if poll_resp.status_code not in (200, 201, 202):
                            logger.error(
                                f"LRO: Poll failed with status {poll_resp.status_code}"
                            )
                            return None
                        poll_data = poll_resp.json()
                        status = poll_data.get("status") or poll_data.get(
                            "operationStatus"
                        )

                        # If 200 response with no status field, the result IS the data
                        # (Location URL returns actual content when operation completes)
                        if poll_resp.status_code == 200 and status is None:
                            logger.info("LRO: Got 200 with no status field - treating as completed result.")
                            return poll_data

                        if status in (
                            "Succeeded",
                            "succeeded",
                            "Completed",
                            "completed",
                        ):
                            logger.info("LRO: Operation succeeded.")

                            # If we have a separate result URL, fetch the actual result
                            if result_url:
                                logger.info(f"LRO: Fetching result from {result_url}")
                                try:
                                    result_resp = requests.get(
                                        result_url, headers=self._get_headers(token_scope), timeout=120
                                    )
                                    if result_resp.status_code == 200 and result_resp.text:
                                        return result_resp.json()
                                    logger.warning(f"LRO: Result fetch returned {result_resp.status_code}")
                                except Exception as result_exc:
                                    logger.warning(f"LRO: Failed to fetch result: {result_exc}")

                            # Extract resource details from the polling response
                            resource = (
                                poll_data.get("resource")
                                or poll_data.get("result")
                                or poll_data.get("item")
                            )
                            if resource and isinstance(resource, dict):
                                return resource
                            return poll_data
                        if status in ("Failed", "failed", "Canceled", "canceled"):
                            logger.error(
                                f"LRO: Operation failed or canceled. Status: {status}"
                            )
                            return poll_data
                        if time.time() - start_time > lro_timeout:
                            logger.error("LRO: Polling timed out.")
                            return None
                        wait_time = retry_after if retry_after is not None else lro_poll_interval
                        logger.debug(
                            f"LRO: Status {status}, waiting {wait_time}s..."
                        )
                        time.sleep(wait_time)
                response.raise_for_status()

                # Handle empty response body (common for DELETE 204, PATCH 200)
                if response.status_code == 204 or not response.text or response.text.strip() == "":
                    if method.upper() == "DELETE":
                        return {"success": True, "status": response.status_code}
                    return {}
                
                try:
                    return response.json()
                except ValueError as e:
                    logger.error(f"Failed to parse JSON response: {e}")
                    logger.error(f"Response text: {response.text[:500]}")
                    return None
            except requests.RequestException as e:
                logger.error(f"API call failed: {str(e)}")
                error_msg = f"API call failed: {str(e)}"
                if e.response is not None:
                    logger.error(f"Response status: {e.response.status_code}")
                    logger.error(f"Response content: {e.response.text}")
                    error_msg += f"\nStatus: {e.response.status_code}\nResponse: {e.response.text}"
                raise ValueError(error_msg)
        else:
            results = []
            continuation_token = None
            while True:
                url = self._build_url(
                    endpoint=endpoint, continuation_token=continuation_token
                )
                request_params = params.copy()
                # Remove any existing continuationToken in parameters to avoid conflict.
                request_params.pop("continuationToken", None)
                try:
                    if method.upper() == "POST":
                        response = requests.post(
                            url,
                            headers=self._get_headers(),
                            json=request_params,
                            timeout=120,
                        )
                    else:
                        if not raw_mode and "maxResults" not in request_params:
                            request_params["maxResults"] = self.config.max_results
                        response = requests.request(
                            method=method.upper(),
                            url=url,
                            headers=self._get_headers(),
                            params=request_params,
                            timeout=120,
                        )
                    response.raise_for_status()
                    data = response.json()
                except requests.RequestException as e:
                    logger.error(f"API call failed: {str(e)}")
                    if e.response is not None:
                        logger.error(f"Response content: {e.response.text}")
                    return results if results else None

                if not isinstance(data, dict) or data_key not in data:
                    raise ValueError(f"Unexpected response format: {data}")

                results.extend(data[data_key])
                continuation_token = data.get("continuationToken")
                if not continuation_token:
                    break
            return results

    async def get_workspaces(self) -> List[Dict]:
        """Get all available workspaces"""
        return await self._make_request("workspaces", use_pagination=True)

    async def create_workspace(
        self,
        display_name: str,
        capacity_id: Optional[str] = None,
        description: Optional[str] = None,
        domain_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new workspace via POST /v1/workspaces"""
        if not display_name:
            raise ValueError("Workspace display name cannot be empty.")

        payload: Dict[str, Any] = {
            "displayName": display_name,
        }
        if capacity_id:
            payload["capacityId"] = capacity_id
        if description:
            payload["description"] = description
        if domain_id:
            payload["domainId"] = domain_id

        return await self._make_request(
            endpoint="workspaces",
            method="post",
            params=payload,
            lro=True,
            lro_poll_interval=1,
        )

    async def get_lakehouses(self, workspace_id: str) -> List[Dict]:
        """Get all lakehouses in a workspace"""
        return await self.get_items(workspace_id=workspace_id, item_type="Lakehouse")

    async def get_warehouses(self, workspace_id: str) -> List[Dict]:
        """Get all warehouses in a workspace
        Args:
            workspace_id: ID of the workspace
        Returns:
            A list of dictionaries containing warehouse details or an error message.
        """
        return await self.get_items(workspace_id=workspace_id, item_type="Warehouse")

    async def get_tables(self, workspace_id: str, rsc_id: str, type: str) -> List[Dict]:
        """Get all tables in a lakehouse
        Args:
            workspace_id: ID of the workspace
            rsc_id: ID of the lakehouse
            type: Type of the resource (e.g., "Lakehouse" or "Warehouse")
        Returns:
            A list of dictionaries containing table details or an error message.
        """
        return await self._make_request(
            f"workspaces/{workspace_id}/{type}s/{rsc_id}/tables",
            use_pagination=True,
            data_key="data",
        )

    async def get_reports(self, workspace_id: str) -> List[Dict]:
        """Get all reports in a lakehouse
        Args:
            workspace_id: ID of the workspace
        Returns:
            A list of dictionaries containing report details or an error message.
        """
        return await self._make_request(
            f"workspaces/{workspace_id}/reports",
            use_pagination=True,
            data_key="value",
        )

    async def get_report(self, workspace_id: str, report_id: str) -> Dict:
        """Get a specific report by ID

        Args:
            workspace_id: ID of the workspace
            report_id: ID of the report

        Returns:
            A dictionary containing the report details or an error message.
        """
        return await self._make_request(
            f"workspaces/{workspace_id}/reports/{report_id}"
        )

    async def get_semantic_models(self, workspace_id: str) -> List[Dict]:
        """Get all semantic models in a lakehouse"""
        return await self._make_request(
            f"workspaces/{workspace_id}/semanticModels",
            use_pagination=True,
            data_key="value",
        )

    async def get_semantic_model(self, workspace_id: str, model_id: str) -> Dict:
        """Get a specific semantic model by ID"""
        return await self._make_request(
            f"workspaces/{workspace_id}/semanticModels/{model_id}"
        )

    async def resolve_workspace(self, workspace: str) -> str:
        """Convert workspace name or ID to workspace ID with caching"""
        return await self._cached_resolve_workspace(workspace)

    async def _resolve_workspace(self, workspace: str) -> str:
        """Internal method to convert workspace name or ID to workspace ID"""
        if _is_valid_uuid(workspace):
            return workspace

        workspaces = await self.get_workspaces()
        matching_workspaces = [
            w for w in workspaces if w["displayName"].lower() == workspace.lower()
        ]

        if not matching_workspaces:
            raise ValueError(f"No workspaces found with name: {workspace}")
        if len(matching_workspaces) > 1:
            raise ValueError(f"Multiple workspaces found with name: {workspace}")

        return matching_workspaces[0]["id"]

    async def resolve_lakehouse(self, workspace_id: str, lakehouse: str) -> str:
        """Convert lakehouse name or ID to lakehouse ID with caching"""
        return await self._cached_resolve_lakehouse(workspace_id, lakehouse)

    async def _resolve_lakehouse(self, workspace_id: str, lakehouse: str) -> str:
        """Internal method to convert lakehouse name or ID to lakehouse ID"""
        if _is_valid_uuid(lakehouse):
            return lakehouse

        lakehouses = await self.get_lakehouses(workspace_id)
        matching_lakehouses = [
            lh for lh in lakehouses if lh["displayName"].lower() == lakehouse.lower()
        ]

        if not matching_lakehouses:
            raise ValueError(f"No lakehouse found with name: {lakehouse}")
        if len(matching_lakehouses) > 1:
            raise ValueError(f"Multiple lakehouses found with name: {lakehouse}")

        return matching_lakehouses[0]["id"]

    async def get_items(
        self,
        workspace_id: str,
        item_type: Optional[str] = None,
        params: Optional[Dict] = None,
    ) -> List[Dict]:
        """Get all items in a workspace"""
        if not _is_valid_uuid(workspace_id):
            raise ValueError("Invalid workspace ID.")
        if item_type:
            params = params or {}
            params["type"] = item_type
        return await self._make_request(
            f"workspaces/{workspace_id}/items", params=params, use_pagination=True
        )

    async def get_item(
        self,
        item_id: str,
        workspace_id: str,
        item_type: Optional[str] = None,
    ) -> Dict:
        """Get a specific item by ID"""

        if not _is_valid_uuid(item_id):
            item_name, item_id = await self.resolve_item_name_and_id(item_id)
        if not _is_valid_uuid(workspace_id):
            (workspace_name, workspace_id) = await self.resolve_workspace_name_and_id(
                workspace_id
            )
        return await self._make_request(
            f"workspaces/{workspace_id}/{item_type}s/{item_id}"
        )

    async def get_item_permissions(
        self,
        workspace_id: str,
        item_id: str,
    ) -> Dict[str, Any]:
        """Retrieve permissions for a given workspace item."""
        if not _is_valid_uuid(workspace_id):
            raise ValueError("Invalid workspace ID.")
        if not _is_valid_uuid(item_id):
            raise ValueError("Invalid item ID.")

        return await self._make_request(
            f"workspaces/{workspace_id}/items/{item_id}/permissions"
        )

    async def set_item_permissions(
        self,
        workspace_id: str,
        item_id: str,
        assignments: List[Dict[str, Any]],
        principal_scope: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Set permissions for a workspace item."""

        if not _is_valid_uuid(workspace_id):
            raise ValueError("Invalid workspace ID.")
        if not _is_valid_uuid(item_id):
            raise ValueError("Invalid item ID.")
        if not assignments:
            raise ValueError("At least one assignment must be provided.")

        payload: Dict[str, Any] = {"value": assignments}
        if principal_scope:
            payload["scope"] = principal_scope

        return await self._make_request(
            f"workspaces/{workspace_id}/items/{item_id}/permissions",
            params=payload,
            method="post",
        )

    async def create_item(
        self,
        name: str,
        type: str,
        description: Optional[str] = None,
        definition: Optional[dict] = None,
        workspace: Optional[str | UUID] = None,
        lro: Optional[bool] = False,
        folder_id: Optional[str] = None,
        creation_payload: Optional[dict] = None,
    ):
        """
        Creates an item in a Fabric workspace.

        Parameters
        ----------
        name : str
            The name of the item to be created.
        type : str
            The type of the item to be created.
        description : str, default=None
            A description of the item to be created.
        definition : dict, default=None
            The definition of the item to be created.
        workspace : str | uuid.UUID, default=None
            The Fabric workspace name or ID.
            Defaults to None which resolves to the workspace of the attached lakehouse
            or if no lakehouse attached, resolves to the workspace of the notebook.
        """
        if _is_valid_uuid(workspace):
            workspace_id = workspace
        else:
            (workspace_name, workspace_id) = await self.resolve_workspace_name_and_id(
                workspace
            )

        # Map item type to API path name
        # Try sempy_labs mapping first, fall back to simple pluralization
        item_type = None
        try:
            from sempy_labs._utils import item_types
            item_type_mapping = item_types.get(type)
            if item_type_mapping:
                item_type = item_type_mapping[0].lower()
        except (ImportError, AttributeError):
            logger.warning("sempy_labs._utils.item_types not available, using fallback")

        if not item_type:
            # Fallback: lowercase the type name
            item_type = type.lower()

        payload = {
            "displayName": name,
        }
        if description:
            payload["description"] = description
        if definition:
            payload["definition"] = definition
        if folder_id:
            payload["folderId"] = folder_id
        if creation_payload:
            payload["creationPayload"] = creation_payload

        try:
            response = await self._make_request(
                endpoint=f"workspaces/{workspace_id}/{item_type}s",
                method="post",
                params=payload,
                lro=lro,
                lro_poll_interval=0.5,
            )
        except requests.RequestException as e:
            logger.error(f"API call failed: {str(e)}")
            if e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            raise ValueError(
                f"Failed to create item '{name}' of type '{item_type}' in the '{workspace_id}' workspace."
            )        
        
        # Check if response is None
        if response is None:
            logger.error(f"Received None response when creating item '{name}'")
            raise ValueError(f"Failed to create item '{name}': API returned None response")
        
        # Check if response contains an error
        if isinstance(response, dict):
            if "error" in response and response["error"]:
                error_value = response["error"]
                if isinstance(error_value, dict):
                    error_msg = error_value.get("message", "Unknown error")
                else:
                    error_msg = str(error_value)
                logger.error(f"API error creating item: {error_msg}")
                raise ValueError(f"Failed to create item '{name}': {error_msg}")
            
            # Check if item was created successfully
            if "id" in response:
                logger.info(f"Successfully created item '{name}' with ID: {response['id']}")
                return response
            
            # If response is empty dict or LRO status, fetch the item by name
            if lro and (len(response) == 0 or response.get("status") in ("Succeeded", "succeeded", "Completed", "completed")):
                logger.info(f"LRO completed but no item details in response. Fetching item '{name}' by name...")
                try:
                    # Wait a moment for the item to be available - use async sleep
                    import asyncio
                    await asyncio.sleep(3)  # Increased wait time to 3 seconds
                    
                    # Fetch the item by name
                    items = await self.get_items(workspace_id=workspace_id, item_type=type)
                    if not items:
                        logger.warning(f"get_items returned None/empty for workspace {workspace_id}, type {type}")
                    elif not isinstance(items, list):
                        logger.warning(f"get_items returned unexpected type: {type(items).__name__}")
                    else:
                        for item in items:
                            if not isinstance(item, dict):
                                logger.warning(f"Skipping non-dict item: {type(item).__name__}")
                                continue
                            if item.get("displayName") == name:
                                logger.info(f"Found created item '{name}' with ID: {item['id']}")
                                return item
                        
                        logger.warning(f"Could not find item '{name}' after LRO completion")
                        logger.warning(f"Available items: {[item.get('displayName') for item in items[:10] if isinstance(item, dict)]}")
                    
                    # If we couldn't find the item, still return a success response
                    # The item was created (LRO succeeded), it just may not be immediately queryable
                    logger.info(f"LRO succeeded for item '{name}'. Returning success response.")
                    return {
                        "displayName": name,
                        "status": "Created",
                        "note": "Item created successfully. It may take a moment to appear in listings."
                    }
                    
                except Exception as fetch_error:
                    logger.warning(f"Failed to fetch item after LRO: {fetch_error}")
                    # Even if fetching fails, the LRO succeeded, so return success
                    return {
                        "displayName": name,
                        "status": "Created",
                        "note": "Item created successfully. Verification failed but creation completed.",
                        "fetch_error": str(fetch_error)
                    }
            
            # If no ID and no error, log the full response for debugging
            logger.warning(f"Unexpected response format: {response}")
        
        # Legacy check - may not be reliable for all item types
        if hasattr(response, 'get') and response.get("displayName") and response.get("displayName") != name:
            logger.warning(f"Response displayName '{response.get('displayName')}' doesn't match requested name '{name}', but this may be normal")
        
        return response

    async def update_item(
        self,
        workspace_id: str,
        item_id: str,
        item_type: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update an item's metadata (rename, update description) via PATCH."""
        if not _is_valid_uuid(workspace_id):
            raise ValueError("Invalid workspace ID.")
        if not _is_valid_uuid(item_id):
            raise ValueError("Invalid item ID.")

        payload: Dict[str, Any] = {}
        if display_name is not None:
            payload["displayName"] = display_name
        if description is not None:
            payload["description"] = description

        if not payload:
            raise ValueError("At least one of display_name or description must be provided.")

        # Map item type to plural API path
        type_lower = item_type.lower()
        endpoint = f"workspaces/{workspace_id}/{type_lower}s/{item_id}"

        return await self._make_request(
            endpoint=endpoint,
            method="PATCH",
            params=payload,
        )

    async def delete_item(
        self,
        workspace_id: str,
        item_id: str,
        item_type: str,
    ) -> Dict[str, Any]:
        """Delete an item via DELETE."""
        if not _is_valid_uuid(workspace_id):
            raise ValueError("Invalid workspace ID.")
        if not _is_valid_uuid(item_id):
            raise ValueError("Invalid item ID.")

        type_lower = item_type.lower()
        endpoint = f"workspaces/{workspace_id}/{type_lower}s/{item_id}"

        return await self._make_request(
            endpoint=endpoint,
            method="DELETE",
        )

    async def resolve_item_name_and_id(
        self,
        item: str | UUID,
        type: Optional[str] = None,
        workspace: Optional[str | UUID] = None,
    ) -> Tuple[str, UUID]:
        (workspace_name, workspace_id) = await self.resolve_workspace_name_and_id(
            workspace
        )
        item_id = await self.resolve_item_id(
            item=item, type=type, workspace=workspace_id
        )
        item_data = await self._make_request(
            f"workspaces/{workspace_id}/items/{item_id}"
        )
        item_name = item_data.get("displayName")
        return item_name, item_id

    async def resolve_item_id(
        self,
        item: str | UUID,
        type: Optional[str] = None,
        workspace: Optional[str | UUID] = None,
    ) -> UUID:
        (workspace_name, workspace_id) = await self.resolve_workspace_name_and_id(
            workspace
        )
        item_id = None

        if _is_valid_uuid(item):
            # Check (optional)
            item_id = item
            try:
                await self._make_request(
                    endpoint=f"workspaces/{workspace_id}/items/{item_id}"
                )
            except requests.RequestException:
                raise ValueError(
                    f"The '{item_id}' item was not found in the '{workspace_name}' workspace."
                )
        else:
            if type is None:
                raise ValueError(
                    "The 'type' parameter is required if specifying an item name."
                )
            responses = await self._make_request(
                endpoint=f"workspaces/{workspace_id}/items?type={type}",
                use_pagination=True,
            )
            for v in responses:
                display_name = v["displayName"]
                if display_name == item:
                    item_id = v.get("id")
                    break

        if item_id is None:
            raise ValueError(
                f"There's no item '{item}' of type '{type}' in the '{workspace_name}' workspace."
            )

        return item_id

    async def resolve_workspace_name_and_id(
        self,
        workspace: Optional[str | UUID] = None,
    ) -> Tuple[str, UUID]:
        """
        Obtains the name and ID of the Fabric workspace.

        Parameters
        ----------
        workspace : str | uuid.UUID, default=None
            The Fabric workspace name or ID.
            Defaults to None which resolves to the workspace of the attached lakehouse
            or if no lakehouse attached, resolves to the workspace of the notebook.

        Returns
        -------
        str, uuid.UUID
            The name and ID of the Fabric workspace.
        """
        logger.debug(f"Resolving workspace name and ID for: {workspace}")
        if workspace is None:
            raise ValueError("Workspace must be specified.")
        elif _is_valid_uuid(workspace):
            workspace_id = workspace
            workspace_name = await self.resolve_workspace_name(workspace_id)
            return workspace_name, workspace_id
        else:
            responses = await self._make_request(
                endpoint="workspaces", use_pagination=True
            )
            if not responses:
                raise ValueError(f"Failed to list workspaces - API returned None/empty")
            if not isinstance(responses, list):
                raise ValueError(f"Failed to list workspaces - API returned unexpected type: {type(responses).__name__}")
            
            workspace_id = None
            workspace_name = None
            for r in responses:
                if not isinstance(r, dict):
                    logger.warning(f"Skipping non-dict workspace entry: {type(r).__name__}")
                    continue
                display_name = r.get("displayName")
                if display_name == workspace:
                    workspace_name = workspace
                    workspace_id = r.get("id")
                    return workspace_name, workspace_id

        if workspace_name is None or workspace_id is None:
            raise ValueError(f"Workspace '{workspace}' not found in available workspaces")

        return workspace_name, workspace_id

    async def resolve_workspace_name(self, workspace_id: Optional[UUID] = None) -> str:
        try:
            response = await self._make_request(endpoint=f"workspaces/{workspace_id}")
            if not response:
                raise ValueError(f"Workspace '{workspace_id}' not found - API returned None/empty response")
            if not isinstance(response, dict):
                raise ValueError(f"Workspace '{workspace_id}' API returned unexpected type: {type(response).__name__}")
            if "displayName" not in response:
                raise ValueError(f"Workspace '{workspace_id}' not found or API response invalid: {response}")
            return response.get("displayName")
        except requests.RequestException as e:
            raise ValueError(f"The '{workspace_id}' workspace was not found: {str(e)}")

    async def get_notebooks(self, workspace_id: str) -> List[Dict]:
        """Get all notebooks in a workspace"""
        return await self.get_items(workspace_id=workspace_id, item_type="Notebook")

    async def get_notebook(self, workspace_id: str, notebook_id: str) -> Dict:
        """Get a specific notebook by ID"""
        return await self.get_item(
            item_id=notebook_id, workspace_id=workspace_id, item_type="notebook"
        )

    async def create_notebook(
        self, workspace_id: str, notebook_name: str, ipynb_name: str, content: str
    ) -> Dict:
        """Create a new notebook."""
        if not _is_valid_uuid(workspace_id):
            raise ValueError("Invalid workspace ID.")

        # Define the notebook definition
        logger.debug(
            f"Defining notebook '{notebook_name}' in workspace '{workspace_id}'."
        )
        definition = {
            "format": "ipynb",
            "parts": [
                {
                    "path": f"{ipynb_name}.ipynb",
                    "payload": base64.b64encode(
                        content
                        if isinstance(content, bytes)
                        else content.encode("utf-8")
                    ).decode("utf-8"),
                    "payloadType": "InlineBase64",
                },
                # {
                #     "path": ".platform",
                #     "payload": base64.b64encode("dotPlatformBase64String".encode("utf-8")).decode("utf-8"),
                #     "payloadType": "InlineBase64",
                # },
            ],
        }
        logger.info(
            f"-------Creating notebook '{notebook_name}' in workspace '{workspace_id}'."
        )
        return await self.create_item(
            workspace=workspace_id,
            type="Notebook",
            name=notebook_name,
            definition=definition,
            lro=True,
        )

    async def create_shortcut(
        self,
        workspace_id: str,
        item_id: str,
        shortcut_name: str,
        shortcut_path: str,
        target_workspace_id: str,
        target_item_id: str,
        target_path: str,
        conflict_policy: str = "CreateOrOverwrite",
    ) -> Dict[str, Any]:
        """
        Create a OneLake shortcut from one lakehouse/warehouse to another.

        Args:
            workspace_id: Source workspace ID
            item_id: Source lakehouse/warehouse ID
            shortcut_name: Name for the shortcut
            shortcut_path: Path in source where shortcut appears (e.g., "Tables", "Files/subfolder")
            target_workspace_id: Target workspace ID containing the data
            target_item_id: Target lakehouse/warehouse ID with the data
            target_path: Path in target to link to (e.g., "Tables/customers_raw")
            conflict_policy: Action when shortcut exists (Abort, GenerateUniqueName, CreateOrOverwrite, OverwriteOnly)

        Returns:
            Dictionary with shortcut details
        """
        if not _is_valid_uuid(workspace_id):
            raise ValueError("Invalid workspace ID.")
        if not _is_valid_uuid(item_id):
            raise ValueError("Invalid item ID.")
        if not _is_valid_uuid(target_workspace_id):
            raise ValueError("Invalid target workspace ID.")
        if not _is_valid_uuid(target_item_id):
            raise ValueError("Invalid target item ID.")

        payload = {
            "name": shortcut_name,
            "path": shortcut_path,
            "target": {
                "oneLake": {
                    "workspaceId": target_workspace_id,
                    "itemId": target_item_id,
                    "path": target_path,
                }
            },
        }

        endpoint = f"workspaces/{workspace_id}/items/{item_id}/shortcuts?shortcutConflictPolicy={conflict_policy}"

        try:
            response = await self._make_request(
                endpoint=endpoint,
                method="POST",
                params=payload,
            )
            logger.info(f"Created shortcut '{shortcut_name}' in {shortcut_path}")
            return response
        except requests.RequestException as e:
            logger.error(f"Failed to create shortcut: {str(e)}")
            if e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            raise ValueError(f"Failed to create shortcut '{shortcut_name}': {str(e)}")

    async def list_shortcuts(
        self,
        workspace_id: str,
        item_id: str,
    ) -> List[Dict[str, Any]]:
        """
        List all shortcuts in a lakehouse/warehouse.

        Args:
            workspace_id: Workspace ID
            item_id: Lakehouse/warehouse ID

        Returns:
            List of shortcuts
        """
        if not _is_valid_uuid(workspace_id):
            raise ValueError("Invalid workspace ID.")
        if not _is_valid_uuid(item_id):
            raise ValueError("Invalid item ID.")

        endpoint = f"workspaces/{workspace_id}/items/{item_id}/shortcuts"

        try:
            response = await self._make_request(
                endpoint=endpoint,
                method="GET",
                use_pagination=True,
            )
            return response if response else []
        except requests.RequestException as e:
            logger.error(f"Failed to list shortcuts: {str(e)}")
            return []

    async def delete_shortcut(
        self,
        workspace_id: str,
        item_id: str,
        shortcut_path: str,
        shortcut_name: str,
    ) -> Dict[str, Any]:
        """
        Delete a OneLake shortcut.

        Args:
            workspace_id: Workspace ID
            item_id: Lakehouse/warehouse ID
            shortcut_path: Path where shortcut exists
            shortcut_name: Name of the shortcut

        Returns:
            Success status
        """
        if not _is_valid_uuid(workspace_id):
            raise ValueError("Invalid workspace ID.")
        if not _is_valid_uuid(item_id):
            raise ValueError("Invalid item ID.")

        # URL encode the path and name
        from urllib.parse import quote
        encoded_path = quote(shortcut_path, safe='')
        encoded_name = quote(shortcut_name, safe='')

        endpoint = f"workspaces/{workspace_id}/items/{item_id}/shortcuts/{encoded_path}/{encoded_name}"

        try:
            response = await self._make_request(
                endpoint=endpoint,
                method="DELETE",
            )
            logger.info(f"Deleted shortcut '{shortcut_name}' from {shortcut_path}")
            return {"success": True, "message": f"Shortcut '{shortcut_name}' deleted successfully"}
        except requests.RequestException as e:
            logger.error(f"Failed to delete shortcut: {str(e)}")
            if e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            raise ValueError(f"Failed to delete shortcut '{shortcut_name}': {str(e)}")

    async def create_pipeline(
        self,
        workspace_id: str,
        pipeline_name: str,
        pipeline_definition: Dict[str, Any],
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a Data Pipeline in a Fabric workspace.

        Args:
            workspace_id: Workspace ID
            pipeline_name: Name for the pipeline
            pipeline_definition: Pipeline JSON definition with activities and dependencies
            description: Optional description for the pipeline

        Returns:
            Dictionary with pipeline details including ID and status

        Example pipeline_definition:
        {
            "properties": {
                "activities": [
                    {
                        "name": "Bronze_Ingestion",
                        "type": "Notebook",
                        "typeProperties": {
                            "notebook": {"name": "bronze_ingest_notebook"}
                        },
                        "dependsOn": []
                    },
                    {
                        "name": "Silver_Transform",
                        "type": "Notebook",
                        "typeProperties": {
                            "notebook": {"name": "silver_transform_notebook"}
                        },
                        "dependsOn": [
                            {
                                "activity": "Bronze_Ingestion",
                                "dependencyConditions": ["Succeeded"]
                            }
                        ]
                    }
                ]
            }
        }
        """
        if not _is_valid_uuid(workspace_id):
            raise ValueError("Invalid workspace ID.")

        # Encode pipeline definition to base64
        definition_json = json.dumps(pipeline_definition)
        definition_base64 = base64.b64encode(definition_json.encode("utf-8")).decode("utf-8")

        payload = {
            "displayName": pipeline_name,
            "definition": {
                "parts": [
                    {
                        "path": "pipeline-content.json",
                        "payload": definition_base64,
                        "payloadType": "InlineBase64"
                    }
                ]
            }
        }

        if description:
            payload["description"] = description

        endpoint = f"workspaces/{workspace_id}/dataPipelines"

        try:
            response = await self._make_request(
                endpoint=endpoint,
                method="POST",
                params=payload,
                lro=True,
                lro_poll_interval=2,
            )
            logger.info(f"Created pipeline '{pipeline_name}' in workspace '{workspace_id}'")
            return response
        except requests.RequestException as e:
            logger.error(f"Failed to create pipeline: {str(e)}")
            if e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            raise ValueError(f"Failed to create pipeline '{pipeline_name}': {str(e)}")

    async def get_pipeline_definition(
        self,
        workspace_id: str,
        pipeline_id: str,
    ) -> Dict[str, Any]:
        """
        Get the definition of an existing Data Pipeline.

        Args:
            workspace_id: Workspace ID
            pipeline_id: Pipeline ID

        Returns:
            Dictionary with pipeline definition including activities and dependencies
        """
        if not _is_valid_uuid(workspace_id):
            raise ValueError("Invalid workspace ID.")
        if not _is_valid_uuid(pipeline_id):
            raise ValueError("Invalid pipeline ID.")

        endpoint = f"workspaces/{workspace_id}/dataPipelines/{pipeline_id}/getDefinition"

        try:
            response = await self._make_request(
                endpoint=endpoint,
                method="POST",
                lro=True,
            )

            # The definition might be base64 encoded in parts
            if response and "definition" in response:
                definition = response["definition"]
                if "parts" in definition:
                    for part in definition["parts"]:
                        if part.get("payloadType") == "InlineBase64":
                            # Decode the base64 payload
                            decoded = base64.b64decode(part["payload"]).decode("utf-8")
                            part["payloadDecoded"] = json.loads(decoded)

            logger.info(f"Retrieved pipeline definition for '{pipeline_id}'")
            return response
        except requests.RequestException as e:
            logger.error(f"Failed to get pipeline definition: {str(e)}")
            if e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            raise ValueError(f"Failed to get pipeline definition for '{pipeline_id}': {str(e)}")
