# internal/context.py
from typing import List, Dict, Any, TYPE_CHECKING, Optional
from dataclasses import dataclass

if TYPE_CHECKING:
    from .ui import TerminalUI
    from .prompt_manager import PromptManager
    from .mcp_manager import MCPManager
    from .agent_manager import AgentManager
    from .kernel import Kernel

@dataclass
class AppContext:
    """A container for shared application configuration and services."""
    model_name: str
    ollama_base_url: str
    gateway_host: str
    gateway_port: int
    mcp_config_path: str
    ui: 'TerminalUI'
    prompt_manager: 'PromptManager'
    all_tools_metadata: List[Dict[str, Any]]
    agent_tools_metadata: List[Dict[str, Any]]
    execute_code_metadata: Dict[str, Any]
    mcp_manager: 'MCPManager'
    agent_manager: 'AgentManager'
    kernel: Optional['Kernel']
    temperature: float
    streaming: bool
    auto_accept_code: bool = False
