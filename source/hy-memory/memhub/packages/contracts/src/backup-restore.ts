/**
 * Managed backup restore contract.
 *
 * Restore replaces the business database. Core refuses while a
 * Runtime-owned Core is live, accepts only managed sources under the
 * One Memory Home `backups/` directory, and takes a protective copy before
 * atomically replacing the live database.
 */

export interface BackupRestoreRequest {
  source: string;
}

export interface BackupRestoreResult {
  state: "restored";
  restored_bytes: number;
  previous_backup_path: string;
  source_schema_version: number;
}

export type BackupRestoreFailureCode =
  | "backup_restore_runtime_running"
  | "backup_restore_source_outside_home"
  | "backup_restore_source_invalid"
  | "backup_restore_source_too_new"
  | "backup_restore_protective_backup_failed"
  | "backup_restore_replace_failed";
