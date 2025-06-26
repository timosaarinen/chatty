import pytest
from agentlib.agent import Agent

def test_agent_creation():
    agent = Agent(instructions="Test instructions")
    assert agent.instructions == "Test instructions"
    assert agent.tools == []
    assert agent.model_config == {}
