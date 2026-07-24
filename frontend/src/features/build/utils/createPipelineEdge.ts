import type { PipelineEdge } from "../types/pipeline";

function nextEdgeId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `edge-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function createPipelineEdge(params: {
  sourceNodeId: string;
  targetNodeId: string;
  sourceHandleId: string;
  routeId?: string;
  routeIndex?: number;
}): PipelineEdge {
  return { id: nextEdgeId(), ...params };
}
