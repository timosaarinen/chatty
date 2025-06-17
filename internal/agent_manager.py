# internal/agent_manager.py
import uuid
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import List, Dict, Any, Callable, Optional

@dataclass
class AgentContext:
    id: str = field(default_factory=lambda: f"agent-{uuid.uuid4().hex[:8]}")
    role: str = "Sub-Agent"
    history: List[Dict[str, str]] = field(default_factory=list)
    status: str = "pending"  # pending -> running -> completed | failed
    result: Optional[str] = None
    parent_id: Optional[str] = None

class AgentManager:
    """Manages the lifecycle and execution of sub-agents."""

    def __init__(self, llm_caller: Callable[[List[Dict[str, str]]], str]):
        self._llm_caller = llm_caller
        self._agents: Dict[str, AgentContext] = {}
        self._task_queue: deque[AgentContext] = deque()

    def create_agent(self, role: str, initial_prompt: str, system_prompt: str, parent_id: Optional[str]) -> str:
        agent = AgentContext(
            role=role,
            history=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": initial_prompt}
            ],
            parent_id=parent_id
        )
        self._agents[agent.id] = agent
        self._task_queue.append(agent)
        logging.info(f"Created and queued agent {agent.id} (Role: {role})")
        return agent.id

    def get_task_queue(self) -> deque[AgentContext]:
        return self._task_queue

    def run_agent_task(self, agent: AgentContext):
        agent.status = "running"
        logging.info(f"Running agent {agent.id} (Role: {agent.role})")
        try:
            final_response = self._llm_caller(agent.history)
            agent.history.append({"role": "assistant", "content": final_response})
            agent.result = final_response
            agent.status = "completed"
            logging.info(f"Agent {agent.id} completed successfully.")
        except Exception as e:
            error_message = f"Sub-agent {agent.id} failed during execution: {e}"
            logging.error(error_message, exc_info=True)
            agent.result = error_message
            agent.status = "failed"

    def get_agent(self, agent_id: str) -> Optional[AgentContext]:
        return self._agents.get(agent_id)
