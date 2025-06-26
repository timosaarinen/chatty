import pytest
from unittest.mock import MagicMock, patch
from agentlib.agent import Agent
from agentlib.manager import AgentManager
from agentlib.tools import get_tools

@pytest.fixture
def mock_agent():
    return Agent(
        instructions="Test instructions",
        tools=get_tools(),
        model_config={"model": "test_model"}
    )

@patch("litellm.completion")
def test_run_llm_only(mock_completion, mock_agent):
    mock_completion.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Hello from the LLM"))]
    )
    manager = AgentManager(mock_agent)
    response = manager.run("User input")
    assert response == "Hello from the LLM"

@patch("litellm.completion")
def test_run_with_tool_call(mock_completion, mock_agent):
    mock_completion.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='<tool>\nread_file(path="/test.txt")\n</tool>'))]
    )
    manager = AgentManager(mock_agent)
    
    # Mock the tool directly in the manager's tool dictionary
    mock_read_file = MagicMock(return_value="File content")
    manager.tools["read_file"] = mock_read_file
    
    response = manager.run("User input")
    
    assert response == "File content"
    mock_read_file.assert_called_once_with(path="/test.txt")

@patch("litellm.completion")
def test_run_with_high_risk_tool_confirmation(mock_completion, mock_agent):
    mock_completion.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='<tool>\nwrite_file(path="/test.txt", content="test")\n</tool>'))]
    )
    confirm_callback = MagicMock(return_value=True)
    manager = AgentManager(mock_agent, confirm_callback=confirm_callback)
    
    # Mock the tool directly
    mock_write_file = MagicMock()
    manager.tools["write_file"] = mock_write_file
    
    manager.run("User input")
    
    confirm_callback.assert_called_once_with("write_file", path="/test.txt", content="test")
    mock_write_file.assert_called_once_with(path="/test.txt", content="test")

@patch("litellm.completion")
def test_run_with_high_risk_tool_rejection(mock_completion, mock_agent):
    mock_completion.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='<tool>\nwrite_file(path="/test.txt", content="test")\n</tool>'))]
    )
    confirm_callback = MagicMock(return_value=False)
    manager = AgentManager(mock_agent, confirm_callback=confirm_callback)
    
    # Mock the tool directly
    mock_write_file = MagicMock()
    manager.tools["write_file"] = mock_write_file
    
    response = manager.run("User input")
    
    assert response == "Tool execution cancelled by user."
    confirm_callback.assert_called_once_with("write_file", path="/test.txt", content="test")
    mock_write_file.assert_not_called()

@patch("litellm.completion")
def test_run_with_python_code(mock_completion, mock_agent):
    mock_completion.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='<python>\nresult = 1 + 1\n</python>'))]
    )
    manager = AgentManager(mock_agent)
    response = manager.run("User input")
    assert response == 2