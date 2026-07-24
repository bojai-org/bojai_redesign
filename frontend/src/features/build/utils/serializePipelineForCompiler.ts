import { AGENT_CONTRACTS } from "../contracts/agentContracts";
import { getDecisionOptions } from "./getDecisionOptions";
import type {
  CompilerNodeDefinition,
  CompilerPipelineDefinition,
} from "../types/compiler";
import type {
  AgentFieldContract,
  PipelineEdge,
  PipelineNode,
  PipelineRuntimeConfig,
  QuerySource,
} from "../types/pipeline";

/**
 * Thrown only when a definition genuinely cannot be constructed -- there is
 * no node to serve as `entrypoint`, or the graph has no single node with zero
 * incoming edges to treat as one. Every other kind of incompleteness (a
 * missing corpus address, an unconnected Decision option, a dangling query
 * reference, ...) is left to validatePipelineGraph: this function still
 * produces a best-effort definition for those cases, so "Preview JSON" stays
 * useful while a pipeline is mid-edit.
 */
export class PipelineSerializationError extends Error {}

export interface SerializePipelineParams {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  runtimeConfig: PipelineRuntimeConfig;
}

/** Nodes with zero incoming edges -- the same definition BuildPage already uses for "entry node". */
export function findEntryNodeIds(nodes: PipelineNode[], edges: PipelineEdge[]): string[] {
  const hasIncoming = new Set(edges.map((edge) => edge.targetNodeId));
  return nodes.filter((node) => !hasIncoming.has(node.id)).map((node) => node.id);
}

/**
 * Deterministic node order: entry node first, then a breadth-first walk
 * following the graph's edges, then any node the walk never reached
 * (disconnected from the entry node) appended in their original array order.
 * This order becomes the `nodes` object's key order, which is exactly what
 * fixes each node's backend ordinal (declaration order, per contract.md
 * section 3) -- so it must also be the order used to resolve any `query`
 * node-reference into that same ordinal.
 */
export function computeSerializationOrder(
  nodes: PipelineNode[],
  edges: PipelineEdge[],
): string[] {
  if (nodes.length === 0) return [];

  const [entryId] = findEntryNodeIds(nodes, edges);
  const startId = entryId ?? nodes[0].id;

  const outgoingByTarget = new Map<string, string[]>();
  for (const edge of edges) {
    const targets = outgoingByTarget.get(edge.sourceNodeId) ?? [];
    targets.push(edge.targetNodeId);
    outgoingByTarget.set(edge.sourceNodeId, targets);
  }

  const order: string[] = [];
  const visited = new Set<string>();
  const queue = [startId];
  while (queue.length > 0) {
    const current = queue.shift()!;
    if (visited.has(current)) continue;
    visited.add(current);
    order.push(current);
    for (const targetId of outgoingByTarget.get(current) ?? []) {
      if (!visited.has(targetId)) queue.push(targetId);
    }
  }

  for (const node of nodes) {
    if (!visited.has(node.id)) order.push(node.id);
  }

  return order;
}

/** node id -> backend declaration-order ordinal, per the same order serializePipelineForCompiler uses. */
export function buildNodeOrdinalMap(
  nodes: PipelineNode[],
  edges: PipelineEdge[],
): Record<string, number> {
  const order = computeSerializationOrder(nodes, edges);
  const map: Record<string, number> = {};
  order.forEach((nodeId, index) => {
    map[nodeId] = index;
  });
  return map;
}

function isQuerySource(value: unknown): value is QuerySource {
  return typeof value === "object" && value !== null && "mode" in value;
}

/** The route key an outgoing edge serializes under: an option's trimmed label for
 * Decision_Agent sources, or the edge's own routeId (already the static route name,
 * e.g. "next"/"yes"/"no") for everything else. */
function routeKeyForEdge(sourceNode: PipelineNode, edge: PipelineEdge): string | null {
  if (sourceNode.data.agentType === "Decision_Agent") {
    const option = getDecisionOptions(sourceNode).find((candidate) => candidate.id === edge.routeId);
    const label = option?.label.trim();
    return label ? label : null;
  }
  return edge.routeId ?? null;
}

function serializeQueryField(
  node: PipelineNode,
  field: AgentFieldContract,
  ordinalOf: Record<string, number>,
): string | number | undefined {
  const raw = node.data.config[field.key];

  if (field.type !== "query-source") {
    // Decision_Agent / Binary_Judge_Agent / Simple_Task_Agent / Static_Agent:
    // `query` is always a plain literal string field.
    const text = typeof raw === "string" ? raw.trim() : "";
    return text ? text : undefined;
  }

  if (!isQuerySource(raw)) return undefined;

  if (raw.mode === "pipeline-input") return undefined; // inherit -- omitting the field is the backend's own default
  if (raw.mode === "custom") return raw.value.trim() ? raw.value : undefined;
  if (raw.mode === "node") {
    const ordinal = ordinalOf[raw.nodeId];
    // A dangling reference (deleted node) is a validation concern, not a
    // serialization failure -- fall back to inheriting rather than emitting
    // a nonsensical ordinal.
    return ordinal === undefined ? undefined : ordinal;
  }
  return undefined;
}

