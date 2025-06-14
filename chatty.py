# chatty.py
# /// script
# dependencies = ["requests<3", "httpx<1", "rich<14"]
# ///
import requests
import json
import subprocess
import tempfile
import os
import re
import sys
import shutil
import textwrap
import argparse
import logging
from typing import List, Dict, Any

from rich.console import Console
from rich.logging import RichHandler

from internal.mcp_manager import MCPManager
from internal.internal_tools import INTERNAL_TOOLS_METADATA, INTERNAL_TOOL_IMPLEMENTATIONS
from internal.agent_prompt import SYSTEM_PROMPT_TEMPLATE, TOOL_CODE_TAG_START, TOOL_CODE_TAG_END
from internal.agent_gateway import start_gateway_server
from internal.code_processor import process_tool_code
from internal.tool_scaffolding import (
    generate_tools_file_content,
    generate_tools_interface_for_prompt,
    TOOLS_GENERATED_FILENAME,
)
from internal.ui import TerminalUI

# --- Configuration: Constants ---
OLLAMA_BASE_URL = "http://localhost:11434"
GATEWAY_HOST = "localhost"
GATEWAY_PORT = 8989

# --- Core Agent Logic Helpers ---
def check_prerequisites(ui: TerminalUI):
    """Checks for required command-line tools and services."""
    ui.display_info("Checking prerequisites...")
    if not shutil.which("uv"):
        ui.display_error("'uv' command not found. Please install it and ensure it's in your PATH.")
        sys.exit(1)
    if not shutil.which("npx"):
        ui.display_warning("'npx' command not found. MCP servers requiring Node.js may fail.")
    try:
        requests.get(OLLAMA_BASE_URL, timeout=3).raise_for_status()
    except requests.RequestException:
        ui.display_error(f"Ollama server not reachable at {OLLAMA_BASE_URL}. Is it running?")
        sys.exit(1)

def prompt_llm_stream(model_name: str, messages_history: list, ui: TerminalUI):
    """Streams the LLM response to the terminal."""
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {"model": model_name, "messages": messages_history, "stream": True, "options": {"temperature": 0.0}}
    full_response_content = ""
    ui.display_assistant_response_start()
    try:
        with requests.post(url, json=payload, stream=True, timeout=300) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line.decode('utf-8'))
                    content = chunk.get('message', {}).get('content', '')
                    if content:
                        ui.display_assistant_stream_chunk(content)
                        full_response_content += content
                    if chunk.get("done"):
                        break
    except requests.RequestException as e:
        logging.critical(f"Ollama connection error: {e}. Exiting.")
        sys.exit(1)
    except KeyboardInterrupt:
        ui.display_warning("\nLLM generation interrupted by user.")
        return full_response_content, True
    finally:
        ui.display_assistant_response_end()
    return full_response_content, False

def list_ollama_models(ui: TerminalUI):
    """Fetches and displays available Ollama models."""
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags")
        response.raise_for_status()
        data = response.json()
        ui.display_ollama_models(data.get("models", []))
    except (requests.RequestException, json.JSONDecodeError) as e:
        ui.display_error(f"Could not connect to Ollama to list models: {e}")

def extract_tool_code(response_text: str) -> str | None:
    """Extracts Python code from between tool code tags."""
    match = re.search(f"{re.escape(TOOL_CODE_TAG_START)}(.*?){re.escape(TOOL_CODE_TAG_END)}", response_text, re.DOTALL)
    return textwrap.dedent(match.group(1).strip()) if match else None

def execute_python_tool(code: str, all_tools_metadata: list):
    """Executes the given Python code in a sandboxed environment using 'uv run'."""
    logging.info("Executing tool code via 'uv run'...")
    with tempfile.TemporaryDirectory(prefix="ollama_tool_run_") as script_dir:
        tools_code = generate_tools_file_content(all_tools_metadata, GATEWAY_HOST, GATEWAY_PORT)
        with open(os.path.join(script_dir, TOOLS_GENERATED_FILENAME), 'w', encoding='utf-8') as f: f.write(tools_code)

        with open(os.path.join(script_dir, "main.py"), 'w', encoding='utf-8') as f: f.write(code)

        proc = subprocess.run(["uv", "run", "main.py"], capture_output=True, text=True, timeout=120, cwd=script_dir)

        filtered_stderr = "\n".join([ln for ln in proc.stderr.splitlines() if not (ln.startswith(("Installed ", "Resolved ", "Downloaded ", "Audited ")) or ln.strip()=="")])

        logging.info("Tool code execution finished.")
        return {"stdout": proc.stdout.strip(), "stderr": filtered_stderr, "error": f"Script exited with code {proc.returncode}." if proc.returncode != 0 else None}

