import { Fragment, useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { Badge } from "../../../components/data-display/Badge";
import { Card } from "../../../components/data-display/Card";
import { Markdown } from "../../../components/data-display/Markdown";
import { Button } from "../../../components/actions/Button";
import { ResponseVote } from "../../../components/feedback/ResponseVote";
import { TextArea } from "../../../components/forms/TextArea";
import { EmptyState } from "../../../components/feedback/EmptyState";
import { LoadingSpinner } from "../../../components/feedback/LoadingSpinner";
import { PageContainer } from "../../../components/layout/PageContainer";
import { BuildApiError, runPipeline } from "../../build/api/pipelineApi";
import { usePipelineWorkspace } from "../../build/state/PipelineWorkspaceContext";
import { useEvaluationRuns } from "../../evaluate/state/EvaluationRunsContext";
import type { ChatResponseFeedback } from "../../evaluate/types/run";
import styles from "./RunPage.module.css";

function formatOutput(output: unknown): string {
  if (typeof output === "string") return output;
  return "```json\n" + JSON.stringify(output, null, 2) + "\n```";
}

/** A pipeline run is stateless server-side -- it only ever sees the `query` string
 * for this one call, with no memory of earlier turns. To make follow-up questions
 * ("what about the second one?") resolvable, prior turns are folded into the query
 * text itself. */
function buildQueryWithHistory(history: ChatResponseFeedback[], nextMessage: string): string {
  if (history.length === 0) return nextMessage;

  const transcript = history
    .map((entry) => `User: ${entry.query}\nAssistant: ${entry.answer}`)
    .join("\n");

  return `Previous chat history:\n${transcript}\n\nNew message from the user:\n${nextMessage}`;
}

export function RunPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { compileState, invalidatePipelineId } = usePipelineWorkspace();
  // The active run (picked in RunBar) is the one whose pipeline is compiled in
  // the workspace, so its responses and compileState.pipelineId always agree.
  const { activeRun, addResponse, setResponseFeedback } = useEvaluationRuns();

  const [query, setQuery] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [pendingQuery, setPendingQuery] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const pipelineId = compileState.pipelineId;
  const responses = activeRun?.responses ?? [];

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [responses.length, pendingQuery, isRunning, sendError]);

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

  const handleSend = async () => {
    const trimmed = query.trim();
    if (!trimmed || isRunning || !activeRun) return;

    const queryWithHistory = buildQueryWithHistory(responses, trimmed);
    const runId = activeRun.id;

    setPendingQuery(trimmed);
    setSendError(null);
    setQuery("");
    setIsRunning(true);

    try {
      const response = await runPipeline(pipelineId, queryWithHistory);
      addResponse(runId, { query: trimmed, answer: formatOutput(response.output) });
      setPendingQuery(null);
    } catch (error) {
      if (error instanceof BuildApiError && error.status === 404) {
        invalidatePipelineId(
          "The compiled pipeline was no longer found on the server. Compile again to run it.",
        );
        setPendingQuery(null);
      } else {
        setSendError(error instanceof BuildApiError ? error.message : "The run failed.");
      }
    } finally {
      setIsRunning(false);
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  };

  const handleVote = (responseId: string, vote: "up" | "down") => {
    if (!activeRun) return;
    const current = responses.find((entry) => entry.id === responseId);
    if (!current) return;
    setResponseFeedback(activeRun.id, responseId, {
      vote: current.vote === vote ? null : vote,
      explanation: current.explanation,
    });
  };

  const handleExplanationChange = (responseId: string, explanation: string) => {
    if (!activeRun) return;
    const current = responses.find((entry) => entry.id === responseId);
    if (!current) return;
    setResponseFeedback(activeRun.id, responseId, { vote: current.vote, explanation });
  };

  const isEmpty = responses.length === 0 && !pendingQuery;

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

      <Card padding="none" className={styles.chatCard}>
        <div className={styles.messages} ref={scrollRef}>
          {isEmpty ? (
            <div className={styles.emptyChat}>
              <EmptyState
                title="Nothing sent yet"
                description="Send a message to try your pipeline out."
              />
            </div>
          ) : (
            responses.map((entry) => (
              <Fragment key={entry.id}>
                <div className={`${styles.bubbleRow} ${styles.bubbleRowUser}`}>
                  <div className={`${styles.bubble} ${styles.bubbleUser}`}>
                    <p className={styles.userText}>{entry.query}</p>
                  </div>
                </div>
                <div className={`${styles.bubbleRow} ${styles.bubbleRowAssistant}`}>
                  <div className={`${styles.bubble} ${styles.bubbleAssistant}`}>
                    <Markdown content={entry.answer} />
                    <ResponseVote
                      vote={entry.vote}
                      explanation={entry.explanation}
                      onVote={(vote) => handleVote(entry.id, vote)}
                      onExplanationChange={(explanation) => handleExplanationChange(entry.id, explanation)}
                    />
                  </div>
                </div>
              </Fragment>
            ))
          )}

          {pendingQuery && (
            <div className={`${styles.bubbleRow} ${styles.bubbleRowUser}`}>
              <div className={`${styles.bubble} ${styles.bubbleUser}`}>
                <p className={styles.userText}>{pendingQuery}</p>
              </div>
            </div>
          )}
          {isRunning && (
            <div className={`${styles.bubbleRow} ${styles.bubbleRowAssistant}`}>
              <div className={`${styles.bubble} ${styles.bubbleAssistant}`}>
                <LoadingSpinner size="sm" label="Thinking…" />
              </div>
            </div>
          )}
          {sendError && (
            <div className={`${styles.bubbleRow} ${styles.bubbleRowAssistant}`}>
              <div className={`${styles.bubble} ${styles.bubbleAssistant} ${styles.bubbleError}`}>
                {sendError}
              </div>
            </div>
          )}
        </div>

        <div className={styles.composer}>
          <TextArea
            id="run-query"
            className={styles.composerInput}
            value={query}
            placeholder="Type a message and press Enter to send…"
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
          />
          <Button
            variant="primary"
            onClick={() => void handleSend()}
            disabled={isRunning || !query.trim()}
          >
            {isRunning ? "Running…" : "Send"}
          </Button>
        </div>
      </Card>
    </PageContainer>
  );
}
