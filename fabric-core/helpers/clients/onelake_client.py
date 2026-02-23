import asyncio
import base64
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

from azure.core.exceptions import ResourceNotFoundError, ResourceExistsError
from azure.storage.filedatalake import DataLakeServiceClient

from helpers.logging_config import get_logger


logger = get_logger(__name__)


@dataclass
class OneLakePath:
    workspace_id: str
    lakehouse_id: str
    relative_path: str


class OneLakeClient:
    """Thin wrapper around Azure Data Lake Storage Gen2 client for OneLake."""

    ACCOUNT_URL = "https://onelake.dfs.fabric.microsoft.com"

    def __init__(self, credential):
        self.credential = credential
        self._service_client = DataLakeServiceClient(
            account_url=self.ACCOUNT_URL,
            credential=credential,
        )

    def _normalize_guid(self, value: str) -> str:
        return str(value).lower()

    def _parse_path(
        self,
        workspace_id: str,
        lakehouse_id: str,
        path: Optional[str] = None,
    ) -> Tuple[OneLakePath, str]:
        workspace_guid = self._normalize_guid(workspace_id)
        lakehouse_guid = self._normalize_guid(lakehouse_id)
        normalized_path = (path or "").strip("/")

        if normalized_path.startswith("Files/") or normalized_path.startswith("Tables/"):
            full_path = f"{lakehouse_guid}/{normalized_path}"
        elif normalized_path:
            full_path = f"{lakehouse_guid}/Files/{normalized_path}"
        else:
            full_path = f"{lakehouse_guid}/Files"

        return (
            OneLakePath(
                workspace_id=workspace_guid,
                lakehouse_id=lakehouse_guid,
                relative_path=normalized_path,
            ),
            full_path.strip("/"),
        )

    def _get_file_system_client(self, workspace_id: str):
        return self._service_client.get_file_system_client(
            file_system=self._normalize_guid(workspace_id)
        )

    async def list_directory(
        self,
        workspace_id: str,
        lakehouse_id: str,
        path: Optional[str] = None,
    ) -> List[Dict[str, Optional[str]]]:
        def _inner():
            onelake_path, full_path = self._parse_path(workspace_id, lakehouse_id, path)
            fs_client = self._get_file_system_client(onelake_path.workspace_id)

            prefix = full_path.rstrip("/")
            logger.debug("Listing OneLake path %s", prefix)

            try:
                paths_iter = fs_client.get_paths(path=prefix, recursive=False)
            except ResourceNotFoundError:
                raise FileNotFoundError(
                    f"Directory '{prefix}' not found in lakehouse '{lakehouse_id}'."
                )

            entries: List[Dict[str, Optional[str]]] = []
            for entry in paths_iter:
                name = entry.name
                relative_name = name[len(f"{onelake_path.lakehouse_id}/") :]
                entries.append(
                    {
                        "name": relative_name,
                        "is_directory": getattr(entry, "is_directory", False),
                        "size": getattr(entry, "content_length", None),
                        "last_modified": getattr(entry, "last_modified", None),
                    }
                )

            return entries

        return await asyncio.to_thread(_inner)

    async def read_file(
        self,
        workspace_id: str,
        lakehouse_id: str,
        path: str,
    ) -> Dict[str, str]:
        def _inner():
            onelake_path, full_path = self._parse_path(workspace_id, lakehouse_id, path)
            fs_client = self._get_file_system_client(onelake_path.workspace_id)
            file_client = fs_client.get_file_client(full_path)

            if not file_client.exists():
                raise FileNotFoundError(
                    f"File '{onelake_path.relative_path or path}' not found."
                )

            downloader = file_client.download_file()
            data = downloader.readall()

            try:
                content = data.decode("utf-8")
                encoding = "utf-8"
            except UnicodeDecodeError:
                content = base64.b64encode(data).decode("utf-8")
                encoding = "base64"

            return {
                "path": path,
                "content": content,
                "encoding": encoding,
            }

        return await asyncio.to_thread(_inner)

    async def write_file(
        self,
        workspace_id: str,
        lakehouse_id: str,
        path: str,
        data: bytes,
        overwrite: bool = True,
    ) -> Dict[str, str]:
        def _inner():
            onelake_path, full_path = self._parse_path(workspace_id, lakehouse_id, path)
            fs_client = self._get_file_system_client(onelake_path.workspace_id)

            directory_path = full_path.rsplit("/", 1)[0]
            directory_client = fs_client.get_directory_client(directory_path)
            try:
                directory_client.create_directory()
            except ResourceExistsError:
                pass
            except ResourceNotFoundError:
                raise FileNotFoundError(
                    f"Directory '{directory_path}' could not be created."
                )

            file_client = fs_client.get_file_client(full_path)
            file_client.upload_data(data, overwrite=overwrite)

            return {
                "path": path,
                "bytes_written": str(len(data)),
                "overwrite": str(overwrite),
            }

        return await asyncio.to_thread(_inner)

    async def delete_path(
        self,
        workspace_id: str,
        lakehouse_id: str,
        path: str,
        recursive: bool = False,
    ) -> Dict[str, str]:
        def _inner():
            onelake_path, full_path = self._parse_path(workspace_id, lakehouse_id, path)
            fs_client = self._get_file_system_client(onelake_path.workspace_id)

            file_client = fs_client.get_file_client(full_path)
            if file_client.exists():
                file_client.delete_file()
                return {"deleted": path, "type": "file"}

            directory_client = fs_client.get_directory_client(full_path)
            if directory_client.exists():
                directory_client.delete_directory(recursive=recursive)
                return {"deleted": path, "type": "directory"}

            raise FileNotFoundError(f"Path '{path}' not found in lakehouse.")

        return await asyncio.to_thread(_inner)

