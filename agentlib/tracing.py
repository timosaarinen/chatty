import logging
import os
from datetime import datetime

LOGS_DIR = "logs"

if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

# Create a unique log file for each run
log_filename = datetime.now().strftime("%Y%m%d_%H%M%S") + ".log"
log_filepath = os.path.join(LOGS_DIR, log_filename)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    handlers=[
        logging.FileHandler(log_filepath, encoding="utf-8"),
        #logging.StreamHandler()  # Also print to console (when --verbose is used)
    ]
)

def disable_litellm_stdout_logs():
    """Get rid of LiteLLM logs from stdout."""
    litellm_logger = logging.getLogger("LiteLLM")
    litellm_logger.handlers.clear()
    litellm_logger.propagate = False
    litellm_logger.setLevel(logging.ERROR)

def log_llm_io(direction: str, content: str):
    """Logs LLM input and output."""
    logging.info(f"{direction.upper()}:\n{content}")

def litellm_logger_fn(model_call_dict):
    """Custom logger function for LiteLLM."""
    logging.info(f"LiteLLM model call details: {model_call_dict}")

disable_litellm_stdout_logs()