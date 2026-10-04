import { RsmClient } from "@/lib/rsm-client";

/**
 * Base URL of the authoritative RSM daemon.
 *
 * `NEXT_PUBLIC_RSM_BASE_URL` is inlined by Next.js at build time — the only
 * environment read in the frontend (ADR 0018; docs/deployment.md). The
 * default preserves the dev-host contract: daemon on loopback :8787 with
 * the CORS origins from `rsm.conf.toml [daemon] allowed_origins`.
 */
export const RSM_BASE_URL: string =
  process.env.NEXT_PUBLIC_RSM_BASE_URL ?? "http://127.0.0.1:8787";

/** Construct the client every surface uses (no browser-side state — ADR 0001). */
export function createRsmClient(): RsmClient {
  return new RsmClient(RSM_BASE_URL);
}