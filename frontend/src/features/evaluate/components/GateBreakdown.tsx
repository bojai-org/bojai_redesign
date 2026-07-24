import type { SafetyGateCounts } from "../../build/types/evaluation";
import styles from "./GateBreakdown.module.css";

export interface GateBreakdownProps {
  gates: SafetyGateCounts[];
}

/** Fixed reading order for barrier actions -- pass, then review, then block --
 * regardless of which order they happened to appear in first (contract.md's
 * BarrierAction union). Unrecognized actions sort last. */
const ACTION_ORDER = ["safe", "accept", "escalate", "escalate_judge", "reject", "harmful"];

const ACTION_TONE: Record<string, string> = {
  safe: styles.pass,
  accept: styles.pass,
  escalate: styles.review,
  escalate_judge: styles.review,
  reject: styles.block,
  harmful: styles.block,
};

function sortActions(actionCounts: Record<string, number>): [string, number][] {
  return Object.entries(actionCounts).sort(([a], [b]) => {
    const indexA = ACTION_ORDER.indexOf(a);
    const indexB = ACTION_ORDER.indexOf(b);
    if (indexA === -1 && indexB === -1) return a.localeCompare(b);
    if (indexA === -1) return 1;
    if (indexB === -1) return -1;
    return indexA - indexB;
  });
}

/** Per-gate (barrier node) breakdown of how many questions produced each action,
 * as a labeled bar per action so the pass/review/block split reads at a glance. */
export function GateBreakdown({ gates }: GateBreakdownProps) {
  return (
    <div className={styles.gates}>
      {gates.map((gate) => (
        <div key={gate.node_id} className={styles.gate}>
          <div className={styles.gateHeader}>
            <span className={styles.gateName}>{gate.node_id}</span>
            <span className={styles.gateType}>{gate.agent_type}</span>
            <span className={styles.gateTotal}>{gate.total} question{gate.total === 1 ? "" : "s"}</span>
          </div>
          <div className={styles.rows}>
            {sortActions(gate.action_counts).map(([action, count]) => {
              const pct = gate.total > 0 ? Math.round((count / gate.total) * 100) : 0;
              return (
                <div key={action} className={styles.row}>
                  <span className={styles.actionLabel}>{action}</span>
                  <span className={styles.track}>
                    <span
                      className={`${styles.fill} ${ACTION_TONE[action] ?? styles.other}`}
                      style={{ width: `${pct}%` }}
                    />
                  </span>
                  <span className={styles.count}>{count}</span>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
