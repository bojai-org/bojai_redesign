"""
BojAI Architecture — Data Primitives

This module is part of the `architecture` layer, which defines the runtime
foundations of the BojAI pipeline. It does not concern itself with how
components are built or configured — that responsibility belongs to the
`build` layer. Instead, this module provides the lowest-level abstractions
that every other component in the system depends on.

Components defined here:

- required (decorator):
    Wraps an abstract method to enforce that subclasses provide a meaningful
    implementation. Raises NotImplementedError both when the method is missing
    and when it returns None, preventing silent no-op overrides.

- Data:
    Abstract base for all data objects passed between pipeline stages.
    Enforces a consistent iteration and indexing interface across InitialData,
    MainData, and any custom data containers.

- Logger:
    Lightweight key-value log store used by pipeline components to record
    events, metrics, and intermediate outputs during a run.

- Trainer:
    Abstract base for training component in the pipeline. Provides uniform access to
    shared runtime resources: model, device, tokenizer, hyperparameters,
    logger, and data. Hyperparameters are automatically unpacked as instance
    attributes via _assign_hyper_params. 
    The user must implement the train method, which serves as the main entry point 
    for the training logic.

This module has no dependencies on the `build` layer and should remain
independent of any LLM-assisted construction logic.
"""

from abc import ABC, abstractmethod
from typing import Any


# Decorators


def required(func):
    """Decorator to mark a method as required for a component."""
    @abstractmethod
    def wrapper(*args, **kwargs):
        ret = None
        try:
            ret = func(*args, **kwargs)
        except NotImplementedError:
            raise NotImplementedError(f"{func.__name__} is required but not implemented.")
        if ret is None:
            raise NotImplementedError(f"{func.__name__} is required but not implemented.")
        return ret
    return wrapper


class Data(ABC):
    """Shared base for data objects passed between components."""

    def __init__(self, input: Any, output: Any = None):
        self.input = input
        self.output = output




class Logger:
    """Simple default logger for pipeline components."""

    def __init__(self):
        self.logs = {}

    def log(self, key: str, value: Any = None):
        self.logs.setdefault(key, []).append(value)

    def get(self, key: str):
        return self.logs.get(key, [])

