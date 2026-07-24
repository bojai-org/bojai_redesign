import type {
  AgentContract,
  AgentFieldContract,
  DecisionOption,
  NodeValidationResult,
  PipelineNode,
  QuerySource,
} from "../types/pipeline";

function isQuerySource(value: unknown): value is QuerySource {
  return (
    typeof value === "object" &&
    value !== null &&
    "mode" in value &&
    typeof (value as { mode: unknown }).mode === "string"
  );
}

function validateQuerySource(value: unknown): string | null {
  if (!isQuerySource(value)) return "Choose a query source.";
  if (value.mode === "custom" && !value.value.trim()) {
    return "Enter a custom query.";
  }
  if (value.mode === "node" && !value.nodeId) {
    return "Choose a node to reuse the query from.";
  }
  return null;
}

function validateNumber(value: unknown, required: boolean): string | null {
  if (value === "" || value === null || value === undefined) {
    return required ? "Enter a number." : null;
  }
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric) || !Number.isInteger(numeric) || numeric <= 0) {
    return "Must be a positive whole number.";
  }
  return null;
}

function validateStringList(value: unknown, required: boolean): string | null {
  const items = Array.isArray(value) ? value : [];
  const nonEmpty = items.filter(
    (item) => typeof item === "string" && item.trim().length > 0,
  );
  if (required && nonEmpty.length === 0) {
    return "Add at least one item.";
  }
  return null;
}

function validateDecisionOptions(value: unknown): string | null {
  const options: DecisionOption[] = Array.isArray(value) ? value : [];
  if (options.length === 0) {
    return "Add at least one option, or connect a route to create one automatically.";
  }
  const trimmed = options.map((option) =>
    typeof option?.label === "string" ? option.label.trim() : "",
  );
  if (trimmed.some((label) => label.length === 0)) {
    return "Options cannot be empty.";
  }
  const unique = new Set(trimmed);
  if (unique.size !== trimmed.length) {
    return "Options must be unique.";
  }
  return null;
}

function validateField(
  field: AgentFieldContract,
  value: unknown,
  agentType: string,
): string | null {
  switch (field.type) {
    case "text":
    case "textarea":
    case "corpus":
      if (field.required && (typeof value !== "string" || !value.trim())) {
        return `${field.label} is required.`;
      }
      return null;
    case "string-list": {
      if (agentType === "Decision_Agent" && field.key === "options") {
        return validateDecisionOptions(value);
      }
      return validateStringList(value, field.required);
    }
    case "query-source":
      if (!field.required) return null;
      return validateQuerySource(value);
    case "number":
      return validateNumber(value, field.required);
    default:
      return null;
  }
}

export function validatePipelineNode(
  node: PipelineNode,
  contract: AgentContract,
): NodeValidationResult {
  const fieldErrors: Record<string, string> = {};

  for (const field of contract.fields) {
    const value = node.data.config[field.key];
    const error = validateField(field, value, contract.type);
    if (error) {
      fieldErrors[field.key] = error;
    }
  }

  return {
    valid: Object.keys(fieldErrors).length === 0,
    fieldErrors,
  };
}
