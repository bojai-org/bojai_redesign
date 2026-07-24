import { SegmentedControl } from "../../../components/forms/SegmentedControl";
import { TextInput } from "../../../components/forms/TextInput";
import { Select } from "../../../components/forms/Select";
import type { PipelineNode, QuerySource } from "../types/pipeline";
import styles from "./QuerySourceEditor.module.css";

export interface QuerySourceEditorProps {
  value: QuerySource;
  onChange: (value: QuerySource) => void;
  /** Other nodes available to reuse a query from. Must already exclude the selected node. */
  otherNodes: PipelineNode[];
}

const MODE_OPTIONS = [
  { value: "pipeline-input", label: "Pipeline input" },
  { value: "custom", label: "Custom query" },
  { value: "node", label: "Reuse from node" },
];

export function QuerySourceEditor({
  value,
  onChange,
  otherNodes,
}: QuerySourceEditorProps) {
  const handleModeChange = (mode: string) => {
    if (mode === "pipeline-input") {
      onChange({ mode: "pipeline-input" });
    } else if (mode === "custom") {
      onChange({ mode: "custom", value: "" });
    } else {
      onChange({ mode: "node", nodeId: otherNodes[0]?.id ?? "" });
    }
  };

  return (
    <div className={styles.editor}>
      <SegmentedControl
        options={MODE_OPTIONS}
        value={value.mode}
        onChange={handleModeChange}
      />

      {value.mode === "custom" && (
        <TextInput
          className={styles.detail}
          value={value.value}
          placeholder="Write the query…"
          onChange={(event) =>
            onChange({ mode: "custom", value: event.target.value })
          }
        />
      )}

      {value.mode === "node" &&
        (otherNodes.length > 0 ? (
          <Select
            className={styles.detail}
            value={value.nodeId}
            onChange={(event) =>
              onChange({ mode: "node", nodeId: event.target.value })
            }
            options={otherNodes.map((node) => ({
              value: node.id,
              label: node.data.label,
            }))}
          />
        ) : (
          <p className={styles.empty}>No other nodes to reuse a query from yet.</p>
        ))}
    </div>
  );
}
