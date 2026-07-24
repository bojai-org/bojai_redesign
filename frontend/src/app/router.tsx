import { createBrowserRouter, Navigate } from "react-router-dom";
import { ProjectsPage } from "../features/projects/pages/ProjectsPage";
import { ProjectWorkspacePage } from "../features/projects/components/ProjectWorkspacePage";
import { BuildPage } from "../features/build/pages/BuildPage";
import { RunPage } from "../features/run/pages/RunPage";
import { EvaluatePage } from "../features/evaluate/pages/EvaluatePage";
import { DeployPage } from "../features/deploy/pages/DeployPage";
import { ProjectSettingsPage } from "../features/settings/pages/ProjectSettingsPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <ProjectsPage />,
  },
  {
    path: "/projects/:projectId",
    element: <ProjectWorkspacePage />,
    children: [
      { index: true, element: <Navigate to="build" replace /> },
      { path: "build", element: <BuildPage /> },
      { path: "run", element: <RunPage /> },
      { path: "evaluate", element: <EvaluatePage /> },
      { path: "deploy", element: <DeployPage /> },
      { path: "settings", element: <ProjectSettingsPage /> },
    ],
  },
]);
