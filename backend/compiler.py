"""Validation and compilation of BojAI JSON pipeline definitions."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from pipeline import Pipeline


class PipelineContractError(ValueError):
    """Raised when a JSON definition violates contract.md."""


_RESERVED_TOP_LEVEL = {"config", "entrypoint", "nodes", "max_steps"}
_RESERVED_NODE_NAMES = {"config", "entrypoint", "nodes"}


def compile_pipeline(
    source: str | Path | Mapping[str, Any],
    *,
    agent_registry: Mapping[str, Callable[..., Any]],
) -> Pipeline:
    """Validate *source*, construct the graph, and return a runnable Pipeline.

    ``source`` may be a parsed mapping, a JSON string, or a path to a JSON file.
    Agent classes/factories are supplied explicitly through ``agent_registry``.
    """

    raw = _load_source(source)
    normalized = _normalize(raw)
    _validate(normalized, agent_registry)
    return Pipeline(
        definition=normalized,
        agent_registry=agent_registry,
        max_steps=normalized.get("max_steps", 100),
    )


def _load_source(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(source, Mapping):
        return copy.deepcopy(dict(source))

    if isinstance(source, Path):
        return json.loads(source.read_text(encoding="utf-8"))

    if isinstance(source, str):
        candidate = Path(source)
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
        try:
            parsed = json.loads(source)
        except json.JSONDecodeError as exc:
            raise PipelineContractError(
                "source must be a mapping, a JSON string, or a path to a JSON file"
            ) from exc
        if not isinstance(parsed, dict):
            raise PipelineContractError("pipeline JSON root must be an object")
        return parsed

    raise PipelineContractError(
        f"unsupported pipeline source type: {type(source).__name__}"
    )


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert the accepted authoring shape into one canonical graph shape."""

    if "nodes" in raw:
        nodes_raw = raw.get("nodes")
        config = raw.get("config")
        entrypoint = raw.get("entrypoint")
        max_steps = raw.get("max_steps", 100)
    else:
        config = raw.get("config")
        entrypoint = raw.get("entrypoint")
        max_steps = raw.get("max_steps", 100)
        nodes_raw = {
            key: value
            for key, value in raw.items()
            if key not in _RESERVED_TOP_LEVEL
        }

    if not isinstance(nodes_raw, dict):
        raise PipelineContractError("'nodes' must be an object")

    node_ids = list(nodes_raw)
    if entrypoint is None and node_ids:
        entrypoint = node_ids[0]

    normalized_nodes: dict[str, dict[str, Any]] = {}
    for ordinal, (node_id, raw_spec) in enumerate(nodes_raw.items()):
        if not isinstance(raw_spec, dict):
            raise PipelineContractError(f"node {node_id!r} must be an object")

        spec = copy.deepcopy(raw_spec)
        node_type = spec.pop("type", None)
        prev = spec.pop("prev", None)
        query = spec.pop("query", None)
        context = spec.pop("context", spec.pop("Context", None))
        explicit_routes = spec.pop("routes", None)
        next_value = spec.pop("next", None)
        options = spec.get("options")

        routes = _normalize_routes(
            node_id=node_id,
            ordinal=ordinal,
            node_ids=node_ids,
            options=options,
            explicit_routes=explicit_routes,
            next_value=next_value,
            remaining_spec=spec,
        )

        # Fields used only to describe routing are not constructor arguments.
        if isinstance(options, list) and node_type == "Decision_Agent":
            agent_args = {"options": copy.deepcopy(options)}
        else:
            agent_args = {}

        for key, value in spec.items():
            if key == "options" and node_type == "Decision_Agent":
                continue
            if key not in routes:
                agent_args[key] = value

        normalized_spec: dict[str, Any] = {
            "type": node_type,
            "prev": prev,
            "query": query,
            "routes": routes,
            "agent_args": agent_args,
        }
        if context is not None:
            normalized_spec["context"] = context
        normalized_nodes[node_id] = normalized_spec

    if "_final" not in normalized_nodes:
        normalized_nodes["_final"] = {
            "type": "_Static_Agent_Auto",
            "prev": [],
            "query": None,
            "routes": {},
            "agent_args": {},
        }

        terminal_ids = [
            node_id
            for node_id, spec in normalized_nodes.items()
            if node_id != "_final" and not spec["routes"]
        ]
        for node_id in terminal_ids:
            normalized_nodes[node_id]["routes"] = {"done": "_final"}

    ordinal_to_id = {
        str(index): node_id for index, node_id in enumerate(normalized_nodes)
    }

    return {
        "config": config,
        "entrypoint": entrypoint,
        "nodes": normalized_nodes,
        "ordinal_to_id": ordinal_to_id,
        "max_steps": max_steps,
    }


def _normalize_routes(
    *,
    node_id: str,
    ordinal: int,
    node_ids: list[str],
    options: Any,
    explicit_routes: Any,
    next_value: Any,
    remaining_spec: dict[str, Any],
) -> dict[str, str]:
    if explicit_routes is not None:
        if not isinstance(explicit_routes, dict):
            raise PipelineContractError(f"node {node_id!r} routes must be an object")
        return {str(route): _target_id(target, node_ids, node_id) for route, target in explicit_routes.items()}

    if isinstance(next_value, dict):
        return {
            str(route): _target_id(target, node_ids, node_id)
            for route, target in next_value.items()
        }

    if next_value not in (None, -1):
        return {"done": _target_id(next_value, node_ids, node_id)}

    if isinstance(options, list):
        routes: dict[str, str] = {}
        for option in options:
            route = str(option)
            if isinstance(option, int) and not isinstance(option, bool):
                routes[route] = _target_id(option, node_ids, node_id)
            elif route in remaining_spec:
                routes[route] = _target_id(remaining_spec.pop(route), node_ids, node_id)
        return routes

    return {}


