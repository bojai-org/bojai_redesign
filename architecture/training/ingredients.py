from abc import ABC, abstractmethod


class Tokenizer(ABC):
    """Abstract base class for all tokenizers."""
    def __init__(self, hyper_params):
        self.hyper_params = hyper_params
    
    @abstractmethod
    def tokenize(self, text):
        pass


class Model(ABC):
    """Abstract base class for all models."""
    def __init__(self,  hyper_params : dict, tokenizer : Tokenizer = None):
        self.tokenizer = tokenizer
        self.hyper_params = hyper_params

