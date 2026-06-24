"""
BojAI Build — Data Pipelines

This module is part of the `build` layer and defines the two high-level data
pipelines that orchestrate the agent steps into complete construction workflows.
Each pipeline inherits from Pipeline (build.base_classes) and owns the full
agent sequence from raw input to a typed output.

Pipelines defined here:

- PreProcessingPipeline(Pipeline):
    Two-step pipeline that selects and confirms data files from a directory.
    Step 1 — DataChoiceAgent: LLM scans the tree and selects candidate files.
    Step 2 — DecisionAgent: LLM reviews the candidates and confirms the final
    list. Returns a list of confirmed file path strings.

- PostProcessingPipeline(Pipeline, CodeRunner, CodeValidator):
    Four-step pipeline that extracts, validates, and runs data-processing code.
    Step 1 — DataChoiceAgent: selects files likely to contain processing code.
    Step 2 — DecisionAgent: confirms which files actually contain useful code.
    Step 3 — CodeExtractionAgent: extracts and sanitizes a build() function.
    Step 4 — DecisionAgent: validates that the extracted code is correct.
    Then runs the sanitized build() in a sandboxed subprocess via CodeRunner
    and wraps the result as an InitialData instance.
"""

from typing import List
from build.base_classes import Pipeline
from build.agents import FileChoiceAgent, DecisionAgent, CodeExtractionAgent, DataDescriptionAgent
from build.data.utils import CodeRunner, CodeValidator
from architecture.data.pre_processor import InitialData
from architecture.data.post_processors import MainData


class PreProcessingPipeline(Pipeline):
    """Routes raw directory input through the pre-processing agent steps and
    returns the final list of confirmed file paths to process."""

    def __init__(self, pipeline_address: list, LLM_config: dict):
        super().__init__(LLM_config)
        self.address = pipeline_address

    async def run(self) -> List[str]:
        choice_agent = FileChoiceAgent("data_choice", self.address, self.LLM_config)
        selected_files = await choice_agent.run()

        decision_agent = DecisionAgent("data_decision", selected_files, choice_agent.dir_tree, self.LLM_config)
        files =  await decision_agent.run()
        print(files)
        return files


class PostProcessingPipeline(Pipeline, CodeRunner, CodeValidator):
    """Selects and extracts data-processing code via agents, runs it in a
    sandbox, and returns the result as an initialized InitialData object."""

    def __init__(self, raw_data, pipeline_address: list, LLM_config: dict):
        super().__init__(LLM_config)
        self.address = pipeline_address
        self.raw_data = raw_data

    async def run(self) -> InitialData:
        confirmed_files = await self._select_code_files()
        code = await self.validate_with_retry(
            self._find_processing_code,
            self._select_code_files,
            "data_code_validation",
            self.LLM_config,
            confirmed_files,
        )
        return self._data_from_code(code)

    async def _select_code_files(self) -> List[str]:
        choice_agent = FileChoiceAgent("data_code_choice", self.address, self.LLM_config)
        files = await choice_agent.run()
        decision_agent = DecisionAgent("data_code_decision", files, choice_agent.dir_tree, self.LLM_config)
        return await decision_agent.run()

    async def _find_processing_code(self, files: List[str]) -> str:
        all_code = ""
        for file in files:
            with open(file, "r") as f:
                all_code += f"\n# Code from {file}\n{f.read()}\n"
        code_agent = CodeExtractionAgent("data_code_extraction", all_code, self.LLM_config)
        return await code_agent.run()

    def _data_from_code(self, code: str) -> InitialData:
        # run_code executes build(raw_data) in an isolated subprocess and
        # returns {"input": [...], "output": [...]} or {"input": [...]}.
        result = self.run_code(code, self.raw_data)

        input_data = result.get("input")
        output_data = result.get("output")

        if input_data is None:
            raise ValueError("build() must return a dict with at least an 'input' key.")

        class DynamicInitialData(InitialData):
            def build(self_inner, *args, **kwargs) -> None:
                self_inner.input = input_data
                self_inner.output = output_data
                self_inner.initialized = True

        instance = DynamicInitialData(self.raw_data)
        instance.build()
        return instance


async def get_data_description(data: MainData, LLM_config: dict) -> str:
    """Ask the LLM to describe the dataset based on a few input/output samples."""
    output = list(data.output) if not data.input_only else None
    agent = DataDescriptionAgent(list(data.input), LLM_config, output)
    return await agent.run()

