# internal/kernel.py
import json
import logging
import re
import requests
import sys
from typing import List, Dict, Any, Callable, TYPE_CHECKING, Tuple

from .agent_manager import AgentContext, AgentManager, AgentStatus
from .agent_prompt import TOOL_TAG_START, TOOL_TAG_END
from .ui import TerminalUI

if TYPE_CHECKING:
    from .mcp_manager import MCPManager

class Kernel:
    """Orchestrates the agent lifecycle, including LLM interaction, tool use, and state management."""

    def __init__(
        self,
        ui: TerminalUI,
        agent_manager: AgentManager,
        mcp_manager: 'MCPManager',
        all_tool_impls: Dict[str, Callable],
        system_prompt_generator: Callable,
        auto_accept_code: bool,
        ollama_base_url: str,
        model_name: str,
        temperature: float,
        streaming: bool,
    ):
        self.ui = ui
        self.agent_manager = agent_manager
        self.mcp_manager = mcp_manager
        self.all_tool_impls = all_tool_impls
        self.system_prompt_generator = system_prompt_generator
        self.auto_accept_code = auto_accept_code
        self.ollama_base_url = ollama_base_url
        self.model_name = model_name
        self.temperature = temperature
        self.streaming = streaming
        self._tool_call_id_counter = 0

    def run_turn(self, agent: AgentContext):
        """Executes one full 'turn' for a given agent."""
        agent.status = AgentStatus.RUNNING
        self.ui.display_agent_activity(agent.id, agent.role, "starting turn...")

        if agent.history and agent.history[0]["role"] == "system":
            agent.history[0]["content"] = self.system_prompt_generator()
        
        response_text, interrupted = self._call_llm(agent)
        if interrupted:
            agent.status = AgentStatus.DONE
            return

        tool_content = self._extract_tool_content(response_text)

        if not tool_content:
            if not (self.streaming and agent.is_main):
                self.ui.display_final_answer(agent.id, agent.role, response_text)
            agent.history.append({"role": "assistant", "content": response_text})
            agent.status = AgentStatus.DONE
            return

        full_assistant_message = f"{TOOL_TAG_START}\n{tool_content}\n{TOOL_TAG_END}"
        agent.history.append({"role": "assistant", "content": full_assistant_message})

        try:
            tool_calls = json.loads(tool_content)
            if not isinstance(tool_calls, list):
                raise ValueError("Tool content is not a JSON list.")
        except (json.JSONDecodeError, ValueError) as e:
            error_message = f"Error: Invalid tool format. Expected a JSON list within <tool> tags. Parser error: {e}"
            self.ui.display_error(error_message)
            agent.history.append({"role": "user", "content": f"TOOL_EXECUTION_RESULT:\n{error_message}"})
            agent.status = AgentStatus.READY
            return
        
        tool_results = self._execute_tool_calls(agent, tool_calls)
        
        feedback_msg = f"TOOL_EXECUTION_RESULT:\n```json\n{json.dumps(tool_results, indent=2)}\n```"
        agent.history.append({"role": "user", "content": feedback_msg})

        if agent.status != AgentStatus.WAITING:
            agent.status = AgentStatus.READY

    def _call_llm(self, agent: AgentContext) -> Tuple[str, bool]:
        """Calls the LLM, either streaming or non-streaming based on configuration."""
        if self.streaming and agent.is_main:
            return self._call_llm_stream(agent.history)
        return self._call_llm_non_stream(agent.history)

    def _call_llm_stream(self, messages_history: list) -> Tuple[str, bool]:
        url = f"{self.ollama_base_url}/api/chat"
        payload = {"model": self.model_name, "messages": messages_history, "stream": True, "options": {"temperature": self.temperature}}
        full_response_content = ""
        
        if not any(msg['role'] == 'assistant' and self._extract_tool_content(msg['content']) for msg in messages_history):
            self.ui.display_assistant_response_start()
            
        try:
            with requests.post(url, json=payload, stream=True, timeout=300) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        chunk = json.loads(line.decode('utf-8'))
                        content = chunk.get('message', {}).get('content', '')
                        if content:
                            self.ui.display_assistant_stream_chunk(content)
                            full_response_content += content
                        if chunk.get("done"):
                            break
        except requests.RequestException as e:
            logging.critical(f"Ollama connection error: {e}. Exiting.")
            sys.exit(1)
        except KeyboardInterrupt:
            self.ui.display_warning("\nLLM generation interrupted by user.")
            return full_response_content, True
        finally:
             self.ui.display_assistant_response_end()

        return full_response_content, False

    def _call_llm_non_stream(self, messages_history: list) -> Tuple[str, bool]:
        url = f"{self.ollama_base_url}/api/chat"
        payload = {"model": self.model_name, "messages": messages_history, "stream": False, "options": {"temperature": self.temperature}}
        try:
            response = requests.post(url, json=payload, timeout=300)
            response.raise_for_status()
            full_response = response.json()
            content = full_response.get('message', {}).get('content', '')
            return content, False
        except requests.RequestException as e:
            logging.error(f"LLM call failed: {e}")
            return f"Error: Could not contact LLM. {e}", False

    def _execute_tool_calls(self, agent: AgentContext, tool_calls: List[Dict]) -> List[Dict]:
        """Executes a list of tool calls, handling dependencies and special directives."""
        results = []
        call_results_by_id = {} # For resolving references

        for call in tool_calls:
            tool_name = call.get("tool_name")
            tool_args = call.get("arguments", {})
            tool_call_id = call.get("call_id", self._get_next_tool_call_id())

            try:
                resolved_args = self._resolve_argument_references(tool_args, call_results_by_id)
            except ValueError as e:
                result = {"status": "error", "error": str(e)}
                results.append({"call_id": tool_call_id, "result": result})
                call_results_by_id[tool_call_id] = result
                continue

            if tool_name == "wait_for_agents":
                agent.status = AgentStatus.WAITING
                self.ui.display_info("Wait directive received. Agent is now waiting.")
                result = {"status": "success", "output": "Agent is now waiting for sub-agents to complete."}
                results.append({"call_id": tool_call_id, "result": result})
                call_results_by_id[tool_call_id] = result
                continue

            action_type = "CODE_EXECUTION" if tool_name == "execute_python_code" else "TOOL_CALL"
            details = resolved_args.get('code', "") if tool_name == 'execute_python_code' else json.dumps(call, indent=2)

            if self.ui.confirm_action(agent.id, agent.role, action_type, details, self.auto_accept_code):
                try:
                    if not tool_name or not isinstance(tool_name, str):
                        raise ValueError("Tool name is missing or invalid in the tool call.")
                    
                    if tool_name == "spawn_agent":
                        agent_tools_instance = self.all_tool_impls[tool_name].__self__
                        agent_tools_instance.system_prompt = self.system_prompt_generator()

                    logging.info(f"Agent '{agent.id}' executing tool '{tool_name}' with args: {resolved_args}")
                    
                    if tool_name in self.all_tool_impls:
                        output = self.all_tool_impls[tool_name](**resolved_args)
                        result = {"status": "success", "output": output}
                    elif tool_name in self.mcp_manager._tool_to_server_map:
                        mcp_result = self.mcp_manager.dispatch_tool_call(tool_name, resolved_args)
                        if mcp_result is None:
                            raise ConnectionError(f"MCP tool dispatch for '{tool_name}' failed. The server may be down or the tool unavailable.")
                        
                        if mcp_result.get("isError"):
                            error_content = mcp_result.get("content", [{}])[0].get("text", "Unknown MCP tool error")
                            raise Exception(error_content)
                        
                        content = mcp_result.get("content", [])
                        output = content[0]["text"] if len(content) == 1 and content[0].get("type") == "text" else content
                        result = {"status": "success", "output": output}
                    else:
                        raise KeyError(f"Tool '{tool_name}' not found.")

                except Exception as e:
                    logging.error(f"Tool call failed for '{tool_name}': {e}", exc_info=True)
                    result = {"status": "error", "error": str(e)}
            else:
                logging.warning(f"Execution of tool '{tool_name}' declined by user.")
                result = {"status": "error", "error": "Tool execution was declined by the user."}
            
            self.ui.display_tool_output(result)
            results.append({"call_id": tool_call_id, "result": result})
            call_results_by_id[tool_call_id] = result
        
        return results

    def _resolve_argument_references(self, args: dict, results_by_id: dict) -> dict:
        """Recursively replaces '$ref' strings in arguments with previous tool results."""
        resolved_args = {}
        for key, value in args.items():
            if isinstance(value, str) and value.startswith("$"):
                ref_id = value[1:] # remove '$'
                if ref_id not in results_by_id:
                    raise ValueError(f"Invalid reference: Tool result for '{ref_id}' not found.")
                # We replace the arg with the 'output' part of the result
                resolved_args[key] = results_by_id[ref_id].get("output")
            elif isinstance(value, dict):
                resolved_args[key] = self._resolve_argument_references(value, results_by_id)
            elif isinstance(value, list):
                resolved_args[key] = [
                    self._resolve_argument_references(item, results_by_id) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                resolved_args[key] = value
        return resolved_args

    def _get_next_tool_call_id(self) -> str:
        self._tool_call_id_counter += 1
        return f"call_{self._tool_call_id_counter}"

    def _extract_tool_content(self, response_text: str) -> str | None:
        """Extracts content from between <tool> tags."""
        match = re.search(f"{re.escape(TOOL_TAG_START)}(.*?){re.escape(TOOL_TAG_END)}", response_text, re.DOTALL)
        return match.group(1).strip() if match else None
