# internal/ui.py
import json
import sys
import textwrap
from typing import List, Dict, Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.prompt import Confirm
from rich.table import Table
from rich.text import Text
from rich.style import Style

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

    def display_splash_screen(self):
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
        self.console.print("Use /history, /tools, or /proxy for info. Type 'exit' or 'quit' to end.", justify="center")
        self.console.print()

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

    def display_assistant_response_start(self):
        """Prints the prefix for the assistant's response stream."""
        self.console.print(Text("🤖 ASSISTANT: ", style=self.theme["assistant"]), end="")

    def display_assistant_stream_chunk(self, text: str):
        """Prints a chunk of the assistant's streaming response."""
        self.console.print(text, end="")

    def display_assistant_response_end(self):
        """Prints a newline to conclude the assistant's response."""
        self.console.print()

    def confirm_tool_execution(self, code: str) -> bool:
        """Displays proposed tool code and asks for user confirmation."""
        self.console.print()
        syntax = Syntax(code, "python", theme="monokai", line_numbers=True, word_wrap=True)
        panel = Panel(
            syntax,
            title="[bold yellow]🤖 Assistant Proposes Tool Code[/]",
            border_style="yellow",
            expand=False
        )
        self.console.print(panel)
        return Confirm.ask("Execute this Python code?", console=self.console, default=True)

    def display_tool_output(self, execution_result: Dict[str, Optional[str]]) -> str:
        """Displays the output of a tool execution in formatted panels."""
        output_panels = []
        if execution_result.get('stdout'):
            output_panels.append(Panel(Text(execution_result['stdout'], style="green"), title="STDOUT", border_style="green", expand=False))
        if execution_result.get('stderr'):
            output_panels.append(Panel(Text(execution_result['stderr'], style="red"), title="STDERR", border_style="red", expand=False))
        if execution_result.get('error'):
             output_panels.append(Panel(Text(str(execution_result['error']), style="bold red"), title="SYSTEM ERROR", border_style="bold red", expand=False))

        llm_output_parts = []
        if execution_result.get('stdout'): llm_output_parts.append(f"STDOUT:\n{execution_result['stdout']}")
        if execution_result.get('stderr'): llm_output_parts.append(f"STDERR:\n{execution_result['stderr']}")
        if execution_result.get('error'): llm_output_parts.append(f"SYSTEM_ERROR: {execution_result['error']}")
        full_output_for_llm = "\n\n".join(llm_output_parts)
        
        self.console.print()
        self.console.rule("[bold blue]🛠️ TOOL OUTPUT", style=self.theme["separator"])
        if not output_panels:
             self.console.print("Script executed with no output.")
             full_output_for_llm = "Script executed with no output."
        else:
            for panel in output_panels:
                self.console.print(panel)
        self.console.rule(style=self.theme["separator"])
        
        return full_output_for_llm

    def display_history(self, history: List[Dict[str, str]]):
        """Displays the conversation history."""
        self.console.rule("[bold]Conversation History", style=self.theme["separator"])
        # Skip the system prompt for user display
        for message in history[1:]:
            style = self.theme["user"] if message["role"] == "user" else self.theme["assistant"]
            title = "👤 USER" if message["role"] == "user" else "🤖 ASSISTANT"
            self.console.print(Panel(message["content"], title=title, border_style=style, expand=False))
        self.console.rule(style=self.theme["separator"])

    def display_tools(self, all_tools_metadata: List[Dict[str, Any]]):
        """Displays available tools as a JSON object."""
        self.console.rule("[bold]Available Tools", style=self.theme["separator"])
        if not all_tools_metadata:
            self.console.print("No tools are currently available.")
        else:
            self.console.print(Syntax(json.dumps(all_tools_metadata, indent=2), "json", theme="monokai", word_wrap=True))
        self.console.rule(style=self.theme["separator"])

    def display_proxy_code(self, proxy_code: str):
        """Displays the generated tools.py proxy code."""
        self.console.rule("[bold]Generated tools.py Proxy Content", style=self.theme["separator"])
        self.console.print(Syntax(proxy_code, "python", theme="monokai", line_numbers=True, word_wrap=True))
        self.console.rule(style=self.theme["separator"])

    def new_turn(self):
        """Prints a separator to denote a new turn in the conversation."""
        self.console.print(self.console.rule(style=self.theme["separator"]))
