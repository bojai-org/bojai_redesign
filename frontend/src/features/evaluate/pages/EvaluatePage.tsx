import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Badge } from "../../../components/data-display/Badge";
import { Card } from "../../../components/data-display/Card";
import { EmptyState } from "../../../components/feedback/EmptyState";
import { LoadingSpinner } from "../../../components/feedback/LoadingSpinner";
import { PageContainer } from "../../../components/layout/PageContainer";
import { BuildApiError, getSafetyAgents } from "../../build/api/pipelineApi";
import { usePipelineWorkspace } from "../../build/state/PipelineWorkspaceContext";
import { getRunReports } from "../../projects/api/projectStateApi";
import { useProjectPersistence } from "../../projects/state/ProjectPersistenceContext";
import { AgentEvaluationPanel } from "../components/AgentEvaluationPanel";
import { CompareRunsPanel } from "../components/CompareRunsPanel";
import { ResponsesPanel } from "../components/ResponsesPanel";
import { SafetyPanel } from "../components/SafetyPanel";
import { useEvaluationRuns } from "../state/EvaluationRunsContext";
import styles from "./EvaluatePage.module.css";

type RunSubView = "evaluation" | "responses";

export function EvaluatePage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { compileState, invalidatePipelineId } = usePipelineWorkspace();
  // Which run is shown is picked in the project-wide RunBar, not here.
  const { runs, activeRun, bestRunId, viewMode, updateRun } = useEvaluationRuns();
  const [subView, setSubView] = useState<RunSubView>("evaluation");
  const { projectId: savedProjectId } = useProjectPersistence();
  const [reportsError, setReportsError] = useState<string | null>(null);
  const reportsInFlight = useRef(new Set<string>());

  // Saved reports aren't part of the project state (they can be large) --
  // fetch them for the run being viewed, or for every run when comparing.
  useEffect(() => {
    const needed = (viewMode === "compare" ? runs : activeRun ? [activeRun] : []).filter(
      (run) => !run.reportsLoaded && !reportsInFlight.current.has(run.id),
    );
    for (const run of needed) {
      reportsInFlight.current.add(run.id);
      getRunReports(savedProjectId, run.id)
        .then((reports) => {
          updateRun(run.id, {
            safetyReport: reports.safety?.report ?? null,
            agentReport: reports.agent?.report ?? null,
            agentCsvName: reports.agent?.csv_name ?? null,
            reportsLoaded: true,
          });
        })
        .catch((error) => {
          setReportsError(
            error instanceof BuildApiError ? error.message : "Could not load this run's saved results.",
          );
        })
        .finally(() => reportsInFlight.current.delete(run.id));
    }
  }, [viewMode, runs, activeRun, savedProjectId, updateRun]);

  const pipelineId = compileState.pipelineId;
  const currentDefinitionHash = compileState.lastCompiledDefinitionHash;

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
        <div className={styles.main}>
          {viewMode === "compare" ? (
            <CompareRunsPanel runs={runs} bestRunId={bestRunId} />
          ) : activeRun ? (
            <>
              <div className={styles.subTabs} role="tablist" aria-label="Run view">
                <button
                  type="button"
                  role="tab"
                  aria-selected={subView === "evaluation"}
                  className={subView === "evaluation" ? styles.subTabActive : styles.subTab}
                  onClick={() => setSubView("evaluation")}
                >
                  Evaluation
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={subView === "responses"}
                  className={subView === "responses" ? styles.subTabActive : styles.subTab}
                  onClick={() => setSubView("responses")}
                >
                  Responses{activeRun.responses.length > 0 ? ` (${activeRun.responses.length})` : ""}
                </button>
              </div>

              {subView === "responses" ? (
                <ResponsesPanel run={activeRun} />
              ) : (
                <>
                  {!activeRun.safetyAgentsChecked && (
                    <LoadingSpinner size="sm" label="Checking for safety agents…" />
                  )}
                  {activeRun.safetyAgentsError && (
                    <p className={styles.error}>{activeRun.safetyAgentsError}</p>
                  )}
                  {!activeRun.reportsLoaded && (
                    <LoadingSpinner size="sm" label="Loading saved results…" />
                  )}
                  {reportsError && <p className={styles.error}>{reportsError}</p>}
                  {activeRun.safetyAgentsInfo?.has_safety_agents && (
                    <SafetyPanel
                      pipelineId={activeRun.pipelineId}
                      runId={activeRun.id}
                      agentsInfo={activeRun.safetyAgentsInfo}
                      report={activeRun.safetyReport}
                      onResult={(report) => updateRun(activeRun.id, { safetyReport: report })}
                      readOnly={!isCurrentRun}
                    />
                  )}

                  <AgentEvaluationPanel
                    projectId={savedProjectId}
                    pipelineId={activeRun.pipelineId}
                    runId={activeRun.id}
                    report={activeRun.agentReport}
                    reportCsvName={activeRun.agentCsvName}
                    onResult={(response, csvName) =>
                      updateRun(activeRun.id, {
                        agentReport: response.agent,
                        agentCsvName: csvName,
                        ...(response.safety ? { safetyReport: response.safety } : {}),
                      })
                    }
                    readOnly={!isCurrentRun}
                  />
                </>
              )}
            </>
          ) : (
            <LoadingSpinner size="sm" label="Loading run…" />
          )}
        </div>
      </div>
    </PageContainer>
  );
}
