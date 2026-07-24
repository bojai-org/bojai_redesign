import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  applyNodeChanges,
  type Connection,
  type Edge,
  type NodeChange,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { EmptyState } from "../../../components/feedback/EmptyState";
import { FlowAgentNode } from "./FlowAgentNode";
import type { FlowAgentNodeType } from "./FlowAgentNode";
import { AGENT_CONTRACTS, STATIC_ROUTE_LABELS, getSourceHandles } from "../contracts/agentContracts";
import { getDecisionOptions } from "../utils/getDecisionOptions";
import { TARGET_HANDLE } from "../utils/handleIds";
import { validateConnection } from "../utils/validateConnection";
import type { ConnectionCandidate } from "../utils/validateConnection";
import { validatePipelineNode } from "../utils/validatePipelineNode";
import type { PipelineEdge, PipelineNode } from "../types/pipeline";
import styles from "./BuildCanvas.module.css";

const NODE_TYPES: NodeTypes = { agent: FlowAgentNode };

export type { ConnectionCandidate };

export interface BuildCanvasProps {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  onSelectNode: (nodeId: string | null) => void;
  onSelectEdge: (edgeId: string | null) => void;
  onNodePositionChange: (nodeId: string, position: { x: number; y: number }) => void;
  onConnect: (candidate: ConnectionCandidate) => void;
  onDeleteNodes: (nodeIds: string[]) => void;
  onDeleteEdges: (edgeIds: string[]) => void;
}

function edgeLabel(edge: PipelineEdge, nodes: PipelineNode[]): string | undefined {
  const sourceNode = nodes.find((node) => node.id === edge.sourceNodeId);
  if (!sourceNode) return undefined;
  if (sourceNode.data.agentType === "Decision_Agent") {
    const option = getDecisionOptions(sourceNode).find(
      (candidate) => candidate.id === edge.routeId,
    );
    return option?.label.trim() || undefined;
  }
  // Single-route agents ("next") don't need a label; multi-route agents
  // (Binary Judge, the safety barriers) do.
  if (!edge.routeId || edge.routeId === "next") return undefined;
  return STATIC_ROUTE_LABELS[edge.routeId] ?? edge.routeId;
}

export function BuildCanvas({
  nodes,
  edges,
  selectedNodeId,
  selectedEdgeId,
  onSelectNode,
  onSelectEdge,
  onNodePositionChange,
  onConnect,
  onDeleteNodes,
  onDeleteEdges,
}: BuildCanvasProps) {
  // React Flow's own node list, kept as local state instead of a derived
  // useMemo. It carries RF-managed fields (`measured`, set once React Flow
  // measures a node's real DOM size) that our domain PipelineNode knows
  // nothing about. Rebuilding a brand-new node object on every render (as a
  // useMemo off `nodes` would) drops `measured` each time; a few renders
  // into an active drag, React Flow decides the node was never measured and
  // hides it (its own error #015, "trying to drag a node that is not
  // initialized"). Reconciling here instead -- carrying `measured` forward
  // -- is what keeps a node visible while it's being dragged.
  const [rfNodes, setRfNodes] = useState<FlowAgentNodeType[]>([]);

  useEffect(() => {
    setRfNodes((current) => {
      const previousById = new Map(current.map((node) => [node.id, node]));
      return nodes.map((node) => {
        const contract = AGENT_CONTRACTS[node.data.agentType];
        return {
          id: node.id,
          type: "agent",
          position: node.position,
          selected: node.id === selectedNodeId,
          measured: previousById.get(node.id)?.measured,
          data: {
            node,
            contract,
            valid: validatePipelineNode(node, contract).valid,
            sourceHandles: getSourceHandles(node, contract),
          },
        };
      });
    });
  }, [nodes, selectedNodeId]);

  const rfEdges = useMemo<Edge[]>(
    () =>
      edges.map((edge) => {
        const isSelected = edge.id === selectedEdgeId;
        return {
          id: edge.id,
          source: edge.sourceNodeId,
          target: edge.targetNodeId,
          sourceHandle: edge.sourceHandleId,
          targetHandle: TARGET_HANDLE,
          selected: isSelected,
          label: edgeLabel(edge, nodes),
          type: "smoothstep",
          style: {
            stroke: isSelected ? "var(--bj-600)" : "var(--bj-400)",
            strokeWidth: isSelected ? 2.5 : 1.75,
          },
          labelStyle: { fill: "var(--ink-700)", fontSize: 11, fontWeight: 600 },
          labelBgStyle: { fill: "var(--surface)" },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: isSelected ? "var(--bj-600)" : "var(--bj-400)",
          },
        };
      }),
    [edges, nodes, selectedEdgeId],
  );

  const handleNodesChange = useCallback(
    (changes: NodeChange<FlowAgentNodeType>[]) => {
      // Applied to React Flow's own node list on every change (including
      // "dimensions", which the domain model has no use for but React Flow
      // needs to keep the node marked as initialized -- see the `rfNodes`
      // comment above). Only committed up to the domain model -- and from
      // there into validation/serialization/dirty-tracking -- once a drag
      // actually settles, not on every intermediate pointer-move tick.
      setRfNodes((current) => applyNodeChanges<FlowAgentNodeType>(changes, current));
      for (const change of changes) {
        if (change.type === "position" && change.position && !change.dragging) {
          onNodePositionChange(change.id, change.position);
        }
      }
    },
    [onNodePositionChange],
  );

  const handleConnect = useCallback(
    (connection: Connection) => {
      if (!connection.sourceHandle) return;
      onConnect({
        sourceNodeId: connection.source,
        targetNodeId: connection.target,
        sourceHandleId: connection.sourceHandle,
      });
    },
    [onConnect],
  );

  const isValidConnection = useCallback(
    (candidate: Edge | Connection) => {
      if (!candidate.sourceHandle) return false;
      return validateConnection(
        {
          sourceNodeId: candidate.source,
          targetNodeId: candidate.target,
          sourceHandleId: candidate.sourceHandle,
        },
        nodes,
        edges,
      ).valid;
    },
    [nodes, edges],
  );

  return (
    <div className={styles.canvas}>
      {nodes.length === 0 && (
        <div className={styles.empty}>
          <EmptyState
            title="No agents yet"
            description="Add an agent from the library above to start building this pipeline."
          />
        </div>
      )}
      <ReactFlow
        className={styles.flow}
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={NODE_TYPES}
        onNodeClick={(_, node) => onSelectNode(node.id)}
        onEdgeClick={(_, edge) => onSelectEdge(edge.id)}
        onPaneClick={() => {
          onSelectNode(null);
          onSelectEdge(null);
        }}
        onNodesChange={handleNodesChange}
        onConnect={handleConnect}
        isValidConnection={isValidConnection}
        onNodesDelete={(deleted) => onDeleteNodes(deleted.map((node) => node.id))}
        onEdgesDelete={(deleted) => onDeleteEdges(deleted.map((edge) => edge.id))}
        deleteKeyCode={null}
        fitView
      >
        <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="var(--border)" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
