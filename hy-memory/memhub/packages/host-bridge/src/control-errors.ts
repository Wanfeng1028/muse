const CODES = new Set([
  "sync_hook_remove_first",
  "sync_hook_preview_stale",
  "sync_hook_apply_failed",
  "sync_hook_connection_changed",
  "sync_hook_connection_required",
  "sync_hook_unsupported",
  "host_install_preview_stale",
  "host_install_failed",
  "host_install_modified_files",
  "host_uninstall_preview_stale",
  "host_uninstall_modified_files",
  "host_uninstall_needs_review",
  "host_permission_relink_required",
  "host_permission_installation_incomplete",
  "host_permission_unavailable",
  "host_permission_storage_unsafe",
  "host_permission_transport_unsupported",
  "connection_controller_needs_attention",
  "connection_controller_recovery_required",
  "connection_controller_plan_missing",
  "connection_controller_plan_changed",
]);

/** Actionable fixed codes only. These do not prove that a mutation had no effect. */
export function isConnectionControlError(value: unknown): value is string {
  return typeof value === "string" && CODES.has(value);
}
