# internal_tools.py
import logging

# --- Example Tool Implementations ---
def get_weather(city: str) -> str:
    """Gets the current weather for a specified city."""
    logging.info(f"[Internal Tool] Called get_weather for: {city}")
    if not isinstance(city, str) or not city.strip():
        raise TypeError("City must be a non-empty string.")
    
    city_lower = city.lower()
    if city_lower == "london":
        return "Weather in London: 12°C, cloudy."
    if city_lower == "tokyo":
        return "Weather in Tokyo: 22°C, clear skies."
    
    raise ValueError(f"Weather information for {city} is not available.")

def multiply_numbers(a: int, b: int) -> int:
    """Multiplies two numbers and returns the result."""
    logging.info(f"[Internal Tool] Called multiply_numbers with a={a}, b={b}")
    if not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
        raise TypeError("Both 'a' and 'b' must be numbers.")
    return a * b

# --- Metadata for Internal Tools ---
INTERNAL_TOOLS_METADATA = [
    {
        "name": "get_weather",
        "description": "Get the current weather for a specific city. Supported cities are 'London' and 'Tokyo'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "The city to get the weather for."}
            },
            "required": ["city"]
        },
        "outputSchema": {
            "type": "string"
        }
    },
    {
        "name": "multiply_numbers",
        "description": "Multiplies two numbers together.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "The first number."},
                "b": {"type": "number", "description": "The second number."}
            },
            "required": ["a", "b"]
        },
        "outputSchema": {
            "type": "integer"
        }
    }
]

# Maps the tool name (string) to the callable function.
INTERNAL_TOOL_IMPLEMENTATIONS = {
    "get_weather": get_weather,
    "multiply_numbers": multiply_numbers,
}