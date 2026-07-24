"""
BojAI Build — Prompt Tree

This module is part of the `build` layer and implements the composite pattern
for constructing structured LLM prompts. Prompts are built as trees of named
nodes; the tree can be navigated by ID and rendered to a plain string for
submission to the LLM.

Components defined here:

- PromptComponent:
    Abstract base node. Every node has a string id (auto-generated UUID if not
    provided) and must implement render() -> str.

- PromptLeaf:
    Terminal node containing a plain text string. render() returns the text as-is.

- PromptComposite:
    Internal node that holds an ordered list of child PromptComponents. Maintains
    a flat id→node index (including all descendants) for O(1) find() lookups.
    add() and remove() rebuild the index automatically. render() joins children
    with double newlines.
"""

from abc import ABC, abstractmethod
from typing import Iterable, List
from typing import Iterable, List
from uuid import uuid4


class PromptComponent(ABC):
    """Base component in the prompt tree."""

    def __init__(self, id: str | None = None):
        self.id = id or str(uuid4())

    @abstractmethod
    def render(self) -> str:
        pass


class PromptLeaf(PromptComponent):
    """Leaf node containing plain prompt text."""

    def __init__(self, text: str, id: str | None = None):
        super().__init__(id)
        self.text = text

    def render(self) -> str:
        return self.text


class PromptComposite(PromptComponent):
    """Composite node containing prompt components."""

    def __init__(
        self,
        components: Iterable[PromptComponent] | None = None,
        id: str | None = None,
    ):
        super().__init__(id)
        self.components: List[PromptComponent] = list(components or [])
        self._index: dict[str, PromptComponent] = {}
        self._build_index()

    def _build_index(self) -> None:
        self._index = {}
        self._index[self.id] = self

        for component in self.components:
            self._index[component.id] = component

            if isinstance(component, PromptComposite):
                self._index.update(component._index)

    def add(self, component: PromptComponent) -> None:
        self.components.append(component)
        self._build_index()

    def remove(self, component: PromptComponent) -> None:
        self.components.remove(component)
        self._build_index()

    def find(self, id: str) -> PromptComponent | None:
        return self._index.get(id)

    def render(self) -> str:
        return "\n\n".join(component.render() for component in self.components)