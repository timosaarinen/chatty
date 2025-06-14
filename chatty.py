# chatty.py
# /// script
# dependencies = ["requests<3", "httpx<1"]
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

from internal.mcp_manager import MCPManager
from internal.internal_tools import INTERNAL_TOOLS_METADATA, INTERNAL_TOOL_IMPLEMENTATIONS
from internal.agent_prompt import SYSTEM_PROMPT_TEMPLATE, TOOL_CODE_TAG_START, TOOL_CODE_TAG_END
from internal.agent_gateway import start_gateway_server
from internal.tool_scaffolding import (
    generate_tools_file_content,
    generate_tools_interface_for_prompt,
    TOOLS_GENERATED_FILENAME,
)

# --- Configuration: Logging & Constants ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(threadName)s] - %(message)s')
OLLAMA_BASE_URL = "http://localhost:11434"
CONFIGURABLE_DEFAULT_MODEL = "llama3:latest"
GATEWAY_HOST = "localhost"
GATEWAY_PORT = 8989

# --- UI/Logging Prefixes ---
PREFIX_USER = "👤 USER:       "
PREFIX_ASSISTANT = "🤖 ASSISTANT:  "
PREFIX_ASSISTANT_PROPOSES_TOOL = "🤖 ASSISTANT proposes to run the following Python code:"
PREFIX_TOOL_OUTPUT = "🛠️ TOOL OUTPUT:  "
SEPARATOR_MAIN = "═" * 80
SEPARATOR_SUB = "─" * 80

# --- Core Agent Logic Helpers ---
def check_prerequisites():
    if not shutil.which("uv"): logging.critical("'uv' command not found. Please install it."); sys.exit(1)
    if not shutil.which("npx"): logging.warning("'npx' command not found. MCP servers requiring Node.js may fail.")
    try: requests.get(OLLAMA_BASE_URL, timeout=3).raise_for_status()
    except requests.RequestException: logging.critical(f"Ollama server not reachable at {OLLAMA_BASE_URL}."); sys.exit(1)
    logging.info("Prerequisites checked.")

def prompt_llm_stream(model_name, messages_history):
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {"model": model_name, "messages": messages_history, "stream": True, "options": {"temperature": 0.0}}
    full_response_content = ""
    print(f"{PREFIX_ASSISTANT}", end="", flush=True)
    try:
        with requests.post(url, json=payload, stream=True, timeout=300) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line.decode('utf-8'))
                    content = chunk.get('message', {}).get('content', '')
                    if content: print(content, end="", flush=True); full_response_content += content
                    if chunk.get("done"): break
    except requests.RequestException as e: logging.critical(f"Ollama connection error: {e}. Exiting."); sys.exit(1)
    except KeyboardInterrupt: print("\n⚠️ LLM generation interrupted by user.", flush=True); return full_response_content, True
    finally: print()
    return full_response_content, False

def list_ollama_models():
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags")
        response.raise_for_status()
        data = response.json()
        models = data.get("models", [])
        if models:
            print("\nPlease choose one of the following models available on your system:")
            for model in models:
                print(f"  - {model['name']}")
        else:
            print("\nCould not find any models installed in Ollama.")
    except requests.RequestException:
        print(f"\nCould not connect to the Ollama server at {OLLAMA_BASE_URL} to list models.")
    except json.JSONDecodeError:
        print("\nReceived an invalid response from the Ollama server.")

def extract_tool_code(response_text):
    match = re.search(f"{re.escape(TOOL_CODE_TAG_START)}(.*?){re.escape(TOOL_CODE_TAG_END)}", response_text, re.DOTALL)
    return textwrap.dedent(match.group(1).strip()) if match else None

def confirm_tool_execution(code):
    print(f"\n{PREFIX_ASSISTANT_PROPOSES_TOOL}\n{SEPARATOR_MAIN}")
    print(textwrap.indent(code, "  ")); print(SEPARATOR_MAIN)
    return input("Execute this Python code? (y/n): ").strip().lower() == 'y'

