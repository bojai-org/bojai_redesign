"""
BojAI Build — Agent and Pipeline Abstractions

This module is part of the `build` layer and defines the abstract base classes
that all LLM-driven construction components inherit from. It sits one level above
the `architecture` layer: while architecture defines runtime data contracts, this
module defines how components are *built* using an LLM.

Components defined here:

- Agent:
    Abstract base for a single LLM-backed step. Subclasses implement
    process_response() to validate and transform the raw LLM string into a typed
    result. Agent.run() handles the full retry loop: it builds the prompt via
    build_prompt(), calls ask_llm(), passes the response to process_response(),
    and injects any error back into the prompt on failure. Retries up to
    MAX_TRIES=3 before raising ValueError.

- Pipeline:
    Abstract base for an ordered sequence of agents that together produce a
    single output. Subclasses implement run() and compose agents internally.
    Pipelines own the LLM config and pass it down to each agent they create.
"""


from abc import ABC, abstractmethod
from typing import Any, List
import json
import re
from pathlib import Path, PurePosixPath

from build.prompt import PromptComposite, PromptLeaf
from llm_config.router import ask_llm

MAX_TRIES = 3


class Agent(ABC):

    def __init__(self, LLM_config: dict):
        self.LLM_config = LLM_config

    def build_prompt(self, config: dict) -> PromptComposite:
        """Load prompts/{name}.json and build a PromptComposite.

        Extra fields in config (beyond 'name') are prepended as content
        nodes so the LLM sees the dynamic data before the static instructions.
        """
        name = config["name"]
        path = Path(__file__).parent.parent / "prompts" / f"{name}.json"

        with open(path) as f:
            data = json.load(f)

        root = PromptComposite(id="root")

        for key, value in config.items():
            if key == "name":
                continue
            root.add(PromptLeaf(id=key, text=str(value)))

        for section in data:
            composite = PromptComposite(id=section["id"])
            for title in section["titles"]:
                composite.add(PromptLeaf(id=title["id"], text=title["text"]))
            root.add(composite)

        return root

    def _prompt_config(self, data_description: str | None = None) -> dict:
        base = {"name": self.LLM_config["name"]}
        if data_description is not None:
            base["Pipeline data form description"] = data_description
        return base
        

    @abstractmethod
    def process_response(self, response: str) -> Any:
        pass

    async def run(self) -> Any:
        self.LLM_config["prompt"] = self.build_prompt(self._prompt_config())
        self.LLM_config.pop("error", None)
        retries = 0
        while True:
            if retries >= MAX_TRIES:
                raise ValueError("Maximum retries reached. No valid response from LLM.")
            response = await ask_llm(self.LLM_config)
            try:
                return self.process_response(response)
            except (ValueError, TypeError) as e:
                self.LLM_config["error"] = str(e)
                retries += 1

    def _find_json(self, text: str) -> Any:
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))

        raise ValueError("No valid JSON found in response")

    def _confirm_paths(self, paths: list[str], dir_tree: dict) -> None:
        if not isinstance(paths, list):
            raise TypeError("paths must be a list of strings")

        root = next(iter(dir_tree.keys()))
        root_normalized = root.replace("\\", "/").rstrip("/")

        for path in paths:
            if not isinstance(path, str):
                raise TypeError(f"Expected path to be a string, got {type(path)}: {path}")

            path_normalized = path.replace("\\", "/").rstrip("/")

            if not path_normalized.startswith(root_normalized):
                raise ValueError(
                    f"Invalid path: {path}. It must start with root: {root_normalized}"
                )

            relative_path = path_normalized[len(root_normalized):].lstrip("/")

            current = dir_tree[root]

            if not relative_path:
                continue

            for part in PurePosixPath(relative_path).parts:
                if part in ("", "."):
                    continue

                if not isinstance(current, dict):
                    raise ValueError(
                        f"Invalid path: {path}. '{part}' is inside a file, not a folder."
                    )

                if part not in current:
                    raise ValueError(
                        f"Invalid path: {path}. Missing component: '{part}'."
                    )

                current = current[part]

class SimpleAgent(Agent):
    """Reusable base for single-shot LLM calls with a plain text prompt.
    Pass the full prompt as a string; override process_response() for structured output."""

    def __init__(self, name: str, prompt: str, LLM_config: dict):
        super().__init__(LLM_config)
        self.name = name
        self._plain_prompt = prompt

    def build_prompt(self, config: dict) -> PromptComposite:
        root = PromptComposite(id="root")
        root.add(PromptLeaf(id="content", text=self._plain_prompt))
        return root

    def _prompt_config(self) -> dict:
        return {"name": self.name}

    def process_response(self, response: str) -> str:
        return response


class Pipeline(ABC):

    def __init__(self, LLM_config: dict):
        self.LLM_config = LLM_config

    @abstractmethod
    async def run(self) -> Any:
        pass

    async def _select_code_files(self, choice_name, decision_name) -> List[str]:
        from build.agents import FileChoiceAgent, DecisionAgent
        choice_agent = FileChoiceAgent(choice_name, self.address, self.LLM_config, self.context)
        selected_files = await choice_agent.run()  
        decision_agent = DecisionAgent(decision_name, selected_files, choice_agent.dir_tree, self.LLM_config, self.context)
        confirmed_files = await decision_agent.run()   
        return confirmed_files
