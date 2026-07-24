"""Runtime pipeline object returned by the BojAI JSON compiler.

The compiler validates and normalizes a JSON pipeline, then constructs this
Pipeline. ``Pipeline.run`` calls ``flow`` once, executes the graph, and passes
the top-level provider/model configuration to every agent ``run`` invocation.
"""

from __future__ import annotations

import copy
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


class PipelineRuntimeError(RuntimeError):
    """Raised when a compiled pipeline cannot be executed safely."""


@dataclass(slots=True)
class ExecutionStep:
    node_id: str
    result: Any
    route: str | None
    next_node_id: str | None


@dataclass(slots=True)
class PipelineResult:
    """The value returned by ``Pipeline.run``.

    ``output`` is the final user-facing value. ``trace`` is intentionally kept
    small and serializable so the builder UI can display what happened.
    """

    output: Any
    trace: list[ExecutionStep] = field(default_factory=list)
    node_outputs: dict[str, Any] = field(default_factory=dict)


class _RouteBuilder:
    def __init__(self, source: "CompiledNode", route: str) -> None:
        self.source = source
        self.route = route

    def __rshift__(self, target: "CompiledNode") -> "CompiledNode":
        self.source.routes[self.route] = target
        return target


@dataclass
class CompiledNode:
    """A runtime wrapper around one configured agent instance."""

    node_id: str
    ordinal: int
    spec: dict[str, Any]
    agent: Any
    routes: dict[str, "CompiledNode"] = field(default_factory=dict)

    def __sub__(self, route: object) -> _RouteBuilder:
        return _RouteBuilder(self, str(route))


