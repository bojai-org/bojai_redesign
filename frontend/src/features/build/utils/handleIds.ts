/**
 * Stable connection-handle id conventions, shared by FlowAgentNode (renders
 * handles), agentContracts.ts (derives which handles a node has), and the
 * connection-resolution utils (interpret which handle a drag started from).
 */

export const TARGET_HANDLE = "target";

export const DECISION_ADD_ROUTE_HANDLE = "decision-add-route";

const STATIC_ROUTE_PREFIX = "source:";
const DECISION_OPTION_PREFIX = "decision-option:";

export function staticRouteHandleId(route: string): string {
  return `${STATIC_ROUTE_PREFIX}${route}`;
}

/** Route name encoded in a static (non-decision) source handle id, e.g. "source:next" -> "next". */
export function parseStaticRouteHandleId(handleId: string): string | undefined {
  return handleId.startsWith(STATIC_ROUTE_PREFIX)
    ? handleId.slice(STATIC_ROUTE_PREFIX.length)
    : undefined;
}

export function decisionOptionHandleId(optionId: string): string {
  return `${DECISION_OPTION_PREFIX}${optionId}`;
}

/** DecisionOption id encoded in a decision-option source handle id, or null if this isn't one. */
export function parseDecisionOptionHandleId(handleId: string): string | null {
  return handleId.startsWith(DECISION_OPTION_PREFIX)
    ? handleId.slice(DECISION_OPTION_PREFIX.length)
    : null;
}
