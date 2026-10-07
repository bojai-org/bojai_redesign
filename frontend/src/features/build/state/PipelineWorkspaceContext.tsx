import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useEvaluationRuns } from "../../evaluate/state/EvaluationRunsContext";
import type { EvaluationRun } from "../../evaluate/types/run";
import { useProjectPersistence } from "../../projects/state/ProjectPersistenceContext";
import type { SavedGraph, WorkspaceState } from "../../projects/types/projectState";
import { hashPipelineDefinition } from "../utils/hashPipelineDefinition";
import { serializePipelineForCompiler } from "../utils/serializePipelineForCompiler";
import { INITIAL_COMPILE_STATE } from "../types/compiler";
import { useCompilePipeline } from "../hooks/useCompilePipeline";
import type { CompiledResult } from "../hooks/useCompilePipeline";
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
/** Canvas edits are saved this long after the last one (and right away when
 * the page is hidden or the project is closed). */
const WORKSPACE_SAVE_DELAY_MS = 500;

/**
 * Compile state for a reopened project. If the saved canvas is exactly what
 * the active run was compiled from, that run's pipeline is the compiled one.
 * Otherwise the canvas has edits made after it was compiled -- the run's
 * pipeline is still what Run/Evaluate use, but Build shows it as changed.
 */
function initialCompileStateFor(graph: SavedGraph, activeRun: EvaluationRun | null): CompileState {
  if (!activeRun) return INITIAL_COMPILE_STATE;
  let canvasHash: string | null = null;
  try {
    canvasHash = hashPipelineDefinition(serializePipelineForCompiler(graph));
  } catch {
    // An incomplete graph can't be serialized -- it can't match any run.
  }
  return {
    status: canvasHash === activeRun.definitionHash ? "compiled" : "dirty",
    pipelineId: activeRun.pipelineId,
    lastCompiledDefinitionHash: activeRun.definitionHash,
    error: null,
    summary: activeRun.workflow.summary,
    successCount: 0,
  };
}
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

  /** Makes `run` the active run for every tab: loads its workflow into the
   * canvas and its pipeline as the compiled one. Replaces whatever is on the
   * canvas -- callers confirm first if there are uncompiled edits. */
  openRun: (run: EvaluationRun) => void;
  /** True when the canvas has edits that aren't compiled into any run yet. */
  hasUncompiledChanges: boolean;
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
 *
 * Must sit inside EvaluationRunsProvider: every successful compile becomes
 * (or re-selects) a run, and the active run's workflow is what the canvas
 * shows -- so picking a run anywhere (see RunBar) switches all tabs to it.
 */
