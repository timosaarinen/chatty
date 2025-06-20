### **Evolving Chatty to a Hybrid Agentic Service**

**1. Mission Statement**

This document outlines the architecture and implementation plan to evolve Chatty from a monolithic REPL into a robust, service-oriented agentic platform. The new architecture will be secure, scalable, and efficient, supporting both simple, direct tool calls and complex, sandboxed code execution. This will serve as the foundation for advanced, multi-agent capabilities.

**2. Core Architectural Principles**

Our design is guided by the following principles:

*   **Hybrid Execution Efficiency:** The system must not force complex solutions for simple problems. It will support both low-latency direct tool calls and powerful Python code orchestration, directing the LLM to use the least power necessary for each task.
*   **Security by Default:** All LLM-generated code execution will occur within a software-defined sandbox. The core service will never directly execute untrusted code.
*   **Clear Separation of Concerns:** Each component will have a single, well-defined responsibility (e.g., orchestration, secure execution, client interaction). This enhances maintainability, testability, and scalability.
*   **Scalability by Design:** The architecture will be composed of stateless services that can be scaled independently, avoiding the pitfalls of a monolithic structure.
*   **Developer-Centric Tooling:** The primary use case is a local developer assistant. The system must seamlessly and securely interact with the user's local filesystem and development tools.

**3. System Architecture**

The platform will consist of three primary components communicating over high-performance gRPC.

| Component                  | Language | Key Responsibility                                                                                                                              |
| -------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **Chatty Client**          | Python   | Provides the user interface (CLI). It is a thin client that sends user prompts to the `AgentKernelService` and displays final results.                |
| **AgentKernelService**     | Go       | The "brain." A gRPC service that manages workspaces, tasks, and agent lifecycles. It orchestrates all workflows, makes LLM calls, and performs all direct file/tool I/O. |
| **SecureRunnerService**    | Python   | The "hands." A dedicated gRPC service that wraps SmolAgents' `LocalPythonExecutor`. It provides a secure, AST-based sandbox for executing LLM-generated Python code on behalf of the Kernel. |

**Architectural Flow:**


1.  The **Client** sends a user prompt to the **AgentKernelService**.
2.  The **Kernel** determines the strategy and calls the LLM.
3.  The LLM responds with either a `<tool>` block or a `<python>` block.
4.  **If `<tool>`:** The **Kernel** executes the tool call directly and returns the result.
5.  **If `<python>`:** The **Kernel** sends the code to the **SecureRunnerService** for execution.
6.  The **Runner** executes the code, proxying any required tool/file access back to the **Kernel** for safe, controlled I/O.
7.  The final result from the runner is passed back to the **Kernel**, which then concludes the task.

**4. The Hybrid Execution Model in Detail**

The LLM will be instructed to choose one of two response formats based on the task's complexity.

| Task Characteristics                                                  | Required Response Format          | Execution Path                            |
| --------------------------------------------------------------------- | --------------------------------- | ----------------------------------------- |
| Single, atomic action covered by a registered tool (e.g., `get_weather`). | **Direct Tool Call** (`<tool>` block) | `AgentKernelService` (Direct Go execution)  |
| Any logic (loops, conditions), file I/O, chaining multiple actions, or spawning sub-agents. | **Code Execution** (`<python>` block) | `SecureRunnerService` (Sandboxed Python) |

This dual-mode approach ensures maximum efficiency by using the fastest path for simple tasks while providing the power and safety of a full scripting environment for complex ones.

**5. Component Specifications**

**5.1. AgentKernelService (Go)**

*   **Responsibilities:**
    *   Expose a gRPC API for the client.
    *   Manage workspaces, tasks, and agent state.
    *   Maintain a registry of "direct-callable" tools (e.g., MCP tools).
    *   Construct prompts and make all LLM API calls.
    *   Implement the central dispatcher to route LLM responses to either the direct tool executor or the `SecureRunnerService`.
    *   Perform all actual file system and tool I/O on behalf of the runner.
    *   Provide structured logging and observability endpoints (`/tasks`, `/health`).
