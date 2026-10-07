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

A list does not mean that all predecessor outputs are merged. At runtime the node's `query` (§4) is resolved only from the predecessor that actually routed into it; shared state (§4a) is common to every node in the run regardless of `prev`, so which predecessor called a node has no bearing on what it can read from `self.state`.

The compiler verifies that `prev` exactly matches the node's actual incoming routes. This prevents the forward and backward graph descriptions from disagreeing.

### `query`

Accepted forms:

- String: a literal query owned by this node.
- Integer ordinal: reuse the effective query of that referenced node.
- `null` or omitted: inherit the effective query from the actual calling predecessor; the runtime `initial_query` is used when no predecessor query exists.

A numeric query reference must refer to a node whose effective query is available before the current node executes. Forward query references fail at runtime.

### `context`

Optional string. It is used only to seed the entrypoint node's initial shared state (§4a) -- a node with an actual calling predecessor ignores its own `context` field entirely.

### 4a. Shared pipeline state

Every node in one `Pipeline.run()` call shares a single state `dict`, created fresh for that run (never reused across separate `run()` calls on the same compiled `Pipeline`, since agent instances persist across runs -- see evaluator.py, which calls `run()` once per CSV row). It is a namespaced blackboard, not a free-for-all node-to-node string: a node may read any key it likes from `self.state`, but the runtime only ever copies a key out of a node's *result* and merges it into shared state if that node's agent class declares owning it, via a `WRITES` class attribute (`frozenset[str]`, empty by default).

The registry of namespaced keys is fixed (`pipeline._STATE_KEYS`): `"context"` (written only by a retrieval/rerank agent -- `RAG_Agent`, `Keyword_Search_Agent`, `Hybrid_Agent`, `Reranker_Agent`), `"answer"` (written only by a node producing a final user-facing reply -- `Direct_Answer_Agent`, `Static_Agent`, and the safety barrier agents when they produce a decline message), and `"decision"` (written only by `Decision_Agent`, its chosen option). Any other key a node's result dict carries -- `"route"`, `"action"`, `"reason"`, `"layer"`, `"score"`, used purely to drive route extraction (§5) or for trace/diagnostic purposes -- is not part of this registry and is never inspected by the state-merge step.

This is what keeps a retrieval hop's passages from ever being confused with another node's final reply or a router's chosen option: a node that wants "the retrieved context" reads `self.state["context"]` itself in `pre()` rather than being handed "whatever the previous node returned" and having to guess what it means. Concretely:

- `Direct_Answer_Agent`, `Binary_Judge_Agent`, `Decision_Agent`, and `Simple_Task_Agent` all read `self.state.get("context", "")` explicitly wherever they need retrieved context in their prompt -- never a blanket, automatic field.
- A node whose result dict happens to carry a namespaced key it does not declare in `WRITES` fails the run immediately with `PipelineRuntimeError`, rather than silently writing (or silently dropping) content another part of the pipeline depends on.
- A node with `WRITES = frozenset()` (e.g. `Binary_Judge_Agent`, a pure router) writes nothing to shared state at all -- its result is only used for route extraction (§5) and the trace, never as another node's prompt input.

Pipeline.run()'s final `output` (§6) prefers `state["answer"]` when any node wrote it, falling back to the terminal node's raw return value for a pipeline with no answer-writing node (e.g. one built purely for routing, or one that intentionally ends on a bare retrieval node).

Some agents also take a plain, per-instance `context` **constructor argument** distinct from shared state -- e.g. the safety barrier agents' fixed deployment description (`DEFAULT_BARRIER_CONTEXT`). That is static configuration set once at construction and never touched by the pipeline runtime; it has nothing to do with the shared `state["context"]` key above.

### Agent constructor arguments

Fields that are not graph-control fields are passed to the registered agent constructor. Graph-control fields are:

- `type`
- `prev`
- `query`
- `context` or `Context`
- `next`
- `routes`
- decision route mapping keys

For `Decision_Agent`, `options` is passed to its constructor. A constructor parameter named `state` is auto-defaulted to `{}` by the runtime the same way `query` is auto-defaulted to `""` (§7) -- it is not read from the node's JSON spec.

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

