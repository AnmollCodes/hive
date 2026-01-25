import os
import re
from mcp.server.fastmcp import FastMCP
from ..security import get_secure_path, WORKSPACES_DIR

def register_tools(mcp: FastMCP) -> None:
    """Register grep search tools with the MCP server."""

    @mcp.tool()
    def grep_search(path: str, pattern: str, workspace_id: str, agent_id: str, session_id: str, recursive: bool = False) -> dict:
        """
        Search for a pattern in a file or directory within the session sandbox.

        Use this when you need to find specific content or patterns in files using regex.
        Set recursive=True to search through all subdirectories.

        Args:
            path: The path to search in (file or directory, relative to session root)
            pattern: The regex pattern to search for
            workspace_id: The ID of the workspace
            agent_id: The ID of the agent
            session_id: The ID of the current session
            recursive: Whether to search recursively in directories (default: False)

        Returns:
            Dict with search results and match details, or error dict
        """
        # 1. Early Regex Validation (Issue #55 Acceptance Criteria)
        # Using .msg for a cleaner, less noisy error response
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return {"error": f"Invalid regex pattern: {e.msg}"}

        try:
            secure_path = get_secure_path(path, workspace_id, agent_id, session_id)
            # Use session dir root for relative path calculations
            session_root = os.path.join(WORKSPACES_DIR, workspace_id, agent_id, session_id)

            # Optimization constants
            IGNORED_DIRS = {
                "node_modules", ".git", "__pycache__", ".venv", "venv", 
                "dist", "build", ".pytest_cache", ".mypy_cache"
            }
            
            BINARY_EXTENSIONS = {
                # Code/Data
                ".pyc", ".pyo", ".pyd", ".class", ".o", ".so", ".dll", ".exe", ".dylib", 
                ".db", ".sqlite", ".sqlite3",
                # Archives
                ".zip", ".tar", ".gz", ".7z", ".rar", ".whl",
                # Media
                ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg",
                ".mp3", ".mp4", ".mov", ".avi",
                ".pdf", ".docx", ".xlsx",
                # Fonts
                ".ttf", ".otf", ".woff", ".woff2"
            }
            
            MAX_MATCHES = 1000
            
            matches = []
            
            # Helper to process a single file
            def process_file(full_path):
                # Binary Check 1: Extension
                _, ext = os.path.splitext(full_path)
                if ext.lower() in BINARY_EXTENSIONS:
                    return

                # Calculate relative path for display
                try:
                    display_path = os.path.relpath(full_path, session_root)
                except ValueError: # Path on different drive
                    display_path = full_path

                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        for i, line in enumerate(f, 1):
                            if len(matches) >= MAX_MATCHES:
                                return "STOP"
                                
                            if regex.search(line):
                                matches.append({
                                    "file": display_path,
                                    "line_number": i,
                                    "line_content": line.strip()
                                })
                except (UnicodeDecodeError, PermissionError, OSError):
                    # Skip binary files detected during read or locked files
                    pass

            # Search logic
            if os.path.isfile(secure_path):
                process_file(secure_path)
                
            elif recursive:
                # Optimized walk with pruning
                for root, dirs, filenames in os.walk(secure_path):
                    if len(matches) >= MAX_MATCHES:
                        break

                    # 1. Tree Pruning (modify dirs in-place)
                    dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]

                    for filename in filenames:
                        if len(matches) >= MAX_MATCHES:
                            break
                        
                        full_path = os.path.join(root, filename)
                        if process_file(full_path) == "STOP":
                            break
            else:
                # Non-recursive directory list
                for item in os.listdir(secure_path):
                    full_path = os.path.join(secure_path, item)
                    if os.path.isfile(full_path):
                        if process_file(full_path) == "STOP":
                            break

            result = {
                "success": True,
                "pattern": pattern,
                "path": path,
                "recursive": recursive,
                "matches": matches,
                "total_matches": len(matches)
            }
            
            if len(matches) >= MAX_MATCHES:
                result["warning"] = f"Stopped early after reaching MAX_MATCHES={MAX_MATCHES}"

            return result

        # 2. Specific Exception Handling (Issue #55 Requirements)
        except FileNotFoundError:
            return {"error": f"Directory or file not found: {path}"}
        except PermissionError:
            return {"error": f"Permission denied accessing: {path}"}
        except Exception as e:
            # 3. Generic Fallback
            return {"error": f"Failed to perform grep search: {str(e)}"}

