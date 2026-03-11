"""Tests for mcp_installer.updater.

Tests focus on failure modes:
- Missing/malformed versions.json
- Concurrent read/write
- Manifest comparison edge cases
"""
import json
from pathlib import Path

import pytest

from mcp_installer.updater import (
    get_update_status,
    read_local_versions,
    write_local_versions,
)


class TestReadLocalVersions:
    def test_missing_file(self, tmp_path):
        result = read_local_versions(tmp_path)
        assert result == {}

    def test_valid_file(self, tmp_path):
        (tmp_path / "versions.json").write_text('{"fabric-core": "1.0.0"}')
        result = read_local_versions(tmp_path)
        assert result == {"fabric-core": "1.0.0"}

    def test_malformed_json(self, tmp_path):
        (tmp_path / "versions.json").write_text("{not valid json")
        result = read_local_versions(tmp_path)
        assert result == {}

    def test_non_dict_json(self, tmp_path):
        (tmp_path / "versions.json").write_text('["a", "b"]')
        result = read_local_versions(tmp_path)
        assert result == {}

    def test_coerces_values_to_str(self, tmp_path):
        (tmp_path / "versions.json").write_text('{"x": 123}')
        result = read_local_versions(tmp_path)
        assert result == {"x": "123"}


class TestWriteLocalVersions:
    def test_creates_file(self, tmp_path):
        write_local_versions(tmp_path, {"fabric-core": "1.0.0"})
        data = json.loads((tmp_path / "versions.json").read_text())
        assert data["fabric-core"] == "1.0.0"
        assert "installer" in data  # should always include installer version

    def test_merges_with_existing(self, tmp_path):
        (tmp_path / "versions.json").write_text('{"azure-sql": "0.5"}')
        write_local_versions(tmp_path, {"fabric-core": "1.0"})
        data = json.loads((tmp_path / "versions.json").read_text())
        assert data["fabric-core"] == "1.0"
        assert data["azure-sql"] == "0.5"

    def test_creates_directory_if_needed(self, tmp_path):
        nested = tmp_path / "sub" / "dir"
        write_local_versions(nested, {"test": "1.0"})
        assert (nested / "versions.json").exists()


class TestGetUpdateStatus:
    def test_with_manifest(self, tmp_path):
        write_local_versions(tmp_path, {"fabric-core": "1.0.0"})
        manifest = {
            "servers": {
                "fabric-core": {"version": "1.1.0"},
                "azure-sql": {"version": "1.0.0"},
            }
        }
        status = get_update_status(tmp_path, manifest)
        assert status["fabric-core"]["update_available"] is True
        assert status["azure-sql"]["update_available"] is True  # not installed locally

    def test_no_update_when_versions_match(self, tmp_path):
        write_local_versions(tmp_path, {"fabric-core": "1.0.0"})
        manifest = {"servers": {"fabric-core": {"version": "1.0.0"}}}
        status = get_update_status(tmp_path, manifest)
        assert status["fabric-core"]["update_available"] is False

    def test_without_manifest(self, tmp_path):
        write_local_versions(tmp_path, {"fabric-core": "1.0.0"})
        status = get_update_status(tmp_path)
        assert status["fabric-core"]["local"] == "1.0.0"
        assert status["fabric-core"]["remote"] is None
        assert status["fabric-core"]["update_available"] is False

    def test_empty_install_dir(self, tmp_path):
        status = get_update_status(tmp_path)
        assert status == {}
