"""
BojAI Build — Data Pipeline API

This module is part of the `build` layer and exposes the HTTP interface for
triggering LLM-assisted data pipeline construction. Callers provide a directory
address list and an LLM config; the endpoints handle agent orchestration
internally and return structured results.

Both pipelines are async end-to-end: each agent calls the LLM, retries on bad
responses, and only returns once a validated result is produced.

Endpoints defined here:

- POST /data/pre-process:
    Runs the PreProcessingPipeline. Scans the given directory tree, uses an LLM
    to select candidate data files, confirms the selection, and returns the final
    list of file paths.

- POST /data/post-process:
    Runs the PostProcessingPipeline. Selects and opens code files, extracts a
    build() function via LLM, validates it, runs it in a sandboxed subprocess
    against raw_data_address, and returns the resulting InitialData as
    {"input": [...], "output": [...]}.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, List, Optional

from build.data.pipelines import PreProcessingPipeline, PostProcessingPipeline, get_data_description
from architecture.data.post_processors import MainData

app = FastAPI(title="BojAI Build API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Request / Response models ─────────────────────────────────────────────────

class LLMConfig(BaseModel):
    model: str
    provider: str


class PreProcessRequest(BaseModel):
    address: str
    llm: LLMConfig


class PostProcessRequest(BaseModel):
    address: str
    raw_data_address: str
    llm: LLMConfig


class PreProcessResponse(BaseModel):
    files: List[str]


class PostProcessResponse(BaseModel):
    input: List[Any]
    output: Optional[List[Any]] = None


class DataDescriptionRequest(BaseModel):
    input: List[Any]
    output: Optional[List[Any]] = None
    llm: LLMConfig


class DataDescriptionResponse(BaseModel):
    description: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/data/pre-process", response_model=PreProcessResponse)
async def pre_process(body: PreProcessRequest):
    pipeline = PreProcessingPipeline(body.address, body.llm.model_dump())
    try:
        
        files = await pipeline.run()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return PreProcessResponse(files=files)


@app.post("/data/post-process", response_model=PostProcessResponse)
async def post_process(body: PostProcessRequest):
    pipeline = PostProcessingPipeline(body.raw_data_address, body.address, body.llm.model_dump())
    try:
        result = await pipeline.run()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return PostProcessResponse(input=result.input, output=result.output)


@app.post("/data/describe", response_model=DataDescriptionResponse)
async def describe_data(body: DataDescriptionRequest):
    data = MainData(body.input, body.output)
    try:
        description = await get_data_description(data, body.llm.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return DataDescriptionResponse(description=description)
