import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useCompilePipeline } from "../hooks/useCompilePipeline";
import { createPipelineNode } from "../utils/createPipelineNode";
import { removeNodeAndConnectedEdges } from "../utils/removeNodeAndConnectedEdges";
import {
  removeDecisionOption,
  removeEdgeAndSyncDecisionOptions,
  syncDecisionOptionLabelsForTarget,
} from "../utils/syncDecisionEdge";
import { resolveConnection } from "../utils/resolveConnection";
import type { ResolveConnectionResult } from "../utils/resolveConnection";
import type { ConnectionCandidate } from "../utils/validateConnection";
import type {
  BuildValidationError,
  CompileState,
  CompilerPipelineDefinition,
} from "../types/compiler";
import type {
  AgentType,
  PipelineEdge,
  PipelineNode,
  PipelineRuntimeConfig,
} from "../types/pipeline";
import { EMPTY_RUNTIME_CONFIG } from "../types/pipeline";

const NEW_NODE_OFFSET = 32;
const DEFAULT_NODE_POSITION = { x: 80, y: 80 };

function nextNodePosition(existingNodes: PipelineNode[]): { x: number; y: number } {
  if (existingNodes.length === 0) return DEFAULT_NODE_POSITION;
  const last = existingNodes[existingNodes.length - 1];
  return {
    x: last.position.x + NEW_NODE_OFFSET,
    y: last.position.y + NEW_NODE_OFFSET,
  };
}

export interface PipelineWorkspaceContextValue {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  runtimeConfig: PipelineRuntimeConfig;

  setRuntimeConfig: (value: PipelineRuntimeConfig) => void;
  addAgent: (agentType: AgentType) => void;
  deleteNodes: (nodeIds: string[]) => void;
  deleteEdges: (edgeIds: string[]) => void;
  changeLabel: (nodeId: string, label: string) => void;
  changeField: (nodeId: string, key: string, value: unknown) => void;
  removeOption: (nodeId: string, optionId: string) => void;
  changeNodePosition: (nodeId: string, position: { x: number; y: number }) => void;
  connect: (candidate: ConnectionCandidate) => ResolveConnectionResult;
  selectNode: (nodeId: string | null) => void;
  selectEdge: (edgeId: string | null) => void;

  compileState: CompileState;
  validationErrors: BuildValidationError[];
  previewDefinition: CompilerPipelineDefinition | null;
  previewError: string | null;
  compile: () => Promise<void>;
  /** A backend 404 on /run means the stored pipeline is gone; drop the id without touching the graph. */
  invalidatePipelineId: (reason: string) => void;

  /** Wipes the graph, runtime config, selection, and compile state back to a blank workspace. */
  resetWorkspace: () => void;
}

const PipelineWorkspaceContext = createContext<PipelineWorkspaceContextValue | null>(null);

/**
 * Owns the pipeline graph, runtime config, and compile state for the
 * duration of a project session. Mounted once around the project workspace
 * routes (see ProjectWorkspacePage), one level above the <Outlet/> that
 * swaps Build/Run/Evaluate/etc. in and out -- so navigating between those
 * tabs re-renders only the page content, never this provider, and the graph
 * and compiled pipeline id survive the trip. See also useCompilePipeline's
 * own module doc for the compile state machine itself.
 */
