import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Badge } from "../../../components/data-display/Badge";
import { Card } from "../../../components/data-display/Card";
import { Button } from "../../../components/actions/Button";
import { TextArea } from "../../../components/forms/TextArea";
import { EmptyState } from "../../../components/feedback/EmptyState";
import { PageContainer } from "../../../components/layout/PageContainer";
import { BuildApiError, runPipeline } from "../../build/api/pipelineApi";
import { usePipelineWorkspace } from "../../build/state/PipelineWorkspaceContext";
import type { RunResponse } from "../../build/types/compiler";
import styles from "./RunPage.module.css";

function formatOutput(output: unknown): string {
  return typeof output === "string" ? output : JSON.stringify(output, null, 2);
}

export function RunPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { compileState, invalidatePipelineId } = usePipelineWorkspace();

  const [query, setQuery] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [result, setResult] = useState<RunResponse | null>(null);

  const pipelineId = compileState.pipelineId;

  if (!pipelineId) {
    return (
      <PageContainer width="wide">
        <EmptyState
          title="No compiled pipeline yet"
          description="Build a pipeline and compile it before you can run it."
          action={<Link to={`/projects/${projectId}/build`}>Go to Build</Link>}
        />
      </PageContainer>
    );
  }

  const handleRun = async () => {
    setIsRunning(true);
    setRunError(null);
    try {
      const response = await runPipeline(pipelineId, query.trim() ? query : undefined);
      setResult(response);
    } catch (error) {
      if (error instanceof BuildApiError && error.status === 404) {
        invalidatePipelineId(
          "The compiled pipeline was no longer found on the server. Compile again to run it.",
        );
        setResult(null);
      } else {
        setRunError(error instanceof BuildApiError ? error.message : "The run failed.");
      }
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <PageContainer width="wide">
      <Card padding="md" className={styles.header}>
        <div className={styles.headerRow}>
          <Badge tone="ok">Compiled</Badge>
          <span className={styles.pipelineId} title={pipelineId}>
            Pipeline ID: {pipelineId.length > 8 ? `${pipelineId.slice(0, 8)}…` : pipelineId}
          </span>
        </div>
        {compileState.status === "dirty" && (
          <p className={styles.staleNotice}>
            The graph has changed since this was compiled. Recompile in Build to run the latest
            version.
          </p>
        )}
      </Card>

      <Card padding="md" className={styles.runCard}>
        <label className={styles.label} htmlFor="run-query">
          Query
        </label>
        <TextArea
          id="run-query"
          value={query}
          placeholder="Type the message to send into the pipeline…"
          onChange={(event) => setQuery(event.target.value)}
          rows={4}
        />
        <div className={styles.actions}>
          <Button variant="primary" onClick={handleRun} disabled={isRunning}>
            {isRunning ? "Running…" : "Run"}
          </Button>
        </div>

        {runError && <p className={styles.error}>{runError}</p>}

        {result && (
          <div className={styles.result}>
            <p className={styles.resultLabel}>Output</p>
            <pre className={styles.output}>{formatOutput(result.output)}</pre>
          </div>
        )}
      </Card>
    </PageContainer>
  );
}
