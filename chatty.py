# chatty.py
# NOTE: do NOT remove the following comment block, it is used by the build system to determine dependencies:
# /// script
# dependencies = ["requests<3", "httpx<1", "rich<14", "litellm<2"]
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
from typing import List, Dict, Any, Callable, Optional
from dataclasses import dataclass

from rich.console import Console
from rich.logging import RichHandler

from internal.context import AppContext
from internal.mcp_manager import MCPManager
from internal.internal_tools import INTERNAL_TOOLS_METADATA, INTERNAL_TOOL_IMPLEMENTATIONS
from internal.agent_prompt import TOOL_TAG_START, TOOL_TAG_END
from internal.prompt_manager import PromptManager
from internal.agent_gateway import start_gateway_server
from internal.agent_manager import AgentManager, AgentStatus
from internal.agent_tools import AgentTools
from internal.tool_scaffolding import generate_tools_interface_for_prompt, generate_tools_file_content
from internal.ui import TerminalUI
from internal.kernel import Kernel
from internal.code_executor import execute_python_code

# --- Configuration: Constants ---
GATEWAY_HOST = "localhost"
GATEWAY_PORT = 8989
DEFAULT_TEMPERATURE = 0.7

# --- Core Logic Helpers ---
def _generate_system_prompt_generator(prompt_manager: PromptManager, all_tools_metadata: list) -> Callable[[], str]:
    """Returns a function that generates the full system prompt content."""
    def generator() -> str:
        system_prompt_template = prompt_manager.get("system")
        if not system_prompt_template:
            raise RuntimeError("No system prompt configured!")
        
        tools_interface_for_prompt = generate_tools_interface_for_prompt(all_tools_metadata)
        
        return system_prompt_template.replace(
            "{AVAILABLE_TOOLS_INTERFACE}", tools_interface_for_prompt
        ).replace(
            "{TOOL_TAG_START}", TOOL_TAG_START
        ).replace(
            "{TOOL_TAG_END}", TOOL_TAG_END
        )
    return generator

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

def list_ollama_models(ui: TerminalUI, ollama_base_url: str):
    """Fetches and displays available Ollama models."""
    try:
        response = requests.get(f"{ollama_base_url}/api/tags")
        response.raise_for_status()
        data = response.json()
        ui.display_ollama_models(data.get("models", []))
    except (requests.RequestException, json.JSONDecodeError) as e:
        ui.display_error(f"Could not connect to Ollama to list models: {e}")

# --- Main Application Loop ---
def run_main_loop(context: AppContext):
    """The main REPL and orchestrator for the agent."""
    if context.litellm_model:
        logging.info(f"Using LiteLLM model: {context.litellm_model} with temperature {context.temperature}")
    else:
        logging.info(f"Using Ollama model: {context.model_name} with temperature {context.temperature}")
    main_agent = context.agent_manager.get_main_agent()

    if not context.kernel or not main_agent:
        logging.critical("Kernel or main agent not initialized. Exiting.")
        return

    while True:
        try:
            if main_agent.status == AgentStatus.DONE:
                user_input = context.ui.prompt_user().strip()
                if not user_input:
                    continue

                if user_input.lower() in ["exit", "quit"]:
                    break
                
                # --- Meta-command handling ---
                if user_input.lower().startswith("/"):
                    command_parts = user_input.lower().split(maxsplit=1)
                    command = command_parts[0]
                    
                    if command == "/help":
                        context.ui.display_help()
                    elif command == "/history":
                        context.ui.display_history(main_agent.history)
                    elif command == "/history-raw":
                        context.ui.display_raw_history(main_agent.history)
                    elif command == "/tools":
                        context.ui.display_tools(context.all_tools_metadata)
                    elif command == "/proxy":
                        proxy_code = generate_tools_file_content(context.all_tools_metadata, context.gateway_host, context.gateway_port)
                        context.ui.display_proxy_code(proxy_code)
                    elif command == "/clear":
                        system_prompt_message = main_agent.history[0]
                        main_agent.history.clear()
                        main_agent.history.append(system_prompt_message)
                        context.ui.display_info("Conversation history has been cleared.")
                    elif command == "/reload":
                        target = command_parts[1] if len(command_parts) > 1 else "all"
                        if target not in ["all", "prompts", "mcp"]:
                            context.ui.display_error(f"Invalid reload target '{target}'. Use 'prompts', 'mcp', or 'all'.")
                            continue
                        
                        if target in ["all", "prompts"]:
                            context.ui.display_info("Reloading prompts from disk...")
                            context.prompt_manager.load()
                        
                        if target in ["all", "mcp"]:
                            context.ui.display_info(f"Reloading MCP configuration from '{context.mcp_config_path}'...")
                            try:
                                with open(context.mcp_config_path, 'r') as f:
                                    new_mcp_config = json.load(f)
                                with context.ui.console.status("[bold green]Restarting MCP servers...", spinner="dots"):
                                    context.mcp_manager.reload(new_mcp_config)
                                context.all_tools_metadata = INTERNAL_TOOLS_METADATA + context.mcp_manager.get_all_tools_metadata() + context.agent_tools_metadata + [context.execute_code_metadata]
                                context.ui.display_info("MCP servers reloaded.")
                            except FileNotFoundError:
                                context.ui.display_error(f"MCP config file not found: '{context.mcp_config_path}'")
                            except json.JSONDecodeError as e:
                                context.ui.display_error(f"Error parsing MCP config: {e}")
                        
                        new_gen = _generate_system_prompt_generator(context.prompt_manager, context.all_tools_metadata)
                        context.kernel.system_prompt_generator = new_gen
                        main_agent.history[0]['content'] = new_gen()
                        context.ui.display_info("System prompt has been updated.")
                    else:
                        context.ui.display_error(f"Unknown command: {command}. Type /help for a list of commands.")
                    continue

                main_agent.history.append({"role": "user", "content": user_input})
                main_agent.status = AgentStatus.READY
            
            agent_to_run = context.agent_manager.get_next_ready_agent()

            if not agent_to_run:
                if main_agent.status == AgentStatus.WAITING:
                    context.ui.display_info("All sub-agents finished. Resuming main agent.")
                    main_agent.status = AgentStatus.READY
                continue

            context.kernel.run_turn(agent_to_run)

        except (KeyboardInterrupt, EOFError):
            context.ui.console.print("\nExiting gracefully...")
            break
        
        context.ui.new_turn_if_needed(main_agent.status)


