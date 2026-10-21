/** RCL v2 contract only. No route/capability is enabled by exporting these types. */
export type RetrievalIntent =
  | "artifact"
  | "fact"
  | "decision"
  | "timeline"
  | "resume";
export type RetrievalChannel =
  | "lexical"
  | "semantic"
  | "object"
  | "governed_semantic";
export type RetrievalLimit =
  | "count_budget"
  | "character_budget"
  | "timeout_budget"
  | "metadata_budget"
  | "candidate_budget"
  | "coverage_budget";

export interface ContextHintsV2 {
  task_text?: string;
  /** Relevance hints only, never evidence-read authorization. */
  already_seen_refs?: string[];
}
export interface ContextSearchRequestV2 {
  operation?: "search";
  query: string;
  kinds?: Array<"raw" | "memory">;
  raw_source_ids?: string[] | null;
  intent?: "auto" | RetrievalIntent;
  context_hints?: ContextHintsV2;
  enhancement?: "local" | "auto";
  limit?: number;
  character_budget?: number;
  timeout_ms?: number;
}
export interface ContextExpandRequestV2 {
  operation: "expand";
  expand_ref: string;
  character_budget?: number;
  message_limit?: number;
  timeout_ms?: number;
}
export type ContextRequestV2 = ContextSearchRequestV2 | ContextExpandRequestV2;

export interface RetrievalTimeRange {
  start: string;
  end: string;
}
/** Unicode code-point offsets, not JavaScript UTF-16 string indices. */
export interface EvidenceSpanV2 {
  start_cp: number;
  end_cp: number;
  text: string;
}
export interface RawEvidenceV2 {
  kind: "raw";
  evidence_id: string;
  revision: number;
  source_id: string;
  conversation_id: string;
  role: string;
  written_by: "person" | "agent" | "tool" | "unknown";
  event_time: string | null;
  spans: EvidenceSpanV2[];
  matched_by: Array<"lexical" | "semantic" | "object">;
  expand_ref: string | null;
}
export interface GovernedEvidenceV2 {
  kind: "memory";
  memory_id: string;
  revision: number;
  content: string;
  memory_kind: string;
  updated_at: string;
  evidence_ids: string[];
  matched_by: Array<"lexical" | "governed_semantic">;
}
export type EvidenceItemV2 = RawEvidenceV2 | GovernedEvidenceV2;
export interface ObjectReferenceV2 {
  kind: "url" | "path" | "explicit_id";
  evidence_id: string;
  revision: number;
  span: EvidenceSpanV2;
}
export interface EvidenceGroupV2 {
  group_id: string;
  answer_target: RetrievalIntent;
  object_refs: ObjectReferenceV2[];
  decision_status:
    | "supported"
    | "ambiguous"
    | "missing_confirmation"
    | "conflicting"
    | "coverage_limited";
  missing_requirements: string[];
  items: EvidenceItemV2[];
}
export interface RetrievalPathV2 {
  status:
    | "ok"
    | "empty"
    | "not_requested"
    | "not_authorized"
    | "unavailable"
    | "degraded";
  reason: string | null;
  returned_count: number;
  searched_channels: RetrievalChannel[];
  coverage: "complete" | "partial" | "not_searched" | "unavailable";
  truncated_by: RetrievalLimit[];
}
export interface RetrievalResponseV2 {
  schema_version: 2;
  request_id: string;
  state: "grounded" | "empty" | "partial" | "unavailable";
  paths: { raw: RetrievalPathV2; memory: RetrievalPathV2 };
  plan: {
    intent: RetrievalIntent;
    interpreted_time_range: RetrievalTimeRange | null;
    time_origin: "none" | "explicit" | "rule" | "model";
    unresolved_constraints: string[];
  };
  groups: EvidenceGroupV2[];
  enhancement: {
    attempted: boolean;
    used: boolean;
    reason: string | null;
    model_profile_revision: number | null;
    usage_state: "not_attempted" | "known" | "unknown";
  };
  budget: { used_characters: number; total_ms: number; truncated: boolean };
  adoption: "unknown";
}
