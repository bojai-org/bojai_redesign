import { AGENT_CONTRACTS, STATIC_ROUTE_LABELS } from "../contracts/agentContracts";
import { findEntryNodeIds } from "./serializePipelineForCompiler";
import { getDecisionOptions } from "./getDecisionOptions";
import { validatePipelineNode } from "./validatePipelineNode";
import type { BuildValidationError } from "../types/compiler";
import type {
  PipelineEdge,
  PipelineNode,
  PipelineRuntimeConfig,
  QuerySource,
} from "../types/pipeline";

/** backend/compiler.py's _RESERVED_NODE_NAMES, plus "_final" (reserved separately). */
const RESERVED_NODE_IDS = new Set(["config", "entrypoint", "nodes", "_final"]);

function isQuerySource(value: unknown): value is QuerySource {
  return typeof value === "object" && value !== null && "mode" in value;
}

/**
 * Everything that must hold before serializePipelineForCompiler's output is
 * worth sending to the backend. Covers what compile_pipeline itself would
 * reject (contract.md section 9) plus graph-shape problems the compiler
 * can't see: an unconnected Decision option or a half-wired Binary Judge
 * don't violate the contract, they just risk the runtime's "sole declared
 * route" leniency rule silently misrouting around whatever the LLM actually
 * decided (contract.md section 5).
 */
export function validatePipelineGraph(
  nodes: PipelineNode[],
  edges: PipelineEdge[],
  runtimeConfig: PipelineRuntimeConfig,
): BuildValidationError[] {
  const errors: BuildValidationError[] = [];

  if (nodes.length === 0) {
    errors.push({ code: "no-nodes", message: "Add at least one node to the canvas." });
    return errors;
  }

  if (!runtimeConfig.provider.trim()) {
    errors.push({ code: "missing-provider", message: "Provider is required.", field: "provider" });
  }
  if (!runtimeConfig.model.trim()) {
    errors.push({ code: "missing-model", message: "Model is required.", field: "model" });
  }

  for (const node of nodes) {
    if (RESERVED_NODE_IDS.has(node.id)) {
      errors.push({
        code: "reserved-node-id",
        message: `"${node.id}" is a reserved id on the backend and cannot be used for a node.`,
        nodeId: node.id,
      });
    }
  }

  const nodeIds = new Set(nodes.map((node) => node.id));
  for (const edge of edges) {
    if (!nodeIds.has(edge.sourceNodeId) || !nodeIds.has(edge.targetNodeId)) {
      errors.push({
        code: "dangling-edge",
        message: "This connection references a node that no longer exists.",
        edgeId: edge.id,
      });
    }
  }

  const entryIds = findEntryNodeIds(nodes, edges);
  if (entryIds.length === 0) {
    errors.push({
      code: "no-entrypoint",
      message:
        "No entry node found: every node has an incoming connection. The pipeline needs one node with no incoming connections to start from.",
    });
  } else if (entryIds.length > 1) {
    for (const nodeId of entryIds) {
      errors.push({
        code: "multiple-entrypoints",
        message:
          "Multiple nodes have no incoming connection. A pipeline needs exactly one entry point.",
        nodeId,
      });
    }
  }

  for (const node of nodes) {
    const contract = AGENT_CONTRACTS[node.data.agentType];
    const { fieldErrors } = validatePipelineNode(node, contract);
    for (const [field, message] of Object.entries(fieldErrors)) {
      errors.push({ code: "invalid-field", message, nodeId: node.id, field });
    }
  }

  for (const node of nodes) {
    const contract = AGENT_CONTRACTS[node.data.agentType];
    const outgoing = edges.filter((edge) => edge.sourceNodeId === node.id);

    if (contract.dynamicRoutes) {
      // Decision_Agent: every configured option needs its own connected target.
      const options = getDecisionOptions(node);
      const optionIds = new Set(options.map((option) => option.id));
      const connectedOptionIds = new Set(
        outgoing.filter((edge) => edge.routeId).map((edge) => edge.routeId as string),
      );

      for (const option of options) {
        const label = option.label.trim();
        if (!label) continue; // already reported by field validation above
        if (!connectedOptionIds.has(option.id)) {
          errors.push({
            code: "decision-option-unconnected",
            message: `Option "${label}" has no connected destination.`,
            nodeId: node.id,
            field: "options",
          });
        }
      }

      for (const edge of outgoing) {
        if (edge.routeId && !optionIds.has(edge.routeId)) {
          errors.push({
            code: "dangling-edge",
            message: "This connection's option no longer exists on the node.",
            edgeId: edge.id,
          });
        }
      }
    } else if (contract.outputRoutes.length > 1) {
      // Any agent with more than one fixed possible outcome (Binary_Judge_Agent,
      // the safety barriers, ...) needs every outcome connected -- leaving one
      // unwired risks the runtime's "sole declared route" leniency rule
      // silently rerouting around whatever the agent actually decided
      // (contract.md section 5, "Dict results and context passthrough").
      const connectedRoutes = new Set(outgoing.map((edge) => edge.routeId));
      for (const route of contract.outputRoutes) {
        if (!connectedRoutes.has(route)) {
          errors.push({
            code: "route-unconnected",
            message: `"${STATIC_ROUTE_LABELS[route] ?? route}" route is not connected.`,
            nodeId: node.id,
          });
        }
      }
    }
    // Every other agent type has a single "next" route: zero or one outgoing
    // edge are both valid (a node with none becomes a terminal node whose
    // output is the pipeline's final answer -- contract.md section 6).
  }

  for (const node of nodes) {
    const contract = AGENT_CONTRACTS[node.data.agentType];
    const queryField = contract.fields.find((field) => field.key === "query");
    if (queryField?.type !== "query-source") continue;

    const raw = node.data.config.query;
    if (!isQuerySource(raw) || raw.mode !== "node" || !raw.nodeId) continue;

    if (raw.nodeId === node.id) {
      errors.push({
        code: "self-query-reference",
        message: "A node cannot reuse its own query.",
        nodeId: node.id,
        field: "query",
      });
    } else if (!nodeIds.has(raw.nodeId)) {
      errors.push({
        code: "dangling-query-reference",
        message: "This reuses the query from a node that no longer exists.",
        nodeId: node.id,
        field: "query",
      });
    }
  }

  if (entryIds.length === 1) {
    const reachable = new Set<string>();
    const queue = [entryIds[0]];
    while (queue.length > 0) {
      const current = queue.shift()!;
      if (reachable.has(current)) continue;
      reachable.add(current);
      for (const edge of edges) {
        if (edge.sourceNodeId === current) queue.push(edge.targetNodeId);
      }
    }
    for (const node of nodes) {
      if (!reachable.has(node.id)) {
        errors.push({
          code: "unreachable-node",
          message: "This node is not reachable from the entry node.",
          nodeId: node.id,
        });
      }
    }
  }

  return errors;
}
