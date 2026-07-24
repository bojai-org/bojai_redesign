import { Badge } from "../../../components/data-display/Badge";
import { LoadingSpinner } from "../../../components/feedback/LoadingSpinner";
import type { CompileState } from "../types/compiler";
import styles from "./CompileStatus.module.css";

export interface CompileStatusProps {
  compileState: CompileState;
  /** Number of local validation errors currently blocking compile. */
  errorCount: number;
}

function truncatePipelineId(pipelineId: string): string {
  return pipelineId.length > 8 ? `${pipelineId.slice(0, 8)}…` : pipelineId;
}

export function CompileStatus({ compileState, errorCount }: CompileStatusProps) {
  if (errorCount > 0) {
    return (
      <div className={styles.row}>
        <Badge tone="amber">
          {errorCount} configuration {errorCount === 1 ? "error" : "errors"}
        </Badge>
      </div>
    );
  }

  switch (compileState.status) {
    case "dirty":
      return (
        <div className={styles.row}>
          <Badge tone="neutral">
            {compileState.pipelineId ? "Changes not compiled" : "Not compiled"}
          </Badge>
        </div>
      );

    case "validating":
    case "compiling":
      return (
        <div className={styles.row}>
          <LoadingSpinner size="sm" />
          <span className={styles.text}>
            {compileState.status === "validating" ? "Validating…" : "Compiling…"}
          </span>
        </div>
      );

    case "compiled":
      return (
        <div className={styles.row}>
          <Badge tone="ok">
            {compileState.successCount > 1 ? "Recompiled successfully" : "Compiled successfully"}
          </Badge>
          {compileState.pipelineId && (
            <span className={styles.pipelineId} title={compileState.pipelineId}>
              Pipeline ID: {truncatePipelineId(compileState.pipelineId)}
            </span>
          )}
        </div>
      );

    case "failed":
      return (
        <div className={styles.column}>
          <Badge tone="no">Compile failed</Badge>
          {compileState.error && <p className={styles.errorText}>{compileState.error}</p>}
        </div>
      );

    default:
      return null;
  }
}
