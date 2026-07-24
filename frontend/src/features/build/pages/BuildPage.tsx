import { useCallback, useEffect, useMemo, useState } from "react";
import { PageContainer } from "../../../components/layout/PageContainer";
import { Toast } from "../../../components/feedback/Toast";
import { AgentLibrary } from "../components/AgentLibrary";
import { BuildCanvas } from "../components/BuildCanvas";
import type { ConnectionCandidate } from "../components/BuildCanvas";
import { AgentInspector } from "../components/AgentInspector";
import { CompileBar } from "../components/CompileBar";
import { AGENT_CONTRACTS } from "../contracts/agentContracts";
import { usePipelineWorkspace } from "../state/PipelineWorkspaceContext";
import { validatePipelineNode } from "../utils/validatePipelineNode";
import styles from "./BuildPage.module.css";

function isEditableTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)
  );
}

export function BuildPage() {
  const {
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
    resetWorkspace,
  } = usePipelineWorkspace();

  // Transient canvas feedback -- deliberately local, not part of the shared
  // workspace: it only makes sense while looking at the canvas, and there is
  // nothing to preserve across navigation (see resolveConnection's own error).
  const [connectionError, setConnectionError] = useState<string | null>(null);

  useEffect(() => {
    if (!connectionError) return;
    const timer = setTimeout(() => setConnectionError(null), 3200);
    return () => clearTimeout(timer);
  }, [connectionError]);

  const handleConnect = useCallback(
    (candidate: ConnectionCandidate) => {
      const result = connect(candidate);
      if (!result.ok) setConnectionError(result.error);
    },
    [connect],
  );

  const handleClearWorkspace = useCallback(() => {
    if (nodes.length === 0 && edges.length === 0) return;
    if (!window.confirm("Clear the current pipeline? This cannot be undone.")) return;
    resetWorkspace();
  }, [nodes.length, edges.length, resetWorkspace]);

  // Also local: only meaningful while BuildPage (and its canvas/selection UI)
  // is actually mounted, unlike the graph and compile state it acts on.
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Delete" && event.key !== "Backspace") return;
      if (isEditableTarget(event.target)) return;
      if (selectedEdgeId) {
        deleteEdges([selectedEdgeId]);
      } else if (selectedNodeId) {
        deleteNodes([selectedNodeId]);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedNodeId, selectedEdgeId, deleteNodes, deleteEdges]);

  const selectedNode = useMemo(
    () => nodes.find((node) => node.id === selectedNodeId) ?? null,
    [nodes, selectedNodeId],
  );

  const otherNodes = useMemo(
    () => nodes.filter((node) => node.id !== selectedNodeId),
    [nodes, selectedNodeId],
  );

  const isEntryNode = useMemo(
    () =>
      selectedNode
        ? !edges.some((edge) => edge.targetNodeId === selectedNode.id)
        : false,
    [edges, selectedNode],
  );

  return (
    <PageContainer width="wide">
      <div className={styles.libraryRow}>
        <AgentLibrary onAdd={addAgent} />
        <button type="button" className={styles.clearButton} onClick={handleClearWorkspace}>
          Clear pipeline
        </button>
      </div>

      <CompileBar
        runtimeConfig={runtimeConfig}
        onRuntimeConfigChange={setRuntimeConfig}
        compileState={compileState}
        validationErrors={validationErrors}
        previewDefinition={previewDefinition}
        previewError={previewError}
        nodes={nodes}
        edges={edges}
        onCompile={compile}
        onSelectErrorNode={selectNode}
      />

      <div className={styles.workspace}>
        <BuildCanvas
          nodes={nodes}
          edges={edges}
          selectedNodeId={selectedNodeId}
          selectedEdgeId={selectedEdgeId}
          onSelectNode={selectNode}
          onSelectEdge={selectEdge}
          onNodePositionChange={changeNodePosition}
          onConnect={handleConnect}
          onDeleteNodes={deleteNodes}
          onDeleteEdges={deleteEdges}
        />

        {selectedNode && (
          <AgentInspector
            node={selectedNode}
            contract={AGENT_CONTRACTS[selectedNode.data.agentType]}
            otherNodes={otherNodes}
            validation={validatePipelineNode(
              selectedNode,
              AGENT_CONTRACTS[selectedNode.data.agentType],
            )}
            isEntryNode={isEntryNode}
            onLabelChange={(label) => changeLabel(selectedNode.id, label)}
            onFieldChange={(key, value) => changeField(selectedNode.id, key, value)}
            onDelete={() => deleteNodes([selectedNode.id])}
            onClose={() => selectNode(null)}
            onRemoveDecisionOption={(optionId) => removeOption(selectedNode.id, optionId)}
          />
        )}
      </div>

      <Toast
        message={connectionError ?? ""}
        variant="error"
        visible={!!connectionError}
        onDismiss={() => setConnectionError(null)}
      />
    </PageContainer>
  );
}
