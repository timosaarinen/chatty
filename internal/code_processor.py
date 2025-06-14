# internal/code_processor.py
import re
import json

# A mapping of common import names to their corresponding package names for uv.
IMPORT_TO_PACKAGE_MAP = {
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python",
    "dotenv": "python-dotenv",
    "fake": "faker",
    "fitz": "pymupdf",
    "google.cloud": "google-cloud",
    "google.oauth2": "google-auth",
    "matplotlib": "matplotlib",
    "numpy": "numpy",
    "pandas": "pandas",
    "PIL": "pillow",
    "pyarrow": "pyarrow",
    "pydantic": "pydantic",
    "pygame": "pygame",
    "pytest": "pytest",
    "requests": "requests",
    "scipy": "scipy",
    "sklearn": "scikit-learn",
    "seaborn": "seaborn",
    "sqlalchemy": "sqlalchemy",
    "torch": "torch",
    "yaml": "pyyaml",
}

def _infer_dependencies(lines: list[str]) -> set[str]:
    """Scans code lines for imports and maps them to package names."""
    found_packages = set()
    import_regex = re.compile(r"^(?:from|import)\s+([a-zA-Z0-9_]+)")
    for line in lines:
        match = import_regex.match(line.strip())
        if match:
            top_level_module = match.group(1).split('.')[0]
            if top_level_module in IMPORT_TO_PACKAGE_MAP:
                found_packages.add(IMPORT_TO_PACKAGE_MAP[top_level_module])
    return found_packages

def process_tool_code(code: str) -> dict[str, str]:
    """
    Processes LLM-generated tool code to handle dependency declarations.

    This function searches for dependency declarations, normalizes them,
    and wraps them in the `/// script` block required by `uv run`. It can
    also infer common dependencies if they are not declared.

    It returns a dictionary containing two versions of the code:
    - `uv_code`: Formatted for direct execution with `uv run`.
    - `llm_history_code`: A simplified version for the LLM's conversation history.
    """
    # Handle the case where the model correctly generates the full uv block.
    # We still want to simplify it for the history.
    script_block_match = re.search(r"# /// script\s*\n\s*(#\s*dependencies\s*=\s*\[.*\])\s*\n\s*# ///", code, re.DOTALL)
    if script_block_match:
        dep_line = script_block_match.group(1).strip()
        llm_history_code = code.replace(script_block_match.group(0), dep_line)
        return {'uv_code': code, 'llm_history_code': llm_history_code}

    lines = code.splitlines()
    
    dep_line_content = None
    dep_line_index = -1
    
    dep_regex = re.compile(r"^\s*(#\s*)?dependencies\s*=\s*(\[.*\])")
    for i, line in enumerate(lines):
        match = dep_regex.match(line)
        if match:
            dep_line_index = i
            # Normalize to '# dependencies = [...]'
            dep_line_content = f'# dependencies = {match.group(2)}'
            break

    # If no dependency line, try to infer it from imports.
    if dep_line_content is None:
        inferred_packages = _infer_dependencies(lines)
        if inferred_packages:
            dep_line_content = f'# dependencies = {json.dumps(sorted(list(inferred_packages)))}'
            lines.insert(0, dep_line_content)
            dep_line_index = 0
    
    # If a dependency line was found, ensure it is in the correct format in the lines list.
    if dep_line_index != -1:
        lines[dep_line_index] = dep_line_content
    
    llm_history_code = '\n'.join(lines)
    
    # If a dependency line exists, wrap it for `uv`.
    if dep_line_content:
        # Re-create lines from llm_history_code to be safe.
        uv_lines = llm_history_code.splitlines()
        for i, line in enumerate(uv_lines):
            if line.strip() == dep_line_content:
                uv_lines[i] = f'# /// script\n{dep_line_content}\n# ///'
                uv_code = '\n'.join(uv_lines)
                break
        else: # Should not happen, but as a fallback.
            uv_code = llm_history_code
    else:
        # No dependencies were found or inferred.
        uv_code = llm_history_code
        
    return {'uv_code': uv_code, 'llm_history_code': llm_history_code}
