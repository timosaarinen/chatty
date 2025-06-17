# agent_gateway.py
import http.server
import json
import logging
import threading
from socketserver import ThreadingMixIn
from .mcp_manager import MCPManager

class UnifiedRequestHandler(http.server.BaseHTTPRequestHandler):
    """Handles incoming tool call requests from the sandboxed Python scripts."""
    mcp_manager: MCPManager = None
    internal_tool_impls: dict = {}
    
    def do_POST(self):
        if self.path == '/mcp_tool_call':
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = json.loads(self.rfile.read(content_length).decode('utf-8'))
                tool_name = post_data.get('tool_name')
                kwargs = post_data.get('arguments', {})
                
                if self.mcp_manager and tool_name in self.mcp_manager._tool_to_server_map:
                    logging.info(f"Gateway dispatching to MCP tool: '{tool_name}'")
                    normalized_result = self.mcp_manager.dispatch_tool_call(tool_name, kwargs)
                elif tool_name in self.internal_tool_impls:
                    logging.info(f"Gateway dispatching to INTERNAL tool: '{tool_name}'")
                    raw_result = self.internal_tool_impls[tool_name](**kwargs)
                    # Normalize the raw result from internal tools to look like MCP results.
                    if not isinstance(raw_result, dict) or "content" not in raw_result:
                        normalized_result = {"content": [{"type": "text", "text": str(raw_result)}], "isError": False}
                    else: # It's already in the right format
                        normalized_result = raw_result
                else:
                    raise KeyError(f"Tool '{tool_name}' not found in any known implementation (internal or MCP).")

                self._send_response(200, {"status": "success", "result": normalized_result})
            except (TypeError, ValueError) as e:
                self._send_response(400, {"status": "error", "type": "INVALID_TOOL_ARGUMENTS", "message": f"Invalid arguments for '{tool_name}': {e}"})
            except KeyError as e: 
                self._send_response(404, {"status": "error", "type": "TOOL_NOT_FOUND", "message": f"Tool '{tool_name}' not found."})
            except Exception as e:
                self._send_response(500, {"status": "error", "type": "TOOL_EXECUTION_ERROR", "message": str(e)})
        else:
            self._send_response(404, {"status": "error", "message": "Endpoint not found."})

    def _send_response(self, code, payload):
        self.send_response(code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode('utf-8'))

    def log_message(self, format, *args):
        # Suppress the default BaseHTTPServer log messages
        return

class ThreadingHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    """A standard HTTP server that can handle requests in separate threads."""
    allow_reuse_address = True

def start_gateway_server(mcp_manager: MCPManager, internal_tool_impls: dict, host: str, port: int):
    """
    Initializes and starts the tool gateway HTTP server in a separate thread.

    Args:
        mcp_manager: The MCPManager instance.
        internal_tool_impls: A dict mapping internal tool names to their functions.
        host: The hostname for the server to bind to.
        port: The port for the server to bind to.

    Returns:
        A tuple of (server_instance, server_thread) or (None, None) on failure.
    """
    try:
        # Statically configure the handler class before instantiating the server
        UnifiedRequestHandler.mcp_manager = mcp_manager
        UnifiedRequestHandler.internal_tool_impls = internal_tool_impls
        
        server = ThreadingHTTPServer((host, port), UnifiedRequestHandler)
        
        thread = threading.Thread(target=server.serve_forever, daemon=True, name="Gateway-HTTP")
        thread.start()
        
        logging.info(f"Unified tool gateway running on http://{host}:{port}")
        return server, thread
    except Exception as e:
        logging.critical(f"Failed to start tool gateway HTTP server: {e}")
        return None, None