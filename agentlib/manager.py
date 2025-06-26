import json
import re
from typing import Any, Callable, Optional

from .agent import Agent
from .tracing import log_llm_io, litellm_logger_fn
from .tools import TOOL_METADATA

import litellm

def execute_python(code: str) -> Any:
    # A simple, non-sandboxed execution for now.
    # Should be replaced with 'uv run' as in v1.
    exec_globals = {}
    exec(code, exec_globals)
    return exec_globals.get("result", None)

class AgentManager:
    """Manages the agent's execution loop and interaction with the LLM."""

    def __init__(self, agent: Agent, confirm_callback: Optional[Callable[..., bool]] = None):
        self.agent = agent
        self.confirm_callback = confirm_callback
        self.tools = {t.__name__: t for t in agent.tools}

    def run(self, user_input: str) -> Any:
        """Runs the agent's execution loop."""
        log_llm_io("input", user_input)

        model_config = self.agent.model_config.copy()
        model = model_config.pop("model", "ollama/gemma3:1b")
        response = litellm.completion(
            model=model,
            messages=[{"role": "system", "content": self.agent.instructions}, 
                      {"role": "user", "content": user_input}],
            **model_config,
            logger_fn=litellm_logger_fn
        )

        response_content = response.choices[0].message.content
        log_llm_io("output", response_content)

        tool_match = re.search(r"<tool>\n(.*?)\n</tool>", response_content, re.DOTALL)
        python_match = re.search(r"<python>\n(.*?)\n</python>", response_content, re.DOTALL)

        if tool_match:
            tool_call = tool_match.group(1).strip()
            return self.execute_tool(tool_call)
        elif python_match:
            python_code = python_match.group(1).strip()
            return execute_python(python_code)
        else:
            return response_content

    def execute_tool(self, tool_call: str) -> Any:
        """Executes a tool call."""
        match = re.match(r"(\w+)\((.*)\)", tool_call)
        if not match:
            return "Invalid tool call format."

        tool_name, args_str = match.groups()
        if tool_name not in self.tools:
            return f"Tool '{tool_name}' not found."

        try:
            # A simplified parser
            args = dict(re.findall(r'(\w+)="(.*?)"', args_str))
        except Exception:
            return "Invalid tool call arguments."

        if TOOL_METADATA.get(tool_name, {}).get("risk") == "high":
            if not self.confirm_callback or not self.confirm_callback(tool_name, **args):
                return "Tool execution cancelled by user."

        try:
            return self.tools[tool_name](**args)
        except Exception as e:
            return f"Error executing tool '{tool_name}': {e}"