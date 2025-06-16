# internal/prompt_manager.py
import os
import logging
from pathlib import Path

class PromptManager:
    """Manages loading and accessing prompt templates from a directory."""

    def __init__(self, prompt_directory: str = "prompts"):
        self.prompt_dir = Path(prompt_directory)
        self.prompts = {}
        self.load()

    def load(self):
        """
        Loads or reloads all .txt prompt files from the specified directory.
        The name of the prompt is the filename without the .txt extension.
        """
        self.prompts.clear()
        if not self.prompt_dir.is_dir():
            logging.warning(f"Prompt directory '{self.prompt_dir}' not found. No prompts will be loaded.")
            return

        for prompt_file in self.prompt_dir.glob("*.txt"):
            try:
                prompt_name = prompt_file.stem
                with open(prompt_file, "r", encoding="utf-8") as f:
                    self.prompts[prompt_name] = f.read()
                logging.info(f"Loaded prompt '{prompt_name}' from {prompt_file}")
            except IOError as e:
                logging.error(f"Failed to read prompt file {prompt_file}: {e}")
        
        if not self.prompts:
            logging.warning(f"No prompts were loaded from '{self.prompt_dir}'.")

    def get(self, name: str) -> str | None:
        """
        Retrieves a loaded prompt template by its name.
        
        Args:
            name: The name of the prompt (e.g., 'system').
        
        Returns:
            The prompt template string, or None if not found.
        """
        return self.prompts.get(name)
