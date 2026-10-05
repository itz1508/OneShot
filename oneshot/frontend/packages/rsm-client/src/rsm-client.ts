/**
 * Typed fetch wrapper for the RSM daemon HTTP transport.
 *
 * The UI MUST NOT persist bucket state locally (spec §3). All reads and writes
 * go through the daemon.
 */

import type {
  BucketPayload, ExecutionState, InteractionRecord, ReadResult,
  ReaderTrace, ReplayEnvelope, RsmErrorBody, ScanResult, StreamPayload,
  WorkClassification,
} from "@/types/bucket";

export class RsmHttpError extends Error {
  readonly status: number;
  readonly body: RsmErrorBody | null;

  constructor(status: number, body: RsmErrorBody | null, message: string) {
    super(message);
    this.status = status;
    this.body = body;
    this.name = "RsmHttpError";
  }

  get code(): string | null {
    return this.body?.code ?? null;
  }
}

async function _assertOk(r: Response, op: string): Promise<void> {
  if (r.ok) return;
  let body: RsmErrorBody | null = null;
  try {
    const raw: unknown = await r.json();
    // Two daemon error shapes reach the browser:
    //   * `RSMError` handler      -> flat    {"code", "message", "details"}
    //   * FastAPI `HTTPException` -> nested  {"detail": {"code", "message"}}
    //     (bare framework errors may carry a plain-string `detail`).
    // Normalise both to the canonical `RsmErrorBody` so `RsmHttpError.code`
    // always carries the daemon error code.
    const detail = (raw as { detail?: unknown } | null)?.detail;
    body =
      typeof detail === "object" && detail !== null && "code" in detail
        ? (detail as RsmErrorBody)
        : (raw as RsmErrorBody);
  } catch { body = null; }
  throw new RsmHttpError(r.status, body, `${op} failed: ${r.status}${body?.code ? " " + body.code : ""}`);
}