# --- Main Application Orchestrator ---
def main():
    parser = argparse.ArgumentParser(
        description="Chatty - A local code agent powered by Ollama and MCP.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--model", type=str, help="Ollama model to use (e.g., 'llama3:latest').\nRequired if --litellm-model is not set.")
    parser.add_argument("--ollama", type=str, default="http://localhost:11434", help="Base URL for the Ollama API server.\nDefault: http://localhost:11434")
    parser.add_argument("--mcp", type=str, default="mcp-config/demo-and-fetch.json", help="Path to the MCP configuration file.")
    parser.add_argument("--auto-accept-code", action="store_true", help="Automatically execute all generated tool code without confirmation.")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE, help=f"Set the LLM temperature for creativity. Default: {DEFAULT_TEMPERATURE}")
    parser.add_argument("--litellm-model", type=str, help="Use LiteLLM for inference via a specific model string (e.g., 'openai/gpt-4o', 'openrouter/claude-3-opus'). Overrides --model for inference.")
    parser.add_argument("--no-streaming", action="store_true", help="Disable streaming responses from the LLM.")
    parser.add_argument("--verbose", action="store_true", help="Enable INFO level logging.")
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG level logging (overrides --verbose).")
    args = parser.parse_args()

    # --- Configure Logging & UI ---
    log_level = "WARNING"
    if args.verbose: log_level = "INFO"
    if args.debug: log_level = "DEBUG"
    console = Console()
    handler = RichHandler(console=console, show_time=False, show_level=False, show_path=False, rich_tracebacks=True)
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s", datefmt="[%X]", handlers=[handler])
    ui = TerminalUI(console)

    if args.litellm_model:
        ui.display_info(f"LiteLLM model '{args.litellm_model}' is set and will be used for inference.")
        ui.display_warning("Ensure any required API keys (e.g., OPENAI_API_KEY) are set as environment variables.")

    check_prerequisites(ui, args.ollama)
    prompt_manager = PromptManager(prompt_directory="prompts")

    if not args.model and not args.litellm_model:
        ui.display_error("Either --model (for Ollama) or --litellm-model must be provided.")
        list_ollama_models(ui, args.ollama)
        ui.console.print("\nUsage: [bold]uv run chatty.py --model <model_name>[/bold]")
        ui.console.print("   or: [bold]uv run chatty.py --litellm-model <provider/model_name>[/bold]")
        sys.exit(1)

    mcp_config = {}
    try:
        with open(args.mcp, 'r') as f: mcp_config = json.load(f)
    except FileNotFoundError:
        ui.display_warning(f"MCP config '{args.mcp}' not found. No external MCP servers will be started.")
    except json.JSONDecodeError as e:
        ui.display_error(f"Could not parse '{args.mcp}': {e}. Continuing without external MCP servers.")

    mcp_manager = MCPManager(mcp_config)
    http_server = None
    try:
        with ui.console.status("[bold green]Starting MCP servers...", spinner="dots"):
            mcp_manager.startup()
        ui.console.print()

        # --- Initialize Core Components ---
        agent_manager = AgentManager()
        
        # Define a function for the 'execute_python_code' tool
        def _execute_python_code_impl(code: str):
            # This implementation needs access to the full tool metadata and gateway info
            # We will fetch it from the AppContext which is configured shortly
            return execute_python_code(
                code, 
                app_context.all_tools_metadata, 
                GATEWAY_HOST, 
                GATEWAY_PORT
            )

        # AgentTools provides spawn/wait capabilities, its implementation uses the AgentManager
        agent_tools = AgentTools(agent_manager)
        agent_tools_metadata = agent_tools.get_metadata()
        agent_tools_impls = agent_tools.get_implementations()
        
        # Combine all tool implementations
        all_tool_impls = {
            **INTERNAL_TOOL_IMPLEMENTATIONS,
            **agent_tools_impls,
            "execute_python_code": _execute_python_code_impl,
        }
        
        # Combine all tool metadata
        execute_code_metadata = {
            "name": "execute_python_code",
            "description": "Executes a Python code string in a sandboxed environment. Use this for complex logic, calculations, or tasks not covered by other tools. The code MUST include necessary imports. For third-party libraries, add a comment `# dependencies = [\"package-name\"]`.",
            "inputSchema": {
                "type": "object",
                "properties": { "code": {"type": "string", "description": "The Python code to execute."}},
                "required": ["code"],
            },
            "outputSchema": {"type": "object", "description": "An object containing stdout, stderr, and any system errors."}
        }
        all_tools_metadata = INTERNAL_TOOLS_METADATA + mcp_manager.get_all_tools_metadata() + agent_tools_metadata + [execute_code_metadata]
        
        if not all_tools_metadata:
            ui.display_warning("No tools were loaded. The agent will have limited capabilities.")

        http_server, _ = start_gateway_server(mcp_manager, all_tool_impls, GATEWAY_HOST, GATEWAY_PORT)
        if not http_server:
            raise RuntimeError("Failed to start the tool gateway, cannot continue.")

        system_prompt_generator = _generate_system_prompt_generator(prompt_manager, all_tools_metadata)
        system_prompt_content = system_prompt_generator()
        if not system_prompt_content:
            ui.display_error("System prompt 'prompts/system.txt' not found or is empty. Please create it.")
            sys.exit(1)

        logging.debug(f"SYSTEM PROMPT:\n{system_prompt_content}")
        
        # The main agent starts with only the system prompt.
        agent_manager.create_agent("MainOrchestrator", "", system_prompt_content)

        kernel = Kernel(
            ui=ui,
            agent_manager=agent_manager,
            mcp_manager=mcp_manager,
            all_tool_impls=all_tool_impls,
            system_prompt_generator=system_prompt_generator,
            auto_accept_code=args.auto_accept_code,
            ollama_base_url=args.ollama,
            model_name=args.model,
            temperature=args.temperature,
            streaming=not args.no_streaming,
            litellm_model=args.litellm_model
        )

        app_context = AppContext(
            model_name=args.model,
            ollama_base_url=args.ollama,
            gateway_host=GATEWAY_HOST,
            gateway_port=GATEWAY_PORT,
            ui=ui,
            prompt_manager=prompt_manager,
            all_tools_metadata=all_tools_metadata,
            agent_tools_metadata=agent_tools_metadata,
            execute_code_metadata=execute_code_metadata,
            mcp_manager=mcp_manager,
            agent_manager=agent_manager,
            kernel=kernel,
            mcp_config_path=args.mcp,
            auto_accept_code=args.auto_accept_code,
            temperature=args.temperature,
            streaming=not args.no_streaming,
            litellm_model=args.litellm_model
        )

        ui.display_splash_screen(app_context.auto_accept_code)
        run_main_loop(app_context)

    except Exception as e:
        logging.critical(f"A critical error occurred in the main orchestrator: {e}", exc_info=args.debug)
    finally:
        if http_server: http_server.shutdown()
        mcp_manager.shutdown()
        logging.info("Main loop exited. All services shut down.")
        ui.display_info("All services shut down. Goodbye!")

if __name__ == "__main__":
    main()
