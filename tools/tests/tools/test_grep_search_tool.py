"""Tests for grep_search tool."""
import os
import pytest
from pathlib import Path
from fastmcp import FastMCP
from aden_tools.tools.file_system_toolkits.grep_search.grep_search import register_tools
from unittest.mock import patch, MagicMock

@pytest.fixture
def grep_search_fn(mcp: FastMCP):
    """Register and return the grep_search tool function."""
    register_tools(mcp)
    return mcp._tool_manager._tools["grep_search"].fn

@patch("aden_tools.tools.file_system_toolkits.grep_search.grep_search.get_secure_path")
class TestGrepSearchTool:
    """Tests for grep_search tool."""

    def test_grep_search_tree_pruning(self, mock_secure, grep_search_fn, tmp_path: Path):
        """Verify that ignored directories (node_modules, .git) are pruned."""
        mock_secure.return_value = str(tmp_path)
        
        # Structure:
        # /src/foo.py (match)
        # /node_modules/bad.py (match - should be ignored)
        # /.git/objects/bad.txt (match - should be ignored)
        
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "foo.py").write_text("def match_me(): pass")
        
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "bad.py").write_text("def match_me(): pass")
        
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "bad.txt").write_text("match_me")
        
        # Recursive search
        result = grep_search_fn(
            path=str(tmp_path),
            pattern="match_me",
            workspace_id="ws", agent_id="ag", session_id="sess",
            recursive=True
        )
        
        assert result["success"] is True
        files_found = [m["file"] for m in result["matches"]]
        
        # Convert paths to unix style for consistent checking
        files_found = [f.replace("\\", "/") for f in files_found]
        
        # Valid file should be found (allow for relative path variations)
        assert any("src/foo.py" in f for f in files_found)
        
        # Ignored files should NOT be found
        assert not any("node_modules" in f for f in files_found)
        assert not any(".git" in f for f in files_found)

    def test_grep_search_binary_skipping(self, mock_secure, grep_search_fn, tmp_path: Path):
        """Verify that binary extensions are skipped without opening."""
        mock_secure.return_value = str(tmp_path)
        
        # Create a "binary" file that matches if read as text
        # But has a binary extension
        bad_file = tmp_path / "image.png"
        bad_file.write_text("secret_password")
        
        good_file = tmp_path / "config.txt"
        good_file.write_text("secret_password")
        
        result = grep_search_fn(
            path=str(tmp_path),
            pattern="secret_password",
            workspace_id="ws", agent_id="ag", session_id="sess",
            recursive=False
        )
        
        files_found = [m["file"] for m in result["matches"]]
        files_found = [f.replace("\\", "/") for f in files_found]
        
        assert any("config.txt" in f for f in files_found)
        assert not any("image.png" in f for f in files_found)

    def test_grep_search_max_matches_cap(self, mock_secure, grep_search_fn, tmp_path: Path):
        """Verify that search stops after MAX_MATCHES."""
        mock_secure.return_value = str(tmp_path)
        
        # Create a file with 1100 matches
        large_file = tmp_path / "large.logs"
        content = "error: crash happened\n" * 1100
        large_file.write_text(content)
        
        result = grep_search_fn(
            path=str(tmp_path),
            pattern="error",
            workspace_id="ws", agent_id="ag", session_id="sess",
            recursive=False
        )
        
        assert len(result["matches"]) == 1000  # Hardcoded cap
        assert "warning" in result
        assert "reaching MAX_MATCHES" in result["warning"]
