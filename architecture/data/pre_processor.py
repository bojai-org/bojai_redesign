"""
BojAI Architecture — Raw Data Container

This module is part of the `architecture` layer and defines InitialData, the
standard container for raw, unstructured input at the start of the pipeline.

InitialData is the input type expected by pre-processors in the `build` layer.
It holds raw data in its original form and enforces an explicit initialization
step before any access is permitted, preventing downstream components from
operating on unprocessed input by accident.

For the abstract base classes that define *how* raw data gets extracted and
structured into an InitialData object, see the `build/data` layer.

Components defined here:

- InitialData:
    A lazy, guarded container for raw pipeline input. Holds a reference to
    raw_data separately from the processed self.data. All access methods
    (__getitem__, __len__, __next__) raise until build() has been called and
    self.initialized is set to True. Provides to_main_data() to hand off a
    fully processed sequence to the post-processing stage as a MainData object.
"""

from typing import Any, Sequence
from architecture.base_class import Data
from architecture.data.post_processors import MainData
from architecture.base_class import required

class InitialData(Data):
    """Base class for main data objects passed between components. It is a singleton."""

    # Singleton pattern to ensure only one instance of InitialData exists
    _instance = None
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance


    def __init__(self, raw_data: Any = None):
        if hasattr(self, '_init_done'):
            return
        super().__init__(None, None)
        self.input : Sequence[Any] = None
        self.output : Sequence[Any] = None
        self.raw_data = raw_data
        self.index = 0
        self.initialized = False
        self._init_done = True
    
    @required
    def build(self, *args, **kwargs) -> None:
        """Build the data object from raw data. This method must be called before accessing the data."""
        if self.raw_data is None:
            raise ValueError("raw_data is required to build the data.")
        self.data = self.raw_data
        self.initialized = True
        raise NotImplementedError("build() method must be implemented by subclasses to transform raw data into an iterable instance.")
    
    def to_main_data(self) -> MainData:
        """Convert to a main data object if needed. By default, returns self."""
        if not self.initialized:
            raise ValueError("Data not initialized. Call build() to initialize the data.")
        return MainData(self.input, self.output)



