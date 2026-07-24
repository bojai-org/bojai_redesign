import { syncDecisionOptionsAfterEdgeRemoval } from "./syncDecisionEdge";
import type { PipelineEdge, PipelineNode } from "../types/pipeline";

/**
 * Removes a node and every edge touching it (incoming or outgoing), then
 * applies the same decision-option cleanup rules edge deletion uses — this
 * matters when the deleted node was the target of another node's decision
 * edge (Case 6 applies to that severed connection too).
 */
export function removeNodeAndConnectedEdges(
  nodes: PipelineNode[],
  edges: PipelineEdge[],
  nodeId: string,
): { nodes: PipelineNode[]; edges: PipelineEdge[] } {
  const removedEdges = edges.filter(
    (edge) => edge.sourceNodeId === nodeId || edge.targetNodeId === nodeId,
  );
  const remainingEdges = edges.filter(
    (edge) => edge.sourceNodeId !== nodeId && edge.targetNodeId !== nodeId,
  );
  const remainingNodes = nodes.filter((node) => node.id !== nodeId);

  const syncedNodes = syncDecisionOptionsAfterEdgeRemoval(
    remainingNodes,
    remainingEdges,
    removedEdges,
  );

  return { nodes: syncedNodes, edges: remainingEdges };
}
