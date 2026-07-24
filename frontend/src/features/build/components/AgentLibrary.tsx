import {
  AGENT_CONTRACTS,
  SAFETY_AGENT_TYPES,
  STANDARD_AGENT_TYPES,
} from "../contracts/agentContracts";
import type { AgentType } from "../types/pipeline";
import styles from "./AgentLibrary.module.css";

export interface AgentLibraryProps {
  onAdd: (agentType: AgentType) => void;
}

function AgentButton({
  agentType,
  onAdd,
  danger,
}: {
  agentType: AgentType;
  onAdd: (agentType: AgentType) => void;
  danger?: boolean;
}) {
  const contract = AGENT_CONTRACTS[agentType];
  return (
    <button
      type="button"
      className={danger ? `${styles.item} ${styles.itemDanger}` : styles.item}
      onClick={() => onAdd(agentType)}
      title={contract.description}
    >
      <span className={styles.plus} aria-hidden="true">
        +
      </span>
      {contract.label}
    </button>
  );
}

export function AgentLibrary({ onAdd }: AgentLibraryProps) {
  return (
    <div className={styles.library} aria-label="Agent library">
      <p className={styles.heading}>Add agent</p>
      <div className={styles.grid}>
        {STANDARD_AGENT_TYPES.map((agentType) => (
          <AgentButton key={agentType} agentType={agentType} onAdd={onAdd} />
        ))}
      </div>

      {SAFETY_AGENT_TYPES.length > 0 && (
        <>
          <p className={`${styles.heading} ${styles.safetyHeading}`}>Safety checks</p>
          <div className={styles.grid}>
            {SAFETY_AGENT_TYPES.map((agentType) => (
              <AgentButton key={agentType} agentType={agentType} onAdd={onAdd} danger />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
