# BojAI JSON Pipeline Contract

## 1. Purpose

A pipeline JSON document describes a directed, executable graph of BojAI agents. The compiler validates the complete document before constructing any agent. A valid document compiles to a runnable `Pipeline` object.

The compiler accepts either the canonical shape below or the compact authoring shape where node objects are placed directly beside `config` and `entrypoint`.

```json
{
  "config": {
    "provider": "provider-name",
    "model": "model-name"
  },
  "entrypoint": "decision",
  "max_steps": 100,
  "nodes": {
    "decision": {
      "type": "Decision_Agent",
      "prev": -1,
      "query": "Choose a retrieval method",
      "context": "Initial context",
      "options": ["semantic", "keyword"],
      "semantic": "rag_1",
      "keyword": "keyword_1"
    },
    "rag_1": {
      "type": "RAG_Agent",
      "prev": "decision",
      "query": 0,
      "corpus_address": "address/to/corpus",
      "next": "rag_2"
    },
    "rag_2": {
      "type": "RAG_Agent",
      "prev": "rag_1",
      "corpus_address": "address/to/corpus",
      "next": "answer"
    },
    "keyword_1": {
      "type": "Keyword_Search_Agent",
      "prev": "decision",
      "query": 0,
      "corpus_address": "address/to/corpus",
      "next": "answer"
    },
    "answer": {
      "type": "Direct_Answer_Agent",
      "prev": ["rag_2", "keyword_1"],
      "next": -1
    }
  }
}
```

`rag_1` routes straight into `rag_2` with nothing in between. `RAG_Agent`, `Keyword_Search_Agent`, and `Hybrid_Agent` never call the LLM — they only retrieve, and each one deduplicates against whatever the run has already found (see §8). So a chain of retrieval hops needs exactly one generation node (`Direct_Answer_Agent` here) at the end, not a reply agent wedged after every hop.

## 2. Top-level contract

### `config`

Required object. It must contain:

- `provider`: non-empty string.
- `model`: non-empty string.

The complete config object is copied and passed to every agent `run()` call. An agent may ignore the config, but the pipeline runtime always supplies it when that agent's `run` signature accepts an argument.

### `entrypoint`

Optional non-empty node ID. When omitted, the first declared user node is the entrypoint. `_final` cannot be the entrypoint.

### `max_steps`

Optional positive integer. Default: `100`. Execution stops with an error when this many steps are exceeded. This prevents an accidental non-terminating loop.

### `nodes`

Required in canonical JSON. It must be a non-empty object whose keys are unique node IDs and whose values satisfy the node contract below.

In compact JSON, `nodes` may be omitted. Every top-level key other than `config`, `entrypoint`, and `max_steps` is then treated as a node.

## 3. Node IDs and ordinals

A node can be referenced by:

1. Its string node ID, which is preferred.
2. Its zero-based integer ordinal in JSON declaration order.

`0` means the first declared node, `1` the second, and so on. `_final`, when inserted automatically, is appended after all user nodes.

String IDs are safer than integer ordinals because they do not change when nodes are reordered.

## 4. Common node fields

### `type`

Required non-empty string. It must exactly match a key in the `agent_registry` passed to `compile_pipeline`.

The compiler never imports arbitrary classes named by JSON. This prevents untrusted JSON from loading arbitrary Python objects.

### `prev`

Required for a strict graph description, except for the entrypoint.

Accepted forms:

- `-1` or `null`: no predecessor. Used by the entrypoint.
- One node ID or ordinal: exactly one allowed predecessor.
- A list of node IDs or ordinals: the node may be called by **any one** of those predecessors.

A list does not mean that all predecessor outputs are merged. At runtime the node receives context only from the predecessor that actually routed into it.

The compiler verifies that `prev` exactly matches the node's actual incoming routes. This prevents the forward and backward graph descriptions from disagreeing.

### `query`

Accepted forms:

- String: a literal query owned by this node.
- Integer ordinal: reuse the effective query of that referenced node.
- `null` or omitted: inherit the effective query from the actual calling predecessor; the runtime `initial_query` is used when no predecessor query exists.

A numeric query reference must refer to a node whose effective query is available before the current node executes. Forward query references fail at runtime.

### `context`

Optional string. It is used only when the node has no actual calling predecessor, normally the entrypoint.

For every later node, context is automatically set to the output of the one predecessor that routed into it. When `prev` lists several nodes, only the actual caller's output becomes context.

