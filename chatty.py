# chatty.py
import argparse
from rich.console import Console
from agentlib.agent import Agent
from agentlib.manager import AgentManager
from agentlib.tools import get_tools
from prompts.system import get_system_prompt

def confirm_action(tool_name: str, **kwargs) -> bool:
    """Asks the user to confirm a high-risk action."""
    console = Console()
    console.print(f"[bold red]High-risk action proposed:[/bold red]")
    console.print(f"  Tool: {tool_name}")
    console.print(f"  Arguments: {kwargs}")
    confirm = console.input("Execute? [y/N] ")
    return confirm.lower() == "y"

def main():
    parser = argparse.ArgumentParser(description="Chatty - A code AI agent.")
    parser.add_argument("--model", type=str, default="ollama/gemma3:1b", help="The model to use for the agent.")
    parser.add_argument("--temperature", type=float, default=0.7, help="The temperature for the LLM.")
    args = parser.parse_args()

    console = Console()
    # TODO: proper startup logo: console.print("[bold green]**Chatty**[/bold green]")

    agent = Agent(
        instructions=get_system_prompt(),
        tools=get_tools(),
        model_config={"model": args.model, "temperature": args.temperature}
    )

    manager = AgentManager(agent, confirm_callback=confirm_action)

    while True:
        try:
            user_input = console.input("[bold yellow]> [/bold yellow]")
            if user_input.lower() in ["exit", "quit"]:
                break
            
            response = manager.run(user_input)
            console.print(f"\n[bold blue]Chatty:[/bold blue]\n{response}\n")

        except (KeyboardInterrupt, EOFError):
            console.print("\nExiting gracefully...")
            break

if __name__ == "__main__":
    main()