def _target_id(target: Any, node_ids: list[str], source_id: str) -> str:
    if isinstance(target, int) and not isinstance(target, bool):
        if target < 0 or target >= len(node_ids):
            raise PipelineContractError(
                f"node {source_id!r} references node ordinal {target}, but valid "
                f"ordinals are 0..{max(len(node_ids) - 1, 0)}"
            )
        return node_ids[target]
    if isinstance(target, str):
        return target
    raise PipelineContractError(
        f"node {source_id!r} has invalid route target {target!r}"
    )


def _validate(
    definition: dict[str, Any],
    agent_registry: Mapping[str, Callable[..., Any]],
) -> None:
    config = definition.get("config")
    if not isinstance(config, dict):
        raise PipelineContractError("top-level 'config' must be an object")
    for required in ("provider", "model"):
        value = config.get(required)
        if not isinstance(value, str) or not value.strip():
            raise PipelineContractError(
                f"config.{required} must be a non-empty string"
            )

    max_steps = definition.get("max_steps")
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps < 1:
        raise PipelineContractError("max_steps must be a positive integer")

    nodes = definition.get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        raise PipelineContractError("pipeline must define at least one node")

    entrypoint = definition.get("entrypoint")
    if not isinstance(entrypoint, str) or entrypoint not in nodes:
        raise PipelineContractError("entrypoint must name an existing node")
    if entrypoint == "_final":
        raise PipelineContractError("entrypoint cannot be '_final'")

    for node_id, spec in nodes.items():
        if not isinstance(node_id, str) or not node_id:
            raise PipelineContractError("every node ID must be a non-empty string")
        if node_id in _RESERVED_NODE_NAMES:
            raise PipelineContractError(f"node ID {node_id!r} is reserved")

        node_type = spec.get("type")
        if not isinstance(node_type, str) or not node_type:
            raise PipelineContractError(f"node {node_id!r} must define a type")
        if node_type not in agent_registry:
            raise PipelineContractError(
                f"node {node_id!r} uses unregistered agent type {node_type!r}"
            )

        prev = spec.get("prev")
        _validate_prev(node_id, prev, nodes, definition["ordinal_to_id"])

        query = spec.get("query")
        if query is not None and not isinstance(query, (str, int)):
            raise PipelineContractError(
                f"node {node_id!r} query must be a string, integer reference, or null"
            )
        if isinstance(query, bool):
            raise PipelineContractError(
                f"node {node_id!r} query cannot be a boolean"
            )
        if isinstance(query, int) and str(query) not in definition["ordinal_to_id"]:
            raise PipelineContractError(
                f"node {node_id!r} query references unknown ordinal {query}"
            )

        routes = spec.get("routes")
        if not isinstance(routes, dict):
            raise PipelineContractError(f"node {node_id!r} routes must be an object")
        for route, target in routes.items():
            if not isinstance(route, str) or not route:
                raise PipelineContractError(
                    f"node {node_id!r} has an empty or non-string route"
                )
            if target not in nodes:
                raise PipelineContractError(
                    f"node {node_id!r} route {route!r} targets unknown node {target!r}"
                )

    if nodes["_final"]["routes"]:
        raise PipelineContractError("'_final' cannot have outgoing routes")

    _validate_prev_matches_routes(definition)
    _validate_reachability(definition)


def _validate_prev(
    node_id: str,
    prev: Any,
    nodes: Mapping[str, Any],
    ordinal_to_id: Mapping[str, str],
) -> None:
    if node_id == "_final":
        return
    if prev in (None, -1):
        return
    values = prev if isinstance(prev, list) else [prev]
    if not values:
        raise PipelineContractError(f"node {node_id!r} prev cannot be empty")
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise PipelineContractError(
                f"node {node_id!r} prev entries must be node IDs or integer ordinals"
            )
        resolved = ordinal_to_id.get(str(value)) if isinstance(value, int) else value
        if resolved not in nodes:
            raise PipelineContractError(
                f"node {node_id!r} prev references unknown node {value!r}"
            )


def _validate_prev_matches_routes(definition: Mapping[str, Any]) -> None:
    nodes = definition["nodes"]
    ordinal_to_id = definition["ordinal_to_id"]
    incoming: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    for source_id, spec in nodes.items():
        for target_id in spec["routes"].values():
            incoming[target_id].add(source_id)

    for node_id, spec in nodes.items():
        if node_id in {definition["entrypoint"], "_final"}:
            continue
        prev = spec.get("prev")
        if prev in (None, -1):
            continue
        values = prev if isinstance(prev, list) else [prev]
        declared = {
            ordinal_to_id[str(value)] if isinstance(value, int) else value
            for value in values
        }
        if declared != incoming[node_id]:
            raise PipelineContractError(
                f"node {node_id!r} declares prev={sorted(declared)}, but its actual "
                f"incoming routes are {sorted(incoming[node_id])}. A prev list means "
                "the node may be called by any one of those predecessors."
            )


def _validate_reachability(definition: Mapping[str, Any]) -> None:
    nodes = definition["nodes"]
    pending = [definition["entrypoint"]]
    visited: set[str] = set()
    while pending:
        node_id = pending.pop()
        if node_id in visited:
            continue
        visited.add(node_id)
        pending.extend(nodes[node_id]["routes"].values())

    unreachable = set(nodes) - visited
    if unreachable:
        raise PipelineContractError(
            f"unreachable nodes from entrypoint: {sorted(unreachable)}"
        )
    if "_final" not in visited:
        raise PipelineContractError("no route from entrypoint reaches '_final'")
