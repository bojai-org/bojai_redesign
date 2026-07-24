import { useState } from "react";
import { Button } from "../../../components/actions/Button";
import { Modal } from "../../../components/feedback/Modal";
import { buildNodeOrdinalMap } from "../utils/serializePipelineForCompiler";
import type { CompilerPipelineDefinition } from "../types/compiler";
import type { PipelineEdge, PipelineNode } from "../types/pipeline";
import styles from "./CompilerJsonPreview.module.css";

export interface CompilerJsonPreviewProps {
  open: boolean;
  onClose: () => void;
  definition: CompilerPipelineDefinition | null;
  error: string | null;
  nodes: PipelineNode[];
  edges: PipelineEdge[];
}

/**
 * Shows exactly the `definition` object serializePipelineForCompiler would
 * send -- no React Flow state, no decision-option ids, no safety-barrier or
 * _Static_Agent_Auto nodes, since the serializer never produces any of that.
 */
export function CompilerJsonPreview({
  open,
  onClose,
  definition,
  error,
  nodes,
  edges,
}: CompilerJsonPreviewProps) {
  const [copied, setCopied] = useState(false);

  const json = definition ? JSON.stringify(definition, null, 2) : null;
  const ordinalMap = definition ? buildNodeOrdinalMap(nodes, edges) : {};

  const handleCopy = async () => {
    if (!json) return;
    try {
      await navigator.clipboard.writeText(json);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard access can be denied by the browser; the JSON is still
      // visible and selectable, so this fails silently.
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Pipeline definition preview"
      footer={
        <Button variant="secondary" onClick={onClose}>
          Close
        </Button>
      }
    >
      {error && <p className={styles.error}>{error}</p>}

      {json && (
        <>
          <div className={styles.toolbar}>
            <Button size="sm" onClick={handleCopy}>
              {copied ? "Copied" : "Copy JSON"}
            </Button>
          </div>
          <pre className={styles.json}>{json}</pre>

          <details className={styles.ordinals}>
            <summary>Node ordinals (used for numeric query references)</summary>
            <table className={styles.ordinalTable}>
              <tbody>
                {Object.entries(ordinalMap).map(([nodeId, ordinal]) => (
                  <tr key={nodeId}>
                    <td className={styles.ordinalIndex}>{ordinal}</td>
                    <td className={styles.ordinalId}>{nodeId}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      )}
    </Modal>
  );
}
