import { Badge } from "../../../components/data-display/Badge";
import { Tag } from "../../../components/data-display/Tag";
import { Button } from "../../../components/actions/Button";
import { IconButton } from "../../../components/actions/IconButton";
import { FormField } from "../../../components/forms/FormField";
import { TextInput } from "../../../components/forms/TextInput";
import { AgentFieldRenderer } from "./AgentFieldRenderer";
import { StringListEditor } from "./StringListEditor";
import { STATIC_ROUTE_LABELS, getNodeOutputRoutes } from "../contracts/agentContracts";
import { createDecisionOption } from "../utils/createDecisionOption";
import { getDecisionOptions } from "../utils/getDecisionOptions";
import type {
  AgentContract,
  AgentFieldContract,
  DecisionOption,
  NodeValidationResult,
  PipelineNode,
} from "../types/pipeline";
import styles from "./AgentInspector.module.css";

export interface AgentInspectorProps {
  node: PipelineNode;
  contract: AgentContract;
  otherNodes: PipelineNode[];
  validation: NodeValidationResult;
  /** True when `node` has zero incoming edges. Hides `entryOnly` fields on every other node. */
  isEntryNode: boolean;
  onLabelChange: (label: string) => void;
  onFieldChange: (key: string, value: unknown) => void;
  onDelete: () => void;
  onClose: () => void;
  /** Removes a decision option and its outgoing edge (if any). Ignored for non-Decision nodes. */
  onRemoveDecisionOption: (optionId: string) => void;
}

function isDecisionOptionsField(contract: AgentContract, field: AgentFieldContract): boolean {
  return contract.type === "Decision_Agent" && field.key === "options";
}

export function AgentInspector({
  node,
  contract,
  otherNodes,
  validation,
  isEntryNode,
  onLabelChange,
  onFieldChange,
  onDelete,
  onClose,
  onRemoveDecisionOption,
}: AgentInspectorProps) {
  const routes = getNodeOutputRoutes(node, contract);

  // Visibility only — entryOnly fields keep their stored config value and
  // stay out of validation regardless of whether they're shown here.
  const visibleFields = contract.fields.filter((field) => !field.entryOnly || isEntryNode);

  return (
    <aside className={styles.panel} aria-label="Agent inspector">
      <div className={styles.header}>
        <div className={styles.headerTop}>
          <Badge tone={validation.valid ? "ok" : "no"}>
            {validation.valid ? "Valid" : "Incomplete"}
          </Badge>
          <IconButton
            label="Close inspector"
            size="sm"
            onClick={onClose}
            icon={
              <svg
                width="13"
                height="13"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                aria-hidden="true"
              >
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            }
          />
        </div>
        <p className={styles.type}>{contract.label}</p>
        <p className={styles.description}>{contract.description}</p>
      </div>

      <FormField label="Node name" htmlFor="agent-node-label">
        <TextInput
          id="agent-node-label"
          value={node.data.label}
          onChange={(event) => onLabelChange(event.target.value)}
        />
      </FormField>

      {visibleFields.map((field) =>
        isDecisionOptionsField(contract, field) ? (
          <DecisionOptionsField
            key={field.key}
            field={field}
            options={getDecisionOptions(node)}
            error={validation.fieldErrors[field.key]}
            onChange={(options) => onFieldChange(field.key, options)}
            onRemove={onRemoveDecisionOption}
          />
        ) : (
          <AgentFieldRenderer
            key={field.key}
            field={field}
            value={node.data.config[field.key]}
            error={validation.fieldErrors[field.key]}
            onChange={(value) => onFieldChange(field.key, value)}
            otherNodes={otherNodes}
          />
        ),
      )}

      <div className={styles.routes}>
        <p className={styles.routesLabel}>Output routes</p>
        <div className={styles.routeTags}>
          {routes.length > 0 ? (
            routes.map((route) => (
              <Tag key={route}>{contract.dynamicRoutes ? route : (STATIC_ROUTE_LABELS[route] ?? route)}</Tag>
            ))
          ) : (
            <p className={styles.empty}>
              {contract.dynamicRoutes
                ? "Add options above to create routes."
                : "No outgoing routes."}
            </p>
          )}
        </div>
      </div>

      <Button variant="danger-ghost" onClick={onDelete}>
        Delete node
      </Button>
    </aside>
  );
}

interface DecisionOptionsFieldProps {
  field: AgentFieldContract;
  options: DecisionOption[];
  error?: string;
  onChange: (options: DecisionOption[]) => void;
  onRemove: (optionId: string) => void;
}

function DecisionOptionsField({
  field,
  options,
  error,
  onChange,
  onRemove,
}: DecisionOptionsFieldProps) {
  const handleAdd = () => {
    onChange([...options, createDecisionOption("", options, "manual")]);
  };

  const handleLabelChange = (id: string, label: string) => {
    onChange(
      options.map((option) =>
        option.id === id ? { ...option, label, origin: "manual" } : option,
      ),
    );
  };

  return (
    <FormField
      label={field.required ? field.label : `${field.label} (optional)`}
      hint={field.description}
      error={error}
    >
      <StringListEditor
        items={options.map((option) => ({ id: option.id, label: option.label }))}
        placeholder="Option label"
        addLabel="Add option"
        onAdd={handleAdd}
        onRemove={onRemove}
        onLabelChange={handleLabelChange}
      />
      <p className={styles.autoHint}>
        Removing an option also removes its connection. Options created by
        connecting a route are named after the target node until edited here.
      </p>
    </FormField>
  );
}
