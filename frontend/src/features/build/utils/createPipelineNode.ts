import { AGENT_CONTRACTS } from "../contracts/agentContracts";
import type { AgentType, PipelineNode } from "../types/pipeline";

function cloneDefault(value: unknown): unknown {
  if (Array.isArray(value)) return [...value];
  if (value && typeof value === "object") return { ...value };
  return value;
}

function nextId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `node-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function createPipelineNode(
  agentType: AgentType,
  position: { x: number; y: number },
): PipelineNode {
  const contract = AGENT_CONTRACTS[agentType];
  const config: Record<string, unknown> = {};
  for (const field of contract.fields) {
    config[field.key] = cloneDefault(field.defaultValue);
  }

  return {
    id: nextId(),
    position,
    data: {
      agentType,
      label: contract.label,
      config,
    },
  };
}
