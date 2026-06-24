# BojAI

BojAI turns a raw pipeline folder with raw model/training and data processing logic into a
runnable ML pipeline by using an LLM to read your code and data, extract the relevant
pieces, validate them, and run them in a sandbox. A human points it at a directory;
agents do the file-finding, code-extraction, and validation; the result is a typed
object (`InitialData`, `MainData`, a `Tokenizer`, a `Model`, ...) that the rest of the
system can consume.


This README covers the Python backend (`architecture/`, `build/`, `llm_config/`,
`prompts/`). The `frontend/bojai` folder is a separate, early-stage VS Code extension
and is intentionally out of scope here.

## Mental model: two layers


The backend is split into two layers that should never blur together:

- **`architecture/`** — the runtime contracts. Plain abstract base classes and data
  containers (`Data`, `Logger`, `InitialData`, `MainData`, `Trainer`, `Model`,
  `Tokenizer`). No LLM calls, no agents, no I/O beyond what a normal Python object
  needs. This is "what a valid pipeline component looks like."
- **`build/`** — the LLM-assisted construction logic. Agents and pipelines that read a
  user's files, ask an LLM to make a decision or extract code, validate the result, and
  produce an instance of one of the `architecture` types. This is "how we build a valid
  pipeline component from a user's existing codebase."

`build` depends on `architecture` (it produces architecture objects); `architecture`
never depends on `build`. If you're adding a new pipeline stage, ask first: am I
defining a new *kind of contract* (→ `architecture`) or a new *way of constructing* an
existing contract (→ `build`)?

```
prompts/            static JSON prompt fragments, one set per agent step
llm_config/         provider-agnostic LLM router (OpenAI, Ollama)
architecture/
  base_class.py      Data, Logger, the @required decorator
  data/
    pre_processor.py   InitialData (raw input container)
    post_processors.py MainData (processed, ready-to-use container)
  training/
    ingredients.py     Tokenizer, Model abstract base classes
    training_classes.py Trainer abstract base class
  app.py              FastAPI app that serves an already-built MainData
build/
  prompt.py           PromptComponent / PromptLeaf / PromptComposite tree
  base_classes.py      Agent, SimpleAgent, Pipeline base classes
  agents.py            concrete data-pipeline agents (choice/decision/extraction)
  data/
    pipelines.py        PreProcessingPipeline, PostProcessingPipeline
    utils.py            CodeRunner (sandbox) + CodeValidator (AST guards)
  training/
    pipelines.py         hyperparameter/tokenizer/model/training-loop pipelines (WIP)
  app.py              FastAPI app that triggers the build pipelines
  tests/              pytest suite mirroring the layout above
```

### The `@required` decorator

Defined in `architecture/base_class.py`, and used on methods like `InitialData.build()`
(`architecture/data/pre_processor.py`) and `Trainer.train()`
(`architecture/training/training_classes.py`) — methods the `build` layer *must* give a
real implementation for before `architecture` can trust the resulting object.

These aren't plain abstract methods because the classes that declare them are no longer
abstract by the time they reach this point — they're concrete, instantiable classes
(singletons, or classes the `build` layer dynamically subclasses/generates code for at
runtime), so Python has to allow instantiating them directly. That also means
`@abstractmethod` stops being useful as a safety net: its only check is "did a subclass
override this method at all," and a do-nothing override like `def build(self): pass`
already satisfies that, letting a broken/unfinished implementation through silently.

`@required` adds the check `@abstractmethod` can't: it wraps the method so that calling
it raises `NotImplementedError` if the implementation either raises `NotImplementedError`
itself or simply returns `None`. So a no-op or unfinished override is no longer good
enough — it fails loudly the moment it's actually called, instead of looking valid just
because the method name was overridden. Reach for `@required` instead of
`@abstractmethod` whenever the class itself must remain directly instantiable but a
specific method still can't be allowed to be a silent no-op.

## How a pipeline run actually works

Every multi-step construction flow follows the same shape:

1. A **`Pipeline`** (`build/base_classes.py`) owns the LLM config and composes a fixed
   sequence of **`Agent`**s.
2. Each **`Agent`** builds a prompt from a static template in `prompts/<name>.json` plus
   whatever dynamic context it has (directory tree, file contents, prior pipeline
   output), calls the LLM via `llm_config.router.ask_llm`, and parses/validates the
   response in `process_response()`. On a `ValueError`/`TypeError` from
   `process_response()`, the agent feeds the error back into the prompt and retries (up
   to `MAX_TRIES`).
3. If an agent's job is to hand back LLM-*generated code* (a `build()` function, a
   tokenizer, a model, a training loop), that code never runs unchecked:
   - `CodeValidator.confirm_code()` parses the code with `ast`, rejects anything that
     imports outside an explicit allowlist, calls a forbidden builtin (`exec`, `eval`,
     `open`, `__import__`, ...), uses `global`/`nonlocal`, has decorators, or has default
     arguments — then strips everything except the function definition itself.
   - `CodeRunner.run_code()` executes the sanitized source in a **separate subprocess**:
     the code is passed via an environment variable (never written to disk), input is
     piped in over stdin via `pickle`, the result comes back over stdout, and on Linux
     the subprocess is capped at 512 MB memory / 30 CPU seconds with a hard wall-clock
     timeout on top.
