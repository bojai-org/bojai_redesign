import { FormField } from "../../../components/forms/FormField";
import { TextInput } from "../../../components/forms/TextInput";
import { TextArea } from "../../../components/forms/TextArea";
import { StringListEditor } from "./StringListEditor";
import { QuerySourceEditor } from "./QuerySourceEditor";
import type { AgentFieldContract, PipelineNode, QuerySource } from "../types/pipeline";

export interface AgentFieldRendererProps {
  field: AgentFieldContract;
  value: unknown;
  error?: string;
  onChange: (value: unknown) => void;
  /** Other nodes available to reuse a query from. Only used by "query-source" fields. */
  otherNodes: PipelineNode[];
}

export function AgentFieldRenderer({
  field,
  value,
  error,
  onChange,
  otherNodes,
}: AgentFieldRendererProps) {
  const fieldId = `agent-field-${field.key}`;

  return (
    <FormField
      label={field.required ? field.label : `${field.label} (optional)`}
      htmlFor={fieldId}
      hint={field.description}
      error={error}
    >
      {renderControl(field, fieldId, value, onChange, otherNodes)}
    </FormField>
  );
}

function renderControl(
  field: AgentFieldContract,
  fieldId: string,
  value: unknown,
  onChange: (value: unknown) => void,
  otherNodes: PipelineNode[],
) {
  switch (field.type) {
    case "text":
    case "corpus":
      return (
        <TextInput
          id={fieldId}
          value={typeof value === "string" ? value : ""}
          placeholder={field.placeholder}
          onChange={(event) => onChange(event.target.value)}
        />
      );

    case "textarea":
      return (
        <TextArea
          id={fieldId}
          value={typeof value === "string" ? value : ""}
          placeholder={field.placeholder}
          onChange={(event) => onChange(event.target.value)}
        />
      );

    case "number":
      return (
        <TextInput
          id={fieldId}
          type="number"
          min={1}
          step={1}
          value={value === "" || value === null || value === undefined ? "" : String(value)}
          placeholder={field.placeholder}
          onChange={(event) => {
            const raw = event.target.value;
            onChange(raw === "" ? "" : Number(raw));
          }}
        />
      );

    case "string-list": {
      const items = Array.isArray(value) ? (value as string[]) : [];
      return (
        <StringListEditor
          items={items.map((label, index) => ({ id: String(index), label }))}
          placeholder={field.placeholder}
          onAdd={() => onChange([...items, ""])}
          onRemove={(id) => onChange(items.filter((_, index) => String(index) !== id))}
          onLabelChange={(id, label) =>
            onChange(items.map((item, index) => (String(index) === id ? label : item)))
          }
        />
      );
    }

    case "query-source":
      return (
        <QuerySourceEditor
          value={
            value && typeof value === "object"
              ? (value as QuerySource)
              : { mode: "pipeline-input" }
          }
          onChange={onChange}
          otherNodes={otherNodes}
        />
      );

    default:
      return null;
  }
}
