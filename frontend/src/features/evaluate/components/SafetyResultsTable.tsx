import { Badge } from "../../../components/data-display/Badge";
import type { SafetyQuestionResult } from "../../build/types/evaluation";
import styles from "./SafetyResultsTable.module.css";

export interface SafetyResultsTableProps {
  results: SafetyQuestionResult[];
}

function formatPath(result: SafetyQuestionResult): string {
  if (result.path.length === 0) return "(no barrier gate reached)";
  return result.path.map((step) => `${step.node_id}:${step.action ?? "?"}`).join(" → ");
}

export function SafetyResultsTable({ results }: SafetyResultsTableProps) {
  return (
    <div className={styles.wrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Question</th>
            <th>Label</th>
            <th>Predicted</th>
            <th>Gate path</th>
          </tr>
        </thead>
        <tbody>
          {results.map((result, index) => (
            <tr key={index}>
              <td className={styles.question}>{result.question}</td>
              <td>{result.label}</td>
              <td>
                {result.error ? (
                  <Badge tone="amber">error</Badge>
                ) : (
                  <Badge tone={result.predicted === result.label ? "ok" : "no"}>
                    {result.predicted}
                  </Badge>
                )}
              </td>
              <td className={styles.path}>{result.error ?? formatPath(result)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
