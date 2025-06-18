# internal/ui.py
import json
import sys
import textwrap
from typing import List, Dict, Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text
from rich.style import Style

from .agent_manager import AgentStatus


class TerminalUI:
    """Handles all terminal user interface rendering using the `rich` library."""

    def __init__(self, console: Console):
        self.console = console
        self.theme = {
            "user": Style(color="cyan", bold=True),
            "assistant": Style(color="green", bold=True),
            "tool_header": Style(color="yellow", bold=True),
            "tool_output": Style(color="bright_black"),
            "separator": Style(color="blue", dim=True),
        }
        self._last_turn_status = None

    def display_splash_screen(self, auto_accept_enabled: bool = False):
        """Displays an ASCII art logo and welcome message."""
        logo = textwrap.dedent("""
             ██████╗██╗  ██╗ █████╗ ████████╗████████╗██╗   ██╗
            ██╔════╝██║  ██║██╔══██╗╚══██╔══╝╚══██╔══╝╚██╗ ██╔╝
            ██║     ███████║███████║   ██║      ██║    ╚████╔╝ 
            ██║     ██╔══██║██╔══██║   ██║      ██║     ╚██╔╝  
            ╚██████╗██║  ██║██║  ██║   ██║      ██║      ██║   
             ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝      ╚═╝      ╚═╝   
        """)
        panel = Panel(
            Text(logo, style="bold blue", justify="center"),
            title="[bold]Chatty[/] - Local Code Agent",
            subtitle="[dim]Powered by Ollama & MCP[/dim]",
            border_style="dim blue"
        )
        self.console.print(panel)
        self.console.print("Type '/help' for a list of commands. Type 'exit' or 'quit' to end.", justify="center")
        if auto_accept_enabled:
            self.console.print("[yellow bold]⚠️ Auto-accepting all tool code executions.[/yellow bold]", justify="center")
        self.console.print()

    def display_agent_activity(self, agent_id: str, role: str, message: str):
        """Displays the status of a sub-agent's activity."""
        self.console.print(f"🔩 [Agent [bold cyan]{role}[/] ({agent_id})] {message}", style="dim")

    def display_help(self):
        """Displays the help message with available commands."""
        table = Table(show_header=False, box=None, expand=False)
        table.add_column("Command", style="cyan", no_wrap=True)
        table.add_column("Description")

        commands = {
            "/help": "Show this help message.",
            "/clear": "Clear the current conversation history.",
            r"/reload \[prompts|mcp]": "Reload prompts, MCP servers, or both from disk.",
            "/history": "Show the formatted conversation history.",
            "/history-raw": "Show the raw JSON conversation history for the LLM.",
            "/tools": "Show available tools as a JSON object.",
            "/proxy": "Show the generated 'tools.py' proxy code.",
            "exit / quit": "Exit the application."
        }

        for cmd, desc in commands.items():
            table.add_row(f"[bold]{cmd}[/bold]", desc)

        panel = Panel(
            table,
            title="[bold]Available Commands[/]",
            border_style="dim blue",
            expand=False
        )
        self.console.print(panel)

    def display_info(self, message: str):
        self.console.print(f"[*] {message}", style="dim")

    def display_warning(self, message: str):
        self.console.print(f"[bold yellow]⚠️ WARNING:[/] {message}")

    def display_error(self, message: str):
        self.console.print(f"[bold red]❌ ERROR:[/] {message}")

    def display_ollama_models(self, models: List[Dict[str, Any]]):
        """Displays available Ollama models in a formatted table."""
        if not models:
            self.console.print("\n[yellow]Could not find any models installed in Ollama.[/yellow]")
            return

        table = Table(title="\nAvailable Ollama Models", style="cyan", title_justify="left", expand=False)
        table.add_column("Model Name", style="green", no_wrap=True)
        table.add_column("Size (GB)", justify="right")
        table.add_column("Modified", style="magenta")

        for model in models:
            size_gb = f"{model.get('size', 0) / 1e9:.2f}"
            modified_at = model.get('modified_at', 'N/A').split('T')[0]
            table.add_row(model['name'], size_gb, modified_at)
        
        self.console.print(table)

    def prompt_user(self) -> str:
        """Prompts the user for input."""
        return self.console.input(Text("👤 USER: ", style=self.theme["user"]))

    def display_final_answer(self, agent_id: str, role: str, text: str):
        """Displays a final text answer from an agent."""
        if agent_id == "main":
            self.console.print(Text("🤖 ASSISTANT: ", style=self.theme["assistant"]), end="")
            self.console.print(text)
        else:
            panel = Panel(text, title=f"🤖 Sub-Agent Output ({role} / {agent_id})", border_style="green", expand=False)
            self.console.print(panel)

    def confirm_action(self, agent_id: str, role: str, action_type: str, details: str, auto_accept: bool) -> bool:
        """Displays a proposed action (tool call or code) and asks for user confirmation."""
        self.console.print()
        
        title_map = {
            "CODE_EXECUTION": "🤖 Assistant Proposes Code Execution",
            "TOOL_CALL": "🤖 Assistant Proposes Tool Call"
        }
        lexer_map = {
            "CODE_EXECUTION": "python",
            "TOOL_CALL": "json"
        }
        
        title = title_map.get(action_type, "🤖 Assistant Proposes Action")
        lexer = lexer_map.get(action_type, "text")

        syntax = Syntax(details, lexer, theme="monokai", line_numbers=True, word_wrap=True)
        panel = Panel(
            syntax,
            title=f"[bold yellow]{title}[/] [dim]({role} / {agent_id})[/dim]",
            border_style="yellow",
            expand=False
        )
        self.console.print(panel)

        if auto_accept:
            self.console.print("Auto-accepting action...", style="dim")
            return True

        # In a real CLI, we would use Prompt.ask here. For now, we auto-accept.
        # This can be expanded to re-introduce the y/n/a prompt.
        return True

    def display_tool_output(self, result: Dict[str, Any]):
        """Displays the output of a single tool execution."""
        self.console.print()
        self.console.rule("[bold blue]🛠️ TOOL OUTPUT", style=self.theme["separator"])

        status = result.get("status", "error")
        if status == "success":
            output = result.get('output', 'Tool executed with no output.')
            if isinstance(output, dict) or isinstance(output, list):
                output_str = json.dumps(output, indent=2)
                p = Panel(Syntax(output_str, "json", theme="monokai"), title="SUCCESS (JSON)", border_style="green")
            else:
                p = Panel(str(output), title="SUCCESS", border_style="green")
        else:
            error_msg = result.get('error', 'Unknown error.')
            p = Panel(Text(str(error_msg), style="red"), title="ERROR", border_style="red")
        
        self.console.print(p)
        self.console.rule(style=self.theme["separator"])

    def new_turn_if_needed(self, agent_status: AgentStatus):
        """Prints a separator if the last turn ended and a new one is beginning."""
        is_new_turn = (self._last_turn_status != AgentStatus.DONE and agent_status == AgentStatus.DONE)
        self._last_turn_status = agent_status
        if is_new_turn:
            self.console.print(self.console.rule(style=self.theme["separator"]))
