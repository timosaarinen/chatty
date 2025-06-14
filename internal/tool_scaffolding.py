# tool_scaffolding.py
import re
import textwrap

MCP_PROXY_LIB_FILENAME = "mcp_proxy_lib.py"
TOOLS_GENERATED_FILENAME = "tools.py"

def mcp_proxy_lib_code_factory(host: str, port: int):
    """Generates the Python code for the MCP proxy library."""
    return f"""
import json, sys, httpx
_MCP_AGENT_BASE_URL = "http://{host}:{port}"
class MCPToolError(Exception):
    def __init__(self, message, error_type=None): super().__init__(message); self.error_type = error_type
    def __str__(self): return f"MCPToolError (Type: {{self.error_type or 'UNKNOWN'}}): {{super().__str__()}}"

async def call_mcp(tool_name, **kwargs):
    try:
        async with httpx.AsyncClient() as client:
            payload = {{"tool_name": tool_name, "arguments": kwargs}}
            response = await client.post(f"{{_MCP_AGENT_BASE_URL}}/mcp_tool_call", json=payload, timeout=60)
        
        data = response.json()
        if response.status_code >= 400: raise MCPToolError(data.get("message", "Unknown error"), error_type=data.get("type"))
        
        tool_result = data.get("result", {{}})
        if tool_result.get("isError"):
            error_message = tool_result.get("content", [{{'text': 'Unknown tool error'}}])[0].get('text')
            raise MCPToolError(error_message, error_type="TOOL_EXECUTION_ERROR")

        content = tool_result.get("content", [])
        if len(content) == 1 and "text" in content[0]:
            # If there's a single text result, return it directly.
            return content[0]["text"]
        elif len(content) == 1 and "blob" in content[0]:
            # Handle blobs if needed in the future
            return content[0]["blob"]
        else:
            # For multiple content parts or other complex types, return the list.
            return content
    except httpx.RequestError as e: raise MCPToolError(f"Communication error with gateway: {{e}}", error_type="AGENT_COMMUNICATION_ERROR")
    except json.JSONDecodeError: raise MCPToolError(f"Failed to decode JSON response from gateway.", error_type="AGENT_COMMUNICATION_ERROR")
"""

def generate_tools_file_content(tools_metadata: list):
    """Generates the content for the `tools.py` file from tool metadata."""
    proxy_lib_no_ext = MCP_PROXY_LIB_FILENAME.replace('.py', '')
    lines = [f"from {proxy_lib_no_ext} import call_mcp, MCPToolError", "import asyncio\n", "class Tools:"]
    if not tools_metadata:
        lines.append("    pass")
    else:
        for tool in tools_metadata:
            py_tool_name = tool['name'].replace('/', '_').replace('-', '_')
            parameters = tool.get('inputSchema', {}).get('properties', {})
            param_names = list(parameters.keys())

            method_sig = f"self, {', '.join(param_names)}" if param_names else "self"
            
            # Instead of creating a `kwargs` dictionary, create a string of direct keyword arguments, e.g., "a=a, b=b".
            kwargs_pass = ", ".join([f"{p}={p}" for p in param_names])
            
            docstring = textwrap.indent(tool.get("description", "No description provided."), "        ").strip()
            
            lines.extend([
                f"    async def {py_tool_name}({method_sig}):",
                f"        \"\"\"{docstring}\\n\\n        (Original Name: {tool['name']})\"\"\"",
                f"        return await call_mcp(\"{tool['name']}\", {kwargs_pass})",
                ""
            ])
    return "\n".join(lines)