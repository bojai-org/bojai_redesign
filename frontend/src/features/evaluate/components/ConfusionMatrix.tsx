import { StatTile } from "./StatTile";
import type { SafetyConfusion } from "../../build/types/evaluation";
import styles from "./ConfusionMatrix.module.css";

export interface ConfusionMatrixProps {
  confusion: SafetyConfusion;
}

/** Correctly blocking harm and correctly passing safe input are both "ok"; missing
 * real harm (a false negative) is the more dangerous failure mode for a safety
 * classifier than over-blocking (a false positive), so they get different tones. */
export function ConfusionMatrix({ confusion }: ConfusionMatrixProps) {
  return (
    <div className={styles.grid}>
      <StatTile
        label="Correctly blocked (harmful)"
        value={String(confusion.true_positive)}
        tone="ok"
      />
      <StatTile
        label="Correctly passed (unharmful)"
        value={String(confusion.true_negative)}
        tone="ok"
      />
      <StatTile
        label="Over-blocked (false positive)"
        value={String(confusion.false_positive)}
        tone="amber"
      />
      <StatTile
        label="Missed harmful (false negative)"
        value={String(confusion.false_negative)}
        tone="no"
      />
    </div>
  );
}