def display_tool_output(execution_result):
    print(f"{PREFIX_TOOL_OUTPUT}", end="")
    output_parts = []
    if execution_result['stdout']: output_parts.append(f"STDOUT:\n{execution_result['stdout']}")
    if execution_result['stderr']: output_parts.append(f"STDERR:\n{execution_result['stderr']}")
    if execution_result['error']: output_parts.append(f"SYSTEM_ERROR: {execution_result['error']}")
    if not output_parts: print("Script executed with no output."); return "Script executed with no output."
    full_output = "\n\n".join(output_parts); print(full_output)
    return full_output

def execute_python_tool(code: str, all_tools_metadata: list):
    logging.info("Executing tool code via 'uv run'...")
    with tempfile.TemporaryDirectory(prefix="ollama_tool_run_") as script_dir:
        # Generate the tools.py file with embedded gateway logic.
        # The new scaffolding function needs host and port.
        tools_code = generate_tools_file_content(all_tools_metadata, GATEWAY_HOST, GATEWAY_PORT)
        with open(os.path.join(script_dir, TOOLS_GENERATED_FILENAME), 'w', encoding='utf-8') as f: f.write(tools_code)
        
        with open(os.path.join(script_dir, "main_script.py"), 'w', encoding='utf-8') as f: f.write(code)
        
        # 'uv run' handles synchronous scripts perfectly.
        proc = subprocess.run(["uv", "run", "main_script.py"], capture_output=True, text=True, timeout=120, cwd=script_dir)

        # Filter stderr to remove common installation messages
        filtered_stderr = "\n".join([ln for ln in proc.stderr.splitlines() if not (ln.startswith(("Installed ", "Resolved ", "Downloaded ", "Audited ")) or ln.strip()=="")])

        logging.info("Tool code execution finished.")
        return {"stdout": proc.stdout.strip(), "stderr": filtered_stderr, "error": f"Script exited with code {proc.returncode}." if proc.returncode != 0 else None}
    
# --- Main Conversation Loop ---
def run_conversation_loop(model_name: str, conversation_history: list, all_tools_metadata: list):
    print(SEPARATOR_MAIN)
    print("Welcome to Chatty - Code Agent with a Local LLM model and MCP tools")
    print("\nUse /history, /tools or /proxy for debug info.");
    print("Type 'exit' or 'quit' to end.")
    print(SEPARATOR_MAIN)

    while True:
        try:
            user_input = input(f"{PREFIX_USER}").strip()
        except KeyboardInterrupt:
            print("\nExiting gracefully...")
            break

        if user_input.lower() in ["exit", "quit"]:
            break
        elif user_input.lower() == "/history":
            print("--- CONVERSATION HISTORY ---")
            for message in conversation_history:
                role = "USER" if message["role"] == "user" else "ASSISTANT"
                print(f"{role}: {message['content']}")
            print(SEPARATOR_SUB)
            continue
        elif user_input.lower() == "/tools":
            print("--- AVAILABLE TOOLS (Internal + MCP) ---")
            if all_tools_metadata:
                print(json.dumps(all_tools_metadata, indent=2))
            else:
                print("No tools are currently available.")
            print(SEPARATOR_SUB)
            continue
        elif user_input.lower() == "/proxy":
            print("--- GENERATED tools.py PROXY CONTENT ---")
            print(generate_tools_file_content(all_tools_metadata, GATEWAY_HOST, GATEWAY_PORT))
            print(SEPARATOR_SUB)
            continue

        conversation_history.append({"role": "user", "content": user_input})

        # This inner loop handles a full "turn", which may involve multiple tool calls
        # until the LLM provides a final answer without a tool.
        while True:
            llm_response, interrupted = prompt_llm_stream(model_name, conversation_history)
            if interrupted:
                break  # Exit turn on user interrupt, wait for next user input

            conversation_history.append({"role": "assistant", "content": llm_response})
            tool_code = extract_tool_code(llm_response)

            if not tool_code:
                break  # No tool code, LLM response is final for this turn.

            # Tool code was found, confirm and execute.
            if confirm_tool_execution(tool_code):
                execution_result = execute_python_tool(tool_code, all_tools_metadata)
                tool_output = display_tool_output(execution_result)

                feedback_msg = (
                    f"Your code was executed. Output:\n\n{tool_output}\n\n"
                    f"Based on this, provide your final answer **without any code block**, or if the execution failed, write a short status update to user and generate corrected code block."
                )
                #print("[FEEDBACK MSG]", feedback_msg) # DEBUG:
                conversation_history.append({"role": "user", "content": feedback_msg})
                # The loop continues, prompting the LLM for its next step.
            else:
                logging.info("Tool execution declined by user.")
                decline_msg = "The user declined to run the code. Acknowledge this and respond to the original request without using tools."
                conversation_history.append({"role": "user", "content": decline_msg})

                # Get one final response from the LLM and then end the turn.
                final_response, _ = prompt_llm_stream(model_name, conversation_history)
                conversation_history.append({"role": "assistant", "content": final_response})
                break  # Exit the tool-use loop for this turn.

        print(SEPARATOR_SUB)

