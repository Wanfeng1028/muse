/** Desktop control metadata only; no paths, credentials or authority tokens. */
export interface ConnectionSetupCapability {
  available: boolean;
  reason:
    | "unsupported_platform"
    | "runtime_unavailable"
    | "storage_unavailable"
    | "noncanonical_data_dir"
    | "app_not_in_applications"
    | "closing"
    | null;
}
export interface ConnectionSetupSelection {
  syncSourceIds: string[];
  hostSourceIds: string[];
}
export interface ConnectionSetupExecute {
  planId: string;
  digest: string;
  userConfirmed: true;
}
export interface ConnectionSetupPreview {
  planId: string;
  operationId: string;
  digest: string;
  items: Array<{
    id: string;
    kind: "sync" | "install" | "readGrant";
    sourceIds: string[];
    hostId?: string;
    restoresRevoked: boolean;
    allowedTools?: readonly string[];
    allowedScopes?: readonly string[];
    previousTools?: readonly string[];
    previousScopes?: readonly string[];
    action?: "unchanged" | "add-rights" | "grant";
  }>;
}
export type ConnectionSetupItemState =
  | "pending"
  | "in_flight"
  | "succeeded"
  | "unknown"
  | "rejected"
  | "changed"
  | "not_applied"
  | "unavailable"
  | "dependency_blocked";
export interface ConnectionSetupItem {
  id: string;
  kind: "sync" | "install" | "readGrant";
  state: ConnectionSetupItemState;
  receipt: {
    kind: "install" | "readGrant";
    hostId: string;
    installationId: string;
    permissionRevision: number;
    allowedTools?: readonly string[];
    allowedScopes?: readonly string[];
  } | null;
}
export interface ConnectionSetupResult {
  operationId: string;
  planDigest: string;
  state: "completed" | "partial";
  recovery: "none" | "process" | "persistent";
  cancelled: boolean;
  items: ConnectionSetupItem[];
  skipped: Array<{
    id: string;
    state: "unchanged" | "changed" | "unavailable";
  }>;
}
/** Mutation-only journal digest is distinct from a preview's composite digest. */
export interface ConnectionSetupJournal {
  operationId: string;
  planDigest: string;
  revision: number;
  state: "completed" | "partial";
  items: ConnectionSetupItem[];
}
