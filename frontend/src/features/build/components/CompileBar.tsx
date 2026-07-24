import { useState } from "react";
import { Button } from "../../../components/actions/Button";
import { Card } from "../../../components/data-display/Card";
import { CompileStatus } from "./CompileStatus";
import { CompilerJsonPreview } from "./CompilerJsonPreview";
import { RuntimeConfigEditor } from "./RuntimeConfigEditor";
import type { BuildValidationError, CompileState } from "../types/compiler";
import type { PipelineEdge, PipelineNode, PipelineRuntimeConfig } from "../types/pipeline";
import type { CompilerPipelineDefinition } from "../types/compiler";
import styles from "./CompileBar.module.css";

export interface CompileBarProps {
  runtimeConfig: PipelineRuntimeConfig;
  onRuntimeConfigChange: (value: PipelineRuntimeConfig) => void;
  compileState: CompileState;
  validationErrors: BuildValidationError[];
  previewDefinition: CompilerPipelineDefinition | null;
  previewError: string | null;
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  onCompile: () => void;
  /** Selects the node an error refers to, where the error names one. */
  onSelectErrorNode: (nodeId: string) => void;
}

const FIELD_ERROR_CODES = new Set(["missing-provider", "missing-model"]);

export function CompileBar({
  runtimeConfig,
  onRuntimeConfigChange,
  compileState,
  validationErrors,
  previewDefinition,
  previewError,
  nodes,
  edges,
  onCompile,
  onSelectErrorNode,
}: CompileBarProps) {
  const [previewOpen, setPreviewOpen] = useState(false);

  const providerError = validationErrors.find((error) => error.code === "missing-provider")?.message;
  const modelError = validationErrors.find((error) => error.code === "missing-model")?.message;
  const graphErrors = validationErrors.filter((error) => !FIELD_ERROR_CODES.has(error.code));

  const isBusy = compileState.status === "compiling" || compileState.status === "validating";
  const canCompile = validationErrors.length === 0 && !isBusy;
  const compileLabel = isBusy ? "Compiling…" : compileState.pipelineId ? "Recompile" : "Compile";

  return (
    <Card className={styles.bar} padding="md">
      <div className={styles.top}>
        <RuntimeConfigEditor
          value={runtimeConfig}
          onChange={onRuntimeConfigChange}
          providerError={providerError}
          modelError={modelError}
        />

        <div className={styles.statusAndActions}>
          <CompileStatus compileState={compileState} errorCount={validationErrors.length} />
          <div className={styles.actions}>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setPreviewOpen(true)}
              disabled={!previewDefinition}
            >
              Preview JSON
            </Button>
            <Button variant="primary" onClick={onCompile} disabled={!canCompile}>
              {compileLabel}
            </Button>
          </div>
        </div>
      </div>

      {graphErrors.length > 0 && (
        <ul className={styles.errorList}>
          {graphErrors.map((error, index) => (
            <li key={`${error.code}-${error.nodeId ?? error.edgeId ?? index}`}>
              {error.nodeId ? (
                <button
                  type="button"
                  className={styles.errorButton}
                  onClick={() => onSelectErrorNode(error.nodeId!)}
                >
                  {error.message}
                </button>
              ) : (
                <span className={styles.errorStatic}>{error.message}</span>
              )}
            </li>
          ))}
        </ul>
      )}

      <CompilerJsonPreview
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
        definition={previewDefinition}
        error={previewError}
        nodes={nodes}
        edges={edges}
      />
    </Card>
  );
}
