import { Card } from "../../../components/data-display/Card";
import { Markdown } from "../../../components/data-display/Markdown";
import { EmptyState } from "../../../components/feedback/EmptyState";
import { ResponseVote } from "../../../components/feedback/ResponseVote";
import type { EvaluationRun } from "../types/run";
import { useEvaluationRuns } from "../state/EvaluationRunsContext";
import styles from "./ResponsesPanel.module.css";

export interface ResponsesPanelProps {
  run: EvaluationRun;
}

/** Read/vote view of every chat exchange sent from the Run tab against this
 * run's pipeline -- the same EvaluationRun.responses record the Run tab's chat
 * bubbles write to, so a vote cast here or there shows up in both places. */
export function ResponsesPanel({ run }: ResponsesPanelProps) {
  const { setResponseFeedback } = useEvaluationRuns();

  const handleVote = (responseId: string, vote: "up" | "down") => {
    const current = run.responses.find((entry) => entry.id === responseId);
    if (!current) return;
    setResponseFeedback(run.id, responseId, {
      vote: current.vote === vote ? null : vote,
      explanation: current.explanation,
    });
  };

  const handleExplanationChange = (responseId: string, explanation: string) => {
    const current = run.responses.find((entry) => entry.id === responseId);
    if (!current) return;
    setResponseFeedback(run.id, responseId, { vote: current.vote, explanation });
  };

  if (run.responses.length === 0) {
    return (
      <Card padding="md">
        <EmptyState
          title="No responses yet"
          description="Send a message from the Run tab to see it here, with room to rate it."
        />
      </Card>
    );
  }

  return (
    <Card padding="md" className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>Responses</h2>
        <p className={styles.description}>
          Every message sent to this pipeline from the Run tab, in order. Rate each answer and
          leave a note on why.
        </p>
      </div>

      <ul className={styles.list}>
        {run.responses.map((entry) => (
          <li key={entry.id} className={styles.item}>
            <p className={styles.query}>{entry.query}</p>
            <div className={styles.answer}>
              <Markdown content={entry.answer} />
            </div>
            <ResponseVote
              vote={entry.vote}
              explanation={entry.explanation}
              onVote={(vote) => handleVote(entry.id, vote)}
              onExplanationChange={(explanation) => handleExplanationChange(entry.id, explanation)}
            />
          </li>
        ))}
      </ul>
    </Card>
  );
}
