import { createContext, useContext, useSyncExternalStore } from "react";
import type { ReactNode } from "react";
import type { ProjectPersistence, SaveStatus } from "./projectPersistence";

const ProjectPersistenceContext = createContext<ProjectPersistence | null>(null);

/** Makes one open project's autosave available to the providers and pages under it. */
export function ProjectPersistenceProvider({
  persistence,
  children,
}: {
  persistence: ProjectPersistence;
  children: ReactNode;
}) {
  return (
    <ProjectPersistenceContext.Provider value={persistence}>{children}</ProjectPersistenceContext.Provider>
  );
}

export function useProjectPersistence(): ProjectPersistence {
  const persistence = useContext(ProjectPersistenceContext);
  if (!persistence) {
    throw new Error("useProjectPersistence must be used within a ProjectPersistenceProvider");
  }
  return persistence;
}

/** Live "saving / saved / couldn't save" status of the open project's autosave. */
export function useSaveStatus(): SaveStatus {
  const persistence = useProjectPersistence();
  return useSyncExternalStore(persistence.subscribe, persistence.getStatus);
}
