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
    and wraps them in the `/// script` block required by `uv run`. It also
    infers dependencies from imports. Crucially, it automatically injects
    `from tools import ...` if the `Tools` class is used without being imported,
    and it cleans up erroneous `tools` entries from package dependencies.

    It returns a dictionary containing two versions of the code:
    - `uv_code`: Formatted for direct execution with `uv run`.
    - `llm_history_code`: A simplified version for the LLM's conversation history.
    """
    lines = code.splitlines()
    packages = set()

    # Fast path for existing /// script block
    script_block_match = re.search(r"(# /// script\s*\n\s*#\s*dependencies\s*=\s*(\[.*\])\s*\n\s*# ///\s*\n?)", code, re.DOTALL)
    if script_block_match:
        try:
            packages.update(json.loads(script_block_match.group(2)))
        except json.JSONDecodeError:
            pass # Ignore malformed json
        # Remove the block for now, we'll add it back later.
        code = code.replace(script_block_match.group(1), "", 1)
        lines = code.splitlines()

    # Find and process single-line dependency comments
    dep_regex = re.compile(r"^\s*(#\s*)?dependencies\s*=\s*(\[.*\])")
    cleaned_lines = []
    for line in lines:
        match = dep_regex.match(line)
        if match:
            try:
                packages.update(json.loads(match.group(2)))
            except json.JSONDecodeError:
                pass # Ignore malformed json
        else:
            cleaned_lines.append(line)

    # Check for usage of the `Tools` class and correct common LLM errors.
    code_body_for_check = '\n'.join(cleaned_lines)
    is_tool_class_used = re.search(r"\bTools\.", code_body_for_check) is not None
    
    if is_tool_class_used:
        # Add implicit dependency for gateway communication via `tools.py`.
        packages.add("requests")
        # Remove "tools" if the LLM mistakenly added it as a package dependency.
        packages.discard("tools")

        # If `Tools` is used but not imported, inject the import statement.
        is_tool_module_imported = any(re.search(r"^\s*(from|import)\s+tools\b", line) for line in cleaned_lines)
        if not is_tool_module_imported:
            import_statement = "from tools import Tools, MCPToolError"
            
            # Find the last import to insert after, for proper code formatting.
            last_import_index = -1
            for i in range(len(cleaned_lines) - 1, -1, -1):
                if cleaned_lines[i].strip().startswith(('import ', 'from ')):
                    last_import_index = i
                    break
            
            if last_import_index != -1:
                cleaned_lines.insert(last_import_index + 1, import_statement)
            else:
                # No existing imports, add near top (respecting shebang).
                insert_pos = 1 if cleaned_lines and cleaned_lines[0].startswith('#!') else 0
                cleaned_lines.insert(insert_pos, import_statement)

    # Infer any other dependencies from the code.
    packages.update(_infer_dependencies(cleaned_lines))

    final_code_body = '\n'.join(cleaned_lines)

    if packages:
        dep_line = f'# dependencies = {json.dumps(sorted(list(packages)))}'
        llm_history_code = f'{dep_line}\n{final_code_body}'
        uv_code = f'# /// script\n{dep_line}\n# ///\n{final_code_body}'
    else:
        llm_history_code = final_code_body
        uv_code = final_code_body

    return {'uv_code': uv_code.strip(), 'llm_history_code': llm_history_code.strip()}
