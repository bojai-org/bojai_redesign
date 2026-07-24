import { DECISION_ADD_ROUTE_HANDLE } from "./handleIds";
import type { PipelineEdge, PipelineNode } from "../types/pipeline";

export interface ConnectionCandidate {
  sourceNodeId: string;
  targetNodeId: string;
  sourceHandleId: string;
}

export interface ConnectionValidationResult {
  valid: boolean;
  error?: string;
}

/**
 * Structural connection rules, independent of agent type:
 * - both endpoints must exist
 * - no self-connections
 * - no duplicate source-handle-to-target connections
 * - a source handle may carry at most one outgoing edge, EXCEPT the
 *   decision "add route" handle, which is reused for every fallback
 *   connection (it resolves to a different underlying option each time).
 *
 * This single "one edge per handle" rule is what enforces, uniformly:
 * one outgoing "next" edge for normal agents, one "yes" and one "no" edge
 * for Binary Judge, and one edge per decision option.
 */
export function validateConnection(
  candidate: ConnectionCandidate,
  nodes: PipelineNode[],
  edges: PipelineEdge[],
): ConnectionValidationResult {
  const { sourceNodeId, targetNodeId, sourceHandleId } = candidate;

  const sourceExists = nodes.some((node) => node.id === sourceNodeId);
  const targetExists = nodes.some((node) => node.id === targetNodeId);
  if (!sourceExists || !targetExists) {
    return { valid: false, error: "That node no longer exists." };
  }

  if (sourceNodeId === targetNodeId) {
    return { valid: false, error: "A node cannot connect to itself." };
  }

  const isDuplicate = edges.some(
    (edge) =>
      edge.sourceNodeId === sourceNodeId &&
      edge.sourceHandleId === sourceHandleId &&
      edge.targetNodeId === targetNodeId,
  );
  if (isDuplicate) {
    return { valid: false, error: "These nodes are already connected on this route." };
  }

  if (sourceHandleId !== DECISION_ADD_ROUTE_HANDLE) {
    const handleTaken = edges.some(
      (edge) => edge.sourceNodeId === sourceNodeId && edge.sourceHandleId === sourceHandleId,
    );
    if (handleTaken) {
      return { valid: false, error: "This route already has an outgoing connection." };
    }
  }

  return { valid: true };
}
