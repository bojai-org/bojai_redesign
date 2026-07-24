import { Outlet, useParams } from "react-router-dom";
import { AppHeader } from "../../../components/layout/AppHeader";
import { Tabs } from "../../../components/navigation/Tabs";
import { TabButton } from "../../../components/navigation/TabButton";
import { PipelineWorkspaceProvider } from "../../build/state/PipelineWorkspaceContext";
import { EvaluationRunsProvider } from "../../evaluate/state/EvaluationRunsContext";

const TABS = [
  { to: "build", label: "Build" },
  { to: "run", label: "Run" },
  { to: "evaluate", label: "Evaluate" },
  { to: "deploy", label: "Deploy" },
  { to: "settings", label: "Settings" },
];

export function ProjectWorkspacePage() {
  const { projectId } = useParams<{ projectId: string }>();

  return (
    <div>
      <AppHeader
        breadcrumbs={[
          { label: "Projects", to: "/" },
          { label: projectId ?? "Project" },
        ]}
      />
      <Tabs>
        {TABS.map((tab) => (
          <TabButton
            key={tab.to}
            to={`/projects/${projectId}/${tab.to}`}
            label={tab.label}
          />
        ))}
      </Tabs>
      {/* Keyed by projectId so switching projects starts a fresh pipeline
          workspace (and evaluation run history), while switching tabs within
          the same project (build, run, ...) never unmounts these providers --
          only the <Outlet/>'s matched child route does. */}
      <PipelineWorkspaceProvider key={projectId}>
        <EvaluationRunsProvider key={projectId}>
          <Outlet />
        </EvaluationRunsProvider>
      </PipelineWorkspaceProvider>
    </div>
  );
}
