"""
BojAI Build — Default Embedding Provider

Supplies the ``embed_texts`` callable evaluator.py uses to score answer
similarity (and that a pipeline's own Neural_Network_Barrier_Agent node would
otherwise need supplied at compile time -- see contract.md section 10).

Contract (matches safety_agents.EmbedFunction):

    async def embed_texts(
        texts: list[str],
        embedding_config: dict,
    ) -> list[list[float]]:
        ...
"""

from __future__ import annotations

import os

from openai import AsyncOpenAI

DEFAULT_EMBEDDING_PROVIDER = "openai"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY environment variable is not set.")
        _client = AsyncOpenAI(api_key=api_key)
    return _client


async def embed_texts(texts: list[str], embedding_config: dict | None = None) -> list[list[float]]:
    """Embed *texts* with the provider/model named in embedding_config.

    Only OpenAI is supported today (the only provider in this repo with an
    embeddings endpoint wired up); embedding_config may still carry
    provider/model keys so this can grow the same way llm_config.router does.
    """
    embedding_config = embedding_config or {}
    provider = embedding_config.get("provider", DEFAULT_EMBEDDING_PROVIDER)
    if provider != "openai":
        raise ValueError(f"Unsupported embedding provider: {provider!r}")

    model = embedding_config.get("model", DEFAULT_EMBEDDING_MODEL)
    client = _get_client()
    response = await client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in response.data]
