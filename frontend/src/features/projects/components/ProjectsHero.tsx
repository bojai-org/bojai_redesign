import { Button } from "../../../components/actions/Button";
import styles from "./ProjectsHero.module.css";

export interface ProjectsHeroProps {
  onNewProject: () => void;
}

export function ProjectsHero({ onNewProject }: ProjectsHeroProps) {
  return (
    <section className={styles.hero}>
      <div className={styles.inner}>
        <div className={styles.copy}>
          <h1>
            Build safe, evaluable healthcare chatbots — no ML engineering
            required.
          </h1>
          <p>
            Assemble safety agents and answer agents into a pipeline, tune
            prompts, and evaluate against your own Q&amp;A datasets — all in
            one workspace.
          </p>
        </div>
        <Button variant="primary" onClick={onNewProject}>
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            stroke="white"
            fill="none"
            strokeWidth="2"
            strokeLinecap="round"
            aria-hidden="true"
          >
            <path d="M12 5v14M5 12h14" />
          </svg>
          New project
        </Button>
      </div>
    </section>
  );
}
