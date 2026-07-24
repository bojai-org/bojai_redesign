import { useState } from "react";
import { Card } from "../../../components/data-display/Card";
import { Select } from "../../../components/forms/Select";
import type { EvaluationRun } from "../types/run";
import styles from "./CompareRunsPanel.module.css";

export interface CompareRunsPanelProps {
  runs: EvaluationRun[];
  bestRunId: string | null;
}

interface CompareRow {
  label: string;
  a: number | null;
  b: number | null;
  isPercent: boolean;
}

function formatValue(value: number | null, isPercent: boolean): string {
  if (value === null) return "—";
  return isPercent ? `${(value * 100).toFixed(1)}%` : String(value);
}

function formatDelta(a: number | null, b: number | null, isPercent: boolean): string | null {
  if (a === null || b === null) return null;
  const delta = b - a;
  if (delta === 0) return "±0";
  const sign = delta > 0 ? "+" : "";
  return isPercent ? `${sign}${(delta * 100).toFixed(1)}pp` : `${sign}${delta}`;
}

function buildRows(a: EvaluationRun, b: EvaluationRun): CompareRow[] {
  return [
    { label: "Safety precision", a: a.safetyReport?.precision ?? null, b: b.safetyReport?.precision ?? null, isPercent: true },
    { label: "Safety recall", a: a.safetyReport?.recall ?? null, b: b.safetyReport?.recall ?? null, isPercent: true },
    { label: "Safety F1", a: a.safetyReport?.f1 ?? null, b: b.safetyReport?.f1 ?? null, isPercent: true },
    {
      label: "Resource recall",
      a: a.agentReport?.resource_recall ?? null,
      b: b.agentReport?.resource_recall ?? null,
      isPercent: true,
    },
    {
      label: "Mean faithfulness",
      a: a.agentReport?.mean_faithfulness ?? null,
      b: b.agentReport?.mean_faithfulness ?? null,
      isPercent: true,
    },
    {
      label: "Mean answer similarity",
      a: a.agentReport?.mean_answer_similarity ?? null,
      b: b.agentReport?.mean_answer_similarity ?? null,
      isPercent: true,
    },
  ];
}

/** Side-by-side comparison of two runs' headline metrics. Every metric here is
 * "higher is better", so a positive delta is always the good direction. */
export function CompareRunsPanel({ runs, bestRunId }: CompareRunsPanelProps) {
  const [pickedAId, setRunAId] = useState(runs.length >= 2 ? runs[runs.length - 2].id : (runs[0]?.id ?? ""));
  const [pickedBId, setRunBId] = useState(runs[runs.length - 1]?.id ?? "");

  // A picked run can disappear out from under this panel if it's deleted while
  // still selected -- derive the effective selection at render time (falling
  // back to the latest two) rather than "correcting" state in an effect.
  const runAId = runs.some((run) => run.id === pickedAId)
    ? pickedAId
    : (runs.length >= 2 ? runs[runs.length - 2].id : (runs[0]?.id ?? ""));
  const runBId = runs.some((run) => run.id === pickedBId) ? pickedBId : (runs[runs.length - 1]?.id ?? "");

  const runA = runs.find((run) => run.id === runAId) ?? null;
  const runB = runs.find((run) => run.id === runBId) ?? null;

  const options = runs.map((run) => ({
    value: run.id,
    label: run.id === bestRunId ? `★ ${run.name}` : run.name,
  }));

  return (
    <Card padding="md" className={styles.card}>
      <h2 className={styles.title}>Compare runs</h2>

      <div className={styles.pickers}>
        <label className={styles.pickerField}>
          <span>Run A</span>
          <Select options={options} value={runAId} onChange={(event) => setRunAId(event.target.value)} />
        </label>
        <label className={styles.pickerField}>
          <span>Run B</span>
          <Select options={options} value={runBId} onChange={(event) => setRunBId(event.target.value)} />
        </label>
      </div>

      {runA && runB && runA.id === runB.id && (
        <p className={styles.hint}>Pick two different runs to compare.</p>
      )}

      {runA && runB && runA.id !== runB.id && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Metric</th>
                <th>{runA.name}</th>
                <th>{runB.name}</th>
                <th>Δ</th>
              </tr>
            </thead>
            <tbody>
              {buildRows(runA, runB).map((row) => {
                const delta = formatDelta(row.a, row.b, row.isPercent);
                const deltaTone =
                  row.a === null || row.b === null || row.b === row.a
                    ? styles.neutral
                    : row.b > row.a
                      ? styles.positive
                      : styles.negative;

                return (
                  <tr key={row.label}>
                    <td>{row.label}</td>
                    <td className={styles.numeric}>{formatValue(row.a, row.isPercent)}</td>
                    <td className={styles.numeric}>{formatValue(row.b, row.isPercent)}</td>
                    <td className={`${styles.numeric} ${deltaTone}`}>{delta ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
