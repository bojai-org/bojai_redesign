import { SearchBar } from "./SearchBar";
import { FilterButton } from "./FilterButton";
import { NewProjectButton } from "./NewProjectButton";
import styles from "./ProjectToolbar.module.css";

export interface ProjectToolbarProps {
  searchQuery: string;
  onSearchChange: (value: string) => void;
  onNewProject: () => void;
}

export function ProjectToolbar({
  searchQuery,
  onSearchChange,
  onNewProject,
}: ProjectToolbarProps) {
  return (
    <div className={styles.toolbar}>
      <SearchBar value={searchQuery} onChange={onSearchChange} />
      <div className={styles.actions}>
        <FilterButton />
        <NewProjectButton onClick={onNewProject} />
      </div>
    </div>
  );
}