export function PipelineWorkspaceProvider({ children }: { children: ReactNode }) {
  const [nodes, setNodes] = useState<PipelineNode[]>([]);
  const [edges, setEdges] = useState<PipelineEdge[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [runtimeConfig, setRuntimeConfig] = useState<PipelineRuntimeConfig>(EMPTY_RUNTIME_CONFIG);

  const {
    compileState,
    validationErrors,
    previewDefinition,
    previewError,
    compile,
    reset: resetCompileState,
    invalidatePipelineId,
  } = useCompilePipeline(nodes, edges, runtimeConfig);

  const addAgent = useCallback(
    (agentType: AgentType) => {
      const node = createPipelineNode(agentType, nextNodePosition(nodes));
      setNodes((current) => [...current, node]);
      setSelectedNodeId(node.id);
      setSelectedEdgeId(null);
    },
    [nodes],
  );

  const deleteNodes = useCallback(
    (nodeIds: string[]) => {
      let nextNodes = nodes;
      let nextEdges = edges;
      for (const nodeId of nodeIds) {
        const result = removeNodeAndConnectedEdges(nextNodes, nextEdges, nodeId);
        nextNodes = result.nodes;
        nextEdges = result.edges;
      }
      setNodes(nextNodes);
      setEdges(nextEdges);
      setSelectedNodeId((current) => (current && nodeIds.includes(current) ? null : current));
    },
    [nodes, edges],
  );

  const deleteEdges = useCallback(
    (edgeIds: string[]) => {
      let nextNodes = nodes;
      let nextEdges = edges;
      for (const edgeId of edgeIds) {
        const result = removeEdgeAndSyncDecisionOptions(nextNodes, nextEdges, edgeId);
        nextNodes = result.nodes;
        nextEdges = result.edges;
      }
      setNodes(nextNodes);
      setEdges(nextEdges);
      setSelectedEdgeId((current) => (current && edgeIds.includes(current) ? null : current));
    },
    [nodes, edges],
  );

  const changeLabel = useCallback((nodeId: string, label: string) => {
    setNodes((current) => {
      const relabeled = current.map((node) =>
        node.id === nodeId ? { ...node, data: { ...node.data, label } } : node,
      );
      return syncDecisionOptionLabelsForTarget(relabeled, nodeId, label);
    });
  }, []);

  const changeField = useCallback((nodeId: string, key: string, value: unknown) => {
    setNodes((current) =>
      current.map((node) =>
        node.id === nodeId
          ? { ...node, data: { ...node.data, config: { ...node.data.config, [key]: value } } }
          : node,
      ),
    );
  }, []);

  const removeOption = useCallback(
    (nodeId: string, optionId: string) => {
      const result = removeDecisionOption(nodes, edges, nodeId, optionId);
      setNodes(result.nodes);
      setEdges(result.edges);
    },
    [nodes, edges],
  );

  const changeNodePosition = useCallback((nodeId: string, position: { x: number; y: number }) => {
    setNodes((current) =>
      current.map((node) => (node.id === nodeId ? { ...node, position } : node)),
    );
  }, []);

  const connect = useCallback(
    (candidate: ConnectionCandidate): ResolveConnectionResult => {
      const result = resolveConnection(candidate, nodes, edges);
      if (!result.ok) return result;
      if (result.updatedNode) {
        const updatedNode = result.updatedNode;
        setNodes((current) =>
          current.map((node) => (node.id === updatedNode.id ? updatedNode : node)),
        );
      }
      setEdges((current) => [...current, result.edge]);
      return result;
    },
    [nodes, edges],
  );

  const selectNode = useCallback((nodeId: string | null) => {
    setSelectedNodeId(nodeId);
    setSelectedEdgeId(null);
  }, []);

  const selectEdge = useCallback((edgeId: string | null) => {
    setSelectedEdgeId(edgeId);
    setSelectedNodeId(null);
  }, []);

  const resetWorkspace = useCallback(() => {
    setNodes([]);
    setEdges([]);
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setRuntimeConfig(EMPTY_RUNTIME_CONFIG);
    resetCompileState();
  }, [resetCompileState]);

  const value = useMemo<PipelineWorkspaceContextValue>(
    () => ({
      nodes,
      edges,
      selectedNodeId,
      selectedEdgeId,
      runtimeConfig,
      setRuntimeConfig,
      addAgent,
      deleteNodes,
      deleteEdges,
      changeLabel,
      changeField,
      removeOption,
      changeNodePosition,
      connect,
      selectNode,
      selectEdge,
      compileState,
      validationErrors,
      previewDefinition,
      previewError,
      compile,
      invalidatePipelineId,
      resetWorkspace,
    }),
    [
      nodes,
      edges,
      selectedNodeId,
      selectedEdgeId,
      runtimeConfig,
      addAgent,
      deleteNodes,
      deleteEdges,
      changeLabel,
      changeField,
      removeOption,
      changeNodePosition,
      connect,
      selectNode,
      selectEdge,
      compileState,
      validationErrors,
      previewDefinition,
      previewError,
      compile,
      invalidatePipelineId,
      resetWorkspace,
    ],
  );

  return (
    <PipelineWorkspaceContext.Provider value={value}>
      {children}
    </PipelineWorkspaceContext.Provider>
  );
}

export function usePipelineWorkspace(): PipelineWorkspaceContextValue {
  const context = useContext(PipelineWorkspaceContext);
  if (!context) {
    throw new Error("usePipelineWorkspace must be used within a PipelineWorkspaceProvider");
  }
  return context;
}
