import type { DecisionOption, PipelineNode } from "../types/pipeline";

function isDecisionOption(value: unknown): value is DecisionOption {
  return (
    !!value &&
    typeof value === "object" &&
    typeof (value as DecisionOption).id === "string" &&
    typeof (value as DecisionOption).label === "string"
  );
}

/** The Decision_Agent node's configured options, in stored order. */
export function getDecisionOptions(node: PipelineNode): DecisionOption[] {
  const raw = node.data.config.options;
  return Array.isArray(raw) ? raw.filter(isDecisionOption) : [];
}

/** Returns a new node with its `options` config replaced. */
export function setDecisionOptions(
  node: PipelineNode,
  options: DecisionOption[],
): PipelineNode {
  return {
    ...node,
    data: {
      ...node.data,
      config: { ...node.data.config, options },
    },
  };
}
