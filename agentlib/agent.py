from dataclasses import dataclass, field
from typing import Any, Callable

@dataclass
class Agent:
    """A simple data container for agent configuration."""
    instructions: str
    tools: list[Callable[..., Any]] = field(default_factory=list)
    model_config: dict[str, Any] = field(default_factory=dict)
