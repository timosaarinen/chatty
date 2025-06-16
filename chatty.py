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
from dataclasses import dataclass

from rich.console import Console
from rich.logging import RichHandler

from internal.context import AppContext
from internal.mcp_manager import MCPManager
from internal.internal_tools import INTERNAL_TOOLS_METADATA, INTERNAL_TOOL_IMPLEMENTATIONS
from internal.agent_prompt import TOOL_CODE_TAG_START, TOOL_CODE_TAG_END
from internal.prompt_manager import PromptManager
from internal.agent_gateway import start_gateway_server
from internal.code_processor import process_tool_code
from internal.tool_scaffolding import (
    generate_tools_file_content,
    generate_tools_interface_for_prompt,
    TOOLS_GENERATED_FILENAME,
)
from internal.ui import TerminalUI

# --- Configuration: Constants ---
GATEWAY_HOST = "localhost"
GATEWAY_PORT = 8989

# --- Core Agent Logic Helpers ---
def _generate_system_prompt(prompt_manager: PromptManager, all_tools_metadata: list) -> str | None:
    """Generates the full system prompt content from the template and tools."""
    system_prompt_template = prompt_manager.get("system")
    if not system_prompt_template:
        return None
    
    tools_interface_for_prompt = generate_tools_interface_for_prompt(all_tools_metadata)
    
    return system_prompt_template.replace(
        "{AVAILABLE_TOOLS_INTERFACE}", tools_interface_for_prompt
    ).replace(
        "{TOOL_CODE_TAG_START}", TOOL_CODE_TAG_START
    ).replace(
        "{TOOL_CODE_TAG_END}", TOOL_CODE_TAG_END
    )

def check_prerequisites(ui: TerminalUI, ollama_base_url: str):
    """Checks for required command-line tools and services."""
    ui.display_info("Checking prerequisites...")
    if not shutil.which("uv"):
        ui.display_error("'uv' command not found. Please install it and ensure it's in your PATH.")
        sys.exit(1)
    if not shutil.which("npx"):
        ui.display_warning("'npx' command not found. MCP servers requiring Node.js may fail.")
    try:
        requests.get(ollama_base_url, timeout=3).raise_for_status()
    except requests.RequestException:
        ui.display_error(f"Ollama server not reachable at {ollama_base_url}. Is it running?")
        sys.exit(1)

def prompt_llm_stream(context: AppContext, messages_history: list):
    """Streams the LLM response to the terminal."""
    url = f"{context.ollama_base_url}/api/chat"
    payload = {"model": context.model_name, "messages": messages_history, "stream": True, "options": {"temperature": 0.0}}
    full_response_content = ""
    context.ui.display_assistant_response_start()
    try:
        with requests.post(url, json=payload, stream=True, timeout=300) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line.decode('utf-8'))
                    content = chunk.get('message', {}).get('content', '')
                    if content:
                        context.ui.display_assistant_stream_chunk(content)
                        full_response_content += content
                    if chunk.get("done"):
                        break
    except requests.RequestException as e:
        logging.critical(f"Ollama connection error: {e}. Exiting.")
        sys.exit(1)
    except KeyboardInterrupt:
        context.ui.display_warning("\nLLM generation interrupted by user.")
        return full_response_content, True
    finally:
        context.ui.display_assistant_response_end()
    return full_response_content, False

def list_ollama_models(ui: TerminalUI, ollama_base_url: str):
    """Fetches and displays available Ollama models."""
    try:
        response = requests.get(f"{ollama_base_url}/api/tags")
        response.raise_for_status()
        data = response.json()
        ui.display_ollama_models(data.get("models", []))
    except (requests.RequestException, json.JSONDecodeError) as e:
        ui.display_error(f"Could not connect to Ollama to list models: {e}")

def extract_tool_code(response_text: str) -> str | None:
    """Extracts Python code from between tool code tags."""
    match = re.search(f"{re.escape(TOOL_CODE_TAG_START)}(.*?){re.escape(TOOL_CODE_TAG_END)}", response_text, re.DOTALL)
    return textwrap.dedent(match.group(1).strip()) if match else None

