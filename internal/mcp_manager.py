# mcp_manager.py
import json
import logging
import os
import shlex
import subprocess
import sys
import threading
import time
from itertools import count
from queue import Empty, Queue

REQUEST_TIMEOUT = 30

class _MCPServerConnection:
    def __init__(self, name, config):
        self.name = name
        self.run_command, self.env = self._parse_config(config)
        self.process = None
        self.stderr_thread = None
        self.stdout_queue = Queue()
        self._request_id_counter = count(1)
        self._comm_lock = threading.Lock()
        self.server_info = {}
        self.capabilities = {}
        self.tools = []
        self.resources = []
        self.prompts = []

    def _parse_config(self, config: dict) -> tuple[list[str] | None, dict | None]:
        """Parses server config, supporting legacy 'run' and standard 'command' formats."""
        if "run" in config:
            # Legacy format: "run": "command with args"
            return shlex.split(config["run"]), None
        elif "command" in config:
            # Standard format: "command": "executable", "args": [...]
            command = [config["command"]]
            if "args" in config and isinstance(config["args"], list):
                command.extend(config["args"])
            
            env = None
            if "env" in config and isinstance(config["env"], dict):
                env = os.environ.copy()
                env.update({k: str(v) for k, v in config["env"].items()})
            return command, env
        else:
            logging.error(f"[{self.name}] Invalid server config: must contain a 'run' string or a 'command' key. Disabling.")
            return None, None

    def start(self):
        if not self.run_command:
            return False
            
        logging.info(f"[{self.name}] Starting server with command: '{' '.join(self.run_command)}'")
        try:
            self.process = subprocess.Popen(self.run_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, encoding="utf-8", env=self.env)
        except FileNotFoundError:
            logging.error(f"[{self.name}] Command not found: {self.run_command[0]}. Is it in your PATH?")
            return False
        threading.Thread(target=self._enqueue_stdout, daemon=True).start()
        self.stderr_thread = threading.Thread(target=self._log_stderr, daemon=True)
        self.stderr_thread.start()
        return True
    
    def stop(self):
        if self.process and self.process.poll() is None:
            logging.info(f"[{self.name}] Terminating server process...")
            self.process.terminate()
            try: self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                logging.warning(f"[{self.name}] Server did not terminate gracefully, killing.")
                self.process.kill()

    def _enqueue_stdout(self):
        if not self.process: return
        for line in iter(self.process.stdout.readline, ''): self.stdout_queue.put(line)

    def _log_stderr(self):
        if not self.process: return
        for line in iter(self.process.stderr.readline, ""): logging.warning(f"[{self.name} LOG]: {line.strip()}")

    def send_request(self, method, params=None):
        with self._comm_lock:
            request_id = next(self._request_id_counter)
            message = {"jsonrpc": "2.0", "id": request_id, "method": method}
            if params: message["params"] = params
            self._send_message(message)
            return self._read_response(expected_id=request_id)
        
    def send_notification(self, method, params=None):
        with self._comm_lock:
            message = {"jsonrpc": "2.0", "method": method}
            if params: message["params"] = params
            self._send_message(message)

    def _send_message(self, message_dict):
        if not self.process or not self.process.stdin: return
        json_str = json.dumps(message_dict)
        logging.info(f"[{self.name}] SENT: {json_str}")
        try:
            self.process.stdin.write(json_str + "\n"); self.process.stdin.flush()
        except (IOError, BrokenPipeError) as e:
            logging.critical(f"[{self.name}] FATAL: Failed to write to server stdin: {e}"); self.stop()

    def _read_response(self, expected_id):
        start_time = time.time()
        while time.time() - start_time < REQUEST_TIMEOUT:
            try:
                line = self.stdout_queue.get(timeout=REQUEST_TIMEOUT)
                line = line.strip()
                if not line: continue
                response = json.loads(line)
                if response.get("id") == expected_id:
                    logging.info(f"[{self.name}] RECEIVED: {json.dumps(response)}"); return response
                else: logging.info(f"[{self.name}] Ignored message with non-matching ID: {line}")
            except Empty: break
            except json.JSONDecodeError: logging.warning(f"[{self.name}] Ignored non-JSON line from stdout: {line}")
        logging.error(f"[{self.name}] Timed out waiting for response with id={expected_id}")
        return None

