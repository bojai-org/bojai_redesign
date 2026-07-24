import { createDecisionOption } from "./createDecisionOption";
import { createPipelineEdge } from "./createPipelineEdge";
import { createUniqueOptionLabel } from "./createUniqueOptionLabel";
import { getDecisionOptions, setDecisionOptions } from "./getDecisionOptions";
import { decisionOptionHandleId, parseDecisionOptionHandleId } from "./handleIds";
import type { PipelineEdge, PipelineNode } from "../types/pipeline";

export interface SyncDecisionEdgeResult {
  /** The decision node, unchanged (reference-equal) unless a new auto option was appended. */
  node: PipelineNode;
  edge: PipelineEdge;
}

/**
 * Resolves a new outgoing connection dragged from a Decision node's source
 * handle into a concrete DecisionOption + PipelineEdge pair.
 *
 * - Dragging from a specific option's own handle (`decision-option:<id>`)
 *   binds deterministically to that option.
 * - Dragging from the add-route handle resolves to the first option with no
 *   outgoing edge yet, in array order; if every option is already
 *   connected (or none exist), a new "auto" option named after the target
 *   node is appended.
 */
export function syncDecisionEdge(params: {
  decisionNode: PipelineNode;
  targetNode: PipelineNode;
  sourceHandleId: string;
  existingEdges: PipelineEdge[];
}): SyncDecisionEdgeResult {
  const { decisionNode, targetNode, sourceHandleId, existingEdges } = params;
  const options = getDecisionOptions(decisionNode);

  const explicitOptionId = parseDecisionOptionHandleId(sourceHandleId);
  if (explicitOptionId) {
    const edge = createPipelineEdge({
      sourceNodeId: decisionNode.id,
      targetNodeId: targetNode.id,
      sourceHandleId: decisionOptionHandleId(explicitOptionId),
      routeId: explicitOptionId,
      routeIndex: options.findIndex((option) => option.id === explicitOptionId),
    });
    return { node: decisionNode, edge };
  }

  const connectedOptionIds = new Set(
    existingEdges
      .filter((edge) => edge.sourceNodeId === decisionNode.id && edge.routeId)
      .map((edge) => edge.routeId as string),
  );
  const nextFreeOption = options.find((option) => !connectedOptionIds.has(option.id));

  if (nextFreeOption) {
    const edge = createPipelineEdge({
      sourceNodeId: decisionNode.id,
      targetNodeId: targetNode.id,
      sourceHandleId: decisionOptionHandleId(nextFreeOption.id),
      routeId: nextFreeOption.id,
      routeIndex: options.indexOf(nextFreeOption),
    });
    return { node: decisionNode, edge };
  }

  const newOption = createDecisionOption(targetNode.data.label, options, "auto", targetNode.id);
  const updatedNode = setDecisionOptions(decisionNode, [...options, newOption]);
  const edge = createPipelineEdge({
    sourceNodeId: decisionNode.id,
    targetNodeId: targetNode.id,
    sourceHandleId: decisionOptionHandleId(newOption.id),
    routeId: newOption.id,
    routeIndex: options.length,
  });
  return { node: updatedNode, edge };
}

/**
 * Applies the decision-option cleanup rules for edges that are about to be
 * removed (Case 6): manual options and pre-existing unconnected options are
 * always preserved; an "auto" option is removed only when the one edge it
 * was created for is among those being removed and nothing else still
 * references it.
 */
export function syncDecisionOptionsAfterEdgeRemoval(
  nodes: PipelineNode[],
  remainingEdges: PipelineEdge[],
  removedEdges: PipelineEdge[],
): PipelineNode[] {
  const decisionNodeIds = new Set(
    removedEdges.filter((edge) => edge.routeId).map((edge) => edge.sourceNodeId),
  );
  if (decisionNodeIds.size === 0) return nodes;

  const stillConnectedOptionIds = new Set(
    remainingEdges.filter((edge) => edge.routeId).map((edge) => edge.routeId as string),
  );

  return nodes.map((node) => {
    if (!decisionNodeIds.has(node.id)) return node;

    const removedOptionIdsForNode = new Set(
      removedEdges
        .filter((edge) => edge.sourceNodeId === node.id && edge.routeId)
        .map((edge) => edge.routeId as string),
    );
    if (removedOptionIdsForNode.size === 0) return node;

    const options = getDecisionOptions(node);
    const nextOptions = options.filter((option) => {
      if (!removedOptionIdsForNode.has(option.id)) return true;
      if (stillConnectedOptionIds.has(option.id)) return true;
      return option.origin !== "auto";
    });

    if (nextOptions.length === options.length) return node;
    return setDecisionOptions(node, nextOptions);
  });
}

/**
 * Case 5: when a node's label changes, any "auto" option elsewhere that
 * still points at it (and hasn't been manually edited) tracks the new
 * label, re-disambiguated against its sibling options. Manual options, and
 * auto options pointing elsewhere, are untouched.
 */
export function syncDecisionOptionLabelsForTarget(
  nodes: PipelineNode[],
  targetNodeId: string,
  targetLabel: string,
): PipelineNode[] {
  return nodes.map((node) => {
    const options = getDecisionOptions(node);
    if (options.length === 0) return node;

    let changed = false;
    const nextOptions = options.map((option) => {
      if (option.origin !== "auto" || option.targetNodeId !== targetNodeId) {
        return option;
      }
      const uniqueLabel = createUniqueOptionLabel(
        targetLabel,
        options.filter((other) => other.id !== option.id),
      );
      if (uniqueLabel === option.label) return option;
      changed = true;
      return { ...option, label: uniqueLabel };
    });

    return changed ? setDecisionOptions(node, nextOptions) : node;
  });
}

/** Removes a single edge and applies the decision-option cleanup rules for it. */
export function removeEdgeAndSyncDecisionOptions(
  nodes: PipelineNode[],
  edges: PipelineEdge[],
  edgeId: string,
): { nodes: PipelineNode[]; edges: PipelineEdge[] } {
  const removedEdge = edges.find((edge) => edge.id === edgeId);
  const remainingEdges = edges.filter((edge) => edge.id !== edgeId);
  if (!removedEdge) return { nodes, edges: remainingEdges };

  const syncedNodes = syncDecisionOptionsAfterEdgeRemoval(nodes, remainingEdges, [removedEdge]);
  return { nodes: syncedNodes, edges: remainingEdges };
}

/**
 * Explicit option deletion from the inspector (Case 7): remove the option's
 * edge (if any), then remove the option itself, regardless of origin. This
 * intentionally bypasses the auto-cleanup rule above — the user is deleting
 * this exact option on purpose, manual or not.
 */
export function removeDecisionOption(
  nodes: PipelineNode[],
  edges: PipelineEdge[],
  nodeId: string,
  optionId: string,
): { nodes: PipelineNode[]; edges: PipelineEdge[] } {
  const nextEdges = edges.filter(
    (edge) => !(edge.sourceNodeId === nodeId && edge.routeId === optionId),
  );
  const nextNodes = nodes.map((node) => {
    if (node.id !== nodeId) return node;
    const options = getDecisionOptions(node).filter((option) => option.id !== optionId);
    return setDecisionOptions(node, options);
  });
  return { nodes: nextNodes, edges: nextEdges };
}
