# /// script
# dependencies = [
#   "mcp[cli]>=1.9.4",
# ]
# ///
from mcp.server.fastmcp import FastMCP

# Create an MCP server
mcp = FastMCP("Demo")

# Add an addition tool
@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

# Add a dynamic greeting resource
@mcp.resource("greeting://{name}")
def get_greeting(name: str) -> str:
    """Get a personalized greeting"""
    return f"Hello, {name}!"

# Add a prompt for code review
@mcp.prompt()
def review_code(code: str) -> str:
    """
    Provide a template for reviewing code.
    
    :param code: The code to review.
    :return: A prompt that asks the LLM to review the code.
    """
    return f"Please review this code:\n\n{code}"

# Start the MCP server
if __name__ == "__main__":
    mcp.run()