# internal/agent_tools.py
import json
from typing import List, Dict, Any

class AgentTools:
    def __init__(self, agent_manager: 'AgentManager', system_prompt: str):
        self.agent_manager = agent_manager
        self.system_prompt = system_prompt

    def spawn_agent(self, role: str, prompt: str) -> str:
        """Spawns a new sub-agent to work on a task. Returns an agent_id."""
        return self.agent_manager.create_agent(role, prompt, self.system_prompt, parent_id=None)

    def llm_request(self, prompt: str) -> str:
        """Performs a simple, one-off LLM request. Returns an agent_id for the task."""
        return self.agent_manager.create_agent("LLM-Request", prompt, self.system_prompt, parent_id=None)

    def wait_for_agents(self, agent_ids: List[str]) -> str:
        """
        Waits for a list of agents to complete.
        This is a special function that signals the main agent to wait.
        It returns a JSON string with a wait directive. The final output to the LLM will be a dictionary of results.
        """
        return json.dumps({"_directive": "wait", "agent_ids": agent_ids})

    def get_metadata(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "spawn_agent",
                "description": "Spawns a new, independent agent to complete a task. Returns an agent_id handle immediately.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string", "description": "The role of the agent, e.g., 'Coder', 'Planner'."},
                        "prompt": {"type": "string", "description": "The initial user-like prompt for the agent to start its work."}
                    },
                    "required": ["role", "prompt"]
                },
                "outputSchema": {"type": "string", "description": "A unique agent_id handle."}
            },
            {
                "name": "llm_request",
                "description": "Performs a simple, one-off LLM request without tool capabilities. Good for summarization or reformatting. Returns a task_id handle immediately.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "The prompt for the LLM."}
                    },
                    "required": ["prompt"]
                },
                "outputSchema": {"type": "string", "description": "A unique agent_id handle for the task."}
            },
            {
                "name": "wait_for_agents",
                "description": "Waits for one or more agents/tasks to complete. This is a blocking call for the current script. Returns a dictionary of {agent_id: result}.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "agent_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "A list of agent_id handles to wait for."
                        }
                    },
                    "required": ["agent_ids"]
                },
                "outputSchema": {"type": "object", "description": "A dictionary mapping each agent_id to its final result."}
            }
        ]

    def get_implementations(self) -> Dict[str, callable]:
        return {
            "spawn_agent": self.spawn_agent,
            "llm_request": self.llm_request,
            "wait_for_agents": self.wait_for_agents,
        }