export function PipelineWorkspaceProvider({
  initialGraph,
  children,
}: {
  /** The project's saved canvas; omitted for a project that has none yet. */
  initialGraph?: SavedGraph;
  children: ReactNode;
}) {
  const [nodes, setNodes] = useState<PipelineNode[]>(initialGraph?.nodes ?? []);
  const [edges, setEdges] = useState<PipelineEdge[]>(initialGraph?.edges ?? []);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [runtimeConfig, setRuntimeConfig] = useState<PipelineRuntimeConfig>(
    initialGraph?.runtimeConfig ?? EMPTY_RUNTIME_CONFIG,
  );

  const persistence = useProjectPersistence();
  const { runs, activeRun, bestRunId, nextRunNumber, recordCompiledRun, pipelineIdForHash, selectRun } =
    useEvaluationRuns();
  const [initialCompileState] = useState(() =>
    initialGraph ? initialCompileStateFor(initialGraph, activeRun) : INITIAL_COMPILE_STATE,
  );

  const handleCompiled = useCallback(
    ({ summary, definitionHash, nodes: compiledNodes, edges: compiledEdges, runtimeConfig: compiledConfig }: CompiledResult) => {
      recordCompiledRun(summary.pipeline_id, definitionHash, {
        nodes: compiledNodes,
        edges: compiledEdges,
        runtimeConfig: compiledConfig,
        summary,
      });
    },
    [recordCompiledRun],
  );

  const {
    compileState,
    validationErrors,
    previewDefinition,
    previewError,
    compile,
    reset: resetCompileState,
    invalidatePipelineId,
    restore: restoreCompile,
  } = useCompilePipeline(nodes, edges, runtimeConfig, {
    projectId: persistence.projectId,
    initialCompileState,
    pipelineIdForHash,
    onCompiled: handleCompiled,
  });

  useAutosaveWorkspace(persistence, {
    graph: { nodes, edges, runtimeConfig },
    active_run_id: activeRun?.id ?? null,
    best_run_id: bestRunId,
    next_run_number: nextRunNumber,
  });

  const loadRunWorkflow = useCallback(
    (run: EvaluationRun) => {
      // Fresh arrays even if they're the snapshot's own: restoreCompile skips
      // exactly one "graph changed" notification, so the swap must produce one.
      setNodes([...run.workflow.nodes]);
      setEdges([...run.workflow.edges]);
      setRuntimeConfig(run.workflow.runtimeConfig);
      setSelectedNodeId(null);
      setSelectedEdgeId(null);
      restoreCompile({
        pipelineId: run.pipelineId,
        definitionHash: run.definitionHash,
        summary: run.workflow.summary,
      });
    },
    [restoreCompile],
  );

  const isShowingRun = (run: EvaluationRun) =>
    compileState.status === "compiled" && compileState.lastCompiledDefinitionHash === run.definitionHash;

  const openRun = useCallback(
    (run: EvaluationRun) => {
      if (!isShowingRun(run)) loadRunWorkflow(run);
      selectRun(run.id);
    },
    // isShowingRun only reads compileState.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [compileState.status, compileState.lastCompiledDefinitionHash, loadRunWorkflow, selectRun],
  );

  // A compiled pipeline should always belong to a run (Run and Evaluate attach
  // their results to it). That only stops being true when its run is deleted
  // with nothing left to fall back to -- recreate it, as a fresh run.
  useEffect(() => {
    // With a run left to fall back to, RunBar opens that one instead.
    if (activeRun) return;
    const { status, pipelineId, lastCompiledDefinitionHash, summary } = compileState;
    if (status !== "compiled" || !pipelineId || !lastCompiledDefinitionHash) return;
    if (runs.some((run) => run.definitionHash === lastCompiledDefinitionHash)) return;
    recordCompiledRun(pipelineId, lastCompiledDefinitionHash, { nodes, edges, runtimeConfig, summary });
    // nodes/edges/runtimeConfig are read as a snapshot, not tracked.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runs, activeRun, compileState, recordCompiledRun]);

  const hasUncompiledChanges =
    compileState.status !== "compiled" && (nodes.length > 0 || edges.length > 0);

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
      openRun,
      hasUncompiledChanges,
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
      openRun,
      hasUncompiledChanges,
    ],
  );

  return (
    <PipelineWorkspaceContext.Provider value={value}>
      {children}
    </PipelineWorkspaceContext.Provider>
  );
}

/**
 * Saves the workspace (the canvas, compiled or not, plus run selection)
 * WORKSPACE_SAVE_DELAY_MS after it last changed, so a burst of edits --
 * typing in a field, dragging a node -- is one save. A pending save is sent
 * immediately when the page is hidden or closed, or the project is left.
 */
function useAutosaveWorkspace(
  persistence: ReturnType<typeof useProjectPersistence>,
  workspace: WorkspaceState,
): void {
  const { graph, active_run_id, best_run_id, next_run_number } = workspace;
  const { nodes, edges, runtimeConfig } = graph;
  const pending = useRef<WorkspaceState | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isFirstRender = useRef(true);

  const flush = useCallback(
    (keepalive: boolean) => {
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
      if (!pending.current) return;
      const toSave = pending.current;
      pending.current = null;
      void persistence.saveWorkspace(toSave, { keepalive });
    },
    [persistence],
  );

  useEffect(() => {
    // What was just loaded is already saved.
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    pending.current = {
      graph: { nodes, edges, runtimeConfig },
      active_run_id,
      best_run_id,
      next_run_number,
    };
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => flush(false), WORKSPACE_SAVE_DELAY_MS);
  }, [nodes, edges, runtimeConfig, active_run_id, best_run_id, next_run_number, flush]);

  useEffect(() => {
    const flushNow = () => flush(true);
    const flushIfHidden = () => {
      if (document.visibilityState === "hidden") flushNow();
    };
    window.addEventListener("pagehide", flushNow);
    document.addEventListener("visibilitychange", flushIfHidden);
    return () => {
      window.removeEventListener("pagehide", flushNow);
      document.removeEventListener("visibilitychange", flushIfHidden);
      flushNow(); // leaving the project
    };
  }, [flush]);
}

export function usePipelineWorkspace(): PipelineWorkspaceContextValue {
  const context = useContext(PipelineWorkspaceContext);
  if (!context) {
    throw new Error("usePipelineWorkspace must be used within a PipelineWorkspaceProvider");
  }
  return context;
}
