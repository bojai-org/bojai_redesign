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

    ``state`` is a dict shared by every node in one pipeline run (see
    Pipeline.run in pipeline.py): the runtime hands the SAME dict to each
    node in turn, patched onto ``self.state`` immediately before that node
    executes. It is a namespaced blackboard, not a free-for-all -- a node
    may read any key it likes, but the runtime only ever copies a key out of
    a node's *result* and into shared state if that node's class declares it
    in ``WRITES``. This is what keeps a RAG hop's retrieved passages (the
    "context" key) from ever being confused with another node's final reply
    (the "answer" key) or a router's chosen option (the "decision" key): a
    node that wants "the retrieved context" reads state["context"] itself in
    pre() rather than being handed "whatever the previous node returned" and
    guessing at what it means.

    ``WRITES`` is empty by default (nothing is written to shared state); a
    subclass that produces content another node should be able to read
    declares the key(s) it owns, e.g. ``WRITES = frozenset({"context"})`` for
    a retrieval agent. See Pipeline._collect_state_writes for how a node's
    raw result is filtered down to just those keys before being merged in --
    and PipelineRuntimeError raised if a result carries a namespaced key
    (see pipeline._STATE_KEYS) the node isn't declared to own.

    Some agents also take a plain, per-instance ``context`` constructor
    argument (e.g. the safety barrier agents' fixed deployment description).
    That is unrelated to shared ``state`` -- it is static configuration set
    once and never touched by the pipeline runtime, not pipeline-flowing data.
    """
    WRITES: frozenset[str] = frozenset()

    def __init__(self, query, state: dict | None, role: str):
        self.query = query
        self.state: dict[str, Any] = state if state is not None else {}
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
        """Base prompt fields common to every agent.

        Deliberately does NOT include any shared-state key (e.g. "context")
        -- unlike ``self.query``/``self.role``, shared state is namespaced
        and agent-specific, so it is each agent's own pre() that decides
        which key(s) of self.state (if any) belong in its prompt, and under
        what field name.
        """
        return {"role": self.role, "query": self.query}
    
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
    