# --- Main Conversation Loop ---
def run_conversation_loop(model_name: str, conversation_history: list, all_tools_metadata: list, ui: TerminalUI):
    """The main REPL for the agent."""
    ui.display_splash_screen()
    logging.info(f"Using Ollama model: {model_name}")

    while True:
        try:
            user_input = ui.prompt_user().strip()
        except KeyboardInterrupt:
            ui.console.print("\nExiting gracefully...")
            break
        except EOFError:
            ui.console.print("\nExiting gracefully...")
            break

        if user_input.lower() in ["exit", "quit"]:
            break
        elif user_input.lower() == "/history":
            ui.display_history(conversation_history)
            continue
        elif user_input.lower() == "/tools":
            ui.display_tools(all_tools_metadata)
            continue
        elif user_input.lower() == "/proxy":
            proxy_code = generate_tools_file_content(all_tools_metadata, GATEWAY_HOST, GATEWAY_PORT)
            ui.display_proxy_code(proxy_code)
            continue

        conversation_history.append({"role": "user", "content": user_input})

        # This inner loop handles a full "turn", which may involve multiple tool calls
        while True:
            llm_response, interrupted = prompt_llm_stream(model_name, conversation_history, ui)
            if interrupted:
                break  # Exit turn on user interrupt, wait for next user input

            tool_code = extract_tool_code(llm_response)

            if not tool_code:
                conversation_history.append({"role": "assistant", "content": llm_response})
                break  # No tool code, LLM response is final for this turn.

            processed = process_tool_code(tool_code)
            uv_code, llm_history_code = processed['uv_code'], processed['llm_history_code']
            
            response_text_part = llm_response.split(TOOL_CODE_TAG_START)[0]
            llm_response_for_history = f"{response_text_part}{TOOL_CODE_TAG_START}\n{llm_history_code}\n{TOOL_CODE_TAG_END}"
            conversation_history.append({"role": "assistant", "content": llm_response_for_history})

            if ui.confirm_tool_execution(uv_code):
                execution_result = execute_python_tool(uv_code, all_tools_metadata)
                tool_output = ui.display_tool_output(execution_result)
                feedback_msg = ""

                if execution_result.get("stderr") and "ModuleNotFoundError" in execution_result["stderr"]:
                    match = re.search(r"No module named '(\S+)'", execution_result["stderr"])
                    module_name = match.group(1).strip("'\"") if match else "a required module"
                    feedback_msg = f"Your code failed with a `ModuleNotFoundError` for '{module_name}'. You MUST add the correct package name to the `# dependencies` comment and provide the full, corrected Python code block now."
                else:
                    feedback_msg = f"Your code was executed. The user's original request was: '{user_input}'.\n\n--- TOOL OUTPUT ---\n{tool_output}\n--- END TOOL OUTPUT ---\n\nBased on this output, provide your final answer that directly addresses the original request. If the tool output suggests another step, only perform it if essential for answering the original request."
                
                logging.debug(f"FEEDBACK TO LLM:\n{feedback_msg}")
                conversation_history.append({"role": "user", "content": feedback_msg})
            else:
                logging.info("Tool execution declined by user.")
                decline_msg = "The user declined to run the code. Acknowledge this and respond to the original request without using tools."
                conversation_history.append({"role": "user", "content": decline_msg})
                
                final_response, _ = prompt_llm_stream(model_name, conversation_history, ui)
                conversation_history.append({"role": "assistant", "content": final_response})
                break
        
        ui.new_turn()

# --- Main Application Orchestrator ---
def main():
    parser = argparse.ArgumentParser(
        description="Chatty - A local code agent powered by Ollama and MCP.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--model", type=str, help="Ollama model to use (e.g., 'llama3:latest').\nThis argument is required.")
    parser.add_argument("--mcp", type=str, default="mcp-config/demo-and-fetch.json", help="Path to the MCP configuration file.")
    parser.add_argument("--verbose", action="store_true", help="Enable INFO level logging.")
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG level logging (overrides --verbose).")
    args = parser.parse_args()

    # --- Configure Logging ---
    log_level = "WARNING"
    if args.verbose: log_level = "INFO"
    if args.debug: log_level = "DEBUG"
    logging.basicConfig(level=log_level, format="%(message)s", datefmt="[%X]", handlers=[RichHandler(rich_tracebacks=True)])

    console = Console(theme={"log.text": ""})
    ui = TerminalUI(console)

    check_prerequisites(ui)

    if not args.model:
        ui.display_error("The --model argument is required.")
        list_ollama_models(ui)
        ui.console.print("\nUsage: [bold]uv run chatty.py --model <model_name>[/bold]")
        sys.exit(1)

    mcp_server_configs = {}
    try:
        with open(args.mcp, 'r') as f:
            mcp_server_configs = json.load(f).get("mcpServers", {})
    except FileNotFoundError:
        ui.display_warning(f"MCP config '{args.mcp}' not found. No external MCP servers will be started.")
    except json.JSONDecodeError as e:
        ui.display_error(f"Could not parse '{args.mcp}': {e}. Continuing without external MCP servers.")

    mcp_manager = MCPManager(mcp_server_configs)
    http_server = None
    try:
        with ui.console.status("[bold green]Starting MCP servers...", spinner="dots"):
            mcp_manager.startup()
        
        all_tools_metadata = INTERNAL_TOOLS_METADATA + mcp_manager.get_all_tools_metadata()
        if not all_tools_metadata:
            ui.display_warning("No tools were loaded (internal or MCP). The agent will have limited capabilities.")

        http_server, _ = start_gateway_server(mcp_manager, INTERNAL_TOOL_IMPLEMENTATIONS, GATEWAY_HOST, GATEWAY_PORT)
        if not http_server:
            raise RuntimeError("Failed to start the tool gateway, cannot continue.")

        tools_interface_for_prompt = generate_tools_interface_for_prompt(all_tools_metadata)
        system_prompt_content = SYSTEM_PROMPT_TEMPLATE.replace("{AVAILABLE_TOOLS_INTERFACE}", tools_interface_for_prompt)
        logging.debug(f"SYSTEM PROMPT:\n{system_prompt_content}")
        conversation_history = [{"role": "system", "content": system_prompt_content}]

        run_conversation_loop(args.model, conversation_history, all_tools_metadata, ui)

    except Exception as e:
        logging.critical(f"A critical error occurred in the main orchestrator: {e}", exc_info=args.debug)
    finally:
        if http_server: http_server.shutdown()
        mcp_manager.shutdown()
        logging.info("Main loop exited. All services shut down.")
        ui.display_info("All services shut down. Goodbye!")

if __name__ == "__main__":
    main()