class MCPManager:
    def __init__(self, mcp_config: dict):
        self._reinit(mcp_config)

    def _reinit(self, mcp_config: dict):
        server_configs = mcp_config.get("mcpServers", {})
        self.tool_patches = mcp_config.get("tool_patches", {})
        self.servers = {name: _MCPServerConnection(name, config) for name, config in server_configs.items()}
        self._tool_to_server_map = {}

    def reload(self, mcp_config: dict):
        logging.info("--- MCP Manager Reloading ---")
        self.shutdown()
        self._reinit(mcp_config)
        self.startup()
        logging.info("--- MCP Manager Reload Complete ---")

    def startup(self):
        logging.info("--- MCP Manager Starting Up ---")
        for name, server in self.servers.items():
            if not server.start(): continue
            init_params = {"protocolVersion": "2025-03-26", "clientInfo": {"name": "MCPManagerAgent", "version": "1.1"}, "capabilities": {}}
            init_response = server.send_request("initialize", init_params)
            if not init_response or "error" in init_response:
                logging.error(f"[{name}] Initialization failed. Shutting it down."); server.stop(); continue
            server.server_info = init_response["result"].get("serverInfo", {})
            server.capabilities = init_response["result"].get("capabilities", {})
            server.send_notification("notifications/initialized", {})
            logging.info(f"[{name}] Handshake complete.")
            self._fetch_metadata(server)
        logging.info("--- MCP Manager Startup Complete ---")

    def _fetch_metadata(self, server: _MCPServerConnection):
        if server.capabilities.get("tools"):
            logging.info(f"[{server.name}] Fetching tools...")
            server.tools = self._fetch_paginated_list(server, "tools/list", "tools")

            for i, tool in enumerate(server.tools):
                tool_name = tool.get('name')
                if tool_name in self.tool_patches:
                    logging.info(f"[{server.name}] Patching metadata for tool '{tool_name}'")
                    # Use dict.update to merge patch, overwriting existing keys
                    server.tools[i].update(self.tool_patches[tool_name])

            for tool in server.tools:
                self._tool_to_server_map[tool['name']] = server.name

    def _fetch_paginated_list(self, server: _MCPServerConnection, method: str, result_key: str):
        full_list = []
        cursor = None
        while True:
            params = {"cursor": cursor} if cursor else {}
            response = server.send_request(method, params)
            if not response or "error" in response:
                logging.error(f"[{server.name}] Failed to fetch from {method}."); break
            result = response.get("result", {})
            full_list.extend(result.get(result_key, []))
            cursor = result.get("nextCursor")
            if not cursor: break
        return full_list
    
    def dispatch_tool_call(self, tool_name: str, arguments: dict):
        server_name = self._tool_to_server_map.get(tool_name)
        if not server_name:
            logging.error(f"Dispatch error: Tool '{tool_name}' not found on any MCP server.")
            return None
            
        server = self.servers.get(server_name)
        if not server or not server.process:
            logging.error(f"Dispatch error: Server '{server_name}' for tool '{tool_name}' not running.")
            return None

        logging.info(f"Dispatching tool '{tool_name}' to server '{server_name}'...")
        params = {"name": tool_name, "arguments": arguments}
        response = server.send_request("tools/call", params)
        # The gateway expects the raw result from the tool, not the full MCP response.
        return response.get("result", {}) if response else None

    def get_all_tools_metadata(self) -> list:
        all_metadata = []
        for server in self.servers.values():
            if server.process and server.process.poll() is None:
                all_metadata.extend(server.tools)
        return all_metadata

    def shutdown(self):
        logging.info("--- MCP Manager Shutting Down ---")
        for server in self.servers.values(): server.stop()
        logging.info("--- MCP Manager Shutdown Complete ---")
