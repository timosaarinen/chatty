```
╭───────────────────────── Chatty - Code Agent ------─────────────────────────╮
│                                                                             │
│              ██████╗██╗  ██╗ █████╗ ████████╗████████╗██╗   ██╗             │
│             ██╔════╝██║  ██║██╔══██╗╚══██╔══╝╚══██╔══╝╚██╗ ██╔╝             │
│              ██║     ███████║███████║   ██║      ██║    ╚████╔╝             │
│              ██║     ██╔══██║██╔══██║   ██║      ██║     ╚██╔╝              │
│               ╚██████╗██║  ██║██║  ██║   ██║      ██║      ██║              │
│                ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝      ╚═╝      ╚═╝              │
│                                                                             │
╰────────── A Local-First, Code-Executing AI Agent Powered by Ollama ─────────╯
```

`chatty` is a minimalist, local-first terminal AI assistant for developers. It runs code in your environment, connects to local [Ollama](https://ollama.com/) or cloud models (via LiteLLM), and can access tools exposed via the Model Context Protocol (MCP).


## Features

- **Local-first:** No cloud by default; everything runs on your machine.
- **Code execution:** Lets an LLM write and run Python code (in a sandbox if Docker is used).
- **Tooling:** Accesses both built-in functions and external MCP tools.
- **Extensible:** Plug in more tools at runtime via MCP.
- **Hot-Reloading:** MCP tools and prompts can be reloaded at runtime.

## Requirements

- [**Docker**](https://www.docker.com/): Recommended for sandboxed, secure execution.
- [**Ollama**](https://ollama.com/): Must be installed and running if using local models.

> **Docker is strongly recommended for security and easy setup.**

`chatty` executes Python code generated by an LLM. While the recommended Docker setup provides a strong sandbox, be aware that the agent can interact with external services and local files within its container.

## How It Works

The core concept is to empower an LLM to write and execute Python code. `chatty` uses `uv run` to execute this code, which creates a temporary virtual environment for dependency management. For true security and filesystem isolation, **running `chatty` inside the provided Docker container is the recommended and safest method.**

The agent provides a special `Tools` class that can be used within the generated code. This class acts as a proxy, forwarding tool calls to either:
1.  **Internal Tools:** Built-in Python functions defined within the agent's code.
2.  **MCP Servers:** External, hot-pluggable [Model Context Protocol (MCP)](https://github.com/modelcontextprotocol/modelcontextprotocol) servers that expose their own tools. This allows `chatty`'s capabilities to be extended dynamically without modifying its core logic.

## Installation & Usage (Docker Recommended)

Running `chatty` inside a Docker container is the safest way to use the agent. It provides a strong security sandbox for code execution and MCP servers.

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/timosaarinen/chatty.git
    cd chatty
    ```
2.  **Build the Docker image:**
    The provided script handles building the `chatty` image.
    ```bash
    scripts/build.sh
    ```

### Running the Agent

Use the `run.sh` script to start an interactive session. You must provide a model name. The script ensures the container can connect to your host's Ollama instance.

```bash
# Run with a specific model
scripts/run.sh codellama:latest

# Pass additional arguments to chatty.py
scripts/run.sh qwen2.5-coder:7b --mcp mcp-config/demo-only.json --debug
```

### Development Workflow

For active development, use `dev.sh` to start a long-running container with your local project directory mounted.

1.  **Start the development container:**
    ```bash
    scripts/dev.sh
    ```
2.  **Get a shell inside the container:**
    ```bash
    scripts/exec.sh
    ```
3.  **Run `chatty` from inside the container shell:**
    From this shell, you can run the agent as you would locally.
    ```bash
    # Inside the container from exec.sh
    uv run chatty.py --model <your-model>
    ```

## Local Usage (Without Docker)

You can run `chatty` directly on your host if you have `uv` installed.

**⚠️ Security Warning**: This method does not provide a security sandbox. MCP tool calls and the Python code generated by the LLM will be executed directly on your machine with the same permissions as your user account. This is **not recommended** unless you understand the risks.

### Requirements

*   [**uv**](https://github.com/astral-sh/uv): For running the script and managing dependencies.
*   [**Ollama**](https://ollama.com/): Must be installed and running if using local models.

### Usage

You must specify a model for inference using either `--model` for a local Ollama model or `--litellm-model` for an external one.

```bash
# Example using a local Ollama model
uv run chatty.py --model codellama:latest

# Example using an external model via LiteLLM
uv run chatty.py --litellm-model openrouter/anthropic/claude-3-opus
```

## Using External Models (LiteLLM)

`chatty` can use [LiteLLM](https://www.litellm.ai/) to connect to hundreds of LLM providers, including OpenAI, Anthropic, Google Gemini, OpenRouter, and more.

To use an external model, provide the `--litellm-model` argument. The value should be a model string in LiteLLM's format, typically `provider/model_name`.

```bash
# Example using OpenAI's GPT-4.1. The --model argument is not needed.
scripts/run.sh --litellm-model openai/gpt-4.1

# Example using OpenRouter to access DeepSeek R1 (free)
scripts/run.sh --litellm-model openrouter/deepseek/deepseek-r1-0528:free
```

### API Key Configuration

To use commercial model providers, you must provide an API key. Set the appropriate environment variable for your chosen provider **before** running `chatty`. LiteLLM automatically detects these variables.

Common examples:
- **OpenAI:** `export OPENAI_API_KEY="sk-..."`
- **Anthropic:** `export ANTHROPIC_API_KEY="..."`
- **Google:** `export GEMINI_API_KEY="..."`
- **OpenRouter:** `export OPENROUTER_API_KEY="..."`

You can pass environment variables to the Docker container using the `-e` flag. Because the `scripts/run.sh` helper does not forward environment variables, you must call `docker run` directly.

```bash
docker run --rm \
  --add-host=host.docker.internal:host-gateway \
  -it \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -v "$(pwd)":/home/developer/chatty:rw \
  "chatty" \
    --litellm-model "openai/gpt-4o" \
    --ollama http://host.docker.internal:11434
```
