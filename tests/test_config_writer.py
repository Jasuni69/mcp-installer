"""Tests for mcp_installer.config_writer.

Tests focus on failure modes:
- Malformed JSON in existing config files
- Missing directories
- Config merge behavior (should not clobber existing entries)
- Fabric item scanning on empty directories
- CLAUDE.md writing with existing content
"""
import json
import os
from pathlib import Path

import pytest

from mcp_installer.config_writer import (
    build_server_configs,
    copy_agents,
    copy_skills,
    install_glossary,
    install_notebook_template,
    scan_fabric_items,
    write_fabric_claude_md,
)


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


class TestBuildServerConfigs:
    def test_basic_fabric_config(self, tmp_dir):
        configs = build_server_configs(
            server_base_dir=tmp_dir,
            selected_servers=["fabric"],
            uv_path="/usr/bin/uv",
            tenant_id="tenant123",
        )
        assert "fabric-core" in configs
        cfg = configs["fabric-core"]
        assert cfg["command"] == "/usr/bin/uv"
        assert "--directory" in cfg["args"]
        assert cfg["env"]["AZURE_TENANT_ID"] == "tenant123"

    def test_no_env_without_tenant(self, tmp_dir):
        configs = build_server_configs(
            server_base_dir=tmp_dir,
            selected_servers=["fabric"],
            uv_path="uv",
        )
        assert "env" not in configs["fabric-core"]

    def test_azure_sql_config(self, tmp_dir):
        configs = build_server_configs(
            server_base_dir=tmp_dir,
            selected_servers=["azure_sql"],
            uv_path="uv",
            az_server="myserver.database.windows.net",
            az_database="mydb",
            az_auth="sql",
            az_user="admin",
            az_password="s3cr3t",
        )
        assert "azure-sql" in configs
        env = configs["azure-sql"]["env"]
        assert env["AZURE_SQL_SERVER"] == "myserver.database.windows.net"
        assert env["AZURE_SQL_USER"] == "admin"
        assert env["AZURE_SQL_PASSWORD"] == "s3cr3t"

    def test_azure_sql_az_cli_no_creds(self, tmp_dir):
        configs = build_server_configs(
            server_base_dir=tmp_dir,
            selected_servers=["azure_sql"],
            uv_path="uv",
            az_server="server",
            az_database="db",
            az_auth="az_cli",
        )
        env = configs["azure-sql"]["env"]
        assert "AZURE_SQL_USER" not in env
        assert "AZURE_SQL_PASSWORD" not in env

    def test_all_servers(self, tmp_dir):
        configs = build_server_configs(
            server_base_dir=tmp_dir,
            selected_servers=["fabric", "powerbi", "translation", "azure_sql"],
            uv_path="uv",
            az_server="s", az_database="d",
        )
        assert len(configs) == 4
        assert "fabric-core" in configs
        assert "powerbi-modeling" in configs
        assert "powerbi-translation-audit" in configs
        assert "azure-sql" in configs

    def test_empty_selection(self, tmp_dir):
        configs = build_server_configs(tmp_dir, [], "uv")
        assert configs == {}


class TestScanFabricItems:
    def test_empty_directory(self, tmp_dir):
        assert scan_fabric_items(tmp_dir) == []

    def test_finds_platform_files(self, tmp_dir):
        item_dir = tmp_dir / "MyNotebook.Notebook"
        item_dir.mkdir()
        (item_dir / ".platform").touch()
        result = scan_fabric_items(tmp_dir)
        assert len(result) == 1
        assert result[0]["name"] == "MyNotebook.Notebook"

    def test_finds_metadata_files(self, tmp_dir):
        item_dir = tmp_dir / "MyLakehouse.Lakehouse"
        item_dir.mkdir()
        (item_dir / "item.metadata.json").touch()
        result = scan_fabric_items(tmp_dir)
        assert len(result) == 1

    def test_no_duplicates(self, tmp_dir):
        """Items with both .platform and metadata should appear once."""
        item_dir = tmp_dir / "MyItem.Report"
        item_dir.mkdir()
        (item_dir / ".platform").touch()
        (item_dir / "item.metadata.json").touch()
        result = scan_fabric_items(tmp_dir)
        assert len(result) == 1


class TestWriteFabricClaudeMd:
    def test_creates_new_file(self, tmp_dir):
        result = write_fabric_claude_md(tmp_dir)
        assert result == "created"
        assert (tmp_dir / "CLAUDE.md").exists()
        content = (tmp_dir / "CLAUDE.md").read_text()
        assert "# Fabric Project" in content

    def test_appends_to_existing(self, tmp_dir):
        (tmp_dir / "CLAUDE.md").write_text("# My Project\nSome content\n")
        result = write_fabric_claude_md(tmp_dir)
        assert result == "appended"
        content = (tmp_dir / "CLAUDE.md").read_text()
        assert "# My Project" in content
        assert "# Fabric Project" in content

    def test_updates_existing_section(self, tmp_dir):
        (tmp_dir / "CLAUDE.md").write_text(
            "# Fabric Project\nold content\n"
            "- Content files (notebooks: .py cells, semantic models: .tmdl, etc.)\n"
        )
        result = write_fabric_claude_md(tmp_dir)
        assert result == "updated"


class TestCopyAgents:
    def test_copies_fabric_agents(self, tmp_dir):
        # Create source structure
        src = tmp_dir / "source"
        (src / "agents" / "fabric").mkdir(parents=True)
        (src / "agents" / "fabric" / "data-engineer.md").write_text("# DE")
        (src / "agents" / "fabric" / "dax-analyst.md").write_text("# DAX")

        dest = tmp_dir / "dest"
        copied = copy_agents(src, ["fabric"], dest)
        assert len(copied) == 2
        assert (dest / "data-engineer.md").exists()

    def test_copies_azure_sql_agents(self, tmp_dir):
        src = tmp_dir / "source"
        (src / "agents" / "azure-sql").mkdir(parents=True)
        (src / "agents" / "azure-sql" / "sql-analyst.md").write_text("# SQL")

        dest = tmp_dir / "dest"
        copied = copy_agents(src, ["azure_sql"], dest)
        assert len(copied) == 1

    def test_no_agents_for_empty_selection(self, tmp_dir):
        src = tmp_dir / "source"
        src.mkdir()
        dest = tmp_dir / "dest"
        copied = copy_agents(src, [], dest)
        assert copied == []


class TestInstallGlossary:
    def test_copies_files_and_updates_claude_md(self, tmp_dir):
        # Create glossary file
        glossary = tmp_dir / "terms.json"
        glossary.write_text('{"hello": "hej"}')

        dest = tmp_dir / "dest"
        claude_md = tmp_dir / "CLAUDE.md"

        copied = install_glossary([glossary], dest, claude_md)
        assert "terms.json" in copied
        assert (dest / "glossary" / "terms.json").exists()
        assert "Translation Glossary" in claude_md.read_text()

    def test_skips_if_already_referenced(self, tmp_dir):
        glossary = tmp_dir / "terms.json"
        glossary.write_text("{}")
        dest = tmp_dir / "dest"
        claude_md = tmp_dir / "CLAUDE.md"
        claude_md.write_text("## Translation Glossary\nAlready here\n")

        install_glossary([glossary], dest, claude_md)
        # Should not duplicate the section
        content = claude_md.read_text()
        assert content.count("## Translation Glossary") == 1
