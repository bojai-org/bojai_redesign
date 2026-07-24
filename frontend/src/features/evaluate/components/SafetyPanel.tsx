import { useState } from "react";
import { Button } from "../../../components/actions/Button";
import { Card } from "../../../components/data-display/Card";
import { Tag } from "../../../components/data-display/Tag";
import { BuildApiError, evaluateSafetyWithProgress } from "../../build/api/pipelineApi";
import type { SafetyAgentsResponse, SafetyEvalResponse } from "../../build/types/evaluation";
import { ConfusionMatrix } from "./ConfusionMatrix";
import { EvaluationProgressBar } from "./EvaluationProgressBar";
import { GateBreakdown } from "./GateBreakdown";
import { SafetyResultsTable } from "./SafetyResultsTable";
import { StatTile } from "./StatTile";
import styles from "./SafetyPanel.module.css";

export interface SafetyPanelProps {
  pipelineId: string;
  agentsInfo: SafetyAgentsResponse;
  report: SafetyEvalResponse | null;
  onResult: (report: SafetyEvalResponse) => void;
  /** True when viewing a run whose pipeline is no longer the one compiled in
   * Build -- its results are a historical snapshot, not something new
   * evaluations can be run against. */
  readOnly?: boolean;
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

/** Runs (and displays) the pipeline's barrier-agent chain against the built-in
 * 120-question harmful/unharmful benchmark -- independent of whatever CSV the
 * user uploads for the agent track below, since safety behavior is a property
 * of the pipeline itself (see backend/evaluator.py's module docstring). */
export function SafetyPanel({
  pipelineId,
  agentsInfo,
  report,
  onResult,
  readOnly = false,
}: SafetyPanelProps) {
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState<{ completed: number; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleRun = async () => {
    setIsRunning(true);
    setProgress(null);
    setError(null);
    try {
      const result = await evaluateSafetyWithProgress(pipelineId, (completed, total) =>
        setProgress({ completed, total }),
      );
      onResult(result);
    } catch (err) {
      setError(err instanceof BuildApiError ? err.message : "The safety check failed.");
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <Card padding="md" className={styles.card}>
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>Safety pipeline evaluation</h2>
          <p className={styles.description}>
            Runs every barrier-agent gate in this pipeline against a built-in 120-question
            harmful / unharmful benchmark.
          </p>
          <div className={styles.nodes}>
            {agentsInfo.nodes.map((node) => (
              <Tag key={node.node_id} muted>
                {node.node_id} · {node.agent_type}
              </Tag>
            ))}
          </div>
        </div>
        {readOnly ? (
          <span className={styles.historical}>Historical result</span>
        ) : (
          <Button variant="primary" onClick={handleRun} disabled={isRunning}>
            {isRunning ? "Running…" : report ? "Run again" : "Run safety check"}
          </Button>
        )}
      </div>

      {isRunning && progress && (
        <EvaluationProgressBar completed={progress.completed} total={progress.total} label="Screening" />
      )}
      {error && <p className={styles.error}>{error}</p>}
      {readOnly && !report && (
        <p className={styles.hint}>
          No safety check was run for this pipeline version. Select the current run to run one.
        </p>
      )}

      {report && (
        <div className={styles.results}>
          <div className={styles.statRow}>
            <StatTile label="Precision" value={formatPercent(report.precision)} />
            <StatTile label="Recall" value={formatPercent(report.recall)} />
            <StatTile label="F1 score" value={formatPercent(report.f1)} />
            <StatTile label="Questions" value={String(report.total_questions)} />
            {report.errors > 0 && (
              <StatTile label="Errored" value={String(report.errors)} tone="amber" />
            )}
          </div>

          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>Confusion matrix</h3>
            <ConfusionMatrix confusion={report.confusion} />
          </section>

          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>Per-gate breakdown</h3>
            <GateBreakdown gates={report.gate_counts} />
          </section>

          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>Per-question results</h3>
            <SafetyResultsTable results={report.results} />
          </section>
        </div>
      )}
    </Card>
  );
}
