"""
BojAI Architecture — Processed Data Container

This module is part of the `architecture` layer and defines MainData, the
standard container for data that has already been processed and is ready
for consumption by downstream pipeline stages (trainers, evaluators, etc.).

MainData is the output type of every post-processor in the `build` layer.
It is intentionally simple — it wraps a flat sequence with a consistent
iteration and indexing interface and carries no processing logic of its own.

For the abstract base classes that define *how* data gets processed into
a MainData object, see the `build/data` layer.

Components defined here:

- MainData:
    A ready-to-use, always-valid data container backed by a flat sequence.
    Unlike InitialData, it has no initialization guard — data is assumed
    to be fully formed on construction. Supports standard indexing, len(),
    and iteration. Used as the output contract between post-processors and
    all downstream components.
"""

from architecture.base_class import Data

from abc import ABC, abstractmethod
from typing import Any, Sequence

class MainData(Data):
    """Base class for main data objects passed between components. It is a singleton."""

    # Singleton pattern to ensure only one instance of MainData exists
    _instance = None
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, input: Sequence, output: Sequence = None):
        super().__init__(input, output)
        if input is None:
            raise ValueError("input is required to initialize MainData, initialize with InitialData.")
        
        #main data
        self.input : Sequence[Any] = input
        self.output : Sequence[Any] = output

        #flags
        self.input_only = True if output is None else False
        self.index = 0

    def __getitem__(self, key: int) -> Any:
        if not self.input_only:
            return {"input": self.input[key], "output": self.output[key]}
        return {"input": self.input[key]}

    def __len__(self) -> int:
        if not self.input_only:
            if len(self.input) != len(self.output):
                raise ValueError("Input and output sequences must be the same length.")
            return len(self.input)
        return len(self.input)

    def __next__(self) -> dict:
        if self.index >= len(self.input):
            raise StopIteration
        self.index += 1
        if not self.input_only:
            return {"input": self.input[self.index - 1], "output": self.output[self.index - 1]}
        return {"input": self.input[self.index - 1]}