### Dict results and shared state (no more context passthrough)

A node's return value is the input to route extraction above, and separately (§4a), the source of whatever it's declared to write into shared state via `WRITES` -- the two are independent uses of the same value, not one value serving both roles by convention.

Earlier revisions of this contract required a gate/judge node to echo its incoming `context` back out under a `"context"` key in its result, so the next node wouldn't lose it (a bare string/bool route decision would otherwise become the next node's entire `context`). That requirement is gone: shared state (§4a) is not threaded node-to-node as a return value, so there is nothing for a routing-only node to lose. `Binary_Judge_Agent` and the three barrier agents in `safety_agents.py` (`Static_Barrier_Agent`, `Neural_Network_Barrier_Agent`, `Judge_Barrier_Agent`) all declare `WRITES = frozenset()` or `frozenset({"answer"})` and carry no `"context"` key in their result at all -- `state["context"]` simply stays whatever the last retrieval node left it, regardless of which way a routing node routes. This is what makes a "judge sufficiency, retrieve more on 'no'" loop (§8) safe with no extra bookkeeping: the `Binary_Judge_Agent` node's `"no"` route reaches the retrieval node it's chained to with shared state untouched.

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

Every terminal user node is connected to `_final` through a single `done` route. The pipeline's final `output` prefers `state["answer"]` (§4a) when any node wrote it during the run; otherwise it's the output of the node that actually called `_final`. `_final` does not call the LLM and cannot have outgoing routes.

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

The runtime updates `agent.query` and `agent.state` immediately before execution when those attributes exist (§4a) -- not `agent.context`, which (when a class has one at all) is a fixed per-instance value the runtime never touches after construction.

## 8. Retrieval agents and accumulation

`RAG_Agent`, `Keyword_Search_Agent`, and `Hybrid_Agent` (agents.py) are retrieval-only: `run()` never calls the LLM. Deciding what to do with retrieved resources — summarize them, answer from them, judge whether they're sufficient — is a separate node's job (typically `Direct_Answer_Agent` or `Binary_Judge_Agent`).

A retrieval agent reads and writes shared state's `"context"` key (§4a) -- the only key it's declared to write -- which doubles as retrieval memory for the rest of the run:

- Every chunk it renders is tagged with a machine-readable `(id: ...)` marker.
- Before retrieving, it reads the ids already present in `state["context"]`.
- It retrieves only chunks not already tagged with one of those ids, and appends them to the existing text rather than replacing it.

Practically, this means:

- Chaining retrieval nodes directly into one another (`rag_1 -> rag_2 -> ...`, as in §1) never returns the same resource twice, and never loses what an earlier hop found.
- A pipeline with a cycle that loops back through the same retrieval node (permitted per §9 below) exhausts the corpus for that query instead of retrieving the same top-k chunks forever.
- Only the terminal generation node needs to call the LLM — retrieval hops in between do not.
- `Binary_Judge_Agent` can gate that chain: route `"yes"` to a generation node and `"no"` back to another retrieval hop, and `state["context"]` arrives intact either way, because `Binary_Judge_Agent` writes nothing to shared state at all (`WRITES` is empty, §4a) -- there's nothing for it to disturb regardless of which route fires.

`Reranker_Agent` chains into this the same way: it reads candidates from `state["context"]` like any other node in the chain, and recovers individual candidate chunks by parsing the `[Resource N] (id: ...) ...` blocks back out of it (`_parse_resources`, the inverse of `_format_resources`). Connect it directly after `RAG_Agent`, `Keyword_Search_Agent`, or `Hybrid_Agent` to re-rank what they found; it does not take a separate `candidates` constructor field.

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
- A custom agent that should participate in shared state (§4a) declares a `WRITES: frozenset[str]` class attribute naming the namespaced key(s) it owns (a subset of `pipeline._STATE_KEYS`); one that doesn't touch shared state at all (a pure router, a diagnostic-only step) simply omits it, inheriting `Agent`'s default of `frozenset()`.
