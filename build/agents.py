"""
BojAI Build — Data Pipeline Agents

This module is part of the `build` layer and provides the concrete agent
implementations used by the data pre-processing and post-processing pipelines.
Each agent handles one decision step: selecting files, confirming selections,
or extracting and sanitizing code.

All agents inherit from Agent (build.base_classes) and implement
process_response() to parse and validate the LLM's reply.

Agents defined here:

- ChoiceAgent:
    Base for agents that operate over a directory tree. Accepts a list of
    dot-separated address strings (e.g. "src.data.train.csv") and builds a
    nested dict tree for path validation.

- DataChoiceAgent(ChoiceAgent):
    Asks the LLM to select a list of file paths from the directory tree.
    process_response() parses a JSON array and validates every path against
    the tree before returning.

- CodeExtractionAgent(Agent, CodeValidator):
    Given the full source of one or more files, asks the LLM to extract a
    clean build() function. process_response() validates the extracted code
    through all six AST guards in CodeValidator before returning the sanitized
    source string.

- DecisionAgent(Agent):
    Asks the LLM to review a list of candidates and confirm which ones to
    keep (true/false per entry). process_response() parses a JSON object
    and filters by the boolean values.

- HyperparameterAgent(Agent):
    Reads a confirmed list of file paths, concatenates their contents, and
    asks the LLM to extract all hyperparameters. process_response() parses
    a JSON object and validates that every value is str, int, float, or bool
    before returning the typed dict.
"""
import json
from build.base_classes import Agent, SimpleAgent
from build.data.utils import CodeValidator
from pathlib import Path
MAX_TRIES = 5

class ChoiceAgent(Agent):
    """Base class for choice agents."""

    def __init__(self, name, address: list, LLM_config: dict, data_description: str | None = None):
        super().__init__(LLM_config)
        self.address = address
        self.dir_tree = self._build_directory_tree()
        self.name = name
        self.data_description = data_description

    def _build_directory_tree(self) -> dict:
        root = Path(self.address)

        if not root.exists():
            raise ValueError(f"Path does not exist: {root}")

        def build(path: Path):
            if path.is_file():
                return None

            return {
                child.name: build(child)
                for child in path.iterdir()
            }

        return {
            str(root).replace("\\", "/"): build(root)
        }
    def _prompt_config(self) -> dict:
        base = super()._prompt_config(self.data_description)
        base["name"] = self.name
        base["dir_tree"] = str(self.dir_tree)
        return base

    def process_response(self, response: str) -> list[str]:
        raise NotImplementedError


class FileChoiceAgent(ChoiceAgent):
    """Step 1 — scans the directory tree and selects candidate files."""

    def process_response(self, response: str) -> list[str]:
        answer = self._find_json(response)
        self._confirm_paths(answer, self.dir_tree)
        return answer


class CodeExtractionAgent(Agent, CodeValidator):
    def __init__(self, name, long_code: str, LLM_config: dict, data_description: str | None = None):
        super().__init__(LLM_config)
        self.long_code = long_code
        self.name = name
        self.data_description = data_description

    def _prompt_config(self) -> dict:
        base = super()._prompt_config(self.data_description)
        base["name"] = self.name
        base["long_code"] = self.long_code
        return base

    def process_response(self, response: str) -> list[str]:
        answer = self._find_json(response)
        code = answer.get("code")
        if not isinstance(code, str):
            raise TypeError(f"Expected 'code' to be a string, got {type(code)}")
        return self.confirm_code({"code": code})

    
class DecisionAgent(Agent):
    """Reviews a list of candidates and confirms which ones to keep (true/false per entry)."""

    def __init__(self, name, selected_files: list[str], dir_tree: dict, LLM_config: dict, data_description: str | None = None):
        super().__init__(LLM_config)
        self.selected_files = selected_files
        self.dir_tree = dir_tree
        self.name = name
        self.data_description = data_description

    def _prompt_config(self) -> dict:
        base = super()._prompt_config(self.data_description)
        base["name"] = self.name
        base["to_confirm"] = json.dumps(self.selected_files)
        return base

    def process_response(self, response: str) -> list[str]:
        confirmation = self._find_json(response)
        print(f"Confirmation received: {confirmation}")
        return self._process_confirmation(confirmation)

    def _process_confirmation(self, confirmation: dict[str, bool] | bool) -> list[str]:
        selected = []
        print(f"Processing confirmation: {confirmation}")
        if isinstance(confirmation, bool):
            return confirmation
        else:
            for path, keep in confirmation.items():
                self._confirm_paths([path], self.dir_tree)
                if not isinstance(keep, bool):
                    raise TypeError(f"Decision for '{path}' must be a boolean, got {type(keep)}")
                if keep:
                    selected.append(path)
        return selected


class DataDescriptionAgent(SimpleAgent):
    """Sends a sample of input (and optional output) to the LLM and returns a plain-text description of the data."""

    def __init__(self, input: list, LLM_config: dict, output: list | None = None):
        samples_in = input[:3]
        samples_out = output[:3] if output is not None else None
        prompt = self._build_prompt(samples_in, samples_out)
        super().__init__("data_description", prompt, LLM_config)

    @staticmethod
    def _build_prompt(samples_in: list, samples_out: list | None) -> str:
        lines = [
            "You are given samples from a machine learning dataset.",
            "Describe the data in two to four sentences: what it represents, its format, types, and structure.",
            "",
            f"Input samples:\n{samples_in}",
        ]
        if samples_out is not None:
            lines.append(f"\nOutput samples:\n{samples_out}")
        lines.append("\nDescription:")
        return "\n".join(lines)


class HyperparameterAgent(Agent):
    """Reads confirmed files and extracts hyperparameters as a typed dict."""

    def __init__(self, name: str, files: list[str], LLM_config: dict, data_description: str | None = None):
        super().__init__(LLM_config)
        self.name = name
        self.files = files
        self.data_description = data_description

    def _read_files(self) -> str:
        parts = []
        for path in self.files:
            with open(path) as f:
                parts.append(f"# {path}\n{f.read()}")
        return "\n\n".join(parts)

    def _prompt_config(self) -> dict:
        base = super()._prompt_config(self.data_description)
        base["name"] = self.name
        base["file_contents"] = self._read_files()
        return base

    def process_response(self, response: str) -> dict[str, str | int | float | bool]:
        answer = self._find_json(response)
        if not isinstance(answer, dict):
            raise TypeError(f"Expected a JSON object, got {type(answer)}")
        for key, val in answer.items():
            if not isinstance(val, (str, int, float, bool)):
                raise TypeError(
                    f"Value for '{key}' must be str, int, float, or bool, got {type(val)}"
                )
        return answer


