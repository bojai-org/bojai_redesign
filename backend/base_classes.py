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

from backend.prompt import PromptComposite, PromptLeaf
from llm_config.router import ask_llm

MAX_TRIES = 3


class Agent(ABC):
    """Abstract base class for a single LLM-backed step.

    ``context`` is a plain string, not a shared mutable object: the pipeline
    runtime sets it to the raw output of whichever predecessor routed into
    this node (see Pipeline._resolve_context in pipeline.py), so it is the
    only channel through which information flows from one node to the next.
    Agents that need to carry structured state (e.g. retrieved resources)
    across multiple hops must encode and decode it from that string — see
    the retrieval agents in agents.py.
    """
    def __init__(self, query, context: str, role: str):
        self.query = query
        self.context = context
        self.role = role

    @abstractmethod
    def pre(self) -> dict:
        """Optional pre-processing before sending the prompt to the LLM."""
        pass

    @abstractmethod
    def specify_output(self) -> str:
        """Specify the expected output type for the LLM response."""
        pass

    def build_prompt(self) -> PromptComposite:
        """Load prompts/{name}.json and build a PromptComposite.

        Extra fields in config (beyond 'name') are prepended as content
        nodes so the LLM sees the dynamic data before the static instructions.
        """
        config = self._prompt_config()  
        config = config | self.pre() 
        config["output"] = self.specify_output()


        root = PromptComposite(id="root")

        for key, value in config.items():
            if key == "name":
                continue
            root.add(PromptLeaf(id=key, text=str(value)))

        return root

    def _prompt_config(self) -> dict:
        return {"role" : self.role, "query" : self.query, "context" : self.context}
    
    @abstractmethod
    def post(self, response: str) -> Any:
        """Optional post-processing of the LLM response before returning to the caller."""
        pass

    @abstractmethod
    def post_fallback(self, response: str) -> Any:
        """Optional post-processing of the LLM response in case of failure."""
        pass

    async def run(self, agent_config: dict) -> Any:
        agent_config["prompt"] = self.build_prompt()
        agent_config.pop("error", None)
        retries = 0
        while True:
            if retries >= MAX_TRIES:
                raise ValueError("Maximum retries reached. No valid response from LLM.")
            response = await ask_llm(agent_config)
            try:
                return self.post(response)
            except (ValueError, TypeError) as e:
                agent_config["error"] = str(e)
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
    

