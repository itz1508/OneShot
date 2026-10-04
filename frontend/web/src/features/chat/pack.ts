/**
 * Pure, dependency-free helpers for the chat intake composer.
 *
 * No React. No I/O. The reducer and the view use these for routing
 * decisions and error presentation.
 */

export type AttachmentKind =
  | "text"
  | "markdown"
  | "pdf"
  | "chatgpt_export"
  | "zip"
  | "opaque";

export type AttachmentState =
  | "QUEUED"
  | "STAGING"
  | "LOADING"
  | "VERIFYING"
  | "ACCEPTED"
  | "REJECTED"
  | "FAILED"
  | "CANCELLED";

export const TERMINAL_STATES: ReadonlySet<AttachmentState> = new Set([
  "ACCEPTED",
  "REJECTED",
  "FAILED",
  "CANCELLED",
]);

/**
 * Classify a File by its extension (lowercased).
 *
 * Deliberately simple: the backend already dispatches by `kind` on the
 * server side; this routing only picks which `kind` to send.
 */
export function kindFor(file: File): AttachmentKind {
  const name = file.name.toLowerCase();
  if (name.endsWith(".md") || name.endsWith(".markdown")) return "markdown";
  if (name.endsWith(".pdf")) return "pdf";
  if (name.endsWith(".zip")) return "zip";
  if (name.endsWith(".txt") || name.endsWith(".log") || name.endsWith(".html") ||
      name.endsWith(".xml")) {
    return "text";
  }
  if (name.endsWith(".json")) return "chatgpt_export";
  return "opaque";
}

/** 64-char hex, lowercase expected. */
export function isValidSha256Hex(s: string): boolean {
  return /^[0-9a-f]{64}$/i.test(s.trim());
}

/**
 * Human-readable label for an RSM error code. Falls back to the code
 * itself when unknown so no error path is swallowed.
 */
export function labelForCode(code: string | null | undefined, fallback = "Rejected"): string {
  if (!code) return fallback;
  switch (code) {
    case "HASH_MISMATCH":   return "Rejected: supplied hash did not match";
    case "ARCHIVE_SAFETY":  return "Rejected: unsafe archive";
    case "MISSING_FILE":    return "Rejected: no file in request";
    case "UNSUPPORTED_KIND":return "Rejected: unsupported source kind";
    case "RSM_DISABLED":    return "Rejected: RSM is disabled for this interaction";
    case "BUCKET_FROZEN":   return "Rejected: bucket is frozen";
    case "BUCKET_NOT_FOUND":return "Rejected: bucket not found";
    default: return `Rejected: ${code}`;
  }
}
