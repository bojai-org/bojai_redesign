"""
BojAI LLM Config — Router

Entry point for all LLM calls in the build layer.
ask_llm() routes a rendered prompt string to the correct provider and returns
the response as a string. Providers are instantiated lazily so unused ones
(e.g. OpenAI when only Ollama is configured) never require their credentials.

Supported providers: "openai", "ollama"
"""

from enum import Enum
from typing import Any

from llm_config.openai_llm import OpenAILLM
from llm_config.ollama_llm import OllamaLLM
from build.prompt import PromptLeaf


class Provider(str, Enum):
    OPENAI = "openai"
    OLLAMA = "ollama"


_provider_classes: dict[Provider, type] = {
    Provider.OPENAI: OpenAILLM,
    Provider.OLLAMA: OllamaLLM,
}

_instances: dict[Provider, Any] = {}


async def ask_llm(config: dict) -> str:
    """Route a prompt to the specified LLM provider and return the response."""
    provider = Provider(config["provider"])
    prompt = config["prompt"]

    if "error" in config:
        prompt.add(PromptLeaf(
            id="error_correction",
            text=(
                f"You made a mistake in your previous response: {config['error']}. "
                "Do not repeat this mistake."
            ),
        ))
    
    print(f"Prompt to be sent to {provider.value}: {prompt.render()}")

    if provider not in _instances:
        _instances[provider] = _provider_classes[provider]()

    answer = await _instances[provider](prompt.render(), config["model"], **config.get("kwargs", {}))
    print(f"LLM response type from {provider.value}: {type(answer)}")
    print(f"LLM response from {provider.value}: {answer}")
    return answer
