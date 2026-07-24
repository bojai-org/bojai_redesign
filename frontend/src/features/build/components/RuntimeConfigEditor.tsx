import { FormField } from "../../../components/forms/FormField";
import { TextInput } from "../../../components/forms/TextInput";
import type { PipelineRuntimeConfig } from "../types/pipeline";
import styles from "./RuntimeConfigEditor.module.css";

export interface RuntimeConfigEditorProps {
  value: PipelineRuntimeConfig;
  onChange: (value: PipelineRuntimeConfig) => void;
  providerError?: string;
  modelError?: string;
}

/**
 * Pipeline-level provider/model config -- backend/contract.md's top-level
 * `config`. Plain text inputs: the project doesn't maintain a provider ->
 * model list anywhere, so this doesn't invent one.
 */
export function RuntimeConfigEditor({
  value,
  onChange,
  providerError,
  modelError,
}: RuntimeConfigEditorProps) {
  return (
    <div className={styles.grid}>
      <FormField label="Provider" htmlFor="runtime-provider" error={providerError}>
        <TextInput
          id="runtime-provider"
          value={value.provider}
          placeholder="openai"
          onChange={(event) => onChange({ ...value, provider: event.target.value })}
        />
      </FormField>
      <FormField label="Model" htmlFor="runtime-model" error={modelError}>
        <TextInput
          id="runtime-model"
          value={value.model}
          placeholder="gpt-4o-mini"
          onChange={(event) => onChange({ ...value, model: event.target.value })}
        />
      </FormField>
    </div>
  );
}
