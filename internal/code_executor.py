# internal/code_executor.py
import json
import logging
import os
import re
import subprocess
import tempfile
import textwrap
from typing import TYPE_CHECKING
from .tool_scaffolding import generate_tools_file_content, TOOLS_GENERATED_FILENAME

if TYPE_CHECKING:
    from .ui import TerminalUI

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

def process_tool_code(code: str) -> str:
    """
    Processes LLM-generated tool code to handle dependency declarations
    and prepares it for execution with 'uv run'.
    """
    lines = code.splitlines()
    packages = set()

    # Find the last /// script block to handle cases where there are multiple blocks, for example inside <think> tags.
    script_block_regex = r"(# /// script\s*\n\s*#\s*dependencies\s*=\s*(\[.*\])\s*\n\s*# ///\s*\n?)"
    all_matches = list(re.finditer(script_block_regex, code, re.DOTALL))
    if all_matches:
        script_block_match = all_matches[-1] # Get the last match
        try:
            packages.update(json.loads(script_block_match.group(2)))
        except json.JSONDecodeError:
            pass # Ignore malformed json
        
        # Remove all script blocks to avoid confusion, then we'll add a clean one back later.
        code = re.sub(script_block_regex, "", code)
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
        packages.add("requests")
        packages.discard("tools")

        is_tool_module_imported = any(re.search(r"^\s*(from|import)\s+tools\b", line) for line in cleaned_lines)
        if not is_tool_module_imported:
            import_statement = "from tools import Tools, MCPToolError"
            
            last_import_index = -1
            for i in range(len(cleaned_lines) - 1, -1, -1):
                if cleaned_lines[i].strip().startswith(('import ', 'from ')):
                    last_import_index = i
                    break
            
            if last_import_index != -1:
                cleaned_lines.insert(last_import_index + 1, import_statement)
            else:
                insert_pos = 1 if cleaned_lines and cleaned_lines[0].startswith('#!') else 0
                cleaned_lines.insert(insert_pos, import_statement)

    packages.update(_infer_dependencies(cleaned_lines))
    final_code_body = '\n'.join(cleaned_lines)

    if packages:
        dep_line = f'# dependencies = {json.dumps(sorted(list(packages)))}'
        uv_code = f'# /// script\n{dep_line}\n# ///\n{final_code_body}'
    else:
        uv_code = final_code_body

    return uv_code.strip()

def execute_python_code(
    code: str,
    all_tools_metadata: list,
    gateway_host: str,
    gateway_port: int,
    interactive: bool = False,
    ui: 'TerminalUI' = None
) -> dict:
    """
    Executes the given Python code in a sandboxed environment using 'uv run'.
    This involves processing the code to inject dependencies and a tools proxy.
    """
    logging.info("Preparing to execute Python code via 'uv run'...")
    processed_code = process_tool_code(code)
    
    with tempfile.TemporaryDirectory(prefix="ollama_tool_run_") as script_dir:
        tools_code = generate_tools_file_content(all_tools_metadata, gateway_host, gateway_port)
        with open(os.path.join(script_dir, TOOLS_GENERATED_FILENAME), 'w', encoding='utf-8') as f:
            f.write(tools_code)

        with open(os.path.join(script_dir, "main.py"), 'w', encoding='utf-8') as f:
            f.write(processed_code)

        if interactive:
            if ui:
                ui.display_interactive_session_start()
            
            logging.info("Executing processed code in INTERACTIVE sandbox...")
            # Let the subprocess inherit stdin, stdout, stderr from the parent
            proc = subprocess.run(["uv", "run", "main.py"], text=True, cwd=script_dir)
            
            if ui:
                ui.display_interactive_session_end(proc.returncode)

            return {
                "stdout": "Interactive session completed.",
                "stderr": f"Process exited with return code {proc.returncode}.",
                "error": f"Script exited with code {proc.returncode}." if proc.returncode != 0 else None
            }
        else:
            logging.info("Executing processed code in sandbox...")
            proc = subprocess.run(["uv", "run", "main.py"], capture_output=True, text=True, timeout=120, cwd=script_dir)

            filtered_stderr = "\n".join([ln for ln in proc.stderr.splitlines() if not (ln.startswith(("Installed ", "Resolved ", "Downloaded ", "Audited ")) or ln.strip()=="")])

            logging.info("Tool code execution finished.")
            return {"stdout": proc.stdout.strip(), "stderr": filtered_stderr, "error": f"Script exited with code {proc.returncode}." if proc.returncode != 0 else None}
