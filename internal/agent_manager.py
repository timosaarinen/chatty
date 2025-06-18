# internal/agent_manager.py
import uuid
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum, auto

class AgentStatus(Enum):
    """Defines the possible states of an agent during its lifecycle."""
    READY = auto()      # Ready for the Kernel to run its next turn.
    RUNNING = auto()    # Currently being processed by the Kernel.
    WAITING = auto()    # Waiting for sub-agents to complete.
    DONE = auto()       # Final response given, awaiting new user input.
    ERROR = auto()      # An unrecoverable error occurred.

@dataclass
class AgentContext:
    """Represents the state and history of a single agent."""
    id: str
    role: str
    history: List[Dict[str, str]] = field(default_factory=list)
    status: AgentStatus = AgentStatus.READY
    result: Optional[str] = None
    parent_id: Optional[str] = None
    is_main: bool = False

class AgentManager:
    """Manages the lifecycle and state of all agents."""

    def __init__(self):
        self._agents: Dict[str, AgentContext] = {}
        self._main_agent_id: Optional[str] = None

    def create_agent(self, role: str, initial_prompt: str, system_prompt: str, parent_id: Optional[str] = None) -> str:
        """Creates a new agent, adds it to the manager, and returns its ID."""
        is_main_agent = not self._main_agent_id
        agent_id = "main" if is_main_agent else f"agent-{uuid.uuid4().hex[:8]}"
        
        history = [{"role": "system", "content": system_prompt}]
        if initial_prompt:
            history.append({"role": "user", "content": initial_prompt})

        agent = AgentContext(
            id=agent_id,
            role=role,
            history=history,
            parent_id=parent_id,
            is_main=is_main_agent,
            # The main agent starts in a DONE state, waiting for user input.
            # Sub-agents start in a READY state, ready for the kernel to run.
            status=AgentStatus.DONE if is_main_agent else AgentStatus.READY
        )
        
        self._agents[agent.id] = agent
        if is_main_agent:
            self._main_agent_id = agent.id
        
        logging.info(f"Created agent {agent.id} (Role: {role}, Main: {is_main_agent})")
        return agent.id

    def get_agent(self, agent_id: str) -> Optional[AgentContext]:
        return self._agents.get(agent_id)

    def get_main_agent(self) -> Optional[AgentContext]:
        if not self._main_agent_id:
            return None
        return self.get_agent(self._main_agent_id)

    def get_next_ready_agent(self) -> Optional[AgentContext]:
        """Finds the next agent that is in the READY state."""
        # Simple FIFO for now. Can be extended with priority later.
        for agent in self._agents.values():
            if agent.status == AgentStatus.READY:
                return agent
        return None
