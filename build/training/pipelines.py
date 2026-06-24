"""
BojAI build - Training Pipelines
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Any
from build.agents import FileChoiceAgent, DecisionAgent, HyperparameterAgent, CodeExtractionAgent
from build.base_classes import Pipeline
from build.data.utils import CodeRunner, CodeValidator
from architecture.training.ingredients import Model, Tokenizer
from architecture.training.training_classes import Trainer

@dataclass
class TrainingComponents:
    hyperparams: dict[str, str | int | float | bool]
    tokenizer: Tokenizer | None
    model: Model



class ChooseThenRunCodePipeline(Pipeline, ABC):
    """Abstract pipeline that selects code files, extracts code, validates it, and runs it."""

    def __init__(self, choice_name, decision_name, validation_name, extraction_name,  LLM_config: dict, context: str | None):
        super().__init__(LLM_config)
        self.choice_name = choice_name
        self.decision_name = decision_name
        self.validation_name = validation_name
        self.extraction_name = extraction_name
        self.context = context

    async def _select_code_files(self) -> List[str]:
        choice_agent = FileChoiceAgent(self.choice_name, self.address, self.LLM_config, self.context)
        selected_files = await choice_agent.run()  
        decision_agent = DecisionAgent(self.decision_name, selected_files, choice_agent.dir_tree, self.LLM_config, self.context)
        confirmed_files = await decision_agent.run()   
        return confirmed_files
    
    async def _find_code(self, files: List[str]) -> str:
        all_code = ""
        for file in files:
            with open(file, "r") as f:
                all_code += f"\n# Code from {file}\n{f.read()}\n"
        code_agent = CodeExtractionAgent(self.extraction_name, all_code, self.LLM_config, self.context)
        return await code_agent.run()
    
    @abstractmethod
    def get_object_from_code(self, code: str) -> Any:
        pass

class HyperparameterPipeline(Pipeline):
    """Finds files containing hyperparameters and returns them as a typed dict."""

    def __init__(self, pipeline_address: list, LLM_config: dict):
        super().__init__(LLM_config)
        self.address = pipeline_address

    async def run(self) -> dict[str, str | int | float | bool]:
        choice_agent = FileChoiceAgent("hyperparameter_choice", self.address, self.LLM_config)
        selected_files = await choice_agent.run()

        decision_agent = DecisionAgent("hyperparameter_decision", selected_files, choice_agent.dir_tree, self.LLM_config)
        files = await decision_agent.run()

        hyperparams = HyperparameterAgent("hyperparameter_extraction", files, self.LLM_config)
        return await hyperparams.run()


class TokenizationPipeline(ChooseThenRunCodePipeline, CodeRunner, CodeValidator):
    """Finds and extracts tokenizer code, with optional context from earlier pipeline stages."""

    def __init__(self, pipeline_address: list, LLM_config: dict, context: str | None = None):
        super().__init__("tokenizer_choice", "tokenizer_decision", "tokenizer_code_validation", "tokenizer_code_extraction", LLM_config, context)   
        self.address = pipeline_address
        self.context = context

    async def run(self) -> Tokenizer:
        files = await self._select_code_files()
        code = await self.validate_with_retry(
            self._find_code   ,
            self._select_code_files,
            "tokenizer_code_validation",
            self.LLM_config,
            files,
            data_description=self.context,
        )
        return self.get_object_from_code(code)

    def get_object_from_code(self, code: str) -> Tokenizer:
        tokenizer: Tokenizer = self.run_code(code)
        if not isinstance(tokenizer, Tokenizer):
            raise ValueError("The extracted code did not return a Tokenizer object.")
        return tokenizer


class ModelPipeline(ChooseThenRunCodePipeline, CodeRunner, CodeValidator):
    """Finds and extracts model code, with optional context from earlier pipeline stages."""

    def __init__(self, pipeline_address: list, LLM_config: dict, context: str | None = None):
        super().__init__("model_choice", "model_decision", "model_code_validation", "model_code_extraction", LLM_config, context)
        self.address = pipeline_address
        self.context = context

    async def run(self) -> Model:
        confirmed_files = await self._select_code_files()
        code = await self.validate_with_retry(
            self._find_code,
            self._select_code_files,
            "model_code_validation",
            self.LLM_config,
            confirmed_files,
            data_description=self.context,
        )
        return self.get_object_from_code(code)

    def get_object_from_code(self, code: str) -> Model:
        model: Model = self.run_code(code)
        if not isinstance(model, Model):
            raise ValueError("The extracted code did not return a Model object.")
        return model

"""
Need to pass model and tokenizer into the training loop pipeline in order to validate that the extracted training loop code actually uses them. 

"""
class TrainingLoopPipeline(ChooseThenRunCodePipeline, CodeRunner, CodeValidator):
    """Finds and extracts training loop code that uses the extracted components, with all prior context available."""

    def __init__(self, pipeline_address: list, LLM_config: dict, context: str):
        super().__init__("training_loop_choice", "training_loop_decision", "training_loop_code_validation", "training_loop_code_extraction", LLM_config, context)
        self.address = pipeline_address
        self.context = context

    async def run(self) -> str:
        confirmed_files = await self._select_code_files()
        code = await self.validate_with_retry(
            self._find_code,
            self._select_code_files,
            "training_loop_code_validation",
            self.LLM_config,
            confirmed_files,
            data_description=self.context,
        )
        return self.get_object_from_code(code)
    
    def get_object_from_code(self, code: str) -> Trainer:
        trainer: Trainer = self.run_code(code)
        if not isinstance(trainer, Trainer):
            raise ValueError("The extracted code did not return a Trainer object.")
        return trainer
    

class TrainingOrchestrationPipeline(Pipeline):
    """Orchestrates hyperparameter extraction, optional tokenization, and model extraction in order.
    Each stage receives the outputs of prior stages as LLM context."""

    def __init__(self, pipeline_address: list, LLM_config: dict, needs_tokenizer: bool = True):
        super().__init__(LLM_config)
        self.address = pipeline_address
        self.needs_tokenizer = needs_tokenizer

    async def run(self) -> TrainingComponents:
        # 1. Extract hyperparameters — no prior context.
        hyperparams = await HyperparameterPipeline(self.address, self.LLM_config).run()

        hyperparam_context = f"Hyperparameters: {hyperparams}"

        # 2. Extract tokenizer (optional) — sees hyperparameters.
        tokenizer = None
        if self.needs_tokenizer:
            tokenizer = await TokenizationPipeline(
                self.address, self.LLM_config, context=hyperparam_context
            ).run()

        # 3. Extract model — sees hyperparameters and tokenizer (if any).
        model_context = hyperparam_context
        if tokenizer is not None:
            model_context += f"\nTokenizer: {type(tokenizer).__name__}"

        model = await ModelPipeline(
            self.address, self.LLM_config, context=model_context
        ).run()

        Ingredients =  TrainingComponents(hyperparams=hyperparams, tokenizer=tokenizer, model=model)

        # 4. Find training loop code that uses the extracted components, with all prior context available.

    



