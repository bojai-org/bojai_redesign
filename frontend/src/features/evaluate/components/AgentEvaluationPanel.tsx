import { useId, useState } from "react";
import type { ChangeEvent } from "react";
import { Button } from "../../../components/actions/Button";
import { Card } from "../../../components/data-display/Card";
import {
  BuildApiError,
  EvaluationCancelledError,
  cancelEvaluateJob,
  evaluatePipelineWithProgress,
} from "../../build/api/pipelineApi";
import type { AgentEvalResponse, EvaluationResponse } from "../../build/types/evaluation";
import { fetchRunEvalCsv } from "../../projects/api/projectStateApi";
import { AgentResultsTable } from "./AgentResultsTable";
import { EvaluationProgressBar } from "./EvaluationProgressBar";
import { StatTile } from "./StatTile";
import styles from "./AgentEvaluationPanel.module.css";

export interface AgentEvaluationPanelProps {
  projectId: string;
  pipelineId: string;
  /** The run this report belongs to -- the backend saves it there (with the
   * uploaded CSV) when the job finishes. */
  runId: string;
  report: AgentEvalResponse | null;
  /** Name of the CSV `report` was produced from; the backend kept that file,
   * so it can be run again without re-uploading. */
  reportCsvName: string | null;
  onResult: (response: EvaluationResponse, csvName: string) => void;
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
  projectId,
  pipelineId,
  runId,
  report,
  reportCsvName,
  onResult,
  readOnly = false,
}: AgentEvaluationPanelProps) {
  const fileInputId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState<{ completed: number; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setFile(event.target.files?.[0] ?? null);
    setError(null);
  };

  /** Runs `csv`, or -- with none given -- the CSV this run's report was
   * produced from, fetched back from the backend. */
  const handleRun = async (csv: File | null) => {
    if (!csv && !reportCsvName) return;
    setIsRunning(true);
    setProgress(null);
    setError(null);
    setJobId(null);
    try {
      const source = csv ?? (await fetchRunEvalCsv(projectId, runId, reportCsvName ?? "evaluation.csv"));
      const response = await evaluatePipelineWithProgress(
        pipelineId,
        source,
        (completed, total) => setProgress({ completed, total }),
        setJobId,
        runId,
      );
      onResult(response, source.name);
    } catch (err) {
      if (!(err instanceof EvaluationCancelledError)) {
        setError(err instanceof BuildApiError ? err.message : "The evaluation failed.");
      }
    } finally {
      setIsRunning(false);
      setIsCancelling(false);
      setJobId(null);
    }
  };

  const handleStop = async () => {
    if (!jobId) return;
    setIsCancelling(true);
    try {
      await cancelEvaluateJob(pipelineId, jobId);
    } catch {
      // The run's own catch block already surfaces a terminal state once its
      // poll loop sees the job leave "running" -- a failed cancel request
      // just means the next poll finds it done/errored instead of cancelled.
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
            disabled={isRunning}
          />
          <label htmlFor={fileInputId} className={styles.fileLabel}>
            Choose CSV file
          </label>
          <span className={styles.fileName}>{file ? file.name : "No file selected"}</span>
          {isRunning ? (
            <Button
              variant="danger-ghost"
              onClick={() => void handleStop()}
              disabled={isCancelling || !jobId}
            >
              {isCancelling ? "Stopping…" : "Stop"}
            </Button>
          ) : (
            <>
              <Button variant="primary" onClick={() => void handleRun(file)} disabled={!file}>
                Run evaluation
              </Button>
              {reportCsvName && !file && (
                <Button onClick={() => void handleRun(null)} title="Run the saved CSV again">
                  Re-run {reportCsvName}
                </Button>
              )}
            </>
          )}
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
          {reportCsvName && <p className={styles.hint}>Evaluated with {reportCsvName}</p>}
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