### Agent constructor arguments

Fields that are not graph-control fields are passed to the registered agent constructor. Graph-control fields are:

- `type`
- `prev`
- `query`
- `context` or `Context`
- `next`
- `routes`
- decision route mapping keys

For `Decision_Agent`, `options` is passed to its constructor.

## 5. Routing contract

An agent's returned value selects its outgoing route.

### Explicit `routes`

Preferred canonical form:

```json
"routes": {
  "yes": "answer",
  "no": "decision"
}
```

Route targets may be node IDs or zero-based ordinals.

### `next` object

Equivalent compact form:

```json
"next": {
  "yes": "answer",
  "no": "decision"
}
```

### Single `next`

A node with one unconditional successor may use:

```json
"next": "check_context"
```

or an ordinal. The compiler normalizes this to a single `done` route. When a node has exactly one outgoing route, its returned value does not need to equal the route name.

### Decision options

For a `Decision_Agent`:

- Numeric options route directly to the node with that ordinal.
- String options require a sibling mapping from the option to its target.

```json
{
  "type": "Decision_Agent",
  "options": ["semantic", "keyword"],
  "semantic": "rag",
  "keyword": "keyword_agent",
  "next": -1
}
```

The decision agent must return the exact option value. Integer values are compared after conversion to strings.

### Route extraction

The runtime tries to match routes using:

1. A string result directly.
2. A boolean result as `yes` or `no`.
3. A dictionary value under `route`, `decision`, `action`, or `result`.
4. The sole declared route when exactly one route exists.

If several routes exist and no route matches, execution fails rather than guessing.

### Dict results and context passthrough

A node's return value becomes both the input to route extraction above *and*, verbatim, the next node's `context` (§4) — whichever route is actually taken receives it. For a node whose only job is to decide a route (a gate or judge), returning a bare string or bool for a two-way decision would forward that same string/bool on as context, discarding whatever the node was gating in the first place.

To gate without losing that payload, return a dict with a `"context"` key alongside the routing key: the runtime forwards `result["context"]` to the next node instead of stringifying the whole dict. `Binary_Judge_Agent` and the three barrier agents in `safety_agents.py` (`Static_Barrier_Agent`, `Neural_Network_Barrier_Agent`, `Judge_Barrier_Agent`) all follow this convention — their result always includes the exact `context` they were evaluating, unchanged, regardless of which way they route. This is what makes a "judge sufficiency, retrieve more on 'no'" loop (§8) safe: the `Binary_Judge_Agent` node's `"no"` route hands the resources it just judged back to the retrieval node it's chained to, not the literal string `"no"`.

## 6. `_final`

`_final` is reserved.

When omitted, the compiler appends:

```json
{
  "type": "_Static_Agent_Auto",
  "prev": [],
  "routes": {}
}
```

Every terminal user node is connected to `_final` through a single `done` route. `_final` returns the output of the node that actually called it. It does not call the LLM and cannot have outgoing routes.

The registry must contain `_Static_Agent_Auto`, even when the compiler adds the node automatically.

## 7. Agent runtime contract

Registered agents must:

1. Be classes or callable factories.
2. Accept their JSON constructor fields as keyword arguments.
3. Expose a callable `run` method.
4. Return either an awaitable or an immediate value.

The preferred signature is:

```python
async def run(self, agent_config: dict) -> Any:
    ...
```

For compatibility with deterministic agents already present in BojAI, `run(self)` is also accepted. The pipeline inspects the signature and calls it without config only when it accepts no argument.

The runtime updates `agent.query` and `agent.context` immediately before execution when those attributes exist.

## 8. Retrieval agents and accumulation

`RAG_Agent`, `Keyword_Search_Agent`, and `Hybrid_Agent` (agents.py) are retrieval-only: `run()` never calls the LLM. Deciding what to do with retrieved resources — summarize them, answer from them, judge whether they're sufficient — is a separate node's job (typically `Direct_Answer_Agent` or `Binary_Judge_Agent`).

Since a node's only channel to the next one is the plain string described in §4 (`context`), a retrieval agent's returned string doubles as retrieval memory for the rest of the run:

- Every chunk it renders is tagged with a machine-readable `(id: ...)` marker.
- Before retrieving, it reads the ids already present in its incoming `context`.
- It retrieves only chunks not already tagged with one of those ids, and appends them to the incoming text rather than replacing it.

