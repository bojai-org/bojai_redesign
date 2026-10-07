"""
BojAI Build — New Agent Builder

Lets a caller (eventually a UI) define a brand-new Agent subclass by
supplying the source of its four required methods -- ``pre``,
``specify_output``, ``post``, ``post_fallback`` -- as plain text, instead of
writing a class in agents.py by hand. This is backend-only for now: there is
no HTTP surface or registry wiring yet, just the AgentSpec -> validated
source -> compiled class pipeline.

Components defined here:

- AgentSpec:
    The plain data a caller provides -- a name, a role (used as the built
    agent's system-prompt framing, same as every other Agent subclass), the
    four method bodies as text, and the shared-state key(s) (``writes``) the
    built agent is allowed to write. See base_classes.Agent's docstring and
    pipeline.py's Pipeline._collect_state_writes for what WRITES means and
    how it's enforced at pipeline-run time -- a hand-authored agent is bound
    by exactly the same "only agents that declare a key may write it" rule
    as RAG_Agent, Direct_Answer_Agent, and everything else in agents.py.

- NewAgentBuilder:
    Abstract base. Subclasses decide *where* each method's source text comes
    from (``_process_full_agent``); every subclass's output is validated the
    same way, through CodeValidator (code_safety.py), before compiler() ever
    turns it into a live class. A future subclass might, say, ask an LLM to
    generate the four methods from a natural-language description -- this
    module only implements the direct case.

- TextNewAgentBuilder(NewAgentBuilder):
    The method source is already plain Python text supplied as-is (e.g.
    pasted or written directly into a UI code editor) -- no LLM extraction
    step runs first. Its only job is running each method through
    CodeValidator's AST guards.

- compiler(builder) -> type[Agent]:
    Validates every method on *builder*, compiles the sanitized source, and
    returns a real Agent subclass -- usable exactly the way any other
    agents.py class is: register it in an AGENT_REGISTRY (see app.py) under
    whatever type name the caller wants, and reference that name from a
    pipeline node's "type".
"""

from __future__ import annotations

import builtins
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from base_classes import Agent
from code_safety import CodeValidationError, CodeValidator

# Every method name accepted from user-submitted source, and how many
# parameters (beyond `self`) its function definition must declare -- must
# match exactly what base_classes.Agent's abstract methods, and Agent.run(),
# actually call each one with.
_METHOD_PARAM_COUNTS: dict[str, int] = {
    "pre": 0,
    "specify_output": 0,
    "post": 1,
    "post_fallback": 1,
}

# A conservative, fixed set of builtins available inside a compiled agent's
# methods -- everything needed to do ordinary text/JSON/dict work, nothing
# with any filesystem, process, network, or introspection capability. Real
# `__import__` is included so a validated `import re`-shaped statement (see
# code_safety.ALLOWED_IMPORTS) actually works at call time; CodeValidator
# already rejects both disallowed import targets and any direct call to
# `__import__` itself, so this does not reopen that door.
_SAFE_BUILTIN_NAMES = (
    "len", "range", "enumerate", "zip", "map", "filter", "sorted", "reversed",
    "min", "max", "sum", "abs", "round", "divmod", "pow",
    "str", "int", "float", "bool", "list", "dict", "tuple", "set", "frozenset",
    "isinstance", "issubclass", "type",
    "ValueError", "TypeError", "KeyError", "IndexError", "AttributeError",
    "StopIteration", "Exception", "RuntimeError", "ArithmeticError", "ZeroDivisionError",
    "__import__",
)
_SAFE_BUILTINS: dict[str, Any] = {name: getattr(builtins, name) for name in _SAFE_BUILTIN_NAMES}
_SAFE_BUILTINS.update({"True": True, "False": False, "None": None})


@dataclass
class AgentSpec:
    name: str
    role: str

    pre: Optional[str] = None
    post: Optional[str] = None
    specify_output: Optional[str] = None
    post_fallback: Optional[str] = None

    writes: set[str] = field(default_factory=set)


class NewAgentBuilder(ABC):
    """Validates the four method bodies in an AgentSpec into ready-to-compile source."""

    def __init__(self, spec: AgentSpec, validator: CodeValidator | None = None):
        self.spec = spec
        self.validator = validator or CodeValidator()
        self.processed_code: dict[str, str] = {}

    def process_pre(self) -> None:
        self.processed_code["pre"] = self._process_full_agent("pre", self.spec.pre)

    def process_post(self) -> None:
        self.processed_code["post"] = self._process_full_agent("post", self.spec.post)

    def process_specify_output(self) -> None:
        self.processed_code["specify_output"] = self._process_full_agent(
            "specify_output", self.spec.specify_output
        )

    def process_post_fallback(self) -> None:
        self.processed_code["post_fallback"] = self._process_full_agent(
            "post_fallback", self.spec.post_fallback
        )

    def process_all(self) -> dict[str, str]:
        """Validate all four methods and return the sanitized-source map.

        Runs every method through its guard even if an earlier one already
        failed to fail (ValueError/CodeValidationError) -- not caught here,
        so the first bad method still stops the build, but this is the one
        place compiler() needs to call to get everything at once.
        """
        self.process_pre()
        self.process_specify_output()
        self.process_post()
        self.process_post_fallback()
        return self.processed_code

    @abstractmethod
    def _process_full_agent(self, method_name: str, code: str | None) -> str:
        """Turn *code* into validated, sanitized source for *method_name*.

        Must raise (ValueError or a subclass, e.g. CodeValidationError) if
        *code* is missing or fails validation -- never return unsanitized
        or partially-validated source.
        """
        raise NotImplementedError


class TextNewAgentBuilder(NewAgentBuilder):
    """The UI (or any caller) supplies each method's source directly, as text.

    No LLM extraction step -- the code is exactly what the caller wrote, run
    through CodeValidator's AST guards and nothing else.
    """

    def _process_full_agent(self, method_name: str, code: str | None) -> str:
        if not code or not code.strip():
            raise CodeValidationError(
                f"No source code was provided for '{method_name}'."
            )
        return self.validator.confirm_code(
            code,
            function_name=method_name,
            extra_params=_METHOD_PARAM_COUNTS[method_name],
        )


def compiler(builder: NewAgentBuilder) -> type[Agent]:
    """Validate every method on *builder* and compile a real Agent subclass.

    Returns the class itself (not an instance) -- register it in an
    AGENT_REGISTRY (see app.py's AGENT_REGISTRY) the same way any concrete
    class from agents.py or safety_agents.py is registered, and it can be
    used as a pipeline node's "type" like any other agent.
    """
    processed = builder.process_all()
    spec = builder.spec

    namespace: dict[str, Any] = {}
    source = "\n\n".join(processed[name] for name in _METHOD_PARAM_COUNTS)
    code_obj = compile(source, f"<new_agent:{spec.name}>", "exec")
    exec(code_obj, {"__builtins__": dict(_SAFE_BUILTINS)}, namespace)

    for method_name in _METHOD_PARAM_COUNTS:
        if method_name not in namespace or not callable(namespace[method_name]):
            raise CodeValidationError(
                f"Validated source did not define a callable '{method_name}'."
            )

    def __init__(self, query: str = "", state: dict | None = None) -> None:
        Agent.__init__(self, query, state, spec.role)

    class_dict: dict[str, Any] = {
        "__init__": __init__,
        "__module__": __name__,
        "WRITES": frozenset(spec.writes),
        **{name: namespace[name] for name in _METHOD_PARAM_COUNTS},
    }

    return type(spec.name, (Agent,), class_dict)
