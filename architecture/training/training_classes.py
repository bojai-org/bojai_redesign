
from architecture.base_class import Logger, required
from architecture.data.post_processors import MainData
from typing import Any
from architecture.data.post_processors import MainData




class Trainer():
    """
    Shared base for BojAI components that need access to:
    - model
    - device
    - tokenizer
    - hyperparameters
    - logger
    - data
    """

    def __init__(
        self,
        model: Any = None,
        device: Any = None,
        tokenizer: Any = None,
        hyper_params: dict = None,
        logger: Logger = None,
        data: MainData = None,
    ):
        self.model = model
        self.device = device
        self.tokenizer = tokenizer
        self.hyper_params = hyper_params or {}
        self.logger = logger or Logger()
        self.data = data

        self._assign_hyper_params(self.hyper_params)

    def _assign_hyper_params(self, hyper_params: dict):
        for key, value in hyper_params.items():
            setattr(self, key, value)

    @required
    def train(self, *args, **kwargs):
        """Default train method, can be overridden by subclasses."""
        pass




