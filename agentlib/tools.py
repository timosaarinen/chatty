import os
import glob
import subprocess
from typing import Any, Callable, Dict, List

def read_file(path: str) -> str:
    """Reads the entire content of a file."""
    with open(path, "r") as f:
        return f.read()

def list_files(path: str) -> List[str]:
    """Lists files and directories at a path."""
    return os.listdir(path)

def glob_files(pattern: str) -> List[str]:
    """Finds files matching a glob pattern."""
    return glob.glob(pattern, recursive=True)

def search_file(path: str, query: str) -> List[str]:
    """Searches for a string within a file."""
    results = []
    with open(path, "r") as f:
        for i, line in enumerate(f, 1):
            if query in line:
                results.append(f"{i}: {line.strip()}")
    return results

def write_file(path: str, content: str) -> str:
    """Writes content to a file. Automatically creates directories."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    return f"File written to {path}"

def edit_file(path: str, search_text: str, replace_text: str) -> str:
    """Search-replace a portion of file contents."""
    with open(path, "r") as f:
        content = f.read()
    if search_text not in content:
        raise ValueError("Search text not found in file.")
    new_content = content.replace(search_text, replace_text)
    with open(path, "w") as f:
        f.write(new_content)
    return f"File {path} edited successfully."

def shell_command(command: str, dry_run: bool = False) -> str:
    """Executes a shell command."""
    if dry_run:
        return f"Dry run: {command}"
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return result.stdout or result.stderr

# Tool metadata
TOOL_METADATA = {
    "read_file": {"risk": "low"},
    "list_files": {"risk": "low"},
    "glob_files": {"risk": "low"},
    "search_file": {"risk": "low"},
    "write_file": {"risk": "high"},
    "edit_file": {"risk": "high"},
    "shell_command": {"risk": "high"},
}

def get_tools() -> List[Callable[..., Any]]:
    """Returns a list of all available tools."""
    return [
        read_file,
        list_files,
        glob_files,
        search_file,
        write_file,
        edit_file,
        shell_command,
    ]
