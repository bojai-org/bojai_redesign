import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { Badge } from "../../../components/data-display/Badge";
import { Card } from "../../../components/data-display/Card";
import { EmptyState } from "../../../components/feedback/EmptyState";
import { LoadingSpinner } from "../../../components/feedback/LoadingSpinner";
import { PageContainer } from "../../../components/layout/PageContainer";
import { BuildApiError, getSafetyAgents } from "../../build/api/pipelineApi";
import { usePipelineWorkspace } from "../../build/state/PipelineWorkspaceContext";
import { AgentEvaluationPanel } from "../components/AgentEvaluationPanel";
import { CompareRunsPanel } from "../components/CompareRunsPanel";
import { RunSidebar } from "../components/RunSidebar";
import { SafetyPanel } from "../components/SafetyPanel";
import { useEvaluationRuns } from "../state/EvaluationRunsContext";
import styles from "./EvaluatePage.module.css";

export function EvaluatePage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { compileState, invalidatePipelineId } = usePipelineWorkspace();
  const {
    runs,
    activeRun,
    bestRunId,
    viewMode,
    ensureRunForPipeline,
    selectRun,
    renameRun,
    updateRun,
    markBest,
    deleteRun,
    showCompare,
  } = useEvaluationRuns();

  const pipelineId = compileState.pipelineId;
  const currentDefinitionHash = compileState.lastCompiledDefinitionHash;

  // Deleting the run that matches the live compiled pipeline would otherwise
  // leave nothing to evaluate against until the next navigation re-triggers
  // the "ensure a run exists" effect below -- re-asserting it immediately
  // after every delete is a no-op unless that's exactly what just happened.
  const handleDeleteRun = (runId: string) => {
    deleteRun(runId);
    if (pipelineId && currentDefinitionHash) {
      ensureRunForPipeline(pipelineId, currentDefinitionHash);
    }
  };

  // Every time this tab is opened (including returning from Build after a
  // recompile), resolve which run the currently-compiled pipeline belongs to
  // -- starting a new one if its definition hash hasn't been seen before.
  useEffect(() => {
    if (!pipelineId || !currentDefinitionHash) return;
    ensureRunForPipeline(pipelineId, currentDefinitionHash);
  }, [pipelineId, currentDefinitionHash, ensureRunForPipeline]);

  // One-time "does this run's pipeline have safety agents" lookup, cached on
  // the run itself so switching between runs never refetches.
  useEffect(() => {
    if (!activeRun || activeRun.safetyAgentsChecked) return;
    let cancelled = false;

    getSafetyAgents(activeRun.pipelineId)
      .then((info) => {
        if (!cancelled) {
          updateRun(activeRun.id, { safetyAgentsInfo: info, safetyAgentsChecked: true, safetyAgentsError: null });
        }
      })
      .catch((error) => {
        if (cancelled) return;
        if (error instanceof BuildApiError && error.status === 404) {
          invalidatePipelineId(
            "The compiled pipeline was no longer found on the server. Compile again to evaluate it.",
          );
          return;
        }
        updateRun(activeRun.id, {
          safetyAgentsChecked: true,
          safetyAgentsError:
            error instanceof BuildApiError ? error.message : "Could not check for safety agents.",
        });
      });

    return () => {
      cancelled = true;
    };
  }, [activeRun, updateRun, invalidatePipelineId]);

  if (!pipelineId) {
    return (
      <PageContainer width="wide">
        <EmptyState
          title="No compiled pipeline yet"
          description="Build a pipeline and compile it before you can evaluate it."
          action={<Link to={`/projects/${projectId}/build`}>Go to Build</Link>}
        />
      </PageContainer>
    );
  }

  const isCurrentRun = activeRun !== null && activeRun.definitionHash === currentDefinitionHash;

  return (
    <PageContainer width="wide">
      <Card padding="md" className={styles.header}>
        <div className={styles.headerRow}>
          <Badge tone="ok">Compiled</Badge>
          <span className={styles.pipelineId} title={pipelineId}>
            Pipeline ID: {pipelineId.length > 8 ? `${pipelineId.slice(0, 8)}…` : pipelineId}
          </span>
        </div>
        {compileState.status === "dirty" && (
          <p className={styles.staleNotice}>
            The graph has changed since this was compiled. Recompile in Build to evaluate the
            latest version.
          </p>
        )}
      </Card>

      <div className={styles.layout}>
        <RunSidebar
          runs={runs}
          activeRunId={activeRun?.id ?? null}
          bestRunId={bestRunId}
          viewMode={viewMode}
          currentDefinitionHash={currentDefinitionHash}
          onSelect={selectRun}
          onRename={renameRun}
          onMarkBest={markBest}
          onDelete={handleDeleteRun}
          onCompare={showCompare}
        />

        <div className={styles.main}>
          {viewMode === "compare" ? (
            <CompareRunsPanel runs={runs} bestRunId={bestRunId} />
          ) : activeRun ? (
            <>
              {!activeRun.safetyAgentsChecked && (
                <LoadingSpinner size="sm" label="Checking for safety agents…" />
              )}
              {activeRun.safetyAgentsError && <p className={styles.error}>{activeRun.safetyAgentsError}</p>}
              {activeRun.safetyAgentsInfo?.has_safety_agents && (
                <SafetyPanel
                  pipelineId={activeRun.pipelineId}
                  agentsInfo={activeRun.safetyAgentsInfo}
                  report={activeRun.safetyReport}
                  onResult={(report) => updateRun(activeRun.id, { safetyReport: report })}
                  readOnly={!isCurrentRun}
                />
              )}

              <AgentEvaluationPanel
                pipelineId={activeRun.pipelineId}
                report={activeRun.agentReport}
                onResult={(response) =>
                  updateRun(activeRun.id, {
                    agentReport: response.agent,
                    ...(response.safety ? { safetyReport: response.safety } : {}),
                  })
                }
                readOnly={!isCurrentRun}
              />
            </>
          ) : (
            <LoadingSpinner size="sm" label="Loading run…" />
          )}
        </div>
      </div>
    </PageContainer>
  );
}
