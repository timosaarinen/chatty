# internal/context.py
from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class AppContext:
    """A container for shared application state, configuration, and services."""
    model_name: str
    ollama_base_url: str
    gateway_host: str
    gateway_port: int
    mcp_config_path: str
    ui: 'TerminalUI'
    prompt_manager: 'PromptManager'
    conversation_history: List[Dict[str, Any]]
    all_tools_metadata: List[Dict[str, Any]]
    mcp_manager: 'MCPManager'
    agent_manager: 'AgentManager'
    auto_accept_code: bool = False
    consecutive_tool_calls: int = 0
    last_tool_code: str = ""
    tool_interaction_limit: int = 10
