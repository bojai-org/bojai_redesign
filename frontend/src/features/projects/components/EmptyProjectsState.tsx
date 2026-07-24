import { EmptyState } from "../../../components/feedback/EmptyState";
import { Button } from "../../../components/actions/Button";

export interface EmptyProjectsStateProps {
  hasSearchQuery: boolean;
  onNewProject: () => void;
}

export function EmptyProjectsState({
  hasSearchQuery,
  onNewProject,
}: EmptyProjectsStateProps) {
  if (hasSearchQuery) {
    return (
      <EmptyState
        title="No projects match your search"
        description="Try a different name or keyword, or clear the search to see all projects."
      />
    );
  }

  return (
    <EmptyState
      title="No projects yet"
      description="Create your first project to start assembling a pipeline."
      action={
        <Button variant="primary" onClick={onNewProject}>
          New project
        </Button>
      }
    />
  );
}
