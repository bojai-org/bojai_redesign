"""
BojAI Architecture — Runtime Data API

This module is part of the `architecture` layer and exposes the HTTP interface
for reading data that has already been built and loaded into MainData. It has
no involvement in pre-processing, post-processing, training, or evaluation —
those belong to the `build` layer and future train/eval layers respectively.

MainData is a singleton: once the build pipeline populates it, every request
here reads from the same in-memory object. All endpoints return 503 if the
singleton has not been populated yet.

Endpoints defined here:

- GET /data/length:
    Returns the total number of items in the loaded dataset.

- GET /data/item/{index}:
    Returns the item at the given index as {"input": ..., "output": ...}.
    Returns 404 if the index is out of range.

- GET /data/next:
    Returns the next item from the internal cursor and advances it.
    Returns 404 when the cursor reaches the end; call /data/reset to restart.

- POST /data/reset:
    Resets the internal iteration cursor back to position 0.

- GET /data/all:
    Returns every item in the dataset as a list. Avoid on large datasets.

- POST /data/init:
    Loads data directly into MainData from a JSON body {"input": [...], "output": [...]}.
    output is optional. Re-calling this endpoint replaces the existing data.
"""

from typing import Any, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from architecture.data.post_processors import MainData

app = FastAPI(title="BojAI Runtime API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class DataInitRequest(BaseModel):
    input: List[Any]
    output: Optional[List[Any]] = None


def _get_data() -> MainData:
    if MainData._instance is None:
        raise HTTPException(
            status_code=503,
            detail="No data loaded. Run the build pipeline first.",
        )
    return MainData._instance


@app.post("/data/init")
def data_init(body: DataInitRequest):
    MainData._instance = None  # drop singleton so __new__ creates a fresh one
    data = MainData(body.input, body.output)
    return {"loaded": True, "length": len(data), "has_output": data.output is not None}


@app.get("/data/length")
def data_length():
    data = _get_data()
    return {"length": len(data)}


@app.get("/data/item/{index}")
def data_item(index: int):
    data = _get_data()
    try:
        return data[index]
    except IndexError:
        raise HTTPException(status_code=404, detail=f"Index {index} out of range.")


@app.get("/data/next")
def data_next():
    data = _get_data()
    try:
        return data.__next__()
    except StopIteration:
        raise HTTPException(
            status_code=404,
            detail="No more items. Call POST /data/reset to start over.",
        )


@app.post("/data/reset")
def data_reset():
    data = _get_data()
    data.index = 0
    return {"reset": True, "length": len(data)}


@app.get("/data/all")
def data_all():
    data = _get_data()
    return {"items": [data[i] for i in range(len(data))], "length": len(data)}