Practically, this means:

- Chaining retrieval nodes directly into one another (`rag_1 -> rag_2 -> ...`, as in §1) never returns the same resource twice, and never loses what an earlier hop found.
- A pipeline with a cycle that loops back through the same retrieval node (permitted per §9 below) exhausts the corpus for that query instead of retrieving the same top-k chunks forever.
- Only the terminal generation node needs to call the LLM — retrieval hops in between do not.
- `Binary_Judge_Agent` can gate that chain: route `"yes"` to a generation node and `"no"` back to another retrieval hop, and the resources it judged arrive intact either way, because it returns them under a `"context"` key rather than replacing them with its verdict (§5's "Dict results and context passthrough"). Placing a plain string- or bool-returning gate node in that same spot would silently truncate the chain instead — its return value becomes the next node's `context` verbatim.

`Reranker_Agent` chains into this the same way: it takes `context` like any other node, and recovers individual candidate chunks by parsing the `[Resource N] (id: ...) ...` blocks back out of it (`_parse_resources`, the inverse of `_format_resources`). Connect it directly after `RAG_Agent`, `Keyword_Search_Agent`, or `Hybrid_Agent` to re-rank what they found; it does not take a separate `candidates` constructor field.

## 9. Graph validation

Compilation fails before returning a `Pipeline` when any of the following is true:

- `config.provider` or `config.model` is missing or empty.
- A node type is absent from the registry.
- A route points to a nonexistent node.
- A query or predecessor ordinal is outside the graph.
- `prev` disagrees with actual incoming routes.
- A node is unreachable from the entrypoint.
- No route reaches `_final`.
- `_final` has outgoing routes.
- `max_steps` is not a positive integer.

Cycles are permitted because agent loops are valid. Runtime termination is protected by `max_steps`.

## 10. Compiler usage

```python
from compiler import compile_pipeline
from agents import (
    Decision_Agent,
    RAG_Agent,
    Keyword_Search_Agent,
    Hybrid_Agent,
    Reranker_Agent,
    Binary_Judge_Agent,
    Direct_Answer_Agent,
    Static_Agent,
    Simple_Task_Agent,
    _Static_Agent_Auto,
)
from safety_agents import (
    Static_Barrier_Agent,
    Neural_Network_Barrier_Agent,
    Judge_Barrier_Agent,
    Input_Barrier_Pipeline,
)

registry = {
    "Decision_Agent": Decision_Agent,
    "RAG_Agent": RAG_Agent,
    "Keyword_Search_Agent": Keyword_Search_Agent,
    "Hybrid_Agent": Hybrid_Agent,
    "Reranker_Agent": Reranker_Agent,
    "Binary_Judge_Agent": Binary_Judge_Agent,
    "Direct_Answer_Agent": Direct_Answer_Agent,
    "Static_Agent": Static_Agent,
    "Simple_Task_Agent": Simple_Task_Agent,
    "_Static_Agent_Auto": _Static_Agent_Auto,
    "Static_Barrier_Agent": Static_Barrier_Agent,
    "Neural_Network_Barrier_Agent": Neural_Network_Barrier_Agent,
    "Judge_Barrier_Agent": Judge_Barrier_Agent,
    "Input_Barrier_Pipeline": Input_Barrier_Pipeline,
}

pipeline = compile_pipeline("pipeline.json", agent_registry=registry)
result = await pipeline.run(initial_query="User message")
print(result.output)
```

Every agent class in `agents.py` and `safety_agents.py` is safe to register this way; the pipeline only requires a callable `run` (§7) and does not care whether the class also subclasses `Agent`. Two wrinkles to know about:

- `Neural_Network_Barrier_Agent` and `Input_Barrier_Pipeline` require `embed_texts`, a Python callable, as a constructor argument. A callable cannot be written in JSON text, so a pipeline definition using either one must be built as a Python `dict` (the `Mapping` form `compile_pipeline` accepts) with the real function embedded in the node's `agent_args`, not loaded from a `.json` file.
- The barrier agents (`Static_Barrier_Agent`, `Neural_Network_Barrier_Agent`, `Judge_Barrier_Agent`) return a `BarrierResult` dict whose `action` key (`"safe"`, `"accept"`, `"escalate"`, `"escalate_judge"`, `"reject"`, `"harmful"`) is picked up automatically by the route-extraction rule in §5 — route your `routes`/`next` mapping off of those action values.
