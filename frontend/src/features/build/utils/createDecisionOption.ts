import { createUniqueOptionLabel } from "./createUniqueOptionLabel";
import type { DecisionOption } from "../types/pipeline";

function nextOptionId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `option-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * Creates a new decision option with a stable id.
 *
 * For "auto" options (created by connecting the add-route handle to a
 * target node) the label is disambiguated against existing option labels.
 * For "manual" options (added by hand in the inspector) the label is used
 * as-is, since it usually starts blank for the user to fill in.
 */
export function createDecisionOption(
  label: string,
  existingOptions: DecisionOption[],
  origin: DecisionOption["origin"],
  targetNodeId?: string,
): DecisionOption {
  return {
    id: nextOptionId(),
    label: origin === "auto" ? createUniqueOptionLabel(label, existingOptions) : label,
    origin,
    ...(targetNodeId ? { targetNodeId } : {}),
  };
}