class Pipeline:
    """Executable graph produced by :func:`compiler.compile_pipeline`.

    Parameters are deliberately registry-based. The compiler does not import a
    project-specific ``agents.py`` module and therefore does not assume where
    user agent classes live.
    """

    def __init__(
        self,
        *,
        definition: Mapping[str, Any],
        agent_registry: Mapping[str, Callable[..., Any]],
        max_steps: int = 100,
    ) -> None:
        self.definition = copy.deepcopy(dict(definition))
        self.agent_registry = dict(agent_registry)
        self.max_steps = max_steps
        self._nodes: dict[str, CompiledNode] | None = None

    @property
    def config(self) -> dict[str, Any]:
        return copy.deepcopy(self.definition["config"])

    @property
    def nodes(self) -> Mapping[str, CompiledNode]:
        if self._nodes is None:
            self.flow()
        assert self._nodes is not None
        return self._nodes

    def flow(self) -> Mapping[str, CompiledNode]:
        """Instantiate every agent and connect the validated routing graph.

        Connections are made through the same readable DSL used by handwritten
        pipelines::

            source - "route" >> target
        """

        if self._nodes is not None:
            return self._nodes

        built: dict[str, CompiledNode] = {}
        node_specs: Mapping[str, dict[str, Any]] = self.definition["nodes"]

        for ordinal, (node_id, spec) in enumerate(node_specs.items()):
            agent_type = spec["type"]
            factory = self.agent_registry[agent_type]
            kwargs = copy.deepcopy(spec.get("agent_args", {}))
            agent = self._instantiate_agent(factory, kwargs, node_id)
            built[node_id] = CompiledNode(
                node_id=node_id,
                ordinal=ordinal,
                spec=copy.deepcopy(spec),
                agent=agent,
            )

        for source_id, spec in node_specs.items():
            source = built[source_id]
            for route, target_id in spec.get("routes", {}).items():
                source - route >> built[target_id]

        self._nodes = built
        return built

    async def run(self, initial_query: str | None = None) -> PipelineResult:
        """Execute the compiled graph and return its final value and trace."""

        nodes = self.flow()
        current = nodes[self.definition["entrypoint"]]
        outputs: dict[str, Any] = {}
        effective_queries: dict[str, Any] = {}
        trace: list[ExecutionStep] = []
        caller_id: str | None = None

        for _ in range(self.max_steps):
            spec = current.spec

            if current.node_id == "_final":
                final_output = outputs.get(caller_id) if caller_id else None
                outputs[current.node_id] = final_output
                trace.append(ExecutionStep(current.node_id, final_output, None, None))
                return PipelineResult(final_output, trace, outputs)

            query = self._resolve_query(
                spec=spec,
                current=current,
                caller_id=caller_id,
                initial_query=initial_query,
                effective_queries=effective_queries,
            )
            context = self._resolve_context(
                spec=spec,
                caller_id=caller_id,
                outputs=outputs,
            )
            effective_queries[current.node_id] = query

            if hasattr(current.agent, "query"):
                current.agent.query = query
            if hasattr(current.agent, "context"):
                current.agent.context = context

            result = await self._run_agent(current.agent)
            outputs[current.node_id] = result

            route = self._select_route(current, result)
            target = current.routes.get(route) if route is not None else None
            trace.append(
                ExecutionStep(
                    node_id=current.node_id,
                    result=result,
                    route=route,
                    next_node_id=target.node_id if target else None,
                )
            )

            if target is None:
                return PipelineResult(result, trace, outputs)

            caller_id = current.node_id
            current = target

        raise PipelineRuntimeError(
            f"Pipeline exceeded max_steps={self.max_steps}; a route cycle may not terminate."
        )

    def _instantiate_agent(
        self,
        factory: Callable[..., Any],
        kwargs: dict[str, Any],
        node_id: str,
    ) -> Any:
        try:
            signature = inspect.signature(factory)
            parameters = signature.parameters
            if "query" in parameters and "query" not in kwargs:
                kwargs["query"] = ""
            if "context" in parameters and "context" not in kwargs:
                kwargs["context"] = ""
            return factory(**kwargs)
        except (TypeError, ValueError) as exc:
            raise PipelineRuntimeError(
                f"Could not instantiate node {node_id!r}: {exc}"
            ) from exc

    async def _run_agent(self, agent: Any) -> Any:
        run_method = getattr(agent, "run", None)
        if not callable(run_method):
            raise PipelineRuntimeError(
                f"Agent {type(agent).__name__} does not define callable run()."
            )

        config = self.config
        try:
            signature = inspect.signature(run_method)
            accepts_config = len(signature.parameters) >= 1
        except (TypeError, ValueError):
            accepts_config = True

        result = run_method(config) if accepts_config else run_method()
        if inspect.isawaitable(result):
            return await result
        return result

    def _resolve_query(
        self,
        *,
        spec: Mapping[str, Any],
        current: CompiledNode,
        caller_id: str | None,
        initial_query: str | None,
        effective_queries: Mapping[str, Any],
    ) -> Any:
        query = spec.get("query")

        if isinstance(query, int) and not isinstance(query, bool):
            referenced_id = self.definition["ordinal_to_id"][str(query)]
            if referenced_id in effective_queries:
                return effective_queries[referenced_id]
            referenced_spec = self.definition["nodes"][referenced_id]
            referenced_query = referenced_spec.get("query")
            if isinstance(referenced_query, str):
                return referenced_query
            if initial_query is not None:
                return initial_query
            raise PipelineRuntimeError(
                f"Node {current.node_id!r} references query from node {referenced_id!r}, "
                "but that query is not available yet."
            )

        if isinstance(query, str):
            return query

        if caller_id and caller_id in effective_queries:
            return effective_queries[caller_id]
        if initial_query is not None:
            return initial_query
        return ""

    @staticmethod
    def _resolve_context(
        *,
        spec: Mapping[str, Any],
        caller_id: str | None,
        outputs: Mapping[str, Any],
    ) -> str:
        if caller_id is None and "context" in spec:
            return str(spec["context"])
        if caller_id is None:
            return ""
        value = outputs.get(caller_id, "")
        if isinstance(value, str):
            return value
        # A gate/judge agent (e.g. Binary_Judge_Agent) returns a dict so its verdict
        # can drive routing without losing what it was actually judging: if that
        # dict carries a "context" key, forward that instead of str()-ing the whole
        # dict, so the resources it evaluated survive into whichever route is taken.
        if isinstance(value, Mapping) and isinstance(value.get("context"), str):
            return value["context"]
        return str(value)

    @staticmethod
    def _select_route(node: CompiledNode, result: Any) -> str | None:
        if not node.routes:
            return None

        candidates: list[str] = []
        if isinstance(result, str):
            candidates.append(result)
        elif isinstance(result, bool):
            candidates.extend(["yes" if result else "no", str(result).lower()])
        elif isinstance(result, int):
            candidates.append(str(result))
        elif isinstance(result, Mapping):
            for key in ("route", "decision", "action", "result"):
                value = result.get(key)
                if isinstance(value, (str, int, bool)):
                    candidates.append(str(value))

        for candidate in candidates:
            if candidate in node.routes:
                return candidate

        if len(node.routes) == 1:
            return next(iter(node.routes))

        raise PipelineRuntimeError(
            f"Node {node.node_id!r} returned {result!r}, which does not match any "
            f"declared route: {sorted(node.routes)}."
        )
