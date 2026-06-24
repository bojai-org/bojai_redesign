"""
BojAI LLM Config — OpenAI Provider

Wraps the OpenAI chat completions API.
Reads OPENAI_API_KEY from the environment at instantiation time.
"""

import os
from openai import AsyncOpenAI


class OpenAILLM:

    def __init__(self):
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY environment variable is not set.")
        self._client = AsyncOpenAI(api_key=api_key)

    async def __call__(self, prompt: str, model: str, **kwargs) -> str:
        response = await self._client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        return response.choices[0].message.content
