import { useEffect, useState } from "react";
import { Link, Outlet, useParams } from "react-router-dom";
import { AppHeader } from "../../../components/layout/AppHeader";
import { PageContainer } from "../../../components/layout/PageContainer";
import { EmptyState } from "../../../components/feedback/EmptyState";
import { LoadingSpinner } from "../../../components/feedback/LoadingSpinner";
import { Tabs } from "../../../components/navigation/Tabs";
import { TabButton } from "../../../components/navigation/TabButton";
import { BuildApiError } from "../../build/api/pipelineApi";
import { PipelineWorkspaceProvider } from "../../build/state/PipelineWorkspaceContext";
import { EvaluationRunsProvider } from "../../evaluate/state/EvaluationRunsContext";
import type { InitialRunsState } from "../../evaluate/state/EvaluationRunsContext";
import { RunBar } from "../../evaluate/components/RunBar";
import { getProjectState } from "../api/projectStateApi";
import { ProjectPersistenceProvider } from "../state/ProjectPersistenceContext";
import { ProjectPersistence, storedRunToRun } from "../state/projectPersistence";
import type { ProjectStateResponse, SavedGraph } from "../types/projectState";

const TABS = [
  { to: "build", label: "Build" },
  { to: "run", label: "Run" },
  { to: "evaluate", label: "Evaluate" },
  { to: "deploy", label: "Deploy" },
  { to: "settings", label: "Settings" },
];

export function ProjectWorkspacePage() {
  const { projectId } = useParams<{ projectId: string }>();
  if (!projectId) return null;
  // Keyed so opening another project starts over: a fresh load, autosave
  // queue, run history and pipeline workspace.
  return <ProjectSession key={projectId} projectId={projectId} />;
}

interface LoadedProject {
  name: string;
  persistence: ProjectPersistence;
  initialRuns: InitialRunsState;
  initialGraph: SavedGraph | undefined;
}

function toLoadedProject(projectId: string, state: ProjectStateResponse): LoadedProject {
  const runs = state.runs.map(storedRunToRun);
  const runIds = new Set(runs.map((run) => run.id));
  const workspace = state.workspace;
  // Ignore saved run ids that no longer exist (e.g. a run deleted while a
  // workspace save was still pending).
  const savedActive = workspace?.active_run_id ?? null;
  const savedBest = workspace?.best_run_id ?? null;
  return {
    name: state.project.name,
    persistence: new ProjectPersistence(projectId),
    initialRuns: {
      runs,
      activeRunId: savedActive && runIds.has(savedActive) ? savedActive : (runs.at(-1)?.id ?? null),
      bestRunId: savedBest && runIds.has(savedBest) ? savedBest : null,
      nextRunNumber: Math.max(workspace?.next_run_number ?? 1, runs.length + 1),
    },
    initialGraph: workspace?.graph,
  };
}

/**
 * One open project: loads everything saved under it (GET .../state) once,
 * then mounts the providers seeded with it. From then on every change is
 * saved automatically -- the canvas and run selection by
 * PipelineWorkspaceProvider, runs and chat responses by
 * EvaluationRunsProvider, evaluation reports by the backend itself.
 */
function ProjectSession({ projectId }: { projectId: string }) {
  const [loaded, setLoaded] = useState<LoadedProject | null>(null);
  const [loadError, setLoadError] = useState<{ status: number; message: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    getProjectState(projectId)
      .then((state) => {
        if (!cancelled) setLoaded(toLoadedProject(projectId, state));
      })
      .catch((error) => {
        if (cancelled) return;
        setLoadError(
          error instanceof BuildApiError
            ? { status: error.status, message: error.message }
            : { status: 0, message: "Could not load this project." },
        );
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const header = (
    <AppHeader breadcrumbs={[{ label: "Projects", to: "/" }, { label: loaded?.name ?? "Project" }]} />
  );

  if (loadError) {
    return (
      <div>
        {header}
        <PageContainer>
          <EmptyState
            title={loadError.status === 404 ? "Project not found" : "Could not open this project"}
            description={loadError.status === 404 ? "It may have been deleted." : loadError.message}
            action={<Link to="/">Back to projects</Link>}
          />
        </PageContainer>
      </div>
    );
  }

  if (!loaded) {
    return (
      <div>
        {header}
        <PageContainer>
          <LoadingSpinner size="sm" label="Opening project…" />
        </PageContainer>
      </div>
    );
  }

  return (
    <div>
      {header}
      <Tabs>
        {TABS.map((tab) => (
          <TabButton key={tab.to} to={`/projects/${projectId}/${tab.to}`} label={tab.label} />
        ))}
      </Tabs>
      {/* These providers live as long as the project is open, so switching
          tabs (build, run, ...) never unmounts them -- only the <Outlet/>'s
          matched child route changes. Runs sit outside the workspace because
          the workspace records compiles as runs and loads the active run's
          workflow; RunBar sits inside both, above every tab's content. */}
      <ProjectPersistenceProvider persistence={loaded.persistence}>
        <EvaluationRunsProvider initialState={loaded.initialRuns}>
          <PipelineWorkspaceProvider initialGraph={loaded.initialGraph}>
            <RunBar />
            <Outlet />
          </PipelineWorkspaceProvider>
        </EvaluationRunsProvider>
      </ProjectPersistenceProvider>
    </div>
  );
}
