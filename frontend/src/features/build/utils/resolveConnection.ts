import { createPipelineEdge } from "./createPipelineEdge";
import { parseStaticRouteHandleId } from "./handleIds";
import { syncDecisionEdge } from "./syncDecisionEdge";
import { validateConnection } from "./validateConnection";
import type { ConnectionCandidate } from "./validateConnection";
import type { PipelineEdge, PipelineNode } from "../types/pipeline";

export type ResolveConnectionResult =
  | { ok: true; edge: PipelineEdge; updatedNode?: PipelineNode }
  | { ok: false; error: string };

/**
 * Turns a raw connection gesture into a validated domain edge (and, for
 * Decision_Agent sources, a possibly-updated node with a new auto option).
 * All decision-option/edge synchronization logic lives here and in
 * syncDecisionEdge.ts — rendering components only call this and apply the
 * result to state.
 */
export function resolveConnection(
  candidate: ConnectionCandidate,
  nodes: PipelineNode[],
  edges: PipelineEdge[],
): ResolveConnectionResult {
  const validation = validateConnection(candidate, nodes, edges);
  if (!validation.valid) {
    return { ok: false, error: validation.error ?? "That connection isn't allowed." };
  }

  const sourceNode = nodes.find((node) => node.id === candidate.sourceNodeId);
  const targetNode = nodes.find((node) => node.id === candidate.targetNodeId);
  if (!sourceNode || !targetNode) {
    return { ok: false, error: "That node no longer exists." };
  }

  if (sourceNode.data.agentType === "Decision_Agent") {
    const { node, edge } = syncDecisionEdge({
      decisionNode: sourceNode,
      targetNode,
      sourceHandleId: candidate.sourceHandleId,
      existingEdges: edges,
    });
    return { ok: true, edge, updatedNode: node !== sourceNode ? node : undefined };
  }

  const edge = createPipelineEdge({
    sourceNodeId: candidate.sourceNodeId,
    targetNodeId: candidate.targetNodeId,
    sourceHandleId: candidate.sourceHandleId,
    routeId: parseStaticRouteHandleId(candidate.sourceHandleId),
  });
  return { ok: true, edge };
}
