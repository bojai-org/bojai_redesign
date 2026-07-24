import { useId, useState } from "react";
import type { ChangeEvent } from "react";
import { Button } from "../../../components/actions/Button";
import { Card } from "../../../components/data-display/Card";
import { BuildApiError, evaluatePipelineWithProgress } from "../../build/api/pipelineApi";
import type { AgentEvalResponse, EvaluationResponse } from "../../build/types/evaluation";
import { AgentResultsTable } from "./AgentResultsTable";
import { EvaluationProgressBar } from "./EvaluationProgressBar";
import { StatTile } from "./StatTile";
import styles from "./AgentEvaluationPanel.module.css";

export interface AgentEvaluationPanelProps {
  pipelineId: string;
  report: AgentEvalResponse | null;
  onResult: (response: EvaluationResponse) => void;
  /** True when viewing a run whose pipeline is no longer the one compiled in
   * Build -- its results are a historical snapshot, not something new
   * evaluations can be run against. */
  readOnly?: boolean;
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

/** Uploads a CSV of evaluation questions and runs the pipeline end-to-end for each
 * row, scoring retrieval accuracy, faithfulness, and answer similarity. See
 * backend/evaluator.py's parse_qa_csv for the exact column contract. */
export function AgentEvaluationPanel({
  pipelineId,
  report,
  onResult,
  readOnly = false,
}: AgentEvaluationPanelProps) {
  const fileInputId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState<{ completed: number; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setFile(event.target.files?.[0] ?? null);
    setError(null);
  };

  const handleRun = async () => {
    if (!file) return;
    setIsRunning(true);
    setProgress(null);
    setError(null);
    try {
      const response = await evaluatePipelineWithProgress(pipelineId, file, (completed, total) =>
        setProgress({ completed, total }),
      );
      onResult(response);
    } catch (err) {
      setError(err instanceof BuildApiError ? err.message : "The evaluation failed.");
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <Card padding="md" className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>Agent evaluation</h2>
        <p className={styles.description}>
          Upload a CSV of evaluation questions to run the pipeline end-to-end and score
          retrieval accuracy, faithfulness, and answer similarity.
        </p>
        <p className={styles.hint}>
          Required columns: <code>question</code>, <code>expected_answer</code>. Optional:{" "}
          <code>expected_resource</code> (or <code>expected_resources</code>), values separated by{" "}
          <code>;</code>, <code>|</code>, or <code>,</code>.
        </p>
      </div>

      {readOnly ? (
        <span className={styles.historical}>Historical result</span>
      ) : (
        <div className={styles.uploadRow}>
          <input
            id={fileInputId}
            className={styles.fileInput}
            type="file"
            accept=".csv,text/csv"
            onChange={handleFileChange}
          />
          <label htmlFor={fileInputId} className={styles.fileLabel}>
            Choose CSV file
          </label>
          <span className={styles.fileName}>{file ? file.name : "No file selected"}</span>
          <Button variant="primary" onClick={handleRun} disabled={!file || isRunning}>
            {isRunning ? "Evaluating…" : "Run evaluation"}
          </Button>
        </div>
      )}

      {isRunning && progress && (
        <EvaluationProgressBar completed={progress.completed} total={progress.total} label="Evaluating" />
      )}
      {error && <p className={styles.error}>{error}</p>}
      {readOnly && !report && (
        <p className={styles.hint}>
          No evaluation was run for this pipeline version. Select the current run to run one.
        </p>
      )}

      {report && (
        <div className={styles.results}>
          <div className={styles.statRow}>
            {report.resource_recall !== null && (
              <StatTile label="Resource recall" value={formatPercent(report.resource_recall)} />
            )}
            <StatTile label="Mean faithfulness" value={formatPercent(report.mean_faithfulness)} />
            <StatTile label="Mean answer similarity" value={formatPercent(report.mean_answer_similarity)} />
            <StatTile label="Questions" value={String(report.results.length)} />
            {report.errors > 0 && (
              <StatTile label="Errored" value={String(report.errors)} tone="amber" />
            )}
          </div>

          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>Per-question results</h3>
            <AgentResultsTable results={report.results} />
          </section>
        </div>
      )}
    </Card>
  );
}