*   **Conceptual gRPC Interface (`kernel.proto`):**
    ```protobuf
    service AgentKernel {
      // Creates a new end-to-end task from a user prompt.
      rpc CreateTask(CreateTaskRequest) returns (CreateTaskResponse);
      // Allows clients to stream results/logs for a task.
      rpc StreamTaskEvents(StreamTaskRequest) returns (stream TaskEvent);
      // Internal endpoint for the runner to call tools.
      rpc ExecuteTool(ExecuteToolRequest) returns (ExecuteToolResponse);
    }
    ```

**5.2. SecureRunnerService (Python)**

*   **Responsibilities:**
    *   Provide a gRPC service that wraps SmolAgents' `local_python_executor`. This is our primary open-source leverage.
    *   On startup, instantiate the executor.
    *   Expose a single primary gRPC method: `Execute(code, context)`.
    *   Dynamically construct the `toolbox` for the executor on each call. The toolbox will contain proxy functions that make gRPC calls back to the `AgentKernelService`'s `ExecuteTool` endpoint. This ensures the sandboxed code never performs I/O directly.
*   **Conceptual gRPC Interface (`runner.proto`):**
    ```protobuf
    service SecureRunner {
      // Executes a script in the sandbox.
      rpc Execute(ExecuteRequest) returns (ExecuteResponse);
    }
    ```

**5.3. System Prompt (`system.txt`)**

The prompt is critical. It must clearly instruct the LLM on how to use the hybrid model. It will contain:
1.  **Core Persona:** "You are a helpful AI assistant..."
2.  **Hybrid Strategy Explanation:** A clear description of when to use `<tool>` for simple actions vs. `<python>` for complex orchestration, based on the table in section 4.
3.  **Direct Tool Specification:** A list of available direct-callable tools and their schemas.
4.  **Python SDK Specification:** A description of the `agents` SDK, including the `Workspace` object (`ws.read`, `ws.write`, `ws.glob`) and the `agents.run()` function for sub-agent management.

**6. Phased Implementation Plan**

This project will be delivered in two distinct, sequential phases.

**Phase 1: MVP with Insecure "Developer Mode"**

*   **Goal:** Establish a functional end-to-end workflow and validate the core service architecture.
*   **Scope:**
    1.  Implement the `AgentKernelService` skeleton in Go with the gRPC API.
    2.  Implement the central dispatcher logic, but the `<python>` path will execute code via a direct, insecure `uv run` subprocess.
    3.  The service will print a prominent `⚠️ INSECURE DEVELOPER MODE ⚠️` warning on startup.
    4.  Refactor the existing `chatty.py` to act as a simple gRPC client.
    5.  Draft the initial version of the new `system.txt` prompt.
*   **Deliverable:** A working prototype that demonstrates the new service-oriented architecture, capable of both direct tool calls and (insecure) code execution.

**Phase 2: Secure Runner Integration**

*   **Goal:** Replace the insecure execution path with the secure, sandboxed solution.
*   **Scope:**
    1.  Build the `SecureRunnerService` in Python, integrating the `LocalPythonExecutor` from SmolAgents.
    2.  Implement the gRPC server and the tool proxying mechanism.
    3.  Modify the `AgentKernelService` to remove the `uv run` subprocess call.
    4.  Integrate the gRPC client in the `AgentKernelService` to call the `SecureRunnerService`.
    5.  Remove the "insecure mode" warning. The default and only execution mode for Python will now be secure.
*   **Deliverable:** A production-ready, secure agentic platform.

**7. Conclusion**

This plan provides a complete and actionable blueprint for transforming Chatty into a next-generation agentic platform. By leveraging a hybrid execution model, a secure-by-default architecture, and proven open-source components, we can deliver a powerful and robust system efficiently. The phased approach ensures we can build momentum with an early MVP while working towards a fully secure and scalable final product.