import { Badge } from "../../../components/data-display/Badge";
import { Modal } from "../../../components/feedback/Modal";
import type { QuestionEvalResult } from "../../build/types/evaluation";
import styles from "./QuestionDetailModal.module.css";

export interface QuestionDetailModalProps {
  result: QuestionEvalResult | null;
  onClose: () => void;
}

export function QuestionDetailModal({ result, onClose }: QuestionDetailModalProps) {
  return (
    <Modal open={result !== null} onClose={onClose} title="Question detail">
      {result && (
        <div className={styles.body}>
          <section>
            <h4 className={styles.label}>Question</h4>
            <p className={styles.text}>{result.question}</p>
          </section>

          {result.error ? (
            <section>
              <h4 className={styles.label}>Error</h4>
              <p className={styles.error}>{result.error}</p>
            </section>
          ) : (
            <>
              <div className={styles.answers}>
                <section>
                  <h4 className={styles.label}>Answer</h4>
                  <p className={styles.text}>{result.answer}</p>
                </section>
                <section>
                  <h4 className={styles.label}>Expected answer</h4>
                  <p className={styles.text}>{result.expected_answer}</p>
                </section>
              </div>

              <section>
                <h4 className={styles.label}>
                  Faithfulness{" "}
                  <Badge tone={result.faithfulness.faithful ? "ok" : "no"}>
                    {(result.faithfulness.score * 100).toFixed(0)}%
                  </Badge>
                </h4>
                <p className={styles.text}>{result.faithfulness.reason}</p>
              </section>

              <section>
                <h4 className={styles.label}>Expected resources</h4>
                {result.resource_matches.length === 0 ? (
                  <p className={styles.muted}>None specified for this question.</p>
                ) : (
                  <ul className={styles.matchList}>
                    {result.resource_matches.map((match, index) => (
                      <li key={index}>
                        <Badge tone={match.found ? "ok" : "no"}>
                          {match.found ? `found · rank ${match.rank}` : "not found"}
                        </Badge>
                        <span className={styles.matchLabel}>{match.expected}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section>
                <h4 className={styles.label}>Retrieved chunks ({result.retrieved_chunks.length})</h4>
                {result.retrieved_chunks.length === 0 ? (
                  <p className={styles.muted}>No resources were retrieved for this question.</p>
                ) : (
                  <ol className={styles.chunkList}>
                    {result.retrieved_chunks.map((chunk) => (
                      <li key={chunk.rank}>
                        <div className={styles.chunkMeta}>
                          <span>#{chunk.rank}</span>
                          {chunk.chunk_id && <span>id: {chunk.chunk_id}</span>}
                          {chunk.section && <span>{chunk.section}</span>}
                          {chunk.url && <span>{chunk.url}</span>}
                        </div>
                        <p className={styles.chunkText}>{chunk.text}</p>
                      </li>
                    ))}
                  </ol>
                )}
              </section>
            </>
          )}
        </div>
      )}
    </Modal>
  );
}
