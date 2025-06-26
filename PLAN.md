# Strategic Plan: The Modular, Developer-First Agent

This document outlines the official plan to refactor Chatty into a modular, reusable, and more robust agentic library, with `chatty.py` serving as its primary client.

## 1. Mission Statement

Our mission is to evolve Chatty from a monolithic script into a powerful, developer-first agentic platform. The architecture will be modular, facilitating maintainability and future reuse. The agent will be equipped with a comprehensive toolset for coding tasks, balanced by a risk-aware execution model that relies on explicit user confirmation for high-risk operations. Security will be achieved through user consent and optional containerization, prioritizing developer empowerment and control.

## 2. Core Architectural Principles

*   **Modular by Design:** The core agent logic will be decoupled from the client UI and encapsulated within a new, reusable Python library named `agentlib`.
*   **Developer-First Tooling:** The agent will have access to a rich set of file system and command-line tools necessary for real-world development tasks. We will not limit the toolset but will manage the associated risks.
*   **Risk-Aware Execution:** Tool calls will be classified by risk level. High-risk operations (e.g., writing files, executing shell commands) will always require explicit user confirmation before execution.
*   **Pragmatic Security:** We will operate on a model of informed user consent. The `chatty` application is a tool for developers, who can achieve maximum security by running it within a Docker container. We will not implement a complex multi-service architecture at this stage.
*   **Iterative Refactoring:** We will build the new `agentlib` in parallel with the existing `internal` structure, ensuring a safe and non-disruptive migration path.

## 3. The Phased Implementation Plan

### Phase 1: Foundational Modularization and Tool Expansion

**Goal:** Establish the `agentlib` library and expand the agent's core capabilities with essential developer tools.

1.  **Create the `agentlib` Directory Structure:**
    A new `agentlib/` directory will be created at the project root to house the new modular codebase.
    *   `agentlib/__init__.py`
    *   `agentlib/agent.py`: Defines the `Agent` class, a simple data container for instructions, tools, and model configuration.
    *   `agentlib/manager.py`: Defines the `AgentManager` class. This will become the new "kernel," responsible for the main execution loop, LLM interaction, and dispatching responses.
    *   `agentlib/tools.py`: Implements a new standard library of developer tools.
    *   `agentlib/tracing.py`: Implements a simple, file-based tracing system for logging all LLM I/O to a `logs/` directory for debugging.

2.  **Implement the Standard Tool Library in `agentlib/tools.py`:**
    The following tools will be implemented with clear risk classifications in their metadata (`"risk": "low" | "high"`).

| Tool Name | Description | Parameters | Risk |
| :--- | :--- | :--- | :--- |
| `read_file` | Reads the entire content of a file. | `path: str` | `low` |
| `list_files` | Lists files and directories at a path. | `path: str` | `low` |
| `glob_files` | Finds files matching a glob pattern. | `pattern: str` | `low` |
| `search_file` | Searches for a string within a file. | `path: str, query: str` | `low` |
| `write_file` | Writes content to a file. Does *NOT* fail if the file exists, can be used as unified create/overwrite. Automatically creates directories, so no separate create directory call is needed. | `path: str, content: str` | `high` |
| `edit_file` | Search-replace a portion of file contents. Fails if the search text doesn't exist. | `path: str, search_text: str, replace_text: str` | `high` |
| `shell_command` | Executes a shell command. | `command: str` | `high` |

3.  **Refactor `chatty.py` into a Thin Client:**
    *   The main application logic in `chatty.py` will be refactored to use `agentlib`.
    *   It will instantiate the `AgentManager` and a default `Agent`, then pass user input to the manager's execution loop.
    *   The `internal/kernel.py` file will be marked for deprecation.

### Phase 2: Hybrid Execution and User Confirmation

**Goal:** Make the agent more reliable by introducing a hybrid execution model and more secure by implementing the risk-aware confirmation flow.

1.  **Update the System Prompt (`prompts/system.txt`):**
    *   The prompt will be revised to instruct the LLM on the new hybrid strategy:
        *   **Simple Tasks:** Use `<tool>` blocks for single, atomic actions.
        *   **Complex Tasks:** Use `<python>` blocks for any task requiring logic (loops, conditions), chaining multiple actions, or complex data manipulation.

2.  **Enhance `agentlib.manager.AgentManager`:**
    *   **Hybrid Dispatcher:** The manager will parse LLM responses to detect either `<tool>` or `<python>` blocks and route them to the appropriate handler (the tool executor or the code executor).
    *   **Confirmation Hook:** The `AgentManager` will be modified to accept a `confirm_callback` function during initialization.
    *   **Risk-Checking Logic:** Before executing any tool, the manager will inspect its metadata. If `"risk": "high"`, it will invoke the `confirm_callback` with the tool call details and await a boolean response. Execution will proceed only on an affirmative response.

3.  **Implement Confirmation UI in `chatty.py`:**
    *   The `chatty.py` client will provide a concrete implementation of the `confirm_callback`. This function will use `rich` to display the proposed high-risk action to the user and prompt for a `[y/n]` confirmation.

### Phase 3: Future Work and Long-Term Vision

This section will be added to the plan to track items that are out of scope for the initial refactoring but represent valuable future enhancements.

*   **TODO: Web-Enabled Tools:** Implement `fetch_url` and `web_search` tools, likely leveraging existing MCP servers. These will also require risk assessment.
*   **TODO: Advanced Workspace Management:** Introduce a more formal "workspace" concept to manage context and state across multiple turns.
*   **Future: Multi-Agent Orchestration:** Re-evaluate and implement agent spawning (`spawn_agent`, `wait_for_agents`) within the new `agentlib` framework.
*   **Future: Security Model Re-evaluation:** The single-process architecture is pragmatic for now, but the option to evolve to a multi-service gRPC model for enhanced security and scalability remains a viable long-term goal, which this modularization makes easier.

# Additional notes

* We should not overwrite the current files in 'internal' directory, but create new directories and files for new modular approach. 'chatty.py' can be freely modified, we have saved the original version to 'chatty-v1.py'. Thus, the files in 'internal' directory and 'chatty-v1.py' can be used for read-only reference at all times.