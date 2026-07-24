import styles from "./EvaluationProgressBar.module.css";

export interface EvaluationProgressBarProps {
  completed: number;
  total: number;
  label?: string;
}

/** A determinate progress meter for a running evaluation job -- backed by real
 * per-question completion counts polled from the backend job (see
 * pipelineApi.ts's evaluate*WithProgress), not a simulated/timed animation. */
export function EvaluationProgressBar({ completed, total, label = "Evaluating" }: EvaluationProgressBarProps) {
  const pct = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;

  return (
    <div className={styles.wrap} role="progressbar" aria-valuenow={completed} aria-valuemin={0} aria-valuemax={total}>
      <div className={styles.labelRow}>
        <span className={styles.label}>{label}…</span>
        <span className={styles.count}>
          {completed} / {total} question{total === 1 ? "" : "s"}
        </span>
      </div>
      <span className={styles.track}>
        <span className={styles.fill} style={{ width: `${pct}%` }} />
      </span>
    </div>
  );
}
