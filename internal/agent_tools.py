# internal/agent_tools.py
import json
from typing import List, Dict, Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .agent_manager import AgentManager

class AgentTools:
    """Provides tools for agent orchestration (spawning, waiting)."""
    def __init__(self, agent_manager: 'AgentManager'):
        # This class needs the system prompt to pass to new agents.
        # This will be provided by the Kernel during tool execution.
        self.agent_manager = agent_manager
        self.system_prompt: str = ""

    def spawn_agent(self, role: str, prompt: str) -> str:
        """Spawns a new sub-agent to work on a task. Returns an agent_id."""
        # The Kernel will inject the current system_prompt before calling this.
        return self.agent_manager.create_agent(role, prompt, self.system_prompt, parent_id=None)

    def wait_for_agents(self, agent_ids: List[str]) -> str:
        """
        Pauses the current agent and waits for a list of sub-agents to complete.
        This is a special directive that the Kernel will intercept.
        The results of the waited-upon agents will be provided in the next turn.
        """
        # The return value is just for show; the Kernel acts on the tool name.
        return f"Directive to wait for agents: {agent_ids}"

    def get_metadata(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "spawn_agent",
                "description": "Spawns a new, independent sub-agent to complete a task. Returns an agent_id handle immediately, which can be used in subsequent tool calls in the same turn.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string", "description": "The role of the agent, e.g., 'Coder', 'Planner', 'Reviewer'."},
                        "prompt": {"type": "string", "description": "The initial user-like prompt for the agent to start its work."}
                    },
                    "required": ["role", "prompt"]
                },
                "outputSchema": {"type": "string", "description": "A unique agent_id handle for referencing the agent."}
            },
            {
                "name": "wait_for_agents",
                "description": "Waits for one or more sub-agents to complete their tasks. CRITICAL: This tool must be the LAST tool called in a turn. It signals the host to execute the sub-agents. The results will be provided in the TOOL_EXECUTION_RESULT of the next turn.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "agent_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "A list of agent_id handles (e.g., from 'spawn_agent') to wait for."
                        }
                    },
                    "required": ["agent_ids"]
                },
                "outputSchema": {
                    "type": "string",
                    "description": "A confirmation message that the agent is entering a waiting state."
                }
            }
        ]

    def get_implementations(self) -> Dict[str, Callable]:
        return {
            "spawn_agent": self.spawn_agent,
            "wait_for_agents": self.wait_for_agents,
        }