function _bytesToBase64(bytes: Uint8Array): string {
  // Compact chunked encoder to avoid "Maximum call stack size exceeded"
  // for large PDFs.
  const chunk = 0x8000;
  let s = "";
  for (let i = 0; i < bytes.length; i += chunk) {
    s += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(s);
}

export class RsmClient {
  constructor(private readonly base = "http://127.0.0.1:8787") {}

  async health(): Promise<{ status: string; schema_version: "1" }> {
    const r = await fetch(`${this.base}/healthz`);
    if (!r.ok) throw new Error(`healthz ${r.status}`);
    return r.json();
  }

  async listBuckets(): Promise<string[]> {
    const r = await fetch(`${this.base}/v1/buckets/`);
    if (!r.ok) throw new Error(`list ${r.status}`);
    const body = await r.json();
    return body.bucket_ids as string[];
  }

  /** Read a single Bucket payload (V1 API). */
  async readBucketPayload(id: string): Promise<BucketPayload> {
    const r = await fetch(`${this.base}/v1/buckets/${encodeURIComponent(id)}`);
    if (!r.ok) throw new Error(`read ${r.status}`);
    return r.json();
  }

  async ingestText(
    content: string,
    opts: { kind?: "text" | "pasted" | "stdin"; sourceUri?: string; expectedHash?: string } = {},
  ): Promise<BucketPayload> {
    const r = await fetch(`${this.base}/v1/buckets/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content,
        kind: opts.kind ?? "text",
        source_uri: opts.sourceUri ?? null,
        ...(opts.expectedHash ? { expected_hash: opts.expectedHash } : {}),
      }),
    });
    await _assertOk(r, "ingestText");
    return r.json();
  }

  async ingestMarkdown(
    content: string,
    opts: { sourceUri?: string; expectedHash?: string } = {},
  ): Promise<BucketPayload> {
    const r = await fetch(`${this.base}/v1/buckets/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kind: "markdown",
        content,
        source_uri: opts.sourceUri ?? null,
        ...(opts.expectedHash ? { expected_hash: opts.expectedHash } : {}),
      }),
    });
    await _assertOk(r, "ingestMarkdown");
    return r.json();
  }

  async ingestPdf(
    bytes: Uint8Array,
    opts: { sourceUri?: string; expectedHash?: string } = {},
  ): Promise<BucketPayload> {
    const b64 = _bytesToBase64(bytes);
    const r = await fetch(`${this.base}/v1/buckets/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kind: "pdf",
        content_base64: b64,
        source_uri: opts.sourceUri ?? null,
        ...(opts.expectedHash ? { expected_hash: opts.expectedHash } : {}),
      }),
    });
    await _assertOk(r, "ingestPdf");
    return r.json();
  }

  async ingestOpaque(
    bytes: Uint8Array,
    opts: { sourceUri?: string; mediaType?: string; expectedHash?: string } = {},
  ): Promise<BucketPayload> {
    const b64 = _bytesToBase64(bytes);
    const r = await fetch(`${this.base}/v1/buckets/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kind: "opaque",
        content_base64: b64,
        source_uri: opts.sourceUri ?? null,
        media_type: opts.mediaType ?? null,
        ...(opts.expectedHash ? { expected_hash: opts.expectedHash } : {}),
      }),
    });
    await _assertOk(r, "ingestOpaque");
    return r.json();
  }

  async ingestChatGptExport(
    payload: unknown,
    opts: { sourceUri?: string; expectedHash?: string } = {},
  ): Promise<BucketPayload> {
    const r = await fetch(`${this.base}/v1/buckets/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kind: "chatgpt_export",
        payload,
        source_uri: opts.sourceUri ?? null,
        ...(opts.expectedHash ? { expected_hash: opts.expectedHash } : {}),
      }),
    });
    await _assertOk(r, "ingestChatGptExport");
    return r.json();
  }

  /** D.1-B — browser-origin ZIP upload (multipart). */
  async uploadZip(
    file: File,
    opts: { sourceUri?: string; expectedHash?: string; signal?: AbortSignal } = {},
  ): Promise<BucketPayload & { children: string[] }> {
    const form = new FormData();
    form.append("file", file, file.name);
    if (opts.sourceUri) form.append("source_uri", opts.sourceUri);
    if (opts.expectedHash) form.append("expected_hash", opts.expectedHash);
    const r = await fetch(`${this.base}/v1/buckets/upload-zip`, {
      method: "POST",
      body: form,
      signal: opts.signal,
    });
    await _assertOk(r, "uploadZip");
    return r.json();
  }

  async transition(id: string, to: string): Promise<BucketPayload> {
    const r = await fetch(
      `${this.base}/v1/buckets/${encodeURIComponent(id)}/transition`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ to }),
      },
    );
    if (!r.ok) throw new Error(`transition ${r.status}`);
    return r.json();
  }

  async activate(id: string): Promise<BucketPayload> {
    const r = await fetch(
      `${this.base}/v1/buckets/${encodeURIComponent(id)}/activate`,
      { method: "POST" },
    );
    if (!r.ok) throw new Error(`activate ${r.status}`);
    return r.json();
  }

  async release(id: string): Promise<BucketPayload> {
    const r = await fetch(
      `${this.base}/v1/buckets/${encodeURIComponent(id)}/release`,
      { method: "POST" },
    );
    if (!r.ok) throw new Error(`release ${r.status}`);
    return r.json();
  }

  async replay(id: string): Promise<ReplayEnvelope> {
    const r = await fetch(
      `${this.base}/v1/buckets/${encodeURIComponent(id)}/replay`,
    );
    if (!r.ok) throw new Error(`replay ${r.status}`);
    return r.json();
  }

  async exportBucket(id: string): Promise<string> {
    const r = await fetch(
      `${this.base}/v1/buckets/${encodeURIComponent(id)}/export`,
    );
    if (!r.ok) throw new Error(`export ${r.status}`);
    return r.text();
  }

  async getClassification(
    id: string,
  ): Promise<{ bucket_id: string; work_classification: WorkClassification }> {
    const r = await fetch(
      `${this.base}/v1/buckets/${encodeURIComponent(id)}/classification`,
    );
    if (!r.ok) throw new Error(`classification ${r.status}`);
    return r.json();
  }

  async setClassification(
    id: string,
    classification: WorkClassification,
  ): Promise<{ bucket_id: string; work_classification: WorkClassification }> {
    const r = await fetch(
      `${this.base}/v1/buckets/${encodeURIComponent(id)}/classification`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ work_classification: classification }),
      },
    );
    if (!r.ok) throw new Error(`classification put ${r.status}`);
    return r.json();
  }

  async getExecution(id: string): Promise<ExecutionState> {
    const r = await fetch(
      `${this.base}/v1/buckets/${encodeURIComponent(id)}/execution`,
    );
    if (!r.ok) throw new Error(`execution ${r.status}`);
    return r.json();
  }

  async putExecution(
    id: string,
    state: Omit<ExecutionState, "bucket_id">,
  ): Promise<ExecutionState> {
    const r = await fetch(
      `${this.base}/v1/buckets/${encodeURIComponent(id)}/execution`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(state),
      },
    );
    if (!r.ok) throw new Error(`execution put ${r.status}`);
    return r.json();
  }


  /** V3 (ADR 0009): read the interaction record. Unknown ⇒ fail-closed default. */
  async getInteraction(interactionId: string): Promise<InteractionRecord> {
    const r = await fetch(
      `${this.base}/v1/interactions/${encodeURIComponent(interactionId)}`,
    );
    await _assertOk(r, "getInteraction");
    return r.json();
  }

  /** V3 (ADR 0009): write the interaction record. */
  async putInteraction(
    interactionId: string,
    patch: { rsmEnabled?: boolean; selectedBucketId?: string | null },
  ): Promise<InteractionRecord> {
    const body: Record<string, unknown> = {};
    if (patch.rsmEnabled !== undefined) body.rsm_enabled = patch.rsmEnabled;
    if (patch.selectedBucketId !== undefined) {
      body.selected_bucket_id = patch.selectedBucketId;
    }
    const r = await fetch(
      `${this.base}/v1/interactions/${encodeURIComponent(interactionId)}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    );
    await _assertOk(r, "putInteraction");
    return r.json();
  }

  /**
   * V3 (ADR 0010): ReplayStreaming — one JSON chunk over chunked HTTP.
   *
   * Returns a lazy iterator so callers can observe "a chunk arrived". For
   * V3's one-chunk transport this yields exactly one `StreamPayload` and
   * then ends. `signal` cancels the fetch (closes the HTTP connection); the
   * daemon records nothing on cancellation.
   */
  async *streamInteraction(
    interactionId: string,
    opts: { budgetUnit?: "bytes" | "characters" | "tokens_estimate"; budgetValue?: number; reduce?: "null" | "prefix"; signal?: AbortSignal } = {},
  ): AsyncGenerator<StreamPayload, void, unknown> {
    const qs = new URLSearchParams();
    if (opts.budgetUnit) qs.set("budget_unit", opts.budgetUnit);
    if (opts.budgetValue !== undefined) qs.set("budget_value", String(opts.budgetValue));
    if (opts.reduce) qs.set("reduce", opts.reduce);
    const url =
      `${this.base}/v1/interactions/${encodeURIComponent(interactionId)}/stream` +
      (qs.toString() ? `?${qs.toString()}` : "");
    const r = await fetch(url, { signal: opts.signal });
    await _assertOk(r, "streamInteraction");
    const body = (await r.json()) as StreamPayload;
    yield body;
  }


  /** V3 Reader: fast shallow discovery for one Bucket. */
  async scanBucket(id: string): Promise<ScanResult> {
    const r = await fetch(`${this.base}/v1/buckets/${encodeURIComponent(id)}/scan`);
    await _assertOk(r, "scanBucket");
    return r.json();
  }

  /** V3 Reader: full event stream + final trace. */
  async readBucket(id: string): Promise<ReadResult> {
    const r = await fetch(`${this.base}/v1/buckets/${encodeURIComponent(id)}/reader/read`);
    await _assertOk(r, "readBucket");
    return r.json();
  }

  /** V3 Reader: current trace only (the continuous observation surface). */
  async readerTrace(id: string): Promise<ReaderTrace> {
    const r = await fetch(`${this.base}/v1/buckets/${encodeURIComponent(id)}/reader/trace`);
    await _assertOk(r, "readerTrace");
    return r.json();
  }
}