def execute_python_tool(code: str, context: AppContext):
    """Executes the given Python code in a sandboxed environment using 'uv run'."""
    logging.info("Executing tool code via 'uv run'...")
    with tempfile.TemporaryDirectory(prefix="ollama_tool_run_") as script_dir:
        tools_code = generate_tools_file_content(context.all_tools_metadata, context.gateway_host, context.gateway_port)
        with open(os.path.join(script_dir, TOOLS_GENERATED_FILENAME), 'w', encoding='utf-8') as f: f.write(tools_code)

        with open(os.path.join(script_dir, "main.py"), 'w', encoding='utf-8') as f: f.write(code)

        proc = subprocess.run(["uv", "run", "main.py"], capture_output=True, text=True, timeout=120, cwd=script_dir)

        filtered_stderr = "\n".join([ln for ln in proc.stderr.splitlines() if not (ln.startswith(("Installed ", "Resolved ", "Downloaded ", "Audited ")) or ln.strip()=="")])

        logging.info("Tool code execution finished.")
        return {"stdout": proc.stdout.strip(), "stderr": filtered_stderr, "error": f"Script exited with code {proc.returncode}." if proc.returncode != 0 else None}

# --- Main Conversation Loop ---
def run_conversation_loop(context: AppContext):
    """The main REPL for the agent."""
    logging.info(f"Using Ollama model: {context.model_name}")

    while True:
        try:
            user_input = context.ui.prompt_user().strip()
        except KeyboardInterrupt:
            context.ui.console.print("\nExiting gracefully...")
            break
        except EOFError:
            context.ui.console.print("\nExiting gracefully...")
            break

        if user_input.lower() in ["exit", "quit"]:
            break
        elif user_input.lower() == "/help":
            context.ui.display_help()
            continue
        elif user_input.lower() == "/history":
            context.ui.display_history(context.conversation_history)
            continue
        elif user_input.lower() == "/history-raw":
            context.ui.display_raw_history(context.conversation_history)
            continue
        elif user_input.lower() == "/tools":
            context.ui.display_tools(context.all_tools_metadata)
            continue
        elif user_input.lower() == "/proxy":
            proxy_code = generate_tools_file_content(context.all_tools_metadata, context.gateway_host, context.gateway_port)
            context.ui.display_proxy_code(proxy_code)
            continue
        elif user_input.lower().startswith("/reload"):
            parts = user_input.lower().split(maxsplit=1)
            target = parts[1] if len(parts) > 1 else "all"

            if target not in ["all", "prompts", "mcp"]:
                context.ui.display_error(f"Invalid reload target '{target}'. Use 'prompts', 'mcp', or leave blank for all.")
                continue

            prompts_reloaded = False
            mcp_reloaded = False

            if target in ["all", "prompts"]:
                context.ui.display_info("Reloading prompts from disk...")
                context.prompt_manager.load()
                prompts_reloaded = True

            if target in ["all", "mcp"]:
                context.ui.display_info(f"Reloading MCP configuration from '{context.mcp_config_path}'...")
                try:
                    new_mcp_config = {}
                    with open(context.mcp_config_path, 'r') as f:
                        new_mcp_config = json.load(f)
                    
                    with context.ui.console.status("[bold green]Restarting MCP servers...", spinner="dots"):
                        context.mcp_manager.reload(new_mcp_config)
                    context.ui.console.print()
                    
                    context.all_tools_metadata = INTERNAL_TOOLS_METADATA + context.mcp_manager.get_all_tools_metadata()
                    context.ui.display_info("MCP servers reloaded.")
                    mcp_reloaded = True
                except FileNotFoundError:
                    context.ui.display_error(f"MCP config file not found at '{context.mcp_config_path}'.")
                except json.JSONDecodeError as e:
                    context.ui.display_error(f"Error parsing MCP config file: {e}")
                except Exception as e:
                    context.ui.display_error(f"An unexpected error occurred during MCP reload: {e}", exc_info=logging.getLogger().isEnabledFor(logging.DEBUG))

            if prompts_reloaded or mcp_reloaded:
                new_system_prompt = _generate_system_prompt(context.prompt_manager, context.all_tools_metadata)
                if not new_system_prompt:
                    context.ui.display_error("Failed to generate system prompt after reload. The 'system.txt' prompt may be missing or unreadable.")
                elif context.conversation_history and context.conversation_history[0]["role"] == "system":
                    context.conversation_history[0]["content"] = new_system_prompt
                    context.ui.display_info("System prompt has been updated with new configuration.")
                    logging.debug(f"NEW SYSTEM PROMPT:\n{new_system_prompt}")
                else:
                    context.ui.display_warning("Could not find system prompt in history to update.")
            continue
        elif user_input.lower() == "/clear":
            # Re-initialize history, preserving the system prompt.
            system_prompt = context.conversation_history[0]
            context.conversation_history.clear()
            context.conversation_history.append(system_prompt)
            context.ui.display_info("Conversation history has been cleared.")
            continue

        context.conversation_history.append({"role": "user", "content": user_input})

        # This inner loop handles a full "turn", which may involve multiple tool calls
        while True:
            llm_response, interrupted = prompt_llm_stream(context, context.conversation_history)
            if interrupted:
                break  # Exit turn on user interrupt, wait for next user input

            tool_code = extract_tool_code(llm_response)

            if not tool_code:
                context.conversation_history.append({"role": "assistant", "content": llm_response})
                break  # No tool code, LLM response is final for this turn.

            processed = process_tool_code(tool_code)
            uv_code, llm_history_code = processed['uv_code'], processed['llm_history_code']
            
            response_text_part = llm_response.split(TOOL_CODE_TAG_START)[0]
            llm_response_for_history = f"{response_text_part}{TOOL_CODE_TAG_START}\n{llm_history_code}\n{TOOL_CODE_TAG_END}"
            context.conversation_history.append({"role": "assistant", "content": llm_response_for_history})

            # --- Loop prevention ---
            if uv_code == context.last_tool_code:
                context.consecutive_tool_calls += 1
            else:
                context.consecutive_tool_calls = 1
                context.last_tool_code = uv_code

            if context.consecutive_tool_calls > context.tool_interaction_limit:
                context.ui.display_error(f"Tool loop detected after {context.tool_interaction_limit} identical calls. Aborting this turn.")
                feedback_msg = "You appear to be in a loop, repeatedly calling the same tool with the same arguments. Stop and inform the user that you are stuck and cannot proceed with the current plan."
                context.conversation_history.append({"role": "user", "content": feedback_msg})
                final_response, _ = prompt_llm_stream(context, context.conversation_history)
                context.conversation_history.append({"role": "assistant", "content": final_response})
                break
            
            # --- Tool execution ---
            if context.ui.confirm_tool_execution(uv_code, context):
                execution_result = execute_python_tool(uv_code, context)
                tool_output = context.ui.display_tool_output(execution_result)

                # --- Structured feedback for the LLM ---
                feedback = {"status": "success" if execution_result.get("error") is None else "error", "output": tool_output}
                
                if execution_result.get("stderr") and "ModuleNotFoundError" in execution_result["stderr"]:
                    match = re.search(r"No module named '(\S+)'", execution_result["stderr"])
                    module_name = match.group(1).strip("'\"") if match else "a required module"
                    instruction = f"Your code failed with a `ModuleNotFoundError` for '{module_name}'. You MUST add the correct package name to the `# dependencies` comment and provide the full, corrected Python code block now."
                else:
                    instruction = f"Analyze the tool output in the context of the original user request: '{user_input}'. If the task is complete, provide the final answer to the user. If the task requires another step, generate the necessary tool code. Do not explain the tool output to the user, just use it to progress the task."

                feedback_msg = f"TOOL_EXECUTION_RESULT:\n```json\n{json.dumps(feedback, indent=2)}\n```\n\nINSTRUCTION: {instruction}"
                logging.debug(f"FEEDBACK TO LLM:\n{feedback_msg}")
                context.conversation_history.append({"role": "user", "content": feedback_msg})
            else:
                logging.info("Tool execution declined by user.")
                decline_msg = "The user declined to run the code. Acknowledge this and respond to the original request without using tools."
                context.conversation_history.append({"role": "user", "content": decline_msg})
                
                final_response, _ = prompt_llm_stream(context, context.conversation_history)
                context.conversation_history.append({"role": "assistant", "content": final_response})
                break
        
        context.ui.new_turn()

