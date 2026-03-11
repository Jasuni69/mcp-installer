"""Tests for mcp_installer.path_manager.

Tests focus on failure modes:
- find_executable with missing tools
- refresh_process_path on non-Windows
- broadcast_env_change error handling
- set_dpi_awareness error handling
"""
import os
import platform
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_installer.path_manager import (
    broadcast_env_change,
    find_executable,
    refresh_process_path,
    set_dpi_awareness,
)


class TestFindExecutable:
    def test_finds_uv_on_path(self):
        """uv should be found since it's installed in this environment."""
        result = find_executable("uv")
        assert result is not None
        assert "uv" in result.lower()

    def test_returns_none_for_nonexistent(self):
        result = find_executable("definitely_not_a_real_tool_xyz123")
        assert result is None

    def test_returns_none_for_empty_name(self):
        result = find_executable("")
        # shutil.which("") returns None
        assert result is None

    @patch("mcp_installer.path_manager.platform.system", return_value="Linux")
    @patch("mcp_installer.path_manager.shutil.which", return_value=None)
    def test_skips_windows_paths_on_linux(self, mock_which, mock_system):
        """On Linux, should not check Windows-specific paths."""
        result = find_executable("uv")
        assert result is None

    @patch("mcp_installer.path_manager.platform.system", return_value="Windows")
    @patch("mcp_installer.path_manager.shutil.which", return_value=None)
    def test_checks_extra_windows_paths(self, mock_which, mock_system):
        """On Windows, should check extra paths even if shutil.which fails."""
        # Will return None since paths don't actually exist, but shouldn't crash
        result = find_executable("git")
        # The function should handle this gracefully
        assert result is None or isinstance(result, str)


class TestRefreshProcessPath:
    @patch("mcp_installer.path_manager.platform.system", return_value="Linux")
    def test_noop_on_linux(self, mock_system):
        result = refresh_process_path()
        assert result == []

    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows only")
    def test_returns_list_on_windows(self):
        result = refresh_process_path()
        assert isinstance(result, list)


class TestBroadcastEnvChange:
    @patch("mcp_installer.path_manager.platform.system", return_value="Linux")
    def test_returns_false_on_linux(self, mock_system):
        result = broadcast_env_change()
        assert result is False

    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows only")
    def test_returns_true_on_windows(self):
        """Should successfully broadcast on Windows."""
        result = broadcast_env_change()
        assert result is True


class TestSetDpiAwareness:
    @patch("mcp_installer.path_manager.platform.system", return_value="Linux")
    def test_returns_false_on_linux(self, mock_system):
        result = set_dpi_awareness()
        assert result is False
