import { IconButton } from "../actions/IconButton";
import { TextArea } from "../forms/TextArea";
import styles from "./ResponseVote.module.css";

export interface ResponseVoteProps {
  vote: "up" | "down" | null;
  explanation: string;
  onVote: (vote: "up" | "down") => void;
  onExplanationChange: (explanation: string) => void;
}

const THUMB_UP_ICON = (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14Z" />
    <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" />
  </svg>
);

const THUMB_DOWN_ICON = (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10Z" />
    <path d="M17 2h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3" />
  </svg>
);

/** Thumb-up/thumb-down toggle plus an explanation box that appears once a vote
 * is cast. Shared between the Run tab's chat bubbles (where feedback is given)
 * and the Evaluate tab's Responses view (where it's reviewed) -- both read and
 * write the same EvaluationRun.responses record, so voting works from either
 * place. Clicking the already-active thumb clears the vote. */
export function ResponseVote({ vote, explanation, onVote, onExplanationChange }: ResponseVoteProps) {
  return (
    <div className={styles.wrap}>
      <div className={styles.buttons}>
        <IconButton
          label={vote === "up" ? "Remove helpful vote" : "Mark as helpful"}
          icon={THUMB_UP_ICON}
          size="sm"
          variant="default"
          className={vote === "up" ? styles.activeUp : undefined}
          onClick={() => onVote("up")}
        />
        <IconButton
          label={vote === "down" ? "Remove not-helpful vote" : "Mark as not helpful"}
          icon={THUMB_DOWN_ICON}
          size="sm"
          variant="default"
          className={vote === "down" ? styles.activeDown : undefined}
          onClick={() => onVote("down")}
        />
      </div>
      {vote && (
        <TextArea
          value={explanation}
          onChange={(event) => onExplanationChange(event.target.value)}
          placeholder={
            vote === "up" ? "What made this a good answer? (optional)" : "What went wrong? (optional)"
          }
          rows={2}
          className={styles.explanation}
        />
      )}
    </div>
  );
}