# --- Main Application Orchestrator ---
def main():
    parser = argparse.ArgumentParser(
        description="Chatty - A local code agent powered by Ollama and MCP.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--model", type=str, help="Ollama model to use (e.g., 'llama3:latest').\nThis argument is required.")
    parser.add_argument("--ollama", type=str, default="http://localhost:11434", help="Base URL for the Ollama API server.\nDefault: http://localhost:11434")
    parser.add_argument("--mcp", type=str, default="mcp-config/demo-and-fetch.json", help="Path to the MCP configuration file.")
    parser.add_argument("--auto-accept-code", action="store_true", help="Automatically execute all generated tool code without confirmation.")
    parser.add_argument("--verbose", action="store_true", help="Enable INFO level logging.")
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG level logging (overrides --verbose).")
    args = parser.parse_args()

    # --- Configure Logging & UI ---
    log_level = "WARNING"
    if args.verbose: log_level = "INFO"
    if args.debug: log_level = "DEBUG"

    console = Console()
    # Configure handler to be minimal, as the code controls the output format.
    # This prevents RichHandler from adding its own timestamps or log levels.
    handler = RichHandler(
        console=console,
        show_time=False,
        show_level=False,
        show_path=False,
        rich_tracebacks=True,
    )
    logging.basicConfig(
        level=log_level, format="%(message)s", datefmt="[%X]", handlers=[handler]
    )

    ui = TerminalUI(console)

    check_prerequisites(ui, args.ollama)
    prompt_manager = PromptManager(prompt_directory="prompts")

    if not args.model:
        ui.display_error("The --model argument is required.")
        list_ollama_models(ui, args.ollama)
        ui.console.print("\nUsage: [bold]uv run chatty.py --model <model_name>[/bold]")
        sys.exit(1)

    mcp_config = {}
    try:
        with open(args.mcp, 'r') as f:
            mcp_config = json.load(f)
    except FileNotFoundError:
        ui.display_warning(f"MCP config '{args.mcp}' not found. No external MCP servers will be started.")
    except json.JSONDecodeError as e:
        ui.display_error(f"Could not parse '{args.mcp}': {e}. Continuing without external MCP servers.")

    mcp_manager = MCPManager(mcp_config)
    http_server = None
    try:
        with ui.console.status("[bold green]Starting MCP servers...", spinner="dots"):
            mcp_manager.startup()
        
        # This explicit print ensures the cursor moves to a new line, preventing
        # the splash screen from overwriting the final status or log line.
        ui.console.print()
        
        all_tools_metadata = INTERNAL_TOOLS_METADATA + mcp_manager.get_all_tools_metadata()
        if not all_tools_metadata:
            ui.display_warning("No tools were loaded (internal or MCP). The agent will have limited capabilities.")

        http_server, _ = start_gateway_server(mcp_manager, INTERNAL_TOOL_IMPLEMENTATIONS, GATEWAY_HOST, GATEWAY_PORT)
        if not http_server:
            raise RuntimeError("Failed to start the tool gateway, cannot continue.")

        system_prompt_content = _generate_system_prompt(prompt_manager, all_tools_metadata)
        if not system_prompt_content:
            ui.display_error("System prompt 'prompts/system.txt' not found or is empty. Please create it.")
            sys.exit(1)

        logging.debug(f"SYSTEM PROMPT:\n{system_prompt_content}")

        context = AppContext(
            model_name=args.model,
            ollama_base_url=args.ollama,
            gateway_host=GATEWAY_HOST,
            gateway_port=GATEWAY_PORT,
            ui=ui,
            prompt_manager=prompt_manager,
            conversation_history=[{"role": "system", "content": system_prompt_content}],
            all_tools_metadata=all_tools_metadata,
            mcp_manager=mcp_manager,
            mcp_config_path=args.mcp,
            auto_accept_code=args.auto_accept_code
        )

        ui.display_splash_screen(context.auto_accept_code)
        run_conversation_loop(context)

    except Exception as e:
        logging.critical(f"A critical error occurred in the main orchestrator: {e}", exc_info=args.debug)
    finally:
        if http_server: http_server.shutdown()
        mcp_manager.shutdown()
        logging.info("Main loop exited. All services shut down.")
        ui.display_info("All services shut down. Goodbye!")

if __name__ == "__main__":
    main()