4. The pipeline wraps the validated result in the matching `architecture` type
   (`InitialData`, `Tokenizer`, `Model`, ...) and returns it.

**Data pipelines today** (`build/data/pipelines.py`):
- `PreProcessingPipeline` — scan a directory → LLM picks candidate data files → LLM
  confirms the final list. Returns `list[str]`.
- `PostProcessingPipeline` — scan a directory → LLM picks/confirms files likely to
  contain processing code → LLM extracts a `build()` function → validate-with-retry →
  run it in the sandbox against your raw data → wrap as `InitialData`.

**Training pipelines** (`build/training/pipelines.py`) are under active development —
hyperparameter extraction, tokenizer extraction, and model extraction work the same
choice → decision → (extract → validate → run) way, each one passing its own output
forward as context to the next. `TrainingOrchestrationPipeline` wires these together
but the final "extract the training loop" step is not implemented yet — expect this
file to change.

## Prompts

Agents never hardcode prompt text. Each step has a JSON file in `prompts/<name>.json`,
a list of sections, each with an `id` and a list of `{id, text}` leaf nodes:

```json
[
  { "id": "intro", "titles": [{ "id": "intro_text", "text": "You are ..." }] },
  { "id": "task",  "titles": [{ "id": "task_text",  "text": "Given ... return JSON." }] }
]
```

`Agent.build_prompt()` (`build/base_classes.py`) loads this file, turns it into a
`PromptComposite` tree (`build/prompt.py`), and prepends any dynamic fields from
`_prompt_config()` (directory tree, file contents, prior context, etc.) as extra nodes
before the static sections. When adding a new agent, add a matching
`prompts/<name>.json` rather than building the prompt string by hand.

## LLM providers

`llm_config/router.py` is the single entry point (`ask_llm(config)`) for every LLM
call in `build/`. `config` is a dict with `provider` (`"openai"` or `"ollama"`),
`model`, a `prompt` (a `PromptComposite`), and optional `kwargs`. Provider clients are
instantiated lazily and cached, so you only need credentials for the provider you
actually use:

- `"openai"` — reads `OPENAI_API_KEY` from the environment, raises immediately if unset.
- `"ollama"` — talks to a local Ollama daemon at `http://localhost:11434`.

To add a provider: implement an async `__call__(self, prompt: str, model: str,
**kwargs) -> str`, then register it in `_provider_classes` in `router.py`.

## HTTP surface

Two separate FastAPI apps, one per layer:

- `architecture/app.py` — read-only API over an already-populated `MainData`
  singleton (`/data/length`, `/data/item/{index}`, `/data/next`, `/data/reset`,
  `/data/all`, `/data/init`). Returns `503` until something has populated `MainData`.
- `build/app.py` — triggers the construction pipelines themselves
  (`POST /data/pre-process`, `POST /data/post-process`, `POST /data/describe`).

Run either with uvicorn, e.g.:

```bash
uvicorn build.app:app --reload
```

`build/curl_tests.sh` has example requests for the build API once the server is up.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

- `openai` / `ollama` are only needed for the provider you actually call, but both are
  in `requirements.txt` since either may be used depending on `LLM_config["provider"]`.
- The code the sandbox executes (`build/data/utils.py: ALLOWED_IMPORTS`) may reference
  packages like `numpy`, `pandas`, or `torch` — those only need to be installed if your
  *generated* `build()`/tokenizer/model code imports them, not to run BojAI itself.

## Running tests

```bash
pytest                              # everything except integration tests need no network
pytest build/tests/                 # all build-layer tests
pytest build/tests/data/            # data pipeline only
pytest -m integration               # end-to-end tests against the real OpenAI API
```

`pytest.ini` sets `asyncio_mode = auto` (no `@pytest.mark.asyncio` needed) and
`pythonpath = .` (run pytest from the repo root). Integration tests
(`build/tests/data/integration_tests/`) call the real OpenAI API and auto-skip unless
`OPENAI_API_KEY` is set — they cost real tokens, so don't run them on every save.

Most unit tests mock `ask_llm` directly (see `build/tests/conftest.py`) rather than
hitting a real LLM, and mock the `Agent`/`Pipeline` collaborators rather than the
network layer when testing orchestration (see `build/tests/data/test_pipelines.py`).
Follow that pattern for new pipeline/agent tests.

## Adding a new pipeline step

1. Add `prompts/<name>.json` with the static instructions for the LLM.
2. Add an `Agent` subclass in `build/agents.py` (or a new module) implementing
   `process_response()` — raise `ValueError`/`TypeError` on bad input so the retry loop
   in `Agent.run()` kicks in.
3. If the agent returns code to execute, mix in `CodeValidator`/`CodeRunner`
   (`build/data/utils.py`) and run it through `confirm_code()` before `run_code()`.
4. Wire the agent into a `Pipeline` subclass, or into an existing pipeline's `run()`.
5. Add unit tests next to the existing ones in `build/tests/`, mocking the LLM call
   rather than hitting a real provider.