function serializeAgentArgs(node: PipelineNode): Partial<CompilerNodeDefinition> {
  const config = node.data.config;
  switch (node.data.agentType) {
    case "Decision_Agent":
      return {
        options: getDecisionOptions(node)
          .map((option) => option.label.trim())
          .filter((label) => label.length > 0),
      };
    case "RAG_Agent":
    case "Keyword_Search_Agent":
    case "Hybrid_Agent": {
      const args: Partial<CompilerNodeDefinition> = {};
      if (typeof config.corpus_address === "string" && config.corpus_address.trim()) {
        args.corpus_address = config.corpus_address;
      }
      if (typeof config.top_k === "number" && Number.isFinite(config.top_k)) {
        args.top_k = config.top_k;
      }
      return args;
    }
    case "Reranker_Agent": {
      // No corpus_address: it reranks whatever resources it inherited in
      // context from an upstream retrieval node (backend/agents.py parses
      // candidates out of that string itself -- see _parse_resources).
      const args: Partial<CompilerNodeDefinition> = {};
      if (typeof config.top_k === "number" && Number.isFinite(config.top_k)) {
        args.top_k = config.top_k;
      }
      return args;
    }
    case "Static_Agent": {
      const args: Partial<CompilerNodeDefinition> = {};
      if (typeof config.message === "string") args.message = config.message;
      return args;
    }
    case "Binary_Judge_Agent":
    case "Direct_Answer_Agent":
    case "Simple_Task_Agent":
    case "Static_Barrier_Agent":
    case "Judge_Barrier_Agent":
      return {};
    default:
      return {};
  }
}

function serializeRoutes(
  node: PipelineNode,
  edges: PipelineEdge[],
): Record<string, string> | undefined {
  const outgoing = edges.filter((edge) => edge.sourceNodeId === node.id);
  if (outgoing.length === 0) return undefined; // terminal -- compiler auto-wires this to _final

  const routes: Record<string, string> = {};
  for (const edge of outgoing) {
    const routeKey = routeKeyForEdge(node, edge);
    if (routeKey) routes[routeKey] = edge.targetNodeId;
  }
  return Object.keys(routes).length > 0 ? routes : undefined;
}

/**
 * Pure transform from the Build canvas's domain graph into exactly the shape
 * compile_pipeline(definition, agent_registry=AGENT_REGISTRY) accepts (see
 * backend/contract.md and backend/compiler.py). Never mutates its inputs.
 *
 * This does not validate the graph -- call validatePipelineGraph first (or
 * alongside) to decide whether the graph is actually ready to compile. This
 * function stays maximally tolerant of incompleteness (missing fields,
 * unconnected routes, dangling query references) so a live "Preview JSON"
 * keeps working mid-edit; it only throws when no definition can be built at
 * all (no nodes, or no resolvable entry node).
 */
export function serializePipelineForCompiler({
  nodes,
  edges,
  runtimeConfig,
}: SerializePipelineParams): CompilerPipelineDefinition {
  if (nodes.length === 0) {
    throw new PipelineSerializationError("Add at least one node before compiling.");
  }

  const entryIds = findEntryNodeIds(nodes, edges);
  if (entryIds.length === 0) {
    throw new PipelineSerializationError(
      "No entry node found: every node has an incoming connection.",
    );
  }

  const order = computeSerializationOrder(nodes, edges);
  const ordinalOf = buildNodeOrdinalMap(nodes, edges);
  const nodesById = new Map(nodes.map((node) => [node.id, node]));
  const entryNodeId = order[0];

  const definitionNodes: Record<string, CompilerNodeDefinition> = {};

  for (const nodeId of order) {
    const node = nodesById.get(nodeId);
    if (!node) continue; // defensive; every id in `order` comes from `nodes`

    const contract = AGENT_CONTRACTS[node.data.agentType];
    const queryField = contract.fields.find((field) => field.key === "query");
    const isEntryNode = nodeId === entryNodeId;

    const incomingSourceIds = [...new Set(edges.filter((edge) => edge.targetNodeId === nodeId).map((edge) => edge.sourceNodeId))].sort(
      (a, b) => (ordinalOf[a] ?? 0) - (ordinalOf[b] ?? 0),
    );

    const definition: CompilerNodeDefinition = { type: node.data.agentType };

    if (!isEntryNode && incomingSourceIds.length > 0) {
      definition.prev = incomingSourceIds.length === 1 ? incomingSourceIds[0] : incomingSourceIds;
    }
    // isEntryNode with zero incoming edges: `prev` omitted, equivalent to backend `-1`.

    if (queryField) {
      const query = serializeQueryField(node, queryField, ordinalOf);
      if (query !== undefined) definition.query = query;
    }

    if (isEntryNode && contract.fields.some((field) => field.key === "context" && field.entryOnly)) {
      const context = node.data.config.context;
      if (typeof context === "string" && context.trim()) definition.context = context;
    }

    Object.assign(definition, serializeAgentArgs(node));

    const routes = serializeRoutes(node, edges);
    if (routes) definition.routes = routes;

    definitionNodes[nodeId] = definition;
  }

  return {
    config: {
      provider: runtimeConfig.provider,
      model: runtimeConfig.model,
    },
    entrypoint: entryNodeId,
    nodes: definitionNodes,
  };
}
