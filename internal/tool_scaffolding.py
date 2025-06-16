# tool_scaffolding.py
import textwrap

TOOLS_GENERATED_FILENAME = "tools.py"

def generate_tools_file_content(tools_metadata: list, host: str, port: int):
    """Generates the content for the `tools.py` file from tool metadata."""
    header = textwrap.dedent(f"""\
    import json
    import sys
    import requests

    _GATEWAY_URL = "http://{host}:{port}/mcp_tool_call"

    class MCPToolError(Exception):
        def __init__(self, message, error_type=None):
            super().__init__(message)
            self.error_type = error_type
        def __str__(self):
            return f"MCPToolError (Type: {{self.error_type or 'UNKNOWN'}}): {{super().__str__()}}"

    def _call_gateway(tool_name: str, **kwargs):
        try:
            payload = {{"tool_name": tool_name, "arguments": kwargs}}
            response = requests.post(_GATEWAY_URL, json=payload, timeout=60)
            
            response.raise_for_status() # Raises HTTPError for 4xx/5xx
            data = response.json()

            result = data.get("result", {{}})
            if result.get("isError"):
                error_content = result.get("content", [{{}}])[0]
                error_message = error_content.get("text", "Unknown tool execution error")
                raise MCPToolError(error_message, error_type="TOOL_EXECUTION_ERROR")
            
            content = result.get("content", [])
            if len(content) == 1 and content[0].get("type") == "text":
                return content[0]["text"]
            return content

        except requests.HTTPError as e:
            try:
                error_data = e.response.json()
                raise MCPToolError(error_data.get("message", str(e)), error_type=error_data.get("type", "HTTP_ERROR"))
            except json.JSONDecodeError:
                raise MCPToolError(f"HTTP error {{e.response.status_code}} and failed to decode error response.", error_type="HTTP_ERROR")
        except requests.RequestException as e:
            raise MCPToolError(f"Communication error with gateway: {{e}}", error_type="AGENT_COMMUNICATION_ERROR")
        except json.JSONDecodeError:
            raise MCPToolError("Failed to decode successful JSON response from gateway.", error_type="AGENT_COMMUNICATION_ERROR")
    """)
    
    lines = [header.strip(), "", "class Tools:"]
    if not tools_metadata:
        lines.append("    pass")
    else:
        for tool in tools_metadata:
            py_tool_name = tool['name'].replace('/', '_').replace('-', '_')
            parameters = tool.get('inputSchema', {}).get('properties', {})
            param_names = list(parameters.keys())
            method_sig = ", ".join(param_names)
            kwargs_pass = ", ".join([f"{p}={p}" for p in param_names])
            docstring = textwrap.indent(tool.get("description", "No description provided."), "        ").strip()
            
            lines.extend([
                f"    @staticmethod",
                f"    def {py_tool_name}({method_sig}):",
                f"        \"\"\"{docstring}\"\"\"",
                f"        return _call_gateway(\"{tool['name']}\", {kwargs_pass})",
                ""
            ])
    return "\n".join(lines)

def _map_json_type_to_python_type(json_type: str) -> str:
    """Maps JSON schema types to Python type hints."""
    return {
        "string": "str",
        "number": "float",
        "integer": "int",
        "boolean": "bool",
        "object": "dict",
        "array": "list",
    }.get(json_type, "any")

def generate_tools_interface_for_prompt(tools_metadata: list) -> str:
    """Generates a Python-like interface string for the system prompt."""
    if not tools_metadata:
        return "    pass  # No tools available."

    lines = []
    for tool in tools_metadata:
        py_tool_name = tool['name'].replace('/', '_').replace('-', '_')

        # Handle multi-line descriptions
        description = tool.get("description", "No description provided.")
        description_lines = description.strip().split('\n')
        lines.append(f'    # Description: {description_lines[0]}')
        for line in description_lines[1:]:
            lines.append(f'    # {line.strip()}')

        # Build method signature with type hints
        parameters = tool.get('inputSchema', {}).get('properties', {})
        param_parts = []
        for param_name, param_schema in parameters.items():
            param_type = _map_json_type_to_python_type(param_schema.get("type"))
            param_parts.append(f"{param_name}: {param_type}")
        method_sig = ", ".join(param_parts)

        # Build method definition with optional return type
        def_line = f"def {py_tool_name}({method_sig})"
        output_schema = tool.get('outputSchema')
        if output_schema and 'type' in output_schema:
            return_type = _map_json_type_to_python_type(output_schema['type'])
            def_line += f" -> {return_type}"
        def_line += ": ..."

        lines.append(f'    @staticmethod')
        lines.append(f'    {def_line}')
        lines.append('')

    return "class Tools:\n" + "\n".join(lines).strip()
