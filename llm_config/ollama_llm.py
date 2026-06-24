"""
BojAI LLM Config — Ollama Provider

Wraps the local Ollama instance via the ollama Python library.
Assumes Ollama is running at http://localhost:11434 (the default).
"""

from ollama import AsyncClient


class OllamaLLM:

    def __init__(self):
        self._client = AsyncClient()

    async def __call__(self, prompt: str, model: str, **kwargs) -> str:
        response = await self._client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        return response.message.content
