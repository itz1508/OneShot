/** TS mirror of the canonical bucket payload (see apps/rsm/src/rsm/bucket/model.py). */
export type SchemaVersion = "1";

export type BucketOrigin =
  | "markdown" | "text" | "pasted" | "stdin"
  | "chatgpt_export" | "pdf" | "folder" | "opaque";

export type BucketState =
  | "RECEIVED" | "STAGED" | "STORED"
  | "ACTIVATED" | "REPLAYED" | "RELEASED" | "RETIRED";

export type Bucket = {
  schema_version: SchemaVersion;
  bucket_id: string;
  hash: { algorithm: "sha256"; value: string };
  provenance: {
    origin: BucketOrigin;
    source_uri: string | null;
    derived_from: string | null;
    produced_at: string;
  };
  full_content: string;
  metadata: Record<string, unknown>;
  integrity_status: "unverified" | "verified" | "corrupt";
  state: BucketState;
  lifecycle: {
    received_at: string | null;
    staged_at: string | null;
    stored_at: string | null;
    activated_at: string | null;
    replayed_at: string | null;
    released_at: string | null;
    retired_at: string | null;
    release_count: number;
  };
  optional_summary: string | null;
};

export type BucketPayload = {
  schema_version: SchemaVersion;
  bucket: Bucket;
  integrity: { sha256: string };
};

/** Work classification (spec §9) — independent of lifecycle. */
export type WorkClassification =
  | "STORE" | "REVIEW" | "REVIEW_TODO" | "READY_EXECUTION";

/** Execution state (spec §10) — independent of lifecycle & content. */
export type ExecutionStatus =
  | "NOT_STARTED" | "IN_PROGRESS" | "COMPLETE" | "FAILED";
export type TaskStatus =
  | "PENDING" | "IN_PROGRESS" | "COMPLETE" | "FAILED" | "SKIPPED";
export type ExecutionState = {
  bucket_id: string;
  state: ExecutionStatus;
  tasks: Array<{ id: string; status: TaskStatus; note?: string | null }>;
};

/** Replay envelope (spec §14) — derived property, not a lifecycle state. */
export type Replayability =
  | "NOT_YET_REPLAYABLE" | "REPLAYABLE" | "REPLAY_BUILDABLE" | "NOT_REPLAYABLE";

export type ReplayEnvelope = {
  source: "rsm";
  bucket_id: string;
  schema_version: SchemaVersion;
  work_classification: WorkClassification;
  replayability: Replayability;
  content: {
    full_content: string;
    metadata: Record<string, unknown>;
    state: BucketState;
  };
  provenance: Bucket["provenance"];
  integrity: { algorithm: "sha256"; value: string };
};

/** V3 — Snapshot (bounded derived representation; see docs/architecture/snapshot.md). */
export type BudgetUnit = "bytes" | "characters" | "tokens_estimate";

export type ContextBudget = {
  unit: BudgetUnit;
  value: number;
  is_hard_limit: boolean;
};

export type SnapshotKind = "preserved" | "summary";

export type SnapshotContent = {
  kind: SnapshotKind;
  text: string;
  size_bytes: number;
  size_chars: number;
  reduced_from_bytes: number | null;
  reduced_from_chars: number | null;
  omitted_bytes: number | null;
  omitted_chars: number | null;
  summary_provider: string | null;
};

export type Snapshot = {
  schema_version: SchemaVersion;
  snapshot_id: string;
  bucket_id: string;
  created_at: string;
  context_budget: ContextBudget;
  source_size_bytes: number;
  source_size_chars: number;
  source_token_estimate: number;
  fits_within_budget: boolean;
  content: SnapshotContent;
  included_sources: string[];
  reduced_sources: string[];
  omitted_sources: string[];
  provenance: { derived_from: { kind: "rsm_bucket"; bucket_id: string; bucket_hash: string }; produced_at: string };
  integrity: { algorithm: "sha256"; value: string };
};

/** V3 — InteractionRecord (ADR 0009). */
export type InteractionRecord = {
  interaction_id: string;
  rsm_enabled: boolean;
  selected_bucket_id: string | null;
  last_streamed_at: string | null;
};

/** V3 — Stream payload returned by GET /v1/interactions/{id}/stream (ADR 0010). */
export type StreamPayload = {
  source: "rsm";
  schema_version: SchemaVersion;
  interaction_id: string;
  bucket_id: string;
  replay: ReplayEnvelope;
  snapshot: Snapshot;
};

/** Daemon error body (see rsm.api.errors.RSMError). */
export type RsmErrorBody = {
  code: string;
  message: string;
  details: Record<string, unknown>;
};

/** V3 Reader architecture — model mirror (see rsm/reader). */
export type FileType = "text" | "markdown" | "pdf" | "image" | "opaque" | "unknown";
export type FileAvailability = "readable" | "opaque" | "unreadable";
export type ReaderMethod = "text" | "document" | "ocr" | "vision" | "none";
export type ReaderStatus = "OBSERVED" | "PARTIAL" | "FAILED" | "NOT_OBSERVED";
export type ReaderEventKind =
  | "FILE_OBSERVED"
  | "FILE_PARTIAL"
  | "FILE_FAILED"
  | "READER_COMPLETE";

export type FileRef = {
  file_id: string;
  index: number;
  bucket_id: string;
  name: string;
  file_type: FileType;
  availability: FileAvailability;
  size_bytes: number;
  page_count: number | null;
  description: string | null;
};

export type FailureInfo = {
  file_id: string;
  index: number;
  reason: string;
  at: string;
};

export type FileCoverage = {
  file_id: string;
  index: number;
  status: ReaderStatus;
  method: ReaderMethod;
  vision: boolean;
  observed_bytes: number;
  observed_chars: number;
};

export type ReaderEvent = {
  kind: ReaderEventKind;
  at: string;
  file_id: string;
  index: number;
  method: ReaderMethod;
  vision: boolean;
  observed_bytes: number;
  observed_chars: number;
  reason: string | null;
};

export type ReaderTrace = {
  schema_version: SchemaVersion;
  bucket_id: string;
  discovered: number;
  latest_index: number;
  observed_count: number;
  partial_count: number;
  failed_count: number;
  complete: boolean;
  failures: FailureInfo[];
  coverage: FileCoverage[];
};

export type ScanResult = {
  schema_version: SchemaVersion;
  bucket_id: string;
  files: FileRef[];
  produced_at: string;
};

export type ReadResult = {
  schema_version: SchemaVersion;
  bucket_id: string;
  events: ReaderEvent[];
  trace: ReaderTrace;
};
