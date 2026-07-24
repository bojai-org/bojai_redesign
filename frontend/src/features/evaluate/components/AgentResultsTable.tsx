import { useState } from "react";
import { Badge } from "../../../components/data-display/Badge";
import { Button } from "../../../components/actions/Button";
import type { QuestionEvalResult } from "../../build/types/evaluation";
import { QuestionDetailModal } from "./QuestionDetailModal";
import styles from "./AgentResultsTable.module.css";

export interface AgentResultsTableProps {
  results: QuestionEvalResult[];
}

function truncate(text: string, max = 80): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

export function AgentResultsTable({ results }: AgentResultsTableProps) {
  const [selected, setSelected] = useState<QuestionEvalResult | null>(null);

  return (
    <div className={styles.wrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Question</th>
            <th>Answer</th>
            <th>Faithful</th>
            <th>Similarity</th>
            <th>Resources</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {results.map((result, index) => {
            const expectedCount = result.resource_matches.length;
            const foundCount = result.resource_matches.filter((match) => match.found).length;

            return (
              <tr key={index}>
                <td className={styles.question}>{truncate(result.question)}</td>
                <td className={styles.answer}>
                  {result.error ? (
                    <Badge tone="amber">error</Badge>
                  ) : (
                    truncate(result.answer)
                  )}
                </td>
                <td>
                  {!result.error && (
                    <Badge tone={result.faithfulness.faithful ? "ok" : "no"}>
                      {(result.faithfulness.score * 100).toFixed(0)}%
                    </Badge>
                  )}
                </td>
                <td className={styles.numeric}>
                  {!result.error && `${(result.answer_similarity * 100).toFixed(0)}%`}
                </td>
                <td>
                  {expectedCount > 0 && (
                    <Badge tone={foundCount === expectedCount ? "ok" : "no"}>
                      {foundCount}/{expectedCount} found
                    </Badge>
                  )}
                </td>
                <td>
                  <Button variant="ghost" size="sm" onClick={() => setSelected(result)}>
                    Details
                  </Button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <QuestionDetailModal result={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
