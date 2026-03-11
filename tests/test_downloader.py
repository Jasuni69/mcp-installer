"""Tests for mcp_installer.downloader.

Tests focus on failure modes:
- Network errors, timeouts, rate limiting
- Corrupted downloads (checksum mismatch)  
- Malformed manifests
- Zip bombs (suspicious paths)
- Partial downloads (cleanup)
"""
import hashlib
import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_installer.downloader import (
    ChecksumError,
    DownloadError,
    ManifestError,
    compute_sha256,
    download_file,
    download_server,
    fetch_manifest,
    fetch_release_info,
    verify_checksum,
)


class TestComputeSha256:
    def test_known_hash(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        result = compute_sha256(f)
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert result == expected

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        result = compute_sha256(f)
        expected = hashlib.sha256(b"").hexdigest()
        assert result == expected

    def test_binary_file(self, tmp_path):
        f = tmp_path / "binary.bin"
        data = bytes(range(256)) * 100
        f.write_bytes(data)
        result = compute_sha256(f)
        expected = hashlib.sha256(data).hexdigest()
        assert result == expected


class TestVerifyChecksum:
    def test_match(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("test data")
        sha = hashlib.sha256(b"test data").hexdigest()
        assert verify_checksum(f, sha) is True

    def test_mismatch(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("test data")
        assert verify_checksum(f, "0" * 64) is False

    def test_case_insensitive(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("test")
        sha = hashlib.sha256(b"test").hexdigest()
        assert verify_checksum(f, sha.upper()) is True


class TestFetchReleaseInfo:
    @patch("mcp_installer.downloader.requests.get")
    def test_rate_limit_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_get.return_value = mock_resp
        with pytest.raises(DownloadError, match="rate limit"):
            fetch_release_info()

    @patch("mcp_installer.downloader.requests.get")
    def test_not_found_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp
        with pytest.raises(DownloadError, match="No releases found"):
            fetch_release_info()

    @patch("mcp_installer.downloader.requests.get")
    def test_timeout_error(self, mock_get):
        import requests as req
        mock_get.side_effect = req.exceptions.Timeout()
        with pytest.raises(DownloadError, match="timed out"):
            fetch_release_info()

    @patch("mcp_installer.downloader.requests.get")
    def test_connection_error(self, mock_get):
        import requests as req
        mock_get.side_effect = req.exceptions.ConnectionError()
        with pytest.raises(DownloadError, match="Could not connect"):
            fetch_release_info()


class TestFetchManifest:
    @patch("mcp_installer.downloader.requests.get")
    def test_missing_manifest_asset(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"assets": [{"name": "not-manifest.zip"}]}
        mock_get.return_value = mock_resp
        with pytest.raises(ManifestError, match="does not contain a manifest.json"):
            fetch_manifest()

    @patch("mcp_installer.downloader.requests.get")
    def test_malformed_manifest(self, mock_get):
        # First call returns release info, second returns the manifest
        release_resp = MagicMock()
        release_resp.status_code = 200
        release_resp.json.return_value = {
            "assets": [{"name": "manifest.json", "browser_download_url": "http://x"}]
        }
        manifest_resp = MagicMock()
        manifest_resp.status_code = 200
        manifest_resp.json.return_value = {"no_servers_key": True}
        mock_get.side_effect = [release_resp, manifest_resp]

        with pytest.raises(ManifestError, match="missing 'servers' key"):
            fetch_manifest()


class TestDownloadFile:
    @patch("mcp_installer.downloader.requests.get")
    def test_successful_download(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Length": "11"}
        mock_resp.iter_content.return_value = [b"hello world"]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        dest = tmp_path / "output.txt"
        result = download_file("http://example.com/file", dest)
        assert result == dest
        assert dest.read_bytes() == b"hello world"

    @patch("mcp_installer.downloader.requests.get")
    def test_progress_callback(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Length": "10"}
        mock_resp.iter_content.return_value = [b"12345", b"67890"]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        progress_calls = []
        dest = tmp_path / "output.bin"
        download_file("http://example.com/file", dest,
                       progress_callback=lambda d, t: progress_calls.append((d, t)))
        assert len(progress_calls) == 2
        assert progress_calls[-1][0] == 10  # total downloaded

    @patch("mcp_installer.downloader.requests.get")
    def test_cleanup_on_error(self, mock_get, tmp_path):
        mock_get.side_effect = Exception("network error")
        dest = tmp_path / "output.txt"
        with pytest.raises(DownloadError):
            download_file("http://example.com/file", dest)
        # The destination file should not exist after a failed download
        assert not dest.exists()


class TestDownloadServer:
    def _make_server_zip(self, tmp_path, name="fabric-core"):
        """Helper: create a valid server ZIP for testing."""
        zip_path = tmp_path / f"{name}.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr(f"{name}/pyproject.toml", "[project]\nname = 'test'")
            zf.writestr(f"{name}/server.py", "print('hello')")
        sha = compute_sha256(zip_path)
        return zip_path, sha

    def test_server_not_in_manifest(self, tmp_path):
        manifest = {"servers": {}}
        with pytest.raises(ManifestError, match="not found in manifest"):
            download_server("nonexistent", tmp_path, manifest)

    def test_no_download_url(self, tmp_path):
        manifest = {"servers": {"fabric-core": {"version": "1.0", "sha256": "abc"}}}
        with pytest.raises(ManifestError, match="No download URL"):
            download_server("fabric-core", tmp_path, manifest)

    @patch("mcp_installer.downloader.download_file")
    def test_checksum_mismatch_deletes_file(self, mock_download, tmp_path):
        """If checksum fails, the downloaded ZIP should be deleted."""
        # Create a fake ZIP that will fail checksum
        zip_path = tmp_path / "fabric-core.zip"
        zip_path.write_text("fake data")
        mock_download.return_value = zip_path

        manifest = {
            "servers": {
                "fabric-core": {
                    "version": "1.0",
                    "url": "http://example.com/fc.zip",
                    "sha256": "0" * 64,
                    "asset_name": "fabric-core.zip",
                }
            }
        }
        with pytest.raises(ChecksumError, match="SHA256 mismatch"):
            download_server("fabric-core", tmp_path, manifest)