# --- Main Application Orchestrator ---
def main():
    parser = argparse.ArgumentParser(
        description="Chatty - Ollama code agent with MCP v2 tool discovery.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--model",
        type=str,
        help="Ollama model to use (e.g., 'llama3:latest').\nThis argument is required. If omitted, the agent will list available models."
    )
    parser.add_argument(
        "--mcp",
        type=str,
        default="mcp-config/demo-and-fetch.json",
        help="Path to the MCP configuration file."
    )
    args = parser.parse_args()

    check_prerequisites()

    # Model is required, display available models and exit if not provided
    if not args.model:
        print("\nERROR: The --model argument is required.")
        list_ollama_models()
        print(f"\nUsage: uv run chatty.py --model <model_name>")
        sys.exit(1)

    # Read MCP configuration
    mcp_server_configs = {}
    try:
        with open(args.mcp, 'r') as f:
            config = json.load(f)
            mcp_server_configs = config.get("mcpServers", {})
    except FileNotFoundError:
        logging.warning(f"MCP config '{args.mcp}' not found. No external MCP servers will be started.")
    except json.JSONDecodeError as e:
        logging.error(f"Could not parse '{args.mcp}': {e}. Continuing without external MCP servers.")

    mcp_manager = MCPManager(mcp_server_configs)
    http_server = None
    try:
        # Start MCP Servers
        mcp_manager.startup()
        
        # Aggregate all available tools (internal + MCP)
        all_tools_metadata = INTERNAL_TOOLS_METADATA + mcp_manager.get_all_tools_metadata()
        if not all_tools_metadata: logging.warning("No tools were loaded (internal or MCP). The agent will have limited capabilities.")

        # Start the tool gateway server
        http_server, _ = start_gateway_server(mcp_manager, INTERNAL_TOOL_IMPLEMENTATIONS, GATEWAY_HOST, GATEWAY_PORT)
        if not http_server:
            raise RuntimeError("Failed to start the tool gateway, cannot continue.")

        # Prepare the system prompt with the discovered tools
        tools_interface_for_prompt = generate_tools_interface_for_prompt(all_tools_metadata)
        system_prompt_content = SYSTEM_PROMPT_TEMPLATE.replace("{{AVAILABLE_TOOLS_INTERFACE}}", tools_interface_for_prompt)
        conversation_history = [{"role": "system", "content": system_prompt_content}]

        logging.info(f"Using Ollama model: {args.model}")
        
        # Begin the main chat loop
        run_conversation_loop(args.model, conversation_history, all_tools_metadata)

    except Exception as e:
        logging.critical(f"A critical error occurred in the main orchestrator: {e}")
    finally:
        if http_server: http_server.shutdown()
        mcp_manager.shutdown()
        logging.info("Main loop exited. All services shut down.")

if __name__ == "__main__":
    main()