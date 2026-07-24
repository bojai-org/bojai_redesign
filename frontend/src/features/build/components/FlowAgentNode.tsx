import { Handle, Position } from "@xyflow/react";
import type { Node, NodeProps } from "@xyflow/react";
import type { CSSProperties } from "react";
import { DECISION_ADD_ROUTE_HANDLE, TARGET_HANDLE } from "../utils/handleIds";
import type { AgentContract, PipelineNode, SourceHandleDescriptor } from "../types/pipeline";
import styles from "./FlowAgentNode.module.css";

export interface FlowAgentNodeData extends Record<string, unknown> {
  node: PipelineNode;
  contract: AgentContract;
  valid: boolean;
  sourceHandles: SourceHandleDescriptor[];
}

export type FlowAgentNodeType = Node<FlowAgentNodeData, "agent">;

/**
 * Lays a source Handle out inline within its label row instead of React
 * Flow's default absolute centering, so nodes with several handles (e.g. a
 * Decision node's options) can list them vertically with visible labels.
 */
const INLINE_HANDLE_STYLE: CSSProperties = {
  position: "relative",
  top: "auto",
  right: "auto",
  left: "auto",
  transform: "none",
};

export function FlowAgentNode({ data, selected }: NodeProps<FlowAgentNodeType>) {
  const { node, contract, valid, sourceHandles } = data;

  const classes = [styles.node, valid ? "" : styles.invalid, selected ? styles.selected : ""]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={classes}>
      <Handle
        type="target"
        position={Position.Left}
        id={TARGET_HANDLE}
        className={styles.targetHandle}
      />

      <div className={styles.top}>
        <span className={styles.type}>{contract.label}</span>
        {valid && (
          <span className={styles.validMark} aria-label="Complete" title="Complete">
            <svg
              width="11"
              height="11"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M5 13l4 4L19 7" />
            </svg>
          </span>
        )}
      </div>
      <p className={styles.label}>{node.data.label}</p>

      <div className={styles.handleList}>
        {sourceHandles.map((handle) => (
          <div
            key={handle.id}
            className={
              handle.id === DECISION_ADD_ROUTE_HANDLE
                ? `${styles.handleRow} ${styles.addRouteRow}`
                : styles.handleRow
            }
          >
            <span className={styles.handleLabel}>{handle.label}</span>
            <Handle
              type="source"
              position={Position.Right}
              id={handle.id}
              className={styles.inlineHandle}
              style={INLINE_HANDLE_STYLE}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
