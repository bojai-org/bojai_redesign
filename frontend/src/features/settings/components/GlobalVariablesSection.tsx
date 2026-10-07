import { useEffect, useRef, useState } from "react";
import { Button } from "../../../components/actions/Button";
import { IconButton } from "../../../components/actions/IconButton";
import { Card } from "../../../components/data-display/Card";
import { EmptyState } from "../../../components/feedback/EmptyState";
import { LoadingSpinner } from "../../../components/feedback/LoadingSpinner";
import { Modal } from "../../../components/feedback/Modal";
import { Toast } from "../../../components/feedback/Toast";
import { BuildApiError } from "../../build/api/pipelineApi";
import { deleteEnvVar, listEnvVars, setEnvVar } from "../api/settingsApi";
import { GlobalVariableModal } from "./GlobalVariableModal";
import styles from "./GlobalVariablesSection.module.css";

const PLUS_ICON = (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
    <path d="M12 5v14M5 12h14" />
  </svg>
);

const KEBAB_ICON = (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <circle cx="12" cy="5" r="1.8" />
    <circle cx="12" cy="12" r="1.8" />
    <circle cx="12" cy="19" r="1.8" />
  </svg>
);

/** Row-level "..." menu: Update / Delete. Closes on an outside click or Escape. */
function RowMenu({
  name,
  onUpdate,
  onDelete,
}: {
  name: string;
  onUpdate: () => void;
  onDelete: () => void;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) setOpen(false);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div className={styles.menuWrap} ref={wrapRef}>
      <IconButton
        label={`Actions for ${name}`}
        size="sm"
        icon={KEBAB_ICON}
        onClick={() => setOpen((current) => !current)}
      />
      {open && (
        <div className={styles.menu} role="menu">
          <button
            type="button"
            role="menuitem"
            className={styles.menuItem}
            onClick={() => {
              setOpen(false);
              onUpdate();
            }}
          >
            Update
          </button>
          <button
            type="button"
            role="menuitem"
            className={`${styles.menuItem} ${styles.menuItemDanger}`}
            onClick={() => {
              setOpen(false);
              onDelete();
            }}
          >
            Delete
          </button>
        </div>
      )}
    </div>
  );
}

/** Global variables -- process environment variables on the running backend
 * (backend/app.py's /config/env), mainly for LLM provider API keys. Kept
 * process-local by design (see backend/app.py's set_env_var docstring): no
 * encryption, nothing written to disk, lost on backend restart. Values are
 * never fetched back from the server -- GET /config/env returns names only. */
export function GlobalVariablesSection() {
  const [names, setNames] = useState<string[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [editingName, setEditingName] = useState<string | null>(null);
  const [deletingName, setDeletingName] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  // Bumped after every add/update/delete to re-run the load effect below,
  // without needing the fetch itself in the effect's dependency array.
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listEnvVars()
      .then((response) => {
        if (!cancelled) setNames(response.names);
      })
      .catch((error) => {
        if (!cancelled) {
          setLoadError(error instanceof BuildApiError ? error.message : "Could not load global variables.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  const modalOpen = addOpen || editingName !== null;

  const handleSave = async (name: string, value: string) => {
    try {
      await setEnvVar(name, value);
      setAddOpen(false);
      setEditingName(null);
      setReloadToken((token) => token + 1);
    } catch (error) {
      setToast(error instanceof BuildApiError ? error.message : "Could not save that variable.");
    }
  };

  const confirmDelete = async () => {
    if (!deletingName) return;
    const name = deletingName;
    setDeletingName(null);
    try {
      await deleteEnvVar(name);
      setReloadToken((token) => token + 1);
    } catch (error) {
      setToast(error instanceof BuildApiError ? error.message : "Could not delete that variable.");
    }
  };

  return (
    <Card padding="md" className={styles.card}>
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>Global variables</h2>
          <p className={styles.description}>
            API keys and other environment variables the backend reads at runtime (e.g.
            OPENAI_API_KEY). Stored only in the running backend process -- not encrypted,
            not written to disk, and lost on restart.
          </p>
        </div>
        <Button variant="primary" icon={PLUS_ICON} onClick={() => setAddOpen(true)}>
          Add variable
        </Button>
      </div>

      {names === null && !loadError && <LoadingSpinner size="sm" label="Loading global variables…" />}
      {loadError && <p className={styles.error}>{loadError}</p>}

      {names !== null && names.length === 0 && (
        <EmptyState title="No global variables yet" description="Add one to get started." />
      )}

      {names !== null && names.length > 0 && (
        <ul className={styles.list}>
          {names.map((name) => (
            <li key={name} className={styles.row}>
              <span className={styles.name}>{name}</span>
              <span className={styles.value} aria-hidden="true">
                ••••••••
              </span>
              <RowMenu
                name={name}
                onUpdate={() => setEditingName(name)}
                onDelete={() => setDeletingName(name)}
              />
            </li>
          ))}
        </ul>
      )}

      <GlobalVariableModal
        open={modalOpen}
        editingName={editingName}
        onClose={() => {
          setAddOpen(false);
          setEditingName(null);
        }}
        onSave={handleSave}
      />

      <Modal
        open={deletingName !== null}
        onClose={() => setDeletingName(null)}
        title="Delete global variable"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeletingName(null)}>
              Cancel
            </Button>
            <Button variant="danger-ghost" onClick={confirmDelete}>
              Delete
            </Button>
          </>
        }
      >
        {deletingName && (
          <p>
            Delete <strong>{deletingName}</strong>? Anything reading it from the backend
            environment will stop finding it.
          </p>
        )}
      </Modal>

      <Toast message={toast ?? ""} variant="error" visible={!!toast} onDismiss={() => setToast(null)} />
    </Card>
  );
}